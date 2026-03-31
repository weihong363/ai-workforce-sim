# GAME_BALANCE.md — Game Economy & Balance

## 0. Core Philosophy

**Balance goal:**

- Reward optimization, not randomness
- Encourage iteration
- Penalize laziness (bad management)

---

## 1. Core Loop

```
Manage → Execute → Evaluate → Profit → Upgrade
```

---

## 2. Reward System

### Base Reward

Each task has:

- **base_reward** (e.g. 100)

---

### Final Reward

```formula
final_reward = base_reward * (score / 100)
```

---

## 3. Cost System (CRITICAL)

Cost is based on token usage:

```formula
cost = tokens_used * cost_per_token
```

---

### Suggested Values (MVP)

- **cost_per_token** = 0.001
- **average task cost** = 20–80

---

## 4. Profit Formula

```formula
profit = final_reward - cost
```

---

### Design Goal:

- **Bad runs** → negative or low profit
- **Good runs** → high profit

---

## 5. Failure Impact

Failure should:

- Reduce score by **10–40%**
- Increase rework (extra cost)

---

## 6. Difficulty Scaling

### Task Difficulty Levels

| Level  | Reward | Constraints |
|--------|--------|-------------|
| Easy   | 50     | loose       |
| Medium | 100    | moderate    |
| Hard   | 200    | strict      |

---

### Difficulty Effects:

- Higher failure penalty
- Higher reward ceiling

---

## 7. Agent Efficiency

Agents affect:

- output quality
- token usage
- error rate

---

### Example:

| Agent Type | Quality | Cost | Error |
|------------|---------|------|-------|
| Junior     | Low     | Low  | High  |
| Senior     | High    | High | Low   |

---

## 8. Market Pricing

---

### Asset Price Formula

```formula
price = score * multiplier
```

---

### Suggested:

- **multiplier** = 0.5 – 1.5

---

## 9. Revenue Distribution

---

### Default Split

- **Creator**: 60%
- **Upstream contributors**: 20%
- **System fee**: 20%

---

## 10. Leaderboard Rules

Rank by:

1. Total profit
2. Average profit per run
3. Consistency

---

## 11. Anti-Exploitation Rules

---

### Prevent:

- Infinite retries with no cost
- Free high-quality generation

---

### Solutions:

- charge every run
- limit retries
- degrade repeated runs

---

## 12. Retention Mechanics

---

### Key Drivers:

- visible improvement
- leaderboard climbing
- unlocking better agents

---

### Avoid:

- random outcomes
- unfair scoring

---

## 13. Tuning Strategy

---

### Start with:

- higher rewards
- lower penalties

### Then:

- tighten economy gradually
