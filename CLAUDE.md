# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project does

音声メモの書き起こしテキストを受け取り、Claude API（claude-sonnet-4-6）でタスクを抽出して Supabase に保存する FastAPI サーバー。Ubuntu サーバー上で systemd サービスとして稼働させることを想定している。

## Commands

パッケージ管理には `uv` を使用する。

```bash
# 依存関係インストール（dev含む）
uv sync

# サーバー起動（要 .env）
set -a && source .env && set +a && uv run uvicorn main:app --reload

# テスト実行
uv run pytest test_main.py -v

# 単一テスト実行
uv run pytest test_main.py::TestExtractTasksAuth::test_wrong_token_returns_401 -v

# Supabase マイグレーション適用
supabase db push

# Supabase TypeScript 型の再生成
supabase gen types typescript --project-id hqmclmorcegnffrgbltz > supabase/types.ts
```

## 環境変数

`.env` ファイルに以下を固定値で記載する（シェル展開は不可、systemd の `EnvironmentFile` はシェル展開しないため）。

```
ANTHROPIC_API_KEY=sk-ant-xxxxx
API_TOKEN=<openssl rand -hex 32 で生成した固定値>
SUPABASE_URL=https://hqmclmorcegnffrgbltz.supabase.co
SUPABASE_SERVICE_KEY=<Supabase Project Settings → API → service_role キー>
```

`API_TOKEN`・`SUPABASE_URL`・`SUPABASE_SERVICE_KEY` のいずれかが未設定の場合、アプリは起動時（lifespan）に `RuntimeError` を投げて起動を拒否する。

## アーキテクチャ

エントリポイントは `main.py` のみ。すべてのロジックが1ファイルに収まっている。

**認証フロー:**
- `HTTPBearer(auto_error=False)` で Authorization ヘッダーを受け取る
- `verify_token` dependency が `credentials is None`（ヘッダーなし）と不一致の両方を 401 で返す
- タイミング攻撃対策として `secrets.compare_digest` でトークン比較
- `/health` のみ認証不要、それ以外は `dependencies=[Depends(verify_token)]` で保護

**タスク抽出フロー:**
- `POST /extract-tasks` で音声メモのテキストと `user_id` を受け取る
- Claude API にタスクの JSON 配列を生成させる（Claude がコードブロックで返す場合はマークダウンを除去）
- 抽出結果を Supabase の `tasks` テーブルに `status=draft` / `source=voice` で INSERT
- タスクが抽出されなかった場合は空配列を返す（Supabase への INSERT はスキップ）

**Supabase:**
- `get_supabase_client()` はリクエストごとに `service_role` キーでクライアントを生成（RLS をバイパス）
- スキーマ管理は `supabase/migrations/` で行い `supabase db push` で適用する

## テスト方針

`test_main.py` はモジュールレベルで `TestClient` を1つ生成し、`autouse` fixture で `API_TOKEN`・`SUPABASE_URL`・`SUPABASE_SERVICE_KEY` を注入する。Anthropic API と Supabase クライアントは `unittest.mock.patch` でモックする。lifespan（起動時チェック）のテストだけは `with TestClient(app):` を個別に生成して使う。

## ブランチ運用

`main` ブランチは保護されており直接 push 不可。変更は必ず feature ブランチ → PR → マージの流れで行う。
