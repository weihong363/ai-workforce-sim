# 🚀 一、第一版「一周上线 Checklist」

**目标：**
👉 7 天内做出一个可玩的 Demo（不是完美，是能跑 + 有体验）

---

## 🗓️ Day 1 — 项目骨架

**目标：** 能启动服务

- [ ] 初始化 FastAPI 项目
- [ ] 建立基础目录结构
- [ ] 接入 Redis
- [ ] 跑起 Celery worker
- [ ] 建立 `/run-task` API

**👉 验收：**
- [ ] 能发请求 → 返回 `job_id`

---

## 🗓️ Day 2 — Agent 系统（核心）

**目标：** 能跑一个"有缺陷的 AI 员工"

- [ ] 写 Agent schema
- [ ] 实现 `build_prompt()`
- [ ] 封装 LLM 调用
- [ ] 加入 failure injection（必须）

**👉 验收：**
- [ ] 输入任务 → 输出"不完美内容"

---

## 🗓️ Day 3 — Workflow 引擎

**目标：** 多 Agent 协作

- [ ] 实现 workflow runner（顺序执行）
- [ ] 支持 2-3 step pipeline
- [ ] 接入 Celery 异步执行

**👉 验收：**
- [ ] 能跑：`Research → Write → Edit`

---
## 🗓️ Day 4 — 评分系统

**目标：** 让结果"有好坏"

- [ ] 写 evaluation prompt
- [ ] 输出结构化评分
- [ ] 计算 profit（奖励 - cost）

**👉 验收：**
- [ ] 每次运行都有：
  - `score`
  - `profit`

---

## 🗓️ Day 5 — Task 系统（用户入口）

**目标：** 用户能玩

- [ ] 定义 5 个任务（用我给你的 SEED_TASKS）
- [ ] API：
  - `GET /tasks`
  - `POST /run-task`

**👉 验收：**
- [ ] 用户能选任务 → 跑完整流程

---

## 🗓️ Day 6 — Asset 系统（关键）

**目标：** 输出变资产

- [ ] 建立 Asset model
- [ ] 每次任务生成 asset
- [ ] 存 DB

**👉 验收：**
- [ ] 每个任务都有：
  - `content`
  - `score`
  - `price`（简单规则）

---

## 🗓️ Day 7 — 最小闭环（上线点）

**目标：** 形成"游戏感"

- [ ] 加一个简单 leaderboard
- [ ] 输出"对比结果"（好 vs 差）
- [ ] 简单 UI（甚至 CLI 都行）

**👉 验收：**
- [ ] 用户可以：
  - 跑任务
  - 看评分
  - 比结果
  - 想再来一次

---

## 🎯 MVP 完成标准（非常重要）

如果满足这 4 点，就可以上线：

- ✅ 有"失败"的 AI 员工
- ✅ 有评分差异
- ✅ 有收益（profit）
- ✅ 用户会想"再试一次"
