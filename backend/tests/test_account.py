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


def test_export_user_data(client):
    auth = _register(client, "export@example.com", "exportuser")
    headers = {"Authorization": f"Bearer {auth['access_token']}"}

    client.post(
        "/api/v1/plans/generate",
        headers=headers,
        json={
            "major": "Computer Science",
            "grade": "Sophomore",
            "goal": "Master data structures",
            "daily_minutes": 60,
            "weeks": 1,
            "subjects": ["Data Structures"],
        },
    )
    response = client.get("/api/v1/users/me/export", headers=headers)
    assert response.status_code == 200
    payload = response.json()
    assert payload["user"]["email"] == "export@example.com"
    assert payload["plans"]
    assert "questions" in payload


def test_delete_account_removes_data(client):
    auth = _register(client, "deleteacct@example.com", "deleteacct")
    headers = {"Authorization": f"Bearer {auth['access_token']}"}
    client.post(
        "/api/v1/plans/generate",
        headers=headers,
        json={
            "major": "Computer Science",
            "grade": "Sophomore",
            "goal": "Test delete",
            "daily_minutes": 60,
            "weeks": 1,
            "subjects": [],
        },
    )
    response = client.delete("/api/v1/users/me", headers=headers)
    assert response.status_code == 204

    login = client.post(
        "/api/v1/auth/login",
        json={"account": "deleteacct@example.com", "password": "123456"},
    )
    assert login.status_code == 401
