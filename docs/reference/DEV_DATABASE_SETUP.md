# Development Database Setup Guide

## 📋 快速开始

### 1. 复制环境配置模板

```bash
cp .env.example .env
```

### 2. 配置环境变量

编辑 `.env` 文件，推荐配置：

```bash
# 开发环境
APP_ENV=dev

# 使用 SQLite（MVP 推荐）
DATABASE_URL=sqlite:///data/sim_engine.db

# 或使用内存数据库（最快，重启清空）
# DATABASE_URL=sqlite:///:memory:

# Mock LLM 提供商（无需 API key）
USE_MOCK_PROVIDER=true
```

### 3. 启动开发服务器

#### 方式 A: 使用启动脚本（推荐）

```bash
./start_dev.sh
```

#### 方式 B: 手动启动

```bash
# 激活虚拟环境
source venv/bin/activate  # macOS/Linux
# 或
.\venv\Scripts\activate  # Windows

# 安装依赖
pip install -r requirements.txt

# 启动服务器
uvicorn api.app:app --reload --host 0.0.0.0 --port 8000
```

---

## 🗄️ 数据库选项

### SQLite（推荐用于开发和测试）

**优点：**

- ✅ 零配置
- ✅ 单文件存储
- ✅ 无需外部服务
- ✅ Python 内置支持

**配置：**

```bash
# 文件数据库
DATABASE_URL=sqlite:///data/sim_engine.db

# 内存数据库（最快）
DATABASE_URL=sqlite:///:memory:
```

### PostgreSQL（生产环境）

**优点：**

- ✅ 高并发支持
- ✅ 完整 SQL 功能
- ✅ 网络访问
- ✅ 多用户协作

**配置：**

```bash
DATABASE_URL=postgresql://user:password@localhost:5432/workforce_sim
```

**安装 PostgreSQL（macOS）：**

```bash
brew install postgresql
brew services start postgresql
createdb workforce_sim
```

---

## 🧪 测试数据库

### 使用内存数据库运行测试

```bash
# 设置环境变量
export APP_ENV=test
export USE_IN_MEMORY_DB=true

# 运行测试
pytest tests/ -v
```

### 使用独立测试数据库文件

```bash
# .env 文件配置
APP_ENV=test
TEST_DATABASE_URL=sqlite:///data/tests/test.db

# 运行测试
pytest tests/ -v
```

---

## 📊 API 端点测试

### 1. 查看健康状态

```bash
curl http://localhost:8000/health
```

**响应：**

```json
{
  "status": "ok",
  "active_game_module": "business_sim",
  "use_mock_provider": true,
  "redis_url": "redis://localhost:6379/0",
  "database_initialized": true
}
```

### 2. 运行任务（封装后的响应）

```bash
curl -X POST http://localhost:8000/run-task \
  -H "Content-Type: application/json" \
  -d '{
    "task_name": "launch_coffee_subscription",
    "module_name": "business_sim"
  }'
```

**响应（封装对象）：**

```json
{
  "run_id": "abc123...",
  "asset_id": "def456...",
  "status": "completed",
  "final_score": 100.0,
  "message": "Task executed successfully",
  "_links": {
    "run_details": "/runs/abc123...",
    "asset": "/assets/def456..."
  }
}
```

### 3. 查询完整链路

```bash
curl http://localhost:8000/runs/{run_id}
```

**响应：**

```json
{
  "run_id": "abc123...",
  "task_name": "launch_coffee_subscription",
  "module_name": "business_sim",
  "final_score": 100.0,
  "status": "completed",
  "created_at": "2026-03-27T06:11:41.178585+00:00",
  "workflow_steps": [
    {
      "step_index": 0,
      "agent_name": "market_analyst",
      "prompt": "Agent: market_analyst\n...",
      "output": "MOCK_LLM_RESPONSE: ...",
      "created_at": "2026-03-27T06:11:41.178585+00:00"
    },
    {
      "step_index": 1,
      "agent_name": "strategy_writer",
      "prompt": "Agent: strategy_writer\n...",
      "output": "MOCK_LLM_RESPONSE: ...",
      "created_at": "2026-03-27T06:11:41.178585+00:00"
    }
  ],
  "assets": [
    {
      "asset_id": "def456...",
      "asset_type": "business_plan",
      "created_at": "2026-03-27T06:11:41.178585+00:00"
    }
  ]
}
```

### 4. 查询模块化 Asset

```bash
curl http://localhost:8000/assets/{asset_id}
```

**响应：**

