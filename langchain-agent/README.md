# LangChain Agent with AtlaSent

A LangChain agent that gates each tool call through AtlaSent authorization.

## Run

```bash
pip install -r requirements.txt
export ATLASENT_API_KEY=your_key_here
export OPENAI_API_KEY=your_openai_key
python main.py
```

## What it demonstrates

- Wrapping a LangChain `Tool` with `atlasent_guard` so every invocation is authorized
- Fail-closed behavior: if AtlaSent denies, the tool raises before executing
- Logging authorization decisions alongside LangChain traces
