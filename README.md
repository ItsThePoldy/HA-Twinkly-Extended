# Twinkly Extended for Home Assistant

> **Beta — this custom integration REPLACES Home Assistant's built-in Twinkly
> integration.** It uses the same `twinkly` domain, so your existing devices and
> entities carry over unchanged, and removing it returns you to the built-in
> version.

The built-in [Twinkly integration](https://www.home-assistant.io/integrations/twinkly/)
plays movies uploaded through the Twinkly app, but leaves several device features
unused even though its client library ([`ttls`](https://github.com/jschlyter/ttls))
already supports them. This project adds them.

## Status

| Feature | Built-in | Twinkly Extended |
|---|---|---|
| On/off, brightness | ✅ | ✅ |
| Colour (RGB / RGBW incl. white channel) | ✅ | ✅ |
| Movies uploaded via the Twinkly app | ✅ | ✅ |
| Mode select (color, movie, playlist, …) | ✅ | ✅ |
| Predefined device effects (`effect` mode) | ❌ | ✅ |
| Leaves the device to the Twinkly app (`App mode`) | ❌ | ✅ |
| Selecting a playlist entry | ❌ | 🚧 planned |
| Music mode | ❌ | 🚧 planned |

The integration is based on the built-in one of Home Assistant 2026.10.2.
See [CHANGELOG.md](CHANGELOG.md) for what each release adds.

## Predefined effects

Twinkly devices ship a few built-in effects besides the movies you upload with
the app. They appear in the light's effect list after the movies:

```
1 Rainbow        ← movie uploaded with the app ("<id> <name>", unchanged)
2 Flare
Rainbow          ← predefined effect
Silver Shower
…
```

The device reports these effects without names, so names come from
[`effect_names.yaml`](custom_components/twinkly/effect_names.yaml), with one rule
per device variant. A device without a rule shows its effects as `Effect 1`,
`Effect 2`, …. Devices on Twinkly's newer API (v2) have no predefined effects.

**Your device shows `Effect 1`, `Effect 2`?** Open an issue with the diagnostics
download of the device (Settings → Devices & services → Twinkly → ⋮ → Download
diagnostics) and the name of each effect as you see it. That is everything a
new rule needs. Measurements behind the existing rules:
[docs/device-notes.md](docs/device-notes.md).

## Installation (HACS)

1. HACS → ⋮ → **Custom repositories** → add
   `https://github.com/ItsThePoldy/HA-Twinkly-Extended`, type **Integration**.
2. Install **Twinkly Extended** and restart Home Assistant.
3. To test pre-releases, enable **Show beta versions** for this repository in HACS.

Requires Home Assistant **2026.10.2** or newer.

Home Assistant logs a warning that a custom integration overrides `twinkly`;
that is expected.

## Going back to the built-in integration

Remove the integration in HACS and restart Home Assistant. Your config entries
stay compatible with the built-in version.

## Good to know

A Twinkly device accepts **one authentication token at a time**: when another
client logs in (the Twinkly app, a second Home Assistant instance, a script),
the previous token is invalidated, and logging in again takes it back from that
client. The integration therefore steps aside:

- When another client takes the token twice within 5 minutes, polling pauses for
  10 minutes, and twice as long each time that client is still there afterwards
  (up to 60 minutes). The entities keep their last state meanwhile.
- The `App mode` switch pauses polling for 30 minutes on demand — turn it on
  before opening the Twinkly app, for example to upload new effects. It also
  shows an automatic pause, and turning it off resumes polling at once.
- A command from Home Assistant (light, mode) ends a pause and takes the device
  back.
- **App proxy request.** If a directory is mounted at `/twinkly-proxy` inside
  Home Assistant, app mode keeps an empty file named after the device's host
  (e.g. `/twinkly-proxy/10.1.9.80`) there for as long as it is on, and removes
  it when app mode ends (switch off, timeout, a command from Home Assistant) and
  when the integration starts. A host-side service can watch that file, for
  example to make the device reachable for the app from another network while
  app mode is on. Without the directory nothing is written.

## Movies on the device

The device page splits what plays from what is stored. Under **Controls**: the
light (its colour wheel sets a static colour), the **`Animation`** select, which
lists the movies saved on the device (by name) and then the predefined effects
(choosing one plays it and turns the device on; a predefined effect named like a
movie is listed as `<name> (effect)`), **`Mode`** (the device's mode — `Real time`
shows only what an app or music sync streams live, `Demo` runs the effects in
turn), and the **`Play all animations in turn`** button, which writes every movie
on the device into the device's playlist and starts it. Under **Configuration**:
`App mode`, `Duration per animation` (seconds each movie plays in that playlist,
kept across restarts), `Upload from library` and `Delete movie`. Entity names are
translated to German.

- **`Delete movie` select** (configuration entity): lists the movies saved on the
  device; choosing one deletes it at once, there is no confirmation. The LEDs are
  switched off for the delete and return to their mode afterwards, as the Twinkly
  app does it. Needs firmware 2.7.1 or newer.
- **`Upload from library` select** — only if a directory is mounted at `/twinkly-library`
  inside Home Assistant. It holds recorded uploads of the Twinkly app, one shelf
  per `<product_code>-<number_of_led>` and one directory per movie with
  `movie.json` (the app's `movies/new` request plus `bytes_per_led`, `size`,
  `sha256`) and `frames.bin`. The select lists the shelf's movies that fit the
  device's LED count and colour profile. Choosing one plays it; a movie the device
  does not have is uploaded first, after its frames are checked against the
  recorded hash. If the device has too few free frames, nothing is uploaded and
  the error names how many are missing: delete a movie first. The library is
  read on every poll, so new recordings appear within 30 s.

## Development

```bash
uv venv --python 3.14 .venv
uv pip install --python .venv/bin/python -r requirements_test.txt
.venv/bin/python script/gen_translations.py   # after any strings.json change
.venv/bin/python -m pytest -q
```

Branch layout:

- `upstream` — the core integration **verbatim**, at the core release named in
  [UPSTREAM](UPSTREAM). Updating it is a plain copy from a newer core tag.
- `main` — `upstream` plus this project's changes. `git diff upstream main`
  shows exactly what this project adds.

## License

Apache License 2.0, like Home Assistant itself. See [LICENSE](LICENSE) and
[NOTICE](NOTICE).
