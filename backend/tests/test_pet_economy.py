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


def _focus_coins(client, headers: dict) -> int:
    transactions = client.get("/api/v1/coins/transactions", headers=headers).json()
    return sum(tx["amount"] for tx in transactions if tx["reason"] == "完成番茄钟")


def test_daily_focus_coin_cap(client):
    auth = _register(client, "cap@example.com", "capuser")
    headers = {"Authorization": f"Bearer {auth['access_token']}"}
    for _ in range(9):
        session = client.post(
            "/api/v1/focus/sessions",
            headers=headers,
            json={"task_label": "Focus", "duration_minutes": 25},
        ).json()
        done = client.patch(
            f"/api/v1/focus/sessions/{session['id']}/complete",
            headers=headers,
            json={"verified": True},
        )
        assert done.status_code == 200
    assert _focus_coins(client, headers) == 40


def test_unverified_focus_earns_nothing(client):
    auth = _register(client, "unverified@example.com", "unverified")
    headers = {"Authorization": f"Bearer {auth['access_token']}"}
    session = client.post(
        "/api/v1/focus/sessions",
        headers=headers,
        json={"task_label": "Focus", "duration_minutes": 25},
    ).json()
    done = client.patch(
        f"/api/v1/focus/sessions/{session['id']}/complete",
        headers=headers,
        json={"verified": False},
    )
    assert done.status_code == 200
    assert done.json()["completed"] is True
    assert _focus_coins(client, headers) == 0


def test_checkin_combo_bonus(client):
    auth = _register(client, "combo@example.com", "combouser")
    headers = {"Authorization": f"Bearer {auth['access_token']}"}

    from app.core.database import SessionLocal
    from app.models import User

    with SessionLocal() as db:
        user = db.get(User, auth["user"]["id"])
        user.checkin_streak = 2
        user.last_checkin_date = date.today() - timedelta(days=1)
        db.commit()

    plan = client.post(
        "/api/v1/plans/generate",
        headers=headers,
        json={
            "major": "Computer Science",
            "grade": "Sophomore",
            "goal": "Combo test",
            "daily_minutes": 30,
            "weeks": 1,
            "subjects": [],
        },
    ).json()
    item_id = plan["items"][0]["id"]
    done = client.patch(
        f"/api/v1/plans/items/{item_id}",
        headers=headers,
        json={"completed": True},
    )
    assert done.status_code == 200

    transactions = client.get("/api/v1/coins/transactions", headers=headers).json()
    reasons = [tx["reason"] for tx in transactions]
    assert "连续打卡 3 天" in reasons
    bonus = next(tx["amount"] for tx in transactions if tx["reason"] == "连续打卡 3 天")
    assert bonus == 50


def test_feed_and_shop(client):
    auth = _register(client, "feed@example.com", "feeduser")
    headers = {"Authorization": f"Bearer {auth['access_token']}"}
    pet = client.get("/api/v1/pets", headers=headers).json()

    shop = client.get("/api/v1/pets/shop", headers=headers).json()
    assert len(shop) == 4

    for _ in range(2):
        session = client.post(
            "/api/v1/focus/sessions",
            headers=headers,
            json={"task_label": "Focus", "duration_minutes": 25},
        ).json()
        client.patch(
            f"/api/v1/focus/sessions/{session['id']}/complete",
            headers=headers,
            json={"verified": True},
        )

    fed = client.post(
        f"/api/v1/pets/{pet['id']}/feed",
        headers=headers,
        json={"amount": 10},
    ).json()
    assert fed["hunger"] == 100
    assert fed["exp"] > pet["exp"]
