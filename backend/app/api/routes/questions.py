import json
from datetime import date, datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete as sa_delete
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_current_user, require_ai_access
from app.core.database import get_db
from app.models import (
    AnswerRecord,
    Document,
    KnowledgeChunk,
    Question,
    QuestionKnowledgePoint,
    User,
    WrongBookItem,
)
from app.schemas.question import (
    AnswerOut,
    AnswerSubmit,
    QuestionFavoriteUpdate,
    QuestionGenerateRequest,
    QuestionKnowledgePointAttachItem,
    QuestionKnowledgePointRead,
    QuestionKnowledgePointReplaceRequest,
    QuestionOut,
    WrongBookItemUpdate,
    WrongBookOut,
)
from app.services.content_filter import validate_text
from app.services.engagement import award_coins, award_pet_exp, record_daily_stat
from app.services.evaluation import build_evaluation, load_knowledge_point_signals
from app.services.mastery import MasteryService
from app.services.question_generator import check_answer, generate_questions
from app.services.question_knowledge_point_service import (
    AssociationNotFound,
    KnowledgePointNotFound,
    NotLearnableNode,
    PrimaryConflict,
    QuestionKnowledgePointError,
    QuestionKnowledgePointService,
    QuestionNotFound,
    SubjectMismatch,
)
from app.services.review import (
    apply_review_outcome,
    reset_for_relearn,
    schedule_first_review,
)

router = APIRouter(prefix="/questions", tags=["questions"])
wrong_book_router = APIRouter(prefix="/wrong-book", tags=["wrong-book"])


def _save_questions(
    db: Session,
    user_id: int,
    document_id: int | None,
    questions: list[dict],
    knowledge_point_id: int | None = None,
) -> list[Question]:
    """落库题目；传入 knowledge_point_id 时在同一事务内建立结构化关联。"""
    saved: list[Question] = []
    for question in questions:
        model = Question(
            user_id=user_id,
            document_id=document_id,
            subject=question["subject"],
            knowledge_point=question["knowledge_point"],
            question_type=question["question_type"],
            stem=question["stem"],
            options_json=json.dumps(question.get("options", []), ensure_ascii=False),
            answer=question["answer"],
            analysis=question["analysis"],
        )
        db.add(model)
        saved.append(model)
    db.flush()
    if knowledge_point_id is not None:
        service = QuestionKnowledgePointService(db)
        for model in saved:
            service.attach(
                model.id,
                knowledge_point_id,
                role="primary",
                source="manual",
                owner_id=user_id,
            )
    db.commit()
    for model in saved:
        db.refresh(model)
    return saved


@router.post("/generate", response_model=list[QuestionOut], status_code=status.HTTP_201_CREATED)
def generate(
    data: QuestionGenerateRequest,
    current_user: Annotated[User, Depends(require_ai_access("basic"))],
    db: Annotated[Session, Depends(get_db)],
) -> list[Question]:
    try:
        validate_text(data.subject, data.knowledge_point)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    context: list[str] = []
    document_id: int | None = data.document_id
    if data.document_id is not None:
        document = db.scalar(
            select(Document).where(
                Document.id == data.document_id, Document.user_id == current_user.id
            )
        )
        if document is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文档不存在")
        if document.status != "parsed":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="文档尚未解析")
        chunks = db.scalars(
            select(KnowledgeChunk)
            .where(KnowledgeChunk.document_id == document.id)
            .limit(8)
        ).all()
        context = [chunk.content for chunk in chunks]

    reference: dict | None = None
    if data.reference_question_id is not None:
        original = db.scalar(
            select(Question).where(
                Question.id == data.reference_question_id,
                Question.user_id == current_user.id,
            )
        )
        if original is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="原题目不存在")
        reference = {
            "subject": original.subject,
            "knowledge_point": original.knowledge_point,
            "question_type": original.question_type,
            "stem": original.stem,
            "options": json.loads(original.options_json or "[]"),
            "answer": original.answer,
            "analysis": original.analysis,
        }

    validate_knowledge_point: int | None = None
    if data.knowledge_point_id is not None:
        try:
            QuestionKnowledgePointService(db).validate_knowledge_point_for_subject(
                data.knowledge_point_id, data.subject
            )
        except KnowledgePointNotFound as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
            ) from exc
        except SubjectMismatch as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
            ) from exc
        except NotLearnableNode as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
            ) from exc
        validate_knowledge_point = data.knowledge_point_id

    try:
        questions = generate_questions(
            data.subject,
            data.knowledge_point,
            data.count,
            data.question_type,
            context=context,
            reference=reference,
        )
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        )
    try:
        return _save_questions(db, current_user.id, document_id, questions,
                               knowledge_point_id=validate_knowledge_point)
    except SubjectMismatch as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    except NotLearnableNode as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc


