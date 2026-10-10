import json
import secrets
from datetime import date, datetime, timedelta, timezone
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
    ActivationCode,
    AnswerRecord,
    CoinTransaction,
    Course,
    CourseChapter,
    DailyStat,
    Document,
    FileAnalyzeResult,
    KnowledgeChunk,
    KnowledgePoint,
    Question,
    QuestionKnowledgePoint,
    StudyPlan,
    User,
    WrongBookItem,
)
from app.schemas.admin import (
    AdminQuestionCreate,
    AdminQuestionDetailOut,
    AdminQuestionKnowledgePointAttach,
    AdminQuestionOut,
    AdminUserOut,
    AdminUserUpdate,
    AiMonitorOut,
    CourseCreate,
    CourseUpdate,
    KnowledgeCoverageItem,
    KnowledgeCoverageOut,
    StatsOverviewOut,
)
from app.schemas.billing import ActivationCodeCreate, ActivationCodeOut
from app.schemas.file import DocumentOut
from app.schemas.ops import CourseOut
from app.schemas.question import QuestionKnowledgePointRead
from app.services.ai_monitor import (
    can_refresh,
    get_monitor_state,
    refresh_deepseek_monitor,
)
from app.services.course_recommender import check_catalog_health
from app.services.knowledge_point_service import KP_NODE_TYPE_CONCEPT
from app.services.question_knowledge_point_service import (
    AssociationNotFound,
    KnowledgePointNotFound,
    QuestionKnowledgePointError,
    QuestionKnowledgePointService,
    QuestionNotFound,
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
        if (
            field == "membership_level"
            and value != "free"
            and user.membership_expires_at is None
        ):
            user.membership_expires_at = (
                datetime.now(timezone.utc) + timedelta(days=30)
            ).replace(tzinfo=None)
        if field == "membership_level" and value == "free":
            user.membership_expires_at = None
        setattr(user, field, value)
    db.commit()
    db.refresh(user)
    return user


@router.get("/activation-codes", response_model=list[ActivationCodeOut])
def list_activation_codes(
    _: Annotated[User, Depends(get_current_admin)],
    db: Annotated[Session, Depends(get_db)],
    limit: int = Query(default=200, ge=1, le=1000),
) -> list[ActivationCode]:
    return list(
        db.scalars(
            select(ActivationCode)
            .order_by(ActivationCode.created_at.desc())
            .limit(limit)
        ).all()
    )


@router.post(
    "/activation-codes",
    response_model=list[ActivationCodeOut],
    status_code=status.HTTP_201_CREATED,
)
def create_activation_codes(
    data: ActivationCodeCreate,
    current_admin: Annotated[User, Depends(get_current_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> list[ActivationCode]:
    codes: list[ActivationCode] = []
    for _ in range(data.count):
        code_value = secrets.token_hex(8).upper()
        while db.scalar(
            select(ActivationCode).where(ActivationCode.code == code_value)
        ) is not None:
            code_value = secrets.token_hex(8).upper()
        code = ActivationCode(
            code=code_value,
            tier=data.tier,
            days=data.days,
            status="unused",
            created_by=current_admin.id,
        )
        db.add(code)
        codes.append(code)
    db.commit()
    for code in codes:
        db.refresh(code)
    return codes


@router.post("/activation-codes/{code_id}/revoke", response_model=ActivationCodeOut)
def revoke_activation_code(
    code_id: int,
    _: Annotated[User, Depends(get_current_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> ActivationCode:
    code = db.get(ActivationCode, code_id)
    if code is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="激活码不存在")
    if code.status == "used":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="已使用的激活码不能撤销",
        )
    code.status = "revoked"
    db.commit()
    db.refresh(code)
    return code


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


@router.post("/questions", response_model=AdminQuestionOut, status_code=status.HTTP_201_CREATED)
def create_admin_question(
    data: AdminQuestionCreate,
    current_admin: Annotated[User, Depends(get_current_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> Question:
    """M4：管理员创建题目（默认共享题库）。

    可选携带 knowledge_point_ids 一并绑定（仅 concept，由
    QuestionKnowledgePointService 关口保证）；第一个作为 primary，
    其余为 secondary。创建 + 绑定在同一事务内，任一失败整体回滚。
    """
    question = Question(
        user_id=current_admin.id,
        subject=data.subject,
        knowledge_point=data.knowledge_point,
        question_type=data.question_type,
        stem=data.stem,
        options_json=json.dumps(data.options, ensure_ascii=False) if data.options else None,
        answer=data.answer,
        analysis=data.analysis,
        source="admin",
        difficulty=data.difficulty,
        visibility=data.visibility,
    )
    db.add(question)
    db.flush()
    try:
        if data.knowledge_point_ids:
            service = QuestionKnowledgePointService(db)
            for index, knowledge_point_id in enumerate(data.knowledge_point_ids):
                service.attach(
                    question.id,
                    knowledge_point_id,
                    role="primary" if index == 0 else "secondary",
                    source="manual",
                    owner_id=None,
                )
    except QuestionKnowledgePointError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    db.commit()
    db.refresh(question)
    return question


@router.get("/questions/{question_id}", response_model=AdminQuestionDetailOut)
def get_admin_question(
    question_id: int,
    _: Annotated[User, Depends(get_current_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> AdminQuestionDetailOut:
    """M4：题目详情（全字段 + 结构化知识点关联）。"""
    question = db.get(Question, question_id)
    if question is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="题目不存在")
    payload = AdminQuestionDetailOut.model_validate(question)
    payload.knowledge_points = [
        QuestionKnowledgePointRead.model_validate(row)
        for row in QuestionKnowledgePointService(db).list_for_question(
            question_id, owner_id=None
        )
    ]
    return payload


@router.post(
    "/questions/{question_id}/knowledge-points",
    response_model=QuestionKnowledgePointRead,
    status_code=status.HTTP_201_CREATED,
)
def attach_admin_question_knowledge_point(
    question_id: int,
    data: AdminQuestionKnowledgePointAttach,
    _: Annotated[User, Depends(get_current_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> QuestionKnowledgePoint:
    """M4：管理员给题目绑定知识点（与用户端同一服务关口：container 一律拒绝）。"""
    service = QuestionKnowledgePointService(db)
    try:
        item = service.attach(
            question_id,
            data.knowledge_point_id,
            role=data.role,
            source="manual",
            owner_id=None,
        )
    except QuestionKnowledgePointError as exc:
        db.rollback()
        raise HTTPException(
            status_code=(
                status.HTTP_404_NOT_FOUND
                if isinstance(exc, (QuestionNotFound, KnowledgePointNotFound, AssociationNotFound))
                else status.HTTP_400_BAD_REQUEST
            ),
            detail=str(exc),
        ) from exc
    db.commit()
    db.refresh(item)
    return item


@router.get("/knowledge-coverage", response_model=KnowledgeCoverageOut)
def admin_knowledge_coverage(
    _: Annotated[User, Depends(get_current_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> KnowledgeCoverageOut:
    """M4：知识覆盖情况。只统计 concept（container 永不计入）；
    covered = 至少有一道题（任意可见性）通过 qkp 关联的 concept 数。
    """
    concept_rows = db.execute(
        select(KnowledgePoint.subject, KnowledgePoint.id).where(
            KnowledgePoint.node_type == KP_NODE_TYPE_CONCEPT
        )
    ).all()
    covered_ids = set(
        db.scalars(select(QuestionKnowledgePoint.knowledge_point_id).distinct())
    )
    question_counts: dict[str, int] = dict(
        db.execute(
            select(Question.subject, func.count(Question.id)).group_by(Question.subject)
        ).all()
    )

    by_subject: dict[str, dict[str, int]] = {}
    for subject, kp_id in concept_rows:
        bucket = by_subject.setdefault(
            subject, {"concept_total": 0, "covered": 0, "question_total": 0}
        )
        bucket["concept_total"] += 1
        if kp_id in covered_ids:
            bucket["covered"] += 1
    for subject, count in question_counts.items():
        bucket = by_subject.setdefault(
            subject, {"concept_total": 0, "covered": 0, "question_total": 0}
        )
        bucket["question_total"] = count

    items = [
        KnowledgeCoverageItem(
            subject=subject,
            concept_total=bucket["concept_total"],
            covered=bucket["covered"],
            uncovered=bucket["concept_total"] - bucket["covered"],
            question_total=bucket["question_total"],
        )
        for subject, bucket in sorted(by_subject.items())
    ]
    return KnowledgeCoverageOut(
        concept_total=sum(item.concept_total for item in items),
        covered=sum(item.covered for item in items),
        uncovered=sum(item.uncovered for item in items),
        question_total=sum(item.question_total for item in items),
        items=items,
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


@router.post("/courses/check-health")
def check_admin_course_health(
    _: Annotated[User, Depends(get_current_admin)],
    db: Annotated[Session, Depends(get_db)],
    max_workers: int = Query(default=6, ge=1, le=12),
) -> dict:
    return check_catalog_health(db, max_workers=max_workers)
