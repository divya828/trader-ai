import pytest

from trader_ai.analytics.measurement import Measurement


def test_available_carries_a_value():
    m = Measurement.of(0.12)
    assert m.available is True
    assert m.value == pytest.approx(0.12)
    assert m.reason is None


def test_unavailable_carries_a_reason_and_no_value():
    m = Measurement.unavailable("no NAV coverage")
    assert m.available is False
    assert m.value is None
    assert m.reason == "no NAV coverage"


def test_unavailable_requires_a_nonempty_reason():
    with pytest.raises(ValueError, match="reason"):
        Measurement.unavailable("")


def test_value_access_on_unavailable_is_explicit_not_silent():
    m = Measurement.unavailable("insufficient cashflows")
    # .value is None rather than raising, but truthiness must not read as a
    # usable number: an unavailable measurement is falsy.
    assert not m
    assert bool(Measurement.of(0.0)) is True  # a real zero IS available


def test_zero_is_available_not_missing():
    # A genuine 0.0 result must never be confused with "no data".
    m = Measurement.of(0.0)
    assert m.available is True
    assert m.value == 0.0


def test_or_else_returns_value_when_available():
    assert Measurement.of(5.0).or_else(99.0) == 5.0


def test_or_else_returns_default_when_unavailable():
    assert Measurement.unavailable("x").or_else(99.0) == 99.0


def test_measurement_is_immutable():
    import dataclasses

    m = Measurement.of(1.0)
    with pytest.raises(dataclasses.FrozenInstanceError):
        m.value = 2.0  # type: ignore[misc]
