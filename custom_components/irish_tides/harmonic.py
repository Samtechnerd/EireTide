"""Self-contained astronomical tide prediction engine.

This implements the classical harmonic method used by essentially every
tide-prediction system since Doodson/Schureman: the tide is modelled as a
sum of constituent waves, one per gravitational forcing term of the Moon
and Sun, each with its own speed (rate of phase change), and a per-station
amplitude and phase lag:

    height(t) = Z0 + sum_i f_i(t) * H_i * cos(speed_i * t + V0_i(t) + u_i(t) - g_i)

- ``H_i`` / ``g_i`` (amplitude / Greenwich phase lag) describe *how a
  specific harbour responds* to constituent ``i`` -- shaped by local
  coastline, bathymetry and resonance. These can only come from harmonic
  analysis of real measurements at that station, so this module does not
  attempt to invent them; they're supplied per station by the caller (see
  ``harmonic_coordinator.py``).
- ``speed_i``, ``V0_i`` (equilibrium argument) and the nodal modulation
  ``f_i``/``u_i`` describe the astronomical forcing itself -- the Moon and
  Sun's positions relative to Earth -- and are the same everywhere on
  Earth. Those *are* computed from first principles here, from the mean
  orbital elements of the Moon and Sun (Meeus, "Astronomical Algorithms",
  low-precision series) and the standard linearised nodal factor
  approximations (Schureman 1958 / Foreman 1977), which is the "moon
  position and stuff" part of this integration.

This is an amateur/hobbyist predictor, not a substitute for official
navigation data: it uses the 8 major astronomical constituents plus a
handful of long-period and shallow-water compound terms, and the linear
(first-order) nodal corrections rather than Schureman's full satellite
series. Both simplifications are standard practice for this class of
predictor and keep the error well under the uncertainty already present in
station harmonic constants derived from a year or so of tide-gauge data.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

# ---------------------------------------------------------------------------
# Constituent speeds, in degrees per mean solar hour.
#
# These are exact rational relationships between the Moon's, Sun's, and
# Earth's mean motions (e.g. S2 = 30.0 deg/h exactly, since it's tied to
# mean solar time), and are universal constants of the harmonic method --
# the same numbers appear in every tide-prediction table published by NOAA,
# UKHO, BODC, etc.
# ---------------------------------------------------------------------------
CONSTITUENT_SPEEDS: dict[str, float] = {
    # Semidiurnal
    "M2": 28.9841042,
    "S2": 30.0000000,
    "N2": 28.4397295,
    "K2": 30.0821373,
    # Diurnal
    "K1": 15.0410686,
    "O1": 13.9430356,
    "P1": 14.9589314,
    "Q1": 13.3986609,
    # Long period
    "Mm": 0.5443747,
    "Mf": 1.0980331,
    "Ssa": 0.0821373,
    "Sa": 0.0410686,
    # Shallow water / compound (overtides of the main lunar/solar terms)
    "M4": 57.9682084,
    "MS4": 58.9841042,
    "M6": 86.9523127,
}

# Named so the engine can reject unknown constituent names early with a
# clear error rather than silently mis-predicting.
KNOWN_CONSTITUENTS: tuple[str, ...] = tuple(CONSTITUENT_SPEEDS)

_EPOCH = datetime(2000, 1, 1, 12, 0, 0, tzinfo=timezone.utc)  # J2000.0


def _julian_centuries(at: datetime) -> float:
    """Julian centuries since J2000.0 for a timezone-aware UTC datetime."""
    if at.tzinfo is None:
        raise ValueError("datetime must be timezone-aware")
    delta = at.astimezone(timezone.utc) - _EPOCH
    days = delta.total_seconds() / 86400.0
    return days / 36525.0


def _norm_deg(angle: float) -> float:
    """Normalise an angle in degrees to [0, 360)."""
    return angle % 360.0


@dataclass(frozen=True)
class AstronomicalArguments:
    """Mean orbital elements of the Moon and Sun at a given instant, in degrees."""

    T: float  # Hour angle of the mean sun, i.e. mean solar time expressed as an angle
    s: float  # Mean longitude of the Moon
    h: float  # Mean longitude of the Sun
    p: float  # Longitude of the Moon's perigee
    N: float  # Longitude of the Moon's ascending node


def astronomical_arguments(at: datetime) -> AstronomicalArguments:
    """Compute the mean lunar/solar orbital elements at ``at`` (Meeus low-precision series)."""
    jc = _julian_centuries(at)

    s = 218.3164477 + 481267.88123421 * jc - 0.0015786 * jc**2 + jc**3 / 538841.0
    h = 280.46646 + 36000.76983 * jc + 0.0003032 * jc**2
    p = 83.3532465 + 4069.0137287 * jc - 0.0103200 * jc**2
    N = 125.04452 - 1934.136261 * jc + 0.0020708 * jc**2

    # T is the Greenwich hour angle of the mean sun: 0 deg at Greenwich mean
    # midnight, +15 deg/hour. Using midnight-referenced UT (rather than the
    # noon-referenced classical convention) here just shifts every V0 by a
    # constant 180 deg, which cancels out because it's applied identically
    # to every constituent's argument below.
    utc = at.astimezone(timezone.utc)
    hours = (
        utc.hour
        + utc.minute / 60.0
        + utc.second / 3600.0
        + utc.microsecond / 3_600_000_000.0
    )
    T = 15.0 * hours

    return AstronomicalArguments(
        T=_norm_deg(T),
        s=_norm_deg(s),
        h=_norm_deg(h),
        p=_norm_deg(p),
        N=_norm_deg(N),
    )


def _equilibrium_argument(name: str, a: AstronomicalArguments) -> float:
    """V0: the equilibrium argument for a constituent, in degrees.

    Expressed as the standard linear combination of the fundamental
    astronomical arguments (Doodson's method). See e.g. Foreman (1977),
    "Manual for Tidal Heights Analysis and Prediction", Table A1.
    """
    if name == "M2":
        v0 = 2 * a.T + 2 * a.h - 2 * a.s
    elif name == "S2":
        v0 = 2 * a.T
    elif name == "N2":
        v0 = 2 * a.T + 2 * a.h - 3 * a.s + a.p
    elif name == "K2":
        v0 = 2 * a.T + 2 * a.h
    elif name == "K1":
        v0 = a.T + a.h + 90.0
    elif name == "O1":
        v0 = a.T + a.h - 2 * a.s - 90.0
    elif name == "P1":
        v0 = a.T - a.h - 90.0
    elif name == "Q1":
        v0 = a.T + a.h - 3 * a.s + a.p - 90.0
    elif name == "Mm":
        v0 = a.s - a.p
    elif name == "Mf":
        v0 = 2 * a.s
    elif name == "Ssa":
        v0 = 2 * a.h
    elif name == "Sa":
        v0 = a.h
    elif name == "M4":
        v0 = 2 * _equilibrium_argument("M2", a)
    elif name == "MS4":
        v0 = _equilibrium_argument("M2", a) + _equilibrium_argument("S2", a)
    elif name == "M6":
        v0 = 3 * _equilibrium_argument("M2", a)
    else:
        raise ValueError(f"Unknown tidal constituent: {name!r}")
    return _norm_deg(v0)


def _node_factors(name: str, node_n_deg: float) -> tuple[float, float]:
    """(f, u): the lunar nodal amplitude/phase modulation for a constituent.

    Standard first-order (linear) approximations in terms of the longitude
    of the Moon's ascending node N (Schureman 1958 Table 2 / Foreman 1977),
    good to within a fraction of a percent -- well inside the uncertainty
    already present in a station's harmonic constants.
    """
    n = math.radians(node_n_deg)

    if name in ("M2", "N2", "M4", "MS4", "M6"):
        f_m2 = 1.0 - 0.037 * math.cos(n)
        u_m2 = -2.14 * math.sin(n)
        if name in ("M2", "N2"):
            return f_m2, u_m2
        if name == "M4":
            return f_m2 * f_m2, 2 * u_m2
        if name == "MS4":
            return f_m2, u_m2
        return f_m2**3, 3 * u_m2  # M6

    if name in ("S2", "P1", "Ssa", "Sa"):
        return 1.0, 0.0

    if name == "K2":
        f = 1.024 + 0.286 * math.cos(n) + 0.008 * math.cos(2 * n)
        u = -17.7 * math.sin(n) + 0.68 * math.sin(2 * n)
        return f, u

    if name == "K1":
        f = 1.006 + 0.115 * math.cos(n) - 0.009 * math.cos(2 * n)
        u = -8.86 * math.sin(n) + 0.68 * math.sin(2 * n)
        return f, u

    if name in ("O1", "Q1"):
        f = 1.009 + 0.187 * math.cos(n) - 0.015 * math.cos(2 * n)
        u = 10.8 * math.sin(n) - 1.34 * math.sin(2 * n)
        return f, u

    if name == "Mm":
        f = 1.0 - 0.130 * math.cos(n)
        return f, 0.0

    if name == "Mf":
        f = 1.043 + 0.414 * math.cos(n)
        u = -23.7 * math.sin(n) + 2.7 * math.sin(2 * n)
        return f, u

    raise ValueError(f"Unknown tidal constituent: {name!r}")


@dataclass(frozen=True)
class HarmonicConstituent:
    """A station's response to one tidal constituent, from harmonic analysis."""

    name: str
    amplitude_m: float
    phase_deg: float  # Greenwich phase lag (kappa / G), degrees

    def __post_init__(self) -> None:
        if self.name not in CONSTITUENT_SPEEDS:
            raise ValueError(
                f"Unknown tidal constituent {self.name!r}; known constituents: "
                f"{', '.join(KNOWN_CONSTITUENTS)}"
            )


def predict_height_m(
    constituents: list[HarmonicConstituent], mean_level_m: float, at: datetime
) -> float:
    """Predict the tide height at ``at`` from a station's harmonic constants.

    Unlike a classical hand tide table -- which fixes speed*t against a
    reference epoch and only re-evaluates the slowly-varying V0/f/u once
    per year to save hand computation -- this evaluates the equilibrium
    argument V0(t) directly at ``at`` on every call. V0(t) already carries
    the full time dependence (through T, which is linear in wall-clock
    time), so it must not also be combined with a separate speed*(t-epoch)
    term -- that would double-count the fast rotation and produce a
    prediction at roughly twice the true constituent frequency.
    """
    args = astronomical_arguments(at)

    height = mean_level_m
    for c in constituents:
        v0 = _equilibrium_argument(c.name, args)
        f, u = _node_factors(c.name, args.N)
        phase = math.radians(_norm_deg(v0 + u - c.phase_deg))
        height += f * c.amplitude_m * math.cos(phase)
    return height


# Constituent names aren't all-caps (Mm, Mf, Ssa, Sa), so matching text input
# against them case-insensitively needs an explicit upper() -> canonical map
# rather than just upper()-ing the input and comparing directly.
_CONSTITUENT_BY_UPPER_NAME = {name.upper(): name for name in CONSTITUENT_SPEEDS}


def parse_constituents_text(text: str) -> list[HarmonicConstituent]:
    """Parse a user-supplied constituent table into `HarmonicConstituent` objects.

    Expected format is one constituent per line: ``NAME AMPLITUDE_M PHASE_DEG``,
    e.g. ``M2 1.90 137``. Blank lines are ignored. Raises ``ValueError`` with a
    line-specific message on any malformed input.
    """
    constituents: list[HarmonicConstituent] = []
    seen: set[str] = set()

    for line_no, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue

        parts = line.split()
        if len(parts) != 3:
            raise ValueError(f"Line {line_no}: expected 'NAME AMPLITUDE PHASE', got {raw_line!r}")

        raw_name, amplitude_text, phase_text = parts
        name = _CONSTITUENT_BY_UPPER_NAME.get(raw_name.upper())
        if name is None:
            raise ValueError(
                f"Line {line_no}: unknown constituent {raw_name!r}; known constituents: "
                f"{', '.join(KNOWN_CONSTITUENTS)}"
            )
        if name in seen:
            raise ValueError(f"Line {line_no}: constituent {name!r} listed more than once")
        seen.add(name)

        try:
            amplitude_m = float(amplitude_text)
            phase_deg = float(phase_text)
        except ValueError as err:
            raise ValueError(f"Line {line_no}: could not parse numbers in {raw_line!r}") from err

        constituents.append(HarmonicConstituent(name=name, amplitude_m=amplitude_m, phase_deg=phase_deg))

    if not constituents:
        raise ValueError("At least one constituent is required")

    return constituents


@dataclass(frozen=True)
class TideExtremum:
    """A predicted high or low tide, found by scanning the height curve."""

    time: datetime
    height_m: float
    is_high: bool


def find_extrema(
    constituents: list[HarmonicConstituent],
    mean_level_m: float,
    start: datetime,
    end: datetime,
    *,
    coarse_step: timedelta = timedelta(minutes=10),
    refine_tolerance: timedelta = timedelta(seconds=30),
) -> list[TideExtremum]:
    """Find local maxima/minima of the harmonic height function in [start, end].

    The dominant constituent everywhere this engine is aimed at is
    semidiurnal (period ~12h25m), so a coarse step well under half that
    period is sufficient to bracket every turning point without missing
    one; each bracket is then refined by golden-section search on the
    height function until it's accurate to ``refine_tolerance``.
    """

    def h(t: datetime) -> float:
        return predict_height_m(constituents, mean_level_m, t)

    samples: list[tuple[datetime, float]] = []
    t = start
    while t <= end:
        samples.append((t, h(t)))
        t += coarse_step
    if samples[-1][0] < end:
        samples.append((end, h(end)))

    extrema: list[TideExtremum] = []
    for i in range(1, len(samples) - 1):
        _, prev_h = samples[i - 1]
        _, cur_h = samples[i]
        _, next_h = samples[i + 1]
        if prev_h < cur_h > next_h:
            is_high = True
        elif prev_h > cur_h < next_h:
            is_high = False
        else:
            continue

        lo_t = samples[i - 1][0]
        hi_t = samples[i + 1][0]
        refined_t = _golden_section_extremum(h, lo_t, hi_t, is_high, refine_tolerance)
        extrema.append(TideExtremum(time=refined_t, height_m=h(refined_t), is_high=is_high))

    return extrema


_GOLDEN_RATIO = (math.sqrt(5) - 1) / 2


def _golden_section_extremum(
    h,
    lo: datetime,
    hi: datetime,
    is_high: bool,
    tolerance: timedelta,
) -> datetime:
    """Golden-section search for the timestamp of a max (or min) of ``h`` in [lo, hi]."""
    sign = 1.0 if is_high else -1.0

    def score(t: datetime) -> float:
        return sign * h(t)

    span = hi - lo
    c = hi - span * _GOLDEN_RATIO
    d = lo + span * _GOLDEN_RATIO
    fc, fd = score(c), score(d)

    while hi - lo > tolerance:
        if fc > fd:
            hi, d, fd = d, c, fc
            span = hi - lo
            c = hi - span * _GOLDEN_RATIO
            fc = score(c)
        else:
            lo, c, fc = c, d, fd
            span = hi - lo
            d = lo + span * _GOLDEN_RATIO
            fd = score(d)

    return lo + (hi - lo) / 2
