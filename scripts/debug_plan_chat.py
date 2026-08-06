"""Debug script: print real AI replies in the plan chat flow."""

import time

import httpx

BASE = "http://127.0.0.1:8000/api/v1"


def main() -> None:
    client = httpx.Client(timeout=90)
    suffix = str(int(time.time()))
    email = f"debug{suffix}@example.com"
    register = client.post(
        f"{BASE}/auth/register",
        json={"email": email, "username": f"debug{suffix}", "password": "123456"},
    )
    print("register:", register.status_code)
    token = register.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    client.post(f"{BASE}/users/me/membership/demo", headers=headers)

    start = client.post(f"{BASE}/plans/chat", headers=headers)
    session_id = start.json()["session_id"]
    print("first:", start.json()["reply"])

    answers = [
        "计算机科学与技术，大二",
        "目标是通过四级，还想把数据结构学扎实",
        "每天大概能学一个半小时，周一到周五晚上有时间",
        "希望覆盖两周，尽量在下个月考试前完成",
        "重点就是数据结构、英语",
        "递归和动态规划最薄弱",
        "我更喜欢做题加看视频",
    ]
    for index, answer in enumerate(answers, 1):
        response = client.post(
            f"{BASE}/plans/chat/{session_id}/messages",
            headers=headers,
            json={"content": answer},
        )
        data = response.json()
        print(f"[turn {index}] user: {answer}")
        print(f"  ai: {data.get('reply', '')[:300]}")
        print(f"  status={data.get('status')} draft={'yes' if data.get('draft') else 'no'}")
        if data.get("draft"):
            break


if __name__ == "__main__":
    main()
