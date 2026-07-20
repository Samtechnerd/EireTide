<p align="center"><img src="logo.png" alt="EireTide logo" width="300"></p>

# EireTide

A Home Assistant custom integration for Irish tide predictions, built on the
[Marine Institute](https://www.marine.ie/)'s open tide prediction data.
Works for any station in their network, and defaults to **Dublin Port**.

## What you get

Each configured station is added as a device with these entities:

| Entity | Description |
| --- | --- |
| `sensor.*_current_tide_height` | The main entity — estimated tide height (metres) right now |
| `sensor.*_next_tide_time` | Timestamp of the next high or low tide |
| `sensor.*_next_tide_type` | `High` or `Low` |
| `sensor.*_next_tide_height` | Predicted height (metres) of the next tide |
| `sensor.*_following_tide_time` | Timestamp of the tide after next |
| `sensor.*_following_tide_type` | `High` or `Low` |
| `sensor.*_following_tide_height` | Predicted height (metres) of the tide after next |
| `binary_sensor.*_tide_rising` | `on` while the tide is rising towards the next high |

The `sensor.*_next_tide_time` entity also exposes an `upcoming_tides`
attribute listing the next 10 predicted tide events, for use in cards or
automations.

`sensor.*_current_tide_height` isn't a direct measurement — the Marine
Institute dataset only publishes high/low predictions, not a continuous
curve. The value is interpolated between the surrounding predicted high and
low using a cosine curve, which is accurate to within a few centimetres for
Ireland's semi-diurnal tides. It refreshes every 5 minutes so it moves
smoothly between the half-hourly prediction fetches.

## Data source

Tide predictions are fetched from the Marine Institute's public
[ERDDAP](https://erddap.marine.ie/erddap/tabledap/IMI_TidePrediction_HighLow.html)
server — no API key or account is required. The integration discovers the
dataset's column names and station list at setup time rather than hardcoding
them, so it adapts automatically if the Marine Institute changes their schema.

Data is refreshed every 30 minutes.

### About the height numbers

All heights are relative to **OD Malin**, Ireland's national geodetic datum
— that's what the Marine Institute publishes, and it's what every height
sensor and the `datum` attribute on them report. OD Malin sits roughly at
mid-tide, so values swing positive *and* negative (a spring low might read
around -2m, a spring high around +2m).

This is different from the **Chart Datum** (≈ Lowest Astronomical Tide)
numbers you'll see in apps like Windfinder or Tides Near Me, which is
pinned near the lowest tide ever recorded at a station and so is always
positive and reads noticeably larger. The two datums differ by a
roughly constant offset per station (commonly ~2-2.5m around the Irish
coast), so don't be surprised if this integration's heights look smaller,
or negative, next to a consumer tide app's — the tide *times* (high/low,
rising/falling) are unaffected either way.

#### Chart Datum estimate (optional)

Once a station is set up, open its **Configure** option (Settings →
Devices & Services → EireTide → the station → Configure) to enter that
station's OD-Malin-to-Chart-Datum offset in metres, if you know it. When
set, every height sensor gains a `chart_datum_estimate_m` attribute
(`native value + offset`) alongside the raw OD Malin reading — the raw
value never changes, this is purely an added estimate.

A handful of offsets, derived from simultaneous OD Malin / LAT readings on
the Marine Institute's real-time observations network on 2026-07-20, are
pre-filled automatically for stations we have data for (see
`KNOWN_HEIGHT_OFFSETS` in `const.py`), including **Howth (2.561m)** and
**Dublin Port (2.458m)**. Treat these as good estimates, not surveyed
figures — for anything precision-critical, use your station's official
Admiralty Tide Table datum correction instead.

## Installation

### HACS (recommended)

1. In HACS, add this repository as a custom repository (category:
   Integration).
2. Install "EireTide".
3. Restart Home Assistant.

### Manual

1. Copy `custom_components/irish_tides` into your Home Assistant
   `config/custom_components/` directory.
2. Restart Home Assistant.

## Configuration

1. Go to **Settings → Devices & Services → Add Integration** and search for
   **EireTide**.
2. Pick a station from the dropdown (Dublin Port is pre-selected if
   available). If the station list can't be loaded, you can type the
   station name manually.
3. Repeat to add additional stations — each station is a separate config
   entry.

## Branding

`custom_components/irish_tides/brand/` ships `icon.png` and `logo.png`.
Home Assistant 2026.3+ serves brand images straight from an integration's
own `brand/` folder (no submission to the separate `home-assistant/brands`
repo needed), so the icon/logo show up in the integrations list, config
flow, and device pages automatically — nothing else to configure. On older
Home Assistant versions this folder is simply ignored and the integration
falls back to the generic puzzle-piece icon.

## Notes

- This integration is not affiliated with, or endorsed by, the Marine
  Institute. It simply consumes their published open data.
- Tide *predictions*, not real-time observations — treat them as forecasts,
  not a substitute for official navigation data.
