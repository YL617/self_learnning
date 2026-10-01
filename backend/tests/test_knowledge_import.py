"""大阶段 4 M2：批量知识库导入的契约与行为验证。

覆盖范围（对应 M2 验收项）：
  - 解析：TSV / CSV（逗号、分号、引号内换行）/ BOM / GBK / 无表头 / 空行剔除；
  - xlsx：基本读取、多 sheet、旧版 .xls、损坏文件、数值单元格；
  - 行级 error E01–E11 与整批级 error B01–B04（含 **成环**）；
  - warning W01–W06 且 **不阻断** apply；
  - 幂等：`skip` 不动既有行 / `update_empty` 只补空 / 重复导入计数演进；
  - 父节点自动创建（单层、多层、复用、跨行共享、跨学科 E08）；
  - 写入事务：注入失败 → 全批零写入 + 批次 `status='failed'` 确实落库；
  - 上限：501 行 → 400 / 超 2 MiB → 413；
  - 回滚：纯新建、外部子节点、题目关联、掌握度、前置边、同批父子；
  - 权限：6 个接口的 401 / 403；
  - ⭐ **只读性**：`preview` 前后所有关键表计数不变；
  - ⭐ **红线回归**：导入带 `difficulty` 的知识点后，掌握度差分测试仍成立。

本阶段**零 DB 变更**：不新增/修改任何 migration、表、列、约束。
"""

import io
import uuid

import pytest
from sqlalchemy import delete, func, select

from app.core.database import SessionLocal
from app.models import (
    AnswerRecord,
    KnowledgePoint,
    KnowledgePointImportBatch,
    KnowledgePointPrerequisite,
    Question,
    QuestionKnowledgePoint,
    User,
    UserKnowledgePointMastery,
    WrongBookItem,
)
from app.services.knowledge_point_service import KnowledgePointService

API = "/api/v1"
IMPORT = f"{API}/knowledge-import"

AI_SUBJECT = "Mock Subject"
CORRECT_ANSWER = "A"

HEADER = "学科,知识点名"
HEADER_FULL = "学科,层级路径,知识点名,别名,难度,预计学时,编码"


# ------------------------------------------------------------------ 环境


def _wipe() -> None:
    """清理本模块会写入的表；顺序必须满足 FK 依赖（先删引用方）。"""
    with SessionLocal() as db:
        db.execute(delete(AnswerRecord))
        db.execute(delete(WrongBookItem))
        db.execute(delete(UserKnowledgePointMastery))
        db.execute(delete(QuestionKnowledgePoint))
        db.execute(delete(KnowledgePointPrerequisite))
        db.execute(delete(Question))
        db.execute(delete(KnowledgePoint))
        db.execute(delete(KnowledgePointImportBatch))
        db.commit()


@pytest.fixture(autouse=True)
def _clean_import_tables():
    _wipe()
    yield
    _wipe()


# ------------------------------------------------------------------ 辅助


def _register(client, role: str = "user") -> tuple[dict, dict]:
    suffix = uuid.uuid4().hex[:10]
    response = client.post(
        f"{API}/auth/register",
        json={
            "email": f"m2_{suffix}@example.com",
            "username": f"m2_{suffix}",
            "password": "123456",
        },
    )
    assert response.status_code == 201, response.text
    auth = response.json()
    if role != "user":
        with SessionLocal() as db:
            db.get(User, auth["user"]["id"]).role = role
            db.commit()
    return auth, {"Authorization": f"Bearer {auth['access_token']}"}


def _post(client, path: str, headers, *, content=None, file=None, strategy=None, extra=None):
    data: dict = dict(extra or {})
    if content is not None:
        data["content"] = content
    if strategy is not None:
        data["conflict_strategy"] = strategy
    files = {"file": file} if file is not None else None
    return client.post(f"{IMPORT}/{path}", headers=headers, data=data, files=files)


def _preview(client, headers, content, *, strategy="skip"):
    response = _post(client, "preview", headers, content=content, strategy=strategy)
    assert response.status_code == 200, response.text
    return response.json()


def _apply(client, headers, content, *, strategy="skip", expected=None, file=None):
    extra = {"expected_total_rows": expected} if expected is not None else None
    return _post(
        client, "apply", headers, content=content, strategy=strategy, extra=extra, file=file
    )


def _apply_ok(client, headers, content, *, strategy="skip", expected=None):
    response = _apply(client, headers, content, strategy=strategy, expected=expected)
    assert response.status_code == 200, response.text
    return response.json()


def _codes(payload: dict, *, row: int | None = None) -> list[str]:
    """从 preview 结果里收集错误/警告码。"""
    found: list[str] = []
    for item in payload["rows"]:
        for issue in item["issues"]:
            if row is None or issue["row"] == row:
                found.append(issue["code"])
    return found


def _issue(payload: dict, code: str) -> dict:
    for item in payload["rows"]:
        for issue in item["issues"]:
            if issue["code"] == code:
                return issue
    raise AssertionError(f"未找到 {code}：{payload}")


def _row_codes(payload: dict, index: int) -> list[str]:
    return [issue["code"] for issue in payload["rows"][index]["issues"]]


def _rejection_code(response) -> str:
    detail = response.json()["detail"]
    assert isinstance(detail, dict), detail
    return detail["code"]


