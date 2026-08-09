from datetime import datetime, timedelta, timezone


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


def _add_coins(client, auth: dict, amount: int) -> None:
    from app.core.database import SessionLocal
    from app.models import CoinTransaction

    with SessionLocal() as db:
        db.add(
            CoinTransaction(
                user_id=auth["user"]["id"],
                amount=amount,
                reason="测试充值",
            )
        )
        db.commit()


def _set_pet(client, pet_id: int, **values) -> None:
    from app.core.database import SessionLocal
    from app.models import Pet

    with SessionLocal() as db:
        row = db.get(Pet, pet_id)
        for key, value in values.items():
            setattr(row, key, value)
        db.commit()


def test_start_and_full_settlement(client):
    auth = _register(client, "playfull@example.com", "playfull")
    headers = _headers(auth)
    pet = client.get("/api/v1/pets", headers=headers).json()
    _add_coins(client, auth, 100)

    start = client.post(f"/api/v1/pets/{pet['id']}/play-out", headers=headers)
    assert start.status_code == 200
    body = start.json()
    assert body["session"]["status"] == "active"
    assert body["pet"]["play_count_today"] == 1
    assert body["pet"]["playing_until"] is not None

    _set_pet(
        client,
        pet["id"],
        playing_until=datetime.now(timezone.utc).replace(tzinfo=None)
        - timedelta(minutes=1),
    )
    state = client.get(f"/api/v1/pets/{pet['id']}/play-session", headers=headers)
    assert state.status_code == 200
    result = state.json()
    assert result["summary"]["mood_gain"] == 15
    assert result["summary"]["exp_gain"] == 20
    assert result["summary"]["hunger_loss"] == 15
    assert result["pet"]["exp"] == 20
    assert result["pet"]["hunger"] == 85
    assert result["pet"]["playing_until"] is None

    transactions = client.get("/api/v1/coins/transactions", headers=headers).json()
    assert any(tx["reason"] == "出门玩" and tx["amount"] == -20 for tx in transactions)


def test_early_return_settles_proportionally(client):
    auth = _register(client, "playearly@example.com", "playearly")
    headers = _headers(auth)
    pet = client.get("/api/v1/pets", headers=headers).json()
    _add_coins(client, auth, 100)

    client.post(f"/api/v1/pets/{pet['id']}/play-out", headers=headers)
    ended = client.post(
        f"/api/v1/pets/{pet['id']}/play-out/end",
        headers=headers,
    )
    assert ended.status_code == 200
    result = ended.json()
    assert result["session"]["status"] == "completed"
    assert result["pet"]["playing_until"] is None
    assert result["summary"]["mood_gain"] < 15
    assert result["summary"]["exp_gain"] < 20


def test_play_validation_and_idempotent_end(client):
    auth = _register(client, "playcheck@example.com", "playcheck")
    headers = _headers(auth)
    pet = client.get("/api/v1/pets", headers=headers).json()

    blocked = client.post(f"/api/v1/pets/{pet['id']}/play-out", headers=headers)
    assert blocked.status_code == 400
    assert "智学币不足" in blocked.json()["detail"]

    _add_coins(client, auth, 100)
    _set_pet(client, pet["id"], runaway=True)
    runaway = client.post(f"/api/v1/pets/{pet['id']}/play-out", headers=headers)
    assert runaway.status_code == 400
    assert "离家出走" in runaway.json()["detail"]

    _set_pet(client, pet["id"], runaway=False, hunger=10)
    hungry = client.post(f"/api/v1/pets/{pet['id']}/play-out", headers=headers)
    assert hungry.status_code == 400
    assert "太饿" in hungry.json()["detail"]

    from datetime import date

    _set_pet(
        client,
        pet["id"],
        hunger=100,
        play_date=date.today(),
        play_count_today=5,
    )
    limited = client.post(f"/api/v1/pets/{pet['id']}/play-out", headers=headers)
    assert limited.status_code == 400
    assert "次数已经用完" in limited.json()["detail"]

    _set_pet(client, pet["id"], play_date=None, play_count_today=0)
    started = client.post(f"/api/v1/pets/{pet['id']}/play-out", headers=headers)
    assert started.status_code == 200
    again = client.post(f"/api/v1/pets/{pet['id']}/play-out", headers=headers)
    assert again.status_code == 400
    assert "正在出门玩" in again.json()["detail"]

    ended = client.post(
        f"/api/v1/pets/{pet['id']}/play-out/end",
        headers=headers,
    )
    assert ended.status_code == 200
    repeated = client.post(
        f"/api/v1/pets/{pet['id']}/play-out/end",
        headers=headers,
    )
    assert repeated.status_code == 200
    assert repeated.json()["summary"]["message"] == "这次出门玩已经结束啦"
