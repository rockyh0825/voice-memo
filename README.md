# Voice Memo API

音声メモの書き起こしテキストから Claude でタスクを抽出し、Supabase に保存する FastAPI サーバー。

## エンドポイント

- `GET /health` — 死活確認
- `POST /extract-tasks` — テキストからタスクを抽出して保存

```json
// リクエスト
{
  "text": "明日までに企画書を提出して、牛乳も買っておく",
  "user_id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
}

// レスポンス
{
  "tasks": [
    {
      "id": "...",
      "title": "企画書を提出する",
      "body": null,
      "priority": 1,
      "due_date": null,
      "status": "draft",
      "source": "voice"
    }
  ]
}
```

抽出されたタスクは `status=draft` で保存される。React PWA 側でユーザーが確認・編集して `todo` に変更する運用。

## ローカル起動

```bash
# 依存関係インストール
uv sync

# .env を作成（下記「環境変数」を参照）
nano .env

# 起動
set -a && source .env && set +a && uv run uvicorn main:app --reload
```

## Ubuntu サーバーへのデプロイ

### 1. サーバーに uv をインストール

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### 2. リポジトリを clone

```bash
git clone https://github.com/rockyh0825/voice-memo.git
cd voice-memo
uv sync
```

### 3. 環境変数を設定

```bash
nano .env
chmod 600 .env
```

### 4. systemd サービスとして登録

`/etc/systemd/system/voice-memo.service` を作成：

```ini
[Unit]
Description=Voice Memo API
After=network.target

[Service]
User=YOUR_USERNAME
WorkingDirectory=/home/YOUR_USERNAME/voice-memo
EnvironmentFile=/home/YOUR_USERNAME/voice-memo/.env
ExecStart=/home/YOUR_USERNAME/.local/bin/uv run uvicorn main:app --host 0.0.0.0 --port 8000
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable voice-memo
sudo systemctl start voice-memo

# 動作確認
sudo systemctl status voice-memo
curl http://localhost:8000/health
```

### 5. アップデート手順

```bash
cd voice-memo
git pull origin main
uv sync
sudo systemctl restart voice-memo
```

## 環境変数

| 変数名 | 説明 |
|---|---|
| `ANTHROPIC_API_KEY` | Anthropic の API キー（必須） |
| `API_TOKEN` | API アクセス用の Bearer トークン（`openssl rand -hex 32` で生成） |
| `SUPABASE_URL` | Supabase プロジェクトの URL |
| `SUPABASE_SERVICE_KEY` | Supabase の service_role キー（Project Settings → API） |

いずれかが未設定の場合、起動時に `RuntimeError` を投げて終了する。

## API 認証

`/health` を除くすべてのエンドポイントに Bearer トークンが必要。

```bash
curl -X POST http://localhost:8000/extract-tasks \
  -H "Authorization: Bearer <API_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"text": "...", "user_id": "..."}'
```

## スキーマ管理

Supabase のマイグレーションは `supabase/migrations/` で管理。

```bash
# 変更を適用
supabase db push

# TypeScript 型を再生成（フロント用）
supabase gen types typescript --project-id hqmclmorcegnffrgbltz > supabase/types.ts
```
