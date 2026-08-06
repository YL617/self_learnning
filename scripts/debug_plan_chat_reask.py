"""Debug: verify AI re-asks instead of answering for the user."""

import time

import httpx

BASE = "http://127.0.0.1:8000/api/v1"


def main() -> None:
    client = httpx.Client(timeout=90)
    suffix = str(int(time.time()))
    email = f"reask{suffix}@example.com"
    register = client.post(
        f"{BASE}/auth/register",
        json={"email": email, "username": f"reask{suffix}", "password": "123456"},
    )
    token = register.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    client.post(f"{BASE}/users/me/membership/demo", headers=headers)

    start = client.post(f"{BASE}/plans/chat", headers=headers)
    session_id = start.json()["session_id"]
    print("first:", start.json()["reply"])

    for turn in range(1, 9):
        response = client.post(
            f"{BASE}/plans/chat/{session_id}/messages",
            headers=headers,
            json={"content": "好的，你继续问吧，我还没有回答。"},
        )
        data = response.json()
        print(f"[turn {turn}] status={data.get('status')} draft={'yes' if data.get('draft') else 'no'}")
        print(f"  ai: {data.get('reply', '')[:240]}")
        if data.get("draft"):
            break


if __name__ == "__main__":
    main()
