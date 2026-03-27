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
