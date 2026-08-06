from datetime import date, timedelta


def _register(client, email: str, username: str) -> dict:
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "username": username,
            "password": "123456",
        },
    )
    assert response.status_code == 201
    return response.json()


def _make_wrong_item(client, headers: dict) -> dict:
    questions = client.post(
        "/api/v1/questions/generate",
        headers=headers,
        json={
            "subject": "Data Structures",
            "knowledge_point": "Queue",
            "count": 1,
            "question_type": "choice",
        },
    ).json()
    client.post(
        f"/api/v1/questions/{questions[0]['id']}/answers",
        headers=headers,
        json={"user_answer": "wrong"},
    )
    return client.get("/api/v1/wrong-book", headers=headers).json()[0]


def test_wrong_item_gets_ebbinghaus_schedule(client):
    auth = _register(client, "review@example.com", "reviewuser")
    headers = {"Authorization": f"Bearer {auth['access_token']}"}
    item = _make_wrong_item(client, headers)

    assert item["review_stage"] == 1
    assert item["next_review_date"] == (date.today() + timedelta(days=1)).isoformat()

    reviewed = client.patch(
        f"/api/v1/wrong-book/{item['id']}",
        headers=headers,
        json={"mastered": False},
    ).json()
    assert reviewed["review_stage"] == 2
    assert reviewed["next_review_date"] == (date.today() + timedelta(days=3)).isoformat()


def test_due_review_endpoint(client):
    auth = _register(client, "due@example.com", "dueuser")
    headers = {"Authorization": f"Bearer {auth['access_token']}"}
    item = _make_wrong_item(client, headers)
    assert client.get("/api/v1/wrong-book/review", headers=headers).json() == []

    from app.core.database import SessionLocal
    from app.models import WrongBookItem

    with SessionLocal() as db:
        row = db.get(WrongBookItem, item["id"])
        row.next_review_date = date.today() - timedelta(days=1)
        db.commit()

    due = client.get("/api/v1/wrong-book/review", headers=headers).json()
    assert len(due) == 1
    assert due[0]["id"] == item["id"]
