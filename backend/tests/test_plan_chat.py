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


def test_plan_chat_requires_membership_after_trial(client):
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import select

    from app.core.database import SessionLocal
    from app.models import User

    token = _register(client, "chatexpired", "chatexpired@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    with SessionLocal() as db:
        user = db.scalar(
            select(User).where(User.username == "chatexpired")
        )
        user.created_at = datetime.now(timezone.utc) - timedelta(days=8)
        user.membership_level = "free"
        db.commit()
    response = client.post("/api/v1/plans/chat", headers=headers)
    assert response.status_code == 403


def test_plan_chat_offline_flow(client):
    token = _register(client, "chatvip", "chatvip@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    vip = client.post("/api/v1/users/me/membership/demo", headers=headers)
    assert vip.status_code == 200
    assert vip.json()["membership_level"] == "advanced"

    start = client.post("/api/v1/plans/chat", headers=headers)
    assert start.status_code == 201
    session_id = start.json()["session_id"]
    assert start.json()["status"] == "collecting"

    answers = [
        "通过四级并掌握数据结构",
        "计算机科学与技术",
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


def test_plan_chat_prefills_profile(client):
    from sqlalchemy import select

    from app.core.database import SessionLocal
    from app.models import User, UserProfile

    token = _register(client, "chatprofile", "chatprofile@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    client.post("/api/v1/users/me/membership/demo", headers=headers)

    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.username == "chatprofile"))
        profile = user.profile or UserProfile(user_id=user.id)
        profile.major = "计算机科学与技术"
        profile.grade = "大二"
        profile.goals = "通过四级并掌握数据结构"
        profile.daily_study_minutes = 90
        profile.weak_subjects = "递归"
        profile.learning_style = "混合"
        profile.available_time_slots = "晚上 7-10 点"
        db.add(profile)
        db.commit()

    start = client.post("/api/v1/plans/chat", headers=headers)
    assert start.status_code == 201
    body = start.json()
    assert "方向" in body["reply"] or "目标" in body["reply"]
    assert "专业年级" in body["known"]
    assert "学习目标" in body["known"]
    assert "每日时长" in body["known"]
    assert "可用时段" in body["known"]


def test_plan_chat_new_direction_clears_history(client):
    import json

    from sqlalchemy import select

    from app.core.database import SessionLocal
    from app.models import PlanChatSession, User, UserProfile

    token = _register(client, "chatnewdir", "chatnewdir@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    client.post("/api/v1/users/me/membership/demo", headers=headers)

    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.username == "chatnewdir"))
        profile = user.profile or UserProfile(user_id=user.id)
        profile.major = "土木工程"
        profile.goals = "通过大学物理"
        profile.daily_study_minutes = 60
        profile.weak_subjects = "力学"
        profile.learning_style = "做题"
        db.add(profile)
        db.commit()

    start = client.post("/api/v1/plans/chat", headers=headers)
    session_id = start.json()["session_id"]
    response = client.post(
        f"/api/v1/plans/chat/{session_id}/messages",
        headers=headers,
        json={"content": "我想转行做前端开发，重新规划"},
    )
    assert response.status_code == 200

    with SessionLocal() as db:
        session = db.get(PlanChatSession, session_id)
        context = json.loads(session.collected_context)
    assert context.get("new_direction") == "true"
    assert "major" not in context
    assert "subjects" not in context
    assert context.get("goal") == "我想转行做前端开发，重新规划"


def test_plan_chat_refines_draft(client, monkeypatch):
    import json
    from datetime import date

    from app.services.ai_gateway import AIModelGateway

    token = _register(client, "chatrefine", "chatrefine@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    client.post("/api/v1/users/me/membership/demo", headers=headers)
    start = client.post("/api/v1/plans/chat", headers=headers)
    session_id = start.json()["session_id"]

    today = date.today().isoformat()
    draft = {
        "type": "draft",
        "draft": {
            "title": "初始计划",
            "goal": "掌握数据结构",
            "items": [
                {
                    "title": "复习栈和队列",
                    "subject": "数据结构",
                    "scheduled_date": today,
                    "duration_minutes": 60,
                    "order_index": 1,
                }
            ],
        },
    }
    refined = {
        "title": "优化后的数据结构提升计划",
        "goal": "两周内掌握栈、队列与递归",
        "items": [
            {
                "title": "栈与队列专项练习",
                "subject": "数据结构",
                "scheduled_date": today,
                "duration_minutes": 45,
                "order_index": 1,
            }
        ],
    }
    calls = {"count": 0}

    def fake_chat(self, messages, *, temperature=0.7, timeout=60.0):
        calls["count"] += 1
        if calls["count"] == 1:
            return json.dumps(draft, ensure_ascii=False)
        return json.dumps(refined, ensure_ascii=False)

    monkeypatch.setattr(AIModelGateway, "chat", fake_chat)

    response = client.post(
        f"/api/v1/plans/chat/{session_id}/messages",
        headers=headers,
        json={"content": "直接生成计划"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "draft_ready"
    assert body["draft"]["title"] == "优化后的数据结构提升计划"
    assert body["draft"]["items"][0]["title"] == "栈与队列专项练习"
