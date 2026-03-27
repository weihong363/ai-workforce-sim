# Local Test Database Setup Guide

## 📊 本地测试数据库选型建议

### 推荐方案：SQLite (MVP 阶段)

**配置文件位置：** `core_engine/config.py`

```python
def get_settings() -> Settings:
    return Settings(
        active_game_module=os.getenv("ACTIVE_GAME_MODULE", "business_sim"),
        use_mock_provider=_to_bool(os.getenv("USE_MOCK_PROVIDER"), default=True),
        database_url=os.getenv("DATABASE_URL", "sqlite:///data/sim_engine.db"),
        redis_url=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
    )
```

---

## 🎯 方案对比

| 方案 | 优点 | 缺点 | 适用场景 |
|------|------|------|----------|
| **SQLite** | ✅ 零配置<br>✅ 单文件<br>✅ 无需服务<br>✅ Python 内置支持 | ❌ 并发写入受限<br>❌ 不支持网络访问 | **开发测试 MVP**<br>本地调试<br>单元测试 |
| **PostgreSQL** | ✅ 高并发<br>✅ 完整 SQL 支持<br>✅ 可扩展性强 | ❌ 需要安装服务<br>❌ 配置复杂<br>❌ 占用资源多 | 生产环境<br>多用户并发测试 |
| **DuckDB** | ✅ 分析型查询快<br>✅ 单文件<br>✅ 列式存储 | ❌ 生态较小<br>❌ 事务支持弱 | 数据分析场景<br>批量处理 |

---

## 🚀 快速开始（SQLite）

### 1. 环境变量配置

**创建 `.env` 文件（项目根目录）：**

```bash
# 使用 SQLite 本地测试
DATABASE_URL=sqlite:///data/sim_engine.db

# 可选：切换到 PostgreSQL
# DATABASE_URL=postgresql://user:password@localhost:5432/workforce_sim

ACTIVE_GAME_MODULE=business_sim
USE_MOCK_PROVIDER=true
REDIS_URL=redis://localhost:6379/0
```

### 2. 目录结构

```
ai-workforce-sim/
├── data/
│   ├── sim_engine.db          # SQLite 数据库文件（自动生成）
│   └── runs/                   # JSON 备份（兼容旧版）
│       └── *.json
├── api/
│   ├── app.py
│   └── run_task.py
└── core_engine/
    ├── result_store.py         # 持久化逻辑
    └── config.py               # 配置加载
```

### 3. 初始化数据库

**自动初始化：** API 启动时自动执行

```python
# api/app.py:L22-25
@app.on_event("startup")
def startup() -> None:
    settings = get_settings()
    init_db(settings.database_url)  # 自动创建表
```

**手动初始化（可选）：**

```bash
# 创建初始化脚本 scripts/init_db.py
from core_engine.result_store import init_db
from core_engine.config import get_settings

settings = get_settings()
init_db(settings.database_url)
print(f"Database initialized at: {settings.database_url}")
```

---

## 🧪 测试验证

### Smoke Test

```bash
# 运行测试
pytest tests/test_mvp_smoke.py -v

# 或手动运行完整链路
python api/run_task.py launch_coffee_subscription
```

**预期输出：**
```json
{
  "run_id": "02fdf64c728043769bcab8763ef252c3",
  "asset_id": "abc123...",
  "status": "completed",
  "final_score": 100.0,
  "_links": {
    "run_details": "/runs/02fdf64c728043769bcab8763ef252c3",
    "asset": "/assets/abc123..."
  }
}
```

### 查询测试

```bash
# 查询 run 详情
curl http://localhost:8000/runs/02fdf64c728043769bcab8763ef252c3

# 查询 asset
curl http://localhost:8000/assets/abc123...
```

**预期响应（GET /runs/{id}）：**
```json
{
  "run_id": "02fdf64c728043769bcab8763ef252c3",
  "task_name": "launch_coffee_subscription",
  "module_name": "business_sim",
  "final_score": 100.0,
  "status": "completed",
  "created_at": "2026-03-27T06:11:41.178585+00:00",
  "workflow_steps": [
    {
      "step_index": 0,
      "agent_name": "market_analyst",
      "prompt": "Agent: market_analyst\nTask Input: ...",
      "output": "MOCK_LLM_RESPONSE: Agent: market_analyst",
      "created_at": "2026-03-27T06:11:41.178585+00:00"
    },
    {
      "step_index": 1,
      "agent_name": "strategy_writer",
      "prompt": "Agent: strategy_writer\nTask Input: ...",
      "output": "MOCK_LLM_RESPONSE: Agent: strategy_writer",
      "created_at": "2026-03-27T06:11:41.178585+00:00"
    }
  ],
  "assets": [
    {
      "asset_id": "abc123...",
      "asset_type": "business_plan",
      "created_at": "2026-03-27T06:11:41.178585+00:00"
    }
  ]
}
```

