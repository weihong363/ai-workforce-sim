# ARCHITECTURE.md — Multi-Agent Simulation Engine

---

## 0. System Philosophy

This system is:

- NOT a chatbot  
- NOT a simple LLM wrapper  

It is a:

```
→ Multi-agent execution engine  
→ Workflow orchestration platform  
→ Pluggable game simulation system  
```

Core idea:

- Engine handles execution  
- Game modules define rules  

---

## 1. High-Level Architecture

```
Client  
↓  
API Layer (FastAPI)  
↓  
Service Layer  
↓  
Task Queue (Celery)  
↓  
Worker Layer  
↓  
Core Engine  
    ↓  
    Agent Controller  
    ↓  
    Workflow Engine  
    ↓  
    Evaluation Engine  
    ↓  
    Asset System  
↓  
Game Module (dynamic)  
↓  
LLM Provider  
↓  
Cache (Redis) + Database (PostgreSQL)  
```

---

## 2. Architecture Layers

---

### 2.1 API Layer (/api)

Responsibilities:

- Receive user requests  
- Validate inputs  
- Trigger async tasks  
- Return job_id  

Rules:

- MUST be stateless  
- MUST NOT execute heavy logic  
- MUST NOT call LLM directly  

---

### 2.2 Service Layer (/services)

Acts as orchestration layer between API and engine.

Modules:

- task_service  
- asset_service  
- user_service  
- module_service  

Responsibilities:

- Route requests to engine  
- Load active game module  
- Transform inputs/outputs  

---

### 2.3 Task Queue (Celery)

Responsibilities:

- Async execution  
- Retry handling  
- Concurrency control  

Task types:

- run_workflow  
- evaluate_output  
- post_process_asset  

---

### 2.4 Worker Layer

Each worker is an execution node.

Responsibilities:

- Execute workflows  
- Call core engine  
- Store results  

Workers must be:

- stateless  
- horizontally scalable  

---

## 3. Core Engine (CRITICAL)

The core engine is reusable across all games.

It MUST NOT contain any game-specific logic.

---

### 3.1 Agent Controller (/core_engine/agents) 🔥

MOST IMPORTANT MODULE

Responsibilities:

1. Construct prompts  
2. Inject personality  
3. Inject flaws  
4. Call LLM  
5. Inject failures  
6. Return structured output  

Design Rules:

- Agents are NOT models  
- Agents wrap LLM behavior  
- All LLM calls MUST go through this layer  
- MUST support multiple providers  

---

### 3.2 Workflow Engine (/core_engine/workflow)

Responsibilities:

- Execute multi-step tasks  
- Pass structured outputs between steps  
- Manage execution order  
- Support async and parallel execution  

Types:

- sequential  
- parallel

Execution Pattern:

```
step1 → output1  
step2(input=output1) → output2  
step3(input=output2)  
```

Rules:

- Workflow must be game-agnostic  
- Task semantics come from game modules  

---

### 3.3 Evaluation Engine (/core_engine/evaluation)

Responsibilities:

- Score outputs using LLM  
- Normalize metrics  
- Aggregate scores

Rules:

- Metrics must be provided by game module  
- Must return structured JSON  
- Must be decoupled from workflow  

---

### 3.4 Asset System (/core_engine/assets)

Core abstraction:

```
→ All outputs can become assets  
```

Responsibilities:

- Serialize outputs  
- Store assets  
- Attach metadata  
- Support reuse  

Rules:

- Asset structure is generic  
- Engine does NOT define asset meaning  
- Game module defines:
  - asset types  
  - usage rules  
  - pricing logic  

---

### 3.5 Execution Layer (/core_engine/execution)

Responsibilities:

- Coordinate workflow execution  
- Handle retries  
- Handle concurrency  
- Track run state  

---

## 4. Game Module Layer (NEW, CRITICAL)

Game modules define domain-specific behavior.

The engine MUST treat game modules as plug-ins.

---

### 4.1 Responsibilities of Game Module

Each game module defines:

