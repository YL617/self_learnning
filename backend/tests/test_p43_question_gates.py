"""M5.5 P4-3.1 —— AI 题目生成管道（门禁 + 离线重放 CLI）测试。

被测对象位于**项目根** ``scripts/``（不进生产镜像）：

  - ``scripts/p43_gates.py``            —— 纯函数门禁（G1–G8），importlib 直载
  - ``scripts/generate_question_batch.py`` —— 离线重放 CLI（--raw-dir，零网络）

本文件**不联网、不写库、不调生产 API**：CLI 全部走 ``--raw-dir`` 重放路径，
只验证"生成 → 门禁 → manifest"这三段里除"调模型"以外的全部逻辑。
"""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
GATES_PATH = ROOT / "scripts" / "p43_gates.py"
CLI_PATH = ROOT / "scripts" / "generate_question_batch.py"

GOOD_ANALYSIS = (
    "栈是只允许在表尾进行插入和删除操作的线性表，插入端称为栈顶，另一端称为栈底。"
    "由于入栈与出栈都发生在栈顶，最后入栈的元素最先出栈，因此栈的核心特性是后进先出。"
)

GOOD_STEM = "在采用顺序存储结构的线性表中，若要在第 i 个位置插入一个新元素，平均需要移动多少个元素？"


