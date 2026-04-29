import os
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from main import app

TEST_TOKEN = "test-token-abc123"

client = TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def set_env(monkeypatch):
    monkeypatch.setenv("API_TOKEN", TEST_TOKEN)


def auth_headers(token: str = TEST_TOKEN) -> dict:
    return {"Authorization": f"Bearer {token}"}


class TestHealth:
    def test_returns_200_without_token(self):
        res = client.get("/health")
        assert res.status_code == 200
        assert res.json() == {"status": "ok"}

    def test_returns_200_with_token(self):
        res = client.get("/health", headers=auth_headers())
        assert res.status_code == 200


class TestSummarizeTextAuth:
    def test_no_token_returns_401(self):
        res = client.post("/summarize-text", json={"text": "hello"})
        assert res.status_code == 401

    def test_wrong_token_returns_401(self):
        res = client.post(
            "/summarize-text",
            json={"text": "hello"},
            headers=auth_headers("wrong-token"),
        )
        assert res.status_code == 401
        assert res.json()["detail"] == "Invalid token"

    def test_api_token_not_set_raises_on_startup(self, monkeypatch):
        monkeypatch.delenv("API_TOKEN")
        with pytest.raises(RuntimeError, match="API_TOKEN"):
            with TestClient(app):
                pass


class TestSummarizeText:
    def _mock_anthropic(self, summary: str = "要約テキスト"):
        mock_client = MagicMock()
        mock_client.messages.create.return_value = MagicMock(
            content=[MagicMock(text=summary)]
        )
        return mock_client

    def test_valid_request_returns_summary(self, monkeypatch):
        mock_client = self._mock_anthropic("要点: テスト")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "dummy-key")
        with patch("main.anthropic.Anthropic", return_value=mock_client):
            res = client.post(
                "/summarize-text",
                json={"text": "これはテストです"},
                headers=auth_headers(),
            )
        assert res.status_code == 200
        assert res.json()["summary"] == "要点: テスト"

    def test_empty_text_returns_400(self):
        res = client.post(
            "/summarize-text",
            json={"text": "   "},
            headers=auth_headers(),
        )
        assert res.status_code == 400
        assert res.json()["detail"] == "text is empty"

    def test_anthropic_key_not_set_returns_500(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        res = client.post(
            "/summarize-text",
            json={"text": "テスト"},
            headers=auth_headers(),
        )
        assert res.status_code == 500
        assert res.json()["detail"] == "ANTHROPIC_API_KEY is not set"
