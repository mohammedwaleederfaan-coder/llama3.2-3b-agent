import re
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from langchain_core.messages import AIMessageChunk
from agent import agent

app = FastAPI(title="AI Agent API")


class ChatRequest(BaseModel):
    message: str
    thread_id: str = "default"


def extract_run_info(messages):
    """Tools used and source URLs for the latest question only."""
    last_human = max(i for i, m in enumerate(messages) if m.type == "human")
    tools_used, urls = [], []
    for m in messages[last_human:]:
        if m.type == "tool":
            tools_used.append(m.name)
            urls += re.findall(r"URL: (\S+)", str(m.content))
    return list(dict.fromkeys(tools_used)), list(dict.fromkeys(urls))


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/chat")
def chat(req: ChatRequest):
    config = {"configurable": {"thread_id": req.thread_id}}
    result = agent.invoke({"messages": [("user", req.message)]}, config)
    tools_used, sources = extract_run_info(result["messages"])
    return {
        "answer": result["messages"][-1].content,
        "tools_used": tools_used,
        "sources": sources,
    }


@app.post("/chat/stream")
def chat_stream(req: ChatRequest):
    config = {"configurable": {"thread_id": req.thread_id}}

    def gen():
        for chunk, _ in agent.stream(
            {"messages": [("user", req.message)]}, config, stream_mode="messages"
        ):
            if isinstance(chunk, AIMessageChunk) and chunk.content:
                yield chunk.content

    return StreamingResponse(gen(), media_type="text/plain")