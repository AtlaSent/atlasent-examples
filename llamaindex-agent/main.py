"""LlamaIndex query engine with AtlaSent authorization gating."""
import asyncio
import os
from atlasent import AsyncAtlaSentClient, async_atlasent_guard
from llama_index.core import VectorStoreIndex, Document
from llama_index.core.query_engine import BaseQueryEngine

atlasent = AsyncAtlaSentClient(api_key=os.environ["ATLASENT_API_KEY"], base_url=os.environ.get("ATLASENT_API_URL", "https://api.atlasent.io/functions/v1"))


# async_atlasent_guard signature: (client, action_type, *, actor_id="",
# context=None, actor_id_kwarg="", context_kwarg=""). No `agent=` or
# `action=` kwargs.
@async_atlasent_guard(
    atlasent,
    "index:query",
    actor_id="llamaindex-agent",
    context={"classification": "internal"},
)
async def gated_query(engine: BaseQueryEngine, question: str, gate_result=None) -> str:
    """Run a query against the index (authorization-gated)."""
    response = engine.query(question)
    return str(response)


async def main():
    docs = [
        Document(text="AtlaSent provides execution-time authorization for AI agents."),
        Document(text="Policies are defined as JSON bundles with allow/deny rules."),
        Document(text="The SDK supports Python and TypeScript."),
    ]
    index = VectorStoreIndex.from_documents(docs)
    engine = index.as_query_engine()

    question = "What languages does AtlaSent support?"
    print(f"Query: {question}")

    try:
        answer = await gated_query(engine, question)
        print(f"Answer: {answer}")
    except PermissionError as e:
        print(f"Query denied by AtlaSent: {e}")


asyncio.run(main())
