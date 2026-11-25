# Embedded AIDA-X UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** One window: the preset picker with AIDA-X's real X11 UI embedded below it.

**Architecture:** The picker (GTK 3, forced onto X11/XWayland) realizes a container widget and sends its XID to the daemon over the existing socket (`embed XID PID`). The daemon calls Carla's `carla_embed_custom_ui` via ctypes so AIDA-X's in-process UI is reparented into the picker. The daemon guards itself against the parent window vanishing (X error handler + picker-PID watchdog) so audio never stops because of the GUI.

**Tech Stack:** Python 3, Carla 2.5.10 `libcarla_standalone2.so` (ctypes), PyGObject GTK 3 + GdkX11 3.0, libX11 (ctypes), PipeWire-JACK.

**Spec:** `docs/superpowers/specs/2026-11-25-embedded-ui-design.md`

## Global Constraints

- AIDA-X UI is `ui:X11UI` only → the picker must run with `GDK_BACKEND=x11`.
- `carla_embed_custom_ui(CarlaHostHandle handle, uint pluginId, void* ptr) -> void*`; handle is `host.handle`, lib is `host.lib` (already loaded by `CarlaHostDLL`).
- The GUI must never be able to stop the audio engine (anti-goal in spec).
- No test suite exists; verification is by running the real programs. Running the daemon opens JACK ports; nothing else may be running as `aida-x-live` (check `pgrep -af aida-x-carla`).
- Keep `aida-x-ctl ui on|off`, `--headless`, `--no-picker` behaviour as in README.

## Review Focus

1. Picker killed with `kill -9` while embedded → daemon keeps running, `aida-x-ctl get MASTER` still answers. (Task 1 step 5, Task 2 step 4)
2. Picker opened a second time after the first was closed → UI embeds again, not blank. (Task 2 step 4)
3. `embed` while the standalone window is shown (`ui on` earlier) → standalone window disappears, UI appears embedded. (Task 1 step 4)
4. `ui on` while embedded → must not pop a second, broken copy; reply `error: embedded (close the picker first)`. (Task 1 step 4)
5. Picker started while the daemon isn't running → window shows "aida-x-live isn't running", no crash, empty area. (Task 2 step 4)

---

### Task 1: Daemon `embed` / `unembed` with crash guards

**Files:**
- Modify: `bin/aida-x-carla.py` (docstring command list, startup flags, `handle()`, main loop)

**Interfaces:**
- Produces socket commands:
  - `embed XID PID` → hides any standalone UI, calls `carla_embed_custom_ui(host.handle, 0, XID)`, `show_custom_ui(0, True)`, remembers `PID`; replies `ok CHILD_XID` (decimal, the returned pointer value) or `error: …`.
  - `unembed` → `show_custom_ui(0, False)`, forgets parent; replies `ok`.
  - `ui on` while embedded → `error: embedded (close the picker first)`.
- Produces startup flag `--no-ui`: engine starts with UI hidden (like `--headless` for the UI only).

