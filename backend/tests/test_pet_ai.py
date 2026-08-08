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


def test_pet_greet_and_chat(client):
    auth = _register(client, "petai@example.com", "petai")
    headers = _headers(auth)
    pet = client.get("/api/v1/pets", headers=headers).json()

    assert client.get(f"/api/v1/pets/{pet['id']}/messages", headers=headers).json() == []

    greet = client.post(f"/api/v1/pets/{pet['id']}/greet", headers=headers)
    assert greet.status_code == 200
    assert greet.json()["reply"]
    assert greet.json()["messages"][-1]["kind"] == "greeting"

    chat = client.post(
        f"/api/v1/pets/{pet['id']}/chat",
        headers=headers,
        json={"message": "今天学什么好？"},
    )
    assert chat.status_code == 200
    body = chat.json()
    assert body["reply"]
    assert len(body["messages"]) == 3
    assert [msg["role"] for msg in body["messages"]] == ["assistant", "user", "assistant"]


def test_pet_pat_and_play(client):
    auth = _register(client, "petplay@example.com", "petplay")
    headers = _headers(auth)
    pet = client.get("/api/v1/pets", headers=headers).json()

    from app.core.database import SessionLocal
    from app.models import Pet

    with SessionLocal() as db:
        row = db.get(Pet, pet["id"])
        row.mood = 40
        db.commit()

    pat = client.post(f"/api/v1/pets/{pet['id']}/pat", headers=headers)
    assert pat.status_code == 200
    assert pat.json()["pet"]["mood"] > 40

    played = client.post(f"/api/v1/pets/{pet['id']}/play", headers=headers)
    assert played.status_code == 200
    assert played.json()["pet"]["exp"] > pat.json()["pet"]["exp"]
    assert played.json()["pet"]["hunger"] < pat.json()["pet"]["hunger"]


def test_pet_revive_requires_coins(client):
    auth = _register(client, "petrevive@example.com", "petrevive")
    headers = _headers(auth)
    pet = client.get("/api/v1/pets", headers=headers).json()

    from app.core.database import SessionLocal
    from app.models import Pet

    with SessionLocal() as db:
        row = db.get(Pet, pet["id"])
        row.runaway = True
        db.commit()

    blocked = client.post(f"/api/v1/pets/{pet['id']}/revive", headers=headers)
    assert blocked.status_code == 400

    from app.models import CoinTransaction

    with SessionLocal() as db:
        db.add(
            CoinTransaction(
                user_id=auth["user"]["id"],
                amount=500,
                reason="测试充值",
            )
        )
        db.commit()

    revived = client.post(f"/api/v1/pets/{pet['id']}/revive", headers=headers)
    assert revived.status_code == 200
    assert revived.json()["pet"]["runaway"] is False


def test_pet_chat_fails_explicitly_without_ai(client, monkeypatch):
    auth = _register(client, "petoffline@example.com", "petoffline")
    headers = _headers(auth)
    pet = client.get("/api/v1/pets", headers=headers).json()

    from app.services.ai_gateway import AIModelGateway

    def offline_chat(self, messages, *, temperature=0.7, timeout=60.0):
        return "离线降级响应：未配置模型 API Key"

    monkeypatch.setattr(AIModelGateway, "chat", offline_chat)

    response = client.post(
        f"/api/v1/pets/{pet['id']}/chat",
        headers=headers,
        json={"message": "你好"},
    )
    assert response.status_code == 502
    assert "AI 服务暂不可用" in response.json()["detail"]
