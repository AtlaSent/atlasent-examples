#!/usr/bin/env python3
"""05 - LangChain Clinical Agent: a LangChain agent whose clinical tools
are individually authorization-gated by AtlaSent via @atlasent_guard.

Each tool call hits AtlaSent first. Denied calls raise AtlaSentDenied,
so the LLM sees the denial and picks a different action. Allowed calls
return the GateResult via the gate_result kwarg; the audit chain is
written server-side during evaluate() and needs no client-side consume.
"""
import os
import sys

from atlasent import AtlaSentClient, atlasent_guard
from langchain.agents import AgentExecutor, create_openai_functions_agent
from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain.tools import Tool
from langchain_openai import ChatOpenAI

API_KEY = os.environ.get("ATLASENT_API_KEY")
if not API_KEY:
    sys.exit("ATLASENT_API_KEY is required. export ATLASENT_API_KEY=... and re-run.")
if not os.environ.get("OPENAI_API_KEY"):
    sys.exit("OPENAI_API_KEY is required to drive the LangChain agent.")

atlasent = AtlaSentClient(
    api_key=API_KEY,
    base_url=os.environ.get("ATLASENT_API_URL", "https://api.atlasent.io/functions/v1"),
)


@atlasent_guard(atlasent, "phi:read", actor_id="clinical-agent")
def read_patient_summary(patient_id: str, gate_result=None) -> str:
    """Return a (simulated) clinical summary for a patient. Gated: phi:read."""
    return (
        f"Patient {patient_id}: 58yo, T2DM, last HbA1c 7.2%, "
        f"on metformin 1000mg BID, no recent adverse events."
    )


@atlasent_guard(atlasent, "lab:order", actor_id="clinical-agent")
def order_lab(patient_id: str, assay: str, gate_result=None) -> str:
    """Place a lab order for a patient. Gated: lab:order."""
    return f"Lab order placed: {assay} for {patient_id}. Result ETA 24h."


@atlasent_guard(atlasent, "rx:prescribe", actor_id="clinical-agent")
def prescribe(patient_id: str, drug: str, dose: str, gate_result=None) -> str:
    """Write a prescription. Gated: rx:prescribe - often denied without MD sign-off."""
    return f"Prescribed {drug} {dose} for {patient_id}."


tools = [
    Tool(
        name="read_patient_summary",
        func=read_patient_summary,
        description="Read a short clinical summary for a patient by MRN-style id.",
    ),
    Tool(
        name="order_lab",
        func=lambda s: order_lab(*(p.strip() for p in s.split(",", 1))),
        description="Order a lab. Input: 'patient_id, assay' (e.g. 'P-0001, hba1c').",
    ),
    Tool(
        name="prescribe",
        func=lambda s: prescribe(*(p.strip() for p in s.split(",", 2))),
        description="Prescribe a drug. Input: 'patient_id, drug, dose'.",
    ),
]


def main() -> int:
    print("=== 05 - LangChain Clinical Agent ===\n")
    question = os.environ.get(
        "QUESTION",
        "For patient P-0001, summarise their status and order an HbA1c follow-up.",
    )

    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "You are a careful clinical assistant. You MUST use the provided tools. "
                "If a tool call is denied by policy, explain why and stop - do not retry "
                "with a different phrasing.",
            ),
            ("human", "{input}"),
            MessagesPlaceholder("agent_scratchpad"),
        ]
    )
    llm = ChatOpenAI(model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"), temperature=0)
    agent = create_openai_functions_agent(llm, tools, prompt)
    executor = AgentExecutor(agent=agent, tools=tools, verbose=True, max_iterations=4)

    result = executor.invoke({"input": question})
    print("\n--- Final answer ---")
    print(result["output"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
