import pytest

from app.services.ai_gateway import AIModelGateway
from app.services.question_generator import generate_questions


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
    assert len(questions) == 1


def test_generate_questions_raises_when_ai_unavailable(monkeypatch):
    monkeypatch.setattr(AIModelGateway, "generate_json", lambda *args, **kwargs: {})
    with pytest.raises(RuntimeError):
        generate_questions("Data Structures", "Stack", 3, "choice")


def test_api_generate_returns_502_when_ai_unavailable(client, monkeypatch):
    register = client.post(
        "/api/v1/auth/register",
        json={
            "email": "ai502@example.com",
            "username": "ai502",
            "password": "123456",
        },
    )
    headers = {"Authorization": f"Bearer {register.json()['access_token']}"}
    monkeypatch.setattr(AIModelGateway, "generate_json", lambda *args, **kwargs: {})
    response = client.post(
        "/api/v1/questions/generate",
        headers=headers,
        json={
            "subject": "Data Structures",
            "knowledge_point": "Stack",
            "count": 3,
            "question_type": "choice",
        },
    )
    assert response.status_code == 502


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
