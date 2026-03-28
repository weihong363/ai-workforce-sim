# Quickstart

## 1) Start Service (one command)

```bash
python -m uvicorn api.app:app --reload
```

Service runs at `http://127.0.0.1:8000`.

## 2) Submit Task (one request example)

```bash
curl -X POST http://127.0.0.1:8000/run-task \
  -H 'Content-Type: application/json' \
  -d '{
    "task_name":"launch_coffee_subscription",
    "module_name":"business_sim",
    "user_id":"demo_user_001",
    "instructions":"Provide a clear 3-step launch plan with budget and risks"
  }'
```

Response example:

```json
{"run_id":"<id>","status":"pending"}
```

## 3) Poll Run Status

```bash
curl http://127.0.0.1:8000/runs/<run_id>
```

Status values:
- `pending`
- `running`
- `completed`
- `failed`

## 4) Optional: Read Asset

```bash
curl http://127.0.0.1:8000/assets/<asset_id>
```

## 5) Switch Provider Mode

Mock mode:

```env
DEFAULT_PROVIDER=mock
PROVIDER_FOR_TASK=mock
PROVIDER_FOR_EVALUATION=mock
```

Real mode (OpenAI-compatible):

```env
DEFAULT_PROVIDER=siliconflow
PROVIDER_SILICONFLOW_BASE_URL=https://api.siliconflow.cn/v1
PROVIDER_SILICONFLOW_API_KEY=your_key
MODEL_TASK_JUNIOR=Qwen/Qwen3-8B
MODEL_TASK_SENIOR=Qwen/Qwen3-32B
MODEL_EVALUATOR=Qwen/Qwen3-14B
```
