"""M5.5 P4-3.1 —— AI 题目批量生成（离线）→ 质量门禁 → 待审核 manifest。

流水线三段中的前两段：**生成** 与 **门禁**。产出 ``questions_manifest.json``
供人工清单审核（P4-3.2）；**本脚本不写库、不调生产 API、不 publish**。

三种运行姿态（必须显式选择，绝不隐式联网）::

    # ① 离线重放：读已留档的原始响应，零网络 —— 回归与离线环境用
    python scripts/generate_question_batch.py \
        --targets docs/M5.5_P4-3_批1生成目标.json \
        --raw-dir docs/p43_raw/批1 \
        --out     docs/M5.5_P4-3_题目供给清单_批1.json

    # ② 真实生成：需要 .env 中的 AI Key；原始响应**必须**留档到 --raw-dir
    python scripts/generate_question_batch.py \
        --targets docs/M5.5_P4-3_批1生成目标.json \
        --live --raw-dir docs/p43_raw/批1 \
        --out     docs/M5.5_P4-3_题目供给清单_批1.json \
        [--existing docs/M5.5_P4-3_现有题面快照.json]

为什么这样设计：

  - **不复用 ``generate_questions()``**：它只做精确 stem 去重，且 ``_normalize()``
    会对 <40 字解析自动补全（``_ensure_analysis``）——两者都会削弱门禁。本脚本
    改为直连 ``AIModelGateway`` + **自带归一化（不做补全）**，把原始解析留给 G3。
  - **--live 强制留档 --raw-dir**：每次真实生成都可重放，把"模型这次到底吐了什么"
    变成可审计证据（AIR：prompt 再详尽也会产重复题）。
  - **离线降级必须显式判错**：``AIModelGateway.chat()`` 在「无 Key」与「请求异常」
    两条路径都静默返回模板文本；本脚本按 G8 把它记为 ``error``，绝不当作"0 题正常"。
  - **--live 预检 Key**：无 Key 直接退出（码 1），不产出一份"看起来跑了其实全是降级"
    的 manifest。

退出码：``0`` 成功｜``1`` 运行期失败（含 --live 无 Key）｜``2`` 用法错误。
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
BACKEND_DIR = PROJECT_ROOT / "backend"

# 同 scripts/backfill_question_knowledge_points.py：本地直跑时把 backend 挂上 sys.path，
# 才能复用 app.services.* （否则只能从 backend/ 目录运行）。
for _path in (SCRIPT_DIR, BACKEND_DIR):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import p43_gates as gates

# 单次 prompt 的题量上限（对齐 QuestionGenerateRequest.count 的 le=20 口径，
# 并留出充足余量；每 concept 一次调用，宁少而准）。
MAX_PER_CONCEPT = 5

# 在 app 既有 SYSTEM_PROMPT 之外追加的唯一要求：显式难度。
# （G6 拒绝 NULL —— 不允许依赖 evaluation.resolve_difficulty() 按题型兜底。）
DIFFICULTY_INSTRUCTION = (
    "每题必须额外给出 difficulty 字段（字符串），取值只能是 easy、medium、hard 之一，"
    "不得省略、不得为 null。"
)


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


def _fallback(value: Any, default: str) -> str:
    text = str(value or "").strip()
    return text or default


# ---------------------------------------------------------------------------
# 目标与快照
# ---------------------------------------------------------------------------
def distribute(total: int, parts: int) -> list[int]:
    """把 total 尽量平均分成 parts 份，余数给靠前的目标。"""
    if parts <= 0:
        return []
    base, remainder = divmod(max(total, 0), parts)
    return [base + (1 if index < remainder else 0) for index in range(parts)]


def load_targets(path: Path) -> dict[str, Any]:
    """读生成目标。支持两种写法（见设计文档 §4.1）::

        {"subject": "数据结构", "count": 20,
         "target_knowledge_points": ["栈的定义与实现", "队列的定义与实现"]}

        {"subject": "数据结构", "batch": 1,
         "target_knowledge_points": [
             {"name": "栈的定义与实现", "id": 19, "code": "DS.STACKQUEUE.STACK.BASIC",
              "count": 2, "question_type": "choice"}]}
    """
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError("targets 根节点必须是 JSON 对象")
    subject = str(payload.get("subject") or "").strip()
    if not subject:
        raise ValueError("targets 缺少 subject")
    raw_targets = payload.get("target_knowledge_points") or payload.get("targets") or []
    if not isinstance(raw_targets, list) or not raw_targets:
        raise ValueError("targets 缺少 target_knowledge_points")
    default_type = str(payload.get("question_type") or "choice").strip() or "choice"
    total = payload.get("count")
    per_target = distribute(int(total), len(raw_targets)) if total else [None] * len(raw_targets)

    targets: list[dict[str, Any]] = []
    for order, (item, fallback_count) in enumerate(zip(raw_targets, per_target), 1):
        if isinstance(item, str):
            item = {"name": item}
        if not isinstance(item, dict):
            raise TypeError(f"第 {order} 个目标既不是字符串也不是对象")
        name = str(item.get("name") or item.get("knowledge_point") or "").strip()
        if not name:
            raise ValueError(f"第 {order} 个目标缺少 name")
        count = item.get("count") or fallback_count or 1
        count = max(1, min(int(count), MAX_PER_CONCEPT))
        targets.append(
            {
                "order": order,
                "name": name,
                "id": item.get("id") or item.get("knowledge_point_id"),
                "code": item.get("code") or item.get("knowledge_point_code"),
                "count": count,
                "question_type": str(item.get("question_type") or default_type).strip(),
            }
        )
    return {
        "subject": subject,
        "batch": int(payload.get("batch") or 1),
        "targets": targets,
    }


def load_existing(path: Path | None) -> list[dict[str, Any]]:
    """读「现有题库题面快照」用于跨批查重；缺省为空（只做批内查重）。"""
    if path is None:
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("questions") if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        raise TypeError('existing 快照必须是数组或 {"questions": [...]}')
    snapshot: list[dict[str, Any]] = []
    for row in rows:
        if isinstance(row, dict) and str(row.get("stem") or "").strip():
            snapshot.append({"id": row.get("id"), "stem": str(row["stem"])})
    return snapshot


# ---------------------------------------------------------------------------
# 归一化（刻意不复用 _ensure_analysis）
# ---------------------------------------------------------------------------
def normalize_candidates(parsed: Any, subject: str, concept_name: str) -> list[dict[str, Any]]:
    """镜像 ``question_generator._normalize()``，但**保留原始 analysis、不补全**。

    唯一的有意差异：不调用 ``_ensure_analysis()``。G3 必须读模型原样输出的解析，
    否则"<40 字被自动补全"会掩盖低质解析。
    """
    if isinstance(parsed, dict):
        raw = parsed.get("questions") or []
    elif isinstance(parsed, list):
        raw = parsed
    else:
        raw = []
    questions: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict) or not str(item.get("stem") or "").strip():
            continue
        options = item.get("options") if isinstance(item.get("options"), list) else []
        questions.append(
            {
                "subject": _fallback(item.get("subject"), subject),
                "knowledge_point": _fallback(item.get("knowledge_point"), concept_name),
                "question_type": _fallback(item.get("question_type"), "choice"),
                "stem": str(item["stem"]).strip(),
                "options": [str(opt).strip() for opt in options if str(opt).strip()],
                "answer": str(item.get("answer", "")).strip(),
                "analysis": str(item.get("analysis", "")).strip(),
                "difficulty": item.get("difficulty"),
            }
        )
    return questions


def entry_from_raw(
    target: dict[str, Any], subject: str, raw_text: str | None, *, parse_json
) -> dict[str, Any]:
    """把一段原始响应变成一条 entry；任何异常都记 ``error``（禁止静默跳过）。"""
    base = {
        "concept": {
            "id": target.get("id"),
            "name": target["name"],
            "code": target.get("code"),
            "order": target["order"],
        },
        "question_type": target["question_type"],
        "questions": [],
        "raw_analysis": {},
    }
    reason = gates.offline_reason(raw_text)
    if reason:
        return {**base, "error": reason}
    parsed = parse_json(raw_text or "")
    if parsed is None:
        return {**base, "error": "G8 响应无法解析为 JSON（既非对象也非数组）"}
    questions = normalize_candidates(parsed, subject, target["name"])
    if not questions:
        return {**base, "error": "G8 解析后 0 题（模型未产出含题干的可用项）"}
    return {
        **base,
        "error": None,
        "questions": questions,
        "raw_analysis": {index: item["analysis"] for index, item in enumerate(questions)},
    }


def _parse_json(text: str) -> Any:
    """复用生产同款解析器，保证重放与线上语义一致。"""
    from app.services.ai_gateway import extract_json

    return extract_json(text)


# ---------------------------------------------------------------------------
# 采集：重放 / 真实生成
# ---------------------------------------------------------------------------
def raw_path(raw_dir: Path, order: int) -> Path:
    """原始响应留档路径：按目标顺序编号（避免中文文件名在 Windows/docker 上踩坑）。"""
    return raw_dir / f"{order:03d}.json"


def collect_replay(
    targets: list[dict[str, Any]], subject: str, raw_dir: Path
) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for target in targets:
        path = raw_path(raw_dir, target["order"])
        if not path.is_file():
            entries.append(
                {
                    "concept": {
                        "id": target.get("id"),
                        "name": target["name"],
                        "code": target.get("code"),
                        "order": target["order"],
                    },
                    "question_type": target["question_type"],
                    "questions": [],
                    "raw_analysis": {},
                    "error": f"缺少原始响应留档 {path.name}",
                }
            )
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, dict) and "raw_text" in payload:
            raw_text = payload["raw_text"]
        else:
            # 允许直接放一段"已解析好的"JSON（人工构造 fixture 更省事）；
            # 重新序列化后走同一条判定路径，G8 仍按文本指纹判定。
            raw_text = json.dumps(payload, ensure_ascii=False)
        entries.append(entry_from_raw(target, subject, raw_text, parse_json=_parse_json))
    return entries


def assert_live_ready(provider: str | None) -> None:
    """--live 预检：无 Key 立即失败，不产出"假成功"manifest。"""
    from app.services.ai_gateway import AIModelGateway

    gateway = AIModelGateway(provider)
    if not gateway.config["api_key"]:
        raise RuntimeError(
            f"AI provider「{gateway.provider}」未配置 API Key；"
            "拒绝在无 Key 情况下运行 --live（否则会得到一整份离线降级 manifest）。"
            "请改用 --raw-dir 重放，或先在 .env 配置 Key。"
        )


def collect_live(
    targets: list[dict[str, Any]],
    subject: str,
    raw_dir: Path,
    provider: str | None,
    sleep_seconds: float,
) -> list[dict[str, Any]]:
    from app.services.ai_gateway import AIModelGateway
    from app.services.content_filter import validate_text
    from app.services.question_generator import SYSTEM_PROMPT

    gateway = AIModelGateway(provider)
    raw_dir.mkdir(parents=True, exist_ok=True)
    system_prompt = f"{SYSTEM_PROMPT}{DIFFICULTY_INSTRUCTION}"
    entries: list[dict[str, Any]] = []
    for index, target in enumerate(targets):
        if index:
            time.sleep(max(sleep_seconds, 0.0))
        try:
            validate_text(target["name"])
        except ValueError as exc:
            entries.append(
                {
                    "concept": {
                        "id": target.get("id"),
                        "name": target["name"],
                        "code": target.get("code"),
                        "order": target["order"],
                    },
                    "question_type": target["question_type"],
                    "questions": [],
                    "raw_analysis": {},
                    "error": f"内容校验未通过：{exc}",
                }
            )
            continue
        user_prompt = (
            f"学科：{subject}\n知识点：{target['name']}\n"
            f"题型：{target['question_type']}\n数量：{target['count']}"
        )
        raw_text = gateway.chat(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.4,
        )
        raw_path(raw_dir, target["order"]).write_text(
            json.dumps(
                {
                    "concept": target["name"],
                    "provider": gateway.provider,
                    "model": gateway.config["model"],
                    "user_prompt": user_prompt,
                    "raw_text": raw_text,
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        entries.append(entry_from_raw(target, subject, raw_text, parse_json=_parse_json))
    return entries


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="M5.5 P4-3.1 离线题目生成 + 质量门禁 → manifest（不写库）"
    )
    parser.add_argument("--targets", required=True, type=Path, help="生成目标 JSON")
    parser.add_argument("--out", required=True, type=Path, help="manifest 输出路径")
    parser.add_argument("--raw-dir", type=Path, default=None, help="原始响应留档目录")
    parser.add_argument("--live", action="store_true", help="联网真实生成（需 API Key）")
    parser.add_argument("--provider", default=None, help="ai provider（deepseek/qwen/glm）")
    parser.add_argument("--existing", type=Path, default=None, help="现有题面快照（跨批查重）")
    parser.add_argument("--batch", type=int, default=None, help="批次号（覆盖 targets 里的 batch）")
    parser.add_argument("--sleep", type=float, default=1.0, help="--live 每次调用间隔秒")
    parser.add_argument("--id-prefix", default="P43", help="临时题号前缀")
    return parser.parse_args(argv)


def print_summary(manifest: dict[str, Any]) -> None:
    summary = manifest["summary"]
    print("=" * 62)
    print(f"batch={manifest['batch']}  subject={manifest['subject']}  schema={manifest['schema_version']}")
    print(
        f"concept={summary['concepts']}  候选={summary['candidates']}  "
        f"通过={summary['passed']}  拒绝={summary['failed']}  生成失败={summary['concepts_with_error']}"
    )
    print(f"命中门禁：{summary['by_gate'] or '{}'}")
    print(f"答案位置：{summary['answer_position']['counts']}")
    for error in manifest["errors"]:
        print(f"  [ERROR] {error['concept_name']}：{error['reason']}")
    print("=" * 62)


def main(argv: list[str] | None = None) -> int:
    _utf8_stdout()
    args = parse_args(argv)
    if not args.live and args.raw_dir is None:
        print("用法错误：必须显式指定 --live 或 --raw-dir（本脚本绝不隐式联网）", file=sys.stderr)
        return 2
    if args.live and args.raw_dir is None:
        print("用法错误：--live 必须配合 --raw-dir（原始响应必须留档以便重放）", file=sys.stderr)
        return 2
    try:
        config = load_targets(args.targets)
        existing = load_existing(args.existing)
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        print(f"用法错误：{exc}", file=sys.stderr)
        return 2

    subject = config["subject"]
    targets = config["targets"]
    batch = args.batch if args.batch is not None else config["batch"]

    try:
        if args.live:
            assert_live_ready(args.provider)
            entries = collect_live(targets, subject, args.raw_dir, args.provider, args.sleep)
        else:
            entries = collect_replay(targets, subject, args.raw_dir)
    except RuntimeError as exc:
        print(f"运行失败：{exc}", file=sys.stderr)
        return 1

    manifest = gates.assemble_manifest(
        subject=subject,
        entries=entries,
        existing_questions=existing,
        generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        batch=batch,
        id_prefix=args.id_prefix,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print_summary(manifest)
    print(f"manifest 已写出：{args.out}")
    if manifest["summary"]["candidates"] == 0:
        print("警告：本次候选题为 0，manifest 不含任何可审核题目。", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
