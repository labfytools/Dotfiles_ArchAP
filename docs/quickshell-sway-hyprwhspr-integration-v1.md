# QUICKSHELL_SWAY_HYPRWHSPR_INTEGRATION_V1

Integration implemented on 2026-11-07. Real recording tests remain manual.

## Local audit

- Arch package `hyprwhspr 1.52.1-1`; `hyprwhspr --version` prints `hyprwhspr unknown`.
- System QuickShell 0.3.2; running instance uses 0.3.2 from
  `~/.local/opt/quickshell-qt612-popup/bin/quickshell` (labfy local Qt 6.12 popup fix).
- `hyprwhspr --help` and `hyprwhspr record --help` both print the top-level help.
- `record status` stdout is exactly `[INFO] Status: Idle\n`, stderr empty,
  exit 0. This remains true with the service stopped and with an absent runtime
  directory. One local measurement: 98 ms; `systemctl --user is-active
  hyprwhspr.service` took 7 ms and returned `inactive\n`, exit 3.
- Installed CLI source emits `[INFO] Status: Recording in progress\n` when
  `$XDG_RUNTIME_DIR/hyprwhspr/recording_status` contains `true`.
  This recording output was verified in installed source and mocked tests,
  not by recording audio.
- `record toggle` sends normal start/stop commands. Installed source can print
  `[ERROR]` while returning 0; the backend checks both code and expected output.
- No Hyprwhspr binding found in Sway config/bind or `/etc/sway/config.d`.
  User config selects `push_to_talk`, with no primary shortcut override;
  installed default is `SUPER+ALT+D`. Actual keyboard operation remains manual.
- User service was inactive before and after integration. No service/config,
  shortcut, model or transcription changes were made.

## Architecture and behavior

One `HyprwhsprService` in ShellRoot serves every Bar. Each RightStatusArea
places a 26 x 26 indicator between network and Bluetooth. Nerd icon is 18 px,
corner radius 4 px, with existing Theme and StatusTooltip components.
No extra bar, terminal or action panel is created; the existing tooltip
surface is reused for hover text.

The backend serializes availability checks, status reads and toggles using
one asynchronous Process. Availability must be confirmed before status is
accepted. Recording is only confirmed by the exact installed CLI response;
there is no locally inverted recording boolean. The click lock lasts through
command completion and the confirming read. Clicks are ignored during
authentication. Errors never masquerade as recording.

Native recording_status notifications accelerate external keyboard and automatic
changes. A single-shot timer starts after the preceding cycle finishes:
1000 ms at idle/error, 400 ms at recording/processing, plus command latency.
At most one pending refresh is retained. Each command uses GNU timeout with
3 seconds before TERM and another second before KILL. No shell is invoked.
A whole read cycle can require two commands; refresh timing is not a hard
real-time guarantee.

`visualizer_state` is an additional native, optional signal. Installed
`mic_osd/runner.py` writes processing/error/success labels and clears the file;
FileView watches it without reading any transcript. A confirmed recording
response has precedence. With CLI idle, `processing` displays a yellow mic and
`Transcription en cours`; `error` displays a red warning. Missing marker,
`success`, or another label does not invent a processing state. The service
availability gate also applies to these labels. This mechanism depends on
Hyprwhspr publishing its OSD marker and is not an independent transcription API.

Idle: muted grey mic, `Dictée inactive`. Recording: Theme.red (Mocha #f38ba8),
`Dictée en cours`. Processing: Theme.yellow (Mocha #f9e2af).
Unavailable/unreadable/command failure: red warning with a short fixed message.
No animation. No command output, audio or transcript is logged by the backend.
A read-only `dictationStatus.state` IPC returns status/tooltip/busy/cadence only.

## Validation

- qmllint against installed Qt imports: all five changed/added QML files pass.
- git diff --check: pass.
- Production backend tested offscreen using isolated fake CLI executables and
  a temporary runtime directory; no windows and no live microphone access.
- Tests cover startup idle and already recording, external recording/stop,
  unavailable service/recovery, duplicate clicks, CLI failure with exit 0,
  unknown output, native processing/end, bounded slow command and recovery.
- Live existing bar reloaded successfully. IPC correctly reports service
  unavailable; no service restart or stop was performed.
- Captured bar region visually inspected: red warning between network and
  Bluetooth; other indicators remain visible. Radius/size/theme preserved.
- One live QuickShell instance remains, PID 2478 at validation time. Temporary
  offscreen test processes exit after testing. A stalled mocked command is
  bounded and repeated refresh requests coalesce.
- Existing log warnings about ControlCenter/DateCenter Keys attachments and
  I3 socket reconnection are outside this change; no new QML load error seen.
- Full live idle/recording/transcription, hover interaction and service outage
  during actual dictation have not been manually exercised.

## Manual acceptance checklist

1. With Hyprwhspr running and idle, verify grey microphone and idle tooltip.
2. Left click: verify red only after recording is actually confirmed.
3. Left click again: normal transcription and insertion; never cancel.
4. Start with the existing keyboard shortcut: red updates automatically.
5. Stop with the keyboard: indicator follows actual state.
6. If native processing marker is published, verify yellow then idle/error.
7. When convenient, stop/restart the service and verify red warning/recovery
   without interruption or duplication of QuickShell.

Do not mark these steps passed until performed with user authorization.
Pre-existing trier-photos changes and its untracked backup are unrelated and
were preserved. No staging, commits or publication performed.