```json
{
  "asset_id": "def456...",
  "run_id": "abc123...",
  "asset_type": "business_plan",
  "payload": {
    "summary": "MOCK_LLM_RESPONSE: ...",
    "score": 100.0,
    "steps": ["market_analyst", "strategy_writer"]
  },
  "created_at": "2026-03-27T06:11:41.178585+00:00"
}
```

---

## 🔍 日志查看

### 控制台日志

启动服务器后，会看到结构化日志：

```
[DEV] Using SQLite database at: /path/to/data/sim_engine.db
[DEV] Initializing database schema...
[DEV] Database ready!
[API] Database initialized: sqlite:///path/to/data/sim_engine.db
INFO:     Started server process
INFO:     Waiting for application startup.
INFO:     Application startup complete.
```

### 运行时日志

每次任务执行会输出：

```json
{"event": "run_start", "task_name": "launch_coffee_subscription", "module_name": "business_sim"}
{"event": "module_loaded", "module_name": "business_sim"}
{"event": "workflow_completed", "steps": 2, "agents": ["market_analyst", "strategy_writer"]}
{"event": "evaluation_result", "task_name": "launch_coffee_subscription", "final_score": 100.0}
{"event": "asset_created", "task_name": "launch_coffee_subscription", "asset_type": "business_plan"}
{"event": "run_end", "task_name": "launch_coffee_subscription", "run_id": "abc123...", "asset_id": "def456..."}
```

---

## 🛠️ 常见问题

### Q1: 如何重置数据库？

**SQLite:**

```bash
# 删除数据库文件
rm data/sim_engine.db

# 重启服务器，会自动重建
uvicorn api.app:app --reload
```

**PostgreSQL:**

```bash
# 连接数据库
psql -U postgres -d workforce_sim

# 删除所有表
DROP TABLE IF EXISTS runs, workflow_steps, assets CASCADE;

# 重启服务器重建表
```

### Q2: 如何查看数据库内容？

**SQLite CLI:**

```bash
sqlite3 data/sim_engine.db

# 查看表
.tables

# 查询数据
SELECT * FROM runs ORDER BY created_at DESC LIMIT 5;
SELECT * FROM workflow_steps WHERE run_id = 'abc123';
SELECT id, asset_type FROM assets;
```

**PostgreSQL:**

```bash
psql -U postgres -d workforce_sim

# 查看表
\dt

# 查询数据
SELECT * FROM runs ORDER BY created_at DESC LIMIT 5;
```

### Q3: 并发测试失败怎么办？

SQLite 不支持高并发写入，建议：

1. **减少并发请求数**
2. **切换到内存数据库**（测试时）
   ```bash
   export DATABASE_URL=sqlite:///:memory:
   ```
3. **使用 PostgreSQL**（生产环境）

### Q4: 如何切换到不同的数据库？

修改 `.env` 文件中的 `DATABASE_URL`：

```bash
# SQLite 文件
DATABASE_URL=sqlite:///data/sim_engine.db

# SQLite 内存
DATABASE_URL=sqlite:///:memory:

# PostgreSQL
DATABASE_URL=postgresql://user:pass@localhost:5432/dbname
```

重启服务器即可生效。

---

## 📈 性能基准

| 数据库类型      | 单次请求  | 并发能力 | 适用场景      |
|------------|-------|------|-----------|
| SQLite 内存  | ~5ms  | 低    | 单元测试、快速原型 |
| SQLite 文件  | ~10ms | 中    | 开发测试、Demo |
| PostgreSQL | ~15ms | 高    | 生产环境      |

---

## ✅ 检查清单

- [x] 复制 `.env.example` 到 `.env`
- [x] 配置 `DATABASE_URL`
- [x] 配置 `APP_ENV`
- [x] 运行 `./start_dev.sh` 或手动启动
- [x] 访问 http://localhost:8000/docs 查看 API 文档
- [x] 测试 `/health` 端点
- [x] 测试 `/run-task` 端点（查看封装响应）
- [x] 测试 `/runs/{id}` 端点（查看完整链路）
- [x] 测试 `/assets/{id}` 端点（查看模块化 asset）

---

## 🎯 下一步

1. **运行 smoke test 验证端到端流程**
   ```bash
   pytest tests/test_mvp_smoke.py -v
   ```

2. **查看 API 文档**
   ```
   http://localhost:8000/docs
   ```

3. **尝试不同的数据库配置**
    - 内存数据库（最快）
    - 文件数据库（持久化）
    - PostgreSQL（生产）

---

**总结：** 现在系统已完全集成开发数据库，支持多种数据库后端，返回对象已封装为结构化格式！
