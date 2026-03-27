# TASKS.md — business_sim Game Module

## 0. Principles

- This file defines ONLY business_sim-specific work
- Do NOT duplicate core engine responsibilities here
- All rules in this module must plug into the engine interface
- Keep the first version narrow and playable

---

# PHASE B0 — Module Setup

## Goal
Create the first playable game module: business_sim

## Tasks

### B0.1 Module Structure
- Create folder:
  - /game_modules/business_sim
- Required files:
  - __init__.py
  - agents.py
  - tasks.py
  - rules.py
  - evaluation.py
  - assets.py

### B0.2 Module Metadata
- Define:
  - module_id = "business_sim"
  - display_name
  - module_description

### Definition of Done
- Module can be discovered by engine loader

---

# PHASE B1 — Industry / Class System

## Goal
Define the core player specialization system

## Tasks

### B1.1 Industry Enum
- Define industries:
  - Content
  - Marketing
  - Product
  - Operations
  - Business

### B1.2 Player Industry Selection
- Add logic so user selects ONE industry

### B1.3 Restriction Rules
- Users can only create assets/tasks within their own industry
- Cross-industry interaction must happen through asset flow or market

### Definition of Done
- A user has one active industry
- Industry affects accessible tasks and agents

---

# PHASE B2 — Agent Presets

## Goal
Create business_sim-specific employee presets

## Tasks

### B2.1 Starter Agents
- Define initial employee presets for MVP
- Suggested presets:
  - junior_writer
  - research_assistant
  - editor

### B2.2 Agent Personality Traits
- Add fields:
  - obedience
  - initiative
  - effort
  - reliability
  - affinity

### B2.3 Seniority Rules
- Junior employees:
  - higher obedience
  - lower skill
- Senior employees:
  - lower obedience
  - higher skill
  - lower overtime willingness

### Definition of Done
- business_sim can provide default agents to engine
- Agents feel distinct in behavior

---

# PHASE B3 — Management Rules

## Goal
Add management gameplay to employee handling

## Tasks

### B3.1 Affinity Rules
- Define affinity range: 0–100
- Affinity affects:
  - obedience
  - effort
  - output quality modifier
  - leave probability

### B3.2 Overtime Rules
- Add overtime penalty to affinity
- Senior employees should resist overtime more

### B3.3 Leave Rules
- If affinity is low, employee may refuse tasks or leave probabilistically

### B3.4 Team Size Rules
- Team size must NOT be fixed
- Add:
  - base team size
  - expansion via progression

### Definition of Done
- Employees can become unstable if badly managed
- Team composition changes over time

---

# PHASE B4 — Task Content System

## Goal
Define the first playable business_sim tasks

## Tasks

### B4.1 Starter Task Templates
- Add at least 5 tasks:
  - write social post
  - rewrite email
  - write product description
  - choose campaign channel
  - suggest pricing idea

### B4.2 Task-to-Industry Mapping
- Map tasks to industries

### B4.3 Real-World Framing
- Ensure tasks are understandable by general users
- Avoid overly technical tasks in MVP

### Definition of Done
- Players can see and run business_sim tasks end-to-end

---

# PHASE B5 — Evaluation Rules

## Goal
Define business_sim-specific scoring logic

## Tasks

### B5.1 Metric Sets
- Content tasks:
  - clarity
  - engagement
  - creativity
- Marketing tasks:
  - attractiveness
  - conversion potential
- Business tasks:
  - feasibility
  - profit potential

### B5.2 Reward Logic
- Compute reward based on:
  - score
  - task difficulty
  - run cost

### B5.3 Profit Logic
- profit = reward - cost

### Definition of Done
- business_sim can score its own outputs via engine evaluation framework

---

# PHASE B6 — Asset Semantics

## Goal
Define what assets mean inside business_sim

## Tasks

### B6.1 Asset Types
- Define business_sim asset types:
  - content
  - strategy
  - product_spec
  - campaign_plan

### B6.2 Output-to-Asset Rules
- Convert task outputs into module-specific assets

### B6.3 Asset Metadata
- Add metadata such as:
  - source_industry
  - quality_level
  - reuse_value

### Definition of Done
- business_sim outputs are meaningful reusable assets

---

# PHASE B7 — Market System

## Goal
Enable asset trading inside business_sim

## Tasks

### B7.1 Listing Rules
- Allow users to list assets for sale

### B7.2 Purchase Rules
- Allow users or system actors to buy assets

### B7.3 Transaction Logic
- Store:
  - buyer
  - seller
  - price
  - asset_id

### B7.4 NPC Buyer
- Add system buyer for MVP
- NPC should buy sufficiently strong assets

### Definition of Done
- Assets can be traded inside business_sim
- Market creates value for better output

---

# PHASE B8 — Multi-Industry Loop

## Goal
Create the core business_sim economic loop

## Tasks

### B8.1 Input/Output Mapping
- Define flow:
  - content asset → marketing usage
  - marketing result → operations/business input

### B8.2 Chained Asset Usage
- Allow one asset to become input for later module tasks

### B8.3 End-to-End Profit Flow
- Build one working loop:
  - content → marketing → business

### Definition of Done
- business_sim has at least one closed economic loop

---

# PHASE B9 — Progression

## Goal
Add long-term progression to business_sim

## Tasks

### B9.1 Employee Growth
- Usage-based growth for employees
- Skill increases slowly over time

### B9.2 Hiring Rules
- Add new employee generation
- Cheap hires = weaker stats
- Expensive hires = stronger stats

### B9.3 Team Expansion
- Increase team size through progression

### Definition of Done
- business_sim supports player growth over multiple sessions

---

# PHASE B10 — Competition / PVP

## Goal
Turn business_sim into a competitive game

## Tasks

### B10.1 Shared Challenges
- Multiple players run the same business task

### B10.2 Ranking Logic
- Rank by:
  - profit
  - score
  - consistency

### B10.3 Asset Competition
- Competing players create rival assets in same category

### B10.4 Social Feedback
- Add simple comments / ratings / comparison view

### Definition of Done
- business_sim supports replayable player competition

---

# MVP CUT LINE

Business Sim MVP =
- B0 Module Setup
- B1 Industry System
- B2 Agent Presets
- B3 Management Rules (minimal)
- B4 Starter Tasks
- B5 Evaluation Rules
- B6 Asset Semantics

---

# V1 CUT LINE

Business Sim V1 =
- MVP
- B7 Market System
- B8 Multi-Industry Loop

---

# PVP CUT LINE

Business Sim Competitive Version =
- V1
- B9 Progression
- B10 Competition / PVP
