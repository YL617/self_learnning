"""今日学习建议 API（推荐系统 V1，只读）。

建议由 `RecommendationService` 的确定性规则引擎生成，不写入任何业务表：
不自动落 `PlanItem`，避免与既有学习计划出现两套"今天干什么"。
"""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import User
from app.schemas.recommendation import RecommendationOut, RecommendationTodayOut
from app.services.mastery import WEAK_THRESHOLD
from app.services.prerequisite import READY_THRESHOLD
from app.services.recommendation import (
    ACTION_LABELS,
    DEFAULT_RECOMMENDATION_LIMIT,
    MAX_RECOMMENDATION_LIMIT,
    RecommendationService,
)

router = APIRouter(prefix="/recommendations", tags=["recommendations"])


@router.get("/today", response_model=RecommendationTodayOut)
def today_recommendations(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    limit: int = Query(
        default=DEFAULT_RECOMMENDATION_LIMIT, ge=1, le=MAX_RECOMMENDATION_LIMIT
    ),
) -> RecommendationTodayOut:
    items = RecommendationService(db).today(current_user.id, limit=limit)
    return RecommendationTodayOut(
        date=date.today().isoformat(),
        weak_threshold=WEAK_THRESHOLD,
        ready_threshold=READY_THRESHOLD,
        items=[
            RecommendationOut(
                action=item.action,
                action_label=ACTION_LABELS[item.action],
                knowledge_point_id=item.knowledge_point_id,
                knowledge_point_name=item.knowledge_point_name,
                subject=item.subject,
                score=item.score,
                reason=item.reason,
                order=item.order,
                estimated_minutes=item.estimated_minutes,
                components=item.components,
                question_ids=list(item.question_ids),
            )
            for item in items
        ],
    )
