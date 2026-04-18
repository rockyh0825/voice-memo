# Voice Memo API

音声メモの書き起こしテキストを Claude で要約する FastAPI サーバー。

## エンドポイント

- `GET /health` — 死活確認
- `POST /summarize-text` — テキストを要約

```json
// リクエスト
{ "text": "書き起こしテキスト..." }

// レスポンス
{ "summary": "要約結果..." }
```

## ローカル起動

```bash
# 依存関係インストール
uv sync

# .env を作成
echo "ANTHROPIC_API_KEY=sk-ant-xxxxx" > .env

# 起動
source .env && uv run uvicorn main:app --reload
```

## Ubuntu サーバーへのデプロイ

### 1. サーバーに uv をインストール

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### 2. リポジトリを clone

```bash
git clone https://github.com/YOUR_USERNAME/voice-memo.git
cd voice-memo
uv sync
```

### 3. APIキーを設定

```bash
nano .env
# ANTHROPIC_API_KEY=sk-ant-xxxxx と記載して保存

chmod 600 .env  # 自分のみ読み取り可能にする
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
