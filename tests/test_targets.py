import pytest

from trader_ai.db.targets import clear_targets, get_targets, set_targets


def test_a_valid_target_round_trips(db):
    set_targets(db, {"EQUITY": 0.7, "DEBT": 0.2, "GOLD": 0.1})
    assert get_targets(db) == pytest.approx({"EQUITY": 0.7, "DEBT": 0.2, "GOLD": 0.1})


def test_setting_a_target_replaces_the_previous_one(db):
    """A class dropped from the new target must not linger from the old one.

    Leftover rows would make the stored weights sum past 1.0.
    """
    set_targets(db, {"EQUITY": 0.6, "DEBT": 0.4})
    set_targets(db, {"EQUITY": 0.8, "GOLD": 0.2})
    assert get_targets(db) == pytest.approx({"EQUITY": 0.8, "GOLD": 0.2})


def test_weights_must_sum_to_one(db):
    with pytest.raises(ValueError, match="sum"):
        set_targets(db, {"EQUITY": 0.7, "DEBT": 0.2})


def test_float_noise_in_the_sum_is_tolerated(db):
    set_targets(db, {"EQUITY": 0.1 + 0.2, "DEBT": 0.7})
    assert sum(get_targets(db).values()) == pytest.approx(1.0)


def test_an_unknown_asset_class_is_rejected(db):
    with pytest.raises(ValueError, match="CRYPTO"):
        set_targets(db, {"EQUITY": 0.9, "CRYPTO": 0.1})


def test_unclassified_is_not_a_target(db):
    """UNCLASSIFIED means 'we could not tell', not a place to put money."""
    with pytest.raises(ValueError, match="UNCLASSIFIED"):
        set_targets(db, {"EQUITY": 0.9, "UNCLASSIFIED": 0.1})


def test_a_negative_weight_is_rejected(db):
    with pytest.raises(ValueError, match="DEBT"):
        set_targets(db, {"EQUITY": 0.9, "GOLD": 0.2, "DEBT": -0.1})


def test_percentages_are_rejected_rather_than_misread(db):
    """70 means 70%, but stored as a fraction it means 7000%. Refuse it."""
    with pytest.raises(ValueError):
        set_targets(db, {"EQUITY": 70, "DEBT": 30})


def test_an_empty_target_is_rejected(db):
    with pytest.raises(ValueError):
        set_targets(db, {})


def test_a_rejected_target_leaves_the_existing_one_intact(db):
    set_targets(db, {"EQUITY": 0.6, "DEBT": 0.4})
    with pytest.raises(ValueError):
        set_targets(db, {"EQUITY": 0.5})
    assert get_targets(db) == pytest.approx({"EQUITY": 0.6, "DEBT": 0.4})


def test_clearing_returns_to_no_target(db):
    set_targets(db, {"EQUITY": 1.0})
    clear_targets(db)
    assert get_targets(db) == {}


def test_a_zero_weight_is_stored_as_an_explicit_choice(db):
    """'No gold' is a decision; storing it keeps it visible."""
    set_targets(db, {"EQUITY": 1.0, "GOLD": 0.0})
    assert get_targets(db) == {"EQUITY": 1.0, "GOLD": 0.0}
