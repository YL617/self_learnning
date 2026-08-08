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


def test_todo_crud_and_calendar(client):
    auth = _register(client, "todo@example.com", "todouser")
    headers = {"Authorization": f"Bearer {auth['access_token']}"}
    today = date.today()

    created = client.post(
        "/api/v1/todos",
        headers=headers,
        json={"title": "Finish notes", "due_date": today.isoformat()},
    )
    assert created.status_code == 201
    todo_id = created.json()["id"]

    listed = client.get("/api/v1/todos", headers=headers)
    assert len(listed.json()) == 1

    updated = client.patch(
        f"/api/v1/todos/{todo_id}",
        headers=headers,
        json={"completed": True},
    )
    assert updated.json()["completed"] is True

    events = client.get(
        f"/api/v1/calendar?month={today.strftime('%Y-%m')}",
        headers=headers,
    ).json()
    assert any(event["id"] == todo_id and event["kind"] == "todo" for event in events)

    deleted = client.delete(f"/api/v1/todos/{todo_id}", headers=headers)
    assert deleted.status_code == 204


def test_reminder_notification_flow(client):
    auth = _register(client, "remind@example.com", "reminduser")
    headers = {"Authorization": f"Bearer {auth['access_token']}"}
    now = datetime.now(timezone.utc)

    client.post(
        "/api/v1/reminders",
        headers=headers,
        json={"title": "Due now", "remind_at": (now - timedelta(hours=1)).isoformat()},
    )
    future = client.post(
        "/api/v1/reminders",
        headers=headers,
        json={"title": "Later", "remind_at": (now + timedelta(days=1)).isoformat()},
    ).json()

    notifications = client.get("/api/v1/notifications", headers=headers).json()
    due = [item for item in notifications if item["title"] == "Due now"]
    assert len(due) == 1

    dismissed = client.patch(
        f"/api/v1/notifications/{due[0]['id']}/dismiss",
        headers=headers,
    )
    assert dismissed.status_code == 204
    after = client.get("/api/v1/notifications", headers=headers).json()
    assert "Due now" not in [item["title"] for item in after]
    assert future["id"] in [item["id"] for item in client.get(
        "/api/v1/reminders", headers=headers
    ).json()]


def test_courses_report_and_demo_seed(client):
    auth = _register(client, "m6@example.com", "m6user")
    headers = {"Authorization": f"Bearer {auth['access_token']}"}

    courses = client.get("/api/v1/courses", headers=headers).json()
    assert len(courses) >= 3
    assert courses[0]["chapters"]

    report = client.get("/api/v1/reports/weekly", headers=headers)
    assert report.status_code == 200
    assert "focus_minutes" in report.json()

    seeded = client.post("/api/v1/demo/seed", headers=headers)
    assert seeded.status_code == 200
    assert seeded.json()["todos"] == 3
    assert len(client.get("/api/v1/todos", headers=headers).json()) == 3
