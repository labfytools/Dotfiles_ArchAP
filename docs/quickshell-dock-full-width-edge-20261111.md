# QuickShell Dock — full-width bottom edge activation (2026-11-11)

## Report and root cause

The centered QuickShell Dock used a layer-shell `PanelWindow` whose width
matched its visible row of icons. Its hidden activation sensor was limited to
`min(360, dock.width)`. Outside that narrow central region, moving the
pointer against the bottom edge of an output could not enter the surface.

## Change

`dock/Dock.qml` now anchors its input surface to the bottom, left and right
edges of **each output**. Only the **4px bottom sensor** is interactive while
hidden; the panel retains `exclusionMode: Ignore`, `exclusiveZone: 0`,
`WlrKeyboardFocus.None` and the existing input `Region` mask.

The visible `body` is centered within this full-width surface and preserves
its former calculated width, icon geometry, hover scale, 180ms activation dwell,
210ms slide, 450ms hide grace and scroll behavior. Context popup coordinates
include the visual body's horizontal offset. This does not affect the top bar,
Sway bindings, system shortcuts, favorites persistence or Session Restore V2.

## Validation

`qmllint quickshell/.config/quickshell/labfy-sway/dock/Dock.qml` passed;
`node tests/dock/test_models.js` and the six unit tests in `tests/dock/`
passed. Full `tests/dock/headless.py` ran with a private SwayFX and a
separate artifacts directory in `~/.cache/labfy-dock-edge-test`:

- `PASS` for activation from the left and right screen corners;
- sensor width equals output width while visual body remains centered;
- all existing favorites, auto-hide, context, scrolling, focus, drag,
  multi-window, framebuffer, animation and resolution scenarios pass;
- no visual geometry or SVG raster reload during the frame sweep.

No user desktop windows or active Sway compositor were touched by the
headless tests. The production QuickShell service must reload the amended
QML to receive the new input region; Sway itself does not need a reload.
