import inspect

from core_engine import user_store


def test_user_store_exposes_event_projection_api() -> None:
    assert callable(getattr(user_store, "append_user_event", None))
    assert callable(getattr(user_store, "get_user_projection", None))
    assert callable(getattr(user_store, "list_user_events", None))


def test_user_store_has_no_eval_usage() -> None:
    source = inspect.getsource(user_store)
    assert "eval(" not in source
