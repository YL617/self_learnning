from __future__ import annotations

import re
from typing import Any

from app.services.ai_gateway import AIModelGateway

SYSTEM_PROMPT = (
    "你是高校出题专家。根据学科、知识点和参考资料生成练习题，"
    "必须生成多道互不相同的题目，严禁重复题干。"
    "若提供了原始题目，必须生成与原始题目知识点相同、但情境、选项顺序、干扰项和问法都不同的变体题，严禁照抄原始题目。"
    "只输出 JSON 数组，不要输出任何解释或 Markdown。"
    "每题结构：{\"subject\": \"...\", \"knowledge_point\": \"...\", "
    "\"question_type\": \"choice|fill|short_answer\", \"stem\": \"...\", "
    "\"options\": [\"A. ...\", \"B. ...\"], \"answer\": \"...\", \"analysis\": \"...\"}"
    "解析必须包含：正确答案的依据、错误选项的辨析、常见易错点、复习建议，且不少于 60 个汉字。"
)


def _ensure_analysis(analysis: str, subject: str, knowledge_point: str) -> str:
    hint = (
        f"复习提示：请结合{subject}教材确认「{knowledge_point}」的定义、"
        "应用场景与常见错误。"
    )
    if not analysis:
        return hint
    if len(analysis) < 40:
        return f"{analysis} {hint}"
    return analysis


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
                "analysis": _ensure_analysis(
                    str(item.get("analysis", "")).strip(),
                    subject,
                    knowledge_point,
                ),
            }
        )
    return questions


def generate_questions(
    subject: str,
    knowledge_point: str,
    count: int,
    question_type: str = "choice",
    context: list[str] | None = None,
    reference: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    context_text = ""
    if context:
        context_text = "\n参考资料（只能基于以下内容出题）：\n" + "\n".join(
            f"- {item[:500]}" for item in context[:5]
        )
    original_text = ""
    if reference:
        original_text = (
            f"\n原始题目：\n题干：{reference.get('stem', '')}\n"
            f"选项：{reference.get('options', [])}\n"
            f"答案：{reference.get('answer', '')}\n"
            f"解析：{reference.get('analysis', '')}"
        )
    user_prompt = (
        f"学科：{subject}\n知识点：{knowledge_point}\n题型：{question_type}\n数量：{count}"
        + original_text
        + context_text
    )
    gateway = AIModelGateway()
    data = gateway.generate_json(SYSTEM_PROMPT, user_prompt, temperature=0.4)
    questions = _normalize(data, subject, knowledge_point)
    if not questions:
        raise RuntimeError("AI 服务暂不可用，请稍后重试")

    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for question in questions:
        stem = str(question.get("stem", "")).strip()
        if stem and stem not in seen:
            seen.add(stem)
            unique.append(question)
    if not unique:
        raise RuntimeError("AI 服务暂不可用，请稍后重试")
    return unique[:count]


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