- [ ] **Step 1: Set `ENGINE_OPTION_PREFER_UI_BRIDGES` to 0** before `add_plugin`, so the UI runs in-process (embedding a bridged UI is not supported by Carla 2.5's LV2 path).

- [ ] **Step 2: Install a non-fatal X error handler** at startup: load `libX11.so.6` with ctypes, define `XErrorHandler = CFUNCTYPE(c_int, c_void_p, c_void_p)`, a handler that prints `aida-x-carla: X error ignored` to stderr and returns 0; call `XSetErrorHandler` and keep a module-level reference to the callback. Also `XSetIOErrorHandler` is NOT set (a dead X connection is a real failure).

- [ ] **Step 3: Implement `embed`, `unembed`, `--no-ui`, and the watchdog.** Watchdog: in the main loop, at most every 0.5 s, if an embed PID is recorded and `os.kill(pid, 0)` raises `ProcessLookupError`, run the `unembed` logic. Update the docstring command list.

- [ ] **Step 4: Verify embed with a scratch parent window**

Write a throwaway script in the session scratchpad (not the repo) that opens a GTK 3 window with `GDK_BACKEND=x11`, realizes it, and sends `embed <xid> <os.getpid()>` via the same `ctl()` as `bin/aida-x-presets`, printing the reply.

Run: `pw-jack python3 bin/aida-x-carla.py --no-ui &` then the scratch script.
Expected: reply `ok <number>`; AIDA-X's UI is drawn inside the scratch window. Then `bin/aida-x-ctl ui on` → `error: embedded (close the picker first)`.
Also: restart the daemon without `--no-ui` (standalone window visible), run the scratch script → standalone window disappears, UI is in the scratch window.

- [ ] **Step 5: Verify the crash guard**

Run: `kill -9 <scratch script pid>`, wait 1 s, `bin/aida-x-ctl get MASTER`.
Expected: a value is printed; `pgrep -af aida-x-carla` still shows the daemon. Then `bin/aida-x-ctl ui on` shows the standalone window again (no longer embedded). `bin/aida-x-ctl quit`.

- [ ] **Step 6: Commit**

```bash
git add bin/aida-x-carla.py
git commit -m "Daemon: embed AIDA-X's UI into a foreign X11 window"
```

### Task 2: Picker as GTK 3 wrapper window

**Files:**
- Modify: `bin/aida-x-presets` (rewrite on GTK 3; keep `ctl()`, preset reload, guitar panel, recall logic)

**Interfaces:**
- Consumes: `embed XID PID` → `ok CHILD_XID`; `unembed` → `ok` (Task 1).
- Produces: X11 window with WM_CLASS `aida-x-presets` (set via `GLib.set_prgname("aida-x-presets")` before creating the app), application id stays `local.aidax.presets`.

- [ ] **Step 1: Port to GTK 3.** `os.environ["GDK_BACKEND"] = "x11"` before importing Gtk; `gi.require_version("Gtk", "3.0")`. Replace `Gtk.DropDown`+`StringList` with `Gtk.ComboBoxText`; `append` → `pack_start`; `set_child` → `add`; `present` after `show_all`. Guitar frame hidden via `set_no_show_all(True)` + `hide()` until a preset with guitar settings is chosen.

- [ ] **Step 2: Add the embed area** below the status label: a `Gtk.DrawingArea` (or `Gtk.EventBox`) with `set_has_window`-backed native window. On `realize`, call `get_window().ensure_native()`, take `GdkX11.X11Window.get_xid()`, send `embed`. On `ok CHILD_XID`, size the area to the child: `GdkX11.X11Window.foreign_new_for_display(display, child_xid)` → `get_width()/get_height()` → `set_size_request`. On error or daemon not running, leave the area hidden and show the reply in the status label.

- [ ] **Step 3: Unembed on close.** Connect `delete-event`: send `unembed` (ignore `OSError`), then let the window close.

- [ ] **Step 4: Verify**

With the daemon from Task 1 running (`--no-ui`):
- `bin/aida-x-presets` → one window: dropdown, guitar frame, status, AIDA-X UI below at its natural size. Pick a preset → knobs in the embedded UI move, status `▶ name`.
- Close the window; reopen `bin/aida-x-presets` → UI embeds again.
- `kill -9` the picker → `bin/aida-x-ctl get MASTER` still answers.
- `bin/aida-x-ctl quit`; start `bin/aida-x-presets` → status "aida-x-live isn't running", no traceback.

- [ ] **Step 5: Commit**

```bash
git add bin/aida-x-presets
git commit -m "Picker: GTK 3 window with AIDA-X's UI embedded"
```

### Task 3: Launcher default + docs

**Files:**
- Modify: `bin/aida-x-live` (pass `--no-ui` to the daemon when the picker will open)
- Modify: `README.md` (Run section, picker paragraph, sway rule, "What didn't work" note on GTK 4/Wayland embedding)
- Modify: `aida-x-presets.desktop` only if `StartupWMClass` is needed for the X11 class

**Interfaces:**
- Consumes: `--no-ui` (Task 1), picker WM_CLASS `aida-x-presets` (Task 2).

- [ ] **Step 1: Launcher.** When `picker=1`, add `--no-ui` to the daemon args. `--no-picker` keeps today's standalone window; `--headless` unchanged.

- [ ] **Step 2: README.** Run section: default is one window. Sway rule becomes `for_window [class="aida-x-presets"] …` (drop the fixed `resize set 380 320`, the window now sizes to AIDA-X's UI). Add to "What didn't work": GTK 4 / Wayland can't host the X11 plugin UI; the picker runs on XWayland via GTK 3. Add `embed` / `unembed` to the control list. Add `StartupWMClass=aida-x-presets` to `aida-x-presets.desktop`.

- [ ] **Step 3: Verify end to end**

Run: `bin/aida-x-live --preset r-u-mine`
Expected: exactly one window (picker with embedded UI), sound through the interface. Running `bin/aida-x-live` again reopens/raises the picker with the UI embedded. `bin/aida-x-live --no-picker` (after quit) → only the standalone AIDA-X window.

- [ ] **Step 4: Commit**

```bash
git add bin/aida-x-live README.md aida-x-presets.desktop
git commit -m "Launch the picker as the single AIDA-X window"
```
