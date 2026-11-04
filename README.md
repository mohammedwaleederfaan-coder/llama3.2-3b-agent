# 🤖 AI Agent with Tool Calling

A local LLM agent built with **LangChain** and **Ollama** that decides on its own which tool to use (calculator, time, weather, live web search) to answer a question. Served as a **FastAPI** service and packaged with **Docker**.

## Features

- **Autonomous tool selection:** the model chooses the right tool, or answers directly when no tool is needed
- **4 tools:** calculator, current time, weather (Open-Meteo), live news search (DuckDuckGo)
- **Conversation memory** per `thread_id`
- **Streaming responses** via a dedicated endpoint
- **Runs fully locally** with Ollama, no API keys required
- **Dockerized:** one command to run the whole stack

## Architecture

```
Client ──► FastAPI (/chat, /chat/stream)
                │
                ▼
        LangChain Agent (create_agent)
           │            │
           ▼            ▼
    Ollama (LLM)      Tools
                       ├─ calculator
                       ├─ get_current_time
                       ├─ get_weather ──► Open-Meteo API
                       └─ web_search  ──► DuckDuckGo News
```

## Project Structure

```
├── agent.py            # Agent, tools and system prompt
├── api.py              # FastAPI application
├── notebooks/
│   └── agent_demo.ipynb  # Interactive demo
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
└── README.md
```

## Quick Start

### Option 1: Docker Compose (recommended)

```bash
git clone https://github.com/mohammedwaleederfaan-coder/llama3.2-3b-agent.git
cd llama3.2-3b-agent
docker compose up --build
```

The first run downloads the model (~2 GB). When it's done, open the interactive docs at **http://localhost:8000/docs**.

### Option 2: Local

1. Install [Ollama](https://ollama.com) and pull the model:
   ```bash
   ollama pull llama3.2:3b
   ```
2. Install dependencies and run:
   ```bash
   python -m venv venv
   venv\Scripts\activate        # Linux/Mac: source venv/bin/activate
   pip install -r requirements.txt
   uvicorn api:app --reload
   ```

## API Usage

| Method | Endpoint | Description |
|---|---|---|
| GET | `/health` | Health check |
| POST | `/chat` | Full response in one JSON |
| POST | `/chat/stream` | Streamed plain-text response |

**Request body**

```json
{ "message": "What is 123 * 456?", "thread_id": "user-1" }
```

**Example**

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "What is the weather in Cairo?", "thread_id": "demo"}'
```

**Response**

```json
{ "answer": "The current weather in Cairo is ..." }
```

Use the same `thread_id` across requests to keep the conversation context.

## Configuration

| Variable | Default | Description |
|---|---|---|
| `OLLAMA_URL` | `http://localhost:11434` | Ollama server URL |
| `OLLAMA_MODEL` | `llama3.2:3b` | Model name (must support tool calling) |

To run the container against Ollama on your host machine instead of compose:

```bash
docker build -t ai-agent .
docker run -p 8000:8000 -e OLLAMA_URL=http://host.docker.internal:11434 ai-agent
```

## Tech Stack

Python · LangChain · LangGraph · Ollama · FastAPI · Docker

## Limitations

- Small models (3B) can occasionally pick the wrong tool or write weak search queries. Larger models such as `qwen2.5:7b` or `llama3.1:8b` perform noticeably better.
- Memory is stored in process RAM (`InMemorySaver`), so it is lost on restart and the service must run with a single worker.
- The calculator uses a restricted `eval` and is meant for simple arithmetic only.

## Roadmap

- [ ] RAG tool over a PDF book (LangChain + Chroma)
- [ ] Persistent memory (SQLite/Postgres checkpointer)
- [ ] Simple web UI

## Author

**YOUR_NAME**
[LinkedIn](https://www.linkedin.com/in/mohammed-waleed-0065b9409/) · [GitHub]([https://github.com/YOUR_USERNAME](https://github.com/mohammedwaleederfaan-coder))
