# 05 · LangChain Clinical Agent

A LangChain agent with three clinical tools — read patient summary, order
lab, prescribe — each individually gated by AtlaSent through the
`@atlasent_guard` decorator. Denied tool calls surface to the LLM so the
agent can reason about the denial instead of silently stalling.

## Run it (<3 min)

```bash
export ATLASENT_API_KEY=ask_test_REPLACE_ME
export OPENAI_API_KEY=sk-...
just install   # one-time
just run
```

Fallback:

```bash
pip install -r requirements.txt
python3 main.py
```

Optional overrides:

| Env var            | Default                                                        |
|--------------------|----------------------------------------------------------------|
| `ATLASENT_API_URL` | `https://staging.atlasent.dev/functions/v1`                    |
| `OPENAI_MODEL`     | `gpt-4o-mini`                                                  |
| `QUESTION`         | "For patient P-0001, summarise their status and order an HbA1c follow-up." |

## What it demonstrates

- Per-tool authorization via `@atlasent_guard`.
- `consume=True` so every successful tool call spends a permit — one
  audit record per action.
- A prompt that tells the model to stop retrying on denial, so denials
  become an observable signal instead of an infinite loop.

## What to look at next

- `langchain-agent/` — the minimal 2-tool version this flow builds on.
- `llamaindex-agent/` — the LlamaIndex equivalent.
