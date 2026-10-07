"""Malformed native messages et privacy du vrai host candidat."""
import json
import struct
import subprocess
import uuid
from common import *
from lab import Lab
from session_v2.native_host import validate as native_validate, correlate, EXTENSION_ID
from session_v2.storage import private_dir, atomic
from session_v2.errors import Failure


def main():
    results = []
    good = {"op": "map-window", "uuid": str(uuid.uuid4()), "runtime_token": "a" * 32}
    for index, value in enumerate((None, [], {}, {**good, "op": "exec"}, {**good, "uuid": True},
                                  {**good, "uuid": "a" * 4096}, {**good, "runtime_token": "x" * 33},
                                  {**good, "argv": []}, {**good, "title": "synthetic"}, {**good, "environment": {}})):
        try: native_validate(value)
        except Failure: results.append({"name": f"schema-{index}", "pass": True})
        else: raise AssertionError(index)
    class Reader:
        def windows(self):
            return [{"id": 1, "app_id": "firefox", "name": "[LABFY:" + good["runtime_token"] + "] ignored"}]
    assert correlate(Reader(), good) == 1
    results.append({"name": "read-only-correlation", "pass": True})
    class Collision:
        def windows(self): return Reader().windows() * 2
    try: correlate(Collision(), good)
    except Failure as e: assert e.code == "EXACT_WINDOW_IDENTITY_COLLISION"
    else: raise AssertionError("collision")
    results.append({"name": "surface-collision", "pass": True})
    with Lab() as lab:
        env = {**lab.env, "HOME": str(private_dir(lab.directory / "home")), "XDG_STATE_HOME": str(private_dir(lab.directory / "state"))}
        messages = [struct.pack("=I", 0), struct.pack("=I", 4097), struct.pack("=I", 2) + b"[", struct.pack("=I", 1) + b"\xff"]
        for raw in (b'{"op":1,"op":2}', b'{"op":NaN}', b'[]', b'{"command":"x"}'):
            messages.append(struct.pack("=I", len(raw)) + raw)
        for i, message in enumerate(messages):
            proc = subprocess.run([sys.executable, "-B", str(BACKEND / "session-v2-native-host.py"), "/unused-private-manifest", EXTENSION_ID],
                                  env=env, input=message, capture_output=True, timeout=8)
            # Une troncature proprement fermée est EOF ; jamais trace ni payload.
            assert not proc.stderr
            if proc.stdout:
                size, = struct.unpack("=I", proc.stdout[:4]); response = json.loads(proc.stdout[4:])
                assert size <= 4096 and set(response) == {"result"} and response["result"] != "OK"
            results.append({"name": f"wire-{i}", "pass": True})
        denied = subprocess.run([sys.executable, "-B", str(BACKEND / "session-v2-native-host.py"), "unused", "other@invalid"],
                                env=env, capture_output=True, timeout=5)
        assert denied.returncode == 1 and not denied.stdout and not denied.stderr
        results.append({"name": "extension-id-allowlist", "pass": True})
    manifest = json.loads((REPO / "firefox-extension/session-v2/manifest.json").read_text())
    assert set(manifest["permissions"]) == {"sessions", "nativeMessaging"} and "content_scripts" not in manifest and "host_permissions" not in manifest
    background = (REPO / "firefox-extension/session-v2/background.js").read_text()
    assert not any(s in background for s in ("browser.tabs.", "browser.history.", "browser.cookies.", "getRecentlyClosed", "labfy_test_control", "ExecuteScript"))
    results.append({"name": "minimal-permissions-no-navigation", "pass": True})
    atomic(private_dir(EVIDENCE) / "security.json", {"cases": results})
    print(len(results), "security PASS")


if __name__ == "__main__": main()
