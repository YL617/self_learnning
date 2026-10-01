"""Mastery 确定性算法单测（不依赖数据库）。

覆盖：初始中性基线、答对上升、答错下降、0~100 clamp、
难度权重、角色权重、连续答对奖励、复习系数。
"""

from app.services.mastery import (
    DIFFICULTY_WEIGHTS,
    MASTERY_INITIAL,
    MASTERY_MAX,
    MASTERY_MIN,
    ROLE_WEIGHTS,
    clamp,
    compute_delta,
    difficulty_weight,
    next_score,
    role_weight,
)


def test_clamp_bounds():
    assert clamp(-100) == MASTERY_MIN
    assert clamp(1000) == MASTERY_MAX
    assert clamp(72.4) == 72
    assert clamp(72.6) == 73


def test_initial_baseline_is_neutral():
    assert MASTERY_INITIAL == 50


def test_correct_raises_and_wrong_lowers():
    up = next_score(MASTERY_INITIAL, correct=True, difficulty="medium", role="primary")
    down = next_score(MASTERY_INITIAL, correct=False, difficulty="medium", role="primary")
    assert up > MASTERY_INITIAL
    assert down < MASTERY_INITIAL


def test_single_question_never_reaches_100_or_0():
    one_answer = next_score(MASTERY_INITIAL, correct=True, difficulty="hard", role="primary")
    assert one_answer < MASTERY_MAX
    one_wrong = next_score(MASTERY_INITIAL, correct=False, difficulty="hard", role="primary")
    assert one_wrong > MASTERY_MIN


def test_score_always_clamped_to_range():
    score = MASTERY_INITIAL
    for _ in range(60):
        score = next_score(score, correct=True, difficulty="hard", role="primary")
        assert MASTERY_MIN <= score <= MASTERY_MAX
    assert score == MASTERY_MAX
    for _ in range(60):
        score = next_score(score, correct=False, difficulty="hard", role="primary")
        assert MASTERY_MIN <= score <= MASTERY_MAX
    assert score == MASTERY_MIN


def test_difficulty_weight_ordering():
    easy = next_score(MASTERY_INITIAL, correct=True, difficulty="easy", role="primary")
    medium = next_score(MASTERY_INITIAL, correct=True, difficulty="medium", role="primary")
    hard = next_score(MASTERY_INITIAL, correct=True, difficulty="hard", role="primary")
    assert easy < medium < hard
    assert difficulty_weight("easy") < difficulty_weight("medium") < difficulty_weight("hard")


def test_primary_weight_greater_than_secondary():
    primary = next_score(MASTERY_INITIAL, correct=True, difficulty="medium", role="primary")
    secondary = next_score(MASTERY_INITIAL, correct=True, difficulty="medium", role="secondary")
    assert secondary < primary
    assert role_weight("primary") == ROLE_WEIGHTS["primary"] == 1.0
    assert role_weight("secondary") == 0.5
    # 次知识点的降幅也更小
    assert (
        next_score(MASTERY_INITIAL, correct=False, difficulty="medium", role="secondary")
        > next_score(MASTERY_INITIAL, correct=False, difficulty="medium", role="primary")
    )


def test_unknown_role_or_difficulty_falls_back_to_medium():
    assert difficulty_weight("impossible") == DIFFICULTY_WEIGHTS["medium"]
    assert role_weight("weird") == 0.5


def test_streak_increases_gain_and_is_capped():
    plain = next_score(MASTERY_INITIAL, correct=True, streak=0)
    streaked = next_score(MASTERY_INITIAL, correct=True, streak=1)
    much = next_score(MASTERY_INITIAL, correct=True, streak=3)
    capped = next_score(MASTERY_INITIAL, correct=True, streak=99)
    assert plain < streaked < much
    assert capped == next_score(MASTERY_INITIAL, correct=True, streak=5)


def test_headroom_makes_high_scores_slower_to_grow():
    low_gain = compute_delta(20, correct=True)
    high_gain = compute_delta(90, correct=True)
    assert high_gain < low_gain


def test_loss_shrinks_near_zero():
    high_loss = abs(compute_delta(90, correct=False))
    low_loss = abs(compute_delta(10, correct=False))
    assert low_loss < high_loss


def test_review_multiplier_increases_gain():
    normal = next_score(MASTERY_INITIAL, correct=True, reviewed=False)
    reviewed = next_score(MASTERY_INITIAL, correct=True, reviewed=True)
    assert reviewed > normal


def test_algorithm_is_deterministic():
    first = next_score(55, correct=True, difficulty="hard", role="secondary", streak=2)
    second = next_score(55, correct=True, difficulty="hard", role="secondary", streak=2)
    assert first == second
