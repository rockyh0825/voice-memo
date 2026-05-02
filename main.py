import json
import os
import secrets
from contextlib import asynccontextmanager
from datetime import date
from typing import Literal
from uuid import UUID

import anthropic
from fastapi import Depends, FastAPI, HTTPException, Query, Security
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from supabase import create_client


@asynccontextmanager
async def lifespan(app: FastAPI):
    missing = [v for v in ("API_TOKEN", "SUPABASE_URL", "SUPABASE_SERVICE_KEY", "USER_ID") if not os.environ.get(v)]
    if missing:
        raise RuntimeError(f"Required environment variables not set: {', '.join(missing)}")
    yield


app = FastAPI(title="Voice Memo API", lifespan=lifespan)
security = HTTPBearer(auto_error=False)

# CORS: localhost は常に許可、本番フロントのオリジンは FRONTEND_ORIGIN で追加
_cors_origins = ["http://localhost:5173", "http://localhost:5174"]
if _frontend_origin := os.environ.get("FRONTEND_ORIGIN"):
    _cors_origins.extend(o.strip() for o in _frontend_origin.split(",") if o.strip())
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)


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


# ---------- Models ----------

class ExtractTasksRequest(BaseModel):
    text: str


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


class TaskUpdateRequest(BaseModel):
    title: str | None = None
    body: str | None = None
    priority: int | None = None
    due_date: str | None = None
    status: Literal["draft", "todo", "done"] | None = None


# ---------- Endpoints ----------

@app.get("/health")
def health():
    return {"status": "ok", "env": os.environ.get("APP_ENV", "production")}


@app.get("/tasks", response_model=list[TaskOut], dependencies=[Depends(verify_token)])
def list_tasks(status: Literal["draft", "todo", "done"] | None = Query(default=None)):
    supabase = get_supabase_client()
    query = (
        supabase.table("tasks")
        .select("*")
        .eq("user_id", os.environ["USER_ID"])
    )
    if status:
        query = query.eq("status", status)
    result = query.order("priority").order("created_at").execute()
    return [TaskOut(**r) for r in result.data]


@app.patch("/tasks/{task_id}", response_model=TaskOut, dependencies=[Depends(verify_token)])
def update_task(task_id: UUID, body: TaskUpdateRequest):
    updates = {k: v for k, v in body.model_dump().items() if k in body.model_fields_set}
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    supabase = get_supabase_client()
    result = (
        supabase.table("tasks")
        .update(updates)
        .eq("id", str(task_id))
        .eq("user_id", os.environ["USER_ID"])
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Task not found")
    return TaskOut(**result.data[0])


@app.delete("/tasks/{task_id}", status_code=204, dependencies=[Depends(verify_token)])
def delete_task(task_id: UUID):
    supabase = get_supabase_client()
    result = (
        supabase.table("tasks")
        .delete()
        .eq("id", str(task_id))
        .eq("user_id", os.environ["USER_ID"])
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Task not found")


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
                    f"今日の日付: {date.today().isoformat()}\n\n"
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

    if not tasks_data:
        return ExtractTasksResponse(tasks=[])

    supabase = get_supabase_client()
    result = supabase.table("tasks").insert([
        {
            "user_id": os.environ["USER_ID"],
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
