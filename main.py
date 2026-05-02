import json
import os
import secrets
from contextlib import asynccontextmanager
from uuid import UUID

import anthropic
from fastapi import Depends, FastAPI, HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from supabase import create_client


@asynccontextmanager
async def lifespan(app: FastAPI):
    missing = [v for v in ("API_TOKEN", "SUPABASE_URL", "SUPABASE_SERVICE_KEY") if not os.environ.get(v)]
    if missing:
        raise RuntimeError(f"Required environment variables not set: {', '.join(missing)}")
    yield


app = FastAPI(title="Voice Memo API", lifespan=lifespan)
security = HTTPBearer(auto_error=False)


def verify_token(credentials: HTTPAuthorizationCredentials | None = Security(security)) -> None:
    if credentials is None:
        raise HTTPException(status_code=401, detail="Missing token")
    api_token = os.environ.get("API_TOKEN", "")
    if not secrets.compare_digest(credentials.credentials, api_token):
        raise HTTPException(status_code=401, detail="Invalid token")


def get_anthropic_client() -> anthropic.Anthropic:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="ANTHROPIC_API_KEY is not set")
    return anthropic.Anthropic(api_key=api_key)


def get_supabase_client():
    return create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])


class ExtractTasksRequest(BaseModel):
    text: str
    user_id: UUID


class TaskOut(BaseModel):
    id: UUID
    title: str
    body: str | None
    priority: int
    due_date: str | None
    status: str
    source: str


class ExtractTasksResponse(BaseModel):
    tasks: list[TaskOut]


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/extract-tasks", response_model=ExtractTasksResponse, dependencies=[Depends(verify_token)])
def extract_tasks(body: ExtractTasksRequest):
    if not body.text.strip():
        raise HTTPException(status_code=400, detail="text is empty")

    client = get_anthropic_client()
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        messages=[
            {
                "role": "user",
                "content": (
                    "以下の音声メモの書き起こしからタスクを抽出してください。\n"
                    "JSONの配列形式のみで返してください。説明文は不要です。各要素のフィールド:\n"
                    "- title: string (必須)\n"
                    "- body: string | null\n"
                    "- priority: 1〜4の整数 (1=緊急, 2=高, 3=中, 4=なし)\n"
                    "- due_date: string | null (YYYY-MM-DD、言及がある場合のみ)\n\n"
                    f"書き起こし:\n{body.text}"
                ),
            }
        ],
    )

    try:
        raw = message.content[0].text.strip()
        # Claude may wrap JSON in markdown code blocks
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1]
            raw = raw.rsplit("```", 1)[0].strip()
        tasks_data = json.loads(raw)
    except (json.JSONDecodeError, IndexError):
        raise HTTPException(status_code=500, detail="Failed to parse tasks from AI response")

    supabase = get_supabase_client()
    result = supabase.table("tasks").insert([
        {
            "user_id": str(body.user_id),
            "title": t["title"],
            "body": t.get("body"),
            "priority": t.get("priority", 3),
            "due_date": t.get("due_date"),
            "status": "draft",
            "source": "voice",
        }
        for t in tasks_data
    ]).execute()

    return ExtractTasksResponse(tasks=[TaskOut(**r) for r in result.data])
