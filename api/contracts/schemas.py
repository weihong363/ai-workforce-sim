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
    llm_provider: str = Field(..., description="Active provider route")
    llm_model: str = Field(..., description="Default model hint")
    redis_url: str = Field(..., description="Redis connection URL")
    database_initialized: bool = Field(..., description="Whether run storage is initialized")
    user_database_initialized: bool = Field(..., description="Whether user storage is initialized")
    agent_database_initialized: bool = Field(..., description="Whether agent storage is initialized")
    task_catalog_initialized: bool = Field(..., description="Whether task catalog is initialized")
    cache_initialized: bool = Field(..., description="Whether cache client is initialized")


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


class GameStartRequest(BaseModel):
    """Request model for POST /game/start."""
    user_id: str = Field(..., min_length=1, description="Player id")
    username: Optional[str] = Field(None, description="Optional display name; defaults to user_id")


class GameStartResponse(BaseModel):
    """Response model for POST /game/start."""
    user_id: str = Field(..., description="Player id")
    wallet_balance: float = Field(..., description="Current wallet balance")
    workers: List[str] = Field(..., description="Owned worker levels/presets")
    tutorial_completed: bool = Field(..., description="Whether tutorial is completed")
    tasks_completed_count: int = Field(..., description="Completed task runs count")


class BenchmarkRequest(BaseModel):
    """Request model for model benchmark debugging."""

    task_id: str = Field(..., description="Task ID to benchmark")
    agent_level: str = Field("mid", description="Agent level: junior/mid/senior")
    models: List[str] = Field(default_factory=list, description="Candidate model list")


class BenchmarkMatrixRequest(BaseModel):
    """Request model for benchmark matrix runs."""

    class InstructionVariantsInput(BaseModel):
        """Instruction variants for benchmark scenarios."""
        model_config = ConfigDict(extra="forbid")

        vague: Optional[str] = Field(default=None, description="Vague instruction sample")
        clear: Optional[str] = Field(default=None, description="Clear instruction sample")

    class TaskDefinitionOverrideInput(BaseModel):
        """Optional explicit task definition override for debug benchmarks."""
        model_config = ConfigDict(extra="forbid")

        title: Optional[str] = Field(default=None, description="Task title")
        description: Optional[str] = Field(default=None, description="Task description")
        input: Optional[str] = Field(default=None, description="Task input prompt")
        difficulty: Optional[str] = Field(default=None, description="Task difficulty: easy/medium/hard")
        base_reward: Optional[float] = Field(default=None, ge=0, description="Base reward")
        estimated_cost: Optional[float] = Field(default=None, ge=0, description="Estimated cost")
        required_constraints: Optional[List[str]] = Field(default=None, description="Required constraints")
        success_threshold: Optional[float] = Field(default=None, ge=0, le=100, description="Success threshold")
        tutorial_only: Optional[bool] = Field(default=None, description="Tutorial-only flag")
        workflow: Optional[List[str]] = Field(default=None, description="Workflow agent names")
        max_total_tokens: Optional[int] = Field(default=None, ge=1, description="Task token budget")
        tutorial_order: Optional[int] = Field(default=None, ge=1, description="Tutorial order")
        strict_constraints: Optional[bool] = Field(default=None, description="Strict constraint toggle")

    task_id: str = Field(..., description="Task ID to benchmark")
    agent_levels: List[str] = Field(
        default_factory=lambda: ["junior", "mid", "senior"],
        description="Agent levels to benchmark",
    )
    models: List[str] = Field(default_factory=list, description="Model overrides")
    user_instruction_variants: InstructionVariantsInput = Field(
        default_factory=InstructionVariantsInput,
        description="Instruction variants for benchmark scenarios",
    )
    repeats: int = Field(1, ge=1, le=20, description="Repeat count per benchmark configuration")
    task_definition: Optional[TaskDefinitionOverrideInput] = Field(
        default=None,
        description="Optional explicit task definition override for synthetic benchmark tasks",
    )


class DebugTuningPatchRequest(BaseModel):
    """Patch model for runtime gameplay tuning."""

    class AgentTraitWeightsInput(BaseModel):
        """Trait weights used in runtime scoring/effects."""
        model_config = ConfigDict(extra="forbid")

        obedience: Optional[float] = Field(default=None, ge=0, description="Weight for obedience")
        initiative: Optional[float] = Field(default=None, ge=0, description="Weight for initiative")
        effort: Optional[float] = Field(default=None, ge=0, description="Weight for effort")

    class TokenBudgetInput(BaseModel):
        """Token budget multipliers."""
        model_config = ConfigDict(extra="forbid")

        task_multiplier: Optional[float] = Field(default=None, ge=0, description="Task-level token multiplier")
        agent_multiplier: Optional[float] = Field(default=None, ge=0, description="Agent-level token multiplier")

    clarity_penalty_weight: Optional[float] = Field(default=None, ge=0,
                                                    description="Score penalty weight for low clarity")
    constraint_penalty_weight: Optional[float] = Field(default=None, ge=0,
                                                       description="Score penalty weight per missed constraint")
    reward_multiplier: Optional[float] = Field(default=None, ge=0,
                                               description="Reward multiplier for positive adherence bonus")
    agent_trait_weights: Optional[AgentTraitWeightsInput] = Field(
        default=None,
        description="Optional trait weights map",
    )
    artificial_delay_multiplier: Optional[float] = Field(default=None, ge=0,
                                                         description="Multiplier for profile artificial_delay_ms")
    token_budget: Optional[TokenBudgetInput] = Field(
        default=None,
        description="Optional token budget multipliers",
    )
    cost_weight_multiplier: Optional[float] = Field(default=None, ge=0,
                                                    description="Multiplier applied to agent profile cost_weight")


