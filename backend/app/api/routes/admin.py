from datetime import date
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import delete as sa_delete
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_current_admin
from app.core.config import get_settings
from app.core.database import get_db
from app.models import (
    AnswerRecord,
    CoinTransaction,
    Course,
    CourseChapter,
    DailyStat,
    Document,
    FileAnalyzeResult,
    KnowledgeChunk,
    Question,
    StudyPlan,
    User,
    WrongBookItem,
)
from app.schemas.admin import (
    AdminQuestionOut,
    AdminUserOut,
    AdminUserUpdate,
    AiMonitorOut,
    CourseCreate,
    CourseUpdate,
    StatsOverviewOut,
)
from app.schemas.file import DocumentOut
from app.schemas.ops import CourseOut
from app.services.ai_monitor import (
    can_refresh,
    get_monitor_state,
    refresh_deepseek_monitor,
)

router = APIRouter(prefix="/admin", tags=["admin"])
settings = get_settings()


@router.get("/users", response_model=list[AdminUserOut])
def list_admin_users(
    _: Annotated[User, Depends(get_current_admin)],
    db: Annotated[Session, Depends(get_db)],
    q: str | None = None,
    membership_level: str | None = None,
    role: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
) -> list[User]:
    stmt = select(User).order_by(User.created_at.desc()).limit(limit)
    if q:
        keyword = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                User.email.ilike(keyword),
                User.username.ilike(keyword),
                User.nickname.ilike(keyword),
            )
        )
    if membership_level:
        stmt = stmt.where(User.membership_level == membership_level)
    if role:
        stmt = stmt.where(User.role == role)
    return list(db.scalars(stmt).all())


