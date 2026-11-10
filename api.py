import json
import re
import uuid
from typing import Optional

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field
from langchain_core.messages import AIMessageChunk, ToolMessage

from agent import WORKSPACE, agent

app = FastAPI(title="AI Agent API")

ALLOWED_EXT = {".xlsx", ".xls", ".csv", ".docx"}
MAX_UPLOAD_MB = 10


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)
    thread_id: Optional[str] = Field(default=None, max_length=100)


# ---------- Helpers ----------
def extract_run_info(messages):
    """Tools used and source URLs for the latest question only."""
    humans = [i for i, m in enumerate(messages) if m.type == "human"]
    start = humans[-1] if humans else 0
    tools_used, urls = [], []
    for m in messages[start:]:
        if m.type == "tool":
            tools_used.append(m.name)
            urls += re.findall(r"URL: (\S+)", str(m.content))
    return list(dict.fromkeys(tools_used)), list(dict.fromkeys(urls))


def last_tool_output(messages):
    for m in reversed(messages):
        if m.type == "tool":
            return str(m.content)
    return None


def resolve_file(name: str):
    """Return a path inside WORKSPACE or raise 400."""
    clean = re.sub(r"[^\w.\- ]", "_", name.split("/")[-1].split("\\")[-1]).strip()
    if not clean or clean.startswith("."):
        raise HTTPException(400, "Invalid file name")
    path = (WORKSPACE / clean).resolve()
    if WORKSPACE not in path.parents:
        raise HTTPException(400, "Invalid file path")
    if path.suffix.lower() not in ALLOWED_EXT:
        raise HTTPException(400, f"Allowed types: {sorted(ALLOWED_EXT)}")
    return path


# ---------- Health ----------
@app.get("/health")
def health():
    return {"status": "ok"}


# ---------- Chat ----------
@app.post("/chat")
def chat(req: ChatRequest):
    thread_id = req.thread_id or str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}

    try:
        result = agent.invoke({"messages": [("user", req.message)]}, config)
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Agent error: {e}")

    messages = result["messages"]
    tools_used, sources = extract_run_info(messages)

    answer = str(messages[-1].content).strip()
    if not answer:
        tool_out = last_tool_output(messages)
        answer = f"(model gave no reply) Tool result: {tool_out}" if tool_out else "No answer."

    return {
        "thread_id": thread_id,
        "answer": answer,
        "tools_used": tools_used,
        "sources": sources,
    }


@app.post("/chat/stream")
def chat_stream(req: ChatRequest):
    """Plain-text token stream."""
    thread_id = req.thread_id or str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}

    def gen():
        got_text = False
        tool_out = None
        try:
            for chunk, _ in agent.stream(
                {"messages": [("user", req.message)]},
                config,
                stream_mode="messages",
            ):
                if isinstance(chunk, ToolMessage):
                    tool_out = str(chunk.content)
                elif isinstance(chunk, AIMessageChunk) and chunk.content:
                    got_text = True
                    yield chunk.content
            if not got_text and tool_out:
                yield f"(model gave no reply) Tool result: {tool_out}"
        except Exception as e:
            yield f"\n[Error: {e}]"

    return StreamingResponse(
        gen(),
        media_type="text/plain",
        headers={"X-Thread-Id": thread_id},
    )


@app.post("/chat/events")
def chat_events(req: ChatRequest):
    """NDJSON event stream: token / tool / error / done."""
    thread_id = req.thread_id or str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}

    def ev(**kw):
        return json.dumps(kw, ensure_ascii=False) + "\n"

    def gen():
        got_text = False
        tool_out = None
        tools, urls = [], []
        try:
            for chunk, _ in agent.stream(
                {"messages": [("user", req.message)]},
                config,
                stream_mode="messages",
            ):
                if isinstance(chunk, ToolMessage):
                    tool_out = str(chunk.content)
                    if chunk.name not in tools:
                        tools.append(chunk.name)
                        yield ev(type="tool", name=chunk.name)
                    urls += re.findall(r"URL: (\S+)", tool_out)
                elif isinstance(chunk, AIMessageChunk) and chunk.content:
                    got_text = True
                    yield ev(type="token", text=chunk.content)
            if not got_text and tool_out:
                yield ev(type="token",
                         text=f"(model gave no reply) Tool result: {tool_out}")
        except Exception as e:
            yield ev(type="error", message=str(e))
        yield ev(type="done", thread_id=thread_id,
                 sources=list(dict.fromkeys(urls)))

    return StreamingResponse(
        gen(),
        media_type="application/x-ndjson",
        headers={"X-Thread-Id": thread_id},
    )


# ---------- Files ----------
@app.get("/files")
def list_files():
    files = [
        {"name": p.name, "size_kb": round(p.stat().st_size / 1024, 1)}
        for p in sorted(WORKSPACE.iterdir())
        if p.is_file() and p.suffix.lower() in ALLOWED_EXT
    ]
    return {"files": files}


@app.post("/files")
async def upload_file(file: UploadFile = File(...)):
    path = resolve_file(file.filename or "")
    data = await file.read(MAX_UPLOAD_MB * 1024 * 1024 + 1)
    if len(data) > MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(413, f"File too large (max {MAX_UPLOAD_MB}MB)")
    path.write_bytes(data)
    return {"name": path.name, "size_kb": round(len(data) / 1024, 1)}


@app.get("/files/{name}")
def download_file(name: str):
    path = resolve_file(name)
    if not path.is_file():
        raise HTTPException(404, "File not found")
    return FileResponse(path, filename=path.name)