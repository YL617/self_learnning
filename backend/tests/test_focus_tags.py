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


def test_focus_tag_crud(client):
    auth = _register(client, "focus-tags@example.com", "focustags")
    headers = {"Authorization": f"Bearer {auth['access_token']}"}

    created = client.post(
        "/api/v1/focus/tags",
        json={"name": "数学", "color": "#2563eb"},
        headers=headers,
    )
    assert created.status_code == 201
    tag = created.json()
    assert tag["name"] == "数学"
    assert tag["color"] == "#2563eb"

    duplicate = client.post(
        "/api/v1/focus/tags",
        json={"name": "数学", "color": "#dc2626"},
        headers=headers,
    )
    assert duplicate.status_code == 409

    updated = client.patch(
        f"/api/v1/focus/tags/{tag['id']}",
        json={"name": "高数", "color": "#dc2626"},
        headers=headers,
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "高数"
    assert updated.json()["color"] == "#dc2626"

    tags = client.get("/api/v1/focus/tags", headers=headers).json()
    assert len(tags) == 1
    assert tags[0]["name"] == "高数"

    deleted = client.delete(
        f"/api/v1/focus/tags/{tag['id']}",
        headers=headers,
    )
    assert deleted.status_code == 204
    assert client.get("/api/v1/focus/tags", headers=headers).json() == []


def test_focus_sessions_include_tag_color(client):
    auth = _register(client, "focus-sessions@example.com", "focussessions")
    headers = {"Authorization": f"Bearer {auth['access_token']}"}

    tag = client.post(
        "/api/v1/focus/tags",
        json={"name": "英语", "color": "#0891b2"},
        headers=headers,
    ).json()
    session = client.post(
        "/api/v1/focus/sessions",
        headers=headers,
        json={
            "task_label": tag["name"],
            "duration_minutes": 25,
            "tag_color": tag["color"],
        },
    ).json()
    assert session["tag_color"] == "#0891b2"

    done = client.patch(
        f"/api/v1/focus/sessions/{session['id']}/complete",
        headers=headers,
        json={"verified": True},
    )
    assert done.status_code == 200

    sessions = client.get(
        "/api/v1/focus/sessions",
        params={"days": 30},
        headers=headers,
    ).json()
    assert len(sessions) == 1
    assert sessions[0]["task_label"] == "英语"
    assert sessions[0]["tag_color"] == "#0891b2"
    assert sessions[0]["completed"] is True
