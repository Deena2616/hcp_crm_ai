"""
LangGraph agent definition.

Graph shape:

    START -> classify_intent -> (route)
        - tool_name == "log_interaction_tool" -> draft_log_interaction_node
                           (LLM extraction only, NO db write - returns a draft that the
                            frontend binds into the structured form for the rep to review) -> END
        - other tool_call   -> agent_node (LLM decides which of the remaining 4 tools to
                           call, tool executes and commits, LLM formats a natural reply) -> END
        - "chit_chat"       -> direct_reply_node (LLM answers conversationally,
                           no DB/tool side effects) -> END

Logging an interaction is intentionally NOT a one-shot chat action anymore: describing a
visit in chat only fills in the structured form (draft), and the actual database write only
happens when the rep reviews the form and clicks "Log Interaction". All other tools (edit,
fetch profile, schedule follow-up, flag adverse event) still execute and commit immediately,
since those aren't "prep a form" actions.
"""
import json
from typing import TypedDict, Optional, List, Annotated
import operator

from langgraph.graph import StateGraph, END
from sqlalchemy.orm import Session

from app.agent.llm import call_llm, call_llm_json
from app.agent.tools import ALL_TOOLS, set_db_session, extract_interaction_fields

TOOLS_BY_NAME = {t.name: t for t in ALL_TOOLS}

TOOL_DESCRIPTIONS = "\n".join(
    f"- {t.name}: {t.description}" for t in ALL_TOOLS
)

# Tools whose result should be bound into the structured form as a draft instead of
# being committed to the database immediately.
DRAFT_TOOLS = {"log_interaction_tool"}


class AgentState(TypedDict):
    message: str
    hcp_id: Optional[str]
    intent: Optional[str]              # "tool_call" | "chit_chat"
    tool_name: Optional[str]
    tool_args: Optional[dict]
    tool_result: Optional[str]
    reply: Optional[str]
    action: Optional[str]              # "draft_interaction" when a draft was produced
    draft: Optional[dict]              # extracted fields to bind into the form, if any


def classify_intent_node(state: AgentState) -> AgentState:
    """Decide whether the user's message requires invoking a sales tool, and if so which one."""
    system_prompt = (
        "You are the routing brain of a pharma CRM sales agent. Given the user's message, "
        "decide if it requires calling one of the following tools, or if it's just "
        "conversational (greeting, question about capabilities, small talk).\n\n"
        f"Available tools:\n{TOOL_DESCRIPTIONS}\n\n"
        "Return STRICT JSON with keys:\n"
        '  intent: "tool_call" or "chit_chat"\n'
        '  tool_name: the exact tool name to call if intent is tool_call, else null\n'
        "  tool_args: a JSON object of arguments for that tool (best guess from the message; "
        "use the exact argument names from the tool signature), else null"
    )
    result = call_llm_json(system_prompt, state["message"])

    intent = result.get("intent", "chit_chat")
    tool_name = result.get("tool_name")
    tool_args = result.get("tool_args") or {}

    if state.get("hcp_id") and "hcp_id" not in tool_args:
        tool_args["hcp_id"] = state["hcp_id"]

    return {
        **state,
        "intent": intent if intent in ["tool_call", "chit_chat"] else "chit_chat",
        "tool_name": tool_name,
        "tool_args": tool_args,
    }


def route_after_classify(state: AgentState) -> str:
    if state["intent"] != "tool_call" or state.get("tool_name") not in TOOLS_BY_NAME:
        return "direct_reply_node"
    if state["tool_name"] in DRAFT_TOOLS:
        return "draft_log_interaction_node"
    return "agent_node"


