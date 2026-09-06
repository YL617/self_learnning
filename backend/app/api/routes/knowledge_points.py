from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin, get_current_user
from app.core.database import get_db
from app.models import KnowledgePoint, User
from app.schemas.knowledge import (
    KnowledgePointCreate,
    KnowledgePointRead,
    KnowledgePointUpdate,
)
from app.services.knowledge_point_service import (
    DuplicateKnowledgePoint,
    InvalidParent,
    KnowledgePointHasChildren,
    KnowledgePointNotFound,
    KnowledgePointService,
    ParentCycleError,
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
    db.commit()


def _raise_not_found() -> KnowledgePoint:
    raise KnowledgePointNotFound("知识点不存在")
