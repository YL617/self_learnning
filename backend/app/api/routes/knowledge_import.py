"""大阶段 4 M2：批量知识库导入接口。

6 个接口全部挂 `get_current_admin`，与既有知识点写接口的权限模型一致（无需新
权限模型）。**所有接口都不落盘临时文件**：管理员上传的表格只在请求内解析进内存，
请求结束即释放（因此 `apply` 必须重传数据 —— 这是刻意的设计取舍）。
"""

from typing import Annotated, NoReturn

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Response,
    UploadFile,
    status,
)
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin
from app.core.database import get_db
from app.models import KnowledgePoint, KnowledgePointImportBatch, User
from app.schemas.knowledge_import import (
    ConflictStrategy,
    ImportApplyOut,
    ImportBatchDetailOut,
    ImportBatchOut,
    ImportPreviewOut,
    ImportRejection,
    RollbackOut,
    RowIssue,
)
from app.schemas.mastery import KnowledgePointBrief
from app.services.knowledge_import import (
    MAX_IMPORT_BYTES,
    PREVIEW_ROW_LIMIT,
    STRATEGY_SKIP,
    ImportBatchNotFound,
    ImportConflictError,
    ImportCycleError,
    ImportWriteError,
    KnowledgeImportError,
    ParsedTable,
    collect_blockers,
    parse_pasted,
    parse_uploaded,
    plan_import,
    preview_rows,
    rollback_batch,
    template_csv,
)
from app.services.knowledge_import import (
    apply_import as run_apply_import,
)

router = APIRouter(prefix="/knowledge-import", tags=["knowledge-import"])

BATCH_DETAIL_LIMIT = 200
MEGABYTE = 1024 * 1024

# Starlette 新版把 413 常量改名为 CONTENT_TOO_LARGE，旧版仍叫
# REQUEST_ENTITY_TOO_LARGE。取存在的那个，避免为一行常量升高依赖下限。
HTTP_413 = getattr(
    status, "HTTP_413_CONTENT_TOO_LARGE", None
) or status.HTTP_413_REQUEST_ENTITY_TOO_LARGE


# --------------------------------------------------------------------------
# 公共工具
# --------------------------------------------------------------------------


def _rejection(exc: KnowledgeImportError) -> dict:
    """把管线异常转成结构化 detail，让前端能直接渲染「哪一行错在哪」。"""
    issues = list(exc.issues) or [
        RowIssue(level="error", code=exc.code, message=exc.message)
    ]
    return ImportRejection(
        message=exc.message,
        code=exc.code,
        batch_errors=[item for item in issues if item.row is None],
        row_issues=[item for item in issues if item.row is not None],
        cycle=exc.cycle,
    ).model_dump()


def _raise_for(exc: KnowledgeImportError) -> NoReturn:
    if isinstance(exc, ImportBatchNotFound):
        code = status.HTTP_404_NOT_FOUND
    elif isinstance(exc, (ImportCycleError, ImportConflictError, ImportWriteError)):
        code = status.HTTP_409_CONFLICT
    else:
        code = status.HTTP_400_BAD_REQUEST
    raise HTTPException(status_code=code, detail=_rejection(exc)) from exc


async def _load_table(*, file: UploadFile | None, content: str | None) -> ParsedTable:
    """两条入口（上传 / 粘贴），同一条解析管线。"""
    has_content = content is not None and content.strip() != ""
    if file is not None and has_content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="请只提供一种输入：上传文件（file）或粘贴内容（content）",
        )
    if file is not None:
        raw = await file.read()
        if len(raw) > MAX_IMPORT_BYTES:
            raise HTTPException(
                status_code=HTTP_413,
                detail=f"文件超过 {MAX_IMPORT_BYTES // MEGABYTE} MiB 上限，请拆分后重试",
            )
        return parse_uploaded(raw, file.filename)
    if has_content and content is not None:
        if len(content.encode("utf-8")) > MAX_IMPORT_BYTES:
            raise HTTPException(
                status_code=HTTP_413,
                detail=f"粘贴内容超过 {MAX_IMPORT_BYTES // MEGABYTE} MiB 上限，请拆分后重试",
            )
        return parse_pasted(content)
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="请提供上传文件（file）或粘贴内容（content）",
    )


def _preview_payload(plan, strategy: str) -> ImportPreviewOut:
    return ImportPreviewOut(
        source_format=plan.table.source_format,
        detected_encoding=plan.table.detected_encoding,
        detected_delimiter=plan.table.detected_delimiter,
        has_header=plan.table.has_header,
        total_rows=plan.total_rows,
        error_rows=plan.error_rows,
        warning_rows=plan.warning_rows,
        parse_notes=list(plan.table.notes),
        planned=plan.counts,
        new_subjects=plan.new_subjects,
        parent_paths_to_create=[item.display_path for item in plan.auto_parents],
        rows=preview_rows(plan),
        truncated=plan.total_rows > PREVIEW_ROW_LIMIT,
        conflict_strategy=strategy,  # type: ignore[arg-type]
        can_apply=plan.error_rows == 0 and not plan.cycle,
    )


# --------------------------------------------------------------------------
# 1 / 2. 预览与执行
# --------------------------------------------------------------------------


