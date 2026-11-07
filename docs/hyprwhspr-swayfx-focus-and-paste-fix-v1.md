# HYPRWHSPR_SWAYFX_FOCUS_AND_PASTE_FIX_V1

Implemented and verified on 2026-11-07 against the locally installed Arch
`hyprwhspr 1.52.1-1`. No real dictation was started and no real application
received test text. Manual audio-to-editor acceptance remains pending.

## Evidence and diagnosis

The installed `_get_active_window_info` probes Niri, Hyprland, X11/XWayland,
then AT-SPI. It has no Sway detector. Consequently native Kitty and Firefox
report `not detected`, while the XWayland ChatGPT reports class `Chatgpt`.
Kitty then resolves the fallback Ctrl+V instead of its terminal Ctrl+Shift+V.
This explains the observed terminal control character; no global paste_mode
setting is needed.

Sway IPC was tested with Kitty, ChatGPT and Firefox individually focused,
restoring the preceding focus after the audit. It correctly returns:

| Application | app_id | window_properties.class | Transport |
|---|---|---|---|
| Kitty | kitty | absent | native Wayland |
| Firefox | firefox | absent | native Wayland |
| ChatGPT | absent | Chatgpt | XWayland |

The service's own `/proc/<pid>/environ` contains:

- SWAYSOCK=/run/user/1000/sway-ipc.1000.2363.sock
- WAYLAND_DISPLAY=wayland-1
- DISPLAY=:0
- XDG_RUNTIME_DIR=/run/user/1000

A `swaymsg get_tree` and corrected `config focused-window` executed with this
service environment succeed for all three applications. No global systemd
environment import or socket workaround was required. The socket's PID-based
path is session-specific and is not hard-coded by the patch.

For ChatGPT, source inspection shows wtype is the normal Wayland injection
transport; ydotool is a fallback. A disposable XWayland Tk widget reproduced
the following with actual synthetic keys:

| Transport | Return | Key event received |
|---|---|---|
| Installed wtype chord | success / exit 0 | keysym `1`, Control mask 4 |
| Patched XWayland dispatch | success | Control_L, then keysym `v`, Control mask 4 |

Adding 50 ms delays to wtype did not correct the wrong keysym. This establishes
a reproducible XWayland keymap/keysym transport failure despite a successful
wtype exit. It is a concrete explanation for the ChatGPT symptom, not proof
that ChatGPT itself has now accepted a real transcript. A manual ChatGPT test
is still required. Clipboard contents were not inspected or logged. The retained
probe blocks all default key bindings and mocks clipboard copy/save/restore.

The OSD source already sets Gtk4LayerShell.KeyboardMode.NONE. No focus-stealing
OSD window appeared in the audit; focus loss remains guarded at delivery time.
Clipboard writes and delayed restoration already use the same clipboard lock;
no demonstrated concurrency defect required changing that mechanism. Firefox
already worked according to the user and retains native wtype + Ctrl+V.

## Patch and installation

`hyprwhspr/integration/sway-focus-paste.patch` adds an authoritative Sway
backend using the i3 IPC GET_TREE protocol directly: little-endian fixed header,
500 ms socket deadline, 8 MiB response bound, iterative nodes/floating_nodes
traversal. It uses focused, app_id, window_properties.class, name and X11 window
ID. It does not invoke a shell, create a poller, or log titles/transcripts.

When SWAYSOCK is set, unavailable/malformed IPC fails closed rather than
falling through to stale XWayland focus. Other compositor detection is retained
when SWAYSOCK is absent. Existing per-application auto_paste rules and automatic
terminal detection are preserved.

Delivery snapshots the current Sway identity, then checks it again after
clipboard publication/settling, immediately before dispatch. Focus change or
IPC failure aborts the paste. No previous window is activated. For an
identified XWayland target it additionally verifies xdotool getactivewindow
against Sway's X11 window ID, then uses the existing XTest Ctrl+V implementation.
It never retries another transport after a possibly dispatched X11 chord.
Native Kitty keeps Ctrl+Shift+V; native Firefox keeps Ctrl+V through wtype.
The focus check and keyboard dispatch are separate operations, not an atomic
compositor transaction.

No pacman-owned file was edited. The installer verifies exact SHA-256 baselines:

- text_injector.py: e6bb5d4291d83cbd189d33bee1dc062b466d59b6a0fb1e1da170dba9b648ca29
- /usr/bin/hyprwhspr: bfe5516566ac12b2f9958109f395d6504ef17dc3ac200eea8779f502a9896f22

