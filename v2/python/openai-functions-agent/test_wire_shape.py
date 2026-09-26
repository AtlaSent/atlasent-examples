"""Standalone smoke test: does agent.py build the real /v1-evaluate wire shape?

No network calls, no live API key, no pytest required — run directly:

    python test_wire_shape.py

(it also collects fine under pytest, since the assertions live in a
`test_`-prefixed function — use whichever runner is convenient).

Background: this example
used to build a raw ``{agent, action, resource, context}`` payload and POST
it directly via ``httpx``, bypassing the ``atlasent`` SDK's normalization.
The real ``/v1-evaluate`` handler (``atlasent-api``
``supabase/functions/v1-evaluate/handler.ts``) requires ``action_type`` /
``actor_id`` at the top level and has no ``agent`` / ``action`` alias on the
wire, so that payload would 400 against the live API. This test pins the
actual wire contract so a reintroduced ``agent``/``action`` shape fails
loudly here instead of silently drifting back to broken.
"""
from __future__ import annotations

from agent import WIRE_ITEM_KEYS, _build_items

# The real /v1-evaluate + /v1/evaluate/batch wire fields required at the
# top level of every item (atlasent-api supabase/functions/v1-evaluate/
# handler.ts and v1-evaluate-batch/handler.ts's BatchItem interface).
REQUIRED_KEYS = {"action_type", "actor_id", "context"}

# The legacy shape this example used to send. Must never reappear.
LEGACY_KEYS = {"agent", "action", "resource"}


def test_build_items_matches_v1_evaluate_wire_contract() -> None:
    tool_calls = [
        {"name": "get_weather", "args": {"city": "Paris"}},
        {
            "name": "send_email",
            "args": {"to": "alice@example.com", "subject": "s", "body": "b"},
        },
    ]
    items = _build_items(tool_calls, "demo-agent")

    assert len(items) == len(tool_calls), "expected one wire item per tool call"

    for item, call in zip(items, tool_calls):
        keys = set(item.keys())

        # Every key present is a real wire field, and nothing extra snuck in.
        assert keys <= WIRE_ITEM_KEYS, (
            f"unexpected key(s) in wire item: {keys - WIRE_ITEM_KEYS}"
        )
        # The required top-level fields are all present.
        assert REQUIRED_KEYS <= keys, (
            f"missing required wire field(s): {REQUIRED_KEYS - keys}"
        )
        # The legacy agent/action/resource shape must never reappear.
        assert not (LEGACY_KEYS & keys), (
            f"legacy field(s) leaked back into the wire payload: {LEGACY_KEYS & keys}"
        )

        assert item["action_type"] == f"tool.{call['name']}"
        assert item["actor_id"] == "demo-agent"
        assert item["context"] == call["args"]
        assert isinstance(item["context"], dict)


if __name__ == "__main__":
    test_build_items_matches_v1_evaluate_wire_contract()
    print(
        "[test_wire_shape] PASS — agent.py's authorize_batch() builds the "
        "real /v1-evaluate wire shape (action_type/actor_id/context), not "
        "the legacy agent/action/resource shape."
    )
