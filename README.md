# Multi-Agent Task Engine

A decentralized, AI-powered task management system that integrates natively with Google Chat. This system utilizes a multi-agent architecture to autonomously parse user intent, manage state in a local database, and serve real-time updates to an operational dashboard.

## 🏗 Architecture Overview
This project uses a **Supervisor/Router Architecture** powered by LangGraph and Gemini 2.5 Flash.

1. **User Interface:** Users interact naturally via Google Chat.
2. **API Gateway:** A FastAPI backend receives webhooks. To prevent platform timeouts during heavy LLM reasoning, FastAPI instantly returns a 200 OK while passing the payload to a Background Worker.
3. **LangGraph Engine:**
   * **Supervisor Router:** Evaluates the prompt and deterministically routes it.
   * **Action Agent:** A strictly constrained agent that extracts JSON to execute database writes (creating/updating tasks).
   * **Query Agent:** An analytical agent that reads the database to provide summaries and recommendations.
4. **Data & Presentation Layer:** SQLite maintains state, while a Jinja2 frontend acts as a live Operational Dashboard. A daily cron job proactively checks for overdue tasks.

## 🚀 Setup & Installation

**1. Clone the repository:**
\`\`\`bash
git clone https://github.com/YOUR_USERNAME/multi-agent-task-engine.git
cd multi-agent-task-engine
\`\`\`

**2. Install dependencies:**
\`\`\`bash
pip install -r requirements.txt
\`\`\`

**3. Environment Variables:**
Create a `.env` file in the root directory and add your Gemini API key:
\`\`\`env
GOOGLE_API_KEY=your_gemini_api_key_here
\`\`\`
*(Note: You will also need your `service-account.json` file in the root directory if you wish to enable native Google Chat bot replies).*

**4. Run the server:**
\`\`\`bash
uvicorn main:app --reload
\`\`\`
The operational dashboard will be available locally at `http://127.0.0.1:8000`.

## 🧪 Example Interactions

- "Create a high priority task for John to deploy the frontend by Friday"
- "Assign API testing to Rahul"
- "Show my pending tasks"
- "What should I focus on today?"
- "Mark task #3 as completed"
- "What are my overdue tasks?"

## 🤖 Multi-Agent Design Rationale

- **Router/Supervisor pattern** keeps intent classification separate from execution — the LLM only ever has to make one binary decision (`action` vs `query`) per turn, which keeps it deterministic and easy to debug.
- **Action Agent** is deliberately constrained to JSON-only output with a fixed schema, eliminating the unpredictability of free-form tool-calling for database writes.
- **Query Agent** has full read access to the task table and is free to reason conversationally, since query responses don't mutate state.
- **Async reply pattern** for Google Chat decouples the platform's strict response-time expectations from the LLM's variable latency, while the synchronous web path keeps local testing fast and simple.
