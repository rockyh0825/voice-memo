# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project does

音声メモの書き起こしテキストを受け取り、Claude API（claude-sonnet-4-6）で要約して返す FastAPI サーバー。Ubuntu サーバー上で systemd サービスとして稼働させることを想定している。

## Commands

パッケージ管理には `uv` を使用する。

```bash
# 依存関係インストール（dev含む）
uv sync

# サーバー起動（要 .env）
source .env && uv run uvicorn main:app --reload

# テスト実行
uv run pytest test_main.py -v

# 単一テスト実行
uv run pytest test_main.py::TestSummarizeTextAuth::test_wrong_token_returns_401 -v
```

## 環境変数

`.env` ファイルに以下を固定値で記載する（シェル展開は不可、systemd の `EnvironmentFile` はシェル展開しないため）。

```
ANTHROPIC_API_KEY=sk-ant-xxxxx
API_TOKEN=<openssl rand -hex 32 で生成した固定値>
```

`API_TOKEN` が未設定の場合、アプリは起動時（lifespan）に `RuntimeError` を投げて起動を拒否する。

## アーキテクチャ

エントリポイントは `main.py` のみ。すべてのロジックが1ファイルに収まっている。

**認証フロー:**
- `HTTPBearer(auto_error=False)` で Authorization ヘッダーを受け取る
- `verify_token` dependency が `credentials is None`（ヘッダーなし）と不一致の両方を 401 で返す
- タイミング攻撃対策として `secrets.compare_digest` でトークン比較
- `/health` のみ認証不要、それ以外は `dependencies=[Depends(verify_token)]` で保護

**Anthropic API 呼び出し:**
- `get_anthropic_client()` はリクエストごとにクライアントを生成する（接続プールの共有はしていない）
- プロンプトは日本語固定で、箇条書き＋1〜2文サマリーの形式を指定している

## テスト方針

`test_main.py` はモジュールレベルで `TestClient` を1つ生成し、`autouse` fixture で `API_TOKEN` を注入する。Anthropic API の呼び出しは `unittest.mock.patch` でモックする。lifespan（起動時チェック）のテストだけは `with TestClient(app):` を個別に生成して使う。
