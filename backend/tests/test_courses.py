def _register(client, email: str, username: str) -> str:
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


def _make_plan(client, headers, subject: str) -> int:
    plan_resp = client.post(
        "/api/v1/plans/generate",
        headers=headers,
        json={
            "major": "计算机",
            "grade": "大二",
            "goal": "学习",
            "daily_minutes": 60,
            "weeks": 1,
            "subjects": [subject],
        },
    )
    assert plan_resp.status_code == 201
    return plan_resp.json()["id"]


def _mock_generate_json(self, system, user, temperature=0.3):
    subject = "数据结构"
    if "重点科目：" in user:
        subject = user.split("重点科目：")[1].strip()
    if "items" in system:
        return {
            "title": "Mock Plan",
            "goal": "Mock goal",
            "items": [
                {
                    "title": "Task 1",
                    "subject": subject,
                    "scheduled_date": "2026-09-06",
                    "duration_minutes": 60,
                    "order_index": 1,
                }
            ],
        }
    # 课程推荐不再调用 AI，此分支仅为兼容旧逻辑保留。
    return [
        {
            "title": "未使用",
            "platform": "中国大学MOOC",
            "url": "https://www.icourse163.org/course/ZJU-93001",
            "description": "未使用",
            "subject": subject,
        }
    ]


def test_generate_plan_recommends_real_courses(client, monkeypatch):
    from app.services.ai_gateway import AIModelGateway

    monkeypatch.setattr(AIModelGateway, "generate_json", _mock_generate_json)

    token = _register(client, "courses@example.com", "coursesuser")
    headers = {"Authorization": f"Bearer {token}"}
    client.post("/api/v1/users/me/membership/demo", headers=headers)

    plan_id = _make_plan(client, headers, "数据结构")

    recs = client.get(f"/api/v1/plans/{plan_id}/courses", headers=headers).json()
    assert len(recs) >= 1
    rec = recs[0]
    assert rec["status"] == "pending"
    assert rec["url"].startswith("http")
    assert "数据结构" in rec["title"]
    # 必须指向真实课程页，而不是平台首页。
    assert rec["url"].rstrip("/") not in {
        "https://www.icourse163.org",
        "https://www.bilibili.com",
        "https://www.xuetangx.com",
        "https://www.coursera.org",
    }

    saved = client.post(
        f"/api/v1/courses/recommendations/{rec['id']}/save",
        headers=headers,
    )
    assert saved.status_code == 200
    assert saved.json()["status"] == "saved"

    courses = client.get("/api/v1/courses", headers=headers).json()
    assert any(course["title"] == rec["title"] for course in courses)


def test_recommend_english_matches_catalog(client, monkeypatch):
    from app.services.ai_gateway import AIModelGateway

    monkeypatch.setattr(AIModelGateway, "generate_json", _mock_generate_json)

    token = _register(client, "eng@example.com", "enguser")
    headers = {"Authorization": f"Bearer {token}"}
    client.post("/api/v1/users/me/membership/demo", headers=headers)

    plan_id = _make_plan(client, headers, "英语")
    recs = client.get(f"/api/v1/plans/{plan_id}/courses", headers=headers).json()

    assert recs
    assert any("英语" in rec["title"] or rec.get("subject") == "英语" for rec in recs)


def test_is_platform_home_detection():
    from app.services.course_recommender import is_platform_home

    assert is_platform_home("https://www.icourse163.org/")
    assert is_platform_home("https://www.bilibili.com")
    assert is_platform_home("https://www.xuetangx.com")
    assert not is_platform_home("https://www.icourse163.org/course/ZJU-93001")
    assert not is_platform_home(
        "https://www.xuetangx.com/course/THU08091000267/5883104"
    )
    assert not is_platform_home("https://www.coursera.org/learn/machine-learning")


def test_public_courses_have_real_links(client):
    from app.services.course_recommender import is_platform_home

    courses = client.get("/api/v1/courses").json()
    assert courses
    assert all(not is_platform_home(course["url"]) for course in courses)


def test_personalization_prefers_kaoyan_level():
    from app.services.course_recommender import _pick_courses

    ctx = {
        "full_text": "数据结构",
        "weak_lower": "",
        "goals_lower": "考研",
        "desired_level": "考研",
    }
    picks = _pick_courses("数据结构", ctx, {})
    assert "王道考研数据结构" in picks[0]["title"]


def test_feedback_demotes_heavily_dismissed():
    from app.services.course_recommender import _pick_courses

    ctx = {
        "full_text": "数据结构",
        "weak_lower": "",
        "goals_lower": "考研",
        "desired_level": "考研",
    }
    counters = {"王道考研数据结构（B站）": {"dismiss": 5, "save": 0}}
    picks = _pick_courses("数据结构", ctx, counters)
    assert "王道考研数据结构" not in picks[0]["title"]


def test_check_catalog_health_updates_status(client, monkeypatch):
    from sqlalchemy import select

    from app.core.database import SessionLocal
    from app.models import Course
    from app.services.course_recommender import check_catalog_health

    def fake_probe(url, timeout=8):
        return {"status": "ok", "http_status": 200, "error": None}

    monkeypatch.setattr("app.services.course_recommender._probe_url", fake_probe)

    with SessionLocal() as db:
        result = check_catalog_health(db)
        assert result["checked"] >= 3
        assert result["ok"] == result["checked"]
        first = db.scalar(select(Course).limit(1))
        assert first is not None
        assert first.health_status == "ok"


def test_save_increments_course_save_count(client, monkeypatch):
    from sqlalchemy import select

    from app.core.database import SessionLocal
    from app.models import Course
    from app.services.ai_gateway import AIModelGateway

    monkeypatch.setattr(AIModelGateway, "generate_json", _mock_generate_json)
    token = _register(client, "savecount@example.com", "savecountuser")
    headers = {"Authorization": f"Bearer {token}"}
    client.post("/api/v1/users/me/membership/demo", headers=headers)

    plan_id = _make_plan(client, headers, "数据结构")
    recs = client.get(f"/api/v1/plans/{plan_id}/courses", headers=headers).json()
    assert recs
    rec = recs[0]
    with SessionLocal() as db:
        existing = db.scalar(select(Course).where(Course.title == rec["title"]))
        baseline = existing.save_count if existing else 0
    saved = client.post(
        f"/api/v1/courses/recommendations/{rec['id']}/save",
        headers=headers,
    )
    assert saved.status_code == 200

    with SessionLocal() as db:
        course = db.scalar(select(Course).where(Course.title == rec["title"]))
        assert course is not None
        assert course.save_count == baseline + 1


def test_probe_url_classifies_anti_bot_as_unknown(monkeypatch):
    import urllib.error

    from app.services.course_recommender import _probe_url

    def fake_urlopen(req, timeout=None):
        raise urllib.error.HTTPError(
            req.full_url,
            412,
            "Precondition Failed",
            {},
            None,
        )

    monkeypatch.setattr(
        "app.services.course_recommender.urllib.request.urlopen",
        fake_urlopen,
    )
    result = _probe_url("https://www.bilibili.com/video/BV1b7411N798")
    assert result["status"] == "unknown"
    assert result["http_status"] == 412
