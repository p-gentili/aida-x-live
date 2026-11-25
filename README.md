# aida-x-live

Run the [AIDA-X](https://github.com/AidaDSP/AIDA-X) neural amp sim so it can be
controlled from scripts (or by an assistant) while you play, with the plugin's
normal window still available.

```
iRig HD 2 in ──► AIDA-X (LV2, hosted by Carla's engine) ──► iRig HD 2 out (L+R)
                         ▲
        aida-x-ctl ──────┘  Unix socket: ~/.local/state/aida-x/carla.sock
```

The AIDA-X standalone app has no control API. It doesn't listen on any socket,
and its JACK MIDI input isn't mapped to the knobs. This project loads the LV2
build of AIDA-X in Carla's engine (`libcarla_standalone2.so`) from a small Python
daemon instead. The daemon exposes the plugin's parameters over a Unix socket
and reads back every value it sets.

## Requirements

- PipeWire with JACK support (`pw-jack`, `pw-link`)
- Carla: `sudo apt install carla`. Only the engine library and UI bridges are
  used; the Carla GUI never starts.
- The AIDA-X release unpacked in `~/.local/opt/AIDA-X/`, which must contain
  `AIDA-X.lv2/`

## Install

```sh
./install.sh
```

This symlinks `bin/*` into `~/.local/bin` and installs an "AIDA-X Live" desktop
entry. An existing non-symlink file is moved to `*.bak` first.
`bin/aida-x-standalone` is the original standalone launcher, linked as `aida-x`.

## Run

```sh
aida-x-live                      # plugin window + preset picker
aida-x-live --no-picker          # without the preset picker
aida-x-live --headless           # no window
aida-x-live --preset r-u-mine    # start from a saved preset
aida-x-live --model "$AIDA_MODELS/AMP Orange Dirty.json" \
            --cab "$AIDA_MODELS/cabs/Marshall 4x12 Greenback - Allure.wav"
```

Only one instance can run. Running `aida-x-live` again just opens the preset
picker, and a second `aida-x-carla.py` refuses to start. Two instances would
fight over the control socket and the `AIDA-X` JACK name, so the one you hear
and the one you control end up being different processes.

To use a different interface, override the ports. Run `pw-link -o` to list
capture ports and `pw-link -i` to list playback sinks:

```sh
AIDA_X_IN='alsa_input.…:capture_FL' AIDA_X_OUT='alsa_output.…analog-stereo' aida-x-live
```

The block size defaults to 128 frames at 48 kHz (~2.7 ms). Set
`PIPEWIRE_LATENCY` to change it.

## Control

The examples assume `AIDA_MODELS` points at your folder of `.json` models,
with cab IRs in a `cabs/` subfolder:

```sh
export AIDA_MODELS=~/AIDA-X-models
```

```sh
aida-x-ctl list                 # every parameter: index, symbol, value, range
aida-x-ctl get MASTER
aida-x-ctl set BASS 3           # clamped to range; replies with read-back value
aida-x-ctl ui on|off            # show/hide the plugin window
aida-x-ctl custom               # plugin custom data (model / cab state)
aida-x-ctl load json    "$AIDA_MODELS/AMP Orange Dirty.json"        # amp model
aida-x-ctl load cabinet "$AIDA_MODELS/cabs/UK V30 4x12 SM57.wav"    # cab IR
aida-x-ctl save r-u-mine        # model + cab + all knobs -> preset
aida-x-ctl recall r-u-mine
aida-x-ctl presets
aida-x-ctl quit
```

For a point-and-click switcher, run `aida-x-presets` (or "AIDA-X Presets" in
the app grid). It's a small GTK 4 window with a dropdown of presets; choosing one
recalls it. The refresh button picks up newly saved presets. Under the dropdown
it shows the settings to use on the guitar (pickup, volume, tone and a tip). They
come from `<preset>.guitar.json` next to the preset:

```json
{"pickup": "bridge", "volume": "10", "tone": "10", "notes": "Too thin? Middle position."}
```

On sway, this rule makes the picker a small sticky floating panel in the
top-left corner (`float-corner` is a local helper; drop that part to keep sway's
default placement):

```
for_window [app_id="local.aidax.presets"] floating enable, sticky enable, resize set 380 320, move position 0 -1000, exec ~/.local/bin/float-corner top-left 0 local.aidax.presets
```

Presets are Carla plugin-state files (`.carxs`) in `~/.local/state/aida-x/presets/`.
They store absolute paths to the model and IR files. A name containing `/` is
treated as a path.

Parameters can be given by symbol (case-insensitive) or Carla index:

| # | Symbol | Range | What it does |
|---|--------|-------|--------------|
| 0 | `ANTIALIASING` | 0–100 | anti-aliasing filter amount |
| 1 | `PREGAIN` | -12–12 dB | INPUT gain into the model |
| 2 | `NETBYPASS` | 0/1 | bypass the amp model |
| 3 | `EQBYPASS` | 0/1 | bypass the EQ |
| 4 | `EQPOS` | 0/1 | EQ before (0) / after (1) the model |
| 5 | `BASS` | -8–8 dB | bass (freq: `BFREQ` 75–600 Hz) |
| 7 | `MID` | -8–8 dB | mid (freq `MFREQ` 150–5000 Hz, `MIDQ` 0.2–5, filter type `MTYPE` 0/1) |
| 11 | `TREBLE` | -8–8 dB | treble (freq `TFREQ` 1–4 kHz) |
| 13 | `DEPTH` | -8–8 dB | low-end depth |
| 14 | `PRESENCE` | -8–8 dB | presence |
| 15 | `MASTER` | -15–15 dB | OUTPUT level |
| 16 | `CABSIMBYPASS` | 0/1 | bypass the cab IR |
| 20 | `DCBLOCKER` | 0/1 | DC blocker |
| 21–23 | `ModelInSize`, `MeterIn`, `MeterOut` | — | outputs (read-only) |

## What didn't work, and why

- **Loading a model/IR with `set_custom_data()`.** With LV2's `atom#Path` type,
  Carla stores the path but never sends it to the plugin. With Carla's own
  `…/ns/carla/path` type, the value is dropped entirely. What works is a state
  round trip: `save_plugin_state` → edit the `#json` / `#cabinet` entries →
  `load_plugin_state`, which runs AIDA-X's LV2 state restore. That's what
  `load` does internally.
- **AIDA-X's log is buffered.** Its "Loading cabinet … N frames" / "Layer: lstm"
  lines appear one load late, so don't assume the latest line is the latest
  load. Distinct IR lengths (`2048`, `18304`, `24001` frames) are a handy way
  to tell which cab is active.
- Carla writes a `<client>.tmp/` folder of symlinks to loaded files into its
  working directory. The daemon `chdir`s to `~/.local/state/aida-x/` so this
  doesn't land wherever you launched it from.

- **jalv 1.8.0.** Its console accepts `set SYMBOL VALUE` and `set INDEX VALUE`
  without an error, but nothing changes: a -15 dB `MASTER` change was
  inaudible. Its `controls` listing is also wrong, with values shifted against
  the labels and never updating. `jalv -s` (show the plugin UI) segfaulted.
- **`PIPEWIRE_QUANTUM`** is ignored by `pw-jack` clients, so jalv came up with
  1024-frame blocks (~21 ms). `PIPEWIRE_LATENCY=128/48000` works.
- **`MeterIn` / `MeterOut`** hold a fixed value when read through the host.
  They seem to update only when the plugin's own UI polls them. Don't use them
  to verify a change; listen instead.
- The **standalone AIDA-X** has a JACK `events-in` MIDI port, but nothing in the
  binary suggests MIDI CC → parameter mapping.

## Files

- `bin/aida-x-live`: starts the daemon under `pw-jack` and wires the ports
- `bin/aida-x-carla.py`: Carla engine and socket server
- `bin/aida-x-ctl`: socket client
- `bin/aida-x-presets`: GTK 4 preset picker
- `bin/aida-x-standalone`: the original standalone launcher, for reference
- `install.sh`, `aida-x-live.desktop`
