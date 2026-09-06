import pytest
from sqlalchemy import delete


@pytest.fixture(autouse=True)
def _clean_knowledge_points():
    from app.core.database import SessionLocal
    from app.models import KnowledgePoint

    with SessionLocal() as db:
        db.execute(delete(KnowledgePoint))
        db.commit()


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


def _set_admin(auth: dict) -> None:
    from app.core.database import SessionLocal
    from app.models import User

    with SessionLocal() as db:
        user = db.get(User, auth["user"]["id"])
        user.role = "admin"
        db.commit()


def test_unauthenticated_access(client):
    assert client.get("/api/v1/knowledge-points").status_code == 401
    assert (
        client.post(
            "/api/v1/knowledge-points",
            json={"name": "指针", "subject": "C语言"},
        ).status_code
        == 401
    )


def test_normal_user_read_only(client):
    auth = _register(client, "kpuser@example.com", "kpuserok")
    headers = _headers(auth)
    auth2 = _register(client, "kpadmin@example.com", "kpadminok")
    admin_headers = _headers(auth2)
    _set_admin(auth2)

    created = client.post(
        "/api/v1/knowledge-points",
        headers=admin_headers,
        json={"name": "指针", "subject": "C语言"},
    )
    assert created.status_code == 201

    assert client.get("/api/v1/knowledge-points", headers=headers).status_code == 200
    assert client.get("/api/v1/knowledge-points", headers=headers).json()
    assert (
        client.post(
            "/api/v1/knowledge-points",
            headers=headers,
            json={"name": "数组", "subject": "C语言"},
        ).status_code
        == 403
    )
    kp_id = created.json()["id"]
    assert (
        client.patch(
            f"/api/v1/knowledge-points/{kp_id}",
            headers=headers,
            json={"name": "改名"},
        ).status_code
        == 403
    )
    assert (
        client.delete(f"/api/v1/knowledge-points/{kp_id}", headers=headers).status_code
        == 403
    )


def test_cleaning_and_normalized_name(client):
    auth = _register(client, "kpclean@example.com", "kpcleanuser")
    headers = _headers(auth)
    _set_admin(auth)

    response = client.post(
        "/api/v1/knowledge-points",
        headers=headers,
        json={"name": "  Pointer  基础  ", "subject": "  C语言  "},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Pointer 基础"
    assert body["normalized_name"] == "pointer 基础"
    assert body["subject"] == "C语言"


def test_duplicate_after_trim(client):
    auth = _register(client, "kpdup@example.com", "kpdupuser")
    headers = _headers(auth)
    _set_admin(auth)

    first = client.post(
        "/api/v1/knowledge-points",
        headers=headers,
        json={"name": "指针", "subject": "C语言"},
    )
    assert first.status_code == 201
    second = client.post(
        "/api/v1/knowledge-points",
        headers=headers,
        json={"name": "  指针  ", "subject": "C语言"},
    )
    assert second.status_code == 409


def test_subject_case_insensitive_dedupe(client):
    auth = _register(client, "kpsubject@example.com", "kpsubjectuser")
    headers = _headers(auth)
    _set_admin(auth)

    first = client.post(
        "/api/v1/knowledge-points",
        headers=headers,
        json={"name": "指针", "subject": "Math"},
    )
    assert first.status_code == 201

    second = client.post(
        "/api/v1/knowledge-points",
        headers=headers,
        json={"name": "  指针  ", "subject": "math"},
    )
    assert second.status_code == 409

    from app.core.database import SessionLocal
    from app.services.knowledge_point_service import KnowledgePointService

    with SessionLocal() as db:
        resolved = KnowledgePointService(db).resolve_by_name(" MATH ", " 指针 ")
        assert resolved is not None
        assert resolved.id == first.json()["id"]


def test_invalid_parent(client):
    auth = _register(client, "kpparent@example.com", "kpparentuser")
    headers = _headers(auth)
    _set_admin(auth)

    missing = client.post(
        "/api/v1/knowledge-points",
        headers=headers,
        json={"name": "子节点", "subject": "C语言", "parent_id": 99999},
    )
    assert missing.status_code == 400

    tech = client.post(
        "/api/v1/knowledge-points",
        headers=headers,
        json={"name": "指针基础", "subject": "C语言"},
    ).json()
    mismatch = client.post(
        "/api/v1/knowledge-points",
        headers=headers,
        json={"name": "子节点", "subject": "Python", "parent_id": tech["id"]},
    )
    assert mismatch.status_code == 400


def test_update_cycle_and_self_parent(client):
    auth = _register(client, "kpcycle@example.com", "kpcycleuser")
    headers = _headers(auth)
    _set_admin(auth)

    root = client.post(
        "/api/v1/knowledge-points",
        headers=headers,
        json={"name": "A", "subject": "Math"},
    ).json()
    child = client.post(
        "/api/v1/knowledge-points",
        headers=headers,
        json={"name": "B", "subject": "Math", "parent_id": root["id"]},
    ).json()
    grand = client.post(
        "/api/v1/knowledge-points",
        headers=headers,
        json={"name": "C", "subject": "Math", "parent_id": child["id"]},
    ).json()

    self_parent = client.patch(
        f"/api/v1/knowledge-points/{child['id']}",
        headers=headers,
        json={"parent_id": child["id"]},
    )
    assert self_parent.status_code == 400

    cycle = client.patch(
        f"/api/v1/knowledge-points/{root['id']}",
        headers=headers,
        json={"parent_id": grand["id"]},
    )
    assert cycle.status_code == 400


def test_delete_blocked_by_children(client):
    auth = _register(client, "kpdelete@example.com", "kpdeleteuser")
    headers = _headers(auth)
    _set_admin(auth)

    parent = client.post(
        "/api/v1/knowledge-points",
        headers=headers,
        json={"name": "父节点", "subject": "物理"},
    ).json()
    child = client.post(
        "/api/v1/knowledge-points",
        headers=headers,
        json={"name": "子节点", "subject": "物理", "parent_id": parent["id"]},
    ).json()

    blocked = client.delete(f"/api/v1/knowledge-points/{parent['id']}", headers=headers)
    assert blocked.status_code == 400

    removed = client.delete(f"/api/v1/knowledge-points/{child['id']}", headers=headers)
    assert removed.status_code == 204

    after = client.get(
        f"/api/v1/knowledge-points/{parent['id']}",
        headers=headers,
    )
    assert after.status_code == 200


def test_not_found_and_resolve(client):
    auth = _register(client, "kpresolve@example.com", "kpresolveuser")
    headers = _headers(auth)
    _set_admin(auth)

    assert (
        client.get("/api/v1/knowledge-points/99999", headers=headers).status_code == 404
    )
    assert (
        client.patch(
            "/api/v1/knowledge-points/99999",
            headers=headers,
            json={"name": "任意"},
        ).status_code
        == 404
    )
    assert (
        client.delete("/api/v1/knowledge-points/99999", headers=headers).status_code
        == 404
    )

    created = client.post(
        "/api/v1/knowledge-points",
        headers=headers,
        json={"name": "指针", "subject": "C语言"},
    ).json()

    from app.core.database import SessionLocal
    from app.services.knowledge_point_service import KnowledgePointService

    with SessionLocal() as db:
        resolved = KnowledgePointService(db).resolve_by_name("  C语言 ", "  指针  ")
        assert resolved is not None
        assert resolved.id == created["id"]
        assert KnowledgePointService(db).resolve_by_name("C语言", "数组") is None
