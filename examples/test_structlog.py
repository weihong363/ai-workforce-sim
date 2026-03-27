#!/usr/bin/env python3
"""Demo script to showcase structlog features."""

from core_engine.logging_utils import setup_logging, get_logger, log_event


def demo_basic_logging():
    """Demonstrate basic logging with JSON format."""
    print("=" * 60)
    print("1. Basic Logging (JSON Format)")
    print("=" * 60)
    
    logger = get_logger(__name__)
    logger.info("Application started")
    logger.debug("Debug information")
    logger.warning("Warning message")
    logger.error("Error occurred")
    print()


def demo_structured_logging():
    """Demonstrate structured logging with key-value pairs."""
    print("=" * 60)
    print("2. Structured Logging")
    print("=" * 60)
    
    logger = get_logger(__name__)
    logger.info(
        "User action",
        user_id="12345",
        action="create_task",
        task_name="coffee_launch",
        duration_ms=150
    )
    
    logger.info(
        "Agent execution",
        agent_name="market_analyst",
        tokens_used=256,
        cost_usd=0.00128,
        cache_hit=False
    )
    print()


def demo_log_event():
    """Demonstrate log_event helper for business events."""
    print("=" * 60)
    print("3. Business Events with log_event")
    print("=" * 60)
    
    logger = get_logger(__name__)
    log_event(logger, "run_start", task_name="launch_product", module_name="business_sim")
    log_event(logger, "workflow_step_complete", step_index=0, agent_name="analyst")
    log_event(logger, "workflow_step_complete", step_index=1, agent_name="writer")
    log_event(logger, "evaluation_complete", final_score=95.5, cache_hit=False)
    log_event(logger, "asset_created", asset_id="abc123", asset_type="business_plan")
    log_event(logger, "run_end", status="success", total_cost=0.00512)
    print()


def demo_console_format():
    """Demonstrate human-readable console format."""
    print("=" * 60)
    print("4. Console Format (Human-Readable)")
    print("=" * 60)
    
    # Reconfigure for console output
    setup_logging(json_format=False)
    logger = get_logger(__name__)
    
    logger.info("This is human-readable format")
    logger.warning("Warnings are highlighted")
    logger.error("Errors stand out")
    print()


def demo_file_logging():
    """Demonstrate file logging with rotation."""
    print("=" * 60)
    print("5. File Logging (logs/demo.log)")
    print("=" * 60)
    
    # Reconfigure with file output
    setup_logging(log_file="logs/demo.log", json_format=True)
    logger = get_logger(__name__)
    
    logger.info("This goes to both console and file", destination="dual")
    log_event(logger, "file_demo", message="Check logs/demo.log")
    
    print("\n📄 Check logs/demo.log for persisted logs")
    print()


if __name__ == "__main__":
    print("\n🚀 Structlog Demo - AI Workforce Simulation\n")
    
    # Initialize with default JSON format
    setup_logging(level="INFO")
    
    demo_basic_logging()
    demo_structured_logging()
    demo_log_event()
    demo_console_format()
    demo_file_logging()
    
    print("=" * 60)
    print("✅ Demo Complete!")
    print("=" * 60)
    print("\nKey Features:")
    print("  • Structured JSON logs for production")
    print("  • Human-readable console format for development")
    print("  • File logging with automatic rotation")
    print("  • Business event tracking with log_event")
    print("  • Ready for OpenTelemetry integration (future)")
    print()
