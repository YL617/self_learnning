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


def _generate_questions(client, headers: dict) -> list[dict]:
    response = client.post(
        "/api/v1/questions/generate",
        headers=headers,
        json={
            "subject": "Data Structures",
            "knowledge_point": "Stack",
            "count": 2,
            "question_type": "choice",
        },
    )
    assert response.status_code == 201
    return response.json()


def test_toggle_question_favorite(client):
    auth = _register(client, "fav@example.com", "favuser")
    headers = {"Authorization": f"Bearer {auth['access_token']}"}
    questions = _generate_questions(client, headers)
    question_id = questions[0]["id"]

    response = client.patch(
        f"/api/v1/questions/{question_id}/favorite",
        headers=headers,
        json={"is_favorite": True},
    )
    assert response.status_code == 200
    assert response.json()["is_favorite"] is True

    listed = client.get("/api/v1/questions", headers=headers).json()
    favorited = [item for item in listed if item["id"] == question_id]
    assert favorited and favorited[0]["is_favorite"] is True


def test_delete_question_cleans_related_records(client):
    auth = _register(client, "qdel@example.com", "qdeluser")
    headers = {"Authorization": f"Bearer {auth['access_token']}"}
    questions = _generate_questions(client, headers)
    question_id = questions[0]["id"]

    client.post(
        f"/api/v1/questions/{question_id}/answers",
        headers=headers,
        json={"user_answer": "wrong"},
    )
    assert client.get("/api/v1/wrong-book", headers=headers).json()

    response = client.delete(f"/api/v1/questions/{question_id}", headers=headers)
    assert response.status_code == 204
    listed = client.get("/api/v1/questions", headers=headers).json()
    assert question_id not in [item["id"] for item in listed]
    assert client.get("/api/v1/wrong-book", headers=headers).json() == []


def test_question_actions_require_owner(client):
    owner = _register(client, "qowner@example.com", "qowneruser")
    other = _register(client, "qother@example.com", "qotheruser")
    owner_headers = {"Authorization": f"Bearer {owner['access_token']}"}
    other_headers = {"Authorization": f"Bearer {other['access_token']}"}
    question_id = _generate_questions(client, owner_headers)[0]["id"]

    favorite = client.patch(
        f"/api/v1/questions/{question_id}/favorite",
        headers=other_headers,
        json={"is_favorite": True},
    )
    assert favorite.status_code == 404

    delete = client.delete(f"/api/v1/questions/{question_id}", headers=other_headers)
    assert delete.status_code == 404
