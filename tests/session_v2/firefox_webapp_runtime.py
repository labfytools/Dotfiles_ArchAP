"""TEST_ONLY: real Firefox webapp-first capture under a private Sway and profile.

No user browser, profile, bus, socket, checkpoint, or extension is modified.
Marionette system access is enabled only for this owned disposable browser.
"""
import argparse
import http.server
import json
import os
from pathlib import Path
import shutil
import socket
import threading
import time
from common import BACKEND
from lab import Lab, until
from session_v2.ipc import Sway
from session_v2.firefox_identity import FirefoxProvider
from session_v2.errors import Failure

APP_UUID = "fcd72ebe-94c5-4209-b3f6-bbaa7784cded"
WEBAPP = "firefox.webapp-" + APP_UUID
WINDOW_UUID = "11111111-2222-4333-8444-555555555555"
KEY = "extension:session-v2@labfy.org:labfy.session.window_uuid"


class TestPage(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        body = b"<!doctype html><title>TEST_ONLY</title><p>TEST_ONLY</p>"
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_):
        pass


class Marionette:
    def __init__(self, port):
        end = time.monotonic() + 20
        while True:
            try:
                self.connection = socket.create_connection(("127.0.0.1", port), timeout=2)
                break
            except OSError:
                if time.monotonic() > end:
                    raise RuntimeError("TEST_FIREFOX_NOT_READY")
                time.sleep(.1)
        self.connection.settimeout(25)
        hello = self.receive()
        assert hello == {"applicationType": "gecko", "marionetteProtocol": 3}
        self.sequence = 0
        self.call("WebDriver:NewSession", {"capabilities": {}})
        self.call("Marionette:SetContext", {"value": "chrome"})

    def receive(self):
        header = bytearray()
        while not header.endswith(b":"):
            part = self.connection.recv(1)
            if not part:
                raise RuntimeError("MARIONETTE_CLOSED")
            header.extend(part)
            assert len(header) < 12
        length = int(header[:-1])
        assert 0 < length < 4 * 1024 * 1024
        data = bytearray()
        while len(data) < length:
            part = self.connection.recv(length - len(data))
            if not part:
                raise RuntimeError("MARIONETTE_CLOSED")
            data.extend(part)
        return json.loads(data)

    def call(self, name, arguments):
        self.sequence += 1
        raw = json.dumps([0, self.sequence, name, arguments]).encode()
        self.connection.sendall(str(len(raw)).encode() + b":" + raw)
        response = self.receive()
        assert response[:2] == [1, self.sequence], response
        if response[2] is not None:
            raise RuntimeError(response[2])
        return response[3]

    def script(self, body, arguments=()):
        script = """const done = arguments[arguments.length - 1];
const args = Array.from(arguments).slice(0, -1);
(async () => { BODY })().then(
  value => done({ok: true, value}),
  error => done({ok: false, error: String(error), stack: error.stack})
);""".replace("BODY", body)
        result = self.call("WebDriver:ExecuteAsyncScript", {
            "script": script, "args": list(arguments), "newSandbox": True,
            "sandbox": "default", "line": 1, "filename": "TEST_ONLY"
        })["value"]
        assert result["ok"], result
        return result.get("value")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--extension", type=Path, required=True)
    parser.add_argument("--expect", choices=("success", "unavailable"), required=True)
    args = parser.parse_args()
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), TestPage)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with Lab() as lab:
            print("TEST_ONLY_DIRECTORY=" + str(lab.directory), flush=True)
            profile = lab.directory / "firefox-profile"
            profile.mkdir(mode=0o700)
            extension = lab.directory / "companion.xpi"
            shutil.copyfile(args.extension, extension)
            reservation = socket.socket()
            reservation.bind(("127.0.0.1", 0))
            port = reservation.getsockname()[1]
            reservation.close()
            url = f"http://127.0.0.1:{server.server_port}/TEST_ONLY"
            prefs = {
                "marionette.port": port, "browser.taskbarTabs.enabled": True,
                "browser.startup.page": 0, "browser.startup.homepage": "about:blank",
                "browser.shell.checkDefaultBrowser": False,
                "browser.aboutwelcome.enabled": False,
                "startup.homepage_welcome_url": "",
                "datareporting.policy.dataSubmissionEnabled": False,
                "toolkit.telemetry.reportingpolicy.firstRun": False,
            }
            (profile / "user.js").write_text("".join(
                "user_pref(" + json.dumps(k) + ", " + json.dumps(v) + ");\n"
                for k, v in prefs.items()))
            taskbars = profile / "taskbartabs"
            taskbars.mkdir(mode=0o700)
            (taskbars / "taskbartabs.json").write_text(json.dumps({
                "version": 1, "taskbarTabs": [{
                    "id": APP_UUID, "scopes": [{"hostname": "127.0.0.1"}],
                    "startUrl": url, "name": "TEST_ONLY", "userContextId": 0,
                }]
            }))
            native_dir = Path(lab.env["XDG_CONFIG_HOME"]) / "mozilla/native-messaging-hosts"
            native_dir.mkdir(parents=True, mode=0o700)
            (Path(lab.env["HOME"]) / ".mozilla").symlink_to(native_dir.parent)
            (native_dir / "org.labfy.session_v2_identity.json").write_text(json.dumps({
                "name": "org.labfy.session_v2_identity",
                "description": "TEST_ONLY", "type": "stdio",
                "path": str(BACKEND / "session-v2-native-host.py"),
                "allowed_extensions": ["session-v2@labfy.org"],
            }))
            # Existing state prevents automatic baseline mint in BOTH versions.
            automatic = Path(lab.env["XDG_STATE_HOME"]) / "labfy-sway/session-v2/automatic"
            automatic.mkdir(parents=True, mode=0o700)
            (automatic / "last.json").write_text('{"TEST_ONLY":true}\n')
            env = dict(lab.env, MOZ_ENABLE_WAYLAND="1", MOZ_CRASHREPORTER_DISABLE="1")
            lab.spawn([
                "/usr/bin/dbus-run-session", "--", "/usr/lib/firefox/firefox",
                "--no-remote", "--profile", str(profile), "--marionette",
                "-remote-allow-system-access", "-taskbar-tab", APP_UUID,
                "-new-window", url, "-container", "0",
            ], env=env)
            control = Marionette(port)
            sway = Sway(lab.socket)
            until(lambda: any(n["app_id"] == WEBAPP for n in sway.windows()), timeout=10)
            initial = [n["app_id"] for n in sway.windows()]
            assert initial == [WEBAPP], initial
            created = control.script("""
const {BrowserWindowTracker} = ChromeUtils.importESModule("resource:///modules/BrowserWindowTracker.sys.mjs");
const {SessionStore} = ChromeUtils.importESModule("moz-src:///browser/components/sessionstore/SessionStore.sys.mjs");
const win = await BrowserWindowTracker.promiseOpenWindow({});
await SessionStore.promiseInitialized;
SessionStore.setCustomWindowValue(win, args[0], JSON.stringify(args[1]));
return {normalID: win.docShell.browsingContext.id};
""", [KEY, WINDOW_UUID])
            assert isinstance(created.get("normalID"), int), created
            until(lambda: any(n["app_id"] == "firefox" for n in sway.windows()), timeout=10)
            installed = control.script("""
const {AddonManager} = ChromeUtils.importESModule("resource://gre/modules/AddonManager.sys.mjs");
const file = Cc["@mozilla.org/file/local;1"].createInstance(Ci.nsIFile);
file.initWithPath(args[0]);
const addon = await AddonManager.installTemporaryAddon(file);
return {id: addon.id, version: addon.version};
""", [str(extension)])
            assert installed["id"] == "session-v2@labfy.org"
            print("INSTALLED_TEST_ONLY=" + json.dumps(installed), flush=True)
            time.sleep(2)
            nodes = [n for n in sway.windows() if n["app_id"] == "firefox"]
            assert len(nodes) == 1
            runtime = Path(lab.env["XDG_RUNTIME_DIR"]) / "labfy-sway"
            provider = FirefoxProvider(sway, runtime)
            result = {}
            try:
                mapping = provider.capture(nodes, timeout=6)
                result = {"status": "success", "mapping_matches": mapping == {WINDOW_UUID: nodes[0]["id"]}}
                assert result["mapping_matches"], result
            except Failure as error:
                result = {"status": "unavailable", "reason": error.code}
                assert error.code == "FIREFOX_IDENTITY_PROVIDER_UNAVAILABLE"
            metadata = control.script("""
const {SessionStore} = ChromeUtils.importESModule("moz-src:///browser/components/sessionstore/SessionStore.sys.mjs");
const windows = Array.from(Services.wm.getEnumerator("navigator:browser"));
return windows.map(win => ({
  runtimeWindowID: win.docShell.browsingContext.id,
  value: SessionStore.getCustomWindowValue(win, args[0]) || null
}));
""", [KEY])
            assert len(metadata) == 2, metadata
            assert [r["value"] for r in metadata if r["runtimeWindowID"] != created["normalID"]] == [None], metadata
            assert [r["value"] for r in metadata if r["runtimeWindowID"] == created["normalID"]] == [json.dumps(WINDOW_UUID)], metadata
            assert result["status"] == args.expect, result
            result.update(extension_version=installed["version"], webapp_first=True,
                          webapp_never_enrolled=True, browser_uuid_unchanged=True,
                          isolated_profile=True, isolated_sway=True)
            (lab.directory / "firefox-webapp-result.json").write_text(json.dumps(result, indent=2))
            print("FIREFOX_WEBAPP_RUNTIME=" + json.dumps(result), flush=True)
            control.connection.close()
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    main()
