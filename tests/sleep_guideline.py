"""Unit tests for tools/sleep_guidelines.py — boundary ages and validation."""

import pytest

from schemas import VerdictLabel
from tools.sleep_guidelines import (
    evaluate_duration_against_guideline,
    fetch_source_verification,
    get_recommended_hours,
)


@pytest.mark.parametrize(
    "age_years,expected_label,expected_min,expected_max",
    [
        (0.0, "Newborn (0-3 months)", 14, 17),
        (0.249, "Newborn (0-3 months)", 14, 17),
        (0.25, "Infant (4-12 months)", 12, 16),
        (0.999, "Infant (4-12 months)", 12, 16),
        (1.0, "Toddler (1-2 years)", 11, 14),
        (2.999, "Toddler (1-2 years)", 11, 14),
        (3.0, "Preschool (3-5 years)", 10, 13),
        (5.999, "Preschool (3-5 years)", 10, 13),
        (6.0, "School age (6-12 years)", 9, 12),
        (12.999, "School age (6-12 years)", 9, 12),
        (13.0, "Teen (13-18 years)", 8, 10),
        (17.999, "Teen (13-18 years)", 8, 10),
        (18.0, "Adult (18-64 years)", 7, 9),  # boundary: must land in Adult, not Teen
        (64.999, "Adult (18-64 years)", 7, 9),
        (65.0, "Older adult (65+ years)", 7, 8),
        (100.0, "Older adult (65+ years)", 7, 8),
    ],
)
def test_get_recommended_hours_boundaries(age_years, expected_label, expected_min, expected_max):
    guideline = get_recommended_hours(age_years)
    assert guideline.label == expected_label
    assert guideline.min_hours == expected_min
    assert guideline.max_hours == expected_max


def test_get_recommended_hours_rejects_negative_age():
    with pytest.raises(ValueError):
        get_recommended_hours(-0.001)


def test_evaluate_duration_within_range_is_on_track():
    result = evaluate_duration_against_guideline(30, 8.0)
    assert result["within_range"] is True
    assert result["verdict"] == VerdictLabel.ON_TRACK


def test_evaluate_duration_below_range_needs_attention():
    result = evaluate_duration_against_guideline(30, 6.2)
    assert result["within_range"] is False
    assert result["verdict"] == VerdictLabel.NEEDS_ATTENTION


def test_evaluate_duration_above_range_is_improving():
    result = evaluate_duration_against_guideline(70, 10.5)
    assert result["within_range"] is False
    assert result["verdict"] == VerdictLabel.IMPROVING


def test_evaluate_duration_rejects_negative_duration():
    with pytest.raises(ValueError):
        evaluate_duration_against_guideline(30, -1)


def test_normal_lookups_never_touch_network(monkeypatch):
    """get_recommended_hours / evaluate_duration_against_guideline must never
    call urllib — only fetch_source_verification() is allowed to."""
    import urllib.request

    def _forbidden(*args, **kwargs):
        raise AssertionError("Network access attempted from a non-verification call.")

    monkeypatch.setattr(urllib.request, "urlopen", _forbidden)

    get_recommended_hours(30)
    evaluate_duration_against_guideline(30, 8.0)
    # If we get here without the monkeypatched urlopen firing, we're clean.


def test_fetch_source_verification_is_opt_in_and_cached(monkeypatch):
    """fetch_source_verification() should only hit the network when called,
    and should cache the result until force_refresh=True."""
    import tools.sleep_guidelines as sg

    sg._verification_cache = None
    call_count = {"n": 0}

    class _FakeResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def _fake_urlopen(request, timeout=10):
        call_count["n"] += 1
        return _FakeResponse()

    monkeypatch.setattr("urllib.request.urlopen", _fake_urlopen)

    result_1 = fetch_source_verification()
    result_2 = fetch_source_verification()  # should use cache, not call again
    assert call_count["n"] == 1
    assert result_1 == result_2
    assert result_1["reachable"] is True

    fetch_source_verification(force_refresh=True)
    assert call_count["n"] == 2

    sg._verification_cache = None  # reset for other tests