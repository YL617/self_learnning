"""Legacy questions.knowledge_point → question_knowledge_points 确定性回填工具。

Phase 2 配套脚本；migration 不携带任何业务数据迁移。

行为约束：
  - 默认 dry-run，只输出统计与明细；显式 --apply 才写库。
  - 仅允许 deterministic exact match：normalize_subject(subject) + clean_name(text)
    与 knowledge_points.normalized_subject/normalized_name 精确相等。
  - 同一 (normalized_subject, normalized_name) 命中多个知识点视为 ambiguous，
    整体拒绝该组并计入统计，绝不猜测。
  - 永远不自动创建 KnowledgePoint。
  - 幂等：已存在的关联跳过；重复运行结果一致。
  - unmatched 只输出清单，不修改任何数据。
  - 旧字段 questions.knowledge_point 不删除、不改写。

用法（在 backend 目录、配置好 DATABASE_URL 后）：
    python ../scripts/backfill_question_knowledge_points.py           # dry-run
    python ../scripts/backfill_question_knowledge_points.py --apply   # 实际写库
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.core.database import SessionLocal
from app.models import KnowledgePoint, Question, QuestionKnowledgePoint
from app.services.knowledge_point_service import (
    clean_name,
    normalize_subject,
)


@dataclass
class BackfillPlan:
    matched: int = 0
    unmatched: int = 0
    ambiguous: int = 0
    already_linked: int = 0
    to_insert: list[tuple[int, int]] = field(default_factory=list)
    unmatched_keys: dict[tuple[str, str], int] = field(default_factory=lambda: defaultdict(int))
    ambiguous_keys: set[tuple[str, str]] = field(default_factory=set)


def build_index(knowledge_points: list) -> dict[tuple[str, str], list[int]]:
    index: dict[tuple[str, str], list[int]] = defaultdict(list)
    for kp in knowledge_points:
        index[(kp.normalized_subject, kp.normalized_name)].append(kp.id)
    return index


def plan_backfill(
    questions: list,
    index: dict[tuple[str, str], list[int]],
    existing: set[tuple[int, int]],
) -> BackfillPlan:
    """纯函数：计算回填计划，绝不修改数据库。"""
    plan = BackfillPlan()
    for question in questions:
        text = (question.knowledge_point or "").strip()
        if not text:
            plan.unmatched += 1
            plan.unmatched_keys[(normalize_subject(question.subject), "<empty>")] += 1
            continue
        key = (normalize_subject(question.subject), clean_name(text))
        hits = index.get(key, [])
        if not hits:
            plan.unmatched += 1
            plan.unmatched_keys[key] += 1
            continue
        if len(hits) > 1:
            plan.ambiguous += 1
            plan.ambiguous_keys.add(key)
            continue
        pair = (question.id, hits[0])
        if pair in existing or pair in plan.to_insert:
            plan.already_linked += 1
            plan.matched += 1
            continue
        plan.matched += 1
        plan.to_insert.append(pair)
    return plan


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="实际写库（默认 dry-run）")
    args = parser.parse_args()

    with SessionLocal() as db:
        questions = list(db.scalars(select(Question)).all())
        knowledge_points = list(db.scalars(select(KnowledgePoint)).all())
        existing = {
            (row.question_id, row.knowledge_point_id)
            for row in db.scalars(select(QuestionKnowledgePoint)).all()
        }
        plan = plan_backfill(questions, build_index(knowledge_points), existing)

        print(f"mode={'APPLY' if args.apply else 'DRY-RUN'}")
        print(f"questions={len(questions)} knowledge_points={len(knowledge_points)}")
        print(f"matched={plan.matched} unmatched={plan.unmatched} ambiguous={plan.ambiguous}")
        print(f"already_linked={plan.already_linked} to_insert={len(plan.to_insert)}")

        if plan.unmatched_keys:
            print("-- unmatched (normalized_subject, normalized_name) -> count")
            for key, count in sorted(plan.unmatched_keys.items()):
                print(f"   {key} -> {count}")
        if plan.ambiguous_keys:
            print("-- ambiguous (refused, no write)")
            for key in sorted(plan.ambiguous_keys):
                print(f"   {key}")

        if not args.apply:
            print("dry-run: no rows written")
            return 0
        if plan.ambiguous_keys:
            print("ABORT: ambiguous matches present; nothing written")
            return 1

        for question_id, kp_id in plan.to_insert:
            db.add(
                QuestionKnowledgePoint(
                    question_id=question_id,
                    knowledge_point_id=kp_id,
                    role="primary",
                    source="legacy",
                )
            )
        db.commit()
        print(f"applied: inserted={len(plan.to_insert)}")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
