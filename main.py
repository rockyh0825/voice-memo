import os
import secrets
from contextlib import asynccontextmanager

import anthropic
from fastapi import Depends, FastAPI, HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not os.environ.get("API_TOKEN"):
        raise RuntimeError("API_TOKEN environment variable is not set")
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

class SummarizeRequest(BaseModel):
    text: str

class SummarizeResponse(BaseModel):
    summary: str

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/summarize-text", response_model=SummarizeResponse, dependencies=[Depends(verify_token)])
def summarize_text(body: SummarizeRequest):
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
                    "以下の音声メモの書き起こしを簡潔に要約してください。"
                    "要点を箇条書きでまとめ、最後に1〜2文のサマリーを加えてください。\n\n"
                    f"書き起こし:\n{body.text}"
                ),
            }
        ],
    )
    return SummarizeResponse(summary=message.content[0].text)
