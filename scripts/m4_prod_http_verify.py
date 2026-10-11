"""M4 生产部署 阶段4/5 HTTP 级验证（对 https://yl617.xyz 真实调用）。

只做最小必要验证：权限隔离、shared 可见性、答题闭环、container 红线。
脚本末尾输出新建对象 id，供后续清理。所有清理动作在独立步骤执行。
"""
import json
import sys
import time
import urllib.error
import urllib.request

BASE = "https://yl617.xyz/api/v1"
ADMIN = sys.argv[1]
CONCEPT_ID = int(sys.argv[2])
CONTAINER_ID = int(sys.argv[3])
EXISTING_ADMIN_PRIVATE_QID = int(sys.argv[4])

RESULTS = []


def call(method, path, token=None, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", "Bearer " + token)
    try:
        with urllib.request.urlopen(req, timeout=40) as resp:
            raw = resp.read().decode()
            return resp.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode()
        try:
            return exc.code, json.loads(raw)
        except Exception:
            return exc.code, raw


def chk(label, ok, detail=""):
    RESULTS.append(bool(ok))
    print(("PASS  " if ok else "FAIL  ") + label + (("  | " + str(detail))[:220] if detail != "" else ""))


# ---- 4.1 管理员可访问 ----
st, qs = call("GET", "/admin/questions", ADMIN)
chk("4.1 管理员 GET /admin/questions", st == 200 and isinstance(qs, list),
    f"status={st} count={len(qs) if isinstance(qs, list) else qs}")

# ---- 4.2 覆盖统计（concept 口径）----
st, cov = call("GET", "/admin/knowledge-coverage", ADMIN)
brief = {k: cov.get(k) for k in ("concept_total", "covered", "uncovered", "question_total")} if isinstance(cov, dict) else cov
chk("4.2 GET /admin/knowledge-coverage concept 口径 56",
    st == 200 and isinstance(cov, dict) and cov.get("concept_total") == 56, f"status={st} {brief}")

# ---- 4.3 管理员建 shared 题并绑定 concept ----
payload = {
    "subject": "数据结构",
    "knowledge_point": "M4部署自检题",
    "question_type": "choice",
    "stem": "M4 部署自检（稍后删除）：循环单链表中，尾结点的 next 指针指向？",
    "options": ["NULL", "头结点", "自身或头结点（构成环）", "随机地址"],
    "answer": "自身或头结点（构成环）",
    "analysis": "自检题，测试完成后删除",
    "difficulty": "easy",
    "visibility": "shared",
    "knowledge_point_ids": [CONCEPT_ID],
}
st, created = call("POST", "/admin/questions", ADMIN, payload)
qid = created.get("id") if isinstance(created, dict) else None
chk("4.3 管理员建 shared 题并绑定 concept",
    st == 201 and isinstance(qid, int) and created.get("visibility") == "shared"
    and created.get("difficulty") == "easy",
    f"status={st} id={qid}")

# ---- 4.4 详情含结构化关联 ----
st, det = call("GET", f"/admin/questions/{qid}", ADMIN)
kps = det.get("knowledge_points") if isinstance(det, dict) else None
chk("4.4 GET /admin/questions/{id} 详情含关联",
    st == 200 and isinstance(kps, list) and len(kps) == 1 and kps[0]["knowledge_point_id"] == CONCEPT_ID,
    f"status={st} kps={kps if st == 200 else det}")

# ---- 4.5 container 绑定被服务层拒绝 ----
st, r = call("POST", f"/admin/questions/{qid}/knowledge-points", ADMIN,
             {"knowledge_point_id": CONTAINER_ID, "role": "secondary"})
chk("4.5 管理员绑定 container 被拒（服务层）", st in (400, 404, 409, 422), f"status={st} {r}")

# ---- 5.0 注册临时普通用户 ----
ts = int(time.time())
email = f"m4verify{ts}@example.com"
username = f"m4verify{ts}"
st, reg = call("POST", "/auth/register", None,
               {"email": email, "username": username, "password": "m4verify123"})
utok = reg.get("access_token") if isinstance(reg, dict) else None
uid = reg.get("user", {}).get("id") if isinstance(reg, dict) else None
chk("5.0 注册临时普通用户", st == 201 and bool(utok), f"status={st} uid={uid}")

# ---- 4.6 普通用户访问 admin 接口被拒 ----
for method, path, body in [
    ("GET", "/admin/questions", None),
    ("GET", f"/admin/questions/{qid}", None),
    ("POST", "/admin/questions", payload),
    ("GET", "/admin/knowledge-coverage", None),
]:
    st, r = call(method, path, utok, body)
    chk(f"4.6 普通用户 {method} {path} → 403", st == 403, f"status={st}")

# ---- 4.7 shared 题对普通用户可见 ----
st, bank = call("GET", "/question-bank", utok)
ids = [q["id"] for q in bank] if isinstance(bank, list) else []
chk("4.7 普通用户 GET /question-bank 可见 shared 题",
    st == 200 and qid in ids, f"status={st} n={len(ids)} contains={qid in ids}")

# ---- 4.8 他人私题 404 ----
st, r = call("POST", f"/questions/{EXISTING_ADMIN_PRIVATE_QID}/answers", utok, {"user_answer": "x"})
chk("4.8 普通用户答他人私题 → 404", st == 404, f"status={st} {r}")

# ---- 4.9 答题闭环：答错 ----
st, ans = call("POST", f"/questions/{qid}/answers", utok, {"user_answer": "错误答案-自检"})
chk("4.9 提交错误答案 → 201 判错",
    st == 201 and isinstance(ans, dict) and ans.get("is_correct") is False,
    f"status={st} {ans if st == 201 else ans}")

st, m = call("GET", f"/mastery/{CONCEPT_ID}", utok)
mbrief = {k: m.get(k) for k in ("attempt_count", "correct_count", "mastery_score", "correct_streak")} if isinstance(m, dict) else m
chk("4.10 掌握度生成且计一次错答",
    st == 200 and isinstance(m, dict) and m.get("attempt_count") == 1 and m.get("correct_count") == 0,
    f"status={st} {mbrief}")

# ---- 4.11 掌握度随答对提升（单调）----
st, ans2 = call("POST", f"/questions/{qid}/answers", utok, {"user_answer": payload["answer"]})
st2, m2 = call("GET", f"/mastery/{CONCEPT_ID}", utok)
mb2 = {k: m2.get(k) for k in ("attempt_count", "correct_count", "mastery_score", "correct_streak")} if isinstance(m2, dict) else m2
chk("4.11 答对后 attempt=2 correct=1 且分数提升",
    isinstance(m, dict) and isinstance(m2, dict) and m2.get("attempt_count") == 2
    and m2.get("correct_count") == 1 and m2.get("mastery_score") > m.get("mastery_score"),
    f"before={mbrief} after={mb2}")

print("_IDS_ " + json.dumps({"qid": qid, "uid": uid, "concept": CONCEPT_ID, "email": email}))
print(f"SUMMARY {sum(RESULTS)}/{len(RESULTS)} passed")
sys.exit(0 if all(RESULTS) else 1)
