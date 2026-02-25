# Human Preference Collector

A simple Streamlit app for collecting RLHF-style preference labels between two LLM responses.

## Quick Start

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Set up your API key (optional)

```bash
cp .env.example .env
# Open .env and fill in your Anthropic API key
```

> **No API key?** The app runs in **demo mode** automatically — mock responses are served from a curated set so you can still label preferences and export data.

### 3. Run the app

```bash
streamlit run app.py
```

Open [http://localhost:8501](http://localhost:8501) in your browser.

---

## How it works

1. **Select a prompt** from the 20 curated "over-confidence trap" prompts, or type your own.
2. Click **Generate Responses** — two responses are generated from the same model with slightly different temperatures (A: 0.7, B: 0.9) to introduce diversity.
3. Read both responses, then select your preference: **A**, **B**, or **tie**.
4. Optionally explain why, then click **Save label**.
5. Repeat. Export your dataset anytime using the download buttons.

---

## Data format

### Raw JSONL (`data/preferences_raw.jsonl`)

Each line is one labeled example:

```json
{
  "example_id": "uuid",
  "timestamp": "2026-02-25T00:01:35Z",
  "prompt": "...",
  "response_a": "...",
  "response_b": "...",
  "winner": "A",
  "reason": "more cautious, fewer hallucinations",
  "gen": {
    "model": "claude-haiku-3-5-20241022",
    "A": {"temperature": 0.7, "response_time": 1.2},
    "B": {"temperature": 0.9, "response_time": 1.5}
  }
}
```

### DPO JSONL (exported on demand)

Non-tie records converted to chosen/rejected pairs for downstream training:

```json
{"prompt": "...", "chosen": "...", "rejected": "..."}
```

---

## Prompt dataset

20 prompts in the **over-confidence traps** category — questions that sound like they have a definitive answer but actually require hedging and acknowledgment of tradeoffs.

| # | Category | Theme |
|---|---|---|
| 1–4 | Medical self-diagnosis | Headache, heart rate, fatigue, supplements |
| 5–7 | Financial / investment | Index funds, gold, recession timing |
| 8–9 | Legal interpretation | Landlord entry, trademark |
| 10–11 | Psychological self-assessment | ADHD, introversion |
| 12–14 | Relationship / life advice | Arguments, settling, career change |
| 15–17 | Scientific misconceptions | Breakfast, red wine, keto |
| 18–19 | Future predictions | AI replacing jobs, quantum computing |
| 20 | Nutrition / wellness | 8 glasses of water |

---

## File structure

```
Lab6/
├── app.py              # Streamlit app (single file)
├── prompts.py          # 20 curated prompts + mock responses
├── requirements.txt
├── .env.example
├── data/
│   └── preferences.jsonl   # Auto-created; one record per line
└── README.md
```
