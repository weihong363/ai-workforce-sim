# EMPLOYEE_LIFECYCLE.md — AI Employee Lifecycle System

## 0. Core Philosophy

Employees are NOT tools.

They are:

→ dynamic entities  
→ emotionally reactive  
→ strategically manageable  

Goal:

Create a system where:

- players manage people, not prompts
- decisions have long-term consequences

---

## 1. Employee Lifecycle Overview

    Recruit → Assign → Perform → React → Evolve → Leave

---

## 2. Core Attributes

Each employee has:

    skill_level (0-100)
    obedience (0-1)
    initiative (0-1)
    effort (0-1)
    reliability (0-1)
    affinity (0-100)

---

## 3. Affinity System (CRITICAL)

Affinity represents how much the employee likes the player.

### 3.1 Effects of Affinity

#### 1. Obedience Modifier
effective_obedience = base_obedience * (affinity / 100)

#### 2. Effort Modifier (Willingness to work)
effective_effort = base_effort * (affinity / 100)


#### 3. Quality Modifier
quality_bonus = (affinity - 50) * 0.2

#### 4. Leave Probability
leave_prob = max(0, (30 - affinity) / 30)

---

## 4. Behavior Effects

### 4.1 Low Affinity Behavior

- ignores instructions
- produces shorter output
- may refuse tasks (low probability)

### 4.2 High Affinity Behavior

- follows instructions more strictly
- produces higher quality output
- willing to “go extra”

---

## 5. Task Assignment Impact

Each task affects affinity:

### Positive Effects

- task success: +5
- high score: +5
- being selected: +3

### Negative Effects

- task failure: -5
- forced overtime: -3
- being ignored (unused): -2

---

## 6. Overtime System


Define overtime trigger:

if task_complexity > threshold:
requires_overtime = True


---

### Overtime Impact

```
if requires_overtime:
affinity -= 3
effort temporarily increases
```

---

## 7. Refusal System

Employees may refuse tasks:
if affinity < 20:
20% chance to refuse

```
Refusal behavior:

- “I don’t want to do this task”
- “This is not my responsibility”

```

---

## 8. Leaving System

Employees do NOT leave instantly.

### Leaving Check (per run)

    if random() < leave_prob:
    employee leaves

---

## 9. Recruitment System

### 9.1 Hiring New Employees

New employees are generated with:

- random personality
- random skill
- neutral affinity (50)

### 9.2 Hiring Quality

Options:

- cheap hire → low skill
- expensive hire → better stats

---

## 10. Team Size Limit

    max_team_size = base + upgrades

Prevents:

- infinite scaling
- brute-force strategies

---

## 11. Employee Growth

### 11.1 Usage Growth

    after N tasks:
    skill_level += 1

### 11.2 Emotional Growth

- repeated success → affinity increases faster
- repeated failure → affinity decay accelerates

---

## 12. System Interactions (VERY IMPORTANT)

### Example Chain Reaction:
    
    force overtime
    → affinity drops
    → effort drops
    → output quality drops
    → score drops
    → profit drops

---

## 13. Strategic Trade-offs

Players must choose:

### Strategy A: Exploit

- force overtime
- maximize short-term output

Result:

- fast gains
- long-term instability

### Strategy B: Maintain

- keep employees happy
- stable performance

Result:

- slower growth
- long-term consistency

---

## 14. Future Extensions (DO NOT IMPLEMENT YET)

### 14.1 Employee Relationships

- employees influence each other
- conflicts / synergy

### 14.2 Mood System

- temporary emotional states
- affects short-term behavior

### 14.3 Loyalty Trait

- some employees less likely to leave

---

## 15. MVP Scope

Only implement:

- affinity
- obedience / effort linkage
- leave probability

DO NOT overbuild.
