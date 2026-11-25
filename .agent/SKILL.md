---
name: song-tone
description: Dial in an AIDA-X amp tone for a named song on the live aida-x-live rig. Pick a model, cab and EQ, apply them while the user plays, verify each step, save a preset, and tell the user which pickup to use. Use when the user names a song or artist and wants "the tone for X", or asks to tweak, save or recall a song preset.
---

# Song tone on the live AIDA-X rig

The user is usually **playing while you work**. Every change is heard right
away, so keep levels safe, change one thing at a time, and never restart the
daemon without asking first.

## Rig facts

- Control goes through `aida-x-ctl …` (see the repo `README.md`). Every `set`
  replies with the read-back value.
- Models: `$AIDA_MODELS/*.json`, usually `~/AIDA-X-models`. Cab IRs:
  `$AIDA_MODELS/cabs/*.wav`.
- Presets: `~/.local/state/aida-x/presets/<slug>.carxs`. List them with
  `aida-x-ctl presets`.
- If `aida-x-ctl` can't connect, the daemon isn't running. Ask the user to
  start it (`aida-x-live`, optionally with `--preset NAME`). Don't start it
  yourself while they might be launching it too.

## Workflow

1. **Interpret the song.** Decide the target character: gain level (clean,
   crunch, drive, fuzz), brightness, low-end weight and mid focus. Base it on
   how the recording sounds. Don't state the artist's real amp, pedals or
   guitar as fact unless you have a source; say you're aiming for the sound,
   not cloning the rig.

2. **Pick a pickup** and say it first, in one word, when you reply. The user
   asks this every time and wants a direct answer.
   - Bridge: tight, bright, fast or riff-driven parts, palm mutes, most
     crunch and high gain.
   - Neck: round, dark, woolly or slow parts, bluesy leads, fuzz that should
     bloom.
   - Middle (both): in-between or slightly scooped rhythm parts.
   Give at most one fallback ("if it gets muddy, switch to bridge").

3. **Pick a model and cab.** Look at the files: `ls "$AIDA_MODELS"`.
   File names are the only catalog. Rough guide:

   | Character | Try first | Alternatives |
   |---|---|---|
   | clean / jangly | `Vox AC-30 Normal`, `AMP Twin Vintage1`, `AMP Blues Deluxe Clean1` | `Matchless DC30 Ch1 Clean`, `AMP Marsh JVM Clean1` |
   | light crunch | `AMP Orange Crunchy1`, `AMP Blues Deluxe Crunchy` | `AMP HB Crunchy`, `Hiwatt DR504 JU Crunch BAL DI` |
   | classic rock crunch | `AMP Marsh JVM Crunch`, `JMP Low Input` | `Bogner Plexi_LSTM-16`, `Colombo Plexi breed` |
   | thick drive | `AMP Orange Dirty`, `AMP Marsh JVM OD1` | `Bogner Plexi Red_LSTM-16`, `Supro Bold G9` |
   | fuzz / vintage raw | `Supro Bold G9` | `Pleasant-Fuzzant-fuzz-tight` (pedal only, may sound thin) |
   | high gain | `AMP Marsh JVM OD2`, `Victory-VX-CH2-*` | `recto R 3 esr 0.073`, `Diplomacy-amp-high-gain` |

   Cabs: `Marshall 4x12 Greenback - Allure` is warm and mid-forward (good
   default); `UK V30 4x12 SM57` is tighter and brighter; `Vox AC30-style 2x12`
   suits chime; `Fender Deluxe-style 1x12` and `Tweed 4x10` suit clean or
   bluesy tones.

   Files with "cab", "pre+cab" or "DI" in the name may already include a cab
   or be preamp-only. For those, consider `set CABSIMBYPASS 1`.

