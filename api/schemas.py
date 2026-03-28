"""API schemas for request/response models."""

from typing import List, Optional

from pydantic import BaseModel, Field, ConfigDict


class RunTaskRequest(BaseModel):
    """Request model for /run-task endpoint."""
    task_id: str = Field(..., description="Task ID to execute")
    user_id: str = Field(..., min_length=1, description="Player id for progression flow (required)")
    instructions: Optional[str] = Field(None, description="Player instruction text for this task")


class RunTaskResponse(BaseModel):
    """Encapsulated response for /run-task endpoint."""
    
    model_config = ConfigDict(populate_by_name=True, extra="forbid")
    
    class Links(BaseModel):
        """Hypermedia links to related resources."""
        model_config = ConfigDict(extra="forbid")
        
        run_details: str = Field(..., description="URL to fetch full run details")
        asset: str = Field(..., description="URL to fetch asset details")
    
    run_id: str = Field(..., description="Unique identifier for this run")
    asset_id: str = Field(..., description="Unique identifier for the generated asset")
    status: str = Field(..., description="Execution status (completed/failed)")
    final_score: float = Field(..., description="Evaluation score from 0-100")
    message: Optional[str] = Field(None, description="Optional status message")
    links: Links = Field(..., alias="_links", description="Related resource links")


class ErrorResponse(BaseModel):
    """Standard error response format."""
    model_config = ConfigDict(extra="forbid")
    
    detail: str = Field(..., description="Error description")
    error_type: Optional[str] = Field(None, description="Type of error")


class HealthResponse(BaseModel):
    """Response model for /health endpoint."""
    status: str = Field(..., description="Health status")
    active_game_module: str = Field(..., description="Currently active game module")
    use_mock_provider: bool = Field(..., description="Whether mock LLM provider is enabled")
    redis_url: str = Field(..., description="Redis connection URL")
    database_initialized: bool = Field(..., description="Whether database is initialized")


class RunDetailResponse(BaseModel):
    """Response model for /runs/{run_id} endpoint."""
    model_config = ConfigDict(extra="allow")
    
    run_id: str = Field(..., description="Unique run identifier")
    task_id: str = Field(..., description="Task ID")
    module_name: str = Field(..., description="Module name")
    final_score: float = Field(..., description="Final evaluation score")
    status: str = Field(..., description="Run status")
    created_at: str = Field(..., description="Creation timestamp in ISO format")
    workflow_steps: list = Field(..., description="List of workflow step details")
    assets: list = Field(..., description="List of associated assets")


class AssetDetailResponse(BaseModel):
    """Response model for /assets/{asset_id} endpoint."""
    model_config = ConfigDict(extra="allow")
    
    asset_id: str = Field(..., description="Unique asset identifier")
    run_id: str = Field(..., description="Associated run ID")
    asset_type: str = Field(..., description="Type of asset")
    payload: dict = Field(..., description="Asset payload data")
    created_at: str = Field(..., description="Creation timestamp in ISO format")


class RegisterUserRequest(BaseModel):
    """Request model for user registration."""
    username: str = Field(..., min_length=3, max_length=50, description="Username (3-50 characters)")


class RegisterUserResponse(BaseModel):
    """Response model for user registration."""
    user_id: str = Field(..., description="Generated unique user ID")
    username: str = Field(..., description="Registered username")
    wallet_balance: float = Field(..., description="Initial wallet balance")
    created_at: str = Field(..., description="Registration timestamp")


class CheckUsernameResponse(BaseModel):
    """Response model for username availability check."""
    username: str = Field(..., description="Checked username")
    available: bool = Field(..., description="True if username is available")


class BenchmarkRequest(BaseModel):
    """Request model for model benchmark debugging."""

    task_id: str = Field(..., description="Task ID to benchmark")
    agent_level: str = Field("mid", description="Agent level: junior/mid/senior")
    models: List[str] = Field(..., min_length=1, description="Candidate model list")
