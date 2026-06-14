import os
import json
from dotenv import load_dotenv
from typing import TypedDict, Annotated, List

load_dotenv()

from langchain_core.tools import tool
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from langgraph.graph import StateGraph, END
from database import db_create_task, db_get_tasks, db_update_task_status

# Initialize LLM
# Replace with your preferred model or configuration
llm = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash", 
    temperature=0,
    google_api_key=os.getenv("GOOGLE_API_KEY")
)

# Define Graph State
class AgentState(TypedDict):
    messages: List[BaseMessage]
    next_step: str
    output: str

# --- Definition of Tools ---
@tool
def create_new_task(title: str, assignee: str, priority: str = "medium", due_date: str = None) -> str:
    """Use this tool to create a new task when requested by the user."""
    return db_create_task(title, assignee, priority, due_date)

@tool
def update_task_status(task_id: int, status: str) -> str:
    """Use this tool to change task status, such as marking a task completed or pending."""
    return db_update_task_status(task_id, status)

@tool
def list_and_search_tasks(assignee: str = None, status: str = None) -> str:
    """Use this tool to view pending, completed, or specific users' tasks."""
    tasks = db_get_tasks(assignee=assignee, status=status)
    if not tasks:
        return "No tasks found matching those parameters."
    return "\n".join([f"ID: {t.id} | {t.title} | Assignee: {t.assignee} | Status: {t.status} | Priority: {t.priority} | Due: {t.due_date}" for t in tasks])

# --- Nodes ---

def router_node(state: AgentState):
    """Evaluates user intent and decides which specialist agent to invoke."""
    user_msg = state["messages"][-1].content
    
    prompt = f"""
    Analyze the user request: "{user_msg}"
    Classify it into one of these actions:
    1. 'action' (If creating a task, modifying, changing status, assigning)
    2. 'query' (If asking to show tasks, what to focus on, checking overdue, or searching)
    
    Respond with ONLY a raw JSON dictionary.
    {{"next_step": "action"}} or {{"next_step": "query"}}
    """
    
    response = llm.invoke([HumanMessage(content=prompt)])
    
    # 1. Clean the text to remove markdown formatting that crashes Python
    clean_text = response.content.strip().replace("```json", "").replace("```", "").strip()
    
    try:
        data = json.loads(clean_text)
        # 2. Print to your terminal so you can see the routing live!
        print(f"\n---> ROUTER DECISION: Sending to {data['next_step'].upper()} AGENT <---")
        return {"next_step": data["next_step"]}
    except Exception as e:
        print(f"\n---> ROUTER ERROR: Failed to parse '{clean_text}'. Defaulting to QUERY AGENT <---")
        return {"next_step": "query"}

# def action_agent_node(state: AgentState):
#     """Executes state changes on the data layer with 100% certainty."""
#     user_msg = state["messages"][-1].content
    
#     # We strip away the LLM's ability to choose. We force it to output ONLY JSON.
#     system_prompt = """
#     You are a strict data extraction tool. You do not converse.
#     Extract the task details from the user's message and output ONLY a raw JSON dictionary.
#     Do not include markdown blocks like ```json. Just the raw dictionary.
    
#     Format:
#     {
#         "action": "create",
#         "title": "the task name",
#         "assignee": "person name",
#         "priority": "high",
#         "due_date": "YYYY-MM-DD or None"
#     }
#     """
    
#     response = llm.invoke([
#         {"role": "system", "content": system_prompt},
#         HumanMessage(content=user_msg)
#     ])
    
#     try:
#         # Clean the response in case Gemini adds markdown anyway
#         clean_text = response.content.replace("```json", "").replace("```", "").strip()
#         data = json.loads(clean_text)
        
#         # MANUALLY execute the database tool based on the JSON
#         if data.get("action") == "create":
#             result = create_new_task.invoke({
#                 "title": data["title"],
#                 "assignee": data["assignee"],
#                 "priority": data.get("priority", "medium"),
#                 "due_date": data.get("due_date", None)
#             })
#             return {"output": result}
            
#     except Exception as e:
#         return {"output": f"System parsed the intent, but encountered an error: {str(e)}\nRaw AI output was: {response.content}"}

#     return {"output": "System could not determine the action."}


def action_agent_node(state: AgentState):
    """Executes state changes on the data layer with 100% certainty."""
    user_msg = state["messages"][-1].content

    system_prompt = """
    You are a strict data extraction tool. You do not converse.
    Extract the task details from the user's message and output ONLY a raw JSON dictionary.
    Do not include markdown blocks like ```json. Just the raw dictionary.

    There are two possible formats depending on the request:

    1. Creating a new task:
    {"action": "create", "title": "the task name", "assignee": "person name", "priority": "high", "due_date": "YYYY-MM-DD or None"}

    2. Updating/completing an existing task (when the user references a task by ID or describes marking something done/in-progress/pending):
    {"action": "update", "task_id": 5, "status": "completed"}

    "status" must be one of: pending, in_progress, completed.
    If the user doesn't give a task ID explicitly, do your best to infer it from numbers in the message.
    """

    response = llm.invoke([
        {"role": "system", "content": system_prompt},
        HumanMessage(content=user_msg)
    ])

    try:
        clean_text = response.content.replace("```json", "").replace("```", "").strip()
        data = json.loads(clean_text)

        if data.get("action") == "create":
            result = create_new_task.invoke({
                "title": data["title"],
                "assignee": data["assignee"],
                "priority": data.get("priority", "medium"),
                "due_date": data.get("due_date", None)
            })
            return {"output": result}

        elif data.get("action") == "update":
            result = update_task_status.invoke({
                "task_id": int(data["task_id"]),
                "status": data["status"]
            })
            return {"output": result}

    except Exception as e:
        return {"output": f"System parsed the intent, but encountered an error: {str(e)}\nRaw AI output was: {response.content}"}

    return {"output": "System could not determine the action."}

def query_agent_node(state: AgentState):
    """Retrieves tasks and creates intelligent summaries or advice."""
    user_msg = state["messages"][-1].content
    
    # Provide system context along with current tasks to let LLM formulate smart summaries
    all_raw_tasks = db_get_tasks()
    task_context = "\n".join([f"ID: {t.id} | {t.title} | Assignee: {t.assignee} | Status: {t.status} | Priority: {t.priority} | Due: {t.due_date}" for t in all_raw_tasks])
    
    prompt = f"""
    You are an intelligent Task Management Optimizer. 
    Here is the current system state of all tasks:
    {task_context}
    
    Answer the user request clearly: "{user_msg}"
    Provide recommendations, prioritize intuitively, and call out critical actions if they ask what to focus on.
    """
    
    response = llm.invoke([HumanMessage(content=prompt)])
    return {"output": response.content}

# --- Construct the LangGraph ---
workflow = StateGraph(AgentState)

workflow.add_node("router", router_node)
workflow.add_node("action_agent", action_agent_node)
workflow.add_node("query_agent", query_agent_node)

workflow.set_entry_point("router")

def route_conditional(state: AgentState):
    return state["next_step"]

workflow.add_conditional_edges(
    "router",
    route_conditional,
    {
        "action": "action_agent",
        "query": "query_agent"
    }
)

workflow.add_edge("action_agent", END)
workflow.add_edge("query_agent", END)

agent_graph = workflow.compile()

def run_task_agent(user_input: str) -> str:
    initial_state = {"messages": [HumanMessage(content=user_input)], "next_step": "", "output": ""}
    result = agent_graph.invoke(initial_state)
    return result["output"]