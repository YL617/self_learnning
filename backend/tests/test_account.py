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


def test_delete_account_cleans_file_analyze_results(client):
    auth = _register(client, "fileclean@example.com", "fileclean")
    headers = {"Authorization": f"Bearer {auth['access_token']}"}

    upload = client.post(
        "/api/v1/files/upload",
        headers=headers,
        files={"file": ("clean.txt", b"clean content\n" * 5, "text/plain")},
    )
    document_id = upload.json()["id"]
    client.post(f"/api/v1/files/{document_id}/parse", headers=headers)
    client.post(f"/api/v1/files/{document_id}/analyze", headers=headers)

    from sqlalchemy import select

    from app.core.database import SessionLocal
    from app.models import FileAnalyzeResult

    with SessionLocal() as db:
        assert db.scalar(
            select(FileAnalyzeResult).where(
                FileAnalyzeResult.document_id == document_id
            )
        ) is not None

    response = client.delete("/api/v1/users/me", headers=headers)
    assert response.status_code == 204

    with SessionLocal() as db:
        assert db.scalar(
            select(FileAnalyzeResult).where(
                FileAnalyzeResult.document_id == document_id
            )
        ) is None
