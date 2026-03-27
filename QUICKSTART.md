# Quick Start

## 🚀 快速开始（5 分钟）

### 1. 一键安装

```bash
# 赋予执行权限
chmod +x setup.sh start.sh

# 运行安装脚本
./setup.sh
```

这会自动：
- ✅ 创建虚拟环境（`venv/`）
- ✅ 安装所有依赖
- ✅ 创建配置文件
- ✅ 创建必要目录

### 2. 启动服务

```bash
./start.sh
```

### 3. 访问 API

打开浏览器访问：
- **API 文档**: http://localhost:8000/docs
- **健康检查**: http://localhost:8000/health

---

## 📦 手动安装（可选）

如果自动脚本不工作：

```bash
# 1. 创建虚拟环境
python3 -m venv venv

# 2. 激活虚拟环境
source venv/bin/activate

# 3. 安装依赖
pip install -r requirements.txt

# 4. 复制配置
cp .env.example .env

# 5. 启动服务
uvicorn api.app:app --reload
```

---

## 🧪 运行测试

```bash
# 确保虚拟环境已激活
source venv/bin/activate

# 运行 smoke test
pytest tests/test_mvp_smoke.py -v

# 运行 e2e test
pytest tests/test_mvp_e2e.py -v
```

---

## 🔧 常用命令

### 激活虚拟环境
```bash
source venv/bin/activate
```

### 退出虚拟环境
```bash
deactivate
```

### 重启服务
```bash
# 停止：Ctrl+C
# 重新启动
./start.sh
```

### 查看日志
```bash
# 服务日志会直接输出到终端
# 按 Ctrl+C 停止服务查看历史
```

### 清理数据（重新开始）
```bash
rm -rf data/*.db
./start.sh  # 会自动重建数据库
```

---

## ☁️ 部署到云端

这个项目已经为云端部署做好准备：

### Docker（推荐）

创建 `Dockerfile`：
```dockerfile
FROM python:3.11-slim

WORKDIR /app

# 复制依赖文件
COPY requirements.txt .

# 安装依赖
RUN pip install --no-cache-dir -r requirements.txt

# 复制代码
COPY . .

# 暴露端口
EXPOSE 8000

# 启动命令
CMD ["uvicorn", "api.app:app", "--host", "0.0.0.0", "--port", "8000"]
```

构建和运行：
```bash
docker build -t workforce-sim .
docker run -p 8000:8000 workforce-sim
```

### Heroku

创建 `Procfile`：
```
web: uvicorn api.app:app --host 0.0.0.0 --port $PORT
```

部署：
```bash
heroku create workforce-sim
git push heroku main
```

### Railway / Render

这些平台会自动检测 Python 项目：
1. 连接 GitHub 仓库
2. 自动安装 `requirements.txt`
3. 设置启动命令：`uvicorn api.app:app --host 0.0.0.0 --port $PORT`

---

## 🎯 验证安装

```bash
# 1. 健康检查
curl http://localhost:8000/health

# 2. 运行任务
curl -X POST http://localhost:8000/run-task \
  -H "Content-Type: application/json" \
  -d '{"task_name": "launch_coffee_subscription"}'

# 3. 查询结果（替换 {run_id}）
curl http://localhost:8000/runs/{run_id}
```

---

## ❓ 常见问题

### Q: 权限错误？
**A:** 不要使用 sudo，用虚拟环境：
```bash
source venv/bin/activate
```

### Q: 端口被占用？
**A:** 修改端口：
```bash
uvicorn api.app:app --reload --port 8001
```

### Q: 依赖安装失败？
**A:** 升级 pip：
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### Q: 如何重置环境？
**A:** 删除并重建虚拟环境：
```bash
rm -rf venv
./setup.sh
```

---

## 📖 下一步

- 查看 [AGENTS.md](AGENTS.md) 了解系统架构
- 查看 [PROMPTS.md](PROMPTS.md) 了解 Agent 配置
- 查看 [LOCAL_DB_SETUP.md](LOCAL_DB_SETUP.md) 了解数据库配置
