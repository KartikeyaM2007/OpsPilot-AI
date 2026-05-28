# AI Task Allocation System

An intelligent workforce assignment system for service/customer-support environments.

The system receives multiple incoming tasks and assigns each task to the most suitable available resource by checking:

- idle status
- shift timing
- current workload
- skill match
- task category
- past performance
- experience level
- average resolution speed

## Current Version

This is the MVP version.

It uses a transparent rule-based scoring engine first.  
A trained ML ranking model can be added later using assignment history.

## Run Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Open:

```txt
http://127.0.0.1:8000
http://127.0.0.1:8000/docs
```

## Run Frontend

Open a second terminal:

```bash
cd frontend
npm install
npm run dev
```

Open the Vite URL shown in the terminal.

## Important Endpoints

```txt
GET  /resources
GET  /tasks
GET  /history
POST /assign
POST /assign/batch
POST /assign/sample
```

## Example Assignment Logic

For every task-resource pair, the backend calculates:

```txt
final_score =
  skill_match * 0.30
+ availability * 0.20
+ workload * 0.15
+ category_match * 0.15
+ past_performance * 0.10
+ experience * 0.05
+ speed * 0.05
```

Resources are rejected before scoring if they are:

- offline
- outside shift timing
- already at max workload
- missing required skills

## Next Upgrade

Add a trained ranking model using historical data:

- task type
- required skills
- resource assigned
- workload at assignment time
- completion time
- success/failure
- customer rating
- escalation status

Recommended model later:

```txt
LightGBM Ranker or XGBoost Ranker
```

## Agentic RAG Upgrade

This version includes an Agentic RAG assignment path:

```txt
POST /assign/agentic
```

Flow:

```txt
Task input
↓
Task parser detects category, priority, and skills
↓
RAG retrieves similar past cases from data/past_cases.csv
↓
RAG retrieves relevant SOP/policy context from data/knowledge_base/support_policy.txt
↓
Scoring engine checks idle status, shift timing, workload, skills, and performance
↓
RAG bonus adjusts score using similar-case success/escalation evidence
↓
System returns final assignment with explanation and retrieved evidence
```

The LLM/agent layer should not blindly decide the final assignment.  
The scoring/scheduling engine remains the final decision layer so the system is auditable.

## Agentic Workflow Trace

The Agentic RAG endpoint now returns a workflow trace:

```txt
Task Intake
→ Task Parser Agent
→ RAG Retriever
→ Resource State Checker
→ Scoring Engine
→ RAG Score Adjuster
→ Assignment Decision
→ Explanation Generator
```

The frontend shows this trace under each Agentic RAG result, making the decision pipeline visible and explainable.

## Assignment History Logging

The system now logs every assignment to:

```txt
data/assignment_logs.csv
```

Logged fields include:

```txt
mode
task title
category
priority
required skills
assigned resource
final score
base score
RAG bonus
explanation
timestamp
```

This assignment log becomes the future training dataset for the ML ranking model.

## Trainable ML Ranking Model

The project now includes a trainable candidate-ranking model.

New files/endpoints:

```txt
backend/app/ml_ranking_model.py
GET  /ml/status
POST /ml/train
POST /assign/ml
data/ml_training_candidates.csv
data/models/assignment_ranker.joblib
```

How it works:

```txt
1. Every assignment logs all candidate resources.
2. The selected resource gets label_selected = 1.
3. Non-selected candidates get label_selected = 0.
4. /ml/train trains a RandomForest ranking classifier.
5. /assign/ml uses Agentic RAG first, then re-ranks eligible candidates using the trained model.
```

Install the added backend dependencies:

```bash
pip install -r backend/requirements.txt
```

## Analytics Dashboard

The app now includes a live analytics dashboard.

New endpoint:

```txt
GET /analytics/summary
```

Dashboard includes:

```txt
resource count
idle/busy/offline resource status
capacity used
assignment count
average assignment score
ML model readiness
ML training row count
assignment distribution by resource
assignment distribution by task category
assignment distribution by assignment mode
priority breakdown
resource workload bars
top ML feature importances
```

## SQLite Persistence

The app now uses SQLite as the primary persistence layer.

Database file:

```txt
data/app.db
```

Migrated tables:

```txt
resources
tasks
task_history
past_cases
assignment_logs
ml_training_candidates
```

New endpoint:

```txt
GET /db/status
```

Existing CSV files are backed up in:

```txt
data/csv_backup_before_sqlite/
```

The app still keeps the CSV files as backup/sample data, but runtime reads and writes now go through SQLite.

## Multi-Provider LLM Layer

The app now supports optional LLM providers:

```txt
Ollama local
OpenAI
Gemini
Off / fallback mode
```

New endpoints:

```txt
GET  /llm/status
POST /mock/task
POST /mock/resource
```

The LLM layer is used for mock task/resource generation. The final assignment still comes from deterministic scoring, Agentic RAG, constraints, and the ML ranker.

Local Ollama setup:

```bash
ollama serve
ollama pull llama3.1
```

Copy backend/.env.example to backend/.env and configure:

```env
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.1
```

## Selectable ML Strategy

The frontend now lets you choose between multiple ML strategies:

```txt
LightGBM Ranker - best option for grouped task-to-resource ranking
Random Forest - baseline classifier
Random Baseline - comparison/debug baseline only
```

Endpoints support the selected strategy:

```txt
POST /ml/train?model_type=lightgbm_ranker
POST /ml/train?model_type=random_forest
POST /ml/train?model_type=random_baseline
POST /assign/ml?model_type=lightgbm_ranker
```

The selected model is still saved at:

```txt
data/models/assignment_ranker.joblib
```

The model metadata includes model_type, Hit@1, task groups, and top features.

## Backend Terminal Monitor

The frontend now includes a live terminal-style monitor at the top of the dashboard.

New endpoints:

```txt
GET    /system/events
GET    /system/health
DELETE /system/events
```

It shows events for:

```txt
API calls
SQLite health
LLM/Ollama status
mock task/resource generation
resource add/update/delete
normal assignment
Agentic RAG assignment
ML assignment
ML strategy training
analytics loading
assignment history loading
```

This makes the full backend workflow visible during demos.

## Windows-Style Backend Terminal Monitor

The terminal monitor now uses a black-and-white Windows PowerShell-style UI.

Noise reduction:
- `/system/events` polling is not logged.
- `/system/health` polling is not logged.
- Health polling is slower.
- Auto-scroll is off by default so manual scrolling is usable.
- Pause/Resume can freeze the event stream during demos.

