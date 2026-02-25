"""
Human Preference Data Collector
A simple Streamlit app for collecting RLHF-style preference labels.
"""

import json
import os
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

from prompts import CURATED_PROMPTS, MOCK_RESPONSES, PROMPT_LABELS

# ── Config ──────────────────────────────────────────────────────────────────
load_dotenv()
DATA_DIR = Path(__file__).parent / "data"
PREFERENCES_FILE = DATA_DIR / "preferences.jsonl"
DATA_DIR.mkdir(exist_ok=True)

MODELS = [
    "claude-haiku-3-5-20241022",
    "claude-sonnet-4-5-20241022",
]

# ── Page setup ───────────────────────────────────────────────────────────────
st.set_page_config(page_title="Human Preference Collector", layout="wide")

# ── Session state defaults ────────────────────────────────────────────────────
_defaults = {
    "response_a": None,
    "response_b": None,
    "gen_metadata": None,
    "current_prompt": "",
    "preference_saved": False,
    "last_winner": None,
    "last_sample_idx": -1,  # track which sample was loaded
}
for k, v in _defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ── API availability check ────────────────────────────────────────────────────
API_KEY = os.getenv("ANTHROPIC_API_KEY", "").strip()
DEMO_MODE = not API_KEY


# ── Helper: generate two responses ───────────────────────────────────────────
def _call_claude(prompt: str, model: str, temperature: float) -> tuple[str, float]:
    import anthropic
    client = anthropic.Anthropic(api_key=API_KEY)
    t0 = time.perf_counter()
    resp = client.messages.create(
        model=model,
        max_tokens=512,
        temperature=temperature,
        messages=[{"role": "user", "content": prompt}],
    )
    elapsed = round(time.perf_counter() - t0, 2)
    return resp.content[0].text, elapsed


def generate_responses(prompt: str, model: str, temp_a: float, temp_b: float) -> dict:
    """Return dict with response_a, response_b, times, and metadata."""
    if DEMO_MODE:
        # Find matching mock responses (cycle by prompt index)
        idx = next(
            (i for i, p in enumerate(CURATED_PROMPTS) if p["prompt"] == prompt),
            0,
        )
        mock_a, mock_b = MOCK_RESPONSES[idx % len(MOCK_RESPONSES)]
        time.sleep(0.4)  # simulate latency
        return {
            "response_a": mock_a,
            "response_b": mock_b,
            "response_time_a": 0.42,
            "response_time_b": 0.38,
            "model": "demo-mode (no API key)",
            "temperature_a": temp_a,
            "temperature_b": temp_b,
        }

    # Real API calls — run concurrently
    with ThreadPoolExecutor(max_workers=2) as ex:
        fut_a = ex.submit(_call_claude, prompt, model, temp_a)
        fut_b = ex.submit(_call_claude, prompt, model, temp_b)
        text_a, time_a = fut_a.result()
        text_b, time_b = fut_b.result()

    return {
        "response_a": text_a,
        "response_b": text_b,
        "response_time_a": time_a,
        "response_time_b": time_b,
        "model": model,
        "temperature_a": temp_a,
        "temperature_b": temp_b,
    }