4. **Apply safely**, in this order:
   ```sh
   aida-x-ctl set MASTER -12                           # before any model change
   aida-x-ctl load json    "$AIDA_MODELS/<model>.json"
   aida-x-ctl load cabinet "$AIDA_MODELS/cabs/<cab>.wav"
   aida-x-ctl set PREGAIN …; aida-x-ctl set BASS …; …   # EQ
   aida-x-ctl set MASTER -6                            # bring the level back last
   ```
   Starting points (dB):

   | Character | PREGAIN | BASS | DEPTH | MID @ MFREQ | TREBLE | PRESENCE |
   |---|---|---|---|---|---|---|
   | dark / heavy (Do I Wanna Know) | +3 | +3 | +3 | +1 @ 600 | -2 | -2 |
   | thick drive (R U Mine) | +4 | +2 | +2 | +3 @ 800 | +1 | +1 |
   | light crunch (Why'd You Only Call Me…) | +1 | 0 | +1 | +2 @ 900 | +1 | 0 |
   | tight bright crunch (Teddy Picker) | +2 | -1 | 0 | +2 @ 1200 | +2 | +2 |

   Mids are what make a guitar cut through. Don't scoop them unless the song
   is clearly scooped.

5. **Verify before you claim it's done.**
   - `aida-x-ctl custom` shows the json/cabinet paths Carla stored. The
     `#json` value can show just the file name; that's fine.
   - The rig log is the proof that AIDA-X actually loaded the files. It's only
     readable if *you* started `aida-x-live` (background task output). If the
     user started it in their terminal, ask them to confirm by ear.
   - **The log is buffered one load behind.** The newest `Loading cabinet … N
     frames` / `Dims: N` lines belong to the *previous* load. To flush, load
     the same cab again, then read the log.
   - Identify the files from what the log prints:
     - Model size: the model's LSTM size (`Dims: 12` vs `16`). Check a file
       with: `python3 -I -c 'import json,sys; print([(l["type"],l["shape"][-1]) for l in json.load(open(sys.argv[1]))["layers"]])' FILE`
     - Cab IR length in frames: Allure cabs = 2048, `UK V30 4x12 SM57` =
       24001, `Marshall 1960A 4x12 i5 close` = 18304, `V30 4x12 i5 (AIDA-X
       default)` = 8192.
     - Pick a cab or model with a different size or length from the current
       one when you need to tell them apart.
   - `MeterIn` / `MeterOut` are latched and useless for verification.

6. **Save** with `aida-x-ctl save <song-slug>` (lowercase, hyphens), then
   `aida-x-ctl presets`. Don't overwrite an existing preset for a different
   song; the user may want to keep it. Check that the model and cab paths in
   the file are absolute:
   `grep -A1 -E '#(json|cabinet)</Key>' ~/.local/state/aida-x/presets/<slug>.carxs`.
   Carla saves bare file names that only resolve through its temporary symlink
   folder; `save` rewrites them, but a daemon started before that fix won't.

   Also write the guitar-side settings the picker GUI shows, next to the preset:
   ```sh
   cat > ~/.local/state/aida-x/presets/<slug>.guitar.json <<'JSON'
   {"pickup": "bridge", "volume": "10", "tone": "10",
    "notes": "one short playing tip or fallback, e.g. 'Too thin? Middle position.'"}
   JSON
   ```
   Keep it consistent with what you tell the user in chat.

   For a song with very different parts (clean intro vs. overdriven solo),
   make one preset per part (`<song>-intro`, `<song>-solo`). You can build a
   preset offline by copying an existing `.carxs` and editing its
   `<Symbol>…</Symbol><Value>` entries, without changing what's playing.

7. **Reply briefly**: pickup first, then model + cab, the knob values with a
   few words on why, the preset name, and one tweak you'd try next. Ask how it
   sounds.

## Tweaking by ear

Translate plain words into small steps (1–2 dB), one or two knobs at a time:

| User says | Do |
|---|---|
| more gain / fuzz / grit | `PREGAIN` +2 (then try a higher-gain model if still not enough) |
| cleaner / less fizz | `PREGAIN` -2, `PRESENCE` -1 |
| muddy / boomy | `BASS` -1…-2, `DEPTH` -1, or move `BFREQ` down |
| thin / weak | `BASS` +1, `DEPTH` +1, `MID` +1 |
| harsh / ice-picky | `TREBLE` -1…-2, `PRESENCE` -1 |
| dull / dark | `TREBLE` +1, `PRESENCE` +1 |
| doesn't cut | `MID` +1…+2, `MFREQ` toward 800–1200 |
| louder / quieter | `MASTER` ±2…3 (range ±15) |

After a tweak the user likes, `save` the preset again.

## Don'ts (learned the hard way)

- Never put `recall` in a batch with other changes. A stray `recall` reverted
  a freshly dialled tone once.
- Don't use jalv, or `set_custom_data()` alone for paths. Neither reaches the
  plugin (see the README).
- Don't load a new model at full `MASTER`; models differ a lot in loudness.
- Don't restart the daemon mid-session without asking; it cuts the sound.
