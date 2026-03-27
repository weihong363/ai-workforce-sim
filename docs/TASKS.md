# TASKS.md — Multi-Agent Simulation Engine

## 0. Principles

- Tasks must be small, atomic, and testable
- Each phase must produce a working system
- Separate core engine work from game module work
- Do NOT hardcode any single game into the engine
- Always keep extensibility in mind

---

# PHASE 0 — Project Setup (Foundation)

## Goal
Initialize reusable backend engine and basic structure

## Tasks

### 0.1 Project Bootstrap
- Initialize FastAPI project
- Setup folder structure:
  - /core_engine
  - /core_engine/agents
  - /core_engine/workflow
  - /core_engine/evaluation
  - /core_engine/assets
  - /core_engine/execution
  - /core_engine/game_loader
  - /game_modules
  - /api
  - /db

### 0.2 Infrastructure Setup
- Setup Redis
- Setup Celery worker
- Setup PostgreSQL (or SQLite for MVP)

### 0.3 Basic Health Endpoints
- GET /health
- GET /status

### 0.4 Config System
- Add environment-based config loader
- Support:
  - REDIS_URL
  - DATABASE_URL
  - ACTIVE_GAME_MODULE
  - MODEL_PROVIDER_KEYS

### Definition of Done
- Server runs
- Worker runs
- Redis connected
- Active game module can be configured

---

# PHASE 1 — Agent System (Core Abstraction)

## Goal
Create reusable controllable AI agent units

## Tasks

### 1.1 Agent Schema
- Define Agent schema
- Fields:
  - role
  - capabilities
  - skills
  - personality
  - flaws
  - metadata

### 1.2 Prompt Builder
- Build function:
  - build_prompt(agent, task, context, game_context=None)

### 1.3 LLM Wrapper
- Create unified LLM client
- Support:
  - prompt input
  - token tracking
  - provider name
  - model name
  - retries
  - timeout

### 1.4 Failure Injection
- Implement:
  - random truncation
  - instruction skipping
  - configurable failure rate
  - optional game-provided modifiers

### 1.5 Agent Executor
- Function:
  - run_agent(agent, task, context, game_context=None)

### Definition of Done
- Can run a single agent task
- Output is imperfect when configured
- Agent schema is game-agnostic

---

# PHASE 2 — Workflow Engine

## Goal
Enable reusable multi-agent collaboration

## Tasks

### 2.1 Workflow Schema
- Define:
  - workflow_id
  - steps[]
  - agent_ref
  - task
  - dependencies
  - execution_mode

### 2.2 Sequential Execution
- Implement workflow runner
- Pass structured output as context

### 2.3 Async Execution
- Move workflow execution to Celery task

### 2.4 Result Storage
- Save:
  - inputs
  - outputs
  - timestamps
  - token usage
  - step status

### 2.5 Workflow Boundary Rules
- Ensure workflow engine contains no game-specific semantics
- Task meaning must come from game module only

### Definition of Done
- Can execute 3-step workflow
- Runs asynchronously
- Workflow execution is game-agnostic

---

# PHASE 3 — Evaluation Engine

## Goal
Provide generic scoring capability for all game modules

## Tasks

### 3.1 Evaluation Input Schema
- Define:
  - metrics[]
  - weights
  - scoring_context
  - expected_output

### 3.2 Scoring Engine
- Support generic metric-based evaluation
- Accept metrics from active game module
- Example metrics:
  - clarity
  - quality
  - accuracy
  - engagement

### 3.3 Cost Tracking
- Track token usage per step and per run

### 3.4 Score Aggregation
- Combine weighted metrics into final_score

### 3.5 Evaluation API
- POST /evaluate

### Definition of Done
- Each run can be scored using module-defined metrics
- Engine does not assume any specific domain metric set

---

# PHASE 4 — Core Task System

## Goal
Define reusable task abstractions

## Tasks

### 4.1 Task Template Schema
- Create generic template structure
- Fields:
  - type
  - input
  - constraints
  - expected_output
  - metadata

### 4.2 Task Instance Generator
- Generate task instances from template

### 4.3 Task API
- GET /tasks
- POST /run-task

### 4.4 Task Boundary Rules
- Engine defines task structure only
- Concrete tasks are provided by game modules

### Definition of Done
- Engine can store and run generic task instances
- No game-specific task content is hardcoded

---

# PHASE 5 — Asset System (Core Abstraction)

## Goal
Convert workflow outputs into reusable assets

## Tasks

### 5.1 Asset Schema
- Fields:
  - id
  - type
  - creator_id
  - data
  - score
  - metadata
  - game_type

### 5.2 Asset Creation
- Convert workflow output → asset

### 5.3 Asset Storage
- Save asset to DB

### 5.4 Asset API
- GET /assets
- GET /asset/{id}

### 5.5 Asset Boundary Rules
- Engine stores and serializes assets
- Game module defines asset meaning and usage

### Definition of Done
- Workflow outputs can be serialized into generic assets
- Asset semantics remain module-defined

---

# PHASE 6 — Game Module Interface

## Goal
Allow multiple games to plug into the same engine

## Tasks

### 6.1 Game Module Schema
- Define required module structure:
  - agents.py
  - tasks.py
  - rules.py
  - evaluation.py
  - assets.py (optional)

### 6.2 Module Loader
- Load active game module dynamically from config

### 6.3 Interface Contract
- Define required functions:
  - get_agents()
  - get_task_templates()
  - get_rules()
  - get_evaluation_config(task)
  - compute_reward(score, context)
  - transform_output_to_asset(output, context)

### 6.4 Module Isolation
- Ensure game-specific logic does not leak into core engine

### Definition of Done
- Engine can boot with one active game module
- Swapping modules does not require engine code changes

---

# PHASE 7 — Competitive Systems (Reusable)

## Goal
Provide reusable competition primitives

## Tasks

### 7.1 Ranking Model
- Rank runs by configurable metrics

### 7.2 Leaderboard API
- GET /leaderboard

### 7.3 Shared Task Support
- Allow same task instance to be used by multiple players

### 7.4 Competitive Run Tracking
- Compare users on same challenge

### Definition of Done
- Any game module can enable leaderboard-based competition

---

# PHASE 8 — Scaling & Optimization

## Goal
Stability, concurrency, and cost control

## Tasks

### 8.1 Caching Layer
- Cache agent outputs
- Cache evaluation results

### 8.2 Rate Limiting
- Limit concurrent jobs
- Limit provider-specific throughput

### 8.3 Parallel Execution
- Support parallel execution for independent workflow steps

### 8.4 Logging & Monitoring
- Track latency
- Track failures
- Track token usage
- Track provider errors

### 8.5 Retry / Fallback
- Retry failed LLM calls
- Support provider/model fallback

### Definition of Done
- System remains stable under moderate load
- Caching and rate limiting are provider-agnostic

---

# FINAL NOTES

## Architecture Rules

- Always separate:
  - agent logic
  - workflow logic
  - evaluation logic
  - game module logic
- Never tightly couple engine code to a specific game

---

## Engine MVP Cut Line

Engine MVP = Phase 0–6

---

## Competitive Engine Version

Engine Competitive Version = Phase 0–8

---

## Core Loop

Load Module → Execute → Evaluate → Serialize → Compare
