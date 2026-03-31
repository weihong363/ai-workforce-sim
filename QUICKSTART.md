# Quickstart

## 1) Setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

## 2) Initialize Storage

```bash
python scripts/bootstrap_storage.py
```

## 3) Start Service

```bash
python -m uvicorn api.app:app --reload
```

Service runs at `http://127.0.0.1:8000`.

## 4) Register User

```bash
curl -X POST http://127.0.0.1:8000/users/register \
  -H 'Content-Type: application/json' \
  -d '{"username":"demo_player"}'
```

## 5) Start Game Session

```bash
curl -X POST http://127.0.0.1:8000/game/start \
  -H 'Content-Type: application/json' \
  -d '{"user_id":"<user_id_from_register>"}'
```

## 6) Get Task Board

```bash
curl "http://127.0.0.1:8000/tasks?user_id=<user_id_from_register>"
```

## 7) Run Tutorial Task

```bash
curl -X POST http://127.0.0.1:8000/run-task \
  -H 'Content-Type: application/json' \
  -d '{
    "task_id":"tsk_tutorial_1_define_the_ta_4e9617a3",
    "user_id":"<user_id_from_register>",
    "instructions":"Provide a clear 3-step launch plan with budget and risks"
  }'
```

Response example:

```json
{"success":true,"run_id":"<id>","status":"success", "...":"..."}
```

## 8) Poll Run Status

```bash
curl http://127.0.0.1:8000/runs/<run_id>
```

Status values:
- `pending`
- `running`
- `completed`
- `failed`

## 9) Optional: Read Asset

```bash
curl http://127.0.0.1:8000/assets/<asset_id>
```

## 10) Optional: Demo Flow Script

```bash
python scripts/demo_playable_flow.py --base-url http://127.0.0.1:8000 --user-id demo_user_001
```

## 11) Switch Provider Mode

Mock mode:

```env
DEFAULT_PROVIDER=mock
PROVIDER_FOR_TASK=mock
PROVIDER_FOR_EVALUATION=mock
```

Real mode (OpenAI-compatible):

```env
DEFAULT_PROVIDER=siliconflow
PROVIDER_FOR_TASK=siliconflow
PROVIDER_FOR_EVALUATION=siliconflow
PROVIDER_SILICONFLOW_BASE_URL=https://api.siliconflow.cn/v1
PROVIDER_SILICONFLOW_API_KEY=your_key
MODEL_TASK_JUNIOR=Qwen/Qwen3-8B
MODEL_TASK_SENIOR=Qwen/Qwen3-32B
MODEL_EVALUATOR=Qwen/Qwen3-14B
```