def _create_kp(client, headers, **payload) -> dict:
    body = {"name": "栈", "subject": AI_SUBJECT, **payload}
    response = client.post(f"{API}/knowledge-points", headers=headers, json=body)
    assert response.status_code == 201, response.text
    return response.json()


def _kp_count_by_name(client, headers, name: str, subject: str = "数据结构") -> int:
    response = client.get(
        f"{API}/knowledge-points", headers=headers, params={"subject": subject}
    )
    assert response.status_code == 200, response.text
    return sum(1 for item in response.json() if item["name"] == name)


def _kp_by_name(client, headers, name: str, subject: str = "数据结构") -> dict | None:
    response = client.get(
        f"{API}/knowledge-points", headers=headers, params={"subject": subject}
    )
    assert response.status_code == 200, response.text
    for item in response.json():
        if item["name"] == name:
            return item
    return None


def _counts() -> dict[str, int]:
    with SessionLocal() as db:
        return {
            "knowledge_points": db.scalar(
                select(func.count()).select_from(KnowledgePoint)
            ),
            "batches": db.scalar(
                select(func.count()).select_from(KnowledgePointImportBatch)
            ),
            "questions": db.scalar(select(func.count()).select_from(Question)),
            "edges": db.scalar(
                select(func.count()).select_from(KnowledgePointPrerequisite)
            ),
        }


