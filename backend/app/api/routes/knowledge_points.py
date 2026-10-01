from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin, get_current_user
from app.core.database import get_db
from app.models import KnowledgePoint, Question, User
from app.schemas.knowledge import (
    KnowledgePointCreate,
    KnowledgePointRead,
    KnowledgePointUpdate,
)
from app.schemas.mastery import KnowledgePointBrief
from app.schemas.prerequisite import (
    LearningPathOut,
    LearningPathStep,
    PrerequisiteCreate,
    PrerequisiteDetailOut,
    PrerequisiteRead,
    PrerequisiteSuggestion,
    PrerequisiteSuggestOut,
)
from app.schemas.question import QuestionOut
from app.services.knowledge_point_service import (
    DuplicateKnowledgePoint,
    InvalidParent,
    KnowledgePointHasChildren,
    KnowledgePointInUse,
    KnowledgePointNotFound,
    KnowledgePointService,
    ParentCycleError,
)
from app.services.mastery import MasteryService
from app.services.prerequisite import (
    EDGE_SOURCE_MANUAL,
    READY_THRESHOLD,
    DuplicatePrerequisite,
    PrerequisiteCycle,
    PrerequisiteLinkNotFound,
    PrerequisiteService,
    SelfLoopPrerequisite,
)
from app.services.prerequisite import (
    KnowledgePointNotFound as PrerequisiteKnowledgePointNotFound,
)
from app.services.prerequisite_suggest import suggest_prerequisites
from app.services.question_knowledge_point_service import (
    KnowledgePointNotFound as QuestionKpNotFound,
)
from app.services.question_knowledge_point_service import (
    QuestionKnowledgePointService,
)

router = APIRouter(prefix="/knowledge-points", tags=["knowledge-points"])


def _service(db: Session) -> KnowledgePointService:
    return KnowledgePointService(db)


@router.get("", response_model=list[KnowledgePointRead])
def list_knowledge_points(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    subject: str | None = Query(default=None),
    parent_id: int | None = Query(default=None),
    q: str | None = Query(default=None),
) -> list[KnowledgePoint]:
    return _service(db).list_all(subject=subject, parent_id=parent_id, query=q)


