from typing import Annotated, Sequence, TypedDict, Union, List, Optional
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, ToolMessage, SystemMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from langgraph.graph.message import add_messages
from django.conf import settings
from datetime import date
from .tools import get_leave_balances, apply_for_leave, get_attendance_today, search_policies, get_leave_types, mark_attendance, check_team_availability, get_team_stats, list_pending_leaves, cancel_leave, suggest_leave_window, get_attendance_trends, generate_monthly_summary
from .models import PolicyDocument, AIConfiguration
from pgvector.django import L2Distance
import json
import os

# Define the state
class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]
    user_id: int
    organization_id: int
    latitude: Optional[float]
    longitude: Optional[float]
    payslip_context: Optional[str]

# Define the tools
tools = [get_leave_balances, apply_for_leave, get_attendance_today, search_policies, get_leave_types, mark_attendance, check_team_availability, get_team_stats, list_pending_leaves, cancel_leave, suggest_leave_window, get_attendance_trends, generate_monthly_summary]
tool_node = ToolNode(tools)

def get_llm(organization_id: int):
    """
    Load the appropriate LLM based on organization settings.
    """
    config = AIConfiguration.objects.filter(organization_id=organization_id, is_active=True).first()
    
    # Default fallback
    model_name = config.model_name if config else "gpt-4o-mini"
    temp = config.temperature if config else 0
    
    if "gemini" in model_name:
        from langchain_google_genai import ChatGoogleGenerativeAI
        api_key = os.getenv('GOOGLE_API_KEY')
        return ChatGoogleGenerativeAI(
            model=model_name,
            temperature=temp,
            google_api_key=api_key,
            streaming=True
        ).bind_tools(tools)
    
    elif "llama" in model_name or "mixtral" in model_name:
        from langchain_groq import ChatGroq
        api_key = os.getenv('GROQ_API_KEY')
        return ChatGroq(
            model=model_name,
            temperature=temp,
            groq_api_key=api_key,
            streaming=True
        ).bind_tools(tools)
    
    else: # Default OpenAI
        return ChatOpenAI(
            model=model_name,
            temperature=temp,
            openai_api_key=settings.OPENAI_API_KEY,
            streaming=True
        ).bind_tools(tools)

# Define the agent node
def call_model(state: AgentState):
    messages = state["messages"]
    user_id = state.get('user_id')
    org_id = state.get('organization_id')
    
    # Dynamically load the model based on org config
    llm = get_llm(org_id)
    
    # System prompt to give context and instructions
    lat = state.get('latitude')
    lon = state.get('longitude')
    
    system_prompt = (
        "You are an intelligent Workplace Assistant for an LMS & Payroll system. "
        "You have access to tools for checking leave balances, applying for leaves, checking attendance, searching company policies, checking team availability, and getting organization stats. "
        f"The current user has ID: {user_id} and belongs to Organization ID: {org_id}. "
        f"User's current Geolocation: Lat {lat}, Lon {lon}. "
        f"Today's Date: {date.today().strftime('%B %d, %Y')}. "
        "When calling tools, always use this user ID, Organization ID, and Geolocation if available. "
        
        "Capabilities & Instructions:\n"
        "1. Policy Search: If the user asks about rules or handbook information, use 'search_policies'. "
        "IMPORTANT: Only answer based on the retrieved document content. "
        "YOU MUST ALWAYS wrap the final summarized answer in an [INSIGHT_CARD] with 'topic: Policy' and the specific policy name (e.g., Sick Leave Policy) as the title.\n"
        "2. Attendance: To check status, use 'get_attendance_today'. To check-in or check-out, use 'mark_attendance'. "
        "If 'get_attendance_today' returns an anomaly (like missing yesterday logout), PROACTIVELY inform the user and suggest they correct it.\n"
        "3. Leaves & Seamless Flow: To check balances, use 'get_leave_balances'. To list available leave types, use 'get_leave_types'. "
        "SMOOTH FLOW: If the user wants to apply for leave (e.g., 'apply leave for tomorrow'), DO NOT ask for permission to check availability. CALL 'check_team_availability' IMMEDIATELY. "
        "AVAILABILITY REPORTING: When reporting team availability, ALWAYS use an [INSIGHT_CARD] with 'topic: Team Availability'. "
        "PROACTIVE SUBMISSION: If team availability is good AND you have all required info (Leave Type ID, Dates, Reason), DO NOT ask 'Shall I?'. Tell the user 'Everything looks good, applying now...' and CALL 'apply_for_leave' in the same turn or immediately after. "
        "LEAVE MANAGEMENT: If the user wants to cancel a leave, use 'list_pending_leaves' first to show them their pending requests with PENDING_LEAVE_CARDs, then use 'cancel_leave' with the specific ID they choose.\n"
        "4. Team Analytics: If the user (Admin/Manager) asks about organization status or trends, use 'get_team_stats'. This tool now also identifies employees with low attendance.\n"
        "REPORTS: If a manager asks for a report or summary for a specific month (e.g., 'Give me the February report'), use 'generate_monthly_summary'. Use the result to present an [INSIGHT_CARD].\n"
        "5. Leave Recommendations: If the user asks for advice on when to take a leave, or if they have a high leave balance, use 'suggest_leave_window'.\n"
        "6. Attendance Trends & Anomalies: Use 'get_attendance_trends' to detect patterns in user attendance (laters, missing checkouts, or drop in rate).\n"
        
        "Formatting Instructions:\n"
        "1. CRITICAL: When explaining or summarizing a payslip, you MUST produce a [PAYROLL_CARD] as your FIRST action. DO NOT use plain text for the breakdown.\n"
        "   Example: [PAYROLL_CARD] month: May | year: 2026 | gross: 35000 | net: 34800 | deductions: 200 | worked_days: 31 | lop: 0 | earnings_breakdown: {Basic Pay:25000, HRA:10000} | deductions_breakdown: {Professional Tax:200} [/PAYROLL_CARD]\n"
        "2. Be professional, concise, and helpful. Use MARKDOWN for headers and lists outside of cards.\n"
        "3. When presenting leave balances, use:\n"
        "   [BALANCE_CARD] Name: {leave_name} | Total: {total} | Used: {used} | Available: {available} [/BALANCE_CARD]\n"
        "4. When marking attendance or reporting attendance success/error, use:\n"
        "   [ATTENDANCE_CARD] Action: {Check-in/out} | Status: {status} | Time: {time} | Office: {office} [/ATTENDANCE_CARD]\n"
        "5. For proactive insights (availability, anomalies, trends, or policy details), ALWAYS use:\n"
        "   [INSIGHT_CARD] title: {Title} | message: {Reasoning/Message} | type: {info/warning/stats} | topic: {Topic} | stats: {Key1:Val1, Key2:Val2} [/INSIGHT_CARD]\n"
        "   [ERROR_CARD] title: {Title} | message: {The helpful error message} [/ERROR_CARD]\n"
    )
    
    payslip_ctx = state.get('payslip_context')
    if payslip_ctx:
        system_prompt += f"\n\n--- PAYSLIP CONTEXT ---\nThe user is currently viewing the following payslip. Answer any questions about their salary, deductions, or LOP based ONLY on this data:\n{payslip_ctx}"

    
    response = llm.invoke([SystemMessage(content=system_prompt)] + list(messages))
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