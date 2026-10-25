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
