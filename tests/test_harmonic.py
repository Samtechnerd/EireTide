"""Tests for the astronomical harmonic tide engine in
custom_components/irish_tides/harmonic.py.

This session's network egress is policy-restricted, so these tests can't
fetch a live NOAA/UKHO station's official predictions to diff against.
Instead they validate the engine against independently-verifiable
astronomical facts that don't require any external data:

- Each constituent's equilibrium argument V0(t) must have a rate of change
  (finite-difference derivative) equal to its tabulated speed -- this is
  effectively a from-scratch re-derivation of the speed table from the
  orbital element formulas, and confirms the argument formulas are
  correctly composed.
- The Moon's mean longitude must advance at the well-known sidereal month
  rate (27.32 days/revolution) and the node must regress at the well-known
  18.6-year nodal cycle rate -- both textbook constants, not tide-specific.
- The spring/neap beat between M2 and S2 must match half the synodic month
  (~14.77 days) -- the fact that spring tides occur at new and full moon.
- Sanity checks on amplitude bounds and high/low spacing for a pure M2
  signal.
"""
from __future__ import annotations

import importlib.util
import math
import sys
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest


def _load_irish_tides_module(name: str):
    package_dir = Path(__file__).resolve().parents[1] / "custom_components" / "irish_tides"
    package_name = "irish_tides_under_test"

    if package_name not in sys.modules:
        package = types.ModuleType(package_name)
        package.__path__ = [str(package_dir)]
        sys.modules[package_name] = package

    full_name = f"{package_name}.{name}"
    if full_name in sys.modules:
        return sys.modules[full_name]
    spec = importlib.util.spec_from_file_location(full_name, package_dir / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[full_name] = module
    spec.loader.exec_module(module)
    return module


harmonic = _load_irish_tides_module("harmonic")

EPOCH = datetime(2026, 7, 19, 12, 0, 0, tzinfo=timezone.utc)


@pytest.mark.parametrize("name", harmonic.KNOWN_CONSTITUENTS)
def test_equilibrium_argument_matches_tabulated_speed(name: str) -> None:
    """dV0/dt must equal the constituent's tabulated speed (deg/hour)."""
    # Small enough that even the fastest constituent (M6, ~87 deg/h) moves
    # well under 180 deg between samples, so the wraparound unwrap below is
    # unambiguous.
    dt_hours = 0.5
    t0 = EPOCH
    t1 = EPOCH + timedelta(hours=dt_hours)

    v0_0 = harmonic._equilibrium_argument(name, harmonic.astronomical_arguments(t0))
    v0_1 = harmonic._equilibrium_argument(name, harmonic.astronomical_arguments(t1))

    # Unwrap the 0-360 wraparound before differencing.
    delta = v0_1 - v0_0
    if delta < -180:
        delta += 360
    elif delta > 180:
        delta -= 360

    measured_speed = delta / dt_hours
    assert measured_speed == pytest.approx(harmonic.CONSTITUENT_SPEEDS[name], abs=2e-4)


def test_lunar_sidereal_month() -> None:
    """The Moon's mean longitude s should advance at the sidereal month rate (27.32 days)."""
    t0 = EPOCH
    t1 = EPOCH + timedelta(days=1)
    s0 = harmonic.astronomical_arguments(t0).s
    s1 = harmonic.astronomical_arguments(t1).s
    delta = (s1 - s0) % 360.0

    sidereal_month_days = 27.321661
    expected_deg_per_day = 360.0 / sidereal_month_days
    assert delta == pytest.approx(expected_deg_per_day, abs=1e-3)


def test_nodal_precession_period() -> None:
    """The ascending node should regress with an 18.6-year period."""
    t0 = EPOCH
    t1 = EPOCH + timedelta(days=365.25)
    n0 = harmonic.astronomical_arguments(t0).N
    n1 = harmonic.astronomical_arguments(t1).N
    delta = (n0 - n1) % 360.0  # N regresses, so n0 > n1 modulo wraparound

    period_years = 360.0 / delta
    assert period_years == pytest.approx(18.6, abs=0.05)


def test_spring_neap_beat_matches_half_synodic_month() -> None:
    """M2/S2 realign (spring tide) every half synodic month (~14.77 days).

    Rather than assuming a particular alignment at t=0 (M2 and S2 don't
    share a common phase reference, so equal g values don't mean they start
    in sync), this scans the combined range over a month and checks the two
    extremes directly: the spacing between successive neaps should match
    half the synodic month, and the min/max ranges should match the
    constructive/destructive interference of the two constituents.
    """
    constituents = [
        harmonic.HarmonicConstituent("M2", amplitude_m=1.0, phase_deg=0.0),
        harmonic.HarmonicConstituent("S2", amplitude_m=0.4, phase_deg=0.0),
    ]

    def semidiurnal_range(day_offset: float) -> float:
        base = EPOCH + timedelta(days=day_offset)
        heights = [
            harmonic.predict_height_m(constituents, 0.0, base + timedelta(minutes=m))
            for m in range(0, 13 * 60, 10)
        ]
        return max(heights) - min(heights)

    step_days = 0.1
    first_window = [i * step_days for i in range(int(10 / step_days))]
    first_ranges = [semidiurnal_range(d) for d in first_window]
    first_min_day = first_window[min(range(len(first_ranges)), key=first_ranges.__getitem__)]

    second_window = [16 + i * step_days for i in range(int(6 / step_days))]
    second_ranges = [semidiurnal_range(d) for d in second_window]
    second_min_day = second_window[min(range(len(second_ranges)), key=second_ranges.__getitem__)]

    half_synodic_days = 29.530589 / 2
    assert (second_min_day - first_min_day) == pytest.approx(half_synodic_days, abs=0.3)

    max_window = [20 + i * step_days for i in range(int(10 / step_days))]
    max_range = max(semidiurnal_range(d) for d in max_window)
    min_range = min(first_ranges + second_ranges)

    # Constructive interference (spring) approaches 2*(H_M2+H_S2); destructive
    # (neap) approaches 2*|H_M2-H_S2|. The M2 node factor varies the lunar
    # amplitude +/-3.7% over the 18.6y cycle, so allow slack for that.
    assert max_range == pytest.approx(2 * (1.0 + 0.4), rel=0.05)
    assert min_range == pytest.approx(2 * abs(1.0 - 0.4), rel=0.08)


def test_pure_m2_signal_is_bounded_and_periodic() -> None:
    constituents = [harmonic.HarmonicConstituent("M2", amplitude_m=2.0, phase_deg=45.0)]
    for minutes in range(0, 60 * 24, 37):
        h = harmonic.predict_height_m(constituents, 10.0, EPOCH + timedelta(minutes=minutes))
        assert 10.0 - 2.05 <= h <= 10.0 + 2.05  # node factor f is always close to 1


def test_find_extrema_spacing_for_pure_m2() -> None:
    constituents = [harmonic.HarmonicConstituent("M2", amplitude_m=1.5, phase_deg=0.0)]
    start = EPOCH
    end = EPOCH + timedelta(hours=48)
    extrema = harmonic.find_extrema(constituents, 0.0, start, end)

    # M2 period is ~12.4206 h, so high-to-low (half period) is ~6.21h apart,
    # and 48h should show ~7-8 highs/lows alternating.
    assert 6 <= len(extrema) <= 9
    for a, b in zip(extrema, extrema[1:]):
        assert a.is_high != b.is_high
        gap_hours = (b.time - a.time).total_seconds() / 3600.0
        assert 5.5 <= gap_hours <= 7.0  # roughly half an M2 period apart

    highs = [e for e in extrema if e.is_high]
    lows = [e for e in extrema if not e.is_high]
    assert all(e.height_m == pytest.approx(1.5, abs=0.05) for e in highs)
    assert all(e.height_m == pytest.approx(-1.5, abs=0.05) for e in lows)


def test_unknown_constituent_rejected() -> None:
    with pytest.raises(ValueError):
        harmonic.HarmonicConstituent("Z9", amplitude_m=1.0, phase_deg=0.0)


def test_parse_constituents_text_is_case_insensitive() -> None:
    # Mixed-case names (Mm, Mf, Ssa, Sa) must round-trip regardless of the
    # case the user typed them in.
    parsed = harmonic.parse_constituents_text("m2 1.90 137\nS2 0.70 171\nMm 0.05 10\nssa 0.02 5")
    assert [c.name for c in parsed] == ["M2", "S2", "Mm", "Ssa"]
    assert parsed[0].amplitude_m == pytest.approx(1.90)
    assert parsed[0].phase_deg == pytest.approx(137.0)


def test_parse_constituents_text_rejects_duplicates() -> None:
    with pytest.raises(ValueError, match="more than once"):
        harmonic.parse_constituents_text("M2 1.0 0\nm2 1.0 0")


def test_parse_constituents_text_rejects_unknown_name() -> None:
    with pytest.raises(ValueError, match="unknown constituent"):
        harmonic.parse_constituents_text("Z9 1.0 0")


def test_parse_constituents_text_rejects_malformed_line() -> None:
    with pytest.raises(ValueError, match="expected 'NAME AMPLITUDE PHASE'"):
        harmonic.parse_constituents_text("M2 1.0")


def test_parse_constituents_text_rejects_empty_input() -> None:
    with pytest.raises(ValueError, match="At least one constituent"):
        harmonic.parse_constituents_text("   \n\n")
