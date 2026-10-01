"""大阶段 3：今日建议引擎（推荐系统 V1）单元测试。

覆盖：动作优先级、打分单调性（缺口/解锁/目标/时效）、确定性、V2 数据规模门禁。
打分函数是纯函数，因此可以在无 DB 的情况下精确断言。
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.services.recommendation import (
    ACTION_LEARN_NEW,
    ACTION_PRACTICE,
    ACTION_REVIEW_WEAK,
    ACTION_REVIEW_WRONG,
    BASE_SCORES,
    MAX_RECOMMENDATION_LIMIT,
    V2_BKT_GATES,
    V2_DEEP_GATES,
    DataScaleSnapshot,
    RecommendationService,
    check_bkt_gate,
    check_deep_kt_gate,
)


@pytest.fixture()
def engine_service() -> RecommendationService:
    """只用于调用纯函数 `_score`，不访问数据库。"""
    return RecommendationService(None)  # type: ignore[arg-type]


NOW = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)


def test_action_priority_is_strictly_ordered():
    assert (
        BASE_SCORES[ACTION_REVIEW_WRONG]
        > BASE_SCORES[ACTION_REVIEW_WEAK]
        > BASE_SCORES[ACTION_LEARN_NEW]
        > BASE_SCORES[ACTION_PRACTICE]
    )


def test_lower_mastery_scores_higher(engine_service):
    low, _ = engine_service._score(
        action=ACTION_REVIEW_WEAK, mastery_score=20, unlock_count=0,
        goal_hit=False, last_answered_at=None, now=NOW,
    )
    high, _ = engine_service._score(
        action=ACTION_REVIEW_WEAK, mastery_score=55, unlock_count=0,
        goal_hit=False, last_answered_at=None, now=NOW,
    )
    assert low > high


def test_more_unlocks_score_higher(engine_service):
    none, _ = engine_service._score(
        action=ACTION_LEARN_NEW, mastery_score=50, unlock_count=0,
        goal_hit=False, last_answered_at=None, now=NOW,
    )
    some, _ = engine_service._score(
        action=ACTION_LEARN_NEW, mastery_score=50, unlock_count=3,
        goal_hit=False, last_answered_at=None, now=NOW,
    )
    many, _ = engine_service._score(
        action=ACTION_LEARN_NEW, mastery_score=50, unlock_count=20,
        goal_hit=False, last_answered_at=None, now=NOW,
    )
    assert none < some < many
    # 解锁加成封顶，不会让分数无界膨胀
    assert many <= none * 2


def test_goal_hit_gets_bonus(engine_service):
    plain, _ = engine_service._score(
        action=ACTION_LEARN_NEW, mastery_score=50, unlock_count=0,
        goal_hit=False, last_answered_at=None, now=NOW,
    )
    boosted, components = engine_service._score(
        action=ACTION_LEARN_NEW, mastery_score=50, unlock_count=0,
        goal_hit=True, last_answered_at=None, now=NOW,
    )
    assert boosted > plain
    assert components["goal"] > 1.0


def test_recent_activity_is_downweighted(engine_service):
    fresh, components = engine_service._score(
        action=ACTION_PRACTICE, mastery_score=70, unlock_count=0, goal_hit=False,
        last_answered_at=NOW - timedelta(days=1), now=NOW,
    )
    stale, _ = engine_service._score(
        action=ACTION_PRACTICE, mastery_score=70, unlock_count=0, goal_hit=False,
        last_answered_at=NOW - timedelta(days=30), now=NOW,
    )
    assert fresh < stale
    assert components["recency"] < 1.0


def test_naive_last_answered_at_is_handled(engine_service):
    """DB 读回的时间可能没有 tzinfo；不能因此抛错或误判。"""
    # 刻意去掉 tzinfo，模拟从数据库读回的 naive datetime
    naive_stamp = (NOW - timedelta(hours=12)).replace(tzinfo=None)
    score, components = engine_service._score(
        action=ACTION_PRACTICE, mastery_score=70, unlock_count=0, goal_hit=False,
        last_answered_at=naive_stamp, now=NOW,
    )
    assert score > 0
    # 半年前才算"最近"，此处应判定为不新鲜
    assert components["recency"] < 1.0


def test_score_is_deterministic(engine_service):
    kwargs = {
        "action": ACTION_REVIEW_WRONG,
        "mastery_score": 42,
        "unlock_count": 2,
        "goal_hit": True,
        "last_answered_at": NOW - timedelta(days=10),
        "now": NOW,
        "urgency": 1.3,
    }
    first, first_components = engine_service._score(**kwargs)
    second, second_components = engine_service._score(**kwargs)
    assert first == second
    assert first_components == second_components
    # 分解项可复现地还原总分
    product = 1.0
    for key in ("base", "urgency", "gap", "goal", "unlock", "recency"):
        product *= first_components[key]
    assert round(product, 2) == pytest.approx(first, abs=0.05)


def test_urgency_caps(engine_service):
    low, _low_components = engine_service._score(
        action=ACTION_REVIEW_WRONG, mastery_score=50, unlock_count=0, goal_hit=False,
        last_answered_at=None, now=NOW, urgency=1.0,
    )
    high, high_components = engine_service._score(
        action=ACTION_REVIEW_WRONG, mastery_score=50, unlock_count=0, goal_hit=False,
        last_answered_at=None, now=NOW, urgency=1.6,
    )
    assert high > low
    assert high_components["urgency"] == 1.6


# ---------------------------------------------------------------- V2 门禁
def _snapshot(**overrides) -> DataScaleSnapshot:
    base = {
        "total_answers": 0,
        "user_count": 1,
        "knowledge_point_count": 0,
        "question_count": 0,
        "tagged_question_count": 0,
        "per_kp_answer_counts": (),
    }
    base.update(overrides)
    return DataScaleSnapshot(**base)


def test_gate_constants_match_documented_thresholds():
    assert V2_BKT_GATES == {
        "min_total_answers": 5_000,
        "min_median_kp_answers": 30,
        "min_users": 50,
        "min_kp_coverage": 0.8,
    }
    assert V2_DEEP_GATES == {"min_total_answers": 100_000, "min_users": 1_000}


def test_bkt_gate_rejects_tiny_dataset():
    result = check_bkt_gate(_snapshot())
    assert result.allowed is False
    assert len(result.failed) == 4
    assert any("5000" in reason for reason in result.failed)
    assert any("30" in reason for reason in result.failed)


def test_bkt_gate_allows_when_all_thresholds_met():
    result = check_bkt_gate(
        _snapshot(
            total_answers=6_000,
            user_count=60,
            question_count=100,
            tagged_question_count=90,
            per_kp_answer_counts=(30, 40, 50),
        )
    )
    assert result.allowed is True
    assert result.failed == ()


def test_bkt_gate_rejects_low_kp_coverage_even_with_enough_answers():
    result = check_bkt_gate(
        _snapshot(
            total_answers=20_000,
            user_count=80,
            question_count=100,
            tagged_question_count=50,
            per_kp_answer_counts=(100, 100),
        )
    )
    assert result.allowed is False
    assert any("覆盖率" in reason for reason in result.failed)


def test_deep_kt_gate_needs_two_orders_of_magnitude_more():
    assert check_deep_kt_gate(_snapshot(total_answers=20_000, user_count=80)).allowed is False
    assert check_deep_kt_gate(
        _snapshot(total_answers=120_000, user_count=1_200)
    ).allowed is True


def test_median_is_used_not_mean():
    # 中位数 30，即使均值很高也必须只按中位数判断
    snapshot = _snapshot(
        total_answers=6_000,
        user_count=60,
        question_count=10,
        tagged_question_count=9,
        per_kp_answer_counts=(1, 30, 10_000),
    )
    assert snapshot.median_kp_answers == 30
    assert check_bkt_gate(snapshot).allowed is True


def test_kp_coverage_is_guarded_against_zero_questions():
    assert _snapshot().kp_coverage == 0.0


def test_limit_is_bounded():
    assert MAX_RECOMMENDATION_LIMIT >= 1