# ── Helper: persistence ───────────────────────────────────────────────────────
def save_record(record: dict) -> None:
    with open(PREFERENCES_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")


def load_records() -> list[dict]:
    if not PREFERENCES_FILE.exists():
        return []
    lines = PREFERENCES_FILE.read_text(encoding="utf-8").strip().splitlines()
    return [json.loads(ln) for ln in lines if ln.strip()]


def to_raw_jsonl(records: list[dict]) -> str:
    return "\n".join(json.dumps(r) for r in records)


def to_dpo_jsonl(records: list[dict]) -> str:
    lines = []
    for r in records:
        winner = r.get("winner")
        if winner == "tie":
            continue
        chosen = r["response_a"] if winner == "A" else r["response_b"]
        rejected = r["response_b"] if winner == "A" else r["response_a"]
        lines.append(
            json.dumps({"prompt": r["prompt"], "chosen": chosen, "rejected": rejected})
        )
    return "\n".join(lines)


# ════════════════════════════════════════════════════════════════════════════
#  SIDEBAR
# ════════════════════════════════════════════════════════════════════════════
with st.sidebar:
    st.header("⚙️ Generation Settings")

    if DEMO_MODE:
        st.warning("⚠️ Demo mode — no API key found.\nSet ANTHROPIC_API_KEY in .env to use Claude.")
    else:
        st.success("✅ Anthropic API connected")

    selected_model = st.selectbox("Model", MODELS, index=0)
    temp_a = st.slider("Temperature A", 0.0, 1.0, 0.7, 0.05)
    temp_b = st.slider("Temperature B", 0.0, 1.0, 0.9, 0.05)

    st.divider()
    st.caption("Settings apply to the **next** generation.")


# ════════════════════════════════════════════════════════════════════════════
#  MAIN AREA
# ════════════════════════════════════════════════════════════════════════════
st.title("Human Preference Collector")
st.caption(
    "Generate two responses to a prompt, pick the one you prefer, and build an RLHF dataset."
)

st.divider()

# ── Prompt input ──────────────────────────────────────────────────────────────
st.subheader("Prompt")

sample_choice = st.selectbox(
    "Load a sample prompt (over-confidence traps)",
    options=["-- type your own below --"] + PROMPT_LABELS,
    index=0,
)

# When the dropdown changes, push the selected prompt into session state
if sample_choice != "-- type your own below --":
    chosen_idx = PROMPT_LABELS.index(sample_choice)
    if chosen_idx != st.session_state.last_sample_idx:
        st.session_state.current_prompt = CURATED_PROMPTS[chosen_idx]["prompt"]
        st.session_state.last_sample_idx = chosen_idx
        # Clear previous generation so a new one is forced
        st.session_state.response_a = None
        st.session_state.response_b = None
        st.session_state.preference_saved = False
        st.rerun()

prompt_text = st.text_area(
    "Your prompt",
    value=st.session_state.current_prompt,
    height=100,
    placeholder="Enter a question or scenario…",
)
# Keep session state synced if user edits manually
if prompt_text != st.session_state.current_prompt:
    st.session_state.current_prompt = prompt_text

# ── Generate button ───────────────────────────────────────────────────────────
generate_clicked = st.button(
    "🚀 Generate Responses",
    disabled=not prompt_text.strip(),
    type="primary",
)

if generate_clicked and prompt_text.strip():
    # Reset for a fresh generation
    st.session_state.response_a = None
    st.session_state.response_b = None
    st.session_state.preference_saved = False
    st.session_state.last_winner = None

    with st.spinner("Generating two responses…"):
        try:
            result = generate_responses(
                prompt=prompt_text,
                model=selected_model,
                temp_a=temp_a,
                temp_b=temp_b,
            )
            st.session_state.response_a = result["response_a"]
            st.session_state.response_b = result["response_b"]
            st.session_state.gen_metadata = result
        except Exception as e:
            st.error(f"Generation failed: {e}")

    st.rerun()

# ── Display responses ─────────────────────────────────────────────────────────
if st.session_state.response_a and st.session_state.response_b:
    st.divider()

    col_a, col_b = st.columns(2)
    with col_a:
        st.subheader("Response A")
        st.write(st.session_state.response_a)
        meta = st.session_state.gen_metadata or {}
        st.caption(
            f"temp={meta.get('temperature_a', '?')} | "
            f"time={meta.get('response_time_a', '?')}s"
        )

    with col_b:
        st.subheader("Response B")
        st.write(st.session_state.response_b)
        st.caption(
            f"temp={meta.get('temperature_b', '?')} | "
            f"time={meta.get('response_time_b', '?')}s"
        )

    # ── Generation metadata expander ─────────────────────────────────────────
    meta = st.session_state.gen_metadata or {}
    example_id = str(int(time.time() * 1000))
    with st.expander("Show generation metadata"):
        st.json(
            {
                "example_id": example_id,
                "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "gen": {
                    "model": meta.get("model"),
                    "A": {
                        "temperature": meta.get("temperature_a"),
                        "response_time": meta.get("response_time_a"),
                    },
                    "B": {
                        "temperature": meta.get("temperature_b"),
                        "response_time": meta.get("response_time_b"),
                    },
                },
            }
        )

    st.divider()

    # ── Preference section ────────────────────────────────────────────────────
    st.subheader("Your preference")

    if not st.session_state.preference_saved:
        st.caption("Select one:")
        preference = st.radio(
            "preference",
            options=["A", "B", "tie"],
            horizontal=True,
            label_visibility="collapsed",
        )

        reason = st.text_input(
            "Optional: why?",
            placeholder="e.g., more cautious, fewer hallucinations, clearer reasoning",
        )

        col_btn, col_hint = st.columns([1, 2])
        with col_btn:
            save_clicked = st.button("Save label", use_container_width=True)
        with col_hint:
            st.caption(
                "Saved labels append to a local JSONL file. "
                "You can combine files across students later if you want."
            )

        if save_clicked:
            record = {
                "example_id": str(uuid.uuid4()),
                "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "prompt": st.session_state.current_prompt,
                "response_a": st.session_state.response_a,
                "response_b": st.session_state.response_b,
                "winner": preference,
                "reason": reason,
                "gen": {
                    "model": meta.get("model"),
                    "A": {
                        "temperature": meta.get("temperature_a"),
                        "response_time": meta.get("response_time_a"),
                    },
                    "B": {
                        "temperature": meta.get("temperature_b"),
                        "response_time": meta.get("response_time_b"),
                    },
                },
            }
            save_record(record)
            st.session_state.preference_saved = True
            st.session_state.last_winner = preference
            st.rerun()

    else:
        winner_label = {"A": "Response A", "B": "Response B", "tie": "Tie"}
        st.success(
            f"Saved to {PREFERENCES_FILE.relative_to(Path(__file__).parent)}"
        )
        st.info(
            f"Preference recorded: **{winner_label.get(st.session_state.last_winner, '?')}**  \n"
            "Click **Generate Responses** above to label another prompt."
        )

