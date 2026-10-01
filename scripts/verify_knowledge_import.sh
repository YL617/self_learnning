#!/usr/bin/env bash
# 大阶段 4 M2+M3 生产无污染 smoke
# 原则：只做「只读」与「preview dry-run」，绝不写入任何业务数据。
set -u
cd /opt/ai-study

BASE=http://127.0.0.1:8000/api/v1
TABLES="knowledge_points knowledge_point_import_batches users questions answer_records user_knowledge_point_mastery question_knowledge_points knowledge_point_prerequisites"

mysql_q() {
  docker compose exec -T mysql sh -c "mysql -uroot -p\"\$MYSQL_ROOT_PASSWORD\" -N -B -e '$1' ai_study" 2>/dev/null | tr -d '\r'
}

counts() {
  local out=""
  for t in $TABLES; do
    out="$out$t=$(mysql_q "SELECT COUNT(*) FROM $t;") "
  done
  echo "  $out"
}

code() { curl -s -o /dev/null -w '%{http_code}' --max-time 20 "$@"; }

echo "=== 1. 业务数据基线 ==="
counts

echo "=== 2. 未登录访问 6 个导入接口（期望全部 401）==="
for spec in \
  "POST $BASE/knowledge-import/preview" \
  "POST $BASE/knowledge-import/apply" \
  "GET  $BASE/knowledge-import/batches" \
  "GET  $BASE/knowledge-import/batches/1" \
  "POST $BASE/knowledge-import/batches/1/rollback" \
  "GET  $BASE/knowledge-import/template" ; do
  m=$(echo "$spec" | awk '{print $1}')
  u=$(echo "$spec" | awk '{print $2}')
  printf '  %-5s %-52s -> %s\n' "$m" "$u" "$(code -X "$m" "$u")"
done

echo "=== 3. 铸造管理员 token（容器内直接签 JWT，不写库、不改密码）==="
ADMIN_TOKEN=$(docker compose exec -T backend python -c "
from app.core.database import SessionLocal
from app.core.security import create_access_token
from app.models import User
db = SessionLocal()
u = db.query(User).filter(User.role == 'admin').order_by(User.id).first()
print(create_access_token(str(u.id)) if u else '')
" 2>/dev/null | tr -d '\r')
if [ -n "$ADMIN_TOKEN" ]; then
  echo "  admin token OK (len=${#ADMIN_TOKEN})"
else
  echo "  !! 未找到管理员账号，后续管理员检查无法进行"
fi

if [ -n "$ADMIN_TOKEN" ]; then
  echo "=== 4. 模板下载（期望 200 / text/csv / UTF-8 BOM）==="
  curl -s -D /tmp/m3_hdr.txt -o /tmp/m3_tpl.csv --max-time 20 \
    -H "Authorization: Bearer $ADMIN_TOKEN" "$BASE/knowledge-import/template"
  grep -iE '^HTTP/|^content-type|^content-disposition' /tmp/m3_hdr.txt | tr -d '\r'
  printf '  首 3 字节(BOM 应为 efbbbf): '
  head -c 3 /tmp/m3_tpl.csv | od -An -tx1 | tr -d ' \n'
  echo
  printf '  表头: '; head -1 /tmp/m3_tpl.csv | sed 's/^\xef\xbb\xbf//'
  printf '  行数: '; wc -l < /tmp/m3_tpl.csv

  echo "=== 5. 批次列表（期望 200）==="
  printf '  GET /batches -> %s  body=' "$(code -H "Authorization: Bearer $ADMIN_TOKEN" "$BASE/knowledge-import/batches")"
  curl -s --max-time 20 -H "Authorization: Bearer $ADMIN_TOKEN" "$BASE/knowledge-import/batches"
  echo

  echo "=== 6. preview dry-run（期望 200，且 planned.create=2，零写入）==="
  CONTENT=$(printf '学科,层级路径,知识点名,别名,难度,预计学时,编码\n数据结构,线性表>SMOKE父,SMOKE父,smoke,easy,10,SMOKE.P\n数据结构,线性表>SMOKE父>SMOKE子,SMOKE子,,medium,20,SMOKE.C')
  curl -s --max-time 30 -H "Authorization: Bearer $ADMIN_TOKEN" \
    -F "content=$CONTENT" -F 'conflict_strategy=skip' \
    "$BASE/knowledge-import/preview" > /tmp/m3_preview.json
  python3 - <<'PY'
import json
d = json.load(open('/tmp/m3_preview.json'))
print('  source_format =', d.get('source_format'))
print('  total_rows    =', d.get('total_rows'), ' error_rows =', d.get('error_rows'), ' warning_rows =', d.get('warning_rows'))
print('  planned       =', d.get('planned'))
print('  can_apply     =', d.get('can_apply'))
print('  前 2 行       =', [(r['row'], r['name'], r['action']) for r in d.get('rows', [])])
PY

  echo "=== 7. 再次计数（必须与基线逐项一致）==="
  counts

  echo "=== 8. 非管理员权限（期望 403）==="
  USER_TOKEN=$(docker compose exec -T backend python -c "
from app.core.database import SessionLocal
from app.core.security import create_access_token
from app.models import User
db = SessionLocal()
u = db.query(User).filter(User.role != 'admin').order_by(User.id).first()
print(create_access_token(str(u.id)) if u else '')
" 2>/dev/null | tr -d '\r')
  if [ -n "$USER_TOKEN" ]; then
    printf '  普通用户 GET /batches -> %s（期望 403）\n' \
      "$(code -H "Authorization: Bearer $USER_TOKEN" "$BASE/knowledge-import/batches")"
  else
    echo "  生产库没有非管理员账号；403 由 CI 测试组 K（6 接口 × 401/403）覆盖"
  fi
fi

echo "=== smoke 完成 ==="
