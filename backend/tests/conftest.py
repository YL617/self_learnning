import os
import tempfile

os.environ["DATABASE_URL"] = (
    f"sqlite:///{tempfile.gettempdir()}/ai_study_test_{os.getpid()}.db"
)
os.environ["SECRET_KEY"] = "test-secret"
os.environ["DEEPSEEK_API_KEY"] = ""

import pytest
from fastapi.testclient import TestClient

from app.core.database import Base, engine
from app.main import app


@pytest.fixture(scope="session", autouse=True)
def setup_database():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(autouse=True)
def mock_ai(monkeypatch):
    import re

    from app.services.ai_gateway import AIModelGateway

    def fake_chat(self, messages, *, temperature=0.7, timeout=60.0):
        system = messages[0]["content"] if messages else ""
        if "学习规划顾问" in system:
            return "离线降级响应：请在 .env 中配置模型 API Key 后获得完整能力。"
        return "好的，我们一起加油！记得按计划完成今天的复习哦。"

    def fake_generate_json(self, system: str, user: str, temperature: float = 0.3):
        if "items" in system:
            return {
                "title": "Mock Plan",
                "goal": "Mock goal",
                "items": [
                    {
                        "title": f"Task {index}",
                        "subject": "Mock",
                        "scheduled_date": "2026-08-09",
                        "duration_minutes": 60,
                        "order_index": index,
                    }
                    for index in range(1, 5)
                ],
            }
        count_match = re.search(r"数量：(\d+)", user)
        count = int(count_match.group(1)) if count_match else 1
        type_match = re.search(r"题型：(\w+)", user)
        question_type = type_match.group(1) if type_match else "choice"
        stem_offset = 100 if "原始题目：" in user else 0
        return [
            {
                "subject": "Mock Subject",
                "knowledge_point": "Mock Point",
                "question_type": question_type,
                "stem": f"Mock question stem {stem_offset + index}",
                "options": ["A. 1", "B. 2", "C. 3", "D. 4"],
                "answer": "A",
                "analysis": "Mock analysis with enough detail for testing purposes and review hints.",
            }
            for index in range(1, count + 1)
        ]

    monkeypatch.setattr(AIModelGateway, "generate_json", fake_generate_json)
    monkeypatch.setattr(AIModelGateway, "chat", fake_chat)


@pytest.fixture()
def client():
    with TestClient(app) as test_client:
        yield test_client