@router.post("/preview", response_model=ImportPreviewOut)
async def preview_import(
    _: Annotated[User, Depends(get_current_admin)],
    db: Annotated[Session, Depends(get_db)],
    file: Annotated[UploadFile | None, File()] = None,
    content: Annotated[str | None, Form()] = None,
    conflict_strategy: Annotated[ConflictStrategy, Form()] = STRATEGY_SKIP,  # type: ignore[assignment]
    source_name: Annotated[str | None, Form()] = None,
) -> ImportPreviewOut:
    """解析 + 校验 + 计划（dry-run）。**不写任何表、不建批次行、不落盘。**

    `source_name` 只在 apply 时写入审计，此处仅为两个接口入参一致而保留。
    """
    del source_name
    try:
        table = await _load_table(file=file, content=content)
        plan = plan_import(db, table, conflict_strategy)
    except KnowledgeImportError as exc:
        _raise_for(exc)
    return _preview_payload(plan, conflict_strategy)


@router.post("/apply", response_model=ImportApplyOut)
async def apply_import(
    user: Annotated[User, Depends(get_current_admin)],
    db: Annotated[Session, Depends(get_db)],
    file: Annotated[UploadFile | None, File()] = None,
    content: Annotated[str | None, Form()] = None,
    conflict_strategy: Annotated[ConflictStrategy, Form()] = STRATEGY_SKIP,  # type: ignore[assignment]
    source_name: Annotated[str | None, Form()] = None,
    expected_total_rows: Annotated[int | None, Form()] = None,
) -> ImportApplyOut:
    """重新解析并完整校验后，单事务写入（全有或全无）。"""
    try:
        table = await _load_table(file=file, content=content)
        report = run_apply_import(
            db,
            user_id=user.id,
            table=table,
            strategy=conflict_strategy,
            source_name=source_name or f"粘贴导入 / {user.username}",
            expected_total_rows=expected_total_rows,
        )
    except KnowledgeImportError as exc:
        _raise_for(exc)
    return ImportApplyOut(
        batch_id=report.batch_id,
        status="applied",
        source_format=table.source_format,
        conflict_strategy=conflict_strategy,
        total_rows=report.total_rows,
        created_count=report.created_count,
        updated_count=report.updated_count,
        skipped_count=report.skipped_count,
        failed_count=0,
        auto_parent_count=report.auto_parent_count,
        duration_ms=report.duration_ms,
        rows=report.rows,
    )


# --------------------------------------------------------------------------
# 3 / 4 / 5. 批次列表、明细与回滚
# --------------------------------------------------------------------------


@router.get("/batches", response_model=list[ImportBatchOut])
def list_batches(
    _: Annotated[User, Depends(get_current_admin)],
    db: Annotated[Session, Depends(get_db)],
    batch_status: Annotated[str | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[KnowledgePointImportBatch]:
    statement = select(KnowledgePointImportBatch)
    if batch_status is not None:
        statement = statement.where(KnowledgePointImportBatch.status == batch_status)
    statement = (
        statement.order_by(KnowledgePointImportBatch.id.desc()).limit(limit).offset(offset)
    )
    return list(db.scalars(statement).all())


@router.get("/batches/{batch_id}", response_model=ImportBatchDetailOut)
def get_batch(
    batch_id: int,
    _: Annotated[User, Depends(get_current_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> ImportBatchDetailOut:
    batch = db.get(KnowledgePointImportBatch, batch_id)
    if batch is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="批次不存在")
    items = list(
        db.scalars(
            select(KnowledgePoint)
            .where(KnowledgePoint.import_batch_id == batch_id)
            .order_by(KnowledgePoint.id)
        ).all()
    )
    payload = ImportBatchDetailOut.model_validate(batch)
    payload.knowledge_points = [
        KnowledgePointBrief.model_validate(item) for item in items[:BATCH_DETAIL_LIMIT]
    ]
    payload.blocking_references = collect_blockers(db, items)
    notes: list[str] = []
    if batch.updated_count:
        notes.append(
            f"本批通过 update_empty 补充了 {batch.updated_count} 条既有知识点的空字段；"
            "批次表没有字段级快照，因此这部分明细无法逐条枚举，回滚也不会清空补充内容。"
        )
    if len(items) > BATCH_DETAIL_LIMIT:
        notes.append(f"本批知识点共 {len(items)} 条，此处仅列出前 {BATCH_DETAIL_LIMIT} 条。")
    payload.notes = notes
    return payload


@router.post("/batches/{batch_id}/rollback", response_model=RollbackOut)
def rollback_import_batch(
    batch_id: int,
    _: Annotated[User, Depends(get_current_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> RollbackOut:
    try:
        result = rollback_batch(db, batch_id)
    except KnowledgeImportError as exc:
        _raise_for(exc)
    return RollbackOut(
        batch_id=result.batch_id,
        deleted_count=result.deleted_count,
        kept_updated_count=result.kept_updated_count,
        status="rolled_back",
        rolled_back_at=result.rolled_back_at,
    )


# --------------------------------------------------------------------------
# 6. 模板下载
# --------------------------------------------------------------------------


@router.get("/template")
def download_template(_: Annotated[User, Depends(get_current_admin)]) -> Response:
    """零依赖生成 CSV 模板；正文带 UTF-8 BOM，否则 Windows Excel 双击会中文乱码。"""
    return Response(
        content="\ufeff" + template_csv(),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": 'attachment; filename="knowledge_points_template.csv"'
        },
    )
