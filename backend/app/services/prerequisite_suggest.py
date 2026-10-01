"""LLM 前置关系「提议」器：**只提议，绝不落库**。

范式来源：MoocRadar（SIGIR 2023）用「LLM 自动抽取 + 专家标注修正」构建概念前置关系。
本项目照搬这个流水线：LLM 只输出候选与理由，是否需要、强度多少、是否落库
全部由管理员在前端确认，数值与写入权都不交给模型。
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import KnowledgePoint
from app.services.ai_gateway import AIModelGateway
from app.services.prerequisite import KnowledgePointNotFound, PrerequisiteService

SUGGEST_LIMIT = 5
CANDIDATE_LIMIT = 40
DEFAULT_CONFIDENCE = 0.5
MIN_CONFIDENCE = 0.0
MAX_CONFIDENCE = 1.0
MAX_REASON_LENGTH = 200

SYSTEM_PROMPT = (
    "你是学科知识图谱专家。给定一个目标知识点和候选知识点列表，"
    "判断哪些候选是学习目标知识点之前**必须先掌握**的前置知识。"
    "只输出 JSON，不要输出任何解释或 Markdown。"
    'JSON 结构：{"suggestions":[{"prerequisite_id":1,"reason":"...","confidence":0.8}]}'
)


def _candidates(
    service: PrerequisiteService, knowledge_point: KnowledgePoint
) -> list[KnowledgePoint]:
    """候选 = 其它活跃知识点，排除已存在的前置、以及会成环的节点。"""
    existing = {
        edge.prerequisite_id
        for edge in service.list_for(knowledge_point.id, include_disabled=True)
    }
    rows = service.db.scalars(
        select(KnowledgePoint)
        .where(
            KnowledgePoint.status == "active",
            KnowledgePoint.id != knowledge_point.id,
        )
        .order_by(KnowledgePoint.normalized_subject, KnowledgePoint.id)
    ).all()
    same_subject = [r for r in rows if r.normalized_subject == knowledge_point.normalized_subject]
    others = [r for r in rows if r.normalized_subject != knowledge_point.normalized_subject]
    picked: list[KnowledgePoint] = []
    for row in same_subject + others:
        if row.id in existing:
            continue
        if service.would_create_cycle(knowledge_point.id, row.id):
            continue
        picked.append(row)
        if len(picked) >= CANDIDATE_LIMIT:
            break
    return picked


def suggest_prerequisites(
    db: Session,
    knowledge_point_id: int,
    *,
    limit: int = SUGGEST_LIMIT,
) -> tuple[list[dict], str | None]:
    """返回 (建议列表, 提示语)。建议列表为空时提示语说明原因。"""
    service = PrerequisiteService(db)
    knowledge_point = db.get(KnowledgePoint, knowledge_point_id)
    if knowledge_point is None:
        raise KnowledgePointNotFound("知识点不存在")

    candidates = _candidates(service, knowledge_point)
    if not candidates:
        return [], "没有可用的候选知识点（可能都已建立前置关系）"

    listing = "\n".join(
        f"- id={row.id} 学科={row.subject} 知识点={row.name}" for row in candidates
    )
    prompt = (
        f"目标知识点：学科={knowledge_point.subject} 名称={knowledge_point.name}\n"
        f"候选知识点：\n{listing}\n\n"
        f"请最多给出 {limit} 个前置知识点，并说明理由与置信度（0~1）。"
    )
    data = AIModelGateway().generate_json(SYSTEM_PROMPT, prompt)
    raw = data.get("suggestions") if isinstance(data, dict) else None
    if not isinstance(raw, list):
        return [], "AI 未返回可用的前置建议，请手工添加"

    allowed = {row.id: row for row in candidates}
    suggestions: list[dict] = []
    seen: set[int] = set()
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        try:
            candidate_id = int(entry.get("prerequisite_id"))
        except (TypeError, ValueError):
            continue
        if candidate_id not in allowed or candidate_id in seen:
            continue
        try:
            confidence = float(entry.get("confidence", DEFAULT_CONFIDENCE))
        except (TypeError, ValueError):
            confidence = DEFAULT_CONFIDENCE
        confidence = min(max(confidence, MIN_CONFIDENCE), MAX_CONFIDENCE)
        reason = str(entry.get("reason") or "").strip()[:MAX_REASON_LENGTH]
        seen.add(candidate_id)
        suggestions.append(
            {
                "prerequisite_id": candidate_id,
                "prerequisite_name": allowed[candidate_id].name,
                "reason": reason or "AI 提议（无理由）",
                "confidence": round(confidence, 2),
            }
        )
        if len(suggestions) >= limit:
            break

    suggestions.sort(key=lambda item: (-item["confidence"], item["prerequisite_id"]))
    if not suggestions:
        return [], "AI 建议均未通过校验，请手工添加"
    return suggestions, None


__all__ = ["SUGGEST_LIMIT", "suggest_prerequisites"]
