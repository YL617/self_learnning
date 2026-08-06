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


def _generate_plan(client, headers: dict) -> dict:
    response = client.post(
        "/api/v1/plans/generate",
        headers=headers,
        json={
            "major": "Computer Science",
            "grade": "Sophomore",
            "goal": "Master data structures",
            "daily_minutes": 90,
            "weeks": 1,
            "subjects": ["Data Structures"],
        },
    )
    assert response.status_code == 201
    return response.json()


def test_delete_plan(client):
    auth = _register(client, "delete@example.com", "deleteuser")
    headers = {"Authorization": f"Bearer {auth['access_token']}"}
    plan = _generate_plan(client, headers)

    response = client.delete(f"/api/v1/plans/{plan['id']}", headers=headers)
    assert response.status_code == 204
    assert client.get("/api/v1/plans", headers=headers).json() == []


def test_delete_plan_requires_owner(client):
    owner = _register(client, "owner@example.com", "owneruser")
    other = _register(client, "other@example.com", "otheruser")
    owner_headers = {"Authorization": f"Bearer {owner['access_token']}"}
    other_headers = {"Authorization": f"Bearer {other['access_token']}"}
    plan = _generate_plan(client, owner_headers)

    response = client.delete(f"/api/v1/plans/{plan['id']}", headers=other_headers)
    assert response.status_code == 404
    assert client.get("/api/v1/plans", headers=owner_headers).json()


def test_delete_plan_item(client):
    auth = _register(client, "item@example.com", "itemuser")
    headers = {"Authorization": f"Bearer {auth['access_token']}"}
    plan = _generate_plan(client, headers)
    item_id = plan["items"][0]["id"]

    response = client.delete(f"/api/v1/plans/items/{item_id}", headers=headers)
    assert response.status_code == 204
    detail = client.get(f"/api/v1/plans/{plan['id']}", headers=headers).json()
    assert len(detail["items"]) == len(plan["items"]) - 1
