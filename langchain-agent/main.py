"""LangChain agent with AtlaSent tool authorization."""
import os
from atlasent import AtlaSentClient, atlasent_guard
from langchain.agents import AgentExecutor, create_openai_functions_agent
from langchain.tools import Tool
from langchain_openai import ChatOpenAI
from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder

atlasent = AtlaSentClient(api_key=os.environ["ATLASENT_API_KEY"], base_url=os.environ.get("ATLASENT_API_URL", "https://api.atlasent.io/functions/v1"))


# atlasent_guard signature: (client, action_type, *, actor_id="", context=None, ...).
# The wrapped function receives the GateResult as a `gate_result` kwarg even
# when it's ignored — include it in the signature so LangChain's invocation
# through Tool.func doesn't blow up with an unexpected-kwarg TypeError.
@atlasent_guard(atlasent, "documents.read", actor_id="langchain-agent")
def read_document(doc_id: str, gate_result=None) -> str:
    """Read a document by ID (authorization-gated)."""
    return f"Document {doc_id}: contents of the requested document."


@atlasent_guard(atlasent, "data:write", actor_id="langchain-agent")
def write_record(payload: str, gate_result=None) -> str:
    """Write a record to the database (authorization-gated)."""
    return f"Record written: {payload}"


tools = [
    Tool(name="read_document", func=read_document, description="Read a document by its ID"),
    Tool(name="write_record", func=write_record, description="Write a record to the database"),
]

prompt = ChatPromptTemplate.from_messages([
    ("system", "You are a helpful assistant with access to documents and records."),
    ("human", "{input}"),
    MessagesPlaceholder("agent_scratchpad"),
])

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
agent = create_openai_functions_agent(llm, tools, prompt)
executor = AgentExecutor(agent=agent, tools=tools, verbose=True)

if __name__ == "__main__":
    result = executor.invoke({"input": "Read document doc-123 and tell me what it says."})
    print("\nFinal answer:", result["output"])
