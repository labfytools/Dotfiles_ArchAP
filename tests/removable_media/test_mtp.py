import importlib.util
from importlib.machinery import SourceFileLoader
import json
import stat
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).parents[2] / "bin/.local/bin/labfy-removable-media"
SPEC = importlib.util.spec_from_loader(
    "labfy_removable_media_mtp", SourceFileLoader("labfy_removable_media_mtp", str(SCRIPT))
)
assert SPEC and SPEC.loader
media = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = media
SPEC.loader.exec_module(media)


class FakeRoot:
    def __init__(self, scheme="mtp", path=None, uri="mtp://fake-device/"):
        self.scheme = scheme
        self.path = path
        self.uri = uri

    def get_uri_scheme(self):
        return self.scheme

    def get_path(self):
        return self.path

    def get_uri(self):
        return self.uri

    def query_filesystem_info(self, _attributes, _cancellable):
        return type("Info", (), {"get_attribute_uint64": lambda self, _name: 1234})()


class FakeMount:
    def __init__(self, volume, path):
        self.volume = volume
        self.root = FakeRoot(path=path)

    def get_root(self):
        return self.root

    def get_name(self):
        return "Stockage du téléphone"

    def unmount_with_operation(self, _flags, _operation, _cancellable, callback):
        self.volume.pending = lambda: setattr(self.volume, "current_mount", None)
        callback(self, object())

    def unmount_with_operation_finish(self, _result):
        self.volume.pending()


class FakeVolume:
    def __init__(self, scheme="mtp", name="Téléphone"):
        self.activation = FakeRoot(scheme=scheme)
        self.name = name
        self.current_mount = None
        self.pending = None
        self.mount_calls = 0

    def get_activation_root(self):
        return self.activation

    def get_name(self):
        return self.name

    def get_mount(self):
        return self.current_mount

    def mount(self, _flags, _operation, _cancellable, callback):
        self.mount_calls += 1
        self.pending = lambda: setattr(
            self, "current_mount", FakeMount(self, "/run/user/1000/gvfs/mtp:host=fake")
        )
        callback(self, object())

    def mount_finish(self, _result):
        self.pending()


class FakeMonitor:
    def __init__(self, volumes):
        self.volumes = volumes
        self.callbacks = {}

    def get_volumes(self):
        return list(self.volumes)

    def connect(self, signal, callback):
        self.callbacks[signal] = callback


class FakeCancellable:
    def __init__(self):
        self.cancelled = False

    def cancel(self):
        self.cancelled = True


class FakeGio:
    class Cancellable:
        @staticmethod
        def new():
            return FakeCancellable()

    class MountMountFlags:
        NONE = 0

    class MountUnmountFlags:
        NONE = 0


class FakeGLib:
    def __init__(self):
        self.sources = {}
        self.next_source = 0

    def timeout_add_seconds(self, _delay, callback):
        self.next_source += 1
        self.sources[self.next_source] = callback
        return self.next_source

    def timeout_add(self, _delay, callback, *args):
        self.next_source += 1
        self.sources[self.next_source] = lambda: callback(*args)
        return self.next_source

    def source_remove(self, source):
        self.sources.pop(source, None)


