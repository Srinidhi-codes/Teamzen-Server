from typing import Annotated, Sequence, TypedDict, Union, List, Optional
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, ToolMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from langgraph.graph.message import add_messages
from django.conf import settings
from .tools import get_leave_balances, apply_for_leave, get_attendance_today, search_policies, get_leave_types, mark_attendance, check_team_availability, get_team_stats, list_pending_leaves, cancel_leave, suggest_leave_window
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
tools = [get_leave_balances, apply_for_leave, get_attendance_today, search_policies, get_leave_types, mark_attendance, check_team_availability, get_team_stats, list_pending_leaves, cancel_leave, suggest_leave_window]
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
        "You have access to tools for checking leave balances, applying for leaves, checking attendance, searching company policies, checking team availability, and getting organization stats. "
        f"The current user has ID: {user_id} and belongs to Organization ID: {org_id}. "
        f"User's current Geolocation: Lat {lat}, Lon {lon}. "
        "When calling tools, always use this user ID, Organization ID, and Geolocation if available. Do not ask the user for these. "
        
        "Capabilities & Instructions:\n"
        "1. Policy Search: If the user asks about rules or handbook information, use 'search_policies'. "
        "IMPORTANT: Only answer based on the retrieved document content.\n"
        "2. Attendance: To check status, use 'get_attendance_today'. To check-in or check-out, use 'mark_attendance'. "
        "If 'get_attendance_today' returns an anomaly (like missing yesterday logout), PROACTIVELY inform the user and suggest they correct it.\n"
        "3. Leaves: To check balances, use 'get_leave_balances'. To list available leave types, use 'get_leave_types'. "
        "To apply for leave, ALWAYS use 'check_team_availability' first to see if many others are off during that period, and mention this in your advice to the user. "
        "If some leaves are 'pending', inform the user that there are potential conflicts.\n"
        "LEAVE MANAGEMENT: If the user wants to cancel a leave, use 'list_pending_leaves' first to show them their pending requests, then use 'cancel_leave' with the specific ID they choose.\n"
        "LEAVE TYPE SELECTION: If the user wants to apply for leave but has not specified WHICH leave type (e.g., Casual, Sick), you MUST call 'get_leave_types' first and present the options using 'LEAVE_TYPE_CARD' so they can choose one.\n"
        "IMPORTANT: To call 'apply_for_leave', you NEED Leave Type ID, Start Date, End Date, and Reason. If any of these are missing from the conversation, DO NOT call the tool; instead, ASK the user to provide the missing details (e.g., 'What dates are you planning?' or 'What is the reason for your leave?').\n"
        "4. Team Analytics: If the user (Admin/Manager) asks about organization status or trends, use 'get_team_stats'.\n"
        "5. Leave Recommendations: If the user asks for advice on when to take a leave, or if they have a high leave balance, use 'suggest_leave_window'.\n"
        
        "Formatting Instructions:\n"
        "1. Be professional, concise, and helpful.\n"
        "2. When presenting leave balances, use:\n"
        "   [BALANCE_CARD] Name: {leave_name} | Total: {total} | Used: {used} | Available: {available} [/BALANCE_CARD]\n"
        "   When SUGGESTING or LISTING available leave types, use:\n"
        "   [LEAVE_TYPE_CARD] name: {leave_name} | description: {short_desc} | availability: {Recommended/Busy/Fair} | id: {leave_type_id} [/LEAVE_TYPE_CARD]\n"
        "3. When marking attendance or reporting attendance success/error, use:\n"
        "   [ATTENDANCE_CARD] Action: {Check-in/out} | Status: {status} | Time: {time} | Office: {office} [/ATTENDANCE_CARD]\n"
        "4. When listing pending leaves (e.g., for cancellation), ALWAYS use:\n"
        "   [PENDING_LEAVE_CARD] id: {request_id} | type: {leave_type} | from: {from_date} | to: {to_date} | duration: {days} | reason: {reason} [/PENDING_LEAVE_CARD]\n"
        "5. For proactive insights (e.g., team availability or yesterday's missed logout), ALWAYS use:\n"
        "   [INSIGHT_CARD] title: {Title} | message: {Reasoning/Message} | type: {info/warning/stats} | stats: {Key1:Val1, Key2:Val2} [/INSIGHT_CARD]\n"
        "6. For errors, use:\n"
        "   [ERROR_CARD] title: {Title} | message: {The helpful error message} [/ERROR_CARD]\n"
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
