"""Run execution and result retrieval endpoints."""

from fastapi import APIRouter, HTTPException, Path

from api.run_task import get_runtime_run, run_task
from api.schemas import ErrorResponse, RunTaskRequest
from api.services.run_preview import with_output_previews
from api.services.run_task_response import build_failed_run_task_response, build_run_task_user_response
from core_engine.config import get_settings
from core_engine.errors import ExecutionError
from core_engine.module_loader import ModuleLoadError
from core_engine.result_store import get_asset, get_run

router = APIRouter(tags=["runs"])


@router.post(
    "/run-task",
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    summary="Run Task",
    description="Execute one gameplay task for a user and return a frontend-friendly result payload.",
)
def run_task_route(request: RunTaskRequest) -> dict:
    settings = get_settings()
    try:
        selected_module = settings.active_game_module
        result = run_task(
            task_id=request.task_id,
            module_name=selected_module,
            user_id=request.user_id,
            instructions=request.instructions,
            selected_agent_name=request.agent_name,
        )
        return build_run_task_user_response(result)
    except (ValueError, ModuleLoadError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ExecutionError as exc:
        if exc.code in {
            "task_locked",
            "insufficient_wallet",
            "invalid_model_output",
            "evaluation_failed",
            "parsing_failed",
            "provider_call_failed",
            "timeout",
            "invalid_agent_selection",
        }:
            return build_failed_run_task_response(exc)
        raise HTTPException(status_code=500, detail=exc.to_dict()) from exc


@router.get(
    "/runs/{run_id}",
    responses={404: {"model": ErrorResponse}},
    summary="Get Run",
    description="Get run status/details. Returns partial runtime state while run is pending/running.",
)
def get_run_route(run_id: str = Path(..., min_length=1, description="Run ID")) -> dict:
    settings = get_settings()
    try:
        runtime = get_runtime_run(run_id)
        run = get_run(run_id, settings.database_url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if run is None and runtime is None:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found.")

    if run is None:
        return runtime

    if runtime is not None and runtime.get("status") in {"pending", "running"}:
        merged = dict(run)
        merged["status"] = runtime.get("status", run.get("status"))
        merged["workflow_steps"] = runtime.get("workflow_steps", run.get("workflow_steps", []))
        merged["total_cost"] = runtime.get("total_cost", run.get("total_cost", 0.0))
        return with_output_previews(merged)

    if runtime is not None and runtime.get("result"):
        merged = dict(run)
        runtime_result = runtime.get("result", {})
        if isinstance(runtime_result, dict):
            for key in ("player_result", "score_breakdown", "penalties", "effective_parameters", "semantic_analysis"):
                if key in runtime_result:
                    merged[key] = runtime_result[key]
        return with_output_previews(merged)

    return with_output_previews(run)


@router.get(
    "/assets/{asset_id}",
    responses={404: {"model": ErrorResponse}},
    summary="Get Asset",
    description="Fetch one generated asset by asset ID.",
)
def get_asset_route(asset_id: str = Path(..., min_length=1, description="Asset ID")) -> dict:
    settings = get_settings()
    try:
        asset = get_asset(asset_id, settings.database_url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if asset is None:
        raise HTTPException(status_code=404, detail=f"Asset '{asset_id}' not found.")
    return asset
