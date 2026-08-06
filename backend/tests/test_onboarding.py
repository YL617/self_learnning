def test_onboarding_creates_profile_and_first_plan(client):
    register = client.post(
        "/api/v1/auth/register",
        json={
            "email": "onboard@example.com",
            "username": "onboarduser",
            "password": "123456",
        },
    )
    assert register.status_code == 201
    token = register.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    response = client.post(
        "/api/v1/onboarding",
        headers=headers,
        json={
            "major": "计算机科学与技术",
            "grade": "大二",
            "goals": ["通过四六级", "掌握数据结构"],
            "weekly_minutes": 840,
            "learning_style": ["看视频", "做题"],
            "pain_point": ["计划难执行"],
            "school_level": "普通本科",
            "available_time_slots": ["晚上", "周末"],
            "generate_plan": True,
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["profile"]["onboarding_completed"] is True
    assert payload["profile"]["major"] == "计算机科学与技术"
    assert payload["plan"] is not None
    assert len(payload["plan"]["items"]) > 0

    status = client.get("/api/v1/users/me/onboarding", headers=headers)
    assert status.status_code == 200
    assert status.json()["profile"]["onboarding_completed"] is True
