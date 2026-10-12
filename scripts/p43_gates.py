"""M5.5 P4-3.1 —— AI 题目质量门禁（纯函数，零依赖）。

职责单一：把「候选题」按 **G1–G8 确定性规则**判成 pass / fail，产出可供人工
清单审核的判定明细。**不判「好不好」** —— 好与不好由人工终审（KMLE 原则：
AI 自评永不可替代专家评审）。

为什么这样切：

  - **不 import app、不联网、不读库、不写库、无全局状态**
    → 可被 pytest 直接用 ``importlib`` 加载（范式同
    ``tests/test_deployment_flow.py`` 加载 ``scripts/check_runtime_storage.py``）。
  - 门禁是**确定性规则集**，不是"看起来像题"的主观判断：答案必须能与选项
    对齐、解析必须够长且未被自动补全、近似题必须被相似度拦住。
  - 只服务「生成 → 门禁 → 待审核」三段中的第二段；**不写库、不发布**。

阈值来源：``docs/M5.5_P4-3.1_AI题目生成管道设计.md`` §4.2（G1–G8 规格表）。
上游依据：``docs/M5.5_P4-3_题目供给设计方案.md`` §3.2。
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence
from typing import Any

# ---------------------------------------------------------------------------
# G1–G8 阈值（冻结值；改动必须同步更新设计文档 §4.2 与本模块 docstring）
# ---------------------------------------------------------------------------
MIN_STEM_CHARS = 12
MAX_STEM_CHARS = 400
MIN_ANALYSIS_CHARS = 60

# `question_generator._ensure_analysis()` 对 <40 字解析自动追加的提示前缀。
# 只要出现它，就说明解析"原始长度不足、被补全过" → 长度信号不可信 → 直接拒。
ANALYSIS_FILLER_FINGERPRINT = "复习提示：请结合"

# `ai_gateway._offline_reply()` 的模板指纹（无 Key 与请求异常两条静默降级路径）。
OFFLINE_FINGERPRINTS = ("离线降级响应", "配置模型 API Key")

DUP_JACCARD_THRESHOLD = 0.80
SHINGLE_SIZE = 3

CHOICE_MIN_OPTIONS = 2
CHOICE_MAX_OPTIONS = 6
OPTION_LENGTH_RATIO_MAX = 2.5
ANSWER_POSITION_MIN_SHARE = 0.20
ANSWER_POSITION_MAX_SHARE = 0.30
# 批内答案位置分布只在样本量够大时才作为**阻断**规则，否则仅作提示。
ANSWER_POSITION_MIN_SAMPLE = 20
# 4 个字母各占 20%~30% ⇒ 至少要用满 4 个不同字母。
ANSWER_POSITION_MIN_LETTERS = 4

VALID_QUESTION_TYPES = ("choice", "fill", "short_answer")
VALID_DIFFICULTIES = ("easy", "medium", "hard")

# KMLE 校验清单：「禁用全选/全不选」「选项同质」。
BANNED_OPTION_PATTERNS = (
    "以上都",
    "以上均",
    "以上皆是",
    "全选",
    "全不选",
    "都不对",
    "都正确",
    "全部正确",
)

GATE_ORDER = ("G1", "G2", "G3", "G4", "G5", "G6", "G7")
GATE_TITLES = {
    "G1": "结构完整性",
    "G2": "答案可对齐",
    "G3": "解析原始质量",
    "G4": "重复检测",
    "G5": "选项质量",
    "G5B": "批内答案位置分布",
    "G6": "元数据完备",
    "G7": "学科一致",
    "G8": "离线降级判定",
}

# 归一化时剔除的字符：空白 + 常见中英标点（NFKC 之后全角已折半角）。
_PUNCT_RE = re.compile(
    r"[\s\u3000，。、；：？！“”‘’（）《》〈〉【】〔〕…—－ー~～\-_/\\|,.!?;:'\"`()\[\]{}<>+=*&^%$#@]"
)
_OPTION_LETTER_RE = re.compile(r"^([A-Za-z])\s*[.、\)．:：]?\s*")


# ---------------------------------------------------------------------------
# 文本工具
# ---------------------------------------------------------------------------
def normalize_text(text: Any) -> str:
    """归一化：NFKC（全角→半角）+ 小写 + 去空白与标点。用于精确查重与比对。"""
    normalized = unicodedata.normalize("NFKC", str(text or "")).lower()
    return _PUNCT_RE.sub("", normalized)


def shingle_set(text: Any, size: int = SHINGLE_SIZE) -> frozenset[str]:
    """字符 n-gram 集合（近似去重用）。"""
    normalized = normalize_text(text)
    if not normalized:
        return frozenset()
    if len(normalized) < size:
        return frozenset({normalized})
    return frozenset(normalized[i : i + size] for i in range(len(normalized) - size + 1))


def jaccard(a: frozenset[str] | set[str], b: frozenset[str] | set[str]) -> float:
    """Jaccard 相似度；任一为空则 0.0（空集不参与比较，避免假命中）。"""
    if not a or not b:
        return 0.0
    union = len(a | b)
    if not union:
        return 0.0
    return len(a & b) / union


def option_letter(text: Any) -> str | None:
    """取选项/答案的前导字母（``"B. xxx"`` → ``"B"``，``"栈"`` → ``None``）。"""
    match = _OPTION_LETTER_RE.match(unicodedata.normalize("NFKC", str(text or "")).strip())
    return match.group(1).upper() if match else None


def option_body(text: Any) -> str:
    """取选项正文（去掉前导 ``"B."`` 之类），用于长度偏差判定。"""
    stripped = str(text or "").strip()
    match = _OPTION_LETTER_RE.match(unicodedata.normalize("NFKC", stripped))
    return (stripped[match.end() :] if match else stripped).strip()


def _fail(gate: str, reason: str, **meta: Any) -> dict[str, Any]:
    return {"gate": gate, "title": GATE_TITLES[gate], "passed": False, "reason": reason, **meta}


def _pass(gate: str, **meta: Any) -> dict[str, Any]:
    return {"gate": gate, "title": GATE_TITLES[gate], "passed": True, "reason": None, **meta}


def _options(question: dict[str, Any]) -> list[str]:
    raw = question.get("options")
    if isinstance(raw, list):
        return [str(item).strip() for item in raw if str(item).strip()]
    return []


def _question_type(question: dict[str, Any]) -> str:
    return str(question.get("question_type") or "choice").strip() or "choice"


# ---------------------------------------------------------------------------
# G1–G7：单题门禁
# ---------------------------------------------------------------------------
def gate_g1_structure(question: dict[str, Any]) -> dict[str, Any]:
    """G1 结构完整性：题干长度、答案非空、题型合法、选择题选项数。"""
    stem = str(question.get("stem") or "").strip()
    if not stem:
        return _fail("G1", "题干为空")
    length = len(stem)
    if not (MIN_STEM_CHARS <= length <= MAX_STEM_CHARS):
        return _fail("G1", f"题干长度 {length} 不在 [{MIN_STEM_CHARS}, {MAX_STEM_CHARS}]")
    if not str(question.get("answer") or "").strip():
        return _fail("G1", "答案为空")
    qtype = _question_type(question)
    if qtype not in VALID_QUESTION_TYPES:
        return _fail("G1", f"题型非法：{qtype}")
    if qtype == "choice":
        count = len(_options(question))
        if not (CHOICE_MIN_OPTIONS <= count <= CHOICE_MAX_OPTIONS):
            return _fail(
                "G1", f"选择题选项数 {count} 不在 [{CHOICE_MIN_OPTIONS}, {CHOICE_MAX_OPTIONS}]"
            )
    return _pass("G1")


def gate_g2_answer_alignment(question: dict[str, Any]) -> dict[str, Any]:
    """G2 答案可对齐：选择题答案首字母必须落在选项首字母集合内。"""
    if _question_type(question) != "choice":
        return _pass("G2", skipped="非选择题，跳过答案对齐")
    letters = {letter for letter in (option_letter(opt) for opt in _options(question)) if letter}
    if not letters:
        return _fail("G2", "选项无字母前缀，无法对齐答案")
    answer_letter = option_letter(question.get("answer"))
    if answer_letter is None:
        answer = str(question.get("answer") or "").strip()
        return _fail("G2", f"答案「{answer[:20]}」不以选项字母开头")
    if answer_letter not in letters:
        return _fail("G2", f"答案字母 {answer_letter} 不在选项 {sorted(letters)} 内")
    return _pass("G2", answer_letter=answer_letter)


def gate_g3_analysis_quality(
    question: dict[str, Any], raw_analysis: str | None = None
) -> dict[str, Any]:
    """G3 解析原始质量：**读原始** ``analysis``（``_ensure_analysis`` 之前）。

    长度 ≥ ``MIN_ANALYSIS_CHARS`` 且不含补全指纹。补全指纹优先判定 —— 它证明
    该解析的原始长度不足、长度信号已被污染。
    """
    text = str(raw_analysis if raw_analysis is not None else question.get("analysis") or "").strip()
    if ANALYSIS_FILLER_FINGERPRINT in text:
        return _fail("G3", f"解析含自动补全指纹「{ANALYSIS_FILLER_FINGERPRINT}」")
    length = len(text)
    if length < MIN_ANALYSIS_CHARS:
        return _fail("G3", f"解析原始长度 {length} < {MIN_ANALYSIS_CHARS}")
    return _pass("G3", raw_analysis_chars=length)


def gate_g4_duplicate(
    question: dict[str, Any], references: Sequence[dict[str, Any]]
) -> dict[str, Any]:
    """G4 重复检测：① 归一化精确比对；② 字符 3-gram Jaccard ≥ 0.80。

    ``references`` 为 ``[{"id": label, "normalized": str, "shingles": frozenset}]``；
    比对范围由调用方给出（现有题库 ∪ 同批在前的候选题）。
    """
    normalized = normalize_text(question.get("stem"))
    if not normalized:
        return _fail("G4", "题干归一化后为空，无法查重")
    shingles = shingle_set(question.get("stem"))
    for reference in references:
        if normalized == reference.get("normalized"):
            return _fail("G4", f"与 {reference['id']} 归一化后完全重复", duplicate_of=reference["id"])
        score = jaccard(shingles, reference.get("shingles") or frozenset())
        if score >= DUP_JACCARD_THRESHOLD:
            return _fail(
                "G4",
                f"与 {reference['id']} 相似度 {score:.2f} ≥ {DUP_JACCARD_THRESHOLD}",
                duplicate_of=reference["id"],
                similarity=round(score, 4),
            )
    return _pass("G4")


def gate_g5_option_quality(question: dict[str, Any]) -> dict[str, Any]:
    """G5 选项质量：① 禁用「以上都对/全不选」类选项；② 选项长度极差比 ≤ 2.5。"""
    if _question_type(question) != "choice":
        return _pass("G5", skipped="非选择题，跳过选项质量")
    options = _options(question)
    for option in options:
        for pattern in BANNED_OPTION_PATTERNS:
            if pattern in option:
                return _fail("G5", f"选项含禁用表述「{pattern}」")
    bodies = [option_body(option) for option in options]
    if any(not body for body in bodies):
        return _fail("G5", "存在空选项")
    lengths = [len(body) for body in bodies]
    shortest, longest = min(lengths), max(lengths)
    ratio = longest / shortest
    if ratio > OPTION_LENGTH_RATIO_MAX:
        return _fail(
            "G5",
            f"选项长度极差比 {ratio:.2f} > {OPTION_LENGTH_RATIO_MAX}（{shortest}~{longest} 字）",
        )
    return _pass("G5", option_length_ratio=round(ratio, 4))


def gate_g6_metadata(
    question: dict[str, Any], expected_concept_name: str | None = None
) -> dict[str, Any]:
    """G6 元数据完备：``knowledge_point`` 必须是本批目标 concept 名；``difficulty`` 合法且非空。"""
    declared = str(question.get("knowledge_point") or "").strip()
    if not declared:
        return _fail("G6", "knowledge_point 为空")
    if expected_concept_name and normalize_text(declared) != normalize_text(expected_concept_name):
        return _fail(
            "G6",
            f"knowledge_point「{declared}」与本批目标 concept「{expected_concept_name}」不一致",
        )
    difficulty = question.get("difficulty")
    if difficulty is None or str(difficulty).strip() == "":
        return _fail("G6", "difficulty 为 NULL（禁止依赖题型兜底映射）")
    if str(difficulty).strip() not in VALID_DIFFICULTIES:
        return _fail("G6", f"difficulty 非法：{difficulty}")
    return _pass("G6")


def gate_g7_subject(question: dict[str, Any], expected_subject: str) -> dict[str, Any]:
    """G7 学科一致（节点类型恒为 concept 由 Apply 阶段的 ``attach()`` 保证）。"""
    declared = str(question.get("subject") or "").strip()
    if not declared:
        return _fail("G7", "subject 为空")
    if normalize_text(declared) != normalize_text(expected_subject):
        return _fail("G7", f"subject「{declared}」与本批学科「{expected_subject}」不一致")
    return _pass("G7", node_type="concept", enforced_by="attach()")


# ---------------------------------------------------------------------------
# G8：离线降级判定（作用于**原始响应文本**，不是解析后的对象）
# ---------------------------------------------------------------------------
def detect_offline(raw_text: str | None) -> bool:
    """G8：原始响应是否命中离线降级模板。禁止把 0 题当正常结果静默跳过。"""
    text = str(raw_text or "")
    return any(fingerprint in text for fingerprint in OFFLINE_FINGERPRINTS)


def offline_reason(raw_text: str | None) -> str | None:
    if raw_text is None:
        return None
    if not str(raw_text).strip():
        return "G8 原始响应为空"
    if detect_offline(raw_text):
        return "G8 AI 网关离线降级（无 Key 或请求异常），非真实生成结果"
    return None


# ---------------------------------------------------------------------------
# G5B：批内答案位置分布（batch 级）
# ---------------------------------------------------------------------------
def answer_letter_counts(questions: Sequence[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for question in questions:
        if _question_type(question) != "choice":
            continue
        letter = option_letter(question.get("answer"))
        if letter:
            counts[letter] = counts.get(letter, 0) + 1
    return counts


def evaluate_answer_distribution(counts: dict[str, int]) -> dict[str, Any]:
    """批内答案位置分布：字母占比须落在 [20%, 30%]，且用满 ≥4 个字母。

    样本量 < ``ANSWER_POSITION_MIN_SAMPLE`` 时只作提示（``blocking=False``）。
    """
    total = sum(counts.values())
    if total == 0:
        return {
            "gate": "G5B",
            "title": GATE_TITLES["G5B"],
            "passed": True,
            "blocking": False,
            "reason": "无选择题，跳过",
            "counts": {},
            "shares": {},
            "offenders": [],
        }
    shares = {letter: count / total for letter, count in sorted(counts.items())}
    blocking = total >= ANSWER_POSITION_MIN_SAMPLE
    offenders = sorted(
        letter
        for letter, share in shares.items()
        if share < ANSWER_POSITION_MIN_SHARE or share > ANSWER_POSITION_MAX_SHARE
    )
    too_few_letters = blocking and len(counts) < ANSWER_POSITION_MIN_LETTERS
    passed = not offenders and not too_few_letters
    if passed:
        reason = None
    elif too_few_letters:
        reason = f"仅使用 {len(counts)} 个字母，少于 {ANSWER_POSITION_MIN_LETTERS} 个"
    else:
        detail = "、".join(
            f"{letter}={shares[letter]:.0%}" for letter in offenders
        )
        reason = f"占比越界（要求 {ANSWER_POSITION_MIN_SHARE:.0%}~{ANSWER_POSITION_MAX_SHARE:.0%}）：{detail}"
    return {
        "gate": "G5B",
        "title": GATE_TITLES["G5B"],
        "passed": passed,
        "blocking": blocking,
        "reason": reason,
        "counts": counts,
        "shares": {letter: round(share, 4) for letter, share in shares.items()},
        "offenders": offenders,
    }


# ---------------------------------------------------------------------------
# 单题总评
# ---------------------------------------------------------------------------
def evaluate(
    question: dict[str, Any],
    *,
    expected_concept_name: str | None = None,
    expected_subject: str,
    raw_analysis: str | None = None,
    references: Sequence[dict[str, Any]] = (),
) -> dict[str, Any]:
    """跑 G1–G7，返回 ``{"passed", "gates", "reasons", "duplicate_of"}``。"""
    results = [
        gate_g1_structure(question),
        gate_g2_answer_alignment(question),
        gate_g3_analysis_quality(question, raw_analysis=raw_analysis),
        gate_g4_duplicate(question, references),
        gate_g5_option_quality(question),
        gate_g6_metadata(question, expected_concept_name),
        gate_g7_subject(question, expected_subject),
    ]
    reasons = [item["reason"] for item in results if not item["passed"] and item.get("reason")]
    duplicate_of = next(
        (item.get("duplicate_of") for item in results if item.get("duplicate_of")), None
    )
    return {
        "passed": not reasons,
        "gates": {item["gate"]: item for item in results},
        "reasons": reasons,
        "duplicate_of": duplicate_of,
    }


# ---------------------------------------------------------------------------
# manifest 组装
# ---------------------------------------------------------------------------
def build_reference(label: str, stem: str) -> dict[str, Any]:
    """构造一条查重参照（现有题库题面 / 同批在前的候选题）。"""
    return {
        "id": label,
        "normalized": normalize_text(stem),
        "shingles": shingle_set(stem),
    }


def gate_config() -> dict[str, Any]:
    """把阈值整体冻结进 manifest，便于日后审计"当时用的是哪套阈值"。"""
    return {
        "min_stem_chars": MIN_STEM_CHARS,
        "max_stem_chars": MAX_STEM_CHARS,
        "min_analysis_chars": MIN_ANALYSIS_CHARS,
        "analysis_filler_fingerprint": ANALYSIS_FILLER_FINGERPRINT,
        "offline_fingerprints": list(OFFLINE_FINGERPRINTS),
        "dup_jaccard_threshold": DUP_JACCARD_THRESHOLD,
        "shingle_size": SHINGLE_SIZE,
        "choice_options_range": [CHOICE_MIN_OPTIONS, CHOICE_MAX_OPTIONS],
        "option_length_ratio_max": OPTION_LENGTH_RATIO_MAX,
        "answer_position_share_range": [ANSWER_POSITION_MIN_SHARE, ANSWER_POSITION_MAX_SHARE],
        "answer_position_min_sample": ANSWER_POSITION_MIN_SAMPLE,
        "answer_position_min_letters": ANSWER_POSITION_MIN_LETTERS,
        "banned_option_patterns": list(BANNED_OPTION_PATTERNS),
        "valid_difficulties": list(VALID_DIFFICULTIES),
    }


def assemble_manifest(
    *,
    subject: str,
    entries: Sequence[dict[str, Any]],
    existing_questions: Sequence[dict[str, Any]] = (),
    generated_at: str,
    batch: int = 1,
    id_prefix: str = "P43",
) -> dict[str, Any]:
    """把「每 concept 一批归一化后的候选题」组装成 manifest（**纯函数**）。

    ``entries`` 结构::

        {"concept": {"id": 19, "name": "栈的定义与实现", "code": "DS...", "order": 1},
         "question_type": "choice",
         "error": None | "AI 服务暂不可用",
         "raw_analysis": {索引: 原始解析},
         "questions": [ {...}, ... ]}

    查重参照 = 现有题库 ∪ **同批在前的候选题**（先到先得：首个出现者通过，
    之后与它近似的被判重并指向它）。这避免了"两个互为近似的题一起被判重后
    全废"的歧义。

    参照标签约定：同批题用其 ``question_id``（如 ``P43-01-003``，便于在 manifest
    内直接定位）；现有题库题用 ``existing:<id>``。
    """
    references: list[dict[str, Any]] = [
        build_reference(f"existing:{item.get('id')}", item.get("stem") or "")
        for item in existing_questions
    ]
    rows: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    by_gate: dict[str, int] = {}
    sequence = 0

    for entry in entries:
        concept = entry.get("concept") or {}
        concept_name = str(concept.get("name") or "")
        if entry.get("error"):
            errors.append(
                {
                    "concept_id": concept.get("id"),
                    "concept_name": concept_name,
                    "code": concept.get("code"),
                    "reason": str(entry["error"]),
                }
            )
            continue
        raw_analysis = entry.get("raw_analysis") or {}
        for index, question in enumerate(entry.get("questions") or []):
            sequence += 1
            verdict = evaluate(
                question,
                expected_concept_name=concept_name or None,
                expected_subject=subject,
                raw_analysis=raw_analysis.get(index),
                references=references,
            )
            for gate, item in verdict["gates"].items():
                if not item["passed"]:
                    by_gate[gate] = by_gate.get(gate, 0) + 1
            rows.append(
                {
                    "question_id": f"{id_prefix}-{batch:02d}-{sequence:03d}",
                    "stem": str(question.get("stem") or "").strip(),
                    "options": _options(question),
                    "answer": str(question.get("answer") or "").strip(),
                    "analysis": str(question.get("analysis") or "").strip(),
                    "difficulty": question.get("difficulty"),
                    "question_type": _question_type(question),
                    "knowledge_point_code": concept.get("code"),
                    "knowledge_point_name": concept_name or None,
                    "knowledge_point_id": concept.get("id"),
                    "source": "ai",
                    "quality_check": {
                        "passed": verdict["passed"],
                        "reasons": verdict["reasons"],
                        "gates": verdict["gates"],
                    },
                    "suggested_action": "accept" if verdict["passed"] else "reject",
                    "duplicate_of": verdict["duplicate_of"],
                }
            )
            references.append(
                build_reference(rows[-1]["question_id"], question.get("stem") or "")
            )

    distribution = evaluate_answer_distribution(
        answer_letter_counts([row for row in rows if row["question_type"] == "choice"])
    )
    # G5B 只在样本充足时阻断；命中时把责任落到"占比越界的字母"对应的题上。
    if distribution["passed"] is False and distribution["blocking"]:
        for row in rows:
            if row["question_type"] != "choice":
                continue
            if option_letter(row["answer"]) in distribution["offenders"]:
                row["quality_check"]["passed"] = False
                row["quality_check"]["reasons"].append(f"G5B {distribution['reason']}")
                row["quality_check"]["gates"]["G5B"] = {
                    "gate": "G5B",
                    "title": GATE_TITLES["G5B"],
                    "passed": False,
                    "reason": distribution["reason"],
                }
                row["suggested_action"] = "reject"
        by_gate["G5B"] = by_gate.get("G5B", 0) + len(
            [
                row
                for row in rows
                if row["quality_check"]["gates"].get("G5B", {}).get("passed") is False
            ]
        )

    passed = sum(1 for row in rows if row["quality_check"]["passed"])
    return {
        "schema_version": "p4-3.1",
        "generated_at": generated_at,
        "subject": subject,
        "batch": batch,
        "gate_config": gate_config(),
        "summary": {
            "concepts": len([entry for entry in entries if entry.get("concept")]),
            "concepts_with_error": len(errors),
            "candidates": len(rows),
            "passed": passed,
            "failed": len(rows) - passed,
            "by_gate": dict(sorted(by_gate.items())),
            "answer_position": distribution,
            "existing_references": len(existing_questions),
        },
        "questions": rows,
        "errors": errors,
    }
