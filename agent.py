import ast
import datetime
import operator
import os
from pathlib import Path

import openpyxl
import pandas as pd
import requests
from ddgs import DDGS
from docx import Document
from langchain.agents import create_agent
from langchain_core.tools import tool
from langchain_ollama import ChatOllama
from langgraph.checkpoint.memory import InMemorySaver
from openpyxl.styles import Font


# ---------- Config ----------

llm = ChatOllama(
    model=os.getenv("OLLAMA_MODEL", "qwen3:4b"),
    base_url=os.getenv("OLLAMA_URL", "http://localhost:11434"),
    temperature=0,
)

WORKSPACE = Path(os.getenv("WORKSPACE_DIR", "workspace")).resolve()
WORKSPACE.mkdir(parents=True, exist_ok=True)


# ---------- Helpers ----------
def _safe_path(name: str, ext: str | None = None) -> Path:
    """Resolve a file name inside WORKSPACE only (blocks ../ and absolute paths)."""
    p = (WORKSPACE / Path(str(name)).name).resolve()
    if ext and p.suffix.lower() != ext:
        p = p.with_suffix(ext)
    if WORKSPACE not in p.parents:
        raise ValueError("Invalid file path")
    return p


_OPS = {
    ast.Add: operator.add, ast.Sub: operator.sub,
    ast.Mult: operator.mul, ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv, ast.Mod: operator.mod,
    ast.Pow: operator.pow, ast.USub: operator.neg, ast.UAdd: operator.pos,
}


def _safe_eval(node):
    if isinstance(node, ast.Expression):
        return _safe_eval(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
        left, right = _safe_eval(node.left), _safe_eval(node.right)
        if isinstance(node.op, ast.Pow) and abs(right) > 100:
            raise ValueError("Exponent too large")
        return _OPS[type(node.op)](left, right)
    if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_safe_eval(node.operand))
    raise ValueError("Unsupported expression")


def _parse_sheet(sheet_name: str):
    """'0' -> 0 (index), 'Sales' -> 'Sales' (name)."""
    s = str(sheet_name).strip()
    return int(s) if s.isdigit() else s


# ---------- Tools ----------
@tool
def calculator(expression: str) -> str:
    """Evaluate a mathematical expression.
    Args:
        expression: e.g. "2 + 2" or "(10 + 5) * 3"
    Returns:
        The result as a string.
    """
    try:
        return str(_safe_eval(ast.parse(expression.strip(), mode="eval")))
    except ZeroDivisionError:
        return "Error: division by zero"
    except Exception:
        return "Invalid Expression"


@tool
def get_current_time() -> str:
    """Return the current date and time in 'YYYY-MM-DD HH:MM:SS' format."""
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


@tool
def get_weather(city: str) -> str:
    """Get the current weather for a city. Use it when the user asks about
    weather or temperature. Input is a city name in English, e.g. 'Cairo'."""
    try:
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
            f"Title: {r.get('title', '')}\nDate: {r.get('date', '')}\n"
            f"URL: {r.get('url') or r.get('href', '')}\n"
            f"Snippet: {r.get('body', '')}"
            for r in results
        )
    except Exception as e:
        return f"Search failed: {e}"


@tool
def read_excel_file(file_path: str, sheet_name: str = "0") -> str:
    """Read an existing Excel file and return its columns, shape, and a 5-row preview.
    Args:
        file_path: Name of the Excel file.
        sheet_name: Sheet name or index (default "0" = first sheet).
    """
    try:
        path = _safe_path(file_path)
        if not path.exists():
            return f"File not found: {path.name}"
        df = pd.read_excel(path, sheet_name=_parse_sheet(sheet_name))
        summary = {
            "columns": list(df.columns),
            "dtypes": {c: str(t) for c, t in df.dtypes.items()},
            "shape": f"{df.shape[0]} rows, {df.shape[1]} columns",
            "preview": df.head(5).to_dict(orient="records"),
        }
        return f"File read successfully. Summary: {summary}"
    except Exception as e:
        return f"Error reading Excel file: {e}"


@tool
def write_excel_with_formulas(
    headers: list[str],
    rows: list[list],
    formulas: dict | None = None,
    file_name: str = "output_with_formulas.xlsx",
) -> str:
    """Create an Excel file with data and Excel formulas.
    Args:
        headers: Column titles.
        rows: 2D list of data rows.
        formulas: Maps cell coordinates to formulas,
                  e.g. {"D2": "=SUM(B2:C2)"}
        file_name: Output filename (.xlsx).
    """
    try:
        path = _safe_path(file_name, ".xlsx")
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Data"

        ws.append(headers)
        for row in rows:
            ws.append(row)

        for cell, formula in (formulas or {}).items():
            ws[cell] = formula

        wb.save(path)
        return f"Excel file with formulas saved as: {path.name}"
    except Exception as e:
        return f"Error writing formulas: {e}"