class MTPBackendTests(unittest.TestCase):
    def backend(self, volumes):
        return media.MTPBackend(FakeGio, FakeGLib(), FakeMonitor(volumes))

    def test_classifies_only_activation_root_mtp_and_uses_opaque_ids(self):
        mtp = FakeVolume("mtp")
        backend = self.backend([mtp, FakeVolume("gphoto2"), FakeVolume(None)])

        records = backend.records()

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].kind, "mtp")
        self.assertTrue(records[0].path.startswith("mtp:"))
        self.assertNotIn("Téléphone", records[0].path)
        self.assertNotIn("mtp://", records[0].path)
        self.assertEqual(records[0].actions(), ["mount"])

    def test_mount_and_safe_remove_complete_async_with_real_root_path(self):
        volume = FakeVolume()
        backend = self.backend([volume])
        runtime_id = backend.records()[0].path
        completed = []

        backend.operate_async(runtime_id, "mount", lambda path, error: completed.append((path, error)))
        self.assertEqual(completed, [("/run/user/1000/gvfs/mtp:host=fake", None)])
        mounted = backend.records()[0]
        self.assertEqual(mounted.mount_point, "/run/user/1000/gvfs/mtp:host=fake")
        self.assertEqual(mounted.display_name, "Stockage du téléphone")
        self.assertEqual(mounted.actions(), ["unmount", "open", "safe-remove"])

        completed.clear()
        backend.operate_async(runtime_id, "safe-remove", lambda path, error: completed.append((path, error)))
        self.assertEqual(completed, [("", None)])
        self.assertIsNone(volume.get_mount())

    def test_mounted_without_local_path_omits_only_open(self):
        volume = FakeVolume()
        volume.current_mount = FakeMount(volume, None)
        record = self.backend([volume]).records()[0]

        self.assertTrue(record.public()["mounted"])
        self.assertEqual(record.mount_point, "")
        self.assertEqual(record.actions(), ["unmount", "safe-remove"])

    def test_disappearance_rejects_stale_runtime_id(self):
        volume = FakeVolume()
        backend = self.backend([volume])
        runtime_id = backend.records()[0].path
        backend.monitor.volumes = []

        with self.assertRaisesRegex(media.RequestError, "introuvable"):
            backend.operate_async(runtime_id, "mount", lambda *_args: None)

    def test_new_wrappers_keep_id_and_live_wrapper_is_used_for_action(self):
        shared = {"mount": None}

        class RewrappedVolume(FakeVolume):
            def get_mount(self):
                return shared["mount"]

            def mount(self, _flags, _operation, _cancellable, callback):
                shared["mount"] = FakeMount(
                    self, "/run/user/1000/gvfs/mtp:host=fake"
                )
                callback(self, object())

            def mount_finish(self, _result):
                pass

        class RewrappingMonitor(FakeMonitor):
            def __init__(self):
                super().__init__([])
                self.calls = 0
                self.last_wrapper = None

            def get_volumes(self):
                self.calls += 1
                self.last_wrapper = RewrappedVolume(name=f"Wrapper {self.calls}")
                return [self.last_wrapper]

        monitor = RewrappingMonitor()
        backend = media.MTPBackend(FakeGio, FakeGLib(), monitor)

        first_id = backend.records()[0].path
        second_id = backend.records()[0].path
        completed = []
        backend.operate_async(
            first_id, "mount", lambda path, error: completed.append((path, error))
        )

        self.assertEqual(second_id, first_id)
        self.assertGreaterEqual(monitor.calls, 3)
        self.assertIsNotNone(monitor.last_wrapper.get_mount())
        self.assertEqual(completed, [("/run/user/1000/gvfs/mtp:host=fake", None)])

    def test_observed_removal_invalidates_id_before_same_uri_reinsertion(self):
        first = FakeVolume()
        monitor = FakeMonitor([first])
        backend = media.MTPBackend(FakeGio, FakeGLib(), monitor)
        backend.connect_changed(lambda: None)
        first_id = backend.records()[0].path

        monitor.callbacks["volume-removed"](monitor, first)
        monitor.volumes = [FakeVolume()]

        self.assertNotEqual(backend.records()[0].path, first_id)

    def test_timeout_cancels_pending_mount_and_returns_bounded_french_error(self):
        class PendingVolume(FakeVolume):
            def mount(self, _flags, _operation, cancellable, _callback):
                self.cancellable = cancellable

        volume = PendingVolume()
        backend = self.backend([volume])
        runtime_id = backend.records()[0].path
        completed = []
        backend.operate_async(
            runtime_id, "mount", lambda path, error: completed.append((path, error))
        )
        timeout = next(iter(backend.GLib.sources.values()))

        self.assertFalse(timeout())
        self.assertTrue(volume.cancellable.cancelled)
        self.assertIsInstance(completed[0][1], media.RequestError)
        self.assertIn("Délai d'opération MTP dépassé", str(completed[0][1]))


