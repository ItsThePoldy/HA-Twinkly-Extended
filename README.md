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
| Predefined device effects (`effect` mode) | ❌ | 🚧 planned |
| Selecting a playlist entry | ❌ | 🚧 planned |
| Music mode | ❌ | 🚧 planned |

The current release is the built-in integration of Home Assistant 2026.10.2,
packaged as a custom integration; the features marked planned land in the
upcoming `0.x` releases. See [CHANGELOG.md](CHANGELOG.md).

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
the previous token is invalidated. The integration logs in again automatically,
but two clients polling the same device will keep displacing each other.

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
