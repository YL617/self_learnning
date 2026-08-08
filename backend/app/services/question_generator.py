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
)


def _fallback_questions(
    subject: str,
    knowledge_point: str,
    count: int,
    question_type: str,
) -> list[dict[str, Any]]:
    size = min(count, 5)
    options = ["A. 教材标准表述", "B. 常见错误表述", "C. 拓展理解", "D. 以上都不对"]
    choice_stems = [
        f"关于「{knowledge_point}」，下列说法最准确的是？",
        f"在{subject}中，「{knowledge_point}」的核心特征是什么？",
        f"下列哪项最能体现「{knowledge_point}」的特点？",
        f"关于「{knowledge_point}」的应用场景，正确的是？",
        f"对「{knowledge_point}」的理解，下列说法错误的是？",
    ]
    open_stems = [
        f"请简述「{knowledge_point}」的核心概念。",
        f"请说明「{knowledge_point}」的主要特点。",
        f"请举例说明「{knowledge_point}」的典型应用。",
        f"请总结「{knowledge_point}」的常见易错点。",
        f"请用自己的话解释「{knowledge_point}」。",
    ]
    stems = choice_stems if question_type == "choice" else open_stems
    questions: list[dict[str, Any]] = []
    for index in range(size):
        questions.append(
            {
                "subject": subject,
                "knowledge_point": knowledge_point,
                "question_type": question_type,
                "stem": stems[index],
                "options": options if question_type == "choice" else [],
                "answer": "A" if question_type == "choice" else f"围绕{knowledge_point}的核心概念进行说明",
                "analysis": (
                    f"请结合{subject}教材确认「{knowledge_point}」的准确表述，"
                    f"并记录第 {index + 1} 个复习要点。"
                ),
            }
        )
    return questions


def _variant_questions(
    reference: dict[str, Any],
    count: int,
    question_type: str,
) -> list[dict[str, Any]]:
    subject = str(reference.get("subject", "")).strip() or "综合"
    knowledge_point = str(reference.get("knowledge_point", "")).strip()
    original_stem = str(reference.get("stem", "")).strip()
    size = min(count, 5)

    if question_type == "choice":
        variant_sets = [
            {
                "stem": f"关于「{knowledge_point}」，下列说法最准确的是？",
                "options": ["A. 教材标准表述", "B. 常见错误表述", "C. 拓展理解", "D. 以上都不对"],
                "answer": "A",
            },
            {
                "stem": f"「{knowledge_point}」的核心特点是？",
                "options": ["A. 定义明确、结构清晰", "B. 实现方式不唯一", "C. 依赖具体语言", "D. 没有固定规律"],
                "answer": "A",
            },
            {
                "stem": f"学习「{knowledge_point}」时，最容易出现的错误是？",
                "options": ["A. 混淆相关概念", "B. 忽略基础定义", "C. 死记硬背", "D. 以上都是"],
                "answer": "D",
            },
            {
                "stem": f"「{knowledge_point}」的典型应用场景是？",
                "options": ["A. 教材示例", "B. 实际问题求解", "C. 竞赛题目", "D. 以上都是"],
                "answer": "D",
            },
            {
                "stem": f"「{knowledge_point}」在考试中的常见考法是？",
                "options": ["A. 概念辨析", "B. 原理推导", "C. 综合应用", "D. 以上都是"],
                "answer": "D",
            },
        ]
        questions: list[dict[str, Any]] = []
        used_stems: set[str] = set()
        for index in range(size):
            item = None
            for candidate in variant_sets:
                if (
                    candidate["stem"] != original_stem
                    and candidate["stem"] not in used_stems
                ):
                    item = candidate
                    break
            if item is None:
                item = variant_sets[index]
            used_stems.add(item["stem"])
            questions.append(
                {
                    "subject": subject,
                    "knowledge_point": knowledge_point,
                    "question_type": "choice",
                    "stem": item["stem"],
                    "options": item["options"],
                    "answer": item["answer"],
                    "analysis": (
                        f"本题为「{knowledge_point}」的变体题，原始题干："
                        f"{original_stem[:80]}"
                    ),
                }
            )
        return questions

    open_templates = [
        f"请结合「{knowledge_point}」的定义进行说明。",
        f"请总结「{knowledge_point}」的主要特点。",
        f"请举例说明「{knowledge_point}」的典型应用。",
        f"请分析「{knowledge_point}」的常见易错点。",
        f"请解释「{knowledge_point}」与相关概念的区别。",
    ]
    stem_candidates = [stem for stem in open_templates if stem != original_stem]
    if len(stem_candidates) < size:
        stem_candidates = (stem_candidates + open_templates)[:size]
    return [
        {
            "subject": subject,
            "knowledge_point": knowledge_point,
            "question_type": question_type,
            "stem": stem_candidates[index],
            "options": [],
            "answer": f"围绕「{knowledge_point}」的核心概念，参考原始题目：{original_stem[:60]}",
            "analysis": f"本题为「{knowledge_point}」的变体题，请结合{subject}教材确认。",
        }
        for index in range(size)
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
        questions = (
            _variant_questions(reference, count, question_type)
            if reference
            else _fallback_questions(subject, knowledge_point, count, question_type)
        )
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for question in questions:
        stem = str(question.get("stem", "")).strip()
        if stem and stem not in seen:
            seen.add(stem)
            unique.append(question)
    fallback = (
        _variant_questions(reference, count, question_type)
        if reference
        else _fallback_questions(subject, knowledge_point, count, question_type)
    )
    for question in fallback:
        if len(unique) >= count:
            break
        stem = str(question.get("stem", "")).strip()
        if stem and stem not in seen:
            seen.add(stem)
            unique.append(question)
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