@router.get("/{knowledge_point_id}", response_model=KnowledgePointRead)
def get_knowledge_point(
    knowledge_point_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> KnowledgePoint:
    try:
        return _service(db).get(knowledge_point_id) or _raise_not_found()
    except KnowledgePointNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/{knowledge_point_id}/questions", response_model=list[QuestionOut])
def list_questions_for_knowledge_point(
    knowledge_point_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> list:
    """反查关联题目：普通用户仅可见自己的题目，管理员可见全部。"""
    service = QuestionKnowledgePointService(db)
    owner_id = None if current_user.role == "admin" else current_user.id
    try:
        question_ids = service.list_question_ids_for_knowledge_point(
            knowledge_point_id, owner_id
        )
    except QuestionKpNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    if not question_ids:
        return []
    return list(
        db.scalars(
            select(Question)
            .where(Question.id.in_(question_ids))
            .order_by(Question.created_at.desc())
        ).all()
    )


@router.post("", response_model=KnowledgePointRead, status_code=status.HTTP_201_CREATED)
def create_knowledge_point(
    data: KnowledgePointCreate,
    _: Annotated[User, Depends(get_current_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> KnowledgePoint:
    service = _service(db)
    try:
        item = service.create(
            name=data.name,
            subject=data.subject,
            parent_id=data.parent_id,
            description=data.description,
            status=data.status,
            source=data.source,
        )
    except (ValueError, InvalidParent, ParentCycleError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except DuplicateKnowledgePoint as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    db.commit()
    db.refresh(item)
    return item


@router.patch("/{knowledge_point_id}", response_model=KnowledgePointRead)
def update_knowledge_point(
    knowledge_point_id: int,
    data: KnowledgePointUpdate,
    _: Annotated[User, Depends(get_current_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> KnowledgePoint:
    service = _service(db)
    try:
        item = service.update(knowledge_point_id, data)
    except KnowledgePointNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except (ValueError, InvalidParent, ParentCycleError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except DuplicateKnowledgePoint as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    db.commit()
    db.refresh(item)
    return item


@router.delete("/{knowledge_point_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_knowledge_point(
    knowledge_point_id: int,
    _: Annotated[User, Depends(get_current_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> None:
    service = _service(db)
    try:
        service.delete(knowledge_point_id)
    except KnowledgePointNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except KnowledgePointHasChildren as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except KnowledgePointInUse as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    db.commit()


def _raise_not_found() -> KnowledgePoint:
    raise KnowledgePointNotFound("知识点不存在")


# --------------------------------------------------------------------------
# 大阶段 3：知识点前置依赖（prerequisite DAG）
# 与 parent_id（归属层级树）语义不同：本组接口表达「必须先学」，多对多。
# --------------------------------------------------------------------------


def _require_knowledge_point(db: Session, knowledge_point_id: int) -> KnowledgePoint:
    item = _service(db).get(knowledge_point_id)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="知识点不存在")
    return item


def _mastery_scores(db: Session, user_id: int) -> dict[int, int]:
    return {
        row.knowledge_point_id: row.mastery_score
        for row in MasteryService(db).list_for_user(user_id)
    }


def _brief(row: KnowledgePoint) -> KnowledgePointBrief:
    return KnowledgePointBrief.model_validate(row)


@router.get("/{knowledge_point_id}/prerequisites", response_model=PrerequisiteDetailOut)
def list_prerequisites(
    knowledge_point_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> PrerequisiteDetailOut:
    knowledge_point = _require_knowledge_point(db, knowledge_point_id)
    service = PrerequisiteService(db)
    edges = service.list_for(knowledge_point_id)
    mastery = _mastery_scores(db, current_user.id)
    statuses = {
        item.prerequisite_id: item
        for item in service.statuses_for(mastery, knowledge_point_id)
    }
    related = service.knowledge_points_by_ids([edge.prerequisite_id for edge in edges])
    items: list[PrerequisiteRead] = []
    for edge in edges:
        payload = PrerequisiteRead.model_validate(edge)
        related_kp = related.get(edge.prerequisite_id)
        if related_kp is not None:
            payload.prerequisite = _brief(related_kp)
        state = statuses.get(edge.prerequisite_id)
        if state is not None:
            payload.satisfied = state.satisfied
            payload.blocking = state.blocking
        items.append(payload)
    return PrerequisiteDetailOut(
        knowledge_point=_brief(knowledge_point),
        ready=service.is_ready(mastery, knowledge_point_id),
        threshold=READY_THRESHOLD,
        items=items,
    )


@router.post(
    "/{knowledge_point_id}/prerequisites",
    response_model=PrerequisiteRead,
    status_code=status.HTTP_201_CREATED,
)
def add_prerequisite(
    knowledge_point_id: int,
    data: PrerequisiteCreate,
    _: Annotated[User, Depends(get_current_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> PrerequisiteRead:
    service = PrerequisiteService(db)
    try:
        edge = service.add(
            knowledge_point_id=knowledge_point_id,
            prerequisite_id=data.prerequisite_id,
            strength=data.strength,
            source=EDGE_SOURCE_MANUAL,
            note=data.note,
        )
    except PrerequisiteKnowledgePointNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except (SelfLoopPrerequisite, PrerequisiteCycle) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except DuplicatePrerequisite as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    db.commit()
    db.refresh(edge)
    payload = PrerequisiteRead.model_validate(edge)
    related_kp = _service(db).get(edge.prerequisite_id)
    if related_kp is not None:
        payload.prerequisite = _brief(related_kp)
    return payload


@router.delete(
    "/{knowledge_point_id}/prerequisites/{prerequisite_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_prerequisite(
    knowledge_point_id: int,
    prerequisite_id: int,
    _: Annotated[User, Depends(get_current_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> None:
    service = PrerequisiteService(db)
    try:
        service.remove(knowledge_point_id, prerequisite_id)
    except PrerequisiteLinkNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    db.commit()


@router.get("/{knowledge_point_id}/path", response_model=LearningPathOut)
def get_learning_path(
    knowledge_point_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> LearningPathOut:
    target = _require_knowledge_point(db, knowledge_point_id)
    service = PrerequisiteService(db)
    ordered = service.learning_path(knowledge_point_id)
    if not ordered:
        ordered = [target]
    mastery = _mastery_scores(db, current_user.id)
    steps = [
        LearningPathStep(
            order=index,
            knowledge_point=_brief(row),
            mastery_score=mastery.get(row.id),
            satisfied=(mastery.get(row.id, 0) >= READY_THRESHOLD),
            is_target=(row.id == knowledge_point_id),
        )
        for index, row in enumerate(ordered, start=1)
    ]
    return LearningPathOut(
        target=_brief(target),
        ready=service.is_ready(mastery, knowledge_point_id),
        threshold=READY_THRESHOLD,
        steps=steps,
    )


@router.post(
    "/{knowledge_point_id}/prerequisites/suggest",
    response_model=PrerequisiteSuggestOut,
)
def suggest_prerequisite_candidates(
    knowledge_point_id: int,
    _: Annotated[User, Depends(get_current_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> PrerequisiteSuggestOut:
    """让 LLM 提议前置关系。**只提议，不落库**，必须由管理员显式确认。"""
    knowledge_point = _require_knowledge_point(db, knowledge_point_id)
    suggestions, note = suggest_prerequisites(db, knowledge_point_id)
    return PrerequisiteSuggestOut(
        knowledge_point=_brief(knowledge_point),
        suggestions=[PrerequisiteSuggestion(**item) for item in suggestions],
        note=note,
    )
