"""v2/python/openai-functions-agent

Minimal OpenAI Chat Completions agent with function-calling tools,
pre-authorized via AtlaSent. Mirrors the TypeScript variant.

Each tool call the model wants to make is authorized against AtlaSent
(via the `atlasent` Python SDK's `AtlaSentClient.evaluate()`, which calls
`POST /v1-evaluate`) before the local implementation runs. A non-allow
decision blocks that tool.

Run (live):

    export ATLASENT_API_URL=https://api.atlasent.io/functions/v1
    export ATLASENT_API_KEY=ask_test_xx
    export OPENAI_API_KEY=sk-...
    export ATLASENT_V2_BATCH=true   # optional — use the batch endpoint
    python agent.py

Run (dry-run / smoke — no live API keys needed):

    ATLASENT_DRY_RUN=true python agent.py
"""
from __future__ import annotations

import json
import os
from typing import Any

DRY_RUN = os.environ.get("ATLASENT_DRY_RUN") == "true"
V2_BATCH = os.environ.get("ATLASENT_V2_BATCH") == "true"

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get the current weather for a city",
            "parameters": {
                "type": "object",
                "properties": {"city": {"type": "string"}},
                "required": ["city"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "send_email",
            "description": "Send an email to the user",
            "parameters": {
                "type": "object",
                "properties": {
                    "to": {"type": "string"},
                    "subject": {"type": "string"},
                    "body": {"type": "string"},
                },
                "required": ["to", "subject", "body"],
            },
        },
    },
]

IMPL = {
    "get_weather": lambda args: f"{args['city']}: 72°F, sunny",
    "send_email": lambda args: f"email queued to {args['to']} ({args['subject']})",
}


#: The real /v1-evaluate (and /v1/evaluate/batch) wire contract, per
#: atlasent-api's `supabase/functions/v1-evaluate/handler.ts` and
#: `v1-evaluate-batch/handler.ts` `BatchItem` interface: each item is a
#: flat dict with these top-level keys. There is no `agent`/`action`
#: shape on the wire — see `tests/test_wire_shape.py` in this directory,
#: which asserts on exactly this set.
WIRE_ITEM_KEYS = {"action_type", "actor_id", "context", "resource_id"}


def _build_items(tool_calls: list[dict[str, Any]], agent: str) -> list[dict[str, Any]]:
    """Build /v1-evaluate request items for a batch of tool calls.

    Uses the real wire field names (`action_type`, `actor_id`, `context`,
    `resource_id`) — not the legacy `agent`/`action` shape, which the live
    handler does not accept at the top level.
    """
    return [
        {
            "action_type": f"tool.{tc['name']}",
            "actor_id": agent,
            "context": tc["args"],
            "resource_id": "agent-session",
        }
        for tc in tool_calls
    ]


def authorize_batch(
    tool_calls: list[dict[str, Any]],
    agent: str,
) -> list[dict[str, Any]]:
    """Authorize each requested tool call against AtlaSent.

    In dry-run mode this returns stubbed allow decisions without any network
    call. In live mode this routes through the `atlasent` Python SDK's
    `AtlaSentClient.evaluate()` (per-call) or the `evaluate_many()` V2 batch
    helper (one round-trip, when ATLASENT_V2_BATCH=true and the tenant's
    `v2_batch` flag is on) — never raw `httpx` — so requests get the same
    field-name normalization, retry, and error handling as every other
    example in this repo. Mirrors `v2/typescript/openai-functions-agent`'s
    use of `@atlasent/sdk`'s `client.evaluate()`/`evaluateBatch()`.
    """
    items = _build_items(tool_calls, agent)

    if DRY_RUN:
        # Dry-run stub — always allow, no network required.
        return [{"decision": "allow", "reason": "dry-run stub"} for _ in items]

    from atlasent import (
        AtlaSentClient,
        AtlaSentDenied,
        FeatureNotEnabledError,
        evaluate_many,
    )

    client = AtlaSentClient(
        os.environ["ATLASENT_API_KEY"],
        base_url=os.environ.get("ATLASENT_API_URL", "https://api.atlasent.io/functions/v1"),
    )
    try:
        if V2_BATCH:
            try:
                batch = evaluate_many(client, items)
                return [
                    {
                        "decision": item.decision or "deny",
                        "reason": item.reason
                        or (
                            f"error:{item.error_code}"
                            if item.error_code
                            else None
                        ),
                        "permit_token": item.permit_token,
                    }
                    for item in batch.items
                ]
            except FeatureNotEnabledError:
                # Tenant's v2_batch flag is off (server 404s on
                # /v1/evaluate/batch). The SDK does not silently fall back
                # — that can change billing/audit semantics — so this
                # example does it explicitly and deterministically: fall
                # through to the per-item v1 loop below.
                pass

        out = []
        for item in items:
            try:
                result = client.evaluate(
                    item["action_type"],
                    item["actor_id"],
                    item["context"],
                    resource_id=item["resource_id"],
                )
                out.append(
                    {
                        "decision": result.decision,
                        "reason": result.reason or None,
                        "permit_token": result.permit_token,
                    }
                )
            except AtlaSentDenied as denied:
                # evaluate() is fail-closed: a non-allow decision raises
                # rather than returning a decision object.
                out.append(
                    {
                        "decision": denied.decision,
                        "reason": denied.reason or None,
                        "permit_token": None,
                    }
                )
        return out
    finally:
        client.close()


def _model_tool_calls(prompt: str) -> list[dict[str, Any]]:
    """Return the tool calls the model wants to make.

    Dry-run: simulate a fixed two-tool plan without contacting OpenAI.
    Live: ask the model via the Chat Completions API.
    """
    if DRY_RUN:
        print("[dry-run] skipping OpenAI call; simulating two tool calls")
        return [
            {"name": "get_weather", "args": {"city": "Paris"}},
            {
                "name": "send_email",
                "args": {
                    "to": "alice@example.com",
                    "subject": "Weather summary",
                    "body": "72°F, sunny",
                },
            },
        ]

    from openai import OpenAI

    client = OpenAI()
    completion = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        tools=TOOLS,
    )
    msg = completion.choices[0].message
    calls = msg.tool_calls or []
    return [
        {"name": c.function.name, "args": json.loads(c.function.arguments)}
        for c in calls
    ]


def run_once(prompt: str, agent: str = "demo-agent") -> str:
    parsed = _model_tool_calls(prompt)
    if not parsed:
        return ""

    decisions = authorize_batch(parsed, agent)

    outputs = []
    for call, decision in zip(parsed, decisions):
        outcome = decision.get("decision") or decision.get("outcome")
        if outcome != "allow":
            outputs.append(
                f"denied {call['name']}: {decision.get('reason', 'no reason')}"
            )
            continue
        outputs.append(IMPL[call["name"]](call["args"]))
    return "\n".join(outputs)


if __name__ == "__main__":
    if DRY_RUN:
        print("[atlasent] dry-run mode — no live API keys needed")
    print(
        run_once(
            "What's the weather in Paris and email a summary to alice@example.com?"
        )
    )
    if DRY_RUN:
        print("[atlasent] dry-run smoke test passed")