It copies the installed lib source into
`~/.local/share/hyprwhspr-swayfx/1.52.1-sway-v1/`, applies the patch with zero
fuzz, and links other package resources. Its launcher retains the packaged
interpreter/environment routing. A SHA guard refuses execution if the original
injector changes after a package update; rebase/review is then required.

The user CLI symlink `~/.local/bin/hyprwhspr` selects this same launcher.
The new drop-in
`~/.config/systemd/user/hyprwhspr.service.d/50-sway-focus-paste.conf` overrides
only ExecStart. Existing config and the pre-existing modified service unit were
preserved. One preparation snapshot was retained as
`1.52.1-sway-v1-before-validation`; it is not active.

Reproduction:

```sh
python ~/.dotfiles/hyprwhspr/integration/install-sway-fix.py
# When dictation and transcription are idle:
systemctl --user daemon-reload
systemctl --user restart hyprwhspr.service
```

Installer rerun/idempotency was verified. The controlled restart completed;
the daemon reports Vulkan (AMD/Intel), large-v3-turbo and READY. NRestarts=0.
Copilot SUPER+SHIFT+F23, push_to_talk, language fr, audio settings, backend and
model remain unchanged. QuickShell was not edited; its existing IPC reports
idle/Dictée inactive after the restart.

## soundfile

The warning originates in FeedbackMixin._report_missing_dependencies running
inside `~/.local/share/hyprwhspr/venv/bin/python`, Python 3.14, with system site
packages enabled. The runtime executable resolves to /usr/bin/python3.14, but
sys.prefix correctly identifies this user venv. soundfile was absent there.

Installed only in that venv, without sudo or dependency upgrades:

```sh
~/.local/share/hyprwhspr/venv/bin/python -m pip install --no-deps soundfile==0.13.1
```

Import now succeeds (0.13.1); missing_imports('vulkan') returns an empty tuple.
The restarted service no longer emits the missing-module error. The backend
and model were not replaced.

## Validation and remaining acceptance

- 16 automated production-method tests pass. They first apply the actual patch
  to installed upstream in a temporary directory, then cover identities/chords,
  fragmented/invalid/oversized/truncated IPC, timeout, socket unavailability,
  stale X focus, delivery-time focus change/loss, XWayland/native routing,
  no retry after X dispatch failure, per-app override and non-Sway fallback.
- Safe real XWayland key probe passes; retained at
  `tools/hyprwhspr-sway-key-probe.py`. It restores focus and terminates its own
  fixture, with no clipboard access or real text delivery.
- Corrected live CLI detection succeeds for all three apps using the service
  environment. User window titles were omitted from the report.
- Python compilation, launcher bash syntax and git diff --check pass.
- Single daemon and original QuickShell instance remain; no fixture or probe
  processes remain. No new scheduler, persistent worker or poller was added.
- No automated tests remain failing. Initial pre-fix focus and XWayland key
  failures are the reproduced defects described above.

Manual checks: use Copilot to dictate a harmless sentence into an empty Kitty
prompt (do not press Enter), a Firefox test field and ChatGPT's input without
submitting. Verify correct accented text, normal transcription/insertion,
QuickShell synchronization and repeated dictation. Actual audio-to-application
insertion remains unclaimed until these tests are performed.

## Rollback

When dictation/transcription are idle, remove only the two newly generated
selectors, then restart the original service:

```sh
unlink ~/.config/systemd/user/hyprwhspr.service.d/50-sway-focus-paste.conf
unlink ~/.local/bin/hyprwhspr
systemctl --user daemon-reload
systemctl --user restart hyprwhspr.service
```

The original unit's ExecStart=/usr/lib/hyprwhspr/bin/hyprwhspr takes effect again.
The user-owned source snapshots can remain for diagnosis; no package restore,
Git restore or cleanup is required. soundfile can safely remain. If its removal
is desired separately, use the same venv's `python -m pip uninstall soundfile`;
it was absent before this task. Preserve all other config/unit modifications.

## Upstream opportunity

A focused upstream contribution is appropriate: Sway identity detection,
fail-closed delivery-time focus checks and the independently reproduced wtype
XWayland keysym failure with targeted X11 dispatch. Keep the local installer and
systemd paths out of the upstream code patch. No issue, PR or publication was
created.
