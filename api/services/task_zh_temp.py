"""Temporary Chinese task copy utilities for MVP play page.

This module is intentionally isolated so it can be removed after full i18n.
"""

from __future__ import annotations

import copy
import hashlib
from typing import Dict

from core_engine.task_store import list_tasks as db_list_tasks, upsert_task as db_upsert_task

TEMP_ZH_MODULE_SUFFIX = "_zh_temp"
TEMP_ZH_SOURCE = "seed_zh_temp"

_TITLE_ZH_MAP = {
    "Tutorial 1 - Define the task clearly": "教程 1 - 清晰定义任务",
    "Tutorial 2 - Add constraints and success criteria": "教程 2 - 增加约束与成功标准",
    "Assess a city launch for coffee subscription": "评估咖啡订阅在单城市上线",
    "Assess a B2B lunch catering pilot": "评估 B2B 午餐配餐试点",
    "Hard mode - structured strategy JSON": "困难模式 - 结构化策略 JSON",
}

_PHRASE_ZH_MAP = {
    "target customer": "目标用户",
    "customer segment": "客户细分",
    "pricing": "定价",
    "pricing strategy": "定价策略",
    "risk analysis": "风险分析",
    "risk": "风险",
    "timeline": "时间线",
    "budget": "预算",
    "budget cap": "预算上限",
    "success metric": "成功指标",
    "go/no-go rule": "继续/停止规则",
    "unit economics": "单位经济模型",
    "acquisition channel": "获客渠道",
    "segmentation": "细分策略",
    "prioritization": "优先级排序",
    "json_only": "仅 JSON 输出",
    "include_key:market_size": "包含字段:market_size",
    "include_key:pricing_plan": "包含字段:pricing_plan",
    "include_key:risk_matrix": "包含字段:risk_matrix",
    "include_key:execution_timeline": "包含字段:execution_timeline",
    "include_key:go_no_go": "包含字段:go_no_go",
    "min_numbers:4": "至少 4 个数字假设",
}


def _to_zh_text(text: object) -> str:
    value = str(text or "")
    if not value.strip():
        return value
    if value in _TITLE_ZH_MAP:
        return _TITLE_ZH_MAP[value]
    localized = value
    # High-signal replacements first.
    localized = localized.replace("coffee subscription", "咖啡订阅")
    localized = localized.replace("target customer", "目标用户")
    localized = localized.replace("pricing strategy", "定价策略")
    localized = localized.replace("pricing plan", "定价方案")
    localized = localized.replace("pricing", "定价")
    localized = localized.replace("risk analysis", "风险分析")
    localized = localized.replace("risk", "风险")
    localized = localized.replace("timeline", "时间线")
    localized = localized.replace("budget", "预算")
    localized = localized.replace("success metric", "成功指标")
    localized = localized.replace("go/no-go", "继续/停止")
    localized = localized.replace("pilot", "试点")
    localized = localized.replace("launch", "上线")
    return localized


def _has_cjk(text: str) -> bool:
    return any("\u4e00" <= ch <= "\u9fff" for ch in str(text or ""))


def _to_zh_list(values: object) -> list[str]:
    if not isinstance(values, list):
        return []
    out: list[str] = []
    for item in values:
        token = str(item or "").strip()
        if not token:
            continue
        out.append(_PHRASE_ZH_MAP.get(token, _to_zh_text(token)))
    return out


def _translate_task_config_to_zh(task_config: Dict[str, object], origin_task_id: str) -> Dict[str, object]:
    cfg = copy.deepcopy(dict(task_config or {}))
    origin_title = str(cfg.get("title") or "").strip()
    origin_desc = str(cfg.get("description") or cfg.get("input") or "").strip()
    if "title" in cfg:
        cfg["title"] = _to_zh_text(cfg.get("title"))
    if "description" in cfg:
        cfg["description"] = _to_zh_text(cfg.get("description"))
    if "input" in cfg:
        cfg["input"] = _to_zh_text(cfg.get("input"))
    if "required_constraints" in cfg:
        cfg["required_constraints"] = _to_zh_list(cfg.get("required_constraints"))
    if "constraints" in cfg:
        cfg["constraints"] = _to_zh_list(cfg.get("constraints"))
    translated_title = str(cfg.get("title") or "").strip()
    if (
            not translated_title
            or translated_title.lower().startswith("tsk ")
            or translated_title.lower().startswith("generated task")
    ):
        seed = _to_zh_text(origin_desc or origin_title or origin_task_id)
        cfg["title"] = f"任务：{seed[:24]}"
    if not _has_cjk(str(cfg.get("description") or "")):
        cfg["description"] = _to_zh_text(origin_desc) or f"任务说明：{origin_task_id}"
    cfg["_origin_task_id"] = str(origin_task_id)
    cfg["_lang"] = "zh-CN"
    return cfg


def _zh_task_id_from_origin(origin_task_id: str) -> str:
    digest = hashlib.sha1(str(origin_task_id).encode("utf-8")).hexdigest()[:20]
    return f"tsk_zh_{digest}"


def ensure_zh_task_copies(database_url: str, module_name: str = "business_sim") -> Dict[str, str]:
    """Ensure a 1:1 Chinese copy exists in DB, return {origin_task_id: zh_task_id}."""
    origin_module = str(module_name)
    zh_module = f"{origin_module}{TEMP_ZH_MODULE_SUFFIX}"
    originals = db_list_tasks(database_url, origin_module)
    existing_zh = db_list_tasks(database_url, zh_module)
    by_origin: Dict[str, str] = {}

    for zh_task_id, zh_cfg in existing_zh.items():
        if isinstance(zh_cfg, dict):
            origin = str(zh_cfg.get("_origin_task_id", "")).strip()
            if origin:
                by_origin[origin] = zh_task_id

    for origin_task_id, cfg in originals.items():
        if not isinstance(cfg, dict):
            continue
        zh_task_id = by_origin.get(origin_task_id) or _zh_task_id_from_origin(origin_task_id)
        zh_cfg = _translate_task_config_to_zh(cfg, origin_task_id=origin_task_id)
        zh_cfg["task_id"] = zh_task_id
        db_upsert_task(
            database_url=database_url,
            module_name=zh_module,
            task_id=zh_task_id,
            task_config=zh_cfg,
            source=TEMP_ZH_SOURCE,
        )
        by_origin[origin_task_id] = zh_task_id
    return by_origin


def build_zh_overlay_by_origin(database_url: str, module_name: str = "business_sim") -> Dict[str, Dict[str, object]]:
    """Return {origin_task_id: zh_task_config} for Chinese overlay."""
    ensure_zh_task_copies(database_url=database_url, module_name=module_name)
    zh_module = f"{module_name}{TEMP_ZH_MODULE_SUFFIX}"
    zh_tasks = db_list_tasks(database_url, zh_module)
    overlay: Dict[str, Dict[str, object]] = {}
    for _, cfg in zh_tasks.items():
        if not isinstance(cfg, dict):
            continue
        origin = str(cfg.get("_origin_task_id", "")).strip()
        if not origin:
            continue
        overlay[origin] = cfg
    return overlay