def _xlsx_bytes(rows, *, sheet_name: str = "Sheet1", extra_sheets: int = 0) -> bytes:
    from openpyxl import Workbook

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = sheet_name
    for row in rows:
        sheet.append(row)
    for index in range(extra_sheets):
        title = f"其它{index + 1}"
        workbook.create_sheet(title=title)
        workbook[title].append(["不应被读取"])
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def _generate(client, headers, kp_id: int) -> dict:
    response = client.post(
        f"{API}/questions/generate",
        headers=headers,
        json={
            "subject": AI_SUBJECT,
            "knowledge_point": "栈",
            "question_type": "choice",
            "count": 1,
            "knowledge_point_id": kp_id,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()[0]


def _answer(client, headers, question_id: int, value: str) -> dict:
    response = client.post(
        f"{API}/questions/{question_id}/answers",
        headers=headers,
        json={"user_answer": value, "spent_seconds": 10},
    )
    assert response.status_code == 201, response.text
    return response.json()


# ==================================================================
# A. 解析层
# ==================================================================


def test_parse_pasted_tsv(client):
    _, headers = _register(client, "admin")
    payload = _preview(client, headers, "学科\t知识点名\n数据结构\t栈\n")
    assert payload["source_format"] == "paste"
    assert payload["has_header"] is True
    assert payload["total_rows"] == 1
    assert payload["detected_delimiter"] == "\t"
    assert payload["rows"][0]["subject"] == "数据结构"
    assert payload["rows"][0]["name"] == "栈"


def test_parse_csv_comma(client):
    _, headers = _register(client, "admin")
    payload = _preview(client, headers, "学科,知识点名\n数据结构,队列\n")
    assert payload["detected_delimiter"] == ","
    assert payload["rows"][0]["name"] == "队列"


def test_parse_csv_semicolon(client):
    _, headers = _register(client, "admin")
    payload = _preview(client, headers, "学科;知识点名\n数据结构;队列\n")
    assert payload["detected_delimiter"] == ";"
    assert payload["rows"][0]["name"] == "队列"


def test_parse_quoted_field_with_comma_and_newline(client):
    _, headers = _register(client, "admin")
    content = '学科,知识点名,别名\n数据结构,"栈, 后进先出",stack\n'
    payload = _preview(client, headers, content)
    assert payload["error_rows"] == 0, payload
    assert payload["rows"][0]["name"] == "栈, 后进先出"
    assert payload["rows"][0]["aliases"] == ["stack"]


def test_parse_utf8_bom_header_is_stripped(client):
    _, headers = _register(client, "admin")
    raw = ("\ufeff" + HEADER + "\n数据结构,栈\n").encode("utf-8")
    response = _post(client, "preview", headers, file=("bom.csv", raw))
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["detected_encoding"] == "utf-8-sig"
    assert payload["rows"][0]["subject"] == "数据结构"


def test_parse_gbk_file_keeps_chinese(client):
    _, headers = _register(client, "admin")
    raw = (HEADER + "\n数据结构,栈\n").encode("gb18030")
    response = _post(client, "preview", headers, file=("gbk.csv", raw))
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["detected_encoding"] == "gb18030"
    assert payload["rows"][0]["name"] == "栈"
    assert any("gb18030" in note for note in payload["parse_notes"])


def test_parse_without_header_uses_positions(client):
    _, headers = _register(client, "admin")
    payload = _preview(client, headers, "数据结构\t\t栈\n")
    assert payload["has_header"] is False
    assert payload["total_rows"] == 1
    assert payload["rows"][0]["subject"] == "数据结构"
    assert payload["rows"][0]["name"] == "栈"
    assert any("未检测到表头" in note for note in payload["parse_notes"])


def test_blank_rows_are_dropped_and_reported(client):
    _, headers = _register(client, "admin")
    payload = _preview(client, headers, "学科,知识点名\n\n数据结构,栈\n\n")
    assert payload["total_rows"] == 1
    assert any("空行" in note for note in payload["parse_notes"])


# ==================================================================
# B. xlsx
# ==================================================================


def test_xlsx_basic_read(client):
    _, headers = _register(client, "admin")
    raw = _xlsx_bytes([["学科", "知识点名", "预计学时"], ["数据结构", "栈", 30]])
    response = _post(client, "preview", headers, file=("kp.xlsx", raw))
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["source_format"] == "xlsx"
    row = payload["rows"][0]
    assert row["name"] == "栈"
    # 数值单元格 30 必须还原成整数 "30"，而不是 "30.0"。
    assert row["estimated_minutes"] == 30


def test_xlsx_multiple_sheets_only_first_is_read(client):
    _, headers = _register(client, "admin")
    raw = _xlsx_bytes([["学科", "知识点名"], ["数据结构", "栈"]], extra_sheets=2)
    response = _post(client, "preview", headers, file=("multi.xlsx", raw))
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["total_rows"] == 1
    assert any("工作表" in note for note in payload["parse_notes"])


def test_legacy_xls_is_rejected_with_clear_message(client):
    _, headers = _register(client, "admin")
    response = _post(client, "preview", headers, file=("legacy.xls", b"\xd0\xcf\x11\xe0"))
    assert response.status_code == 400, response.text
    assert _rejection_code(response) == "B01"
    assert ".xls" in response.json()["detail"]["message"]


def test_corrupted_xlsx_is_rejected(client):
    _, headers = _register(client, "admin")
    response = _post(client, "preview", headers, file=("broken.xlsx", b"not a zip file"))
    assert response.status_code == 400, response.text
    assert _rejection_code(response) == "B01"


# ==================================================================
# C. 行级 error E01–E11
# ==================================================================


def test_e01_empty_subject(client):
    _, headers = _register(client, "admin")
    payload = _preview(client, headers, f"{HEADER}\n,栈\n")
    assert "E01" in _row_codes(payload, 0)
    assert _issue(payload, "E01")["field"] == "subject"
    assert payload["can_apply"] is False


def test_e02_empty_name(client):
    _, headers = _register(client, "admin")
    payload = _preview(client, headers, f"{HEADER}\n数据结构,\n")
    assert "E02" in _row_codes(payload, 0)


def test_e03_too_long_name_and_subject(client):
    _, headers = _register(client, "admin")
    payload = _preview(client, headers, f"{HEADER}\n{'主' * 101},栈\n")
    assert "E03" in _row_codes(payload, 0)
    payload = _preview(client, headers, f"{HEADER}\n数据结构,{'点' * 201}\n")
    assert "E03" in _row_codes(payload, 0)


def test_e04_code_too_long(client):
    _, headers = _register(client, "admin")
    payload = _preview(client, headers, f"学科,知识点名,编码\n数据结构,栈,{'C' * 65}\n")
    assert "E04" in _row_codes(payload, 0)


def test_e05_invalid_difficulty(client):
    _, headers = _register(client, "admin")
    payload = _preview(client, headers, "学科,知识点名,难度\n数据结构,栈,super\n")
    assert "E05" in _row_codes(payload, 0)


def test_e06_invalid_minutes(client):
    _, headers = _register(client, "admin")
    payload = _preview(client, headers, "学科,知识点名,预计学时\n数据结构,栈,abc\n")
    assert "E06" in _row_codes(payload, 0)
    payload = _preview(client, headers, "学科,知识点名,预计学时\n数据结构,栈,-5\n")
    assert "E06" in _row_codes(payload, 0)


def test_e07_too_many_aliases(client):
    _, headers = _register(client, "admin")
    aliases = "|".join(f"a{index}" for index in range(21))
    payload = _preview(client, headers, f"学科,知识点名,别名\n数据结构,栈,{aliases}\n")
    assert "E07" in _row_codes(payload, 0)


def test_e08_parent_subject_mismatch(client):
    _, admin_headers = _register(client, "admin")
    _create_kp(client, admin_headers, name="栈", subject="算法")
    payload = _preview(
        client, admin_headers, "学科,层级路径,知识点名\n数据结构,栈,出栈操作\n"
    )
    assert "E08" in _row_codes(payload, 0)


def test_e09_duplicate_within_batch(client):
    _, headers = _register(client, "admin")
    payload = _preview(client, headers, f"{HEADER}\n数据结构,栈\n数据结构,栈\n")
    assert payload["total_rows"] == 2
    assert "E09" in _row_codes(payload, 1)
    assert "E09" not in _row_codes(payload, 0)
    assert "第 2 行" in _issue(payload, "E09")["message"]


def test_e10_self_reference_in_path(client):
    _, headers = _register(client, "admin")
    payload = _preview(client, headers, "学科,层级路径,知识点名\n数据结构,栈>线性表,栈\n")
    assert "E10" in _row_codes(payload, 0)


def test_e11_column_overflow(client):
    _, headers = _register(client, "admin")
    payload = _preview(client, headers, "学科,知识点名\n数据结构,栈,x,y,z\n")
    assert "E11" in _row_codes(payload, 0)


# ==================================================================
# D. 整批级 error B01–B04
# ==================================================================


def test_b01_binary_content(client):
    _, headers = _register(client, "admin")
    response = _post(client, "preview", headers, file=("bin.csv", b"\x00\x01\x02abc"))
    assert response.status_code == 400, response.text
    assert _rejection_code(response) == "B01"
    assert response.json()["detail"]["batch_errors"][0]["row"] is None


def test_b01_unrecognizable_encoding(client):
    _, headers = _register(client, "admin")
    # 0xFF 在 gb18030 / utf-8 中都不是合法起始字节。
    response = _post(client, "preview", headers, file=("bad.csv", b"\xff\xff\xff\xff"))
    assert response.status_code == 400, response.text
    assert _rejection_code(response) == "B01"


def test_b02_missing_required_column(client):
    _, headers = _register(client, "admin")
    response = _post(client, "preview", headers, content="层级路径,知识点名\n线性表,栈\n")
    assert response.status_code == 400, response.text
    assert _rejection_code(response) == "B02"
    assert "学科" in response.json()["detail"]["message"]


def test_b02_duplicate_header_column(client):
    _, headers = _register(client, "admin")
    response = _post(client, "preview", headers, content="学科,学科,知识点名\n数据结构,算法,栈\n")
    assert response.status_code == 400, response.text
    assert _rejection_code(response) == "B02"


def test_b03_too_many_rows(client):
    _, headers = _register(client, "admin")
    body = "".join(f"数据结构,点{index}\n" for index in range(501))
    response = _post(client, "preview", headers, content=f"{HEADER}\n{body}")
    assert response.status_code == 400, response.text
    assert _rejection_code(response) == "B03"
    assert "501" in response.json()["detail"]["message"]


def test_b04_cycle_detected_across_rows(client):
    """A>B 与 B>A 各自合法，合起来才成环 —— 逐行校验永远发现不了。"""
    _, headers = _register(client, "admin")
    content = "学科,层级路径,知识点名\n数据结构,A>B,B\n数据结构,B>A,A\n"
    payload = _preview(client, headers, content)
    # preview 不落库，因此这里能正常返回；成环在 apply 时才拒绝写入。
    assert payload["rows"][0]["name"] == "B"
    response = _apply(client, headers, content)
    assert response.status_code == 409, response.text
    assert _rejection_code(response) == "B04"
    detail = response.json()["detail"]
    assert len(detail["cycle"]) >= 3
    assert "数据结构 > B" in detail["cycle"]
    assert _counts()["knowledge_points"] == 0


# ==================================================================
# E. warning W01–W06（不阻断）
# ==================================================================


def test_w01_new_subject_does_not_block(client):
    _, headers = _register(client, "admin")
    payload = _preview(client, headers, f"{HEADER}\n全新学科,栈\n")
    assert "W01" in _row_codes(payload, 0)
    assert payload["new_subjects"] == ["全新学科"]
    assert payload["can_apply"] is True
    assert payload["error_rows"] == 0


def test_w02_auto_parent_and_paths_to_create(client):
    _, headers = _register(client, "admin")
    payload = _preview(client, headers, "学科,层级路径,知识点名\n数据结构,线性表>栈,栈\n")
    assert "W02" in _row_codes(payload, 0)
    assert payload["parent_paths_to_create"] == ["线性表"]
    assert payload["planned"]["create_parent"] == 1
    assert payload["can_apply"] is True


def test_w03_existing_row_is_warning_not_error(client):
    _, admin_headers = _register(client, "admin")
    _create_kp(client, admin_headers, name="栈", subject="数据结构")
    payload = _preview(client, admin_headers, f"{HEADER}\n数据结构,栈\n")
    assert "W03" in _row_codes(payload, 0)
    assert payload["can_apply"] is True
    assert payload["planned"]["skip"] == 1


def test_w04_deep_hierarchy(client):
    _, headers = _register(client, "admin")
    payload = _preview(client, headers, "学科,层级路径,知识点名\n数据结构,a>b>c>d>e,f\n")
    assert "W04" in _row_codes(payload, 0)
    assert payload["can_apply"] is True


def test_w05_alias_cross_row(client):
    _, headers = _register(client, "admin")
    # 第 1 行的别名「栈」与第 2 行的名称「栈」重复 —— M1 有意留到 M2 的检查。
    content = "学科,知识点名,别名\n数据结构,堆栈,栈\n数据结构,栈,x\n"
    payload = _preview(client, headers, content)
    assert "W05" in _row_codes(payload, 0)
    assert payload["can_apply"] is True


def test_w06_missing_metadata(client):
    _, headers = _register(client, "admin")
    payload = _preview(client, headers, f"{HEADER}\n数据结构,栈\n")
    assert "W06" in _row_codes(payload, 0)


# ==================================================================
# F. 幂等与冲突策略
# ==================================================================


def test_skip_strategy_leaves_existing_row_untouched(client):
    _, admin_headers = _register(client, "admin")
    existing = _create_kp(client, admin_headers, name="栈", subject="数据结构")
    content = f"{HEADER_FULL}\n数据结构,线性表>栈,栈,堆栈,easy,30,DS.STACK\n"
    report = _apply_ok(client, admin_headers, content, strategy="skip")
    # skip 表示「完全不动」：连它要用的自动父节点也不建，避免留下孤儿节点
    assert report["created_count"] == 0
    assert report["auto_parent_count"] == 0
    assert report["skipped_count"] == 1
    assert report["updated_count"] == 0
    assert _kp_by_name(client, admin_headers, "线性表") is None

    after = client.get(
        f"{API}/knowledge-points/{existing['id']}", headers=admin_headers
    ).json()
    assert after["aliases"] is None
    assert after["difficulty"] is None
    assert after["estimated_minutes"] is None
    assert after["code"] is None
    assert after["parent_id"] is None


def test_update_empty_fills_only_empty_fields(client):
    _, admin_headers = _register(client, "admin")
    existing = _create_kp(
        client,
        admin_headers,
        name="栈",
        subject="数据结构",
        difficulty="hard",
        estimated_minutes=99,
    )
    content = f"{HEADER_FULL}\n数据结构,,栈,堆栈,easy,30,DS.STACK\n"
    report = _apply_ok(client, admin_headers, content, strategy="update_empty")
    assert report["updated_count"] == 1

    after = client.get(
        f"{API}/knowledge-points/{existing['id']}", headers=admin_headers
    ).json()
    # 空字段被补上
    assert after["aliases"] == ["堆栈"]
    assert after["code"] == "DS.STACK"
    # 非空字段绝不被覆盖
    assert after["difficulty"] == "hard"
    assert after["estimated_minutes"] == 99


def test_update_empty_with_nothing_to_fill_counts_as_skipped(client):
    _, admin_headers = _register(client, "admin")
    _create_kp(
        client,
        admin_headers,
        name="栈",
        subject="数据结构",
        difficulty="hard",
        estimated_minutes=99,
        code="DS.STACK",
        aliases=["堆栈"],
    )
    content = f"{HEADER_FULL}\n数据结构,,栈,,,,\n"
    report = _apply_ok(client, admin_headers, content, strategy="update_empty")
    assert report["updated_count"] == 0
    assert report["skipped_count"] == 1


def test_repeated_import_creates_then_skips(client):
    _, admin_headers = _register(client, "admin")
    content = f"{HEADER}\n数据结构,栈\n"
    first = _apply_ok(client, admin_headers, content)
    assert (first["created_count"], first["skipped_count"]) == (1, 0)
    second = _apply_ok(client, admin_headers, content)
    assert (second["created_count"], second["skipped_count"]) == (0, 1)
    third = _apply_ok(client, admin_headers, content)
    assert (third["created_count"], third["skipped_count"]) == (0, 1)
    assert _counts()["knowledge_points"] == 1


def test_duplicate_code_is_conflict_and_rolls_back_whole_batch(client):
    _, admin_headers = _register(client, "admin")
    _create_kp(client, admin_headers, name="队列", subject="数据结构", code="DS.QQ")
    content = f"{HEADER_FULL}\n数据结构,,栈,,,,DS.QQ\n"
    response = _apply(client, admin_headers, content)
    assert response.status_code == 409, response.text
    assert _rejection_code(response) == "A02"
    # 全有或全无：栈没有被写进去
    assert _kp_by_name(client, admin_headers, "栈") is None


# ==================================================================
# G. 父节点自动创建
# ==================================================================


def test_auto_parent_single_and_multi_level(client):
    _, headers = _register(client, "admin")
    content = "学科,层级路径,知识点名\n数据结构,线性表,线性表\n数据结构,线性表>栈>出栈,出栈\n"
    report = _apply_ok(client, headers, content)
    assert report["created_count"] == 2
    # 第 1 行把「线性表」建成普通知识点，第 2 行只需自动补出中间的「栈」
    assert report["auto_parent_count"] == 1

    linear = _kp_by_name(client, headers, "线性表")
    stack = _kp_by_name(client, headers, "栈")
    pop = _kp_by_name(client, headers, "出栈")
    assert linear is not None and stack is not None and pop is not None
    assert stack["parent_id"] == linear["id"]
    assert pop["parent_id"] == stack["id"]


def test_auto_parent_is_reused_across_rows(client):
    _, headers = _register(client, "admin")
    # 两行的「层级路径」末段与知识点名同形，因此路径末段就是本行本身，
    # 真正需要自动创建的只有共同祖先「线性表」，且只能建一次。
    content = "学科,层级路径,知识点名\n数据结构,线性表>A,a\n数据结构,线性表>B,b\n"
    report = _apply_ok(client, headers, content)
    assert report["created_count"] == 2
    assert report["auto_parent_count"] == 1
    assert _kp_count_by_name(client, headers, "线性表") == 1
    linear = _kp_by_name(client, headers, "线性表")
    assert _kp_by_name(client, headers, "a")["parent_id"] == linear["id"]
    assert _kp_by_name(client, headers, "b")["parent_id"] == linear["id"]


def test_existing_parent_is_reused(client):
    _, headers = _register(client, "admin")
    _create_kp(client, headers, name="线性表", subject="数据结构")
    report = _apply_ok(client, headers, "学科,层级路径,知识点名\n数据结构,线性表>栈,栈\n")
    assert report["auto_parent_count"] == 0
    linear = _kp_by_name(client, headers, "线性表")
    assert _kp_by_name(client, headers, "栈")["parent_id"] == linear["id"]


# ==================================================================
# H. 写入事务（全有或全无）
# ==================================================================


def test_injected_write_failure_rolls_back_everything_and_records_failed_batch(
    client, monkeypatch
):
    _, admin_headers = _register(client, "admin")
    before = _counts()

    def boom(self, **kwargs):
        raise RuntimeError("injected failure")

    monkeypatch.setattr(KnowledgePointService, "create", boom)
    response = _apply(
        client, admin_headers, "学科,层级路径,知识点名\n数据结构,线性表>栈,栈\n"
    )
    assert response.status_code == 409, response.text
    assert _rejection_code(response) == "A02"

    after = _counts()
    assert after["knowledge_points"] == before["knowledge_points"]
    # 失败批次必须在回滚之后用新事务单独落库
    assert after["batches"] == before["batches"] + 1
    with SessionLocal() as db:
        batch = db.scalar(
            select(KnowledgePointImportBatch).order_by(KnowledgePointImportBatch.id.desc())
        )
        assert batch is not None
        assert batch.status == "failed"
        assert batch.failed_count == batch.total_rows == 1
        assert batch.applied_at is None
        assert "injected failure" in (batch.error_summary or "")


# ==================================================================
# I. 上限
# ==================================================================


def test_oversized_paste_is_rejected(client):
    """超长粘贴会被拒。

    Starlette 的表单解析器对「非文件字段」有 1 MiB 上限，因此超大粘贴在我们
    自己的 2 MiB 闸门之前就已返回 400；关键是**任何情况下都不会有写入**。
    """
    _, headers = _register(client, "admin")
    response = _post(client, "preview", headers, content="x" * (2 * 1024 * 1024 + 16))
    assert response.status_code in (400, 413), response.text
    assert _counts()["knowledge_points"] == 0


def test_oversized_upload_is_413(client):
    _, headers = _register(client, "admin")
    response = _post(
        client, "preview", headers, file=("big.csv", b"x" * (2 * 1024 * 1024 + 16))
    )
    assert response.status_code == 413, response.text


# ==================================================================
# J. 回滚
# ==================================================================


def _last_batch_id() -> int:
    with SessionLocal() as db:
        batch = db.scalar(
            select(KnowledgePointImportBatch).order_by(KnowledgePointImportBatch.id.desc())
        )
        assert batch is not None
        return batch.id


def test_rollback_deletes_created_rows_and_auto_parents(client):
    _, headers = _register(client, "admin")
    report = _apply_ok(client, headers, "学科,层级路径,知识点名\n数据结构,线性表>栈,栈\n")
    assert _counts()["knowledge_points"] == 2

    response = client.post(
        f"{IMPORT}/batches/{report['batch_id']}/rollback", headers=headers
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["deleted_count"] == 2
    assert payload["status"] == "rolled_back"
    assert _counts()["knowledge_points"] == 0

    with SessionLocal() as db:
        batch = db.get(KnowledgePointImportBatch, report["batch_id"])
        assert batch.status == "rolled_back"
        assert batch.rolled_back_at is not None
        # 计数列保留「本批曾导入了多少」的历史事实
        assert batch.created_count == 1


def test_rollback_twice_is_rejected(client):
    _, headers = _register(client, "admin")
    report = _apply_ok(client, headers, f"{HEADER}\n数据结构,栈\n")
    url = f"{IMPORT}/batches/{report['batch_id']}/rollback"
    assert client.post(url, headers=headers).status_code == 200
    again = client.post(url, headers=headers)
    assert again.status_code == 409, again.text
    assert _rejection_code(again) == "A03"


def test_rollback_blocked_by_external_child(client):
    _, headers = _register(client, "admin")
    report = _apply_ok(client, headers, f"{HEADER}\n数据结构,线性表\n")
    parent = _kp_by_name(client, headers, "线性表")
    _create_kp(client, headers, name="栈", subject="数据结构", parent_id=parent["id"])

    response = client.post(
        f"{IMPORT}/batches/{report['batch_id']}/rollback", headers=headers
    )
    assert response.status_code == 409, response.text
    detail = response.json()["detail"]
    assert "阻止回滚" in detail["message"]
    assert _counts()["knowledge_points"] == 2  # 零删除


def test_rollback_blocked_by_linked_question(client):
    _, admin_headers = _register(client, "admin")
    _apply_ok(client, admin_headers, f"{HEADER}\n{AI_SUBJECT},栈\n")
    kp = _kp_by_name(client, admin_headers, "栈", subject=AI_SUBJECT)
    _, user_headers = _register(client, "user")
    _generate(client, user_headers, kp["id"])

    response = client.post(
        f"{IMPORT}/batches/{_last_batch_id()}/rollback", headers=admin_headers
    )
    assert response.status_code == 409, response.text
    assert "题目" in response.json()["detail"]["message"] or "阻止回滚" in (
        response.json()["detail"]["message"]
    )
    assert _counts()["knowledge_points"] == 1


def test_rollback_blocked_by_mastery(client):
    _, admin_headers = _register(client, "admin")
    _apply_ok(client, admin_headers, f"{HEADER}\n{AI_SUBJECT},栈\n")
    kp = _kp_by_name(client, admin_headers, "栈", subject=AI_SUBJECT)
    _, user_headers = _register(client, "user")
    question = _generate(client, user_headers, kp["id"])
    _answer(client, user_headers, question["id"], CORRECT_ANSWER)

    response = client.post(
        f"{IMPORT}/batches/{_last_batch_id()}/rollback", headers=admin_headers
    )
    assert response.status_code == 409, response.text
    assert _counts()["knowledge_points"] == 1


def test_rollback_blocked_by_prerequisite_edge(client):
    _, headers = _register(client, "admin")
    _apply_ok(client, headers, f"{HEADER}\n{AI_SUBJECT},栈\n")
    imported = _kp_by_name(client, headers, "栈", subject=AI_SUBJECT)
    other = _create_kp(client, headers, name="队列", subject=AI_SUBJECT)
    add = client.post(
        f"{API}/knowledge-points/{imported['id']}/prerequisites",
        headers=headers,
        json={"prerequisite_id": other["id"]},
    )
    assert add.status_code == 201, add.text

    response = client.post(
        f"{IMPORT}/batches/{_last_batch_id()}/rollback", headers=headers
    )
    assert response.status_code == 409, response.text
    assert _counts()["knowledge_points"] == 2


def test_rollback_deletes_same_batch_parent_child_in_safe_order(client):
    """同批既有父又有子：必须从叶子往根删，否则撞 ON DELETE RESTRICT。"""
    _, headers = _register(client, "admin")
    report = _apply_ok(
        client,
        headers,
        "学科,层级路径,知识点名\n数据结构,线性表,线性表\n数据结构,线性表>A,a\n",
    )
    assert _counts()["knowledge_points"] == 2

    response = client.post(
        f"{IMPORT}/batches/{report['batch_id']}/rollback", headers=headers
    )
    assert response.status_code == 200, response.text
    assert response.json()["deleted_count"] == 2
    assert _counts()["knowledge_points"] == 0


def test_rollback_keeps_update_empty_fills(client):
    _, headers = _register(client, "admin")
    existing = _create_kp(client, headers, name="栈", subject="数据结构")
    report = _apply_ok(
        client, headers, f"{HEADER_FULL}\n数据结构,,栈,堆栈,easy,30,DS.STACK\n",
        strategy="update_empty",
    )
    assert report["updated_count"] == 1

    response = client.post(
        f"{IMPORT}/batches/{report['batch_id']}/rollback", headers=headers
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["deleted_count"] == 0
    assert payload["kept_updated_count"] == 1
    after = client.get(
        f"{API}/knowledge-points/{existing['id']}", headers=headers
    ).json()
    assert after["code"] == "DS.STACK"  # 已知局限：回滚不清空补充内容


def test_rollback_unknown_batch_is_404(client):
    _, headers = _register(client, "admin")
    response = client.post(f"{IMPORT}/batches/999999/rollback", headers=headers)
    assert response.status_code == 404, response.text


def test_batch_detail_lists_knowledge_points_and_blockers(client):
    _, headers = _register(client, "admin")
    report = _apply_ok(client, headers, "学科,层级路径,知识点名\n数据结构,线性表>栈,栈\n")
    response = client.get(f"{IMPORT}/batches/{report['batch_id']}", headers=headers)
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["status"] == "applied"
    assert {item["name"] for item in payload["knowledge_points"]} == {"线性表", "栈"}
    assert payload["blocking_references"] == []

    listing = client.get(f"{IMPORT}/batches", headers=headers)
    assert listing.status_code == 200, listing.text
    assert [item["id"] for item in listing.json()] == [report["batch_id"]]

    missing = client.get(f"{IMPORT}/batches/999999", headers=headers)
    assert missing.status_code == 404


# ==================================================================
# K. 权限
# ==================================================================


_M2_ENDPOINTS = (
    ("post", f"{IMPORT}/preview"),
    ("post", f"{IMPORT}/apply"),
    ("get", f"{IMPORT}/batches"),
    ("get", f"{IMPORT}/batches/1"),
    ("post", f"{IMPORT}/batches/1/rollback"),
    ("get", f"{IMPORT}/template"),
)


@pytest.mark.parametrize(("method", "url"), _M2_ENDPOINTS)
def test_endpoints_require_login(client, method, url):
    response = getattr(client, method)(url)
    assert response.status_code == 401, (url, response.status_code)


@pytest.mark.parametrize(("method", "url"), _M2_ENDPOINTS)
def test_endpoints_require_admin(client, method, url):
    _, headers = _register(client, "user")
    response = getattr(client, method)(url, headers=headers)
    assert response.status_code == 403, (url, response.status_code)


# ==================================================================
# L. ⭐ 只读性（preview 不落库的直接证据）
# ==================================================================


def test_preview_writes_nothing(client):
    _, headers = _register(client, "admin")
    content = "学科,层级路径,知识点名,难度\n数据结构,线性表>栈,栈,easy\n"
    before = _counts()
    payload = _preview(client, headers, content)
    assert payload["can_apply"] is True
    after = _counts()
    assert after == before
    assert after["batches"] == 0
    assert after["knowledge_points"] == 0


# ==================================================================
# M. ⭐ 红线回归：difficulty 仍不参与掌握度
# ==================================================================


def test_imported_difficulty_still_does_not_affect_mastery(client):
    """通过**导入**建立知识点后，翻转其 difficulty 仍不影响掌握度。

    与 M1 的同名测试形成双保险：M1 走单条 API 写入，本用例走批量导入写入，
    两条入口都不能让 difficulty 进入 MasteryService。
    """
    _, admin_headers = _register(client, "admin")
    report = _apply_ok(client, admin_headers, f"{HEADER}\n{AI_SUBJECT},栈\n")
    assert report["created_count"] == 1
    kp = _kp_by_name(client, admin_headers, "栈", subject=AI_SUBJECT)
    assert kp["difficulty"] is None

    scores: list[int] = []
    for level in (None, "hard", "easy"):
        if level is not None:
            patched = client.patch(
                f"{API}/knowledge-points/{kp['id']}",
                headers=admin_headers,
                json={"difficulty": level},
            )
            assert patched.status_code == 200, patched.text
        _, headers = _register(client, "user")
        question = _generate(client, headers, kp["id"])
        _answer(client, headers, question["id"], CORRECT_ANSWER)
        row = client.get(f"{API}/mastery/{kp['id']}", headers=headers).json()
        assert row["knowledge_point"]["difficulty"] == level
        scores.append(row["mastery_score"])

    assert scores[0] == scores[1] == scores[2], scores
    assert scores[0] > 50


def test_import_leaves_mastery_and_prerequisite_modules_untouched():
    """红线：M2 不得改动掌握度 / 前置依赖 / 题目关联的算法实现。

    直接对源码做结构性断言，比「跑一遍恰好通过」更能守住这条线：
    掌握度里的 `difficulty` 只允许来自作答记录（`result.difficulty`），
    绝不允许来自知识点（`knowledge_point.difficulty`）。
    """
    import inspect

    from app.services import mastery, prerequisite, question_knowledge_point_service

    mastery_source = inspect.getsource(mastery)
    assert "knowledge_point.difficulty" not in mastery_source
    assert "KnowledgePoint.difficulty" not in mastery_source
    for module in (prerequisite, question_knowledge_point_service):
        assert "difficulty" not in inspect.getsource(module)


# ==================================================================
# N. 模板
# ==================================================================


def test_template_download_has_bom_and_csv_content_type(client):
    _, headers = _register(client, "admin")
    response = client.get(f"{IMPORT}/template", headers=headers)
    assert response.status_code == 200, response.text
    assert "text/csv" in response.headers["content-type"]
    assert "charset=utf-8" in response.headers["content-type"]
    assert "knowledge_points_template.csv" in response.headers["content-disposition"]
    assert response.text.startswith("\ufeff")
    assert "学科,层级路径,知识点名" in response.text

    # 模板必须能被自己的解析器吃下去（自洽性）。
    listing = client.get(f"{IMPORT}/template", headers=headers)
    payload = _preview(client, headers, listing.text.lstrip("\ufeff"))
    assert payload["total_rows"] == 3
    assert payload["error_rows"] == 0
    assert payload["planned"]["create"] == 3
    # 第 1 行把「线性表」本身建成知识点，因此不需要自动创建任何父节点。
    assert payload["planned"]["create_parent"] == 0


# ==================================================================
# O. 误操作防护
# ==================================================================


def test_apply_rejects_mismatched_expected_total_rows(client):
    _, headers = _register(client, "admin")
    response = _apply(client, headers, f"{HEADER}\n数据结构,栈\n", expected=99)
    assert response.status_code == 409, response.text
    assert _counts()["knowledge_points"] == 0


def test_apply_rejects_when_row_errors_exist(client):
    _, headers = _register(client, "admin")
    response = _apply(client, headers, f"{HEADER}\n,栈\n")
    assert response.status_code == 409, response.text
    detail = response.json()["detail"]
    assert detail["row_issues"], detail
    assert detail["row_issues"][0]["code"] == "E01"
    assert _counts()["knowledge_points"] == 0


def test_apply_rejects_both_file_and_content(client):
    _, headers = _register(client, "admin")
    response = _post(
        client, "preview", headers, content=f"{HEADER}\n数据结构,栈\n",
        file=("a.csv", b"x"),
    )
    assert response.status_code == 400, response.text


def test_apply_rejects_missing_input(client):
    _, headers = _register(client, "admin")
    response = _post(client, "preview", headers)
    assert response.status_code == 400, response.text


def test_apply_records_batch_audit_fields(client):
    _, headers = _register(client, "admin")
    report = _apply_ok(client, headers, "学科,层级路径,知识点名\n数据结构,线性表>栈,栈\n")
    assert report["status"] == "applied"
    assert report["auto_parent_count"] == 1
    assert report["duration_ms"] >= 0
    with SessionLocal() as db:
        batch = db.get(KnowledgePointImportBatch, report["batch_id"])
        assert batch is not None
        assert batch.source_format == "paste"
        assert batch.conflict_strategy == "skip"
        assert batch.total_rows == 1
        assert batch.created_count == 1
        assert batch.user_id is not None
        assert batch.applied_at is not None
        assert batch.source_name is not None
