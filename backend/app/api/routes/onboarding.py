import json
from datetime import date, datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import PlanItem, StudyPlan, User, UserProfile
from app.schemas.onboarding import OnboardingIn, OnboardingOut
from app.services.study_planner import generate_study_plan

router = APIRouter(prefix="/onboarding", tags=["onboarding"])


@router.post("", response_model=OnboardingOut)
def submit_onboarding(
    data: OnboardingIn,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> OnboardingOut:
    profile = current_user.profile
    if profile is None:
        profile = UserProfile(user_id=current_user.id, daily_study_minutes=60)
        db.add(profile)
        db.flush()

    if data.major is not None:
        profile.major = data.major
    if data.grade is not None:
        profile.grade = data.grade
    if data.goals:
        profile.goals = "、".join(data.goals)
    if data.weekly_minutes is not None:
        profile.weekly_study_minutes = data.weekly_minutes
    if data.learning_style:
        profile.learning_style = json.dumps(data.learning_style, ensure_ascii=False)
    if data.pain_point:
        profile.pain_point = json.dumps(data.pain_point, ensure_ascii=False)
    if data.school_level is not None:
        profile.school_level = data.school_level
    if data.available_time_slots:
        profile.available_time_slots = json.dumps(data.available_time_slots, ensure_ascii=False)

    if data.complete:
        profile.onboarding_completed = True
        profile.onboarding_completed_at = datetime.now(timezone.utc)

    plan: StudyPlan | None = None
    if data.generate_plan:
        weekly = data.weekly_minutes or profile.weekly_study_minutes or 420
        daily = max(30, round(weekly / 7 * 0.8))
        goals = "、".join(data.goals) or profile.goals or "巩固基础"
        result = generate_study_plan(
            major=data.major or profile.major or "综合",
            grade=data.grade or profile.grade or "其他",
            goal=goals,
            daily_minutes=daily,
            weeks=1,
            subjects=[data.major] if data.major else [],
        )
        start = date.today()
        plan = StudyPlan(
            user_id=current_user.id,
            title=result["title"],
            goal=result["goal"],
            start_date=start,
            end_date=start + timedelta(weeks=1),
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

    user = db.scalar(
        select(User).options(selectinload(User.profile)).where(User.id == current_user.id)
    )
    plan_out = None
    if plan is not None:
        plan_out = db.scalar(
            select(StudyPlan)
            .options(selectinload(StudyPlan.items))
            .where(StudyPlan.id == plan.id)
        )
    return OnboardingOut(profile=user.profile, plan=plan_out)
