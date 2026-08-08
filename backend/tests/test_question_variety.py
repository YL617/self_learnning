from app.services.ai_gateway import AIModelGateway
from app.services.question_generator import _fallback_questions, generate_questions


def test_fallback_questions_are_distinct():
    questions = _fallback_questions("Data Structures", "Stack", 3, "choice")
    assert len(questions) == 3
    assert len({q["stem"] for q in questions}) == 3


def test_generate_questions_fallback_distinct(monkeypatch):
    monkeypatch.setattr(AIModelGateway, "generate_json", lambda *args, **kwargs: {})
    questions = generate_questions("Data Structures", "Stack", 3, "choice")
    assert len(questions) == 3
    assert len({q["stem"] for q in questions}) == 3


def test_generate_questions_dedupes_ai_output(monkeypatch):
    duplicate = {
        "subject": "Data Structures",
        "knowledge_point": "Stack",
        "question_type": "choice",
        "stem": "Same stem",
        "options": ["A. 1", "B. 2", "C. 3", "D. 4"],
        "answer": "A",
        "analysis": "Same analysis",
    }
    monkeypatch.setattr(
        AIModelGateway,
        "generate_json",
        lambda *args, **kwargs: [duplicate, duplicate, duplicate],
    )
    questions = generate_questions("Data Structures", "Stack", 3, "choice")
    assert len(questions) == 3
    assert len({q["stem"] for q in questions}) == 3
