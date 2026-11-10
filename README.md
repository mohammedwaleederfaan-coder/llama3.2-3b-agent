# 🤖 AI Agent with Tool Calling

A local LLM agent built with **LangChain** and **Ollama** that decides on its own which tool to use (calculator, time, weather, web search, Excel, Word) to answer a request. Served as a **FastAPI** service and packaged with **Docker**.

## Features

- **Autonomous tool selection:** the model chooses the right tool, or answers directly when no tool is needed
- **8 tools** for math, time, weather, live news search, and office files (see below)
- **Conversation memory** per `thread_id`
- **Streaming responses** via a dedicated endpoint
- **Runs fully locally** with Ollama, no API keys required
- **Sandboxed file access:** all file tools are restricted to a single `workspace/` folder (path traversal blocked)
- **Dockerized:** one command to run the whole stack

## Tools

| Tool | Description |
|---|---|
| `calculator` | Safe arithmetic evaluator (AST-based, no `eval`) |
| `get_current_time` | Current date and time |
| `get_weather` | Current weather for a city (Open-Meteo) |
| `web_search` | Live news search (DuckDuckGo) with source URLs |
| `read_excel_file` | Columns, data types, shape and preview of an `.xlsx` file |
| `write_excel_with_formulas` | Creates an `.xlsx` file with data and Excel formulas |
| `create_pivot_table` | Pivot-style summary table (group by + optional cross-tab, with totals) |
| `word_document` | Creates a `.docx` report with headings, paragraphs, bullets and tables |

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
                       ├─ web_search  ──► DuckDuckGo News
                       └─ Excel / Word tools ──► workspace/
```

## Project Structure

```
├── agent.py            # Agent, tools and system prompt
├── api.py              # FastAPI application
├── workspace/          # Input/output files for the Excel and Word tools
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
| POST | `/chat/stream` | Streamed plain-text response (`X-Thread-Id` header) |

**Request body**

```json
{ "message": "What is 123 * 456?", "thread_id": "user-1" }
```

`thread_id` is optional. If omitted, a new one is generated and returned.

**Example**

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "What is the weather in Cairo?", "thread_id": "demo"}'
```

**Response**

```json
{
  "thread_id": "demo",
  "answer": "The current weather in Cairo is ...",
  "tools_used": ["get_weather"],
  "sources": []
}
```

Use the same `thread_id` across requests to keep the conversation context. For `web_search`, `sources` contains the article URLs.

## Working with Files

Input files (e.g. `sales.xlsx`) must be placed in the `workspace/` folder, and every generated file is saved there too. The tools only accept a file **name**, never a path.

Example prompts:

```
Read the file sales.xlsx and tell me its columns.
From sales.xlsx, create a pivot of Sales by Product and Region using sum.
Create a Word document named report.docx titled 'Sales Report' with a Summary section.
```

## Configuration

| Variable | Default | Description |
|---|---|---|
| `OLLAMA_URL` | `http://localhost:11434` | Ollama server URL |
| `OLLAMA_MODEL` | `llama3.2:3b` | Model name (must support tool calling) |
| `WORKSPACE_DIR` | `workspace` | Folder used by the Excel and Word tools |

To run the container against Ollama on your host machine instead of compose:

```bash
docker build -t ai-agent .
docker run -p 8000:8000 \
  -e OLLAMA_URL=http://host.docker.internal:11434 \
  -v ./workspace:/app/workspace \
  ai-agent
```

## Tech Stack

Python · LangChain · LangGraph · Ollama · FastAPI · Docker · pandas · openpyxl · python-docx

## Limitations

- Small models (3B) can occasionally pick the wrong tool, write weak search queries, or give an empty reply after a tool call (the API falls back to returning the tool result). Larger models such as `qwen2.5:7b` or `llama3.1:8b` perform noticeably better.
- Memory is stored in process RAM (`InMemorySaver`), so it is lost on restart and the service must run with a single worker.
- `create_pivot_table` produces a pivot-style summary table (values), not a native Excel PivotTable object.
- Formulas written by `write_excel_with_formulas` are calculated when the file is opened in Excel, not when it is created.

## Author

**Mohammed Waleed**
[LinkedIn](https://www.linkedin.com/in/mohammed-waleed-0065b9409/) · [GitHub](https://github.com/mohammedwaleederfaan-coder)