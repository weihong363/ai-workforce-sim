# DB_SCHEMA.md — AI Workforce Simulation System

## 0. Design Principles

- Normalize core entities
- Keep relationships explicit
- Support future expansion (PVP, market, teams)

---

## 1. Users

```sql
CREATE TABLE users (
  id UUID PRIMARY KEY,
  email TEXT,
  industry TEXT,
  level INT,
  created_at TIMESTAMP
);
```

---

## 2. Agents

```sql
CREATE TABLE agents (
  id UUID PRIMARY KEY,
  user_id UUID,
  role TEXT,
  skills JSONB,
  personality JSONB,
  flaws JSONB,
  created_at TIMESTAMP
);
```

---

## 3. Tasks

```sql
CREATE TABLE tasks (
  id UUID PRIMARY KEY,
  template TEXT,
  input JSONB,
  constraints JSONB,
  reward INT,
  industry TEXT,
  game_type TEXT,
  created_at TIMESTAMP
);
```

---

## 4. Workflow Runs

```sql
CREATE TABLE runs (
  id UUID PRIMARY KEY,
  user_id UUID,
  task_id UUID,
  status TEXT,
  total_cost FLOAT,
  final_score FLOAT,
  profit FLOAT,
  created_at TIMESTAMP
);
```

---

## 5. Workflow Steps

```sql
CREATE TABLE steps (
  id UUID PRIMARY KEY,
  run_id UUID,
  agent_id UUID,
  step_order INT,
  input TEXT,
  output TEXT,
  token_usage INT,
  created_at TIMESTAMP
);
```

---

## 6. Assets (CRITICAL)

```sql
CREATE TABLE assets (
  id UUID PRIMARY KEY,
  type TEXT,
  creator_id UUID,
  run_id UUID,
  content TEXT,
  score FLOAT,
  price FLOAT,
  game_type TEXT
  created_at TIMESTAMP
);
```

---

## 7. Market Listings

```sql
CREATE TABLE market_listings (
  id UUID PRIMARY KEY,
  asset_id UUID,
  seller_id UUID,
  price FLOAT,
  status TEXT,
  created_at TIMESTAMP
);
```

---

## 8. Transactions

```sql
CREATE TABLE transactions (
  id UUID PRIMARY KEY,
  asset_id UUID,
  buyer_id UUID,
  seller_id UUID,
  price FLOAT,
  created_at TIMESTAMP
);
```

---

## 9. Leaderboard

```sql
CREATE TABLE leaderboard (
  user_id UUID,
  total_profit FLOAT,
  rank INT
);
```

---

## 10. Evaluation Logs

```sql
CREATE TABLE evaluations (
  id UUID PRIMARY KEY,
  run_id UUID,
  metrics JSONB,
  final_score FLOAT,
  created_at TIMESTAMP
);
```

---

## 11. Future Extensions (DO NOT IMPLEMENT YET)

### Teams (PVP)

```sql
CREATE TABLE teams (
  id UUID PRIMARY KEY,
  name TEXT
);
```

### Team Members

```sql
CREATE TABLE team_members (
  team_id UUID,
  user_id UUID
);
```

### Contracts (Collaboration)

```sql
CREATE TABLE contracts (
  id UUID,
  asset_id UUID,
  parties JSONB,
  revenue_split JSONB
);
```

---

## 12. Relationships Overview

- users → agents
- users → runs
- runs → steps
- runs → assets
- assets → market_listings
- market_listings → transactions

---

## 13. Key Constraints

- One user = one industry
- One run = one task execution
- One asset = one run output

---

## 14. Indexing Suggestions

- users.industry
- assets.score
- market_listings.status
- transactions.created_at


