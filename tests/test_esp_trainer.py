"""Tests for the atemporal ESP trainer.

These exercise the protocol end to end against a temporary database, and
pin down the two properties that matter most: the target is not generated
until reveal, and scoring/stats behave correctly.
"""

import json
import math

import pytest

import esp_trainer as esp


@pytest.fixture
def db(tmp_path):
    return str(tmp_path / "test_trials.db")


def _row(db, trial_id):
    with esp.connect(db) as conn:
        return conn.execute(
            "SELECT id, created_at, reveal_after, target, guess, guess_at, "
            "revealed_at, hit FROM trials WHERE id = ?",
            (trial_id,),
        ).fetchone()


def test_new_trial_has_no_target(db):
    trial_id = esp.new_trial(db, hours_until_reveal=0)
    target = _row(db, trial_id)[3]
    assert target is None, "target must not exist until reveal"


def test_negative_hours_rejected(db):
    assert esp.new_trial(db, hours_until_reveal=-1) is None


def test_guess_is_locked_once(db):
    esp.new_trial(db, hours_until_reveal=0)
    esp.enter_guess(db, guess_text="Circle")
    esp.enter_guess(db, guess_text="square")  # should be ignored
    with esp.connect(db) as conn:
        row = esp.get_open_trial(conn)
    assert row[4] == "circle"  # normalized, first guess wins


def test_reveal_requires_a_guess(db):
    trial_id = esp.new_trial(db, hours_until_reveal=0)
    esp.reveal(db, force=True)
    assert _row(db, trial_id)[6] is None  # not revealed without a guess


def test_reveal_too_early_does_nothing(db):
    trial_id = esp.new_trial(db, hours_until_reveal=24)
    esp.enter_guess(db, guess_text="star")
    esp.reveal(db, force=False)
    row = _row(db, trial_id)
    assert row[6] is None and row[3] is None  # still blind


def test_reveal_generates_target_and_scores(db):
    trial_id = esp.new_trial(db, hours_until_reveal=0)
    esp.enter_guess(db, guess_text="triangle")
    esp.reveal(db, force=True)
    row = _row(db, trial_id)
    target, revealed_at, hit = row[3], row[6], row[7]
    assert target in esp.TARGETS
    assert revealed_at is not None
    assert hit == int(target == "triangle")


def test_hit_scoring_over_many_trials(db):
    revealed_targets = []
    for _ in range(50):
        esp.new_trial(db, hours_until_reveal=0)
        esp.enter_guess(db, guess_text="circle")
        esp.reveal(db, force=True)
    with esp.connect(db) as conn:
        rows = conn.execute("SELECT target, guess, hit FROM trials").fetchall()
    for target, guess, hit in rows:
        assert hit == int(target == guess)
        revealed_targets.append(target)
    # Fresh randomness should produce more than one distinct target.
    assert len(set(revealed_targets)) > 1


def test_export_roundtrip(db, tmp_path):
    esp.new_trial(db, hours_until_reveal=0)
    esp.enter_guess(db, guess_text="hexagon")
    esp.reveal(db, force=True)
    out = tmp_path / "export.json"
    esp.export_json(db, str(out))
    data = json.loads(out.read_text())
    assert len(data) == 1
    assert data[0]["guess"] == "hexagon"
    assert data[0]["target"] in esp.TARGETS


def test_binomial_tail_basic():
    # P(X >= 0) == 1
    assert esp.binomial_tail(0, 10, 0.1) == pytest.approx(1.0)
    # P(X >= n) == p**n
    assert esp.binomial_tail(10, 10, 0.1) == pytest.approx(0.1 ** 10)
    # Symmetry sanity for a fair coin: P(X>=3 of 4) == comb sum
    expected = sum(math.comb(4, i) * 0.5 ** 4 for i in range(3, 5))
    assert esp.binomial_tail(3, 4, 0.5) == pytest.approx(expected)


def test_binomial_tail_no_trials_is_nan():
    assert math.isnan(esp.binomial_tail(0, 0, 0.1))


def test_normalize():
    assert esp.normalize("  Wavy   LINE ") == "wavy line"
