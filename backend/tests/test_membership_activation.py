from datetime import date, datetime, timedelta, timezone


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


def _expire_trial(auth: dict) -> None:
    from app.core.database import SessionLocal
    from app.models import User

    with SessionLocal() as db:
        user = db.get(User, auth["user"]["id"])
        user.created_at = datetime.now(timezone.utc) - timedelta(days=8)
        user.membership_level = "free"
        db.commit()


def _set_membership(auth: dict, level: str) -> None:
    from app.core.database import SessionLocal
    from app.models import User

    with SessionLocal() as db:
        user = db.get(User, auth["user"]["id"])
        user.membership_level = level
        user.membership_expires_at = (
            datetime.now(timezone.utc) + timedelta(days=30)
        ).replace(tzinfo=None)
        db.commit()


def test_membership_status_and_quota_info(client):
    auth = _register(client, "memstatus@example.com", "memstatus")
    headers = _headers(auth)

    status = client.get("/api/v1/users/me/membership", headers=headers)
    assert status.status_code == 200
    body = status.json()
    assert body["trial_active"] is True
    assert body["ai_quota_total"] == 20
    assert body["ai_quota_used"] == 0


def test_activate_code_flow(client):
    admin = _register(client, "codeadmin@example.com", "codeadmin")
    admin_headers = _headers(admin)
    _set_admin(admin)

    created = client.post(
        "/api/v1/admin/activation-codes",
        headers=admin_headers,
        json={"tier": "advanced", "days": 30, "count": 2},
    )
    assert created.status_code == 201
    codes = created.json()
    assert len(codes) == 2

    user = _register(client, "codeuser@example.com", "codeuser")
    headers = _headers(user)
    activated = client.post(
        "/api/v1/users/me/activate",
        headers=headers,
        json={"code": codes[0]["code"]},
    )
    assert activated.status_code == 200
    assert activated.json()["membership_level"] == "advanced"
    assert activated.json()["membership_expires_at"] is not None

    duplicate = client.post(
        "/api/v1/users/me/activate",
        headers=headers,
        json={"code": codes[0]["code"]},
    )
    assert duplicate.status_code == 400

    revoked = client.post(
        f"/api/v1/admin/activation-codes/{codes[1]['id']}/revoke",
        headers=admin_headers,
    )
    assert revoked.status_code == 200
    revoked_user = _register(client, "coderevoked@example.com", "coderevoked")
    blocked = client.post(
        "/api/v1/users/me/activate",
        headers=_headers(revoked_user),
        json={"code": codes[1]["code"]},
    )
    assert blocked.status_code == 400


def test_membership_gate_and_ai_quota(client):
    auth = _register(client, "quota2@example.com", "quota2")
    headers = _headers(auth)
    _expire_trial(auth)

    blocked = client.post(
        "/api/v1/questions/generate",
        headers=headers,
        json={
            "subject": "数学",
            "knowledge_point": "函数",
            "count": 1,
            "question_type": "choice",
        },
    )
    assert blocked.status_code == 403

    _set_membership(auth, "advanced")
    allowed = client.post(
        "/api/v1/questions/generate",
        headers=headers,
        json={
            "subject": "数学",
            "knowledge_point": "函数",
            "count": 1,
            "question_type": "choice",
        },
    )
    assert allowed.status_code == 201

    from sqlalchemy import select

    from app.core.database import SessionLocal
    from app.models import AiDailyUsage

    with SessionLocal() as db:
        row = db.scalar(
            select(AiDailyUsage).where(
                AiDailyUsage.user_id == auth["user"]["id"],
                AiDailyUsage.usage_date == date.today(),
            )
        )
        if row is None:
            db.add(
                AiDailyUsage(
                    user_id=auth["user"]["id"],
                    usage_date=date.today(),
                    calls=120,
                )
            )
        else:
            row.calls = 120
        db.commit()

    limited = client.post(
        "/api/v1/questions/generate",
        headers=headers,
        json={
            "subject": "数学",
            "knowledge_point": "函数",
            "count": 1,
            "question_type": "choice",
        },
    )
    assert limited.status_code == 429


def test_content_filter_blocks_sensitive_input(client):
    auth = _register(client, "filter@example.com", "filter")
    headers = _headers(auth)

    response = client.post(
        "/api/v1/questions/generate",
        headers=headers,
        json={
            "subject": "数学",
            "knowledge_point": "代写论文",
            "count": 1,
            "question_type": "choice",
        },
    )
    assert response.status_code == 400
    assert "敏感词" in response.json()["detail"]


def test_digital_human_access_gated_by_full_membership(client):
    auth = _register(client, "digital@example.com", "digital")
    headers = _headers(auth)

    trial = client.get("/api/v1/users/me/digital-human", headers=headers)
    assert trial.status_code == 200
    assert trial.json()["access"] is True

    _expire_trial(auth)
    blocked = client.get("/api/v1/users/me/digital-human", headers=headers)
    assert blocked.json()["access"] is False

    _set_membership(auth, "full")
    allowed = client.get("/api/v1/users/me/digital-human", headers=headers)
    assert allowed.json()["access"] is True
