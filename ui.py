import json
import os
import uuid

import requests
import streamlit as st

API_URL = os.getenv("API_URL", "http://localhost:8000")

st.set_page_config(page_title="AI Agent", page_icon="🤖", layout="wide")


# ---------- State ----------
if "thread_id" not in st.session_state:
    st.session_state.thread_id = str(uuid.uuid4())
if "messages" not in st.session_state:
    st.session_state.messages = []


def new_chat():
    st.session_state.thread_id = str(uuid.uuid4())
    st.session_state.messages = []


def stream_chat(prompt: str, state: dict, tools_box):
    """Yield text tokens; collect tools/sources into `state`."""
    try:
        with requests.post(
            f"{API_URL}/chat/events",
            json={"message": prompt, "thread_id": st.session_state.thread_id},
            stream=True,
            timeout=300,
        ) as r:
            r.raise_for_status()
            r.encoding = "utf-8"
            for line in r.iter_lines(decode_unicode=True):
                if not line:
                    continue
                event = json.loads(line)
                if event["type"] == "token":
                    yield event["text"]
                elif event["type"] == "tool":
                    state["tools"].append(event["name"])
                    tools_box.caption("🛠️ " + ", ".join(state["tools"]))
                elif event["type"] == "done":
                    state["sources"] = event["sources"]
                elif event["type"] == "error":
                    yield f"\n\n⚠️ Error: {event['message']}"
    except requests.RequestException as e:
        yield f"⚠️ Could not reach the API: {e}"


# ---------- Sidebar ----------
with st.sidebar:
    st.title("🤖 AI Agent")
    st.button("➕ New chat", on_click=new_chat, use_container_width=True)

    st.divider()
    st.subheader("📁 Files")

    uploaded = st.file_uploader(
        "Upload an Excel / CSV / Word file",
        type=["xlsx", "xls", "csv", "docx"],
    )
    if uploaded and st.session_state.get("last_uploaded") != uploaded.file_id:
        try:
            r = requests.post(
                f"{API_URL}/files",
                files={"file": (uploaded.name, uploaded.getvalue())},
                timeout=60,
            )
            if r.ok:
                st.session_state.last_uploaded = uploaded.file_id
                st.success(f"Uploaded as: {r.json()['name']}")
            else:
                st.error(r.json().get("detail", r.text))
        except requests.RequestException as e:
            st.error(f"Upload failed: {e}")

    try:
        files = requests.get(f"{API_URL}/files", timeout=10).json()["files"]
    except Exception:
        files = []
        st.warning("Cannot reach the API")

    if not files:
        st.caption("No files yet.")

    for f in files:
        try:
            content = requests.get(f"{API_URL}/files/{f['name']}", timeout=30).content
        except requests.RequestException:
            continue
        st.download_button(
            f"⬇️ {f['name']} ({f['size_kb']} KB)",
            data=content,
            file_name=f["name"],
            key=f"dl-{f['name']}",
            use_container_width=True,
        )


# ---------- Chat ----------
st.title("AI Agent")
st.caption(
    "Ask about the weather, math, or the latest news, or let it read and write "
    "Excel and Word files."
)

for m in st.session_state.messages:
    with st.chat_message(m["role"]):
        st.markdown(m["content"])
        if m.get("tools"):
            st.caption("🛠️ " + ", ".join(m["tools"]))
        if m.get("sources"):
            with st.expander("Sources"):
                for url in m["sources"]:
                    st.markdown(f"- {url}")

if prompt := st.chat_input("Type your message here..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    state = {"tools": [], "sources": []}
    with st.chat_message("assistant"):
        tools_box = st.empty()
        answer = st.write_stream(stream_chat(prompt, state, tools_box))
        if state["sources"]:
            with st.expander("Sources"):
                for url in state["sources"]:
                    st.markdown(f"- {url}")

    st.session_state.messages.append({
        "role": "assistant",
        "content": answer,
        "tools": state["tools"],
        "sources": state["sources"],
    })
    st.rerun()