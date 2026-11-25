# One window: preset picker with AIDA-X's UI embedded

## Intent

Today `aida-x-live` opens two windows: AIDA-X's own plugin UI and the GTK 4
preset picker. Paolo wants one window: the picker becomes a wrapper with the
**real** AIDA-X interface inside it. Toolkit is free; it should stay small.

## Goals / non-goals

- Goal: one window with presets + guitar notes on top, AIDA-X's UI below.
- Goal: closing or crashing the window must not stop the audio.
- Non-goal: redrawing AIDA-X's knobs ourselves.
- Non-goal: changing the socket protocol beyond what embedding needs.
- Anti-goal: a GUI problem that kills the daemon (sound drops mid-play).

## Constraints

- AIDA-X's UI is `ui:X11UI` (DPF) only. Sway is Wayland; a Wayland toolkit
  can't host a foreign window, so the wrapper must be an X11 window (XWayland).
- GTK 4 has no X11 embedding; GTK 3 does (window XIDs via GdkX11).
- Carla 2.5.10's `libcarla_standalone2.so` exports `carla_embed_custom_ui`;
  the Python bindings don't wrap it, so call it with ctypes.
- The plugin UI runs inside the daemon process (driven by `engine_idle`).

## Approaches

- **A. Separate picker, ported to GTK 3 on X11, daemon embeds by XID (chosen).**
  Small port of the existing picker, audio stays independent of the GUI.
  Risk: parent window disappearing under the embedded UI.
- B. Tk window inside the daemon. Avoids cross-process lifetime, but a GUI
  hang stops the sound; dated look; breaks headless/reopen flow.
- C. Two windows grouped by a sway rule. Nearly free but still two windows.

## Design

- **Picker (`bin/aida-x-presets`)**: GTK 3, forced `GDK_BACKEND=x11`. Same
  dropdown / refresh / Guitar frame / status on top; below, a container
  widget whose X window ID is sent as `embed <xid>` once realized. It sizes
  itself to the embedded UI. On close it sends `unembed` and waits for the
  reply before destroying the window.
- **Daemon (`bin/aida-x-carla.py`)**:
  - `embed XID`: hide any standalone UI, call `carla_embed_custom_ui` with
    that parent, show it, reply with the UI size if known.
  - `unembed`: hide the UI so nothing references the parent anymore.
  - Survive the parent vanishing without `unembed` (picker killed): guard
    against X errors / detect parent loss so the engine keeps running.
  - Start without showing the UI when the picker will embed it.
- **Launcher (`bin/aida-x-live`)**: with the picker (default), the daemon
  starts with the UI hidden and the picker embeds it. `--no-picker` keeps
  today's standalone AIDA-X window; `--headless` unchanged. Launching again
  while running reopens the picker, which re-embeds.
- **`aida-x-ctl ui on|off`**: still works for the standalone window when
  nothing is embedded.
- **README**: update the run/picker sections and the sway rule (an XWayland
  window matches on `class`, not `app_id`).

## Left to the builder

- Exact ctypes signature (check Carla 2.5.10 headers: handle + plugin id +
  parent pointer) and how to get the UI's size.
- How to make the daemon survive a vanished parent; must be verified by
  `kill -9` on the picker while audio plays.
- Layout details (spacing, whether the Guitar frame sits beside or above).
