# openai-functions-agent (Python)

Python sibling of `v2/typescript/openai-functions-agent`. Uses the
`openai` Python SDK for the model call and the `atlasent` Python SDK
(`AtlaSentClient.evaluate()` / the `evaluate_many()` V2 batch helper) to
authorize each tool call before it runs — never raw `httpx` against
`/v1-evaluate` directly, so requests get the SDK's field-name
normalization, retry, and error handling for free.

## Run

```bash
pip install -r requirements.txt
export ATLASENT_API_URL=https://...
export ATLASENT_API_KEY=ask_test_xx
export OPENAI_API_KEY=sk-...
export ATLASENT_V2_BATCH=true   # optional — use /v1/evaluate/batch in one round-trip
python agent.py
```

Run (dry-run / smoke — no live API keys needed):

```bash
ATLASENT_DRY_RUN=true python agent.py
```

## Wire shape

Each tool call is authorized as `{action_type, actor_id, context, resource_id}`
— the real `/v1-evaluate` contract (`atlasent-api`
`supabase/functions/v1-evaluate/handler.ts`). There is no `agent`/`action`
top-level shape on the wire; see `tests/test_wire_shape.py` for a standalone
assertion of this.
