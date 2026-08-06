from datetime import date, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import PlanItem, StudyPlan, User
from app.schemas.plan import (
    PlanGenerateRequest,
    PlanItemCreate,
    PlanItemOut,
    PlanItemUpdate,
    StudyPlanCreate,
    StudyPlanOut,
)
from app.services.engagement import award_coins, award_pet_exp
from app.services.study_planner import generate_study_plan

router = APIRouter(prefix="/plans", tags=["plans"])


def _get_own_plan(db: Session, user_id: int, plan_id: int) -> StudyPlan:
    plan = db.scalar(
        select(StudyPlan)
        .options(selectinload(StudyPlan.items))
        .where(StudyPlan.id == plan_id, StudyPlan.user_id == user_id)
    )
    if plan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="学习计划不存在")
    return plan


@router.get("", response_model=list[StudyPlanOut])
def list_plans(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> list[StudyPlan]:
    return list(
        db.scalars(
            select(StudyPlan)
            .options(selectinload(StudyPlan.items))
            .where(StudyPlan.user_id == current_user.id)
            .order_by(StudyPlan.created_at.desc())
        ).all()
    )


@router.post("", response_model=StudyPlanOut, status_code=status.HTTP_201_CREATED)
def create_plan(
    data: StudyPlanCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> StudyPlan:
    plan = StudyPlan(user_id=current_user.id, **data.model_dump())
    db.add(plan)
    db.commit()
    return _get_own_plan(db, current_user.id, plan.id)


@router.post("/generate", response_model=StudyPlanOut, status_code=status.HTTP_201_CREATED)
def generate_plan(
    data: PlanGenerateRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> StudyPlan:
    result = generate_study_plan(
        major=data.major,
        grade=data.grade,
        goal=data.goal,
        daily_minutes=data.daily_minutes,
        weeks=data.weeks,
        subjects=data.subjects,
    )
    start = date.today()
    plan = StudyPlan(
        user_id=current_user.id,
        title=result["title"],
        goal=result["goal"],
        start_date=start,
        end_date=start + timedelta(weeks=data.weeks),
        status="active",
    )
    for item in result["items"]:
        plan.items.append(
            PlanItem(
                title=item["title"],
                subject=item["subject"],
                scheduled_date=date.fromisoformat(item["scheduled_date"]),
                duration_minutes=item["duration_minutes"],
                order_index=item["order_index"],
            )
        )
    db.add(plan)
    db.commit()
    return _get_own_plan(db, current_user.id, plan.id)


@router.get("/{plan_id}", response_model=StudyPlanOut)
def get_plan(
    plan_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> StudyPlan:
    return _get_own_plan(db, current_user.id, plan_id)


@router.delete("/{plan_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_plan(
    plan_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> None:
    plan = _get_own_plan(db, current_user.id, plan_id)
    db.delete(plan)
    db.commit()


@router.post("/{plan_id}/items", response_model=PlanItemOut, status_code=status.HTTP_201_CREATED)
def add_plan_item(
    plan_id: int,
    data: PlanItemCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> PlanItem:
    plan = _get_own_plan(db, current_user.id, plan_id)
    order = len(plan.items) + 1
    item = PlanItem(plan_id=plan.id, order_index=order, **data.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.delete("/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_plan_item(
    item_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> None:
    item = db.get(PlanItem, item_id)
    plan = db.get(StudyPlan, item.plan_id) if item else None
    if item is None or plan is None or plan.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="计划任务不存在")
    db.delete(item)
    db.commit()


@router.api_route("/items/{item_id}", response_model=PlanItemOut, methods=["PATCH", "PUT"])
def update_plan_item(
    item_id: int,
    data: PlanItemUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> PlanItem:
    item = db.get(PlanItem, item_id)
    plan = db.get(StudyPlan, item.plan_id) if item else None
    if item is None or plan is None or plan.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="计划任务不存在")
    if data.completed is True and not item.completed:
        award_coins(db, current_user.id, 10, "完成学习任务")
        award_pet_exp(db, current_user.id, 5)
    if data.completed is not None:
        item.completed = data.completed
    db.commit()
    db.refresh(item)
    return item
