"""Append a review hint to questions with overly short analysis."""

import sqlite3
from pathlib import Path

DB = Path(__file__).resolve().parent.parent / "backend" / "ai_study_dev.db"

con = sqlite3.connect(str(DB))
rows = con.execute(
    "SELECT id, subject, knowledge_point, analysis FROM questions"
).fetchall()
updated = 0
for question_id, subject, knowledge_point, analysis in rows:
    current = (analysis or "").strip()
    if len(current) >= 40:
        continue
    hint = (
        f"复习提示：请结合{subject or '教材'}确认"
        f"「{knowledge_point or '该知识点'}」的定义、应用场景与常见错误。"
    )
    new_analysis = f"{current} {hint}" if current else hint
    con.execute(
        "UPDATE questions SET analysis = ? WHERE id = ?",
        (new_analysis, question_id),
    )
    updated += 1
con.commit()
con.close()
print(f"updated {updated} questions")
