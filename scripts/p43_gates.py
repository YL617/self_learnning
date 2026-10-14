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

阈值来源：``docs/M5.5_P4-3.1_AI题目生成管道设计.md`` §4.2（G1–G8 规格表，
**已按 P4-3.3.1 校准**）。
上游依据：``docs/M5.5_P4-3_题目供给设计方案.md`` §3.2；校准依据
``docs/M5.5_P4-3.3.1_门禁校准设计.md``。

**两级语义（P4-3.3.1）**：门禁结论分 ``fail``（阻断，确定性缺陷）与 ``warning``
（提示，风格/批级属性）。**只有 fail 能把一题判成不通过**；warning 只进
``quality_check.warnings``，供人审参考，绝不改变 ``passed``。
"""

from __future__ import annotations

import hashlib
import random
import re
import statistics
import unicodedata
from collections.abc import Sequence
from typing import Any

# ---------------------------------------------------------------------------
# G1–G8 阈值（冻结值；改动必须同步更新设计文档 §4.2 与本模块 docstring）
#
# P4-3.3.1 校准（2026-10-12）：把「批级/风格属性」从**阻断**降级为**提示**。
#   · G5B 批内答案位置分布 —— 只出批级 advisory，绝不逐题 FAIL（详见该函数）。
#   · G5 长度均衡 —— 从「全局极差比 ≤ 2.5」改为「正确答案显著长于干扰项」告警。
#   阻断项只剩**确定性缺陷**：禁用表述、空选项、答案不可对齐、重复、元数据缺失…
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

# --- G5 长度均衡（**仅提示，不再阻断**）-------------------------------------
# 旧规则「全部选项正文 max/min ≤ 2.5」对定量短选项过敏：
#   [e, 2e, n+e, n²-e] → 长度 1/2/3/5 → 极差比 5.0 → 被误判。
# 真正的泄漏风险是「正确答案因解释而显著更长」。故改为：仅当**正确答案**
# 同时满足「≥ 干扰项长度中位数的 OPTION_ANSWER_LEAK_RATIO 倍」「严格最长」
# 「本身 ≥ OPTION_ANSWER_LEAK_MIN_CHARS 字」时，出一条 advisory（passed 仍为 True）。
OPTION_ANSWER_LEAK_RATIO = 2.0
OPTION_ANSWER_LEAK_MIN_CHARS = 6
OPTION_ANSWER_LEAK_MIN_DISTRACTORS = 2

# --- G5B 批内答案位置分布（**批级 advisory，绝不逐题 FAIL**）----------------
# 参考区间仅用于**提示**（建议后续做选项洗牌），不作为任何单题的剔除理由。
ANSWER_POSITION_MIN_SHARE = 0.20
ANSWER_POSITION_MAX_SHARE = 0.30
ANSWER_POSITION_MIN_SAMPLE = 20
# 4 个字母各占 20%~30% ⇒ 理想上要用满 4 个不同字母。
ANSWER_POSITION_MIN_LETTERS = 4
# 洗牌建议的标识（写入 manifest advisory，供外部系统消费）。
SHUFFLE_SUGGESTION = "shuffle_options"
# 答案位置的候选字母池（批内轮转分配用）。
ANSWER_LETTER_POOL = ("A", "B", "C", "D")

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
_ANALYSIS_ANSWER_RE = re.compile(
    r"((?:正确)?答案\s*(?:是|为|选(?:择)?)\s*)([A-Z])(?![A-Za-z0-9])",
    re.IGNORECASE,
)
_ANALYSIS_OPTION_AFTER_RE = re.compile(
    r"(?<![A-Za-z0-9])([A-Z])(\s*(?:项|选项))",
    re.IGNORECASE,
)
_ANALYSIS_OPTION_BEFORE_RE = re.compile(
    r"(选项\s*)([A-Z])(?![A-Za-z0-9])",
    re.IGNORECASE,
)


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
    return {
        "gate": gate,
        "title": GATE_TITLES[gate],
        "passed": False,
        "severity": "fail",
        "reason": reason,
        **meta,
    }


def _pass(gate: str, **meta: Any) -> dict[str, Any]:
    return {"gate": gate, "title": GATE_TITLES[gate], "passed": True, "severity": None, "reason": None, **meta}


def _advisory(result: dict[str, Any], reason: str) -> dict[str, Any]:
    """把一条**通过但带提示**的门禁结果打上 ``severity='warning'``（不改变 passed）。"""
    return {**result, "reason": reason, "severity": "warning"}


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
    if _question_type(question) == "choice":
        answer_letter = option_letter(question.get("answer"))
        declared_answers = {
            match.group(2).upper() for match in _ANALYSIS_ANSWER_RE.finditer(text)
        }
        if answer_letter and declared_answers and declared_answers != {answer_letter}:
            return _fail(
                "G3",
                f"解析声明答案 {sorted(declared_answers)} 与答案字段 {answer_letter} 不一致",
            )
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


def answer_option_index(question: dict[str, Any]) -> int | None:
    """定位「正确选项」在 ``options`` 中的下标。

    优先按答案前导字母匹配选项前导字母；失败时按**归一化正文**匹配；仍失败返回
    ``None``（此时交给 G2 报"答案不可对齐"，本处不重复报错）。
    """
    options = _options(question)
    letters = [option_letter(option) for option in options]
    answer_letter = option_letter(question.get("answer"))
    if answer_letter:
        for index, letter in enumerate(letters):
            if letter == answer_letter:
                return index
    answer_text = str(question.get("answer") or "").strip()
    target = normalize_text(answer_text)
    if target:
        for index, option in enumerate(options):
            if normalize_text(option_body(option)) == target:
                return index
    return None


def option_length_advisory(question: dict[str, Any]) -> str | None:
    """「正确答案显著长于干扰项」提示；条件不满足返回 ``None``（**不阻断**）。

    旧规则是"全部选项正文 max/min ≤ 2.5"，对 ``[e, 2e, n+e, n²-e]`` 这类定量短选项
    误伤（极差比 5.0）。真正需要留意的是："正确答案因为附带解释而明显更长" →
    **泄露答案**。故只在「正确项 ≥ 干扰项长度中位数的 N 倍 ∧ 严格最长 ∧ 本身够长」时提示。
    """
    options = _options(question)
    if len(options) < CHOICE_MIN_OPTIONS + 1:  # 至少 3 个选项才有"干扰项中位数"可言
        return None
    correct = answer_option_index(question)
    if correct is None:
        return None
    bodies = [option_body(option) for option in options]
    correct_length = len(bodies[correct])
    if correct_length < OPTION_ANSWER_LEAK_MIN_CHARS:
        return None
    distractor_lengths = [len(body) for index, body in enumerate(bodies) if index != correct]
    if len(distractor_lengths) < OPTION_ANSWER_LEAK_MIN_DISTRACTORS:
        return None
    median = statistics.median(distractor_lengths)
    if median <= 0:
        return None
    if correct_length >= OPTION_ANSWER_LEAK_RATIO * median and correct_length > max(distractor_lengths):
        return (
            f"正确选项（{correct_length} 字）显著长于干扰项（中位数 {median:g} 字），"
            "可能泄露答案；建议改写成与干扰项长度相近的同类表述后人工复核"
        )
    return None


def gate_g5_option_quality(question: dict[str, Any]) -> dict[str, Any]:
    """G5 选项质量。

    ① **阻断**（确定性缺陷 / KMLE 合规）：禁用「以上都对 / 全不选」类表述、空选项。
    ② **仅提示**（``severity='warning'``，不改 ``passed``）：正确答案显著长于干扰项。
       旧版「全局极差比 ≤ 2.5」已废除 —— 它对定量短选项（``e / 2e / n+e``）过敏，
       把正常题误判为坏题（P4-3.3.1 校准）。
    """
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
    shortest = min(lengths) or 1
    result = _pass("G5", option_length_ratio=round(max(lengths) / shortest, 4))
    advisory = option_length_advisory(question)
    return _advisory(result, advisory) if advisory else result


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


def _answer_position_thresholds() -> dict[str, Any]:
    return {
        "share_range": [ANSWER_POSITION_MIN_SHARE, ANSWER_POSITION_MAX_SHARE],
        "min_letters": ANSWER_POSITION_MIN_LETTERS,
        "min_sample": ANSWER_POSITION_MIN_SAMPLE,
    }


def _answer_distribution_warning(
    shares: dict[str, float],
    offenders: list[str],
    missing: list[str],
    total: int,
    small_sample: bool,
) -> dict[str, Any]:
    details: list[str] = []
    if offenders:
        details.append(
            "占比越界：" + "、".join(f"{letter}={shares[letter]:.0%}" for letter in offenders)
        )
    if missing:
        details.append("未使用字母：" + "、".join(missing))
    if len(shares) < ANSWER_POSITION_MIN_LETTERS:
        details.append(f"仅使用 {len(shares)} 个字母")
    message = "批内答案位置不均衡（" + "；".join(details) + "）"
    if small_sample:
        message = f"样本 {total} < {ANSWER_POSITION_MIN_SAMPLE}，" + message
    message += "；建议开启选项洗牌（shuffle_options）后再送审"
    return {"type": "answer_distribution", "suggestion": SHUFFLE_SUGGESTION, "message": message}


def evaluate_answer_distribution(counts: dict[str, int]) -> dict[str, Any]:
    """批内答案位置分布 —— **批级 advisory，绝不逐题 FAIL**（P4-3.3.1 校准）。

    为什么不再是阻断规则：答案位置不均衡是**整批的统计属性**，不是任何**单题**的缺陷。
    旧实现把「C 占 45%」记成"9 道 C 题各自 FAIL" —— 既责任错配（D 从未出现反而不指责
    任何题）、又不自洽（删掉 C 之后剩下的题依旧不均衡）、也违背初衷（题本身无缺陷却要
    人工逐条写 override）。正解是「批级提示 + **选项洗牌**（见 :func:`shuffle_options`）」。

    ``warning`` 为结构化提示 ``{"type","suggestion","message"}``；均衡时为 ``None``。
    返回值**不含** ``passed`` / ``blocking`` —— 本函数不参与任何单题裁定。
    """
    total = sum(counts.values())
    if total == 0:
        return {
            "gate": "G5B",
            "title": GATE_TITLES["G5B"],
            "advisory": True,
            "balanced": True,
            "sample": 0,
            "small_sample": True,
            "counts": {},
            "shares": {},
            "offenders": [],
            "missing_letters": [],
            "warning": None,
            "thresholds": _answer_position_thresholds(),
        }
    shares = {letter: count / total for letter, count in sorted(counts.items())}
    offenders = sorted(
        letter
        for letter, share in shares.items()
        if share < ANSWER_POSITION_MIN_SHARE or share > ANSWER_POSITION_MAX_SHARE
    )
    missing = sorted(set("ABCD") - set(counts))
    too_few_letters = len(counts) < ANSWER_POSITION_MIN_LETTERS
    small_sample = total < ANSWER_POSITION_MIN_SAMPLE
    balanced = not offenders and not too_few_letters and not missing
    warning = (
        None
        if balanced
        else _answer_distribution_warning(shares, offenders, missing, total, small_sample)
    )
    return {
        "gate": "G5B",
        "title": GATE_TITLES["G5B"],
        "advisory": True,
        "balanced": balanced,
        "sample": total,
        "small_sample": small_sample,
        "counts": counts,
        "shares": {letter: round(share, 4) for letter, share in shares.items()},
        "offenders": offenders,
        "missing_letters": missing,
        "warning": warning,
        "thresholds": _answer_position_thresholds(),
    }


# ---------------------------------------------------------------------------
# 选项洗牌：把正确答案均匀打散到 A–D（治本，替代"检测+逐题 FAIL"）
# ---------------------------------------------------------------------------
def option_label(index: int) -> str:
    """0 → ``"A"``，1 → ``"B"`` …（越界退化为 ``"1"``、``"2"``…）。"""
    return chr(ord("A") + index) if 0 <= index < 26 else str(index + 1)


def _stable_seed(*parts: str) -> int:
    """内容派生的稳定种子。

    关键：用 ``hashlib`` 而非内置 ``hash()`` —— 后者受 ``PYTHONHASHSEED`` 影响，
    同一份原始响应重放会得到不同顺序，破坏"可重放"契约。
    """
    payload = "\x1f".join(parts).encode("utf-8")
    return int.from_bytes(hashlib.sha256(payload).digest()[:8], "big")


def relabel_analysis_options(analysis: Any, old_to_new: dict[str, str]) -> str:
    """同步改写解析中的选项字母引用，避免洗牌后解析指向旧选项。"""
    text = str(analysis or "")

    def replace_answer(match: re.Match[str]) -> str:
        return match.group(1) + old_to_new.get(match.group(2).upper(), match.group(2).upper())

    def replace_after(match: re.Match[str]) -> str:
        return old_to_new.get(match.group(1).upper(), match.group(1).upper()) + match.group(2)

    def replace_before(match: re.Match[str]) -> str:
        return match.group(1) + old_to_new.get(match.group(2).upper(), match.group(2).upper())

    text = _ANALYSIS_ANSWER_RE.sub(replace_answer, text)
    text = _ANALYSIS_OPTION_AFTER_RE.sub(replace_after, text)
    return _ANALYSIS_OPTION_BEFORE_RE.sub(replace_before, text)


def shuffle_options(question: dict[str, Any], *, position: int | None = None, seed: str = "") -> dict[str, Any]:
    """确定性重排选项并**同步重算答案字母**（纯函数，不改入参）。

    - 种子 = ``sha256(seed + 题干)`` → 同一题干重放得到同一顺序（可复现、可审计）。
    - ``position`` 给定则把**正确项**放在该槽位（供 :func:`plan_answer_positions` 做
      批内均衡）；为 ``None`` 时随机槽位。
    - 选项统一重写为 ``"A. 正文"`` 形式；正确答案的新字母按重排后的位置推出。
    - 答案以**正文**给出时，按归一化正文匹配定位正确项；答案无法定位则只打乱顺序、
      原样保留答案（交给 G2 报"答案不可对齐"，本函数不吞错）。
    - 非选择题 / 选项 < 2 个：原样返回。
    """
    if _question_type(question) != "choice":
        return dict(question)
    options = _options(question)
    if len(options) < CHOICE_MIN_OPTIONS:
        return dict(question)
    bodies = [option_body(option) or str(option).strip() for option in options]
    correct = answer_option_index(question)
    rng = random.Random(_stable_seed(seed, str(question.get("stem") or "")))
    if correct is None:
        order = list(range(len(bodies)))
        rng.shuffle(order)
    else:
        slots = len(bodies)
        slot = rng.randrange(slots) if position is None else position % slots
        others = [index for index in range(slots) if index != correct]
        rng.shuffle(others)
        iterator = iter(others)
        order = [correct if index == slot else next(iterator) for index in range(slots)]
    shuffled = {
        **question,
        "options": [
            f"{option_label(slot_index)}. {bodies[index]}" for slot_index, index in enumerate(order)
        ],
    }
    old_to_new = {
        option_label(old_index): option_label(new_index)
        for new_index, old_index in enumerate(order)
    }
    shuffled["analysis"] = relabel_analysis_options(question.get("analysis"), old_to_new)
    if correct is not None:
        new_letter = option_label(order.index(correct))
        answer_letter = option_letter(question.get("answer"))
        shuffled["answer"] = new_letter if answer_letter else f"{new_letter}. {bodies[correct]}"
    return shuffled


def plan_answer_positions(count: int, *, seed: str = "") -> list[int]:
    """规划 ``count`` 道题的答案槽位：**批内尽可能均匀**（各字母出现次数差 ≤ 1）。

    为什么不"每题独立随机"：独立随机在 20 题规模下某字母可占到 40%+（P4-3.3.1 实测
    D=45%，仍会被考生察觉）。轮转 + 洗牌则天然均匀（20 题 → 每个字母恰好 5 次），
    既满足"把答案打散"的初衷，又保持确定性（同一批重放必得同一分配）。
    """
    if count <= 0:
        return []
    slots = [index % len(ANSWER_LETTER_POOL) for index in range(count)]
    random.Random(_stable_seed(seed, "answer-position-plan")).shuffle(slots)
    return slots


def shuffle_entries(entries: Sequence[dict[str, Any]], *, seed: str = "") -> int:
    """就地洗牌 ``entries`` 里每个 concept 的候选题；返回**被洗牌的题数**。

    答案槽位由 :func:`plan_answer_positions` 按**整批**统一规划 → 批内答案字母天然均衡。
    """
    targets: list[tuple[dict[str, Any], int, dict[str, Any]]] = []
    for entry in entries:
        for index, question in enumerate(entry.get("questions") or []):
            if _question_type(question) == "choice" and len(_options(question)) >= CHOICE_MIN_OPTIONS:
                targets.append((entry, index, question))
    plan = plan_answer_positions(len(targets), seed=seed)
    for (entry, index, question), position in zip(targets, plan):
        shuffled = shuffle_options(question, position=position, seed=seed)
        entry["questions"][index] = shuffled
        raw_analysis = entry.get("raw_analysis")
        if isinstance(raw_analysis, dict) and index in raw_analysis:
            raw_analysis[index] = shuffled.get("analysis")
    return len(targets)


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
    """跑 G1–G7，返回 ``{"passed", "gates", "reasons", "warnings", "duplicate_of"}``。

    ``reasons`` 只含**阻断**（``severity='fail'``）理由；``warnings`` 为不影响通过的
    提示（``severity='warning'``，如"正确选项显著长于干扰项"）。二者严格分离 ——
    提示永远不能把一题变成 FAIL（P4-3.3.1 校准）。
    """
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
    warnings = [
        item["reason"]
        for item in results
        if item.get("severity") == "warning" and item.get("reason")
    ]
    duplicate_of = next(
        (item.get("duplicate_of") for item in results if item.get("duplicate_of")), None
    )
    return {
        "passed": not reasons,
        "gates": {item["gate"]: item for item in results},
        "reasons": reasons,
        "warnings": warnings,
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
    """把阈值整体冻结进 manifest，便于日后审计"当时用的是哪套阈值"。

    语义分级（P4-3.3.1）：``blocking`` 列出会判 FAIL 的规则；``advisory`` 列出只出提示
    的规则。人审只看 blocking，advisory 仅作参考。
    """
    return {
        "min_stem_chars": MIN_STEM_CHARS,
        "max_stem_chars": MAX_STEM_CHARS,
        "min_analysis_chars": MIN_ANALYSIS_CHARS,
        "analysis_filler_fingerprint": ANALYSIS_FILLER_FINGERPRINT,
        "offline_fingerprints": list(OFFLINE_FINGERPRINTS),
        "dup_jaccard_threshold": DUP_JACCARD_THRESHOLD,
        "shingle_size": SHINGLE_SIZE,
        "choice_options_range": [CHOICE_MIN_OPTIONS, CHOICE_MAX_OPTIONS],
        "banned_option_patterns": list(BANNED_OPTION_PATTERNS),
        "valid_difficulties": list(VALID_DIFFICULTIES),
        "blocking_rules": ["G1", "G2", "G3", "G4", "G5:合法性", "G6", "G7"],
        "advisory_rules": ["G5:长度均衡", "G5B"],
        "option_answer_leak_ratio": OPTION_ANSWER_LEAK_RATIO,
        "option_answer_leak_min_chars": OPTION_ANSWER_LEAK_MIN_CHARS,
        "answer_position_share_range": [ANSWER_POSITION_MIN_SHARE, ANSWER_POSITION_MAX_SHARE],
        "answer_position_min_sample": ANSWER_POSITION_MIN_SAMPLE,
        "answer_position_min_letters": ANSWER_POSITION_MIN_LETTERS,
        "shuffle_suggestion": SHUFFLE_SUGGESTION,
    }


def _suggested_action(verdict: dict[str, Any]) -> str:
    """机器建议：``reject``（有阻断）｜``review``（仅提示、需人看）｜``accept``。

    注意：**批级 advisory（G5B）永远不会把这里变成 ``reject``** —— 答案分布不平衡
    不是单题缺陷（P4-3.3.1）。
    """
    if not verdict["passed"]:
        return "reject"
    return "review" if verdict["warnings"] else "accept"


def assemble_manifest(
    *,
    subject: str,
    entries: Sequence[dict[str, Any]],
    existing_questions: Sequence[dict[str, Any]] = (),
    generated_at: str,
    batch: int = 1,
    id_prefix: str = "P43",
    options_shuffle: dict[str, Any] | None = None,
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
                        "warnings": verdict["warnings"],
                        "gates": verdict["gates"],
                    },
                    "suggested_action": _suggested_action(verdict),
                    "duplicate_of": verdict["duplicate_of"],
                }
            )
            references.append(
                build_reference(rows[-1]["question_id"], question.get("stem") or "")
            )

    distribution = evaluate_answer_distribution(
        answer_letter_counts([row for row in rows if row["question_type"] == "choice"])
    )
    # G5B 只产出**批级 advisory**（P4-3.3.1）：不再把任何单题改成 FAIL / reject。
    passed = sum(1 for row in rows if row["quality_check"]["passed"])
    return {
        "schema_version": "p4-3.1",
        "generated_at": generated_at,
        "subject": subject,
        "batch": batch,
        "gate_config": gate_config(),
        "options_shuffle": dict(options_shuffle or {"enabled": False}),
        "summary": {
            "concepts": len([entry for entry in entries if entry.get("concept")]),
            "concepts_with_error": len(errors),
            "candidates": len(rows),
            "passed": passed,
            "failed": len(rows) - passed,
            "needs_review": sum(1 for row in rows if row["suggested_action"] == "review"),
            "by_gate": dict(sorted(by_gate.items())),
            "answer_position": distribution,
            "answer_distribution_warning": distribution.get("warning"),
            "existing_references": len(existing_questions),
        },
        "questions": rows,
        "errors": errors,
    }
