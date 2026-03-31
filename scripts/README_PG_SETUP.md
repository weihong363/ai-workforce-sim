# PostgreSQL 配置指南

## 📋 当前配置

已配置的数据库连接信息：

```bash
# .env 文件
DATABASE_URL=postgresql://postgres:difyai123456@localhost:5432/workforce
```

---

## 🔧 启动 PostgreSQL 服务

### macOS + Homebrew

```bash
# 检查 PostgreSQL 状态
brew services list | grep postgresql

# 启动服务
brew services start postgresql

# 或手动启动
/opt/homebrew/opt/postgresql/bin/postgres -D /opt/homebrew/var/postgresql

# 验证服务
psql -U postgres -d dify -c "SELECT version();"
```

### Docker（推荐）

如果本地没有安装 PostgreSQL，可以用 Docker：

```bash
# 使用已有的 dify 数据库容器
docker ps | grep postgres

# 或者启动新的 PostgreSQL 容器
docker run -d \
  --name postgres-workforce \
  -e POSTGRES_PASSWORD=difyai123456 \
  -e POSTGRES_DB=dify \
  -p 5432:5432 \
  postgres:15-alpine

# 等待容器启动
sleep 5

# 验证连接
docker exec -it postgres-workforce psql -U postgres -d dify -c "SELECT version();"
```

---

## 🚀 初始化测试数据

### 方法 1: 自动脚本（推荐）

```bash
# 确保虚拟环境已激活
source venv/bin/activate

# 运行初始化脚本
python scripts/init_pg_test_data.py
```

**预期输出：**
```
📦 Connecting to PostgreSQL...
   Host: localhost:5432
   Database: dify
   User: postgres

✅ Connected to database

📝 Creating tables...
   ✓ runs table
   ✓ workflow_steps table
   ✓ assets table
✅ Tables created successfully

🗑️  Clearing existing test data...
✅ Existing data cleared

📊 Inserting test data...
   ✓ Test run 1: tsk_assess_a_city_launch_for_d9bbd92d (score: 95.5)
   ✓ Test run 2: evaluate_market_expansion (score: 88.0)
   ✓ Test run 3: optimize_pricing_strategy (score: 92.5)

✅ Test data inserted successfully

📊 Verifying data...
   ✓ runs: 3
   ✓ workflow_steps: 6
   ✓ assets: 3

==============================================
✅ Database initialization completed!
==============================================
```

### 方法 2: 手动执行 SQL

```bash
# 连接到数据库
psql -U postgres -d dify

# 创建表
CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY,
    task_name TEXT NOT NULL,
    module_name TEXT NOT NULL,
    final_score REAL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS workflow_steps (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    step_index INTEGER NOT NULL,
    agent_name TEXT NOT NULL,
    prompt TEXT NOT NULL,
    output TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS assets (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    asset_type TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

# 验证表
\dt

# 退出
\q
```

---

## ✅ 验证连接

### 方式 1: 使用 psql

```bash
# 连接测试
psql postgresql://postgres:difyai123456@localhost:5432/workforce -c "SELECT version();"

# 查看表
psql postgresql://postgres:difyai123456@localhost:5432/workforce -c "\dt"

# 查看测试数据
psql postgresql://postgres:difyai123456@localhost:5432/workforce -c "SELECT * FROM runs;"
```

### 方式 2: 使用 Python

```bash
source venv/bin/activate
python -c "
from core_engine.result_store import get_run
run = get_run('test_run_001', 'postgresql://postgres:difyai123456@localhost:5432/workforce')
print(run)
"
```

### 方式 3: 启动 API 测试

```bash
# 启动服务
./start.sh

# 在另一个终端测试
curl http://localhost:8000/health
curl http://localhost:8000/runs/test_run_001
curl http://localhost:8000/assets/asset_001
```

---

## 🔍 查看测试数据

```sql
-- 查看所有 runs
SELECT id, task_name, final_score, status, created_at 
FROM runs 
ORDER BY created_at;

-- 查看特定 run 的详细步骤
SELECT ws.step_index, ws.agent_name, LEFT(ws.output, 100) as output_preview
FROM workflow_steps ws
WHERE ws.run_id = 'test_run_001'
ORDER BY ws.step_index;

-- 查看资产
SELECT a.id, a.asset_type, a.payload_json
FROM assets a
WHERE a.run_id = 'test_run_001';
```

---

## 🎯 测试数据说明

初始化脚本会创建 3 个测试 run：

### Run 1: tsk_assess_a_city_launch_for_d9bbd92d
- **Score**: 95.5
- **Agents**: market_analyst → strategy_writer
- **Asset**: 咖啡订阅商业计划
- **Recommendation**: proceed

### Run 2: evaluate_market_expansion
- **Score**: 88.0
- **Agents**: market_analyst → strategy_writer
- **Asset**: 市场扩张评估
- **Recommendation**: proceed_with_caution

### Run 3: optimize_pricing_strategy
- **Score**: 92.5
- **Agents**: market_analyst → strategy_writer
- **Asset**: 定价优化策略
- **Recommendation**: implement

---

## ❓ 常见问题

### Q1: Connection refused 错误？

**A:** PostgreSQL 服务未启动

```bash
# macOS
brew services start postgresql

# Docker
docker start postgres-workforce
```

### Q2: 权限错误？

**A:** 检查密码和用户名

```bash
# 重置密码（如果需要）
psql -U postgres
ALTER USER postgres WITH PASSWORD 'difyai123456';
\q
```

### Q3: 数据库不存在？

**A:** 创建数据库

```bash
psql -U postgres
CREATE DATABASE dify;
\q
```

### Q4: 如何清空测试数据？

**A:** 重新运行初始化脚本

```bash
python scripts/init_pg_test_data.py
# 会自动先删除现有数据
```

### Q5: 如何切换回 SQLite？

**A:** 修改 .env 文件

```bash
# 注释掉 PostgreSQL
# DATABASE_URL=postgresql://postgres:difyai123456@localhost:5432/workforce

# 启用 SQLite
DATABASE_URL=sqlite:///data/sim_engine.db
```

---

## 📖 下一步

1. ✅ 启动 PostgreSQL 服务
2. ✅ 运行初始化脚本
3. ✅ 验证测试数据
4. ✅ 启动 API 服务
5. ✅ 测试查询端点

---

**总结：** 配置已完成，只需启动 PostgreSQL 并运行初始化脚本即可！