@tool
def create_pivot_table(
    file_path: str,
    index_col: str,
    values_col: str,
    agg_func: str = "sum",
    columns_col: str = "",
    sheet_name: str = "0",
    output_file: str = "pivot_report.xlsx",
) -> str:
    """Create a summary (pivot-style) table from an Excel file and save it.
    Args:
        file_path: Source Excel file name.
        index_col: Column to group by (rows).
        values_col: Column to aggregate.
        agg_func: One of 'sum', 'mean', 'count', 'max', 'min'.
        columns_col: Optional column to spread across as columns (cross-tab).
        sheet_name: Sheet name or index (default "0").
        output_file: Output file name.
    """
    allowed = {"sum", "mean", "count", "max", "min"}
    if agg_func not in allowed:
        return f"Invalid agg_func '{agg_func}'. Use one of: {sorted(allowed)}"
    try:
        src = _safe_path(file_path)
        if not src.exists():
            return f"File not found: {src.name}"
        out = _safe_path(output_file, ".xlsx")

        df = pd.read_excel(src, sheet_name=_parse_sheet(sheet_name))
        pivot_df = pd.pivot_table(
            df,
            index=index_col,
            columns=columns_col or None,
            values=values_col,
            aggfunc=agg_func,
            margins=True,
            margins_name="Total",
            fill_value=0,
        ).reset_index()
        pivot_df.columns = [str(c) for c in pivot_df.columns]
        pivot_df.to_excel(out, index=False, engine="openpyxl")

        wb = openpyxl.load_workbook(out)
        ws = wb.active
        for cell in ws[1]:
            cell.font = Font(bold=True)
        for col in ws.columns:
            ws.column_dimensions[col[0].column_letter].width = 16
        wb.save(out)

        return f"Pivot-style table saved as: {out.name}"
    except Exception as e:
        return f"Error generating pivot table: {e}"


@tool
def word_document(
    title: str,
    sections: list[dict],
    file_name: str = "advanced_report.docx",
) -> str:
    """Create a structured Word document (.docx).
    Args:
        title: Main title of the document.
        sections: List of dicts, each may contain:
            - "heading": str
            - "paragraphs": list[str]
            - "bullets": list[str]
            - "table_data": {"headers": list, "rows": 2D list}
        file_name: Output filename (.docx).
    """
    try:
        path = _safe_path(file_name, ".docx")
        doc = Document()
        doc.add_heading(title, level=1)

        for section in sections:
            if "heading" in section:
                doc.add_heading(section["heading"], level=2)

            for p in section.get("paragraphs", []):
                doc.add_paragraph(p)

            for b in section.get("bullets", []):
                doc.add_paragraph(b, style="List Bullet")

            table_info = section.get("table_data")
            if table_info:
                headers = table_info.get("headers", [])
                rows = table_info.get("rows", [])
                if headers and rows:
                    table = doc.add_table(rows=1, cols=len(headers))
                    table.style = "Table Grid"
                    for i, h in enumerate(headers):
                        table.rows[0].cells[i].text = str(h)
                    for row_data in rows:
                        cells = table.add_row().cells
                        for i, v in enumerate(row_data):
                            cells[i].text = str(v)

            doc.add_paragraph()

        doc.save(path)
        return f"Word document saved as: {path.name}"
    except Exception as e:
        return f"Error creating Word document: {e}"


# ---------- Agent ----------
tools = [
    calculator, get_current_time, get_weather, web_search,
    read_excel_file, write_excel_with_formulas, create_pivot_table, word_document,
]

SYSTEM_PROMPT = """You are a helpful assistant with access to these tools:

- calculator: use it for ANY arithmetic. Pass only numbers and operators, e.g. "123 * 456".
- get_current_time: use it when asked about the current date or time.
- get_weather: use it for weather or temperature. Pass the city name in English (e.g. "Cairo").
- web_search: use it for news, recent events, or facts that may have changed. Pass a short English query.
- read_excel_file: use it to inspect an existing Excel file (columns, shape, preview).
- write_excel_with_formulas: use it to create a NEW Excel file with data and formulas.
  Formulas must start with "=" and use cell coordinates like {"D2": "=B2*C2"}.
- create_pivot_table: use it to build a pivot-style summary table (group by one column, optionally spread another column) from an existing Excel file.
- word_document: use it to create a Word (.docx) report.

Rules:
1. Call a tool only when it is needed. For general knowledge or casual chat, answer directly.
2. Never invent tool results. Use only what the tool returns.
3. After web_search, base your answer on the results and mention the source URL.
4. If a tool fails or returns nothing, say so honestly. Do not retry the same failing call more than once.
5. Use the exact file names and column names the user gives you. Never guess a file path or column name; if it is missing, ask the user.
6. After creating a file, reply with ONE short sentence that states the saved file name, e.g. "Saved: budget.xlsx". Do not repeat the file contents.
7. Always reply in the same language the user writes in (Arabic or English).
8. Keep answers short and clear."""

agent = create_agent(
    model=llm,
    tools=tools,
    system_prompt=SYSTEM_PROMPT,
    checkpointer=InMemorySaver(),
)