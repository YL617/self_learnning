from __future__ import annotations

from typing import Any

from app.services.ai_gateway import AIModelGateway

SYSTEM_PROMPT = (
    "你是高校课程资料分析专家。分析文档切片后返回交互式出题菜单。"
    "只输出 JSON，不要输出解释或 Markdown。"
    'JSON 结构：{"knowledge_points": 5, "completeness": "rich|medium|low", '
    '"message": "...", "menu": [{"question_type": "choice", "count": 5}]}'
)


def _normalize(data: Any, chunk_count: int) -> dict:
    menu: list[dict[str, Any]] = []
    raw_menu = data.get("menu", []) if isinstance(data, dict) else []
    if isinstance(raw_menu, list):
        for item in raw_menu:
            if not isinstance(item, dict):
                continue
            question_type = str(item.get("question_type", "choice")).strip()
            if question_type not in {"choice", "fill", "short_answer"}:
                continue
            try:
                count = max(1, min(20, int(item.get("count") or 1)))
            except (TypeError, ValueError):
                count = 1
            menu.append({"question_type": question_type, "count": count})
    if not menu:
        menu = [
            {"question_type": "choice", "count": min(5, max(1, chunk_count))},
            {"question_type": "fill", "count": 2},
            {"question_type": "short_answer", "count": 1},
        ]
    knowledge_points = 0
    if isinstance(data, dict):
        try:
            knowledge_points = max(1, int(data.get("knowledge_points") or 0))
        except (TypeError, ValueError):
            knowledge_points = 0
    if knowledge_points <= 0:
        knowledge_points = max(1, min(10, chunk_count // 2 + 1))
    completeness = str(data.get("completeness", "")) if isinstance(data, dict) else ""
    if completeness not in {"rich", "medium", "low"}:
        completeness = "rich" if chunk_count >= 8 else "medium" if chunk_count >= 3 else "low"
    message = str(data.get("message", "")) if isinstance(data, dict) else ""
    if not message:
        message = "已分析文档内容，请选择题型组合开始出题。"
    return {
        "knowledge_points": knowledge_points,
        "completeness": completeness,
        "message": message,
        "menu": menu,
    }


def analyze_document(filename: str, chunks: list[str]) -> dict:
    gateway = AIModelGateway()
    user_prompt = (
        f"文档名称：{filename}\n"
        f"文档切片数：{len(chunks)}\n"
        "内容片段：\n" + "\n".join(f"- {chunk[:200]}" for chunk in chunks[:8])
    )
    data = gateway.generate_json(SYSTEM_PROMPT, user_prompt, temperature=0.2)
    return _normalize(data, len(chunks))
