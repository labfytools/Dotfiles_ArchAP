import importlib.util
from importlib.machinery import SourceFileLoader
import json
import stat
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path


SCRIPT = Path(__file__).parents[2] / "bin/.local/bin/labfy-removable-media"
SPEC = importlib.util.spec_from_loader(
    "labfy_removable_media", SourceFileLoader("labfy_removable_media", str(SCRIPT))
)
assert SPEC and SPEC.loader
media = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = media
SPEC.loader.exec_module(media)


def record(path, drive="/org/freedesktop/UDisks2/drives/usb", mount=""):
    return media.FilesystemRecord(
        path=f"/org/freedesktop/UDisks2/block_devices/{path}",
        drive_path=drive,
        display_name=path,
        label=path.upper(),
        filesystem="vfat",
        size_bytes=1024,
        mount_point=mount,
        removable=True,
        ejectable=True,
        power_off_capable=True,
    )


class FakeBackend:
    def __init__(self, records):
        self.items = records
        self.calls = []

    def records(self):
        return list(self.items)

    def _change_mount(self, path, value):
        self.items = [
            replace(item, mount_point=value if item.path == path else item.mount_point)
            for item in self.items
        ]

    def mount(self, path):
        self.calls.append(("mount", path))
        self._change_mount(path, f"/run/media/test/{Path(path).name}")
        return self.mount_points_sync(path)

    def unmount(self, path):
        self.calls.append(("unmount", path))
        self._change_mount(path, "")
        return []

    def mount_points_sync(self, path):
        for item in self.items:
            if item.path == path:
                return [item.mount_point.encode() + b"\0"] if item.mount_point else []
        raise media.RequestError("Volume introuvable après la demande")

    def safe_remove(self, drive):
        self.calls.append(("safe-remove", drive.drive_path))


class FakeInterface:
    def __init__(self, name, **properties):
        self.name = name
        self.properties = properties

    def get_interface_name(self):
        return self.name

    def get_cached_property(self, name):
        return self.properties.get(name)


class FakeObject:
    def __init__(self, path, *interfaces):
        self.path = path
        self.interfaces = interfaces

    def get_object_path(self):
        return self.path

    def get_interfaces(self):
        return self.interfaces


class MediaDaemonTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.state_path = Path(self.temporary.name) / media.STATE_NAME

    def tearDown(self):
        self.temporary.cleanup()

    def test_state_contract_and_private_atomic_file(self):
        backend = FakeBackend([record("sdb1", mount="/run/media/test/A")])
        daemon = media.MediaDaemon(backend, self.state_path)

        state = daemon.state()
        self.assertEqual(state["schema"], "labfy.removable-media")
        self.assertEqual(state["version"], 2)
        self.assertEqual(set(state), {"schema", "version", "devices", "updated_at"})
        self.assertEqual(
            set(state["devices"][0]),
            {
                "runtime_id", "safe_remove_runtime_id", "kind", "actions",
                "display_name", "label",
                "filesystem", "size_bytes", "mount_point", "mounted",
                "removable", "ejectable", "power_off_capable", "busy", "error",
            },
        )
        self.assertTrue(state["devices"][0]["mounted"])
        self.assertEqual(state["devices"][0]["kind"], "block")
        self.assertEqual(
            state["devices"][0]["safe_remove_runtime_id"],
            "/org/freedesktop/UDisks2/drives/usb",
        )
        self.assertEqual(stat.S_IMODE(self.state_path.stat().st_mode), 0o600)
        self.assertEqual(json.loads(self.state_path.read_text()), state)

    def test_mount_and_unmount_only_apply_to_selected_volume(self):
        first, second = record("sdb1"), record("sdb2")
        other = record("sdc1", "/org/freedesktop/UDisks2/drives/other")
        backend = FakeBackend([first, second, other])
        daemon = media.MediaDaemon(backend, self.state_path)

        daemon.handle({"operation": "mount", "runtime_id": first.path})
        self.assertEqual(
            backend.calls,
            [("mount", first.path)],
        )
        daemon.handle({"operation": "unmount", "runtime_id": first.path})
        self.assertEqual(
            backend.calls[-1:],
            [("unmount", first.path)],
        )

    def test_safe_remove_is_delegated_once_at_drive_scope(self):
        first = record("sdb1", mount="/run/media/test/one")
        second = record("sdb2", mount="/run/media/test/two")
        backend = FakeBackend([first, second])
        daemon = media.MediaDaemon(backend, self.state_path)

        daemon.handle({"operation": "safe-remove", "runtime_id": first.drive_path})
        self.assertEqual(
            backend.calls,
            [("safe-remove", first.drive_path)],
        )

    def test_stale_runtime_id_is_rejected_after_revalidation(self):
        item = record("sdb1")
        backend = FakeBackend([item])
        daemon = media.MediaDaemon(backend, self.state_path)
        backend.items = []

        with self.assertRaisesRegex(media.RequestError, "introuvable"):
            daemon.handle({"operation": "mount", "runtime_id": item.path})
        self.assertEqual(backend.calls, [])

    def test_open_mounts_then_launches_selected_mountpoint(self):
        item = record("sdb1")
        backend = FakeBackend([item])
        launched = []
        daemon = media.MediaDaemon(backend, self.state_path, launched.append)

        daemon.handle({"operation": "open", "runtime_id": item.path})
        self.assertEqual(launched, ["/run/media/test/sdb1"])

    def test_error_is_bounded_and_published(self):
        class FailingBackend(FakeBackend):
            def mount(self, path):
                raise RuntimeError("x" * 500)

        item = record("sdb1")
        daemon = media.MediaDaemon(FailingBackend([item]), self.state_path)
        with self.assertRaises(media.RequestError):
            daemon.handle({"operation": "mount", "runtime_id": item.path})
        self.assertEqual(len(daemon.state()["devices"][0]["error"]), media.MAX_ERROR)

    def test_device_busy_is_translated_and_preserves_mounted_state(self):
        item = record("sda1", mount="/run/media/test/Ventoy")

        class BusyUnmountBackend(FakeBackend):
            def unmount(self, path):
                self.calls.append(("unmount", path))
                raise RuntimeError(
                    "g-io-error-quark: "
                    "GDBus.Error:org.freedesktop.UDisks2.Error.DeviceBusy: "
                    "Error unmounting /dev/sda1: target is busy (36)"
                )

        backend = BusyUnmountBackend([item])
        daemon = media.MediaDaemon(backend, self.state_path)

        with self.assertRaisesRegex(
            media.RequestError, "Le périphérique est utilisé par une application\\."
        ):
            daemon.handle({"operation": "unmount", "runtime_id": item.path})

        device = daemon.state()["devices"][0]
        self.assertTrue(device["mounted"])
        self.assertEqual(device["error"], "Le périphérique est utilisé par une application.")

    def test_start_automounts_each_existing_unmounted_volume_once(self):
        first, second = record("sdb1"), record("sdb2", mount="/media/already")
        backend = FakeBackend([first, second])
        daemon = media.MediaDaemon(backend, self.state_path)

        daemon.start()
        daemon.devices_changed()

        self.assertEqual(backend.calls, [("mount", first.path)])
        self.assertTrue(daemon.state()["devices"][0]["mounted"])

    def test_added_object_is_mounted_once_despite_duplicate_property_events(self):
        backend = FakeBackend([])
        daemon = media.MediaDaemon(backend, self.state_path)
        daemon.start()
        item = record("sdb1")
        backend.items = [item]

        daemon.devices_changed()
        daemon.devices_changed()

        self.assertEqual(backend.calls, [("mount", item.path)])

    def test_manual_unmount_stays_unmounted_on_later_event(self):
        item = record("sdb1")
        backend = FakeBackend([item])
        daemon = media.MediaDaemon(backend, self.state_path)
        daemon.start()
        backend.calls.clear()

        daemon.handle({"operation": "unmount", "runtime_id": item.path})
        daemon.devices_changed()

        self.assertEqual(backend.calls, [("unmount", item.path)])
        self.assertFalse(daemon.state()["devices"][0]["mounted"])

    def test_automount_failure_is_isolated_and_not_retried_until_reinserted(self):
        first, second = record("sdb1"), record("sdb2")

        class OneFailureBackend(FakeBackend):
            def mount(self, path):
                self.calls.append(("mount", path))
                if path == first.path:
                    raise RuntimeError("échec " + "x" * 500)
                self._change_mount(path, "/media/second")

        backend = OneFailureBackend([first, second])
        daemon = media.MediaDaemon(backend, self.state_path)
        daemon.start()
        daemon.devices_changed()

        state = {item["runtime_id"]: item for item in daemon.state()["devices"]}
        self.assertEqual(backend.calls, [("mount", first.path), ("mount", second.path)])
        self.assertEqual(len(state[first.path]["error"]), media.MAX_ERROR)
        self.assertTrue(state[second.path]["mounted"])
        self.assertEqual(state[second.path]["error"], "")

        backend.items = [second]
        daemon.devices_changed()
        backend.items = [first, second]
        daemon.devices_changed()
        self.assertEqual(backend.calls.count(("mount", first.path)), 2)

    def test_manual_mount_uses_real_mountpoint_and_unmount_verifies_state(self):
        item = record("sdb1")

        class StickyUnmountBackend(FakeBackend):
            def mount(self, path):
                self.calls.append(("mount", path))
                self._change_mount(path, "/media/udisks-result")

            def unmount(self, path):
                self.calls.append(("unmount", path))

        backend = StickyUnmountBackend([item])
        launched = []
        daemon = media.MediaDaemon(backend, self.state_path, launched.append)
        daemon.handle({"operation": "open", "runtime_id": item.path})
        self.assertEqual(launched, ["/media/udisks-result"])

        with self.assertRaisesRegex(media.RequestError, "reste monté"):
            daemon.handle({"operation": "unmount", "runtime_id": item.path})


