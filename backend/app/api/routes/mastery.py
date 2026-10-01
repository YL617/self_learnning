"""知识点掌握度 API（大阶段 2）。

只读接口：掌握度由答题事务内的 MasteryService 维护，不提供客户端直接写入，
避免出现"绕过答题改分数"的漏洞。
"""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import User, UserKnowledgePointMastery, WrongBookItem
from app.schemas.mastery import KnowledgePointBrief, MasteryOut, MasterySummary
from app.services.mastery import WEAK_THRESHOLD, MasteryService

router = APIRouter(prefix="/mastery", tags=["mastery"])


def _decorate(
    db: Session, rows: list[UserKnowledgePointMastery]
) -> list[MasteryOut]:
    """补齐知识点名称等展示字段（表本身只存 id，避免跨表冗余）。"""
    service = MasteryService(db)
    knowledge_points = service.knowledge_points_by_ids(
        [row.knowledge_point_id for row in rows]
    )
    payload: list[MasteryOut] = []
    for row in rows:
        item = MasteryOut.model_validate(row)
        knowledge_point = knowledge_points.get(row.knowledge_point_id)
        if knowledge_point is not None:
            item.knowledge_point = KnowledgePointBrief.model_validate(knowledge_point)
        payload.append(item)
    return payload


@router.get("", response_model=list[MasteryOut])
def list_mastery(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    limit: int | None = Query(default=None, ge=1, le=500),
) -> list[MasteryOut]:
    rows = MasteryService(db).list_for_user(current_user.id, limit=limit)
    return _decorate(db, rows)


@router.get("/summary", response_model=MasterySummary)
def mastery_summary(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> MasterySummary:
    service = MasteryService(db)
    total = db.scalar(
        select(func.count(UserKnowledgePointMastery.id)).where(
            UserKnowledgePointMastery.user_id == current_user.id
        )
    ) or 0
    weak_count = db.scalar(
        select(func.count(UserKnowledgePointMastery.id)).where(
            UserKnowledgePointMastery.user_id == current_user.id,
            UserKnowledgePointMastery.attempt_count >= 1,
            UserKnowledgePointMastery.mastery_score < WEAK_THRESHOLD,
        )
    ) or 0
    today_review_count = db.scalar(
        select(func.count(WrongBookItem.id)).where(
            WrongBookItem.user_id == current_user.id,
            WrongBookItem.mastered.is_(False),
            WrongBookItem.next_review_date <= date.today(),
        )
    ) or 0
    return MasterySummary(
        total=int(total),
        weak_count=int(weak_count),
        average_score=round(service.average_score(current_user.id), 1),
        today_review_count=int(today_review_count),
        weak_threshold=WEAK_THRESHOLD,
    )


@router.get("/weak", response_model=list[MasteryOut])
def list_weak_mastery(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    threshold: int = Query(default=WEAK_THRESHOLD, ge=0, le=100),
    limit: int = Query(default=10, ge=1, le=100),
) -> list[MasteryOut]:
    rows = MasteryService(db).list_weak(
        current_user.id, threshold=threshold, limit=limit
    )
    return _decorate(db, rows)


@router.get("/{knowledge_point_id}", response_model=MasteryOut)
def get_mastery(
    knowledge_point_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> MasteryOut:
    row = MasteryService(db).get(current_user.id, knowledge_point_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="暂无该知识点的掌握度记录"
        )
    return _decorate(db, [row])[0]
