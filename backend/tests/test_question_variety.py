from app.services.ai_gateway import AIModelGateway
from app.services.question_generator import (
    _fallback_questions,
    _variant_questions,
    generate_questions,
)


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


def test_variant_questions_are_distinct_and_different_from_original():
    reference = {
        "subject": "Data Structures",
        "knowledge_point": "Stack",
        "stem": "Which operation removes an element from a stack?",
        "options": ["A. push", "B. pop", "C. peek", "D. enqueue"],
        "answer": "B",
        "analysis": "pop removes the top element.",
    }
    questions = _variant_questions(reference, 3, "choice")
    assert len(questions) == 3
    stems = [q["stem"] for q in questions]
    assert len(set(stems)) == 3
    assert reference["stem"] not in stems
    option_sets = [tuple(q["options"]) for q in questions]
    assert len(set(option_sets)) == 3


def test_generate_with_reference_fallback(monkeypatch):
    monkeypatch.setattr(AIModelGateway, "generate_json", lambda *args, **kwargs: {})
    reference = {
        "subject": "Data Structures",
        "knowledge_point": "Stack",
        "stem": "Original stem",
        "options": ["A. push", "B. pop", "C. peek", "D. enqueue"],
        "answer": "B",
        "analysis": "Analysis",
    }
    questions = generate_questions(
        "Data Structures",
        "Stack",
        3,
        "choice",
        reference=reference,
    )
    assert len(questions) == 3
    assert len({q["stem"] for q in questions}) == 3
    assert reference["stem"] not in [q["stem"] for q in questions]


def test_api_generate_with_reference(client):
    register = client.post(
        "/api/v1/auth/register",
        json={
            "email": "variant@example.com",
            "username": "variantuser",
            "password": "123456",
        },
    )
    token = register.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    original = client.post(
        "/api/v1/questions/generate",
        headers=headers,
        json={
            "subject": "Data Structures",
            "knowledge_point": "Stack",
            "count": 1,
            "question_type": "choice",
        },
    ).json()[0]

    response = client.post(
        "/api/v1/questions/generate",
        headers=headers,
        json={
            "subject": "Data Structures",
            "knowledge_point": "Stack",
            "count": 3,
            "question_type": "choice",
            "reference_question_id": original["id"],
        },
    )
    assert response.status_code == 201
    questions = response.json()
    assert len(questions) == 3
    assert len({q["stem"] for q in questions}) == 3
    assert original["stem"] not in [q["stem"] for q in questions]
