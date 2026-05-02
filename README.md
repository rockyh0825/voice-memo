# Voice Memo API

音声メモの書き起こしテキストから Claude でタスクを抽出し、Supabase に保存する FastAPI サーバー。

## エンドポイント

- `GET /health` — 死活確認
- `POST /extract-tasks` — テキストからタスクを抽出して保存（要 Bearer 認証）

```json
// リクエスト
{ "text": "明日までに企画書を提出して、牛乳も買っておく" }

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

---

## 環境変数

`.env` に以下を記載する（値を `"` で囲まない）。

| 変数名 | 説明 | 生成方法 |
|---|---|---|
| `ANTHROPIC_API_KEY` | Anthropic の API キー | Anthropic Console |
| `API_TOKEN` | API アクセス用 Bearer トークン | `openssl rand -hex 32` |
| `SUPABASE_URL` | Supabase プロジェクト URL | Project Settings → API |
| `SUPABASE_SERVICE_KEY` | Supabase service_role キー | Project Settings → API |
| `USER_ID` | Supabase Auth のユーザー UUID | Supabase ダッシュボード Authentication → Users |

いずれかが未設定の場合、起動時に `RuntimeError` を投げて終了する。

---

## デプロイ手順（初回）

### 1. uv をインストール

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
source $HOME/.local/bin/env  # または新しいシェルを開く
```

### 2. リポジトリを clone して依存関係をインストール

```bash
git clone https://github.com/rockyh0825/voice-memo.git
cd voice-memo
uv sync
```

### 3. 環境変数を設定

```bash
nano .env        # 上記「環境変数」をすべて記載
chmod 600 .env   # 自分のみ読み取り可能に
```

### 4. systemd サービスを登録

`/etc/systemd/system/voice-memo.service` を作成（`YOUR_USERNAME` は実際のユーザー名に置き換え）：

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
```

### 5. 動作確認

```bash
sudo systemctl status voice-memo
curl http://localhost:8000/health
# → {"status":"ok"}

curl -X POST http://localhost:8000/extract-tasks \
  -H "Authorization: Bearer <API_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"text": "牛乳を買う"}'
```

---

## デプロイ手順（更新時）

```bash
cd voice-memo
git pull origin main
uv sync                          # 依存関係の変更があった場合に反映
sudo systemctl restart voice-memo
sudo systemctl status voice-memo  # active (running) であることを確認
```

---

## ローカル起動（開発時）

```bash
uv sync
nano .env  # 環境変数を設定
set -a && source .env && set +a && uv run uvicorn main:app --reload
```

---

## スキーマ管理

Supabase のマイグレーションは `supabase/migrations/` で管理。

```bash
# 変更を適用
supabase db push

# TypeScript 型を再生成（フロント用）
supabase gen types typescript --project-id hqmclmorcegnffrgbltz > supabase/types.ts
```
