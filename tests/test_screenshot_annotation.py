"""Parcours annotation isolé : aucun vrai écran ni presse-papiers n'est lu."""

import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "sway/.config/sway/scripts/screenshot-region"


class ScreenshotAnnotationTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="annotation test ")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.home = self.root / "home with spaces"
        self.bin = self.root / "fake tools"
        self.runtime = self.root / "runtime with spaces"
        self.bin.mkdir()
        self.runtime.mkdir()
        (self.home / ".local/libexec").mkdir(parents=True)
        (self.home / ".config").mkdir()
        self.pictures = self.root / "Images de test"
        (self.home / ".config/user-dirs.dirs").write_text(
            f'XDG_PICTURES_DIR="{self.pictures}"\n')
        self.png = self.root / "synthetic.png"
        Image.new("RGB", (4, 3), (7, 13, 29)).save(self.png)
        self.log = self.root / "calls.log"
        self.make_tool("swaymsg", "#!/bin/sh\necho '[{\"focused\":true,\"name\":\"eDP-1\"}]'\n")
        self.make_tool("quickshell", """#!/bin/sh
if [ "${TEST_PANELS:-}" = yes ]; then
    marker="$TEST_PANEL_DIR/$5"
    if [ "$6" = toggle ]; then
        touch "$marker"
        echo true
    elif [ -e "$marker" ]; then
        echo '{"loaded":false,"requested":false}'
    else
        echo '{"loaded":true,"requested":true}'
    fi
else
    echo '{"loaded":false}'
fi
""")
        self.make_tool("grim", "#!/bin/sh\necho \"$0\" >> \"$TEST_LOG\"\n[ \"$TEST_CASE\" = grim_fail ] && exit 1\n[ \"$TEST_CASE\" = bad_png ] && { printf 'not a png' > \"$3\"; exit 0; }\ncp \"$TEST_PNG\" \"$3\"\n")
        self.make_tool("wl-copy", "#!/bin/sh\necho \"$0\" >> \"$TEST_LOG\"\n")
        self.make_tool("swappy", """#!/usr/bin/python3
import os, pathlib, sys
p = pathlib.Path(os.environ['TEST_LOG'])
with p.open('a') as out: out.write(sys.argv[0] + '\\n')
assert sys.argv[1] == '--file'
assert pathlib.Path(sys.argv[2]).read_bytes() == pathlib.Path(os.environ['TEST_PNG']).read_bytes()
config_root = pathlib.Path(os.environ['XDG_CONFIG_HOME'])
source_root = pathlib.Path(os.environ['TEST_SOURCE_CONFIG'])
assert config_root != source_root
for shared in ['dconf', 'gtk-3.0']:
    link = config_root / shared
    assert link.is_symlink()
    assert os.readlink(link) == str(source_root / shared)
    for source in (source_root / shared).rglob('*'):
        if source.is_file():
            assert (link / source.relative_to(source_root / shared)).read_bytes() == source.read_bytes()
assert os.environ.get('GTK_THEME') == os.environ.get('TEST_EXPECT_GTK_THEME')
config = config_root / 'swappy/config'
content = config.read_text()
assert 'show_panel=true' in content and 'early_exit=true' in content
assert 'auto_save=false' in content and 'save_dir="$LABFY_SWAPPY_SAVE_DIR"' in content
assert len(sys.argv) == 3
if os.environ['TEST_CASE'] == 'save':
    dest = pathlib.Path(os.environ['LABFY_SWAPPY_SAVE_DIR']) / 'swappy-test.png'
    dest.write_bytes(pathlib.Path(os.environ['TEST_PNG']).read_bytes())
if os.environ['TEST_CASE'] == 'save_slow':
    import time
    time.sleep(0.25)
    dest = pathlib.Path(os.environ['LABFY_SWAPPY_SAVE_DIR']) / 'swappy-test.png'
    dest.write_bytes(pathlib.Path(os.environ['TEST_PNG']).read_bytes())
""")
        selector = self.home / ".local/libexec/labfy-slurp"
        selector.write_text("#!/bin/sh\necho \"$0\" >> \"$TEST_LOG\"\nif [ \"${TEST_PANELS:-}\" = yes ]; then\n  [ -e \"$TEST_PANEL_DIR/clipboardUi-eDP-1\" ] && [ -e \"$TEST_PANEL_DIR/applicationsUi-eDP-1\" ] && [ -e \"$TEST_PANEL_DIR/overviewUi-eDP-1\" ] || exit 17\nfi\ncase \"$TEST_CASE\" in cancel) exit 1;; empty) exit 0;; invalid) echo bogus;; *) echo '10,20 4x3';; esac\n")
        selector.chmod(0o755)

    def make_tool(self, name, body):
        path = self.bin / name
        path.write_text(body)
        path.chmod(0o755)

    def case_env(self, name):
        env = dict(os.environ, HOME=str(self.home), XDG_CONFIG_HOME=str(self.home / ".config"),
                   XDG_RUNTIME_DIR=str(self.runtime),
                   PATH=f"{self.bin}:{os.environ['PATH']}", TEST_CASE=name,
                   TEST_LOG=str(self.log), TEST_PNG=str(self.png),
                   TEST_SOURCE_CONFIG=str(self.home / ".config"))
        env.pop("GTK_THEME", None)
        env.pop("TEST_EXPECT_GTK_THEME", None)
        env.pop("XDG_PICTURES_DIR", None)
        return env

    def run_case(self, name, annotate=True):
        env = self.case_env(name)
        return subprocess.run([str(SCRIPT)] + (["--annotate"] if annotate else []), env=env,
                              capture_output=True, text=True, timeout=10)

    def calls(self):
        return self.log.read_text().splitlines() if self.log.exists() else []

    def expected(self, *names):
        return [str(self.home / ".local/libexec/labfy-slurp") if name == "slurp"
                else str(self.bin / name) for name in names]

    def assert_clean(self):
        self.assertEqual(list(self.runtime.iterdir()), [])

    def test_cancel_and_invalid_geometry(self):
        for case, expected in (("cancel", 0), ("empty", 0), ("invalid", 1)):
            with self.subTest(case=case):
                self.log.unlink(missing_ok=True)
                self.assertEqual(self.run_case(case).returncode, expected)
                self.assertEqual(self.calls(), self.expected("slurp"))
                self.assert_clean()

    def test_grim_failure(self):
        self.assertNotEqual(self.run_case("grim_fail").returncode, 0)
        self.assertEqual(self.calls(), self.expected("slurp", "grim"))
        self.assert_clean()

    def test_invalid_png_never_opens_editor(self):
        self.assertNotEqual(self.run_case("bad_png").returncode, 0)
        self.assertEqual(self.calls(), self.expected("slurp", "grim"))
        self.assert_clean()

    def test_exclusive_panels_close_before_selector(self):
        panel_dir = self.root / "panels"
        panel_dir.mkdir()
        env = self.case_env("close")
        env.update(TEST_PANELS="yes", TEST_PANEL_DIR=str(panel_dir))
        result = subprocess.run([str(SCRIPT), "--annotate"], env=env,
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(list(panel_dir.iterdir())), 3)
        self.assertEqual(self.calls(), self.expected("slurp", "grim", "swappy"))
        self.assert_clean()

    def test_close_does_not_publish_or_copy(self):
        self.assertEqual(self.run_case("close").returncode, 0)
        self.assertEqual(self.calls(), self.expected("slurp", "grim", "swappy"))
        self.assertFalse(self.pictures.exists())
        self.assert_clean()

    def test_explicit_save_and_two_invocations(self):
        for _ in range(2):
            self.assertEqual(self.run_case("save").returncode, 0)
            self.assert_clean()
        images = list((self.pictures / "Screenshots").glob("Screenshot-*.png"))
        self.assertEqual(len(images), 2)
        self.assertEqual(len({p.name for p in images}), 2)
        self.assertTrue(all(p.read_bytes() == self.png.read_bytes() for p in images))
        self.assertNotIn(str(self.bin / "wl-copy"), self.calls())

    def test_overlapping_invocations_have_distinct_outputs(self):
        env = self.case_env("save_slow")
        processes = [subprocess.Popen([str(SCRIPT), "--annotate"], env=env,
                                      stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                     for _ in range(2)]
        for process in processes:
            _, stderr = process.communicate(timeout=10)
            self.assertEqual(process.returncode, 0, stderr.decode())
        images = list((self.pictures / "Screenshots").glob("Screenshot-*.png"))
        self.assertEqual(len(images), 2)
        self.assertEqual(len({p.name for p in images}), 2)
        self.assert_clean()

    def test_system_theme_changes_are_shared_without_copy_or_override(self):
        config = self.home / ".config"
        for shared in ("dconf", "gtk-3.0"):
            (config / shared).mkdir()
        for theme in ("Fixture-Dark", "Fixture-Light"):
            with self.subTest(theme=theme):
                # Données factices : aucune base dconf personnelle n'est lue.
                database = config / "dconf/user"
                settings = config / "gtk-3.0/settings.ini"
                css = config / "gtk-3.0/gtk.css"
                database.write_bytes(("fixture:" + theme).encode())
                settings.write_text("[Settings]\ngtk-theme-name=" + theme + "\n")
                css.write_text("/* CSS système factice " + theme + " */\n")
                before = {p: p.read_bytes() for p in (database, settings, css)}
                result = self.run_case("close")
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual({p: p.read_bytes() for p in before}, before)
                self.assert_clean()

    def test_custom_xdg_config_and_inherited_theme_are_preserved(self):
        config = self.root / "custom config with spaces"
        (config / "dconf").mkdir(parents=True)
        (config / "gtk-3.0").mkdir()
        settings = config / "gtk-3.0/settings.ini"
        settings.write_text("[Settings]\ngtk-theme-name=Fixture-User\n")
        env = self.case_env("close")
        env.update(XDG_CONFIG_HOME=str(config), TEST_SOURCE_CONFIG=str(config),
                   GTK_THEME="Fixture-Session", TEST_EXPECT_GTK_THEME="Fixture-Session")
        result = subprocess.run([str(SCRIPT), "--annotate"], env=env,
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(settings.read_text(), "[Settings]\ngtk-theme-name=Fixture-User\n")
        self.assert_clean()

    def test_unset_xdg_config_and_missing_gtk_settings_are_supported(self):
        env = self.case_env("close")
        env.pop("XDG_CONFIG_HOME")
        result = subprocess.run([str(SCRIPT), "--annotate"], env=env,
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse((self.home / ".config/gtk-3.0").exists())
        self.assertFalse((self.home / ".config/dconf").exists())
        self.assert_clean()

    def test_print_default_and_shift_binding_remain(self):
        self.assertEqual(self.run_case("close", annotate=False).returncode, 0)
        self.assertEqual(self.calls(), self.expected("slurp", "grim", "wl-copy"))
        self.assert_clean()
        binds = (ROOT / "sway/.config/sway/bind").read_text()
        self.assertIn("bindsym Shift+Print exec grim - | wl-copy -t image/png", binds)
        self.assertIn("bindsym Print exec ~/.config/sway/scripts/screenshot-region\n", binds)


if __name__ == "__main__":
    unittest.main()
