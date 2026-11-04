from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from langchain_core.messages import AIMessageChunk
from agent import agent

app = FastAPI(title="AI Agent API")

class ChatRequest(BaseModel):
    message: str
    thread_id: str = "default"

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/chat")
def chat(req: ChatRequest):
    config = {"configurable": {"thread_id": req.thread_id}}
    result = agent.invoke({"messages": [("user", req.message)]}, config)
    return {"answer": result["messages"][-1].content}

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