@router.get("", response_model=list[QuestionOut])
def list_questions(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> list[Question]:
    return list(
        db.scalars(
            select(Question)
            .where(Question.user_id == current_user.id)
            .order_by(Question.created_at.desc())
            .limit(100)
        ).all()
    )


@router.api_route(
    "/{question_id}/favorite",
    response_model=QuestionOut,
    methods=["PATCH", "PUT"],
)
def update_question_favorite(
    question_id: int,
    data: QuestionFavoriteUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> Question:
    question = db.scalar(
        select(Question).where(
            Question.id == question_id,
            Question.user_id == current_user.id,
        )
    )
    if question is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="题目不存在")
    question.is_favorite = data.is_favorite
    db.commit()
    db.refresh(question)
    return question


def _resolve_question(
    db: Session, question_id: int, current_user: User
) -> Question:
    """owner 或管理员可见；越权统一 404，不泄漏题目是否存在。"""
    statement = select(Question).where(Question.id == question_id)
    if current_user.role != "admin":
        statement = statement.where(Question.user_id == current_user.id)
    question = db.scalar(statement)
    if question is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="题目不存在")
    return question


def _association_owner_id(current_user: User) -> int | None:
    """管理员传 None 表示不做 owner 过滤。"""
    return None if current_user.role == "admin" else current_user.id


def _map_association_errors(exc: Exception) -> HTTPException:
    if isinstance(exc, (QuestionNotFound, KnowledgePointNotFound, AssociationNotFound)):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, (SubjectMismatch, PrimaryConflict, QuestionKnowledgePointError)):
        return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="关联操作失败")


