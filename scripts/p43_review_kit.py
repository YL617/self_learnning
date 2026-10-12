"""M5.5 P4-3.2 —— 人工审核工作流（manifest → Excel 审核清单 → 审核决定）。

三段式流水线的最后一段：把人从"逐条读 JSON"里解放出来。

    生成 (P4-3.1) → 门禁 (P4-3.1) → **人工审核（本模块）** → 决定 JSON → Apply (P4-3.3)

两个子命令::

    # ① 构建审核清单：questions_manifest.json → 审核清单.xlsx
    python scripts/p43_review_kit.py build \
        --manifest docs/M5.5_P4-3_题目供给清单_批1.json \
        --out      docs/M5.5_P4-3.2_审核清单_批1.xlsx

    # ② 回收审核决定：审核清单.xlsx（人工已填） → 决定.json
    python scripts/p43_review_kit.py collect \
        --checklist docs/M5.5_P4-3.2_审核清单_批1.xlsx \
        --manifest  docs/M5.5_P4-3_题目供给清单_批1.json \
        --out       docs/M5.5_P4-3.2_审核决定_批1.json \
        [--existing docs/M5.5_P4-3_现有题面快照.json]

为什么这样设计（每条都是刻意的取舍）：

  - **内容列就地可编辑 = 修订**：不设"修订副本"列。审阅人直接改题干 / 选项 / 答案 /
    解析 / 难度，``collect`` 以 manifest 为基线逐字段 diff 出 ``changed_fields``。
    "原始内容"永远由 manifest 保管，清单里只有一份内容，人不必在两套列之间对照。
  - **判定只能四选一**（Excel 下拉）：通过 / 修改后通过 / 驳回 / 待定。
    **空白 = 未审核**，``collect`` 一律阻断 —— 杜绝"没审就入库"。
  - **推翻门禁必须留字**：门禁 PASS 才算机器放行；对门禁 FAIL 的题点"通过 / 修改后
    通过"，必须写「审核备注」，``collect`` 记录 ``overridden_gates`` 供审计
    （KMLE：AI 自评不可替代专家评审，但推翻要留痕）。
  - **改完再验结构**：修订后重跑 G1/G2/G5/G6（确定性硬规则）—— 例如改了选项却没同步
    答案 → 直接判错。G3/G4/G7 仅作提示（解析长度、措辞是审阅人的裁量）。
  - **最后一道门查重**：对全部"可入库"题的**最终内容**重跑 G4（对照现有题库 + 彼此），
    防止"两题各自通过、修订后撞车"。
  - **提示与阻断分离**（P4-3.3.1）：``quality_check.warnings``（G5 长度均衡、G5B 批级
    答案分布等）只以「提示：」展示在门禁列与批信息表，**永不**改变 PASS/FAIL，
    也不要求人工写推翻理由 —— 避免把"批级/风格属性"变成人工负担。
  - **零写库**：本模块只读 manifest / 读写本地文件；不 import app、不联网、不碰数据库、
    不建 migration。

退出码::

    0  成功且无阻断问题
    1  校验发现阻断问题（仍写出决定 JSON 供人工修正）
    2  用法错误
    3  运行期失败（文件不可读 / manifest 非法 / 清单结构不符）
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill, Protection
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

SCRIPT_DIR = Path(__file__).resolve().parent

# 门禁模块与主脚本同目录；本地直跑（非从 backend/ 运行）时必须显式注入 sys.path。
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import p43_gates as gates

SCHEMA_VERSION = "p4-3.2"
TOOL_NAME = "p43_review_kit"

CHECKLIST_SHEET = "审核清单"
GUIDE_SHEET = "审核说明"
BATCH_SHEET = "批信息"

COL_QID = "编号"
COL_CONCEPT = "知识点"
COL_CODE = "知识域代码"
COL_GATE = "门禁"
COL_GATE_REASON = "门禁原因"
COL_SUGGEST = "建议"
COL_DIFFICULTY = "难度"
COL_STEM = "题干"
COL_ANSWER = "答案"
COL_ANALYSIS = "解析"
COL_DECISION = "判定"
COL_NOTE = "审核备注"
ROW_KEY = "_行号"

OPTION_HEADER_TEMPLATE = "选项{}"
_OPTION_HEADER_RE = re.compile(r"^选项[A-Z]$")

# (表头, 是否机器锁定, 列宽) —— 锁定列 = 由 manifest 生成、人工不得修改
BASE_COLUMNS: tuple[tuple[str, bool, int], ...] = (
    (COL_QID, True, 13),
    (COL_CONCEPT, True, 18),
    (COL_CODE, True, 26),
    (COL_GATE, True, 8),
    (COL_GATE_REASON, True, 40),
    (COL_SUGGEST, True, 8),
    (COL_DIFFICULTY, False, 8),
    (COL_STEM, False, 52),
)
TAIL_COLUMNS: tuple[tuple[str, bool, int], ...] = (
    (COL_ANSWER, False, 8),
    (COL_ANALYSIS, False, 52),
    (COL_DECISION, False, 13),
    (COL_NOTE, False, 28),
)
OPTION_COLUMN_WIDTH = 24
MIN_OPTION_COLUMNS = 4

# 决策：Excel 里显示中文，机器侧用稳定的 key（便于日后外部系统消费）。
DECISION_APPROVE = "通过"
DECISION_REVISE = "修改后通过"
DECISION_REJECT = "驳回"
DECISION_DEFER = "待定"
DECISION_LABELS: tuple[str, ...] = (
    DECISION_APPROVE,
    DECISION_REVISE,
    DECISION_REJECT,
    DECISION_DEFER,
)
DECISION_TO_KEY = {
    DECISION_APPROVE: "approve",
    DECISION_REVISE: "revise",
    DECISION_REJECT: "reject",
    DECISION_DEFER: "defer",
}
APPLY_HINT = {
    "approve": "submit_review → approve → publish（用原内容）",
    "revise": "用修订后内容建题 → submit_review → approve → publish",
    "reject": "submit_review → reject（不入共享题库）",
    "defer": None,
}

# 修订后必须重新通过的**确定性结构门禁**（改坏了就在这里拦）。
REVISION_BLOCKING_GATES = ("G1", "G2", "G5", "G6")
# 修订后仅提示、不阻断（解析长度 / 措辞属审阅人裁量）。
REVISION_ADVISORY_GATES = ("G3", "G4", "G7")

HEADER_FONT = Font(color="FFFFFFFF", bold=True, size=10)
LOCKED_FILL = PatternFill("solid", fgColor="FF44546A")
EDITABLE_FILL = PatternFill("solid", fgColor="FF2E7D32")
DECISION_FILL = PatternFill("solid", fgColor="FFFFF2CC")
GATE_PASS_FONT = Font(color="FF1B5E20", bold=True, size=10)
GATE_FAIL_FONT = Font(color="FFC62828", bold=True, size=10)
BODY_FONT = Font(size=10)
TITLE_FONT = Font(bold=True, size=12)
WRAP_LEFT = Alignment(vertical="top", wrap_text=True)
CENTER_TOP = Alignment(vertical="top", horizontal="center", wrap_text=True)
HEADER_ALIGN = Alignment(vertical="center", horizontal="center", wrap_text=True)

WRAP_LEFT_HEADERS = {COL_CONCEPT, COL_GATE_REASON, COL_STEM, COL_ANALYSIS, COL_NOTE}


class ReviewKitError(Exception):
    """本模块可预期的运行期错误（用法错误以外的失败）。"""


# ---------------------------------------------------------------------------
# 通用工具
# ---------------------------------------------------------------------------
def _utf8_stdout() -> None:
    """Windows 控制台默认 cp936，中文输出会炸；尽量切 UTF-8。"""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8")
        except (ValueError, OSError):
            pass


def _norm_cell(value: Any) -> str:
    """单元格 → 用于比较的字符串（Excel 可能把数字读成 float）。"""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, float):
        return str(int(value)) if value.is_integer() else str(value)
    return str(value).strip()


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# xlsx 的 zip 条目时间戳统一钉在 1980-01-01（DOS epoch）。
ZIP_FIXED_TIMESTAMP = (1980, 1, 1, 0, 0, 0)
CORE_PROPS_ENTRY = "docProps/core.xml"
_CORE_MODIFIED_RE = re.compile(rb"(<dcterms:modified[^>]*>)([^<]*)(</dcterms:modified>)")


def _w3cdtf(moment: Any) -> str:
    """datetime → ``dcterms:W3CDTF`` 文本（与 openpyxl 的输出格式一致）。"""
    if isinstance(moment, str):
        return moment
    if moment is None:
        return "1980-01-01T00:00:00Z"
    if getattr(moment, "tzinfo", None) is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _pin_core_modified(payload: bytes, stamp: str) -> bytes:
    """把 ``docProps/core.xml`` 的 ``dcterms:modified`` 钉成 ``stamp``。

    openpyxl 在 ``save()`` 时**无视** ``properties.modified``、一律写当前时间
    （``properties.created`` 却被尊重）→ 产物仍带时间依赖。这里显式改回来。
    """
    return _CORE_MODIFIED_RE.sub(
        lambda match: match.group(1) + stamp.encode("utf-8") + match.group(3), payload, count=1
    )


def save_workbook(workbook: Workbook, path: Path) -> None:
    """把工作簿保存成**逐字节可复现**的 xlsx（产物只取决于内容）。

    两处时间依赖都要治：

    1. **zip 条目时间戳**：``Workbook.save`` 用当前时间写 zip 时间戳（DOS 2 秒粒度）
       → 同一内容两次构建会差几个字节。这里按固定时间戳重新打包。
    2. **``docProps/core.xml`` 的 ``dcterms:modified``**：openpyxl 保存时会用当前时间
       覆盖 ``properties.modified``（``created`` 不受影响）→ 同样破坏可复现性。
       这里在重新打包时按调用方设定的值钉死。

    只有这样，"清单 SHA-256" 才真正等价于"清单内容"。
    """
    stamp = _w3cdtf(workbook.properties.modified or workbook.properties.created)
    buffer = io.BytesIO()
    workbook.save(buffer)
    buffer.seek(0)
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(buffer) as source, zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as target:
        for info in source.infolist():
            data = source.read(info.filename)
            if info.filename == CORE_PROPS_ENTRY:
                data = _pin_core_modified(data, stamp)
            fixed = zipfile.ZipInfo(info.filename, date_time=ZIP_FIXED_TIMESTAMP)
            fixed.compress_type = info.compress_type
            fixed.external_attr = info.external_attr
            fixed.internal_attr = info.internal_attr
            fixed.create_system = info.create_system
            target.writestr(fixed, data)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _parse_time(value: str | None) -> datetime:
    """ISO 字符串 → naive UTC datetime（写进 xlsx 属性，便于可复现）。"""
    if not value:
        return datetime.now(timezone.utc).replace(tzinfo=None)
    try:
        stamp = datetime.fromisoformat(value)
    except ValueError:
        return datetime.now(timezone.utc).replace(tzinfo=None)
    if stamp.tzinfo is not None:
        stamp = stamp.astimezone(timezone.utc).replace(tzinfo=None)
    return stamp


def _label(index: int) -> str:
    return chr(ord("A") + index)


def option_count_for(manifest: dict[str, Any]) -> int:
    """清单里要放几条选项列：取实际最大选项数，至少 4，至多 gates.CHOICE_MAX_OPTIONS。"""
    counts = [
        len(question.get("options") or [])
        for question in manifest.get("questions") or []
        if (question.get("question_type") or "choice") == "choice"
    ]
    return max(MIN_OPTION_COLUMNS, min(max(counts, default=0), gates.CHOICE_MAX_OPTIONS))


def option_headers_for(option_count: int) -> list[str]:
    return [OPTION_HEADER_TEMPLATE.format(_label(index)) for index in range(option_count)]


def ordered_headers(option_count: int) -> list[str]:
    names = [name for name, _locked, _width in BASE_COLUMNS]
    names += option_headers_for(option_count)
    names += [name for name, _locked, _width in TAIL_COLUMNS]
    return names


def is_editable(header: str, option_headers: list[str]) -> bool:
    """人工可编辑 = 选项列，或非锁定列（其余列由 manifest 生成、受保护）。"""
    if header in option_headers:
        return True
    for name, locked, _width in BASE_COLUMNS:
        if name == header:
            return not locked
    for name, locked, _width in TAIL_COLUMNS:
        if name == header:
            return not locked
    return False


def column_widths(option_headers: list[str]) -> dict[str, int]:
    widths: dict[str, int] = {name: width for name, _locked, width in BASE_COLUMNS}
    widths.update({name: width for name, _locked, width in TAIL_COLUMNS})
    widths.update({name: OPTION_COLUMN_WIDTH for name in option_headers})
    return widths


# ---------------------------------------------------------------------------
# build：manifest → 审核清单工作簿
# ---------------------------------------------------------------------------
def load_manifest(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ReviewKitError(f"manifest 不是合法 JSON：{exc}") from exc
    if not isinstance(payload, dict):
        raise ReviewKitError("manifest 根节点必须是 JSON 对象")
    questions = payload.get("questions")
    if not isinstance(questions, list):
        raise ReviewKitError("manifest 缺少 questions 数组")
    if not questions:
        raise ReviewKitError(
            "manifest 含 0 道候选题，无内容可审核（请先跑 scripts/generate_question_batch.py）"
        )
    return payload


def gate_reason_text(question: dict[str, Any]) -> str:
    """门禁列文本：先列**阻断**原因（带门禁代号），再追加**提示**（前缀「提示：」）。

    提示（``quality_check.warnings``）**不会**让 PASS 变成 FAIL —— 它只提醒审阅人
    "这里有一条建议看一眼"（如"正确选项显著长于干扰项，可能泄露答案"）。
    """
    quality = question.get("quality_check") or {}
    parts = [
        f"{code} {item.get('reason')}"
        for code, item in (quality.get("gates") or {}).items()
        if item.get("passed") is False and item.get("reason")
    ]
    if not parts:
        parts = [str(reason) for reason in (quality.get("reasons") or [])]
    parts.extend(f"提示：{warning}" for warning in (quality.get("warnings") or []))
    return "；".join(parts)


def answer_distribution_text(manifest: dict[str, Any]) -> str:
    """批信息表里的"批内答案分布提示"：均衡则写明无提示，否则给出建议原文。"""
    summary = manifest.get("summary") or {}
    warning = (summary.get("answer_position") or {}).get("warning")
    if not warning:
        return "均衡（无提示）"
    return str(warning.get("message") or warning)


def options_shuffle_text(manifest: dict[str, Any]) -> str:
    shuffle = manifest.get("options_shuffle") or {}
    if not shuffle.get("enabled"):
        return "关"
    return f"开（已洗牌 {shuffle.get('applied', 0)} 题）"


def _question_row_values(question: dict[str, Any], option_headers: list[str]) -> dict[str, Any]:
    quality = question.get("quality_check") or {}
    values: dict[str, Any] = {
        COL_QID: question.get("question_id"),
        COL_CONCEPT: question.get("knowledge_point_name"),
        COL_CODE: question.get("knowledge_point_code"),
        COL_GATE: "PASS" if quality.get("passed") else "FAIL",
        COL_GATE_REASON: gate_reason_text(question),
        COL_SUGGEST: question.get("suggested_action"),
        COL_DIFFICULTY: question.get("difficulty"),
        COL_STEM: question.get("stem"),
        COL_ANSWER: question.get("answer"),
        COL_ANALYSIS: question.get("analysis"),
        COL_DECISION: None,
        COL_NOTE: None,
    }
    options = [str(item) for item in (question.get("options") or [])]
    for index, header in enumerate(option_headers):
        values[header] = options[index] if index < len(options) else None
    return values


def _write_checklist_sheet(ws, manifest: dict[str, Any], option_headers: list[str]) -> int:
    headers = ordered_headers(len(option_headers))
    widths = column_widths(option_headers)
    for column, header in enumerate(headers, start=1):
        cell = ws.cell(row=1, column=column, value=header)
        cell.font = HEADER_FONT
        cell.fill = EDITABLE_FILL if is_editable(header, option_headers) else LOCKED_FILL
        cell.alignment = HEADER_ALIGN
        ws.column_dimensions[get_column_letter(column)].width = widths.get(header, 16)
    ws.row_dimensions[1].height = 26

    for row_index, question in enumerate(manifest["questions"], start=2):
        values = _question_row_values(question, option_headers)
        for column, header in enumerate(headers, start=1):
            cell = ws.cell(row=row_index, column=column, value=values.get(header))
            if isinstance(cell.value, str):
                cell.data_type = "s"  # 防 Excel 把 "=..." 当公式
            cell.font = BODY_FONT
            if header in WRAP_LEFT_HEADERS or header in option_headers:
                cell.alignment = WRAP_LEFT
            else:
                cell.alignment = CENTER_TOP
            if header == COL_GATE:
                cell.font = GATE_PASS_FONT if values.get(COL_GATE) == "PASS" else GATE_FAIL_FONT
            if header == COL_DECISION:
                cell.fill = DECISION_FILL
    last_row = len(manifest["questions"]) + 1
    ws.freeze_panes = "B2"
    ws.auto_filter.ref = f"A1:{get_column_letter(len(headers))}{last_row}"
    return last_row


def _add_decision_validation(ws, headers: list[str], last_row: int) -> None:
    if COL_DECISION not in headers or last_row < 2:
        return
    column = get_column_letter(headers.index(COL_DECISION) + 1)
    validation = DataValidation(
        type="list",
        formula1='"' + ",".join(DECISION_LABELS) + '"',
        allow_blank=True,
    )
    validation.showErrorMessage = True
    validation.errorTitle = "判定值非法"
    validation.error = "只能选择：" + " / ".join(DECISION_LABELS) + "（留空 = 未审核）"
    validation.promptTitle = "人工判定"
    validation.prompt = "四选一；留空表示尚未审核，将阻断入库。"
    ws.add_data_validation(validation)
    validation.add(f"{column}2:{column}{last_row}")


def _apply_protection(ws, *, unlock_headers: set[str] | None = None, headers: list[str] | None = None,
                      last_row: int = 1) -> None:
    """启用工作表保护（无密码，仅作护栏）。解锁指定的可编辑列。"""
    if unlock_headers is not None and headers is not None:
        for row in range(2, last_row + 1):
            for column, header in enumerate(headers, start=1):
                if header in unlock_headers:
                    ws.cell(row=row, column=column).protection = Protection(locked=False)
    protection = ws.protection
    protection.sheet = True
    for attribute in (
        "formatCells",
        "formatColumns",
        "formatRows",
        "insertRows",
        "insertColumns",
        "deleteRows",
        "deleteColumns",
        "sort",
        "autoFilter",
        "pivotTables",
        "selectLockedCells",
        "selectUnlockedCells",
    ):
        setattr(protection, attribute, False)


def _write_guide_sheet(ws) -> None:
    lines = [
        ("M5.5 P4-3.2 · 题目人工审核清单 —— 使用说明", True),
        ("", False),
        ("1. 本表由 scripts/p43_review_kit.py build 从 questions_manifest.json 生成。", False),
        ("2. 只有「深绿表头」的列可以修改：难度 / 题干 / 选项A… / 答案 / 解析 / 判定 / 审核备注。", False),
        ("   「浅蓝表头」为机器生成，已被工作表保护锁定（编号 / 知识点 / 知识域代码 / 门禁 / 门禁原因 / 建议）。", False),
        ("3. 「判定」为下拉框，四选一：", False),
        ("     通过        —— 内容无需改动，照原样入库。", False),
        ("     修改后通过  —— 就地改好内容（至少改动一个字段）后选它。", False),
        ("     驳回        —— 不采用此题。", False),
        ("     待定        —— 本轮不决定（不得入库）。", False),
        ("   留空 = 未审核 → 回收决定时会阻断，杜绝「没审就入库」。", False),
        ("4. 门禁列是 P4-3.1 的 G1–G8 质量门禁结论。对门禁 FAIL 的题选「通过 / 修改后通过」，", False),
        ("   必须在「审核备注」写明推翻理由（会记入 overridden_gates 供审计）。", False),
        ("   「提示：…」为**建议**（如「正确选项显著长于干扰项」），不影响 PASS/FAIL，无需推翻理由。", False),
        ("5. 审核要点（当前无教材 grounding，属模型先验出题，务必「实际解题」式复核）：", False),
        ("   · 题干是否只有一个正确答案？是否存在多解 / 关键条件缺失？", False),
        ("   · 选项是否同质可比？有没有明显错别字、幻觉事实、常识错误？", False),
        ("   · 解析是否真的解释了所选项、且与答案一致？", False),
        ("   · 难度标注与实际解题难度是否相符？", False),
        ("6. 改完保存为 .xlsx（文件名与工作表名保持不变），再跑 collect 回收决定。", False),
        ("7. 修订后系统会重跑结构门禁（G1/G2/G5/G6）：例如把选项改了却忘了同步答案，会被直接判错。", False),
    ]
    ws.column_dimensions["A"].width = 110
    for index, (text, is_title) in enumerate(lines, start=1):
        cell = ws.cell(row=index, column=1, value=text)
        cell.font = TITLE_FONT if is_title else BODY_FONT
        cell.alignment = Alignment(vertical="center", wrap_text=False)


def _write_batch_sheet(
    ws,
    manifest: dict[str, Any],
    *,
    built_at: str,
    manifest_sha: str,
    manifest_name: str,
) -> None:
    summary = manifest.get("summary") or {}
    pairs: list[tuple[str, Any]] = [
        ("批次", manifest.get("batch")),
        ("学科", manifest.get("subject")),
        ("manifest schema 版本", manifest.get("schema_version")),
        ("清单 schema 版本", SCHEMA_VERSION),
        ("manifest 生成时间", manifest.get("generated_at")),
        ("manifest 文件名", manifest_name),
        ("manifest SHA-256", manifest_sha),
        ("清单生成时间", built_at),
        ("候选题数", summary.get("candidates")),
        ("门禁通过", summary.get("passed")),
        ("门禁拒绝", summary.get("failed")),
        ("仅提示待留意", summary.get("needs_review")),
        ("生成失败 concept 数", summary.get("concepts_with_error")),
        ("命中门禁统计", json.dumps(summary.get("by_gate") or {}, ensure_ascii=False)),
        ("选项洗牌", options_shuffle_text(manifest)),
        (
            "批内答案位置分布",
            json.dumps((summary.get("answer_position") or {}).get("counts") or {}, ensure_ascii=False),
        ),
        ("批内答案分布提示", answer_distribution_text(manifest)),
        ("跨批查重参照数", summary.get("existing_references")),
    ]
    ws.column_dimensions["A"].width = 24
    ws.column_dimensions["B"].width = 76
    ws.cell(row=1, column=1, value="批信息 / 溯源").font = TITLE_FONT
    for index, (key, value) in enumerate(pairs, start=3):
        ws.cell(row=index, column=1, value=str(key)).font = Font(bold=True, size=10)
        ws.cell(row=index, column=2, value="" if value is None else str(value)).font = BODY_FONT

    errors = manifest.get("errors") or []
    block = len(pairs) + 5
    ws.cell(row=block, column=1, value="生成失败（该 concept 未产出任何候选题）").font = TITLE_FONT
    header_row = block + 1
    for column, name in enumerate(("知识点", "知识域代码", "原因"), start=1):
        cell = ws.cell(row=header_row, column=column, value=name)
        cell.font = HEADER_FONT
        cell.fill = LOCKED_FILL
        cell.alignment = HEADER_ALIGN
    if not errors:
        ws.cell(row=header_row + 1, column=1, value="（无）").font = BODY_FONT
    for offset, item in enumerate(errors, start=1):
        row_index = header_row + offset
        ws.cell(row=row_index, column=1, value=item.get("concept_name")).font = BODY_FONT
        ws.cell(row=row_index, column=2, value=item.get("code")).font = BODY_FONT
        reason_cell = ws.cell(row=row_index, column=3, value=item.get("reason"))
        reason_cell.font = BODY_FONT
        reason_cell.alignment = WRAP_LEFT

    config = manifest.get("gate_config") or {}
    config_block = header_row + max(len(errors), 1) + 3
    ws.cell(row=config_block, column=1, value="门禁阈值（manifest.gate_config 冻结值）").font = TITLE_FONT
    for column, name in enumerate(("字段", "冻结值"), start=1):
        cell = ws.cell(row=config_block + 1, column=column, value=name)
        cell.font = HEADER_FONT
        cell.fill = LOCKED_FILL
        cell.alignment = HEADER_ALIGN
    for offset, (key, value) in enumerate(sorted(config.items()), start=2):
        ws.cell(row=config_block + offset, column=1, value=key).font = BODY_FONT
        ws.cell(
            row=config_block + offset, column=2, value=json.dumps(value, ensure_ascii=False)
        ).font = BODY_FONT

    legend_row = config_block + len(config) + 3
    ws.cell(row=legend_row, column=1, value="门禁名称对照").font = TITLE_FONT
    for offset, (code, title) in enumerate(gates.GATE_TITLES.items(), start=1):
        ws.cell(row=legend_row + offset, column=1, value=code).font = BODY_FONT
        ws.cell(row=legend_row + offset, column=2, value=title).font = BODY_FONT


def build_workbook(
    manifest: dict[str, Any],
    *,
    lock: bool = True,
    built_at: str | None = None,
    manifest_sha: str = "",
    manifest_name: str = "",
) -> Workbook:
    """manifest → 审核清单工作簿（纯内存操作，不落盘）。"""
    questions = manifest.get("questions")
    if not isinstance(questions, list) or not questions:
        raise ReviewKitError("manifest 含 0 道候选题，无法生成审核清单")
    stamp = built_at or _now_iso()
    option_headers = option_headers_for(option_count_for(manifest))

    workbook = Workbook()
    checklist = workbook.active
    checklist.title = CHECKLIST_SHEET
    last_row = _write_checklist_sheet(checklist, manifest, option_headers)
    _add_decision_validation(checklist, ordered_headers(len(option_headers)), last_row)

    guide = workbook.create_sheet(GUIDE_SHEET)
    _write_guide_sheet(guide)
    batch = workbook.create_sheet(BATCH_SHEET)
    _write_batch_sheet(
        batch, manifest, built_at=stamp, manifest_sha=manifest_sha, manifest_name=manifest_name
    )

    workbook.properties.creator = TOOL_NAME
    workbook.properties.lastModifiedBy = TOOL_NAME
    workbook.properties.created = _parse_time(stamp)
    workbook.properties.modified = _parse_time(stamp)

    if lock:
        headers = ordered_headers(len(option_headers))
        editable = {header for header in headers if is_editable(header, option_headers)}
        _apply_protection(
            checklist, unlock_headers=editable, headers=headers, last_row=last_row
        )
        _apply_protection(guide)
        _apply_protection(batch)
    return workbook


# ---------------------------------------------------------------------------
# collect：审核清单 → 审核决定
# ---------------------------------------------------------------------------
def read_checklist(path: Path) -> tuple[list[str], list[dict[str, Any]], dict[str, str]]:
    """读回审核清单：返回 (表头, 数据行, 批信息 key→value)。"""
    try:
        workbook = load_workbook(path)
    except Exception as exc:  # 文件解析边界：非 xlsx / 损坏一律转成可读错误
        raise ReviewKitError(f"无法读取审核清单（非 xlsx 或文件损坏）：{exc}") from exc
    if CHECKLIST_SHEET not in workbook.sheetnames:
        raise ReviewKitError(f"审核清单缺少工作表「{CHECKLIST_SHEET}」")
    sheet = workbook[CHECKLIST_SHEET]
    raw_rows = list(sheet.iter_rows(values_only=True))
    if not raw_rows:
        raise ReviewKitError("审核清单为空表（连表头都没有）")
    headers = [_norm_cell(value) for value in raw_rows[0]]
    while headers and not headers[-1]:
        headers.pop()
    rows: list[dict[str, Any]] = []
    for offset, raw in enumerate(raw_rows[1:], start=2):
        record = {
            header: (raw[index] if index < len(raw) else None)
            for index, header in enumerate(headers)
        }
        if not any(_norm_cell(value) for value in record.values()):
            continue
        record[ROW_KEY] = offset
        rows.append(record)
    return headers, rows, _read_batch_meta(workbook)


def _read_batch_meta(workbook) -> dict[str, str]:
    if BATCH_SHEET not in workbook.sheetnames:
        return {}
    meta: dict[str, str] = {}
    for row in workbook[BATCH_SHEET].iter_rows(values_only=True, max_col=2):
        key = _norm_cell(row[0] if row else None)
        value = _norm_cell(row[1] if row and len(row) > 1 else None)
        if key and value and key not in meta:
            meta[key] = value
    return meta


def _option_values(row: dict[str, Any], option_headers: list[str]) -> tuple[list[str], bool]:
    """取选项列（去尾部空列）。返回 (选项, 是否存在中间空档)。"""
    values = [_norm_cell(row.get(header)) for header in option_headers]
    while values and not values[-1]:
        values.pop()
    return values, any(not value for value in values)


def _err(sheet_row, question_id, code: str, reason: str, severity: str = "error") -> dict[str, Any]:
    return {
        "sheet_row": sheet_row,
        "question_id": question_id,
        "code": code,
        "severity": severity,
        "reason": reason,
    }


def _evaluate_row(
    manifest: dict[str, Any],
    question: dict[str, Any],
    row: dict[str, Any],
    option_headers: list[str],
    sheet_row: Any,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    qid = question.get("question_id")
    quality = question.get("quality_check") or {}
    gate_passed = bool(quality.get("passed"))
    label = _norm_cell(row.get(COL_DECISION))
    note = _norm_cell(row.get(COL_NOTE))
    errors: list[dict[str, Any]] = []

    options, option_gap = _option_values(row, option_headers)
    final = {
        "stem": _norm_cell(row.get(COL_STEM)),
        "options": options,
        "answer": _norm_cell(row.get(COL_ANSWER)),
        "analysis": _norm_cell(row.get(COL_ANALYSIS)),
        "difficulty": _norm_cell(row.get(COL_DIFFICULTY)),
    }
    original = {
        "stem": _norm_cell(question.get("stem")),
        "options": [_norm_cell(item) for item in (question.get("options") or [])],
        "answer": _norm_cell(question.get("answer")),
        "analysis": _norm_cell(question.get("analysis")),
        "difficulty": _norm_cell(question.get("difficulty")),
    }
    revision_diff: list[dict[str, Any]] = []
    for field in ("stem", "answer", "analysis", "difficulty"):
        if final[field] != original[field]:
            revision_diff.append({"field": field, "before": original[field], "after": final[field]})
    if final["options"] != original["options"]:
        revision_diff.append(
            {"field": "options", "before": original["options"], "after": final["options"]}
        )
    changed_fields = [item["field"] for item in revision_diff]

    if option_gap:
        errors.append(_err(sheet_row, qid, "E08", "选项列存在空档（中间选项为空但后面仍有内容）"))

    key: str | None
    if not label:
        errors.append(_err(sheet_row, qid, "E01", "未审核（判定为空）"))
        key = None
    elif label not in DECISION_TO_KEY:
        errors.append(
            _err(sheet_row, qid, "E02", f"判定值「{label}」非法，仅允许：{' / '.join(DECISION_LABELS)}")
        )
        key = None
    else:
        key = DECISION_TO_KEY[label]

    revised_gate_check: dict[str, Any] | None = None
    overridden_gates: list[str] = []
    if key in {"approve", "revise"} and not gate_passed:
        overridden_gates = sorted(
            gate
            for gate, item in (quality.get("gates") or {}).items()
            if item.get("passed") is False
        )
        if not note:
            errors.append(
                _err(
                    sheet_row,
                    qid,
                    "E03",
                    f"该题未通过质量门禁（{'、'.join(overridden_gates) or '未知'}），"
                    f"判定为「{label}」必须在「审核备注」写明推翻理由",
                )
            )

    if key == "approve":
        if revision_diff:
            errors.append(
                _err(sheet_row, qid, "E04", "判定为「通过」但内容已被改动；请改用「修改后通过」")
            )
    elif key == "revise":
        if not revision_diff:
            errors.append(_err(sheet_row, qid, "E05", "判定为「修改后通过」但未改动任何字段"))
        else:
            revised_question = {
                **final,
                "question_type": question.get("question_type") or "choice",
                "knowledge_point": question.get("knowledge_point_name"),
                "subject": manifest.get("subject"),
            }
            verdict = gates.evaluate(
                revised_question,
                expected_concept_name=question.get("knowledge_point_name"),
                expected_subject=str(manifest.get("subject") or ""),
                raw_analysis=final["analysis"],
            )
            gate_map = verdict["gates"]
            revised_gate_check = {
                "passed": verdict["passed"],
                "reasons": verdict["reasons"],
                "warnings": verdict["warnings"],
                "gates": {
                    code: {
                        "passed": item["passed"],
                        "severity": item.get("severity"),
                        "reason": item.get("reason"),
                    }
                    for code, item in gate_map.items()
                },
            }
            broken = [code for code in REVISION_BLOCKING_GATES if not gate_map[code]["passed"]]
            if broken:
                detail = "；".join(gate_map[code]["reason"] for code in broken if gate_map[code].get("reason"))
                errors.append(
                    _err(sheet_row, qid, "E06", f"修订后未通过结构门禁 {'/'.join(broken)}：{detail}")
                )
            for code in REVISION_ADVISORY_GATES:
                if not gate_map[code]["passed"]:
                    errors.append(
                        _err(
                            sheet_row,
                            qid,
                            "E07",
                            f"修订后 {code} 提示：{gate_map[code]['reason']}",
                            severity="warning",
                        )
                    )
            # 门禁**内部**的提示（severity='warning'，如 G5 长度均衡）同样入告警、不阻断。
            for code, item in gate_map.items():
                if item.get("severity") == "warning" and item.get("reason"):
                    errors.append(
                        _err(sheet_row, qid, "E07", f"修订后 {code} 提示：{item['reason']}", severity="warning")
                    )
    elif key in {"reject", "defer"} and revision_diff:
        errors.append(
            _err(
                sheet_row,
                qid,
                "E09",
                f"判定为「{label}」但内容已被改动；如需保留修订请改用「{DECISION_REVISE}」",
            )
        )

    blocked = any(item["severity"] == "error" for item in errors)
    record = {
        "question_id": qid,
        "sheet_row": sheet_row,
        "knowledge_point_name": question.get("knowledge_point_name"),
        "knowledge_point_code": question.get("knowledge_point_code"),
        "gate_passed": gate_passed,
        "gate_reasons": quality.get("reasons") or [],
        "suggested_action": question.get("suggested_action"),
        "decision_label": label or None,
        "decision": key,
        "note": note,
        "changed_fields": changed_fields,
        "revision_diff": revision_diff,
        "overridden_gates": overridden_gates,
        "revised_gate_check": revised_gate_check,
        "final": final,
        "original": original,
        "apply_hint": APPLY_HINT.get(key or ""),
        "ready_for_apply": key in {"approve", "revise"} and not blocked,
        "errors": [item for item in errors if item["severity"] == "error"],
        "warnings": [item for item in errors if item["severity"] == "warning"],
    }
    return record, errors


def collect_decisions(
    manifest: dict[str, Any],
    headers: list[str],
    rows: list[dict[str, Any]],
    *,
    expected_sha: str | None = None,
    actual_sha: str | None = None,
    existing: list[dict[str, Any]] | None = None,
    collected_at: str | None = None,
    manifest_name: str = "",
    checklist_name: str = "",
) -> dict[str, Any]:
    """审核清单数据 + manifest → 审核决定（纯逻辑，不读写文件）。"""
    index = {header: position for position, header in enumerate(headers)}
    required = {COL_QID, COL_DIFFICULTY, COL_STEM, COL_ANSWER, COL_ANALYSIS, COL_DECISION}
    missing = sorted(required - set(index))
    if missing:
        raise ReviewKitError(f"审核清单缺少必需列 {missing}，请用 build 重新生成本表")
    option_headers = [header for header in headers if _OPTION_HEADER_RE.match(header)]
    if not option_headers:
        raise ReviewKitError("审核清单缺少选项列（选项A/选项B…）")

    errors: list[dict[str, Any]] = []
    if expected_sha and actual_sha and expected_sha != actual_sha:
        errors.append(
            _err(
                None,
                None,
                "E00",
                "审核清单记录的 manifest 指纹与本次提供的 manifest 不一致"
                f"（清单 {expected_sha[:12]}… vs 传入 {actual_sha[:12]}…）",
            )
        )

    questions = {str(item.get("question_id")): item for item in manifest.get("questions") or []}
    records: list[dict[str, Any]] = []
    seen: list[str] = []
    for row in rows:
        qid = _norm_cell(row.get(COL_QID))
        sheet_row = row.get(ROW_KEY)
        if not qid:
            errors.append(_err(sheet_row, None, "E13", "该行有内容但「编号」为空，无法定位题目"))
            continue
        if qid in seen:
            errors.append(_err(sheet_row, qid, "E11", f"编号 {qid} 重复出现"))
            continue
        seen.append(qid)
        question = questions.get(qid)
        if question is None:
            errors.append(
                _err(sheet_row, qid, "E10", f"编号 {qid} 不在本批 manifest 中（清单与 manifest 不匹配）")
            )
            continue
        record, row_errors = _evaluate_row(manifest, question, row, option_headers, sheet_row)
        records.append(record)
        errors.extend(row_errors)

    for qid in questions:
        if qid not in seen:
            errors.append(_err(None, qid, "E12", f"manifest 中的 {qid} 未出现在审核清单中"))

    # 最后一道门：对可入库题的**最终内容**重跑查重（现有题库 ∪ 彼此，先到先得）。
    references = [
        gates.build_reference(f"existing:{item.get('id')}", item.get("stem") or "")
        for item in (existing or [])
    ]
    for record in records:
        if not record["ready_for_apply"]:
            continue
        verdict = gates.gate_g4_duplicate({"stem": record["final"]["stem"]}, references)
        if not verdict["passed"]:
            reason = f"{verdict['reason']}（最终内容查重）"
            errors.append(_err(record["sheet_row"], record["question_id"], "E20", reason))
            record["errors"].append(_err(record["sheet_row"], record["question_id"], "E20", reason))
            record["ready_for_apply"] = False
        references.append(
            gates.build_reference(record["question_id"], record["final"]["stem"])
        )

    blockers = [item for item in errors if item["severity"] == "error"]
    warnings = [item for item in errors if item["severity"] == "warning"]
    counts = {"approve": 0, "revise": 0, "reject": 0, "defer": 0, "unreviewed": 0}
    for record in records:
        decision = record["decision"]
        counts[decision if decision in counts else "unreviewed"] += 1

    return {
        "schema_version": SCHEMA_VERSION,
        "tool": TOOL_NAME,
        "collected_at": collected_at or _now_iso(),
        "subject": manifest.get("subject"),
        "batch": manifest.get("batch"),
        "manifest": {
            "schema_version": manifest.get("schema_version"),
            "generated_at": manifest.get("generated_at"),
            "file": manifest_name,
            "sha256": actual_sha,
            "recorded_sha256": expected_sha,
        },
        "checklist": {"file": checklist_name},
        "summary": {
            "questions": len(records),
            "expected": len(questions),
            "approve": counts["approve"],
            "revise": counts["revise"],
            "reject": counts["reject"],
            "defer": counts["defer"],
            "unreviewed": counts["unreviewed"],
            "ready_for_apply": sum(1 for record in records if record["ready_for_apply"]),
            "blocking": len(blockers),
            "warnings": len(warnings),
        },
        "decisions": records,
        "errors": errors,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="p43_review_kit",
        description="M5.5 P4-3.2 人工审核工作流：manifest ⇄ Excel 审核清单 ⇄ 审核决定",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    build = sub.add_parser("build", help="manifest → 审核清单 xlsx")
    build.add_argument("--manifest", required=True, type=Path, help="P4-3.1 产出的 manifest JSON")
    build.add_argument("--out", required=True, type=Path, help="审核清单 xlsx 输出路径")
    build.add_argument("--built-at", default=None, help="清单生成时间（默认当前 UTC）")
    build.add_argument("--no-lock", action="store_true", help="不启用工作表保护（默认启用）")

    collect = sub.add_parser("collect", help="审核清单 xlsx → 审核决定 json")
    collect.add_argument("--checklist", required=True, type=Path, help="人工填好的审核清单 xlsx")
    collect.add_argument("--manifest", required=True, type=Path, help="同批 manifest JSON（diff 基线）")
    collect.add_argument("--out", required=True, type=Path, help="审核决定 json 输出路径")
    collect.add_argument("--existing", type=Path, default=None, help="现有题面快照（最终查重参照）")
    collect.add_argument("--collected-at", default=None, help="回收时间（默认当前 UTC）")
    return parser.parse_args(argv)


def load_existing(path: Path | None) -> list[dict[str, Any]]:
    if path is None:
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("questions") if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        raise ReviewKitError('existing 快照必须是数组或 {"questions": [...]}')
    return [
        {"id": row.get("id"), "stem": str(row.get("stem") or "")}
        for row in rows
        if isinstance(row, dict) and str(row.get("stem") or "").strip()
    ]


def _cmd_build(args: argparse.Namespace) -> int:
    try:
        manifest = load_manifest(args.manifest)
    except FileNotFoundError as exc:
        print(f"用法错误：{exc}", file=sys.stderr)
        return 2
    except ReviewKitError as exc:
        print(f"运行失败：{exc}", file=sys.stderr)
        return 3
    try:
        workbook = build_workbook(
            manifest,
            lock=not args.no_lock,
            built_at=args.built_at,
            manifest_sha=sha256_file(args.manifest),
            manifest_name=args.manifest.name,
        )
        args.out.parent.mkdir(parents=True, exist_ok=True)
        save_workbook(workbook, args.out)
    except ReviewKitError as exc:
        print(f"运行失败：{exc}", file=sys.stderr)
        return 3
    summary = manifest.get("summary") or {}
    print("=" * 62)
    print(f"审核清单已写出：{args.out}")
    print(
        f"batch={manifest.get('batch')}  subject={manifest.get('subject')}  "
        f"候选题={summary.get('candidates')}  门禁通过={summary.get('passed')}  "
        f"拒绝={summary.get('failed')}"
    )
    print(f"工作表：{CHECKLIST_SHEET} / {GUIDE_SHEET} / {BATCH_SHEET}    列保护：{'开' if not args.no_lock else '关'}")
    print("=" * 62)
    return 0


def _cmd_collect(args: argparse.Namespace) -> int:
    try:
        manifest = load_manifest(args.manifest)
        existing = load_existing(args.existing)
    except FileNotFoundError as exc:
        print(f"用法错误：{exc}", file=sys.stderr)
        return 2
    except (ReviewKitError, json.JSONDecodeError) as exc:
        print(f"运行失败：{exc}", file=sys.stderr)
        return 3
    try:
        headers, rows, meta = read_checklist(args.checklist)
    except (FileNotFoundError, ReviewKitError) as exc:
        print(f"运行失败：无法读取审核清单：{exc}", file=sys.stderr)
        return 3

    try:
        decisions = collect_decisions(
            manifest,
            headers,
            rows,
            expected_sha=meta.get("manifest SHA-256"),
            actual_sha=sha256_file(args.manifest),
            existing=existing,
            collected_at=args.collected_at,
            manifest_name=args.manifest.name,
            checklist_name=args.checklist.name,
        )
    except ReviewKitError as exc:
        print(f"运行失败：{exc}", file=sys.stderr)
        return 3

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(decisions, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    summary = decisions["summary"]
    print("=" * 62)
    print(f"审核决定已写出：{args.out}")
    print(
        f"候选题={summary['questions']}  通过={summary['approve']}  修改后通过={summary['revise']}  "
        f"驳回={summary['reject']}  待定={summary['defer']}  未审核={summary['unreviewed']}"
    )
    print(f"可入库={summary['ready_for_apply']}  阻断问题={summary['blocking']}  提示={summary['warnings']}")
    for item in decisions["errors"]:
        marker = "ERROR" if item["severity"] == "error" else "WARN "
        print(f"  [{marker}] {item['code']} {item.get('question_id') or '-'}：{item['reason']}")
    print("=" * 62)
    if summary["blocking"]:
        print("存在阻断问题：请修正审核清单后重跑 collect。", file=sys.stderr)
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    _utf8_stdout()
    args = parse_args(argv)
    if args.command == "build":
        return _cmd_build(args)
    return _cmd_collect(args)


if __name__ == "__main__":
    raise SystemExit(main())