---

## 📝 日志查看

**结构化日志输出示例：**

```bash
# 启动 API 服务
uvicorn api.app:app --reload

# 日志输出
{"event": "run_start", "task_name": "launch_coffee_subscription", "module_name": "business_sim"}
{"event": "module_loaded", "module_name": "business_sim"}
{"event": "workflow_completed", "steps": 2, "agents": ["market_analyst", "strategy_writer"]}
{"event": "evaluation_result", "task_name": "launch_coffee_subscription", "final_score": 100.0}
{"event": "asset_created", "task_name": "launch_coffee_subscription", "asset_type": "business_plan"}
{"event": "run_end", "task_name": "launch_coffee_subscription", "module_name": "business_sim", "run_id": "02fdf64c...", "asset_id": "abc123..."}
```

**日志文件（可选）：**

```python
# 修改 logging_utils.py 添加文件输出
import logging
from logging.handlers import RotatingFileHandler

def setup_logging(log_file: str = "logs/sim_engine.log") -> logging.Logger:
    logger = logging.getLogger(LOGGER_NAME)
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        
        # 控制台处理器
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(console_handler)
        
        # 文件处理器（带轮转）
        Path("logs").mkdir(exist_ok=True)
        file_handler = RotatingFileHandler(log_file, maxBytes=10*1024*1024, backupCount=5)
        file_handler.setFormatter(logging.Formatter(
            "%(asctime)s - %(levelname)s - %(message)s"
        ))
        logger.addHandler(file_handler)
    
    return logger
```

---

## 🔄 切换到 PostgreSQL（未来扩展）

### 1. 安装依赖

```bash
pip install psycopg2-binary
```

### 2. 配置环境变量

```bash
DATABASE_URL=postgresql://postgres:password@localhost:5432/workforce_sim
```

### 3. 创建数据库

```sql
CREATE DATABASE workforce_sim;
CREATE USER sim_user WITH PASSWORD 'your_password';
GRANT ALL PRIVILEGES ON DATABASE workforce_sim TO sim_user;
```

### 4. 修改 result_store.py（可选）

当前代码已抽象，**无需修改**。`_connect()` 函数会根据 URL 自动适配。

---

## ⚠️ 常见问题

### Q1: SQLite 文件在哪里？
**A:** `data/sim_engine.db`（相对于项目根目录）

### Q2: 如何清空数据库重新测试？
**A:** 
```bash
# 删除 SQLite 文件
rm data/sim_engine.db

# 重启 API，会自动重建表
uvicorn api.app:app --reload
```

### Q3: 如何查看数据库内容？
**A:** 
```bash
# 使用 SQLite CLI
sqlite3 data/sim_engine.db

# 查看表
.tables

# 查询 runs
SELECT * FROM runs ORDER BY created_at DESC LIMIT 5;

# 查询 workflow_steps
SELECT run_id, step_index, agent_name, output FROM workflow_steps;

# 查询 assets
SELECT id, asset_type, payload_json FROM assets;
```

### Q4: 并发测试失败怎么办？
**A:** SQLite 不支持高并发写入，建议：
- 减少并发请求数
- 切换到 PostgreSQL
- 使用不同的 run_id 避免锁竞争

---

## 📊 性能基准（SQLite）

| 操作 | 耗时 | 备注 |
|------|------|------|
| 单次 run_task | ~50-200ms | Mock LLM |
| persist_result | ~5-10ms | SQLite INSERT |
| get_run | ~2-5ms | SELECT + JOIN |
| get_asset | ~1-3ms | 简单查询 |

**并发限制：**
- 同时写入：~10 req/s（会出现 SQLITE_BUSY）
- 同时读取：~100 req/s
- 适合：开发测试、Demo 演示
- 不适合：生产环境高并发场景

---

## ✅ 检查清单

- [x] SQLite 配置正确
- [x] 数据库表自动创建
- [x] persist_result 调用包含 database_url
- [x] POST /run-task 返回精简结构
- [x] GET /runs/{id} 可查询完整链路
- [x] GET /assets/{id} 可查询模块化 asset
- [x] 日志系统已集成
- [ ] （可选）日志文件输出
- [ ] （可选）PostgreSQL 切换测试

---

## 🎯 下一步建议

1. **运行 smoke test 验证端到端流程**
   ```bash
   pytest tests/test_mvp_smoke.py -v
   ```

2. **添加更多测试用例**
   - 多任务并发测试
   - 错误处理测试
   - Asset 查询测试

3. **性能优化（可选）**
   - 添加数据库连接池
   - 添加 Redis 缓存层
   - 批量插入优化

4. **监控与可观测性**
   - Prometheus 指标导出
   - Grafana 仪表盘
   - 慢查询日志

---

**总结：** MVP 阶段使用 SQLite 是最佳选择，零配置、快速验证核心功能。等需要支持多用户并发时再考虑切换到 PostgreSQL。