class CompositeBackend:
    def __init__(self, mtp_backend):
        self.mtp = mtp_backend

    def records(self):
        return self.mtp.records()

    def operate_mtp_async(self, runtime_id, operation, callback):
        return self.mtp.operate_async(runtime_id, operation, callback)


class MTPDaemonTests(unittest.TestCase):
    def test_public_v2_snapshot_uses_opaque_id_and_authoritative_mount_path(self):
        volume = FakeVolume(name="Téléphone de test")
        raw_uri = "mtp://[usb:001,007]/raw-serial-ABC-123/"
        volume.activation.uri = raw_uri
        # CONTRACT: GVFS peut inclure une identité dans son chemin local ; ce
        # chemin exact reste nécessaire à Yazi et le snapshot est privé (0600).
        mount_path = "/run/user/1000/gvfs/mtp:host=raw-serial-ABC-123"
        volume.current_mount = FakeMount(volume, mount_path)

        with tempfile.TemporaryDirectory() as directory:
            state_path = Path(directory) / media.STATE_NAME
            daemon = media.MediaDaemon(
                CompositeBackend(media.MTPBackend(FakeGio, FakeGLib(), FakeMonitor([volume]))),
                state_path,
            )

            state = daemon.state()
            device = state["devices"][0]
            snapshot = state_path.read_text()
            snapshot_mode = stat.S_IMODE(state_path.stat().st_mode)

        self.assertEqual(state["version"], 2)
        self.assertEqual(
            set(device),
            {
                "runtime_id", "safe_remove_runtime_id", "kind", "actions",
                "display_name", "label", "filesystem", "size_bytes",
                "mount_point", "mounted", "removable", "ejectable",
                "power_off_capable", "busy", "error",
            },
        )
        self.assertEqual(device["kind"], "mtp")
        self.assertEqual(device["actions"], ["unmount", "open", "safe-remove"])
        self.assertTrue(device["mounted"])
        self.assertTrue(device["runtime_id"].startswith("mtp:"))
        self.assertEqual(device["runtime_id"], device["safe_remove_runtime_id"])
        self.assertEqual(device["mount_point"], mount_path)
        self.assertNotIn("mtp://", device["runtime_id"])
        self.assertNotIn("raw-serial-ABC-123", device["runtime_id"])
        self.assertNotIn(raw_uri, json.dumps(state, ensure_ascii=False))
        self.assertIn(mount_path, snapshot)
        self.assertEqual(snapshot_mode, 0o600)

    def test_manual_unmount_is_not_automounted_again(self):
        volume = FakeVolume()
        monitor = FakeMonitor([volume])
        mtp = media.MTPBackend(FakeGio, FakeGLib(), monitor)
        with tempfile.TemporaryDirectory() as directory:
            daemon = media.MediaDaemon(
                CompositeBackend(mtp), Path(directory) / media.STATE_NAME
            )
            mtp.connect_changed(daemon.devices_changed)
            daemon.start()
            runtime_id = daemon.state()["devices"][0]["runtime_id"]
            self.assertEqual(volume.mount_calls, 1)
            replies = []
            daemon.handle_async(
                {"operation": "unmount", "runtime_id": runtime_id}, replies.append
            )
            monitor.callbacks["mount-changed"](monitor, None)

            self.assertEqual(len(replies), 1)
            self.assertFalse(daemon.state()["devices"][0]["mounted"])
            self.assertEqual(volume.mount_calls, 1)
            self.assertIn("volume-changed", monitor.callbacks)
            self.assertIn("mount-changed", monitor.callbacks)


if __name__ == "__main__":
    unittest.main()
