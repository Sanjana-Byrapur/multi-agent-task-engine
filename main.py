# import os
# import requests
# from fastapi import FastAPI, Request, Form, Body
# from fastapi.responses import HTMLResponse
# from fastapi.staticfiles import StaticFiles
# from fastapi.templating import Jinja2Templates
# from fastapi import Request, BackgroundTasks
# import json
# from apscheduler.schedulers.background import BackgroundScheduler
# from google.oauth2 import service_account
# from googleapiclient.discovery import build
# from database import SessionLocal, Task, db_get_tasks
# from agents import run_task_agent, llm
# from langchain_core.messages import HumanMessage

# app = FastAPI(title="Multi-Agent Task Engine")

# SCOPES = ['https://www.googleapis.com/auth/chat.bot']
# CREDS = service_account.Credentials.from_service_account_file(
#     'service-account.json', scopes=SCOPES
# )

# def send_chat_message(space_name: str, text: str, thread_name: str = None):
#     service = build('chat', 'v1', credentials=CREDS)
#     body = {"text": text}
#     if thread_name:
#         body["thread"] = {"name": thread_name}
#     service.spaces().messages().create(parent=space_name, body=body).execute()

# def run_task_agent(user_text: str, space_name: str, thread_name: str):
#     try:
#         result_text = your_agent_pipeline(user_text)  # router -> action -> sqlite
#     except Exception as e:
#         result_text = f"Error processing task: {e}"
#     send_chat_message(space_name, result_text, thread_name)

# # Setup safe folders for UI layout
# os.makedirs("templates", exist_ok=True)
# templates = Jinja2Templates(directory="templates")

# # Optional: Configuration variable to send outgoing notices to Slack or Google Chat
# CHAT_WEBHOOK_URL = os.getenv("CHAT_WEBHOOK_URL", "")

# # --- Autonomous Assistant Job ---
# def proactive_overdue_check_job():
#     """Runs automatically to look for overdue tasks and post summaries to chat platforms."""
#     overdue_tasks = db_get_tasks(check_overdue=True)
#     if overdue_tasks and CHAT_WEBHOOK_URL:
#         task_list_str = "\n".join([f"- {t.title} (Assigned to: {t.assignee}, Due: {t.due_date})" for t in overdue_tasks])
        
#         prompt = f"Write a professional, concise daily warning reminder for a team chat highlighting these overdue items:\n{task_list_str}"
#         ai_summary = llm.invoke([HumanMessage(content=prompt)]).content
        
#         # Post directly to the team communication platform
#         try:
#             requests.post(CHAT_WEBHOOK_URL, json={"text": ai_summary})
#         except Exception as e:
#             print(f"Failed to transmit proactive notification: {e}")

# # Start background cron tasks
# scheduler = BackgroundScheduler()
# scheduler.add_job(proactive_overdue_check_job, 'cron', hour=9, minute=0) # Runs daily at 9:00 AM
# scheduler.start()

# # --- Endpoints ---

# @app.post("/webhook/chat")
# async def chat_webhook(request: Request, background_tasks: BackgroundTasks):
#     try:
#         payload = await request.json()
        
#         user_text = ""
#         if "chat" in payload and "messagePayload" in payload["chat"]:
#             user_text = payload["chat"]["messagePayload"]["message"].get("text", "")
#         else:
#             user_text = payload.get("text", "")
            
#         user_text = user_text.strip()
            
#         if not user_text:
#             return {"text": "Hello! I am ready to manage your tasks."}
            
#         # 1. Send the heavy AI lifting to the background
#         background_tasks.add_task(run_task_agent, user_text)
        
#         # 2. Reply to Google instantly so it never times out
#         return {"text": f"Received request. Processing your task in the background..."}
        
#     except Exception as e:
#         print(f"Webhook error: {e}")
#         return {"text": f"System encountered an error: {str(e)}"}
    
# @app.get("/", response_class=HTMLResponse)
# async def dashboard_home(request: Request):
#     """Renders the simple dashboard tracking task states."""
#     db = SessionLocal()
#     tasks = db.query(Task).order_by(Task.id.desc()).all()
#     db.close()
#     return templates.TemplateResponse("index.html", {"request": request, "tasks": tasks})



