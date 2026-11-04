import datetime
import os
import requests # type: ignore
from ddgs import DDGS
from langchain_ollama import ChatOllama
from langchain_core.tools import tool
from langchain_core.messages import AIMessageChunk
from langchain.agents import create_agent
from langgraph.checkpoint.memory import InMemorySaver

llm = ChatOllama(
    model=os.getenv("OLLAMA_MODEL", "llama3.2:3b"),
    base_url=os.getenv("OLLAMA_URL", "http://localhost:11434"),
    temperature=0,
)

@tool
def calculator(expression: str) -> str:
    """Evaluate a mathematical expression like '2 + 2'. Use it for ANY arithmetic."""
    allowed = set("0123456789+-*/(). ")
    if not set(expression) <= allowed or "**" in expression:
        return "Invalid expression"
    try:
        return str(eval(expression, {"__builtins__": {}}, {}))
    except Exception as e:
        return f"Calculation failed: {e}"

@tool
def get_current_time() -> str:
    """This is a tool that returns the current time.
    Returns:
        str: The current time in HH:MM:SS format.
    e.g. "14:30:15"
    """
    return datetime.datetime.now().strftime("%H:%M:%S")


@tool
def get_weather(city: str) -> str:
    """Get the current weather for a city. Use it when the user asks about
    weather or temperature. Input is a city name in English, e.g. 'Cairo'."""
    try:
        # 1) اسم المدينة -> إحداثيات
        geo = requests.get(
            "https://geocoding-api.open-meteo.com/v1/search",
            params={"name": city, "count": 1},
            timeout=10,
        ).json()
        if not geo.get("results"):
            return f"Could not find city: {city}"
        place = geo["results"][0]

        w = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": place["latitude"],
                "longitude": place["longitude"],
                "current": "temperature_2m,relative_humidity_2m,wind_speed_10m",
            },
            timeout=10,
        ).json()["current"]

        return (
            f"{place['name']}, {place.get('country', '')}: "
            f"{w['temperature_2m']}°C, humidity {w['relative_humidity_2m']}%, "
            f"wind {w['wind_speed_10m']} km/h"
        )
    except Exception as e:
        return f"Weather lookup failed: {e}"

@tool
def web_search(query: str) -> str:
    """Search the internet for current information, news, or recent facts.
    Input is a short, specific English query, e.g. 'OpenAI new model release'."""
    try:
        with DDGS() as ddgs:
            results = list(ddgs.news(query, max_results=5))
        if not results:
            return "No results found."
        return "\n\n".join(
            f"Title: {r['title']}\nDate: {r.get('date', '')}\n"
            f"URL: {r['url']}\nSnippet: {r['body']}"
            for r in results
        )
    except Exception as e:
        return f"Search failed: {e}"

tools = [calculator, get_current_time, get_weather, web_search]

agent = create_agent(
    model = llm,
    tools = tools,
    system_prompt = """You are a helpful assistant with access to these tools:

- calculator: use it for ANY arithmetic. Never calculate in your head.
- get_current_time: use it when asked about the current time.
- get_weather: use it when asked about weather or temperature. Pass the city name in English (e.g. "Cairo").
- web_search: use it for news, recent events, or facts that may have changed. Pass a short English query.

Rules:
1. Call a tool only when it is needed. For general knowledge or casual chat, answer directly.
2. Never invent tool results. Use only what the tool returns.
3. After web_search, base your answer on the results and mention the source URL.
4. If a tool fails or returns nothing, say so honestly.
5. Always reply in the same language the user writes in (Arabic or English).
6. Keep answers short and clear."""
    ,
    checkpointer=InMemorySaver()
)
