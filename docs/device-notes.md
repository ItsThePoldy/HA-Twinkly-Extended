# Device notes

Observed behaviour of real Twinkly devices, measured against the local REST API
(`/xled/v1/…`). Each entry names the device and firmware it was measured on;
behaviour on other generations may differ.

## TWW210SPP2 — Curtain 210 LED RGBW, firmware 2.11.0

Measured 2026-10-24. `gestalt`: hardware_version 308, `led_profile: RGBW`,
210 LEDs, `fw_family: G`, `max_movies: 55`, `movie_capacity: 4786` frames.

### API

- Only API v1 answers; every `/xled/v2/…` path returns 404. `ttls`
  `detect_api_version()` tries v1 first, so the predefined-effect methods
  (v1-only in `ttls`) are available.
- Login token lifetime: `authentication_token_expires_in: 14400` (4 h).
- Current movie: `movies/current`. `led/movies/current` returns 404.
- `led/mode` in movie mode also returns the current movie's `id`, `unique_id`
  and `name`.
- `playlist/current` returns HTTP 200 with an empty body while the playlist is
  empty.

### Predefined effects

`led/effects` reports `effects_number: 5` and `unique_ids` only — no names.

- **Selecting** accepts both field names: `POST led/effects/current` with
  `{"effect_id": N}` (what `ttls.set_current_predefined_effect` sends) or
  `{"preset_id": N}`, and `POST led/mode {"mode": "effect", "effect_id": N}`.
  Setting the effect alone does not leave the current mode; `led/mode` has to be
  set to `effect` as well.
- **Reading** `GET led/effects/current` returns the index as `preset_id`, not
  `effect_id`: `{"preset_id": 4, "unique_id": "…0005"}`.

Names as they appear on this device, assigned by watching each effect run:

| Index | unique_id | Name |
|---|---|---|
| 0 | `00000000-0000-0000-0000-000000000001` | Rainbow |
| 1 | `00000000-0000-0000-0000-000000000002` | Silver Shower |
| 2 | `00000000-0000-0000-0000-000000000003` | Color Glow |
| 3 | `00000000-0000-0000-0000-000000000004` | Fireworks |
| 4 | `00000000-0000-0000-0000-000000000005` | Spring Glow |

Whether the same `unique_id` names the same effect on other products or
firmware is not yet known; reports from other devices are welcome.

### Music

`music/drivers`: `drivers_number: 26`, unique_ids only. `music/enabled`:
`{"enabled": 1, "active": 0, "mode": "auto", "auto_mode": "effectsets"}`.
`music/config` returns 404.