class TuningScanRequest(BaseModel):
    """Request model for simple tuning parameter scan."""

    task_id: str = Field(..., description="Task ID used for scan benchmark runs")
    clarity_penalty_weights: Optional[List[float]] = Field(
        default=None,
        description="Optional candidate values for clarity_penalty_weight",
    )
    constraint_penalty_weights: Optional[List[float]] = Field(
        default=None,
        description="Optional candidate values for constraint_penalty_weight",
    )
    reward_multipliers: Optional[List[float]] = Field(
        default=None,
        description="Optional candidate values for reward_multiplier",
    )
    models: Optional[List[str]] = Field(
        default=None,
        description="Optional model overrides applied during scan",
    )


class TaskManageRequest(BaseModel):
    """Create/upsert task request payload."""
    task_config: "TaskConfigInput" = Field(..., description="Task definition object")
    source: str = Field("manual", description="Task source label")


class TaskUpdateRequest(BaseModel):
    """Update task request payload."""
    task_config: "TaskConfigInput" = Field(..., description="Task definition object")
    source: str = Field("manual", description="Task source label")


class TaskConfigInput(BaseModel):
    """Explicit task definition payload for admin create/update APIs."""
    model_config = ConfigDict(extra="forbid")

    title: str = Field(..., min_length=1, description="Task title")
    description: str = Field(..., min_length=1, description="Task description")
    difficulty: str = Field("easy", description="Task difficulty: easy/medium/hard")
    base_reward: float = Field(0.0, ge=0, description="Base reward when task succeeds")
    estimated_cost: float = Field(0.0, ge=0, description="Estimated execution cost")
    required_constraints: List[str] = Field(default_factory=list, description="Required instruction/output constraints")
    success_threshold: float = Field(72.0, ge=0, le=100, description="Success threshold for effective score")
    tutorial_only: bool = Field(False, description="Whether this is a tutorial-only task")
    workflow: List[str] = Field(
        default_factory=lambda: ["market_analyst", "strategy_writer"],
        description="Ordered agent workflow names",
    )
    max_total_tokens: int = Field(320, ge=1, description="Per-task token budget")
    tutorial_order: int = Field(9999, ge=1, description="Tutorial ordering (lower first)")
    strict_constraints: bool = Field(False, description="Whether to apply strict constraint penalties")


TaskManageRequest.model_rebuild()
TaskUpdateRequest.model_rebuild()


class AgentProfileInput(BaseModel):
    """Explicit agent profile payload for admin APIs."""

    model_config = ConfigDict(extra="forbid")

    description: str = Field("", description="Human-readable agent description")
    level: str = Field("junior", description="Agent level: junior/mid/senior")
    skill: float = Field(0.0, ge=0, description="Skill score")
    overtime_willingness: float = Field(0.0, ge=0, description="Overtime willingness score")
    max_output_tokens: int = Field(0, ge=0, description="Max output tokens")
    cost_weight: float = Field(0.0, ge=0, description="Relative execution cost weight")
    artificial_delay_ms: int = Field(0, ge=0, description="Artificial response delay in milliseconds")
    obedience: float = Field(0.0, ge=0, description="Instruction obedience score")
    initiative: float = Field(0.0, ge=0, description="Initiative/deviation tendency score")
    effort: float = Field(0.0, ge=0, description="Effort/completeness score")
    affinity: float = Field(0.0, ge=0, description="Affinity score")


class AgentCreateRequest(BaseModel):
    """Create agent request payload."""

    model_config = ConfigDict(extra="forbid")

    agent_name: str = Field(..., min_length=1, description="Unique agent name")
    profile: AgentProfileInput = Field(..., description="Agent profile")
    source: str = Field("manual", description="Source label")


class AgentUpdateRequest(BaseModel):
    """Update agent request payload."""

    model_config = ConfigDict(extra="forbid")

    profile: AgentProfileInput = Field(..., description="Agent profile")
    source: str = Field("manual", description="Source label")


class AgentUserBindRequest(BaseModel):
    """Bind one catalog agent to a user."""

    model_config = ConfigDict(extra="forbid")

    agent_name: str = Field(..., min_length=1, description="Catalog agent name to bind")
    status: str = Field("active", description="User-agent status, e.g. active")
