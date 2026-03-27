# MANAGEMENT_STRATEGY_SYSTEM.md — Management Strategy System

## 0. Core Philosophy

The player is NOT controlling tools.

The player is managing:

    → personalities  
    → emotions  
    → trade-offs  

Goal:

Create meaningful strategic choices.

---

## 1. Management Styles (Core System)

Players can choose a management style.

Each style affects:

- employee behavior
- performance
- long-term stability

---

## 2. Core Management Modes

### 2.1 Control Mode (强控制)

Description:

Strict, top-down management.

```
Effects:

+ obedience +0.3
+ reliability +0.2
- initiative -0.3
- affinity decay faster  
```

```
Behavior:

- employees follow instructions strictly
- low creativity
- high burnout risk
```

### 2.2 Balanced Mode (平衡)

Description:

Moderate control with some flexibility.

```
Effects:

+ small boost to all stats  
no major penalties  
```

```
Behavior:

- stable performance
- predictable outcomes
```

### 2.3 Freedom Mode (自由发挥)

Description:

Encourage employees to think independently.

```
Effects:

+ initiative +0.4  
+ creativity +0.3  
- obedience -0.3  
- reliability -0.2  
```

```
Behavior:

- employees may deviate from instructions
- higher variance in results
```

---

## 3. Dynamic Adjustment

Players can switch styles:

- per task
- per employee (advanced)

Switch cost:

- small affinity drop (-2)

---

## 4. Management Actions (Micro Layer)

### 4.1 Praise

```
Effect:

+ affinity +5  
+ temporary effort boost  
```

### 4.2 Pressure

```
Effect:

+ short-term effort  
- affinity -5  
```

### 4.3 Ignore

```
Effect:

- affinity -2 over time  
```

### 4.4 Reward (Future)

```
Effect:

+ affinity  
+ loyalty  
```

---

## 5. Strategy Archetypes

### Strategy A: Exploiter

- heavy pressure
- overtime usage

```
Result:

+ high short-term output  
- high churn  
```

### Strategy B: Builder

- maintain affinity
- avoid overtime

```
Result:

+ stable team  
- slower growth  
```

### Strategy C: Risk Taker

- freedom mode
- high initiative

```
Result:

+ occasional high scores  
- unstable performance  
```

---

## 6. System Interactions

### Example:

    Control Mode + Pressure
    → high output
    → fast affinity decay
    → employee leaves
### Example:

    Freedom Mode + High skill employee
    → creative output
    → higher evaluation variance

---

## 7. Emergent Gameplay (IMPORTANT)

System should allow:

- unexpected outcomes
- player learning over time


Goal:

    Player asks:
    
    → “Which strategy is better?”
    
    NOT:
    
    → “What is the correct answer?”

---

## 8. UI Suggestions

Show:

- employee mood indicators
- warnings (low affinity)
- risk hints

---

## 9. MVP Scope

Only implement:

- 2 management modes (Control / Balanced)
- Praise + Pressure actions

DO NOT overbuild.
