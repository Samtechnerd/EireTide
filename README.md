<p align="center"><img src="logo.png" alt="EireTide logo" width="300"></p>

# EireTide

A Home Assistant custom integration for tide predictions in Ireland and the
UK. It supports two independent prediction sources, picked per station when
you add the integration:

- **Marine Institute** (Ireland only) — fetches official predictions from the
  Marine Institute's open tide data. Works for any station in their network,
  and defaults to **Dublin Port**.
- **Local harmonic model** (Ireland or UK, or anywhere) — computes
  predictions on-device from Moon/Sun position using a harmonic tide model,
  with harmonic constants you supply for your station. No network access
  needed at all. See [Local harmonic model](#local-harmonic-model-moonsun-position)
  below.

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

On a **Marine Institute** station, `sensor.*_current_tide_height` isn't a
direct measurement — the dataset only publishes high/low predictions, not a
continuous curve. The value is interpolated between the surrounding
predicted high and low using a cosine curve, which is accurate to within a
few centimetres for Ireland's semi-diurnal tides. On a **local harmonic
model** station, this sensor instead evaluates the harmonic model directly
at the current instant, so it's not an interpolation at all. Either way, it
refreshes every 5 minutes so it keeps moving smoothly between coordinator
updates.

## Data source (Marine Institute)

Tide predictions are fetched from the Marine Institute's public
[ERDDAP](https://erddap.marine.ie/erddap/tabledap/IMI_TidePrediction_HighLow.html)
server — no API key or account is required. The integration discovers the
dataset's column names and station list at setup time rather than hardcoding
them, so it adapts automatically if the Marine Institute changes their schema.

Data is refreshed every 30 minutes. (The local harmonic model source has no
equivalent network step — see
[Local harmonic model](#local-harmonic-model-moonsun-position) above.)

### About the height numbers (Marine Institute)

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
rising/falling) are unaffected either way. There's no reliable per-station
OD-Malin-to-Chart-Datum offset in this dataset, so this integration doesn't
attempt a conversion.

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
2. Choose a prediction source: **Marine Institute** or **Local harmonic
   model**.
   - For Marine Institute, pick a station from the dropdown (Dublin Port is
     pre-selected if available). If the station list can't be loaded, you
     can type the station name manually.
   - For the local harmonic model, see
     [Local harmonic model](#local-harmonic-model-moonsun-position) below.
3. Repeat to add additional stations — each station is a separate config
   entry.

## Local harmonic model (Moon/Sun position)

This mode predicts tides the way tide tables have worked since Doodson and
Schureman formalised the method in the early 20th century: the tide is
modelled as a sum of constituent waves, one per gravitational forcing term of
the Moon and Sun (semidiurnal M2/S2/N2/K2, diurnal K1/O1/P1/Q1, long-period
Mm/Mf/Ssa/Sa, and the shallow-water compounds M4/MS4/M6). The engine
(`custom_components/irish_tides/harmonic.py`) computes each constituent's
astronomical phase and lunar-nodal amplitude/phase correction directly from
the Moon and Sun's real orbital elements at request time — that part needs no
external data and works anywhere on Earth.

What it *can't* do without your input is know how a specific harbour responds
to each of those forcing terms — that response (amplitude + phase lag per
constituent) is shaped by local coastline and bathymetry and can only come
from harmonic analysis of real measurements at that station. So this mode
asks you to supply your station's harmonic constants directly:

1. Choose **Local harmonic model** in the config flow.
2. Give the station a name, a mean sea level (Z0, the reference level your
   constants are relative to), and a datum label (free text, just for your
   own reference on the sensors — this integration doesn't convert between
   datums).
3. Enter one constituent per line as `NAME AMPLITUDE_M PHASE_DEG`, e.g.:
   ```
   M2 1.90 137
   S2 0.70 171
   N2 0.40 120
   K1 0.10 200
   O1 0.08 190
   ```
   `PHASE_DEG` must be the **Greenwich phase lag** (sometimes called `G` or
   `kappa`), the standard international convention every harmonic-constants
   provider publishes in — not a local high-water-time offset.

### Where to get real harmonic constants

This repository doesn't ship a built-in constants table for any Ireland/UK
station. That's a licensing choice, not an oversight: the only
public-domain, freely-redistributable harmonic constituent database
(XTide's `harmonics-dwf-free`) covers US stations only — the equivalent data
for the UK and Ireland (e.g. via UKHO/Admiralty) is published for
non-commercial use only, which isn't compatible with bundling it into an
openly-licensed repository. You'll need to source your own constants for
your station, for example from:

- The UK's [National Tidal and Sea Level Facility](https://ntslf.org/) / [BODC UK Tide Gauge Network](https://www.bodc.ac.uk/data/hosted_data_systems/sea_level/uk_tide_gauge_network/)
- [Admiralty EasyTide](https://easytide.admiralty.co.uk/) / UKHO tidal harmonics products
- Your own harmonic analysis of measured water-level data (e.g. with the
  Python [`utide`](https://github.com/wesleybowman/UTide) package)

### Accuracy and limitations

This is a hobbyist predictor, not a substitute for official tide tables or
navigation data:

- It uses 15 constituents and linear (first-order) nodal corrections, rather
  than the full satellite-term expansion professional software uses. Error
  from this simplification is small compared to the uncertainty already
  present in a year of harmonic-analysed station data.
- It's only as accurate as the constants you give it — get those from a
  proper harmonic analysis, not guesswork.
- The engine's astronomical math is covered by unit tests
  (`tests/test_harmonic.py`) that check it against independently-verifiable
  facts — the sidereal month, the 18.6-year lunar nodal cycle, and the
  half-synodic-month spring/neap beat between M2 and S2 — rather than a
  single station's official predictions, since verifying against a live
  official feed isn't something a repository can bundle as a repeatable
  test.

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
  Institute, UKHO, Admiralty, NTSLF, or BODC.
- Tide *predictions*, not real-time observations — treat them as forecasts,
  not a substitute for official navigation data, on either prediction source.
