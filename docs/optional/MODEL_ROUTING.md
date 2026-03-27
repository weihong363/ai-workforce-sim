# MODEL_ROUTING.md — Model Routing & Cost Strategy

---

## 0. Principles

- Model selection must be dynamic, not fixed
- Different agents should use different models
- Cost must be controllable at runtime
- Model choice is part of gameplay design

---

## 1. Core Idea

Model routing is NOT just engineering.

It controls:

- cost
- output quality
- agent differentiation

---

## 2. Model Layers

Define 3 tiers:

---

### 2.1 Low Tier (Cheap / High Volume)

Use for:

- junior agents
- batch generation
- simulation

Examples:

- minimax
- qwen-low
- gpt-4o-mini

---

### 2.2 Mid Tier (Balanced)

Use for:

- main workflow steps
- standard agents

Examples:

- gpt-4o-mini
- qwen-max

---

### 2.3 High Tier (Expensive / Critical)

Use for:

- final output
- evaluation
- high-value steps

Examples:

- gpt-4.1
- claude sonnet

---

## 3. Routing Rules

---

### 3.1 By Agent Level

...

if agent.level == "junior":
    model = "low_tier"
elif agent.level == "mid":
    model = "mid_tier"
else:
    model = "high_tier"

...

---

### 3.2 By Task Importance

...

if task.is_critical:
    model = "high_tier"

...

---

### 3.3 By Budget Constraint

...

if budget < threshold:
    downgrade_model()

...

---

## 4. Multi-Agent Strategy

Instead of:

- 1 strong agent

Use:

- multiple weak agents + selection

...

Example:

run 3 low-tier agents  
→ evaluate  
→ pick best  

...

Benefits:

- lower cost
- higher variance (gameplay)
- more realistic teamwork

---

## 5. Evaluation Model Rules

Evaluation MUST use:

- stable model
- consistent outputs

...

Rules:

- DO NOT use low-tier models for evaluation
- DO NOT mix multiple evaluation models randomly

---

## 6. Cost Tracking

Each run must track:

- tokens used
- model used
- cost per step

...

Example:

{
  "model": "gpt-4o-mini",
  "tokens": 1200,
  "cost": 0.02
}

...

---

## 7. Budget System (Optional but Recommended)

Define per-task budget:

...

task_budget = 0.05

...

If exceeded:

- downgrade model
- reduce retries
- skip optional steps

---

## 8. Caching Strategy

Cache key:

...

hash(model + prompt)

...

Cache:

- agent outputs
- evaluation results

---

## 9. Fallback Strategy

If model fails:

...

try:
    call primary model
except:
    fallback to cheaper model

...

---

## 10. Behavior + Model Coupling (IMPORTANT)

Agent behavior is NOT only model-based.

Final capability =

...

model_strength × prompt × personality × affinity

...

Example:

- same model
- different obedience → different output

---

## 11. Game Impact

Model routing affects gameplay:

- cheap agents = unstable
- expensive agents = reliable
- multi-agent = strategic choice

---

## 12. Anti-Patterns

DO NOT:

- use same model for all agents
- use strongest model everywhere
- ignore cost tracking
- mix evaluation models randomly

---

## 13. Final Principle

...

Model = capability ceiling  
Behavior = actual performance  

...

Design both.

---

END OF FILE