class UDisksBackendTests(unittest.TestCase):
    def test_records_keep_usb_filesystems_only_and_exclude_luks(self):
        usb_drive = "/org/freedesktop/UDisks2/drives/usb"
        sata_drive = "/org/freedesktop/UDisks2/drives/sata"
        drive_interface = media.UDisksBackend.IFACE_DRIVE
        block_interface = media.UDisksBackend.IFACE_BLOCK
        filesystem_interface = media.UDisksBackend.IFACE_FILESYSTEM
        objects = [
            FakeObject(
                usb_drive,
                FakeInterface(
                    drive_interface,
                    ConnectionBus="usb",
                    MediaCompatibility=[],
                    Model="Clé USB",
                    Removable=True,
                    Ejectable=False,
                    CanPowerOff=True,
                ),
            ),
            FakeObject(
                sata_drive,
                FakeInterface(
                    drive_interface,
                    ConnectionBus="ata",
                    MediaCompatibility=[],
                    Model="Disque interne",
                    Removable=True,
                ),
            ),
            FakeObject(
                "/org/freedesktop/UDisks2/block_devices/sdb1",
                FakeInterface(
                    block_interface,
                    Drive=usb_drive,
                    IdUsage="filesystem",
                    IdType="vfat",
                    IdLabel="DONNEES",
                    Size=4096,
                ),
                FakeInterface(filesystem_interface, MountPoints=[b"/run/media/test\0"]),
            ),
            FakeObject(
                "/org/freedesktop/UDisks2/block_devices/sdb2",
                FakeInterface(
                    block_interface,
                    Drive=usb_drive,
                    IdUsage="crypto",
                    IdType="crypto_LUKS",
                    Size=4096,
                ),
                FakeInterface(filesystem_interface, MountPoints=[]),
            ),
            FakeObject(
                "/org/freedesktop/UDisks2/block_devices/sda1",
                FakeInterface(
                    block_interface,
                    Drive=sata_drive,
                    IdUsage="filesystem",
                    IdType="ext4",
                    Size=8192,
                ),
                FakeInterface(filesystem_interface, MountPoints=[b"/\0"]),
            ),
        ]
        backend = media.UDisksBackend.__new__(media.UDisksBackend)
        backend.manager = type("Manager", (), {"get_objects": lambda self: objects})()

        records = backend.records()

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].label, "DONNEES")
        self.assertEqual(records[0].mount_point, "/run/media/test")
        self.assertTrue(records[0].power_off_capable)

    def test_records_exclude_hint_system_and_hint_ignore(self):
        drive_path = "/org/freedesktop/UDisks2/drives/usb"
        drive_interface = media.UDisksBackend.IFACE_DRIVE
        block_interface = media.UDisksBackend.IFACE_BLOCK
        filesystem_interface = media.UDisksBackend.IFACE_FILESYSTEM
        objects = [
            FakeObject(
                drive_path,
                FakeInterface(
                    drive_interface,
                    ConnectionBus="usb",
                    MediaCompatibility=[],
                    Removable=True,
                ),
            )
        ]
        for name, properties in (
            ("visible", {}),
            ("efi", {"HintSystem": True}),
            ("ignored", {"HintIgnore": True}),
        ):
            objects.append(
                FakeObject(
                    f"/org/freedesktop/UDisks2/block_devices/{name}",
                    FakeInterface(
                        block_interface,
                        Drive=drive_path,
                        IdUsage="filesystem",
                        IdType="vfat",
                        **properties,
                    ),
                    FakeInterface(filesystem_interface, MountPoints=[]),
                )
            )
        backend = media.UDisksBackend.__new__(media.UDisksBackend)
        backend.manager = type("Manager", (), {"get_objects": lambda self: objects})()

        self.assertEqual(
            [item.path for item in backend.records()],
            ["/org/freedesktop/UDisks2/block_devices/visible"],
        )

    def test_safe_remove_rechecks_every_filesystem_child_before_power_off(self):
        drive = record("visible", mount="/run/media/test/visible")

        class Backend(media.UDisksBackend):
            def __init__(self):
                self.calls = []
                self.reads = 0

            def _drive_filesystems(self, drive_path):
                self.reads += 1
                return [
                    (drive.path, [b"/run/media/test/visible\0"]),
                    ("/org/freedesktop/UDisks2/block_devices/hidden", [b"/mnt/hidden\0"]),
                ]

            def _drive_filesystems_sync(self, drive_path):
                return self._drive_filesystems(drive_path)

            def unmount(self, path):
                self.calls.append(("unmount", path))

            def _call(self, path, interface, method):
                self.calls.append((method, path))

        backend = Backend()
        with self.assertRaisesRegex(media.RequestError, "reste monté"):
            backend.safe_remove(drive)
        self.assertEqual(backend.reads, 2)
        self.assertEqual(
            backend.calls,
            [
                ("unmount", "/org/freedesktop/UDisks2/block_devices/hidden"),
                ("unmount", drive.path),
            ],
        )


if __name__ == "__main__":
    unittest.main()