def draft_log_interaction_node(state: AgentState) -> AgentState:
    """
    Runs extraction only (no DB write) for a log_interaction request and returns the result
    as a draft to be bound into the structured form. The rep reviews/edits it there and the
    actual commit happens when they click "Log Interaction" on the form.
    """
    args = state.get("tool_args", {}) or {}
    hcp_name = args.get("hcp_name", "") or ""
    raw_text = args.get("raw_text") or state["message"]
    interaction_type = args.get("interaction_type", "meeting") or "meeting"

    try:
        fields = extract_interaction_fields(raw_text, hcp_name, interaction_type)
        reply = (
            f"I've filled in the form based on what you told me"
            + (f" for {fields['hcp_name']}" if fields.get("hcp_name") else "")
            + " — take a look, adjust anything if needed, and click Log Interaction to save it."
        )
        return {**state, "action": "draft_interaction", "draft": fields, "reply": reply}
    except Exception as e:
        return {
            **state,
            "action": None,
            "draft": None,
            "reply": f"I had trouble reading that back into the form ({str(e)}). Could you rephrase?",
        }


def agent_node(state: AgentState) -> AgentState:
    """Execute the chosen tool, then have the LLM phrase a friendly reply summarizing the result."""
    tool_name = state["tool_name"]
    tool_args = state.get("tool_args", {}) or {}
    tool = TOOLS_BY_NAME[tool_name]

    try:
        # filter args to only those the tool accepts, to avoid TypeErrors on stray keys
        valid_keys = tool.args.keys() if hasattr(tool, "args") else tool_args.keys()
        filtered_args = {k: v for k, v in tool_args.items() if k in valid_keys}
        raw_result = tool.invoke(filtered_args)
    except Exception as e:
        raw_result = json.dumps({"status": "error", "message": str(e)})

    reply = call_llm(
        system_prompt=(
            "You are a helpful pharma CRM assistant speaking to a field sales rep. "
            "Given the JSON result of a tool call, write ONE short, natural sentence or two "
            "confirming what happened. Be specific (names, dates, key facts) but concise. "
            "Do not mention JSON or that you are an AI tool."
        ),
        user_prompt=f"Tool called: {tool_name}\nResult: {raw_result}",
    )

    return {**state, "tool_result": raw_result, "reply": reply}


def direct_reply_node(state: AgentState) -> AgentState:
    """Handle conversational messages with no tool side-effects."""
    reply = call_llm(
        system_prompt=(
            "You are a friendly AI assistant embedded in a pharma CRM's 'Log Interaction' "
            "screen, helping field sales reps. If asked what you can do, mention you can: "
            "log HCP interactions (by filling in the form for you to review and save), "
            "edit past logs, look up an HCP's profile/history, schedule follow-ups, and flag "
            "adverse events. Keep replies short."
        ),
        user_prompt=state["message"],
    )
    return {**state, "reply": reply}


def build_graph():
    graph = StateGraph(AgentState)
    graph.add_node("classify_intent", classify_intent_node)
    graph.add_node("agent_node", agent_node)
    graph.add_node("draft_log_interaction_node", draft_log_interaction_node)
    graph.add_node("direct_reply_node", direct_reply_node)

    graph.set_entry_point("classify_intent")
    graph.add_conditional_edges(
        "classify_intent",
        route_after_classify,
        {
            "agent_node": "agent_node",
            "draft_log_interaction_node": "draft_log_interaction_node",
            "direct_reply_node": "direct_reply_node",
        },
    )
    graph.add_edge("agent_node", END)
    graph.add_edge("draft_log_interaction_node", END)
    graph.add_edge("direct_reply_node", END)

    return graph.compile()


_compiled_graph = None


def get_graph():
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = build_graph()
    return _compiled_graph


def run_agent(message: str, db: Session, hcp_id: Optional[str] = None) -> dict:
    """Entry point called by the FastAPI chat route."""
    set_db_session(db)
    graph = get_graph()
    final_state = graph.invoke({
        "message": message,
        "hcp_id": hcp_id,
        "intent": None,
        "tool_name": None,
        "tool_args": None,
        "tool_result": None,
        "reply": None,
        "action": None,
        "draft": None,
    })
    return final_state