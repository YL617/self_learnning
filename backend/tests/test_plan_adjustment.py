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


def test_adjust_plan_lightens_overdue_item(client):
    auth = _register(client, "adjust@example.com", "adjustuser")
    headers = {"Authorization": f"Bearer {auth['access_token']}"}
    today = date.today()

    plan_response = client.post(
        "/api/v1/plans",
        headers=headers,
        json={
            "title": "Adjustment Test",
            "goal": "Test dynamic adjustment",
            "start_date": today.isoformat(),
            "end_date": today.isoformat(),
        },
    )
    assert plan_response.status_code == 201
    plan_id = plan_response.json()["id"]

    item_response = client.post(
        f"/api/v1/plans/{plan_id}/items",
        headers=headers,
        json={
            "title": "Overdue task",
            "subject": "Math",
            "scheduled_date": (today - timedelta(days=1)).isoformat(),
            "duration_minutes": 100,
            "difficulty": "hard",
        },
    )
    assert item_response.status_code == 201

    adjust_response = client.post(
        f"/api/v1/plans/{plan_id}/adjust",
        headers=headers,
    )
    assert adjust_response.status_code == 200

    detail = client.get(f"/api/v1/plans/{plan_id}", headers=headers).json()
    item = detail["items"][0]
    assert item["scheduled_date"] == (today + timedelta(days=1)).isoformat()
    assert item["duration_minutes"] <= 80
    assert item["difficulty"] == "medium"


def test_adjust_plan_requires_owner(client):
    owner = _register(client, "adjust_owner@example.com", "adjustowner")
    other = _register(client, "adjust_other@example.com", "adjustother")
    owner_headers = {"Authorization": f"Bearer {owner['access_token']}"}
    other_headers = {"Authorization": f"Bearer {other['access_token']}"}
    today = date.today()

    plan_response = client.post(
        "/api/v1/plans",
        headers=owner_headers,
        json={
            "title": "Owner Plan",
            "goal": None,
            "start_date": today.isoformat(),
            "end_date": today.isoformat(),
        },
    )
    plan_id = plan_response.json()["id"]

    response = client.post(
        f"/api/v1/plans/{plan_id}/adjust",
        headers=other_headers,
    )
    assert response.status_code == 404
