"""Tests for the pure-logic OvershootLearner (no Home Assistant deps)."""
from custom_components.onna.overshoot import (
    OvershootLearner,
    EMA_ALPHA,
    SAMPLE_MAX,
    APPLY_THRESHOLD,
    DAMPING_MAX,
)


def test_new_learner_has_zero_and_no_damping():
    lrn = OvershootLearner()
    assert lrn.learned_heat == 0.0
    assert lrn.learned_cool == 0.0
    assert lrn.sampling is False
    assert lrn.damping(is_winter=True) == 0.0
    assert lrn.damping(is_winter=False) == 0.0


def test_heat_sample_learns_peak_minus_start():
    lrn = OvershootLearner()
    lrn.start_sample(start_temp=21.0, is_winter=True)
    assert lrn.sampling is True
    lrn.observe(21.4)
    lrn.observe(21.8)  # peak
    lrn.observe(21.6)  # falls back
    lrn.close_sample()
    # sample = 21.8 - 21.0 = 0.8 ; learned = 0.3 * 0.8 = 0.24
    assert lrn.learned_heat == round(EMA_ALPHA * 0.8, 10)
    assert lrn.learned_cool == 0.0
    assert lrn.sampling is False


def test_cool_sample_learns_start_minus_trough():
    lrn = OvershootLearner()
    lrn.start_sample(start_temp=25.0, is_winter=False)
    lrn.observe(24.6)
    lrn.observe(24.2)  # trough
    lrn.observe(24.5)
    lrn.close_sample()
    # sample = 25.0 - 24.2 = 0.8 ; learned = 0.3 * 0.8
    assert lrn.learned_cool == round(EMA_ALPHA * 0.8, 10)
    assert lrn.learned_heat == 0.0


def test_sample_is_clamped_to_sample_max():
    lrn = OvershootLearner()
    lrn.start_sample(start_temp=20.0, is_winter=True)
    lrn.observe(99.0)  # absurd peak
    lrn.close_sample()
    assert lrn.learned_heat == round(EMA_ALPHA * SAMPLE_MAX, 10)


def test_ema_blends_prior_and_new():
    lrn = OvershootLearner(learned_heat=1.0)
    lrn.start_sample(start_temp=20.0, is_winter=True)
    lrn.observe(20.5)  # sample 0.5
    lrn.close_sample()
    # 0.3 * 0.5 + 0.7 * 1.0 = 0.85
    assert lrn.learned_heat == round(EMA_ALPHA * 0.5 + (1 - EMA_ALPHA) * 1.0, 10)


def test_invalidate_drops_in_flight_sample_without_learning():
    lrn = OvershootLearner(learned_heat=0.5)
    lrn.start_sample(start_temp=20.0, is_winter=True)
    lrn.observe(21.0)
    lrn.invalidate()
    assert lrn.sampling is False
    assert lrn.learned_heat == 0.5  # unchanged


def test_sample_without_observations_does_not_change_learned():
    # A coast window shorter than the external sensor's reporting interval
    # receives zero observe() calls; extreme stays == start.  Such a sample
    # measured nothing and must be discarded, not blended in as 0 (which would
    # decay the learned value toward zero every time — the real-world bug).
    lrn = OvershootLearner(learned_cool=0.6)
    lrn.start_sample(start_temp=25.0, is_winter=False)
    lrn.close_sample()  # no observe() in between
    assert lrn.learned_cool == 0.6  # unchanged, not decayed
    assert lrn.sampling is False


def test_observe_and_close_are_noops_when_not_sampling():
    lrn = OvershootLearner(learned_heat=0.5)
    lrn.observe(30.0)      # ignored
    lrn.close_sample()     # ignored
    assert lrn.learned_heat == 0.5


def test_damping_below_threshold_is_zero():
    lrn = OvershootLearner(learned_heat=APPLY_THRESHOLD - 0.01)
    assert lrn.damping(is_winter=True) == 0.0


def test_damping_at_or_above_threshold_returns_learned():
    lrn = OvershootLearner(learned_heat=0.5, learned_cool=0.3)
    assert lrn.damping(is_winter=True) == 0.5
    assert lrn.damping(is_winter=False) == 0.3


def test_damping_is_clamped_to_max():
    lrn = OvershootLearner(learned_heat=DAMPING_MAX + 1.0)
    assert lrn.damping(is_winter=True) == DAMPING_MAX


def test_round_trip_serialization():
    lrn = OvershootLearner(learned_heat=0.4, learned_cool=0.7)
    restored = OvershootLearner.from_dict(lrn.as_dict())
    assert restored.learned_heat == 0.4
    assert restored.learned_cool == 0.7