- agent presets  
- task templates  
- evaluation rules  
- reward logic  
- asset semantics  
- progression systems  

---

### 4.2 Module Structure

```
game_modules/{module_name}/
├── agents.py       # Agent presets and configurations
├── tasks.py        # Task templates and definitions
├── rules.py        # Game-specific rules and constraints
├── evaluation.py   # Evaluation logic and metrics
└── assets.py       # Asset transformation and pricing
```

---

### 4.3 Interface Contract

Each module must expose:

```
class GameModule:

    def get_agents(self): ```
    def get_task_templates(self): ```
    def get_rules(self): ```
    def get_evaluation_config(self, task): ```
    def compute_reward(self, score, context): ```
    def transform_output_to_asset(self, output, context): ```
```

---

### 4.4 Isolation Rules

- Engine MUST NOT import module-specific logic directly  
- Module MUST NOT modify engine behavior  
- Interaction only through defined interfaces  

---

## 5. Data Flow

---

### 5.1 Task Execution Flow

```
User → API → Celery Task → Worker  
→ Load Game Module  
→ Workflow Engine  
→ Agent Controller (LLM)  
→ Evaluation Engine  
→ Asset Creation  
→ Store in DB  
```

---

### 5.2 Asset Flow

```
Workflow Output  
→ Transform (module-defined)  
→ Asset  
→ Store  
→ Reuse  
```

---

### 5.3 Game-Specific Flow (Example)

NOTE: Defined by module, NOT engine

```
Asset A  
→ Used as input  
→ New task execution  
→ New asset  
```

---

## 6. Key Abstractions

---

### 6.1 Agent

Encapsulates behavior

---

### 6.2 Workflow

Encapsulates execution logic

---

### 6.3 Task

Encapsulates structured problem

---

### 6.4 Asset

Encapsulates output container

---

### 6.5 Game Module

Encapsulates domain rules

---

## 7. Extensibility Points (VERY IMPORTANT)

System MUST support:

---

### 7.1 New Agent Types

- Add new capabilities  
- Add new personalities  
- No engine changes required  

---

### 7.2 New Game Modules

- Plug into engine  
- Define own rules  
- No engine rewrite  

---

### 7.3 Multi-Model Support

- Swap LLM providers  
- Route by agent or task  

---

### 7.4 Competitive Systems

- Shared tasks  
- Leaderboards  
- Reusable across modules  

---

## 8. Anti-Patterns (DO NOT DO)

❌ Direct LLM calls in API  
❌ Hardcoding prompts in multiple places  
❌ Mixing workflow + evaluation logic  
❌ Embedding game rules in engine  
❌ Treating outputs as raw text  

---

## 9. Performance Strategy

Use Redis for:

- caching agent outputs  
- caching evaluation results  

Use Celery for:

- concurrency  
- retries  

Use asyncio for:

- parallel agent execution

---

## 10. Mental Model

Think of system as:

- Execution Engine  
- Simulation Engine  
- Game Platform

NOT as:

- A single game  
- A chatbot  
- A prompt tool  

---

## 11. Final Principle

    Engine = HOW things run  
    Game Module = WHAT the rules are

Never mix the two.

---

## Future Extensions (Not in MVP)

These are planned but MUST NOT be implemented now.

### 1. Agent-level Workers

Future:
- each agent may run as an independent worker
- distributed execution
- queue-based scheduling

Current MVP:
- one run = one execution context
- agents run inside workflow runner

---

### 2. Semantic Layer (Vector Search)

Future:
- pgvector or similar for:
  - task similarity search
  - asset retrieval
  - prompt improvement suggestions
  - agent memory

Current MVP:
- no vector database
- no semantic retrieval

---

### 3. Advanced Simulation

Future:
- hiring / firing
- agent resignation (low affinity)
- team management
- multi-agent collaboration optimization

Current MVP:
- single user owns small agent set
- no lifecycle management yet

---

## Rule

Future features must NOT affect current MVP architecture.

Do not introduce:
- distributed workers
- vector DB
- long-term memory

until core loop is validated.
