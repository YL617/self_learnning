from __future__ import annotations

import re
from typing import Any

from app.services.ai_gateway import AIModelGateway

SYSTEM_PROMPT = (
    "你是高校出题专家。根据学科、知识点和参考资料生成练习题，"
    "只输出 JSON 数组，不要输出任何解释或 Markdown。"
    "每题结构：{\"subject\": \"...\", \"knowledge_point\": \"...\", "
    "\"question_type\": \"choice|fill|short_answer\", \"stem\": \"...\", "
    "\"options\": [\"A. ...\", \"B. ...\"], \"answer\": \"...\", \"analysis\": \"...\"}"
)


def _fallback_questions(
    subject: str,
    knowledge_point: str,
    count: int,
    question_type: str,
) -> list[dict[str, Any]]:
    size = min(count, 5)
    stem = (
        f"关于「{knowledge_point}」，下列描述最准确的是？"
        if question_type == "choice"
        else f"请简述「{knowledge_point}」的核心要点。"
    )
    options = ["A. 教材标准表述", "B. 常见错误表述", "C. 拓展理解", "D. 以上都不对"]
    return [
        {
            "subject": subject,
            "knowledge_point": knowledge_point,
            "question_type": question_type,
            "stem": stem,
            "options": options if question_type == "choice" else [],
            "answer": "A" if question_type == "choice" else f"围绕{knowledge_point}的核心概念进行说明",
            "analysis": f"请结合{subject}教材确认「{knowledge_point}」的准确表述，并记录复习要点。",
        }
        for _ in range(size)
    ]


def _normalize(raw: Any, subject: str, knowledge_point: str) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        raw = raw.get("questions", []) if isinstance(raw, dict) else []
    questions: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict) or not item.get("stem"):
            continue
        options = item.get("options") if isinstance(item.get("options"), list) else []
        questions.append(
            {
                "subject": str(item.get("subject", subject)).strip(),
                "knowledge_point": str(item.get("knowledge_point", knowledge_point)).strip(),
                "question_type": str(item.get("question_type", "choice")).strip(),
                "stem": str(item["stem"]).strip(),
                "options": [str(opt).strip() for opt in options if str(opt).strip()],
                "answer": str(item.get("answer", "")).strip(),
                "analysis": str(item.get("analysis", "")).strip(),
            }
        )
    return questions


def generate_questions(
    subject: str,
    knowledge_point: str,
    count: int,
    question_type: str = "choice",
    context: list[str] | None = None,
) -> list[dict[str, Any]]:
    context_text = ""
    if context:
        context_text = "\n参考资料（只能基于以下内容出题）：\n" + "\n".join(
            f"- {item[:500]}" for item in context[:5]
        )
    user_prompt = (
        f"学科：{subject}\n知识点：{knowledge_point}\n题型：{question_type}\n数量：{count}"
        + context_text
    )
    gateway = AIModelGateway()
    data = gateway.generate_json(SYSTEM_PROMPT, user_prompt, temperature=0.4)
    questions = _normalize(data, subject, knowledge_point)
    if not questions:
        questions = _fallback_questions(subject, knowledge_point, count, question_type)
    return questions[:count]


def check_answer(question: Any, user_answer: str) -> bool:
    answer = str(question.answer or "").strip().lower()
    submitted = user_answer.strip().lower()
    if not answer:
        return False
    if question.question_type == "choice":
        return submitted.startswith(answer[:1])
    if question.question_type == "fill":
        return answer in submitted or submitted in answer
    answer_tokens = {w for w in re.split(r"[\s，。；、,.;]+", answer) if len(w) > 1}
    submitted_tokens = {w for w in re.split(r"[\s，。；、,.;]+", submitted) if len(w) > 1}
    if not answer_tokens:
        return False
    return len(answer_tokens & submitted_tokens) / len(answer_tokens) >= 0.5