@router.patch("/users/{user_id}", response_model=AdminUserOut)
def update_admin_user(
    user_id: int,
    data: AdminUserUpdate,
    current_admin: Annotated[User, Depends(get_current_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
    if user.id == current_admin.id:
        if data.is_active is False:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="不能禁用自己")
        if data.role is not None and data.role != "admin":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="不能取消自己的管理员角色")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(user, field, value)
    db.commit()
    db.refresh(user)
    return user


@router.get("/ai-monitor", response_model=AiMonitorOut)
def admin_ai_monitor(
    _: Annotated[User, Depends(get_current_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> AiMonitorOut:
    return AiMonitorOut(**get_monitor_state(db))


@router.post("/ai-monitor/refresh", response_model=AiMonitorOut)
def admin_ai_monitor_refresh(
    _: Annotated[User, Depends(get_current_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> AiMonitorOut:
    if not can_refresh(db):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="刷新过于频繁，请稍后再试",
        )
    refresh_deepseek_monitor(db)
    return AiMonitorOut(**get_monitor_state(db))


@router.get("/stats/overview", response_model=StatsOverviewOut)
def admin_stats_overview(
    _: Annotated[User, Depends(get_current_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> StatsOverviewOut:
    today = date.today()
    active_today = db.scalar(
        select(func.count(func.distinct(DailyStat.user_id))).where(
            DailyStat.stat_date == today
        )
    )
    total_coins = db.scalar(
        select(func.coalesce(func.sum(CoinTransaction.amount), 0)).where(
            CoinTransaction.amount > 0
        )
    )
    return StatsOverviewOut(
        user_count=db.scalar(select(func.count(User.id))) or 0,
        active_today=active_today or 0,
        plan_count=db.scalar(select(func.count(StudyPlan.id))) or 0,
        question_count=db.scalar(select(func.count(Question.id))) or 0,
        wrong_book_count=db.scalar(select(func.count(WrongBookItem.id))) or 0,
        document_count=db.scalar(select(func.count(Document.id))) or 0,
        course_count=db.scalar(select(func.count(Course.id))) or 0,
        total_focus_minutes=db.scalar(
            select(func.coalesce(func.sum(DailyStat.focus_minutes), 0))
        )
        or 0,
        total_coins_issued=int(total_coins or 0),
        ai_monitor=AiMonitorOut(**get_monitor_state(db)),
    )


@router.get("/questions", response_model=list[AdminQuestionOut])
def list_admin_questions(
    _: Annotated[User, Depends(get_current_admin)],
    db: Annotated[Session, Depends(get_db)],
    limit: int = Query(default=100, ge=1, le=500),
) -> list[Question]:
    return list(
        db.scalars(select(Question).order_by(Question.created_at.desc()).limit(limit)).all()
    )


@router.delete("/questions/{question_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_admin_question(
    question_id: int,
    _: Annotated[User, Depends(get_current_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> None:
    question = db.get(Question, question_id)
    if question is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="题目不存在")
    db.execute(
        sa_delete(AnswerRecord).where(AnswerRecord.question_id == question_id)
    )
    db.execute(
        sa_delete(WrongBookItem).where(WrongBookItem.question_id == question_id)
    )
    db.delete(question)
    db.commit()


@router.get("/documents", response_model=list[DocumentOut])
def list_admin_documents(
    _: Annotated[User, Depends(get_current_admin)],
    db: Annotated[Session, Depends(get_db)],
    limit: int = Query(default=100, ge=1, le=500),
) -> list[Document]:
    return list(
        db.scalars(select(Document).order_by(Document.created_at.desc()).limit(limit)).all()
    )


@router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_admin_document(
    document_id: int,
    _: Annotated[User, Depends(get_current_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> None:
    document = db.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文档不存在")
    db.execute(
        sa_delete(KnowledgeChunk).where(KnowledgeChunk.document_id == document_id)
    )
    db.execute(
        sa_delete(FileAnalyzeResult).where(
            FileAnalyzeResult.document_id == document_id
        )
    )
    db.delete(document)
    db.commit()
    path = Path(document.storage_path)
    if path.exists():
        path.unlink()


@router.get("/courses", response_model=list[CourseOut])
def list_admin_courses(
    _: Annotated[User, Depends(get_current_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> list[Course]:
    return list(
        db.scalars(
            select(Course)
            .options(selectinload(Course.chapters))
            .order_by(Course.id.desc())
        ).all()
    )


@router.post("/courses", response_model=CourseOut, status_code=status.HTTP_201_CREATED)
def create_admin_course(
    data: CourseCreate,
    _: Annotated[User, Depends(get_current_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> Course:
    course = Course(
        title=data.title,
        platform=data.platform,
        url=data.url,
        description=data.description,
    )
    for chapter in data.chapters:
        course.chapters.append(
            CourseChapter(title=chapter.title, order_index=chapter.order_index)
        )
    db.add(course)
    db.commit()
    db.refresh(course)
    return db.scalar(
        select(Course)
        .options(selectinload(Course.chapters))
        .where(Course.id == course.id)
    )


@router.patch("/courses/{course_id}", response_model=CourseOut)
def update_admin_course(
    course_id: int,
    data: CourseUpdate,
    _: Annotated[User, Depends(get_current_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> Course:
    course = db.scalar(
        select(Course)
        .options(selectinload(Course.chapters))
        .where(Course.id == course_id)
    )
    if course is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="课程不存在")
    for field in ("title", "platform", "url", "description"):
        value = getattr(data, field)
        if value is not None:
            setattr(course, field, value)
    if data.chapters is not None:
        course.chapters.clear()
        for index, chapter in enumerate(data.chapters, start=1):
            course.chapters.append(
                CourseChapter(
                    title=chapter.title,
                    order_index=chapter.order_index or index,
                )
            )
    db.commit()
    return db.scalar(
        select(Course)
        .options(selectinload(Course.chapters))
        .where(Course.id == course_id)
    )


@router.delete("/courses/{course_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_admin_course(
    course_id: int,
    _: Annotated[User, Depends(get_current_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> None:
    course = db.get(Course, course_id)
    if course is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="课程不存在")
    db.delete(course)
    db.commit()
