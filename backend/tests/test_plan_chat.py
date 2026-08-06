def _register(client, username: str, email: str) -> str:
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "username": username,
            "password": "123456",
        },
    )
    assert response.status_code == 201
    return response.json()["access_token"]


def test_plan_chat_requires_vip(client):
    token = _register(client, "chatfree", "chatfree@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    response = client.post("/api/v1/plans/chat", headers=headers)
    assert response.status_code == 403


def test_plan_chat_offline_flow(client):
    token = _register(client, "chatvip", "chatvip@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    vip = client.post("/api/v1/users/me/membership/demo", headers=headers)
    assert vip.status_code == 200
    assert vip.json()["membership_level"] == "vip"

    start = client.post("/api/v1/plans/chat", headers=headers)
    assert start.status_code == 201
    session_id = start.json()["session_id"]
    assert start.json()["status"] == "collecting"

    answers = [
        "计算机科学与技术",
        "通过四级并掌握数据结构",
        "90",
        "2",
        "数据结构,英语",
        "递归",
        "混合",
    ]
    final_status = "collecting"
    for answer in answers:
        response = client.post(
            f"/api/v1/plans/chat/{session_id}/messages",
            headers=headers,
            json={"content": answer},
        )
        assert response.status_code == 200
        final_status = response.json()["status"]
        if response.json().get("draft"):
            break

    assert final_status == "draft_ready"

    confirm = client.post(
        f"/api/v1/plans/chat/{session_id}/confirm",
        headers=headers,
    )
    assert confirm.status_code == 200
    plan_id = confirm.json()["plan_id"]

    detail = client.get(f"/api/v1/plans/{plan_id}", headers=headers)
    assert detail.status_code == 200
    assert len(detail.json()["items"]) > 0