import os
import json
from fastapi import FastAPI, Request, BackgroundTasks
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from apscheduler.schedulers.background import BackgroundScheduler
from google.oauth2 import service_account
from googleapiclient.discovery import build
from database import SessionLocal, Task, db_get_tasks
from agents import run_task_agent, llm
from langchain_core.messages import HumanMessage

app = FastAPI(title="Multi-Agent Task Engine")

# --- Google Chat credentials (graceful fallback if missing) ---
SCOPES = ['https://www.googleapis.com/auth/chat.bot']
SERVICE_ACCOUNT_FILE = os.getenv("SERVICE_ACCOUNT_FILE", "service-account.json")

CREDS = None
if os.path.exists(SERVICE_ACCOUNT_FILE):
    CREDS = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE, scopes=SCOPES
    )
else:
    print(f"WARNING: {SERVICE_ACCOUNT_FILE} not found. Chat reply sending is disabled.")

# --- Tiny persistence for "where do I post proactive messages" ---
SPACES_FILE = "known_spaces.json"

def remember_space(space_name: str):
    if not space_name:
        return
    spaces = set()
    if os.path.exists(SPACES_FILE):
        with open(SPACES_FILE) as f:
            spaces = set(json.load(f))
    spaces.add(space_name)
    with open(SPACES_FILE, "w") as f:
        json.dump(list(spaces), f)

def get_known_spaces():
    if os.path.exists(SPACES_FILE):
        with open(SPACES_FILE) as f:
            return json.load(f)
    return []

# --- Chat send helper ---
def send_chat_message(space_name: str, text: str, thread_name: str = None):
    if CREDS is None:
        print(f"[Chat send skipped — no credentials] Would send to {space_name}: {text}")
        return
    if not space_name:
        print(f"[Chat send skipped — no space_name] Message was: {text}")
        return
    service = build('chat', 'v1', credentials=CREDS)
    body = {"text": text}
    if thread_name:
        body["thread"] = {"name": thread_name}
    service.spaces().messages().create(parent=space_name, body=body).execute()

# --- Background worker: runs the actual agent, then replies async ---
def process_and_reply(user_text: str, space_name: str, thread_name: str):
    try:
        result_text = run_task_agent(user_text)
    except Exception as e:
        result_text = f"Error processing task: {e}"
    send_chat_message(space_name, result_text, thread_name)

templates = Jinja2Templates(directory="templates")

# --- Autonomous Assistant Job ---
def proactive_overdue_check_job():
    overdue_tasks = db_get_tasks(check_overdue=True)
    if not overdue_tasks:
        return

    task_list_str = "\n".join(
        [f"- {t.title} (Assigned to: {t.assignee}, Due: {t.due_date})" for t in overdue_tasks]
    )
    prompt = f"Write a professional, concise daily warning reminder for a team chat highlighting these overdue items:\n{task_list_str}"
    ai_summary = llm.invoke([HumanMessage(content=prompt)]).content

    for space_name in get_known_spaces():
        try:
            send_chat_message(space_name, ai_summary)
        except Exception as e:
            print(f"Failed to post proactive notification to {space_name}: {e}")

scheduler = BackgroundScheduler()
scheduler.add_job(proactive_overdue_check_job, 'cron', hour=9, minute=0)
scheduler.start()

# --- Endpoints ---

@app.post("/webhook/chat")
async def chat_webhook(request: Request, background_tasks: BackgroundTasks):
    try:
        payload = await request.json()
        print("Incoming payload:", json.dumps(payload, indent=2))  # remove once verified

        message = payload.get("chat", {}).get("messagePayload", {}).get("message", {})
        user_text = message.get("text", "").strip()
        space_name = message.get("space", {}).get("name")
        thread_name = message.get("thread", {}).get("name")

        if not user_text:
            return {"text": "Hello! I am ready to manage your tasks."}

        remember_space(space_name)

        background_tasks.add_task(process_and_reply, user_text, space_name, thread_name)

        return {}

    except Exception as e:
        print(f"Webhook error: {e}")
        return {"text": f"System encountered an error: {str(e)}"}

@app.get("/", response_class=HTMLResponse)
async def dashboard_home(request: Request):
    db = SessionLocal()
    tasks = db.query(Task).order_by(Task.id.desc()).all()
    db.close()
    return templates.TemplateResponse("index.html", {"request": request, "tasks": tasks})