import json
import os
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from main import app

TEST_TOKEN = "test-token-abc123"
TEST_USER_ID = str(uuid4())

client = TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def set_env(monkeypatch):
    monkeypatch.setenv("API_TOKEN", TEST_TOKEN)
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "dummy-supabase-key")


def auth_headers(token: str = TEST_TOKEN) -> dict:
    return {"Authorization": f"Bearer {token}"}


def make_supabase_mock(inserted_rows: list[dict]):
    mock_result = MagicMock()
    mock_result.data = inserted_rows
    mock_table = MagicMock()
    mock_table.insert.return_value.execute.return_value = mock_result
    mock_supabase = MagicMock()
    mock_supabase.table.return_value = mock_table
    return mock_supabase


class TestHealth:
    def test_returns_200_without_token(self):
        res = client.get("/health")
        assert res.status_code == 200
        assert res.json() == {"status": "ok"}

    def test_returns_200_with_token(self):
        res = client.get("/health", headers=auth_headers())
        assert res.status_code == 200


class TestExtractTasksAuth:
    def test_no_token_returns_401(self):
        res = client.post("/extract-tasks", json={"text": "hello", "user_id": TEST_USER_ID})
        assert res.status_code == 401

    def test_wrong_token_returns_401(self):
        res = client.post(
            "/extract-tasks",
            json={"text": "hello", "user_id": TEST_USER_ID},
            headers=auth_headers("wrong-token"),
        )
        assert res.status_code == 401
        assert res.json()["detail"] == "Invalid token"

    def test_missing_env_raises_on_startup(self, monkeypatch):
        monkeypatch.delenv("API_TOKEN")
        with pytest.raises(RuntimeError, match="API_TOKEN"):
            with TestClient(app):
                pass


class TestExtractTasks:
    def _mock_anthropic(self, tasks: list[dict]):
        mock_client = MagicMock()
        mock_client.messages.create.return_value = MagicMock(
            content=[MagicMock(text=json.dumps(tasks))]
        )
        return mock_client

    def _task_row(self, title: str = "テストタスク") -> dict:
        return {
            "id": str(uuid4()),
            "title": title,
            "body": None,
            "priority": 3,
            "due_date": None,
            "status": "draft",
            "source": "voice",
        }

    def test_valid_request_returns_tasks(self, monkeypatch):
        extracted = [{"title": "牛乳を買う", "body": None, "priority": 3, "due_date": None}]
        row = self._task_row("牛乳を買う")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "dummy-key")
        with (
            patch("main.anthropic.Anthropic", return_value=self._mock_anthropic(extracted)),
            patch("main.get_supabase_client", return_value=make_supabase_mock([row])),
        ):
            res = client.post(
                "/extract-tasks",
                json={"text": "牛乳を買っておいて", "user_id": TEST_USER_ID},
                headers=auth_headers(),
            )
        assert res.status_code == 200
        tasks = res.json()["tasks"]
        assert len(tasks) == 1
        assert tasks[0]["title"] == "牛乳を買う"
        assert tasks[0]["status"] == "draft"
        assert tasks[0]["source"] == "voice"

    def test_empty_text_returns_400(self):
        res = client.post(
            "/extract-tasks",
            json={"text": "   ", "user_id": TEST_USER_ID},
            headers=auth_headers(),
        )
        assert res.status_code == 400
        assert res.json()["detail"] == "text is empty"

    def test_anthropic_key_not_set_returns_500(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        res = client.post(
            "/extract-tasks",
            json={"text": "テスト", "user_id": TEST_USER_ID},
            headers=auth_headers(),
        )
        assert res.status_code == 500
        assert res.json()["detail"] == "ANTHROPIC_API_KEY is not set"

    def test_no_tasks_extracted_returns_empty(self, monkeypatch):
        mock_client = MagicMock()
        mock_client.messages.create.return_value = MagicMock(
            content=[MagicMock(text="[]")]
        )
        monkeypatch.setenv("ANTHROPIC_API_KEY", "dummy-key")
        with patch("main.anthropic.Anthropic", return_value=mock_client):
            res = client.post(
                "/extract-tasks",
                json={"text": "今日はいい天気ですね", "user_id": TEST_USER_ID},
                headers=auth_headers(),
            )
        assert res.status_code == 200
        assert res.json() == {"tasks": []}

    def test_invalid_ai_response_returns_500(self, monkeypatch):
        mock_client = MagicMock()
        mock_client.messages.create.return_value = MagicMock(
            content=[MagicMock(text="これはJSONではありません")]
        )
        monkeypatch.setenv("ANTHROPIC_API_KEY", "dummy-key")
        with patch("main.anthropic.Anthropic", return_value=mock_client):
            res = client.post(
                "/extract-tasks",
                json={"text": "テスト", "user_id": TEST_USER_ID},
                headers=auth_headers(),
            )
        assert res.status_code == 500
        assert res.json()["detail"] == "Failed to parse tasks from AI response"