# ════════════════════════════════════════════════════════════════════════════
#  DATASET SECTION
# ════════════════════════════════════════════════════════════════════════════
st.divider()
st.subheader("Dataset")

all_records = load_records()
dpo_records = [r for r in all_records if r.get("winner") != "tie"]

st.write(f"**Raw labels:** {len(all_records)}")
st.write(f"**DPO pairs (non-ties):** {len(dpo_records)}")

dl_col1, dl_col2 = st.columns(2)
with dl_col1:
    st.download_button(
        label="Download raw JSONL",
        data=(to_raw_jsonl(all_records) or "").encode("utf-8"),
        file_name="preferences_raw.jsonl",
        mime="application/x-jsonlines",
        disabled=len(all_records) == 0,
        use_container_width=True,
    )
with dl_col2:
    st.download_button(
        label="Download DPO JSONL",
        data=(to_dpo_jsonl(all_records) or "").encode("utf-8"),
        file_name="preferences_dpo.jsonl",
        mime="application/x-jsonlines",
        disabled=len(dpo_records) == 0,
        use_container_width=True,
    )

# ── Recent entries ────────────────────────────────────────────────────────────
st.subheader("Recent entries")
if all_records:
    # Show last 5 entries most-recent first
    recent = list(reversed(all_records[-5:]))
    st.json(recent)
else:
    st.info("No labels saved yet. Generate responses and save your first preference above.")
