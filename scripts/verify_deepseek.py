"""Real DeepSeek connectivity and output verification."""

from app.core.config import get_settings
from app.services.ai_gateway import AIModelGateway
from app.services.question_generator import generate_questions
from app.services.study_planner import generate_study_plan


def main() -> None:
    settings = get_settings()
    print("provider:", settings.AI_PROVIDER)
    print("key_configured:", bool(settings.DEEPSEEK_API_KEY), "len:", len(settings.DEEPSEEK_API_KEY))

    gateway = AIModelGateway("deepseek")
    chat_text = gateway.chat(
        [{"role": "user", "content": "Reply with exactly: OK"}],
        temperature=0,
    )
    print("chat_fallback:", "离线降级响应" in chat_text)
    print("chat_preview:", repr(chat_text[:120]))

    plan = generate_study_plan(
        "计算机科学与技术",
        "大二",
        "掌握数据结构与算法",
        90,
        2,
        ["数据结构"],
    )
    print("plan_title_len:", len(plan.get("title", "")))
    print("plan_items:", len(plan.get("items", [])))
    first_item = plan.get("items", [{}])[0]
    print("first_item_keys:", sorted(first_item.keys()))

    questions = generate_questions("数据结构", "栈和队列", 3, "choice")
    print("question_count:", len(questions))
    question = questions[0] if questions else {}
    print("question_keys:", sorted(question.keys()))
    print("has_stem:", bool(question.get("stem")))
    print("has_answer:", bool(question.get("answer")))
    print("has_analysis:", bool(question.get("analysis")))
    print("has_options:", bool(question.get("options")))


if __name__ == "__main__":
    main()
