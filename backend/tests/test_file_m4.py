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


def _upload_txt(client, headers: dict, name: str, content: bytes) -> dict:
    response = client.post(
        "/api/v1/files/upload",
        headers=headers,
        files={"file": (name, content, "text/plain")},
    )
    assert response.status_code == 201
    return response.json()


def test_analyze_and_question_plan(client):
    auth = _register(client, "filem4@example.com", "filem4")
    headers = {"Authorization": f"Bearer {auth['access_token']}"}
    content = ("数据结构第1章 栈与队列。\n" * 20).encode("utf-8")
    document = _upload_txt(client, headers, "ds.txt", content)

    parsed = client.post(f"/api/v1/files/{document['id']}/parse", headers=headers)
    assert parsed.status_code == 200

    analysis = client.post(f"/api/v1/files/{document['id']}/analyze", headers=headers)
    assert analysis.status_code == 200
    payload = analysis.json()
    assert payload["knowledge_points"] >= 1
    assert payload["menu"]

    response = client.post(
        f"/api/v1/files/{document['id']}/questions",
        headers=headers,
        json={
            "question_plan": [
                {"question_type": "choice", "count": 2},
                {"question_type": "fill", "count": 1},
            ]
        },
    )
    assert response.status_code == 201
    questions = response.json()
    assert len(questions) == 3
    assert {q["question_type"] for q in questions} == {"choice", "fill"}


def test_upload_quota(client):
    auth = _register(client, "quota@example.com", "quota")
    headers = {"Authorization": f"Bearer {auth['access_token']}"}
    for index in range(5):
        _upload_txt(client, headers, f"file{index}.txt", b"x" * 100)

    response = client.post(
        "/api/v1/files/upload",
        headers=headers,
        files={"file": ("sixth.txt", b"x" * 100, "text/plain")},
    )
    assert response.status_code == 400
