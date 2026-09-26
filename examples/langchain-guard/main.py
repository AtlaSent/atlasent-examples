"""
AtlaSent + LangChain Policy Guard

Wraps LangChain Tools so every invocation is authorized by AtlaSent
before the tool runs: evaluate, then verify the permit, then execute.
A denied or unverified call raises AtlaSentDeniedError and the tool
body never runs.

Uses only the published `atlasent` SDK (`atlasent.with_permit`). The
`atlasent-langchain` package is not on PyPI yet.

Run:
    ATLASENT_API_KEY=ask_... python main.py
"""

import os
from typing import Callable

import atlasent
from atlasent import AtlaSentDeniedError
from langchain.tools import Tool

AGENT = "user-123"


def web_search(query: str) -> str:
    """Simulated web search — replace with a real search integration."""
    return f"Results for: {query}"


def send_email(recipient: str) -> str:
    """Simulated email send — gated as a high-impact action."""
    return f"Email sent to {recipient}."


def guarded(name: str, func: Callable[[str], str], environment: str = "production") -> Callable[[str], str]:
    """Run `func` only under a verified AtlaSent permit.

    The action is the canonical "agent.tool.invoke" (Canon ACT-0029),
    which requires context.tool and context.environment.
    """

    def run(arg: str) -> str:
        return atlasent.with_permit(
            agent=AGENT,
            action="agent.tool.invoke",
            context={"tool": name, "environment": environment, "tool_input": arg},
            fn=lambda _permit: func(arg),
        )

    return run


atlasent.configure(
    api_key=os.environ["ATLASENT_API_KEY"],
    # The SDK default is the bare host; the AtlaSent API lives under /functions/v1.
    base_url=os.environ.get("ATLASENT_URL", "https://api.atlasent.io/functions/v1"),
)

guarded_search = Tool(
    name="web_search",
    func=guarded("web_search", web_search),
    description="Search the web for recent information.",
)

guarded_email = Tool(
    name="send_email",
    func=guarded("send_email", send_email),
    description="Send an email to a recipient. High-impact action.",
)


def main() -> None:
    print("=== AtlaSent + LangChain Policy Guard ===\n")

    # Low-risk: search is typically allowed.
    try:
        result = guarded_search.run("latest AI news")
        print(f"Search result: {result}")
    except AtlaSentDeniedError as e:
        print(f"Search denied by policy: {e}")

    print()

    # High-impact: email may require approval or be denied outright.
    try:
        result = guarded_email.run("ceo@example.com")
        print(f"Email result: {result}")
    except AtlaSentDeniedError as e:
        print(f"Email denied by policy: {e}")


if __name__ == "__main__":
    main()
