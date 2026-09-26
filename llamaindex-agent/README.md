# LlamaIndex Agent with AtlaSent

A LlamaIndex query pipeline that gates index queries through AtlaSent.

## Run

```bash
pip install -r requirements.txt
export ATLASENT_API_KEY=your_key_here
export OPENAI_API_KEY=your_openai_key
python main.py
```

## What it demonstrates

- Wrapping a `QueryEngine` query method with `async_atlasent_guard`
- Per-query authorization with contextual metadata (user role, document classification)
- Graceful denial handling in an agentic retrieval workflow
