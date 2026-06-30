# 💤 RestIQ

<div align="center">

### Your Personal AI Sleep Concierge

*Track your sleep. Understand your habits. Build healthier routines with a team of AI agents.*

![Python](https://img.shields.io/badge/Python-3.11-blue)
![Google ADK](https://img.shields.io/badge/Google-ADK-green)
![Gemini](https://img.shields.io/badge/Gemini-2.5%20Flash-orange)
![SQLite](https://img.shields.io/badge/SQLite-Database-lightgrey)
![License](https://img.shields.io/badge/License-MIT-yellow)

</div>

---

## 🌙 Why RestIQ?

Many people know they should sleep better—but struggle to consistently build healthy habits.

Most sleep trackers simply collect data. RestIQ goes one step further by acting as an **AI sleep concierge** that understands your daily check-ins, identifies patterns, adapts recommendations over time, and provides personalized coaching.

Instead of overwhelming users with charts, RestIQ answers:

* 😴 *How well did I actually sleep?*
* 📈 *Am I improving?*
* ⏰ *When should I go to bed tonight?*
* 💡 *What small habit should I change next?*

---

# ✨ Features

| Feature                       | Description                                                    |
| ----------------------------- | -------------------------------------------------------------- |
| 🗣 Natural Language Check-ins | Log sleep naturally instead of filling forms                   |
| 🤖 Multi-Agent AI             | Specialized agents collaborate to analyze your sleep           |
| 📊 Sleep Score                | Personalized score based on duration, consistency, and quality |
| 🌙 Adaptive Bedtime           | Dynamically adjusts bedtime recommendations                    |
| 📈 Weekly Reports             | Trend analysis with visual charts                              |
| 📱 Telegram Integration       | Daily reminders and weekly summaries                           |
| 💾 Persistent Storage         | Sleep history stored locally using SQLite                      |

---

# 🧠 Multi-Agent Workflow

```
User
 │
 ▼
Intake Agent
 │
 ▼
Scheduler Agent
 │
 ▼
Tracker Agent
 │
 ▼
Analyzer Agent
 │
 ▼
Reporter Agent
 │
 ▼
Dashboard / Telegram
```

Each agent has a dedicated responsibility:

### Intake Agent

* Understands natural language
* Extracts sleep information
* Validates user input

### Scheduler Agent

* Calculates circadian recommendations
* Adjusts bedtime gradually
* Evaluates improvement plans

### Tracker Agent

* Stores sleep records
* Retrieves historical data
* Manages user profiles

### Analyzer Agent

* Detects sleep trends
* Identifies unhealthy habits
* Generates personalized insights

### Reporter Agent

* Produces weekly summaries
* Creates visual charts
* Suggests actionable improvements

---

# 🏗 Architecture

```
                 Streamlit Dashboard
                        │
                        ▼
                Agent Orchestrator
                        │
 ┌──────────┬──────────┬──────────┬──────────┬──────────┐
 │ Intake   │Scheduler │ Tracker  │Analyzer  │Reporter  │
 └──────────┴──────────┴──────────┴──────────┴──────────┘
                        │
                  MCP Tool Server
                        │
        ┌───────────────┴──────────────┐
        │                              │
     SQLite Database            Telegram Bot
```

---

# 🛠 Tech Stack

| Category           | Technology       |
| ------------------ | ---------------- |
| AI Agent Framework | Google ADK       |
| Language Model     | Gemini 2.5 Flash |
| MCP                | FastMCP          |
| Frontend           | Streamlit        |
| Notifications      | Telegram Bot     |
| Database           | SQLite           |
| Validation         | Pydantic         |
| Visualization      | Plotly           |

---

# 📂 Project Structure

```text
restiq/
│
├── agents/
│   ├── intake.py
│   ├── scheduler.py
│   ├── tracker.py
│   ├── analyzer.py
│   └── reporter.py
│
├── restiq_agent/
│   ├── __init__.py
│   └── agent.py
│
├── pipeline.py
├── db/                    # SQLite schema + entry access
├── tools/                 # Tool implementations (parse, store, analyze, …)
├── agents/                # Agent orchestration (calls tools/)
├── mcp_server.py          # Thin MCP wrapper for ADK / external clients
├── plan_engine.py
├── schemas.py
├── streamlit_app.py
├── bot.py
├── logger_config.py
├── sleep_data.db
├── pyproject.toml
├── uv.lock
└── README.md
```

---

# 🚀 Getting Started

## Clone Repository

```bash
git clone https://github.com/yourusername/restiq.git

cd restiq
```

## Install [uv](https://docs.astral.sh/uv/)

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Windows (PowerShell):

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

## Install Dependencies

From the project root:

```bash
uv sync
```

This creates a `.venv` virtual environment and installs locked dependencies from `uv.lock`.

## Configure Environment

Copy the example file and add your keys:

```bash
cp .env.example .env
```

Edit `.env` with your values. See `.env.example` for what each variable does.

| Variable | Required for | Notes |
|----------|--------------|-------|
| `GOOGLE_API_KEY` | Check-ins, ADK agent | [Google AI Studio](https://aistudio.google.com/apikey) |
| `GEMINI_MODEL` | Optional | Defaults to `gemini-2.5-flash` |
| `TELEGRAM_BOT_TOKEN` | Telegram bot | From [@BotFather](https://t.me/BotFather) |
| `TELEGRAM_BOT_USERNAME` | Streamlit Telegram link | Bot username without `@` |

Streamlit and the pipeline only need `GOOGLE_API_KEY`. The Telegram bot needs all four.

---

# ▶ Running RestIQ

Start Streamlit

```bash
uv run streamlit run streamlit_app.py
```

Start Telegram Bot

```bash
uv run python bot.py
```

Run Agent Development UI

```bash
uv run adk web restiq_agent
```

Run Full Pipeline

```bash
uv run python pipeline.py
```

---

# 📱 Example User Journey

### Step 1

Register through the dashboard.

↓

### Step 2

Connect Telegram using the generated deep link.

↓

### Step 3

Log today's sleep.

Example:

> "I slept from 11 PM until 7 AM. Woke up once and felt refreshed."

↓

### Step 4

RestIQ analyzes your sleep.

Example Output

```
Sleep Score: 87/100

Duration:
8 hours

Quality:
Good

Recommendation:
Move bedtime 15 minutes earlier this week.

Weekly Trend:
Improving consistency.
```

---

# 🔧 MCP Tools

| Tool                | Purpose                  |
| ------------------- | ------------------------ |
| register_user       | Create user profile      |
| link_telegram       | Connect Telegram account |
| parse_sleep_input   | Parse natural language   |
| calculate_circadian | Recommend bedtime        |
| evaluate_plan       | Update sleep plan        |
| store_sleep_data    | Save sleep record        |
| analyze_patterns    | Detect trends            |
| generate_report     | Produce weekly report    |
| get_user_profile    | Retrieve profile         |

---

# 🎓 Google x Kaggle AI Agents Intensive

This project demonstrates concepts learned throughout the course.

| Day   | Applied Concept                  |
| ----- | -------------------------------- |
| Day 1 | Prompt Engineering & Vibe Coding |
| Day 2 | MCP & Agent Communication        |
| Day 3 | Agent Skills & Planning          |
| Day 4 | Identity & Secure Design         |
| Day 5 | Production Multi-Agent System    |

---

# 🔮 Future Improvements

* Apple Health integration
* Google Fit integration
* Wearable device support
* AI-powered sleep forecasting
* Personalized sleep coaching memory
* Calendar-aware bedtime recommendations

---

# 📸 Demo

> *(Add screenshots or GIFs here)*

Dashboard

```
images/dashboard.png
```

Weekly Report

```
images/report.png
```

Telegram Bot

```
images/telegram.png
```

---

# 📄 License

This project is licensed under the MIT License.

---

<div align="center">

Built for the **Google x Kaggle 5-Day AI Agents Intensive**.

Made with ❤️ to help people build healthier sleep habits.

</div>
