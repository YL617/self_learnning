from io import BytesIO


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


def _headers(auth: dict) -> dict:
    return {"Authorization": f"Bearer {auth['access_token']}"}


def _set_admin(auth: dict) -> None:
    from app.core.database import SessionLocal
    from app.models import User

    with SessionLocal() as db:
        user = db.get(User, auth["user"]["id"])
        user.role = "admin"
        db.commit()


def test_admin_endpoint_requires_admin(client):
    auth = _register(client, "admincheck@example.com", "admincheck")
    headers = _headers(auth)

    blocked = client.get("/api/v1/admin/users", headers=headers)
    assert blocked.status_code == 403

    _set_admin(auth)
    allowed = client.get("/api/v1/admin/users", headers=headers)
    assert allowed.status_code == 200


def test_update_nickname_and_password(client):
    auth = _register(client, "profile@example.com", "profileuser")
    headers = _headers(auth)

    updated = client.patch(
        "/api/v1/users/me",
        headers=headers,
        json={"nickname": "小智同学"},
    )
    assert updated.status_code == 200
    assert updated.json()["nickname"] == "小智同学"

    wrong = client.post(
        "/api/v1/users/me/password",
        headers=headers,
        json={"old_password": "wrong1", "new_password": "654321"},
    )
    assert wrong.status_code == 400

    changed = client.post(
        "/api/v1/users/me/password",
        headers=headers,
        json={"old_password": "123456", "new_password": "654321"},
    )
    assert changed.status_code == 200

    login = client.post(
        "/api/v1/auth/login",
        json={"account": "profileuser", "password": "654321"},
    )
    assert login.status_code == 200


def test_avatar_upload(client):
    auth = _register(client, "avatar@example.com", "avataruser")
    headers = _headers(auth)

    uploaded = client.post(
        "/api/v1/users/me/avatar",
        headers=headers,
        files={"file": ("avatar.png", BytesIO(b"fake-png"), "image/png")},
    )
    assert uploaded.status_code == 200
    assert uploaded.json()["avatar_url"].startswith("/uploads/avatars/")

    invalid = client.post(
        "/api/v1/users/me/avatar",
        headers=headers,
        files={"file": ("avatar.exe", BytesIO(b"bad"), "application/octet-stream")},
    )
    assert invalid.status_code == 400


def test_ai_monitor_refresh_and_cooldown(client, monkeypatch):
    auth = _register(client, "aicheck@example.com", "aicheck")
    headers = _headers(auth)
    _set_admin(auth)

    from app.core.config import get_settings
    from app.core.database import SessionLocal
    from app.services.ai_monitor import (
        DEEPSEEK_BALANCE_URL,
        refresh_deepseek_monitor,
    )

    def fake_fetch(url, api_key, *, method="GET", body=None, timeout=15.0):
        if url == DEEPSEEK_BALANCE_URL:
            return {
                "is_available": True,
                "balance_infos": [
                    {
                        "currency": "CNY",
                        "total_balance": "10.5",
                        "granted_balance": "2.5",
                        "topped_up_balance": "8.0",
                    }
                ],
            }
        if "amount" in url:
            return {"code": 0, "data": {}}
        return {
            "code": 0,
            "data": {
                "items": [
                    {"date": "2026-08-10", "tokens": 120, "cost": 0.6}
                ]
            },
        }

    monkeypatch.setattr("app.services.ai_monitor._fetch_json", fake_fetch)
    get_settings().DEEPSEEK_API_KEY = "test-key"

    with SessionLocal() as db:
        snapshot = refresh_deepseek_monitor(db)
        assert snapshot.status == "ok"
        assert snapshot.total_balance == "10.5"

    state = client.get("/api/v1/admin/ai-monitor", headers=headers)
    assert state.status_code == 200
    assert state.json()["snapshot"]["total_balance"] == "10.5"
    assert state.json()["usage"][0]["tokens"] == 120

    refresh = client.post("/api/v1/admin/ai-monitor/refresh", headers=headers)
    assert refresh.status_code == 429


def test_admin_stats_and_user_management(client):
    auth = _register(client, "stats@example.com", "statsuser")
    headers = _headers(auth)
    _set_admin(auth)

    overview = client.get("/api/v1/admin/stats/overview", headers=headers)
    assert overview.status_code == 200
    assert overview.json()["user_count"] >= 1

    users = client.get("/api/v1/admin/users", headers=headers).json()
    target = next(user for user in users if user["id"] == auth["user"]["id"])
    changed = client.patch(
        f"/api/v1/admin/users/{target['id']}",
        headers=headers,
        json={"membership_level": "vip", "is_active": True},
    )
    assert changed.status_code == 200
    assert changed.json()["membership_level"] == "vip"


def test_admin_content_management(client):
    auth = _register(client, "content@example.com", "contentuser")
    headers = _headers(auth)
    _set_admin(auth)

    from app.core.database import SessionLocal
    from app.models import Course, CourseChapter, Question, User

    with SessionLocal() as db:
        user = db.get(User, auth["user"]["id"])
        question = Question(
            user_id=user.id,
            subject="测试",
            knowledge_point="管理",
            question_type="choice",
            stem="管理接口测试题目",
            answer="A",
        )
        course = Course(title="管理课程", platform="测试", url="https://example.com")
        course.chapters.append(CourseChapter(title="第一章", order_index=1))
        db.add_all([question, course])
        db.commit()
        question_id = question.id
        course_id = course.id

    questions = client.get("/api/v1/admin/questions", headers=headers)
    assert questions.status_code == 200
    assert any(item["id"] == question_id for item in questions.json())

    deleted_q = client.delete(
        f"/api/v1/admin/questions/{question_id}",
        headers=headers,
    )
    assert deleted_q.status_code == 204

    courses = client.get("/api/v1/admin/courses", headers=headers)
    assert courses.status_code == 200
    assert any(item["id"] == course_id for item in courses.json())

    deleted_c = client.delete(
        f"/api/v1/admin/courses/{course_id}",
        headers=headers,
    )
    assert deleted_c.status_code == 204
