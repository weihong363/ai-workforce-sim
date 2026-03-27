# AGENTS.md — AI Workforce Simulation System

## 0. Overview

This project is a reusable multi-agent simulation engine.

Core concept:
- Users manage AI agents instead of directly prompting LLMs
- The engine executes structured multi-agent workflows
- Game-specific rules are defined in pluggable game modules
- Outputs can be evaluated, transformed into assets, and used by higher-level systems

This is NOT a chatbot system.
This is a structured multi-agent workflow + simulation engine.

---

## 1. Core Architecture

System layers:

1. API Layer (FastAPI)
2. Task Queue (Celery + Redis)
3. Agent Controller (core logic)
4. LLM Provider (OpenAI / others)
5. Cache (Redis)
6. Database (PostgreSQL)

Execution flow:

```
User → API → Task Queue → Worker → Agent Controller → LLM → Cache/DB → Response
```

---

## 2. Core Concepts

### 2.1 Agent

Agents are NOT models.
Agents are controlled behavior units on top of LLMs.

Each agent must have:
- role
- capabilities
- skills
- personality
- flaws

Example:

```json
{
  "role": "text_worker",
  "capabilities": ["write", "summarize"],
  "skills": {"text_generation": 80},
  "personality": {
    "laziness": 0.6,
    "accuracy": 0.7
  },
  "flaws": ["skip_details", "generic_output"]
}
```

**IMPORTANT:**

- Agents must NOT be perfect
- Imperfection = core gameplay
- Game modules may define role presets such as copywriter, analyst, editor, etc.

### 2.2 Workflow

A workflow is a sequence of agent tasks.

Example:

```json
[
  {"agent": "agent_a", "task": "analyze input"},
  {"agent": "agent_b", "task": "generate draft"},
  {"agent": "agent_c", "task": "refine output"}
]
```

**Rules:**

- Each step only sees structured output from previous step 
- No raw prompt leakage across agents 
- Keep context minimal 
- Game modules define the concrete meaning of each task

### 2.3 Asset (CRITICAL)

All outputs can be converted into Assets.

An Asset is a structured representation of a workflow result.

Example:

```json
{
  "id": "...",
  "type": "generic",
  "creator_id": "...",
  "data": {},
  "score": 0-100,
  "metadata": {}
}
```
**Rules:**

- Asset structure must be generic
- Engine does NOT define asset meaning 
- Game modules define:
  - asset types 
  - pricing logic
  - usage rules

### 2.4 Game Module (CRITICAL)

Game-specific logic must be defined in game modules.

A game module is responsible for:
- defining task templates
- defining agent presets
- defining evaluation rules
- defining reward logic
- defining any domain-specific systems (industry, classes, market rules, etc.)

The core engine must NOT hardcode game-specific concepts.

### 2.5 Asset / Economy Layer

Assets are optional higher-level abstractions built on top of workflow outputs.

A game module may choose to:
- store outputs as assets
- price them
- trade them in a market
- connect them into an economy loop

The engine only guarantees that outputs can be evaluated and serialized.

## 3. Game Module Interface

Each game module must implement or define:

- agent presets
- task templates
- evaluation rules
- reward calculation
- asset transformation rules (optional)

Example interface:

```python
class GameModule:
    def get_agents(self): ...
    def get_tasks(self): ...
    def evaluate(self, output): ...
    def compute_reward(self, score): ...
    def transform_output_to_asset(self, output): ...
```

Engine responsibilities:

execute workflows
manage agent behavior
handle concurrency
cache results
persist data
Game module responsibilities:
define rules
define content
define progression/economy specifics

## 4. Agent Controller (MOST IMPORTANT MODULE)

**Responsibilities:**

Build prompt from agent config

Inject personality + flaws

Call LLM

Inject failure (random or rule-based)

- Return structured output

### 4.1 Prompt Construction Rules

Always include:

- role
- personality
- constraints

**Never:**

- Expose system internals
- Make prompts non-deterministic

### 4.2 Failure Injection

**Required behavior:**

- 10–30% chance of degraded output

**Possible failures:**

- truncate output
- ignore instructions
- introduce minor errors

This is REQUIRED for gameplay.

## 5. Evaluation System

Evaluation is LLM-based.

Each task must define:

```json
{
  "metrics": ["clarity", "engagement", "quality"],
  "weights": {}
}
```

Evaluation returns:

```json
{
  "scores": {},
  "final_score": number
}
```

### 5.1 Profit Calculation

```
profit = reward - cost
```

Cost = token usage

Profit is the PRIMARY leaderboard metric.

## 6. Task System

Tasks are generated from templates.

Structure:

```json
{
  "template": "...",
  "input": {},
  "constraints": {},
  "reward": number
}
```

### 6.1 Task Design Principles

Tasks must:
- be structured
- be evaluable
- be understandable within the context of the active game module
- define clear inputs, constraints, and expected outputs

The engine should not assume any specific domain.
Domain-specific tasks are defined by game modules.

## 7. Concurrency & Execution

Use Celery workers.

**Rules:**

- All workflows run asynchronously
- Do NOT block API

Use Redis for:

- queue
- caching

### 7.1 Caching Strategy

Cache key:

```
hash(agent + prompt)
```

Cache:

- agent outputs
- evaluation results

## 8. Data Model (Simplified)

Tables:
- users
- agents
- tasks
- runs
- assets
- transactions
- leaderboard
- game_modules (optional registry)

Important:
- tasks, assets, and runs should support a game_type / module_id field
- this enables multiple games to share the same engine

## 9. Coding Guidelines

- Use Python (FastAPI + Celery)
- Keep modules small and composable

Separate:

- agent logic
- workflow logic
- evaluation logic

## 10. Important Design Constraints

**DO NOT:**

- Build a chatbot interface
- Let users directly prompt LLM freely
- Make agents too smart
- Skip failure injection
- Hardcode business_sim concepts into the engine
- Hind agent definitions to a single game world

**ALWAYS:**

- Keep agents imperfect
- Keep workflows structured
- Keep outputs measurable
- Convert outputs into assets

## 11. Future Extensions (Do NOT implement yet)

- Agent training / memory
- Multi-model routing
- PvP competitions
- Team collaboration

Focus on MVP first.

## 12. Development Priority

Build in this order:

1. Agent Controller
2. Workflow Executor
3. Evaluation System
4. Asset + Market system
5. Basic leaderboard

## 13. Mental Model

Treat this system as:
- a reusable simulation engine
- a workflow execution engine
- a foundation for multiple game modules

Not as:
- a single hardcoded game
- a chatbot
- a prompt wrapper

**Core loop:**

```
Manage → Execute → Evaluate → Trade → Optimize
```
