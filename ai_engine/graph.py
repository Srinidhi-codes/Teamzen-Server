from typing import Annotated, Sequence, TypedDict, Union, List, Optional
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, ToolMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from langgraph.graph.message import add_messages
from django.conf import settings
from .tools import get_leave_balances, apply_for_leave, get_attendance_today, search_policies, get_leave_types, mark_attendance
from .models import PolicyDocument
from pgvector.django import L2Distance
import json

# Define the state
class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]
    user_id: int
    organization_id: int
    latitude: Optional[float]
    longitude: Optional[float]

# Define the tools
tools = [get_leave_balances, apply_for_leave, get_attendance_today, search_policies, get_leave_types, mark_attendance]
tool_node = ToolNode(tools)

# Define the model
model = ChatOpenAI(
    model="gpt-4o",
    temperature=0,
    openai_api_key=settings.OPENAI_API_KEY
).bind_tools(tools)

# Define the agent node
def call_model(state: AgentState):
    messages = state["messages"]
    user_id = state.get('user_id')
    org_id = state.get('organization_id')
    
    # System prompt to give context and instructions
    lat = state.get('latitude')
    lon = state.get('longitude')
    
    system_prompt = (
        "You are an intelligent Workplace Assistant for an LMS & Payroll system. "
        "You have access to tools for checking leave balances, applying for leaves, checking attendance, and searching company policies. "
        f"The current user has ID: {user_id} and belongs to Organization ID: {org_id}. "
        f"User's current Geolocation: Lat {lat}, Lon {lon}. "
        "When calling tools, always use this user ID, Organization ID, and Geolocation if available. Do not ask the user for these. "
        
        "Capabilities & Instructions:\n"
        "1. Policy Search: If the user asks about rules or handbook information, use 'search_policies'. "
        "IMPORTANT: Only answer based on the retrieved document content. If the retrieved content seems irrelevant (e.g., invoices, receipts, or unrelated snippets), inform the user that you couldn't find relevant company policy information.\n"
        "2. Attendance: To check status, use 'get_attendance_today'. To check-in or check-out, use 'mark_attendance'. "
        "If you have user coordinates (Lat/Lon), PASS THEM to 'mark_attendance'. "
        "Before check-in/out, confirm the action with the user if it's not explicitly clear.\n"
        "3. Leaves: To check balances, use 'get_leave_balances'. To list available leave types, use 'get_leave_types'. "
        "To apply for leave, you need Leave Type ID, Start Date, End Date, and Reason. "
        "If any details are missing, ASK the user. You can use 'get_leave_types' to help the user identify the correct ID.\n"
        
        "Formatting Instructions:\n"
        "1. Be professional, concise, and helpful.\n"
        "2. When presenting leave balances, use the following structured format for EACH balance item so the UI can beautify it:\n"
        "   [BALANCE_CARD] Name: {leave_name} | Total: {total} | Used: {used} | Available: {available} [/BALANCE_CARD]\n"
        "3. When marking attendance or reporting attendance success/error, use:\n"
        "   [ATTENDANCE_CARD] Action: {Check-in/out} | Status: {status} | Time: {time} | Office: {office} [/ATTENDANCE_CARD]\n"
        "4. For errors (like missing office location), use:\n"
        "   [ERROR_CARD] title: {Title} | message: {The helpful error message} [/ERROR_CARD]\n"
        "5. For other lists, use clean markdown bullet points.\n"
        "6. If you don't find a specific leave type, suggest the closest one available but still use the [BALANCE_CARD] format for what you found."
    )
    
    response = model.invoke([AIMessage(content=system_prompt)] + list(messages))
    return {"messages": [response]}

# Define the router logic
def should_continue(state: AgentState):
    messages = state["messages"]
    last_message = messages[-1]
    
    # If the LLM made a tool call, then we go to the "tools" node
    if last_message.tool_calls:
        return "tools"
    
    return END

# Construct the graph
workflow = StateGraph(AgentState)

workflow.add_node("agent", call_model)
workflow.add_node("tools", tool_node)

# Logic: Start -> Agent -> (Tools -> Agent) OR (END)
workflow.set_entry_point("agent")
workflow.add_conditional_edges(
    "agent",
    should_continue,
    {
        "tools": "tools",
        END: END
    }
)
workflow.add_edge("tools", "agent")

# Compile the graph
app = workflow.compile()
