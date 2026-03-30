# DATA_FLOW.md

## Core Flow

run_task
→ load module
→ build workflow
→ run agents
→ evaluate
→ transform to asset
→ persist

---

## Agent Flow

step
→ build prompt
→ route model
→ call LLM
→ normalize output
→ failure injection
→ return result

---

## Evaluation Flow

output
→ module provides metrics
→ evaluate
→ final_score

---

## Asset Flow

output
→ module transform
→ asset
→ store

---

## Rule

engine controls flow
module defines meaning

---

## Future Data Flow (Disabled in MVP)

### Semantic Retrieval Flow

task input
→ embed
→ vector search
→ retrieve similar tasks/assets
→ enrich context
→ run agent

Status:
NOT ENABLED

---

### Distributed Agent Execution

run_task
→ split into agent jobs
→ queue
→ multiple workers
→ aggregate results

Status:
NOT ENABLED

---

## Current Rule

All execution is:

single run
→ sequential workflow
→ single execution context

No distributed system.