def load_gates():
    spec = importlib.util.spec_from_file_location("p43_gates", GATES_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


gates = load_gates()


def make_question(**overrides):
    question = {
        "subject": "数据结构",
        "knowledge_point": "栈的定义与实现",
        "question_type": "choice",
        "stem": GOOD_STEM,
        # 选项长度均衡（极差比 2.0 ≤ 2.5），且答案必须落在选项内。
        "options": ["A. n/2 个", "B. n 个", "C. 固定 1 个", "D. 恰好 i 个"],
        "answer": "A",
        "analysis": GOOD_ANALYSIS,
        "difficulty": "easy",
    }
    question.update(overrides)
    return question


def raw_payload(questions):
    return json.dumps({"raw_text": json.dumps(questions, ensure_ascii=False)}, ensure_ascii=False)


# ---------------------------------------------------------------------------
# 文本工具
# ---------------------------------------------------------------------------
def test_normalize_text_folds_width_case_and_punctuation():
    assert gates.normalize_text("Ａ Ｂ，Ｃ。d") == gates.normalize_text("ab cd")
    assert gates.normalize_text("栈 的 定义") == "栈的定义"
    assert gates.normalize_text(None) == ""


def test_jaccard_identical_disjoint_and_empty():
    stem = gates.shingle_set(GOOD_STEM)
    assert gates.jaccard(stem, stem) == 1.0
    assert gates.jaccard(stem, gates.shingle_set("完全不相关的另一句话，用于对照测试")) < 0.2
    assert gates.jaccard(stem, frozenset()) == 0.0
    assert gates.jaccard(frozenset(), frozenset()) == 0.0


def test_shingle_set_handles_short_text():
    assert gates.shingle_set("栈") == frozenset({"栈"})
    assert gates.shingle_set("") == frozenset()


def test_option_letter_and_body():
    assert gates.option_letter("B. 先进先出") == "B"
    assert gates.option_letter("c、随机存取") == "C"
    assert gates.option_letter("栈") is None
    assert gates.option_body("B. 先进先出") == "先进先出"


# ---------------------------------------------------------------------------
# G1 结构
# ---------------------------------------------------------------------------
def test_g1_rejects_empty_and_overlong_stem():
    assert gates.gate_g1_structure(make_question())["passed"] is True
    assert gates.gate_g1_structure(make_question(stem=""))["passed"] is False
    assert gates.gate_g1_structure(make_question(stem="太短"))["passed"] is False
    assert gates.gate_g1_structure(make_question(stem="题" * 401))["passed"] is False


def test_g1_rejects_empty_answer_bad_type_and_bad_option_count():
    assert gates.gate_g1_structure(make_question(answer=""))["passed"] is False
    assert gates.gate_g1_structure(make_question(question_type="essay"))["passed"] is False
    assert gates.gate_g1_structure(make_question(options=["A. 只有一个"]))["passed"] is False
    assert gates.gate_g1_structure(
        make_question(options=[f"{letter}. 选项" for letter in "ABCDEFG"])
    )["passed"] is False


# ---------------------------------------------------------------------------
# G2 答案可对齐
# ---------------------------------------------------------------------------
def test_g2_requires_answer_letter_within_options():
    assert gates.gate_g2_answer_alignment(make_question())["passed"] is True
    assert gates.gate_g2_answer_alignment(make_question(answer="B"))["passed"] is True
    # 答案字母不在选项内（选项只有 A–D）
    assert gates.gate_g2_answer_alignment(make_question(answer="E"))["passed"] is False
    # 答案不是字母
    assert gates.gate_g2_answer_alignment(make_question(answer="后进先出"))["passed"] is False
    # 选项没有字母前缀
    assert (
        gates.gate_g2_answer_alignment(make_question(options=["后进先出", "先进先出"]))["passed"]
        is False
    )
    # 非选择题跳过
    assert (
        gates.gate_g2_answer_alignment(make_question(question_type="fill", options=[]))["passed"]
        is True
    )


# ---------------------------------------------------------------------------
# G3 解析原始质量
# ---------------------------------------------------------------------------
def test_g3_reads_raw_analysis_not_padded_value():
    padded = GOOD_ANALYSIS
    assert gates.gate_g3_analysis_quality(make_question(), raw_analysis=padded)["passed"] is True
    # 归一化后的字段够长，但**原始**解析过短 → 必须拒
    short_raw = "后进先出"
    assert gates.gate_g3_analysis_quality(make_question(), raw_analysis=short_raw)["passed"] is False


def test_g3_filler_fingerprint_beats_length():
    padded = GOOD_ANALYSIS + gates.ANALYSIS_FILLER_FINGERPRINT + "数据结构教材确认。" * 3
    result = gates.gate_g3_analysis_quality(make_question(), raw_analysis=padded)
    assert result["passed"] is False
    assert "补全指纹" in result["reason"]


# ---------------------------------------------------------------------------
# G4 去重
# ---------------------------------------------------------------------------
def test_g4_detects_exact_duplicate():
    reference = gates.build_reference("existing:7", GOOD_STEM)
    result = gates.gate_g4_duplicate(make_question(), [reference])
    assert result["passed"] is False
    assert result["duplicate_of"] == "existing:7"
    assert "完全重复" in result["reason"]


def test_g4_detects_near_duplicate_above_threshold():
    # 典型近似题：原题尾部追加一句要求（精确 stem 去重拦不住）。
    near = GOOD_STEM + "请说明理由"
    score = gates.jaccard(gates.shingle_set(GOOD_STEM), gates.shingle_set(near))
    assert score >= gates.DUP_JACCARD_THRESHOLD, f"测试前提：近似句相似度 {score:.3f} 应不低于阈值"
    result = gates.gate_g4_duplicate(make_question(stem=near), [gates.build_reference("q1", GOOD_STEM)])
    assert result["passed"] is False
    assert result["similarity"] >= gates.DUP_JACCARD_THRESHOLD


def test_g4_passes_for_unrelated_stem():
    reference = gates.build_reference("q1", "关于图的深度优先搜索，下列说法中错误的是哪一项？")
    assert gates.gate_g4_duplicate(make_question(), [reference])["passed"] is True


# ---------------------------------------------------------------------------
# G5 选项质量
# ---------------------------------------------------------------------------
def test_g5_rejects_banned_option_patterns():
    for banned in ("C. 以上都对", "D. 全不选", "B. 以上均正确"):
        result = gates.gate_g5_option_quality(
            make_question(options=["A. 后进先出", "C. 先进先出", banned])
        )
        assert result["passed"] is False
        assert "禁用表述" in result["reason"]


def test_g5_rejects_option_length_spread():
    result = gates.gate_g5_option_quality(
        make_question(options=["A. 短", "B. 这是一个非常非常长的选项文本内容啊"])
    )
    assert result["passed"] is False
    assert "极差比" in result["reason"]


def test_g5_passes_for_balanced_options():
    assert gates.gate_g5_option_quality(make_question())["passed"] is True


# ---------------------------------------------------------------------------
# G6 元数据 / G7 学科
# ---------------------------------------------------------------------------
def test_g6_requires_concept_name_and_difficulty():
    assert gates.gate_g6_metadata(make_question(), "栈的定义与实现")["passed"] is True
    # 写成章节名（不是原子 concept 名）
    assert gates.gate_g6_metadata(make_question(knowledge_point="栈和队列"), "栈的定义与实现")[
        "passed"
    ] is False
    assert gates.gate_g6_metadata(make_question(difficulty=None), "栈的定义与实现")["passed"] is False
    assert gates.gate_g6_metadata(make_question(difficulty="very hard"), "栈的定义与实现")[
        "passed"
    ] is False


def test_g7_requires_subject_consistency():
    assert gates.gate_g7_subject(make_question(), "数据结构")["passed"] is True
    assert gates.gate_g7_subject(make_question(subject="操作系统"), "数据结构")["passed"] is False
    assert gates.gate_g7_subject(make_question(subject=""), "数据结构")["passed"] is False


# ---------------------------------------------------------------------------
# G8 离线降级
# ---------------------------------------------------------------------------
def test_g8_detects_offline_degradation():
    assert gates.detect_offline("（离线降级响应）已收到请求：xxx") is True
    assert gates.detect_offline("请在 .env 中配置模型 API Key 后获得完整能力。") is True
    assert gates.detect_offline('[{"stem": "正常题目"}]') is False
    assert gates.offline_reason("") == "G8 原始响应为空"
    assert gates.offline_reason("（离线降级响应）") is not None
    assert gates.offline_reason('[{"stem": "ok"}]') is None


# ---------------------------------------------------------------------------
# G5B 批内答案位置分布
# ---------------------------------------------------------------------------
def test_answer_distribution_balanced_passes():
    report = gates.evaluate_answer_distribution({"A": 5, "B": 5, "C": 5, "D": 5})
    assert report["passed"] is True
    assert report["blocking"] is True


def test_answer_distribution_flags_skew_and_few_letters():
    report = gates.evaluate_answer_distribution({"A": 20})
    assert report["passed"] is False
    assert report["blocking"] is True
    assert report["offenders"] == ["A"]
    skewed = gates.evaluate_answer_distribution({"A": 8, "B": 8, "C": 4})
    assert skewed["passed"] is False
    assert set(skewed["offenders"]) == {"A", "B"}


def test_answer_distribution_is_advisory_below_sample():
    report = gates.evaluate_answer_distribution({"A": 10})
    assert report["blocking"] is False


# ---------------------------------------------------------------------------
# 单题总评 + manifest 组装
# ---------------------------------------------------------------------------
def test_evaluate_passes_for_well_formed_question():
    verdict = gates.evaluate(make_question(), expected_subject="数据结构", expected_concept_name="栈的定义与实现")
    assert verdict["passed"] is True
    assert verdict["reasons"] == []
    assert set(verdict["gates"]) == set(gates.GATE_ORDER)


def test_evaluate_collects_all_failed_reasons():
    broken = make_question(answer="Z", difficulty=None, subject="操作系统")
    verdict = gates.evaluate(broken, expected_subject="数据结构")
    assert verdict["passed"] is False
    assert {"G2", "G6", "G7"} <= set(verdict["gates"])
    assert len(verdict["reasons"]) >= 3


def _entry(concept_id, name, questions, code=None, error=None):
    return {
        "concept": {"id": concept_id, "name": name, "code": code, "order": 1},
        "question_type": "choice",
        "questions": questions,
        "raw_analysis": {index: item.get("analysis") for index, item in enumerate(questions)},
        "error": error,
    }


def test_assemble_manifest_contract_and_counts():
    manifest = gates.assemble_manifest(
        subject="数据结构",
        entries=[_entry(19, "栈的定义与实现", [make_question()], code="DS.STACKQUEUE.STACK.BASIC")],
        generated_at="2026-10-12T00:00:00+00:00",
        batch=1,
    )
    assert manifest["schema_version"] == "p4-3.1"
    assert manifest["summary"]["candidates"] == 1
    assert manifest["summary"]["passed"] == 1
    assert manifest["summary"]["concepts_with_error"] == 0
    row = manifest["questions"][0]
    for key in (
        "question_id",
        "stem",
        "options",
        "answer",
        "analysis",
        "difficulty",
        "knowledge_point_code",
        "source",
        "quality_check",
    ):
        assert key in row, f"manifest 契约缺字段：{key}"
    assert row["question_id"] == "P43-01-001"
    assert row["source"] == "ai"
    assert row["knowledge_point_code"] == "DS.STACKQUEUE.STACK.BASIC"
    assert row["quality_check"]["passed"] is True
    assert row["suggested_action"] == "accept"
    assert manifest["gate_config"]["dup_jaccard_threshold"] == gates.DUP_JACCARD_THRESHOLD


def test_assemble_manifest_records_generation_errors_separately():
    manifest = gates.assemble_manifest(
        subject="数据结构",
        entries=[
            _entry(19, "栈的定义与实现", [], error="G8 AI 网关离线降级"),
            _entry(38, "堆", [make_question(knowledge_point="堆", stem=GOOD_STEM + "补充问法？")]),
        ],
        generated_at="2026-10-12T00:00:00+00:00",
    )
    assert manifest["summary"]["concepts_with_error"] == 1
    assert manifest["errors"][0]["concept_name"] == "栈的定义与实现"
    # 生成失败的 concept 不产生候选题
    assert manifest["summary"]["candidates"] == 1


def test_assemble_manifest_dedupes_within_batch_first_wins():
    duplicated = [make_question(), make_question(options=["A. 1", "B. 2"])]
    manifest = gates.assemble_manifest(
        subject="数据结构",
        entries=[_entry(19, "栈的定义与实现", duplicated)],
        generated_at="2026-10-12T00:00:00+00:00",
    )
    rows = manifest["questions"]
    assert rows[0]["quality_check"]["passed"] is True
    assert rows[1]["quality_check"]["passed"] is False
    assert rows[1]["duplicate_of"] == rows[0]["question_id"]
    assert manifest["summary"]["by_gate"]["G4"] == 1


def test_assemble_manifest_dedupes_against_existing_snapshot():
    manifest = gates.assemble_manifest(
        subject="数据结构",
        entries=[_entry(19, "栈的定义与实现", [make_question()])],
        existing_questions=[{"id": 1, "stem": GOOD_STEM}],
        generated_at="2026-10-12T00:00:00+00:00",
    )
    row = manifest["questions"][0]
    assert row["quality_check"]["passed"] is False
    assert row["duplicate_of"] == "existing:1"
    assert manifest["summary"]["existing_references"] == 1


DISTINCT_WORDS = [
    "栈", "队列", "串", "树", "图", "排序", "查找", "散列", "堆", "递归",
    "指针", "结点", "遍历", "插入", "删除", "扩容", "平衡", "哈希", "路径", "连通",
]


def distinct_stem(index: int) -> str:
    """构造彼此差异足够大（G4 不误判）的题干：靠 index 轮换不同知识点词。"""
    first = DISTINCT_WORDS[index % len(DISTINCT_WORDS)]
    second = DISTINCT_WORDS[(index * 7 + 3) % len(DISTINCT_WORDS)]
    third = DISTINCT_WORDS[(index * 11 + 5) % len(DISTINCT_WORDS)]
    return f"围绕{first}与{second}的相互关系，并结合{third}的适用场景，下列说法中正确的是哪一项？"


def test_assemble_manifest_g5b_only_blocks_when_sample_is_large_enough():
    small = [make_question(stem=distinct_stem(index)) for index in range(4)]
    manifest = gates.assemble_manifest(
        subject="数据结构",
        entries=[_entry(19, "栈的定义与实现", small)],
        generated_at="2026-10-12T00:00:00+00:00",
    )
    assert manifest["summary"]["answer_position"]["blocking"] is False
    assert manifest["summary"]["passed"] == 4, manifest["questions"][0]["quality_check"]

    large = [make_question(stem=distinct_stem(index)) for index in range(20)]
    manifest = gates.assemble_manifest(
        subject="数据结构",
        entries=[_entry(19, "栈的定义与实现", large)],
        generated_at="2026-10-12T00:00:00+00:00",
    )
    assert manifest["summary"]["answer_position"]["blocking"] is True
    assert manifest["summary"]["passed"] == 0
    assert manifest["summary"]["by_gate"]["G5B"] == 20


# ---------------------------------------------------------------------------
# CLI：离线重放（零网络）
# ---------------------------------------------------------------------------
def run_cli(*args, cwd=ROOT):
    return subprocess.run(
        [sys.executable, str(CLI_PATH), *args],
        cwd=str(cwd),
        capture_output=True,
        text=False,
        check=False,
    )


@pytest.fixture()
def replay_workspace(tmp_path):
    targets = tmp_path / "targets.json"
    targets.write_text(
        json.dumps(
            {
                "subject": "数据结构",
                "batch": 2,
                "count": 2,
                "target_knowledge_points": ["栈的定义与实现", "队列的定义与实现"],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    (raw_dir / "001.json").write_text(
        raw_payload(
            [
                make_question(),
                make_question(stem="关于循环队列判满与队空条件的叙述，下列哪一项是正确的？"),
            ]
        ),
        encoding="utf-8",
    )
    (raw_dir / "002.json").write_text(
        raw_payload(
            [
                make_question(
                    knowledge_point="队列的定义与实现",
                    stem="队列的入队与出队顺序，下列说法正确的是哪一项？",
                )
            ]
        ),
        encoding="utf-8",
    )
    return targets, raw_dir, tmp_path / "manifest.json"


def test_cli_requires_explicit_mode(tmp_path):
    targets = tmp_path / "t.json"
    targets.write_text('{"subject": "数据结构", "target_knowledge_points": ["栈"]}', encoding="utf-8")
    result = run_cli("--targets", str(targets), "--out", str(tmp_path / "m.json"))
    assert result.returncode == 2


def test_cli_live_requires_raw_dir(tmp_path):
    targets = tmp_path / "t.json"
    targets.write_text('{"subject": "数据结构", "target_knowledge_points": ["栈"]}', encoding="utf-8")
    result = run_cli("--targets", str(targets), "--out", str(tmp_path / "m.json"), "--live")
    assert result.returncode == 2


def test_cli_rejects_missing_targets_file(tmp_path):
    result = run_cli(
        "--targets",
        str(tmp_path / "nope.json"),
        "--raw-dir",
        str(tmp_path),
        "--out",
        str(tmp_path / "m.json"),
    )
    assert result.returncode == 2


def test_cli_replay_end_to_end(replay_workspace):
    targets, raw_dir, out = replay_workspace
    result = run_cli("--targets", str(targets), "--raw-dir", str(raw_dir), "--out", str(out))
    assert result.returncode == 0, result.stdout
    manifest = json.loads(out.read_text(encoding="utf-8"))
    assert manifest["batch"] == 2
    assert manifest["subject"] == "数据结构"
    assert manifest["summary"]["candidates"] == 3
    assert manifest["summary"]["passed"] == 3
    assert manifest["summary"]["concepts_with_error"] == 0
    names = {row["knowledge_point_name"] for row in manifest["questions"]}
    assert names == {"栈的定义与实现", "队列的定义与实现"}
    assert all(row["question_id"].startswith("P43-02-") for row in manifest["questions"])


def test_cli_replay_missing_raw_file_is_recorded_as_error(replay_workspace):
    targets, raw_dir, out = replay_workspace
    (raw_dir / "002.json").unlink()
    result = run_cli("--targets", str(targets), "--raw-dir", str(raw_dir), "--out", str(out))
    assert result.returncode == 0
    manifest = json.loads(out.read_text(encoding="utf-8"))
    assert manifest["summary"]["concepts_with_error"] == 1
    assert "缺少原始响应留档" in manifest["errors"][0]["reason"]


def test_cli_replay_marks_offline_degradation_explicitly(tmp_path):
    targets = tmp_path / "targets.json"
    targets.write_text(
        '{"subject": "数据结构", "target_knowledge_points": ["栈的定义与实现"]}',
        encoding="utf-8",
    )
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    (raw_dir / "001.json").write_text(
        json.dumps(
            {"raw_text": "（离线降级响应）已收到请求：xxx。请在 .env 中配置模型 API Key。"},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    out = tmp_path / "manifest.json"
    result = run_cli("--targets", str(targets), "--raw-dir", str(raw_dir), "--out", str(out))
    manifest = json.loads(out.read_text(encoding="utf-8"))
    assert manifest["summary"]["candidates"] == 0
    assert "G8" in manifest["errors"][0]["reason"]
    # 全部为 0 题时必须非零退出，避免"假成功"
    assert result.returncode == 1


def test_cli_never_touches_database_layers():
    """CLI 只依赖 --out 写文件；不得触碰任何数据库/迁移配置。"""
    text = CLI_PATH.read_text(encoding="utf-8")
    assert "SessionLocal" not in text
    assert "create_engine" not in text
    assert "alembic" not in text.lower()
