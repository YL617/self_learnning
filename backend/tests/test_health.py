def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_register_login_and_me(client):
    payload = {
        "email": "demo@example.com",
        "username": "demo",
        "password": "123456",
    }
    register = client.post("/api/v1/auth/register", json=payload)
    assert register.status_code == 201
    token = register.json()["access_token"]

    login = client.post(
        "/api/v1/auth/login",
        json={"account": "demo", "password": "123456"},
    )
    assert login.status_code == 200

    me = client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["username"] == "demo"


def test_generate_plan_offline(client):
    register = client.post(
        "/api/v1/auth/register",
        json={
            "email": "plan@example.com",
            "username": "planuser",
            "password": "123456",
        },
    )
    token = register.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    response = client.post(
        "/api/v1/plans/generate",
        headers=headers,
        json={
            "major": "计算机科学与技术",
            "grade": "大二",
            "goal": "通过四级并掌握数据结构",
            "daily_minutes": 90,
            "weeks": 2,
            "subjects": ["数据结构", "英语"],
        },
    )
    assert response.status_code == 201
    assert len(response.json()["items"]) > 0