@router.get("/{question_id}/knowledge-points", response_model=list[QuestionKnowledgePointRead])
def list_question_knowledge_points(
    question_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> list:
    _resolve_question(db, question_id, current_user)
    service = QuestionKnowledgePointService(db)
    try:
        return service.list_for_question(question_id, _association_owner_id(current_user))
    except QuestionKnowledgePointError as exc:
        raise _map_association_errors(exc) from exc


@router.post("/{question_id}/knowledge-points", response_model=QuestionKnowledgePointRead, status_code=status.HTTP_201_CREATED)
def attach_question_knowledge_point(
    question_id: int,
    data: QuestionKnowledgePointAttachItem,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    _resolve_question(db, question_id, current_user)
    service = QuestionKnowledgePointService(db)
    try:
        item = service.attach(
            question_id,
            data.knowledge_point_id,
            role=data.role,
            source="manual",
            owner_id=_association_owner_id(current_user),
        )
    except QuestionKnowledgePointError as exc:
        raise _map_association_errors(exc) from exc
    db.commit()
    db.refresh(item)
    return item


@router.put("/{question_id}/knowledge-points", response_model=list[QuestionKnowledgePointRead])
def replace_question_knowledge_points(
    question_id: int,
    data: QuestionKnowledgePointReplaceRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> list:
    _resolve_question(db, question_id, current_user)
    service = QuestionKnowledgePointService(db)
    try:
        items = service.replace(
            question_id,
            [(item.knowledge_point_id, item.role) for item in data.items],
            source="manual",
            owner_id=_association_owner_id(current_user),
        )
    except QuestionKnowledgePointError as exc:
        db.rollback()
        raise _map_association_errors(exc) from exc
    db.commit()
    return items


@router.patch("/{question_id}/knowledge-points/{knowledge_point_id}", response_model=QuestionKnowledgePointRead)
def set_primary_question_knowledge_point(
    question_id: int,
    knowledge_point_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    _resolve_question(db, question_id, current_user)
    service = QuestionKnowledgePointService(db)
    try:
        item = service.set_primary(
            question_id,
            knowledge_point_id,
            _association_owner_id(current_user),
        )
    except QuestionKnowledgePointError as exc:
        raise _map_association_errors(exc) from exc
    db.commit()
    db.refresh(item)
    return item


@router.delete("/{question_id}/knowledge-points/{knowledge_point_id}", status_code=status.HTTP_204_NO_CONTENT)
def detach_question_knowledge_point(
    question_id: int,
    knowledge_point_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> None:
    _resolve_question(db, question_id, current_user)
    service = QuestionKnowledgePointService(db)
    try:
        service.detach(question_id, knowledge_point_id, _association_owner_id(current_user))
    except QuestionKnowledgePointError as exc:
        raise _map_association_errors(exc) from exc
    db.commit()


@router.delete("/{question_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_question(
    question_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> None:
    question = db.scalar(
        select(Question).where(
            Question.id == question_id,
            Question.user_id == current_user.id,
        )
    )
    if question is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="题目不存在")
    db.execute(sa_delete(AnswerRecord).where(AnswerRecord.question_id == question.id))
    db.execute(sa_delete(WrongBookItem).where(WrongBookItem.question_id == question.id))
    db.execute(
        sa_delete(QuestionKnowledgePoint).where(
            QuestionKnowledgePoint.question_id == question.id
        )
    )
    db.delete(question)
    db.commit()


def _get_wrong_book_item(
    db: Session, user_id: int, question_id: int
) -> WrongBookItem | None:
    return db.scalar(
        select(WrongBookItem).where(
            WrongBookItem.user_id == user_id,
            WrongBookItem.question_id == question_id,
        )
    )


def _apply_learning_state(
    db: Session,
    *,
    user_id: int,
    question: Question,
    correct: bool,
    spent_seconds: int,
    mistake_reason: str | None,
) -> None:
    """学习状态闭环（同一事务内）：EvaluationResult → Mastery → WrongBook/Review。

    题目没有结构化知识点时 signals 为空，MasteryService 不做任何事，
    legacy 题目行为与旧版完全一致。
    """
    existing = _get_wrong_book_item(db, user_id, question.id)
    reviewed = existing is not None
    signals = load_knowledge_point_signals(db, question.id)
    result = build_evaluation(
        question,
        correct=correct,
        spent_seconds=spent_seconds,
        knowledge_points=signals,
    )
    MasteryService(db).apply_evaluation(user_id, result, reviewed=reviewed)

    today = date.today()
    if correct:
        if existing is not None:
            apply_review_outcome(existing, correct=True, today=today)
        return
    if existing is None:
        created = WrongBookItem(
            user_id=user_id,
            question_id=question.id,
            mistake_reason=mistake_reason,
            review_stage=1,
        )
        db.add(created)
        db.flush()
        schedule_first_review(created, today)
    else:
        apply_review_outcome(existing, correct=False, today=today)


@router.post("/{question_id}/answers", response_model=AnswerOut, status_code=status.HTTP_201_CREATED)
def submit_answer(
    question_id: int,
    data: AnswerSubmit,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> AnswerRecord:
    question = db.get(Question, question_id)
    if question is None or question.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="题目不存在")

    is_correct = check_answer(question, data.user_answer)
    record = AnswerRecord(
        user_id=current_user.id,
        question_id=question.id,
        user_answer=data.user_answer,
        is_correct=is_correct,
        spent_seconds=max(0, int(data.spent_seconds or 0)),
    )
    try:
        db.add(record)
        if is_correct:
            award_coins(db, current_user.id, 5, "答对题目")
        _apply_learning_state(
            db,
            user_id=current_user.id,
            question=question,
            correct=is_correct,
            spent_seconds=record.spent_seconds,
            mistake_reason=data.user_answer,
        )
        award_pet_exp(db, current_user.id, 3)
        record_daily_stat(
            db,
            current_user.id,
            answered=1,
            correct=1 if is_correct else 0,
            coins=5 if is_correct else 0,
        )
        # 单一事务：答案、掌握度、错题/复习状态必须同时成功或同时失败。
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="提交冲突，请重试"
        ) from exc
    except Exception as exc:
        # 任何评估/掌握度/错题写入异常都必须整体回滚，
        # 否则会出现"答案已保存但掌握度没更新"的半完成状态。
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="学习状态更新失败，本次作答未保存，请重试",
        ) from exc
    db.refresh(record)
    return record


@wrong_book_router.get("", response_model=list[WrongBookOut])
def list_wrong_book(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> list[WrongBookItem]:
    return list(
        db.scalars(
            select(WrongBookItem)
            .options(selectinload(WrongBookItem.question))
            .where(WrongBookItem.user_id == current_user.id)
            .order_by(WrongBookItem.updated_at.desc())
        ).all()
    )


@wrong_book_router.get("/review", response_model=list[WrongBookOut])
def list_due_review(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> list[WrongBookItem]:
    return list(
        db.scalars(
            select(WrongBookItem)
            .options(selectinload(WrongBookItem.question))
            .where(
                WrongBookItem.user_id == current_user.id,
                WrongBookItem.mastered.is_(False),
                WrongBookItem.next_review_date <= date.today(),
            )
            .order_by(WrongBookItem.next_review_date.asc())
        ).all()
    )


@wrong_book_router.api_route("/{item_id}", response_model=WrongBookOut, methods=["PATCH", "PUT"])
def update_wrong_book_item(
    item_id: int,
    data: WrongBookItemUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> WrongBookItem:
    """三种语义，互不混淆：

    - mastered=True  → 标记已掌握（不再进入复习队列）
    - mastered=False → 取消掌握，重新回到复习队列第 1 阶段
    - reviewed=True  → 完成一次复习：阶段前进、下次复习时间延后，最高阶段后再答对即掌握
    """
    item = db.scalar(
        select(WrongBookItem)
        .options(selectinload(WrongBookItem.question))
        .where(WrongBookItem.id == item_id, WrongBookItem.user_id == current_user.id)
    )
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="错题记录不存在")
    today = date.today()
    if data.mastered is True:
        item.mastered = True
        item.last_reviewed_at = datetime.now(timezone.utc)
    elif data.mastered is False:
        reset_for_relearn(item, today)
    if data.reviewed:
        if item.mastered:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="该错题已标记为掌握，无需重复复习",
            )
        apply_review_outcome(item, correct=True, today=today)
    db.commit()
    db.refresh(item)
    return item
