"""Helpers for stable user-facing run_task responses."""

from __future__ import annotations

from core_engine.errors import ExecutionError


def _normalize_lang(lang: str) -> str:
    value = str(lang or "").strip().lower()
    return "zh" if value.startswith("zh") else "en"


_TEMP_ZH_TEXT: dict[str, str] = {
    "success": "成功",
    "failed": "失败",
    "Task Completed": "任务完成",
    "Almost There": "接近成功",
    "Task Failed": "任务失败",
    "Good work!": "做得很好！",
    "Almost there!": "差一点就成功了！",
    "Needs improvement.": "还需要改进。",
    "Run failed.": "执行失败。",
    "Task succeeded.": "任务成功。",
    "Task failed.": "任务失败。",
    "Fix the key issue and retry. Every run is a learning signal.": "先修复关键问题再重试。每次执行都是一次学习信号。",
    "Clear instructions made the difference.": "清晰的指令直接提升了结果质量。",
    "Your structure is solid; one more missing point can push this over the line.": "你的结构已经不错，再补一个缺失点就可能过线。",
    "Specific instructions usually convert into higher scores and rewards.": "更具体的指令通常会带来更高分和更高奖励。",
    "Tightening key constraints is the fastest way to improve outcomes.": "补齐关键约束是提升结果最快的方法。",
    "You are close. Add the missing required point and retry.": "你已经很接近了，补上缺失要点后再试一次。",
    "You are missing a pricing strategy.": "你缺少定价策略。",
    "You are missing a risk analysis.": "你缺少风险分析。",
    "You are missing a clear target customer.": "你缺少清晰的目标用户。",
    "You are missing a clear timeline.": "你缺少明确的时间线。",
    "Great improvement": "进步明显",
    "Good clarity": "指令清晰度较好",
    "empty output": "模型输出为空",
    "insufficient balance": "余额不足",
    "parsing failure": "解析失败",
    "provider/evaluation failure": "模型或评估失败",
}


def _localize_text_to_zh(text: str) -> str:
    value = str(text or "").strip()
    if not value:
        return value
    mapped = _TEMP_ZH_TEXT.get(value)
    if mapped:
        return mapped
    lowered = value.lower()
    if "missing target customer" in lowered:
        return "缺少目标用户定义。"
    if "missing pricing" in lowered:
        return "缺少定价策略。"
    if "missing risk" in lowered:
        return "缺少风险分析。"
    if "missing milestones" in lowered or "missing timeline" in lowered:
        return "缺少明确时间线。"
    if "missing budget" in lowered:
        return "缺少预算信息。"
    if "instruction too vague" in lowered:
        return "指令过于模糊。"
    if "too few required constraint hits" in lowered:
        return "关键约束命中不足。"
    if "poor agent-task fit" in lowered:
        return "员工与任务匹配度偏低。"
    if "almost success" in lowered:
        return "接近成功。"
    if "output quality is below the task requirement" in lowered:
        return "输出质量未达到任务要求。"
    if "retry with clearer and more specific instructions" in lowered:
        return "请用更清晰、更具体的指令重试。"
    if "retry with shorter prompt scope" in lowered:
        return "请缩小提示范围后重试，或稍后再试。"
    if "choose a lower-cost task" in lowered:
        return "请选择更低成本任务，或先提升钱包余额。"
    if "add concrete target customer" in lowered:
        return "请补充明确的目标用户、预算、时间线和可衡量目标。"
    if "add a clear target customer segment" in lowered:
        return "请补充清晰的目标用户画像（是谁、在哪里、为什么需要）。"
    if "add a pricing plan" in lowered:
        return "请补充至少一个具体价格和套餐方案。"
    if "add a simple risk section" in lowered:
        return "请补充风险部分，并给每项风险添加对应缓解措施。"
    if "add a timeline" in lowered:
        return "请补充含 2-3 个里程碑和预期日期的时间线。"
    if "add a budget cap" in lowered:
        return "请补充预算上限和粗略支出拆分。"
    if "explicitly include all required constraints" in lowered:
        return "请在指令中显式覆盖所有必需约束。"
    if "keep your structure" in lowered:
        return "保持当前结构，并显式补齐缺失的 1-2 个约束点。"
    if "retry with clearer instructions and explicit expected format" in lowered:
        return "请用更清晰的指令并明确期望输出格式后重试。"
    if "clear audience targeting made the plan stronger" in lowered:
        return "清晰的目标用户定义显著增强了方案质量。"
    if "followed instructions with a clear structure" in lowered:
        return "你按清晰结构完成了指令执行。"
    if "covered required point" in lowered:
        return value.replace("Covered required point:", "覆盖了必需要点：")
    if "great improvement:" in lowered and "points vs last attempt" in lowered:
        return value.replace("Great improvement:", "进步明显：").replace("points vs last attempt.", "分（相较上次）")
    return value


def _localize_list_to_zh(items: list[str]) -> list[str]:
    return [_localize_text_to_zh(str(item)) for item in (items or [])]


def _localize_payload(payload: dict, lang: str) -> dict:
    if _normalize_lang(lang) != "zh":
        return payload
    out = dict(payload or {})
    for key in (
            "status", "headline", "message", "summary", "insight", "hint",
            "missing_focus", "retry_suggestion", "improvement_message",
    ):
        if isinstance(out.get(key), str):
            out[key] = _localize_text_to_zh(str(out[key]))
    for key in ("what_you_did_well", "what_you_got_right", "failure_reasons"):
        if isinstance(out.get(key), list):
            out[key] = _localize_list_to_zh(out[key])
    feedback = out.get("feedback")
    if isinstance(feedback, dict):
        issues = feedback.get("issues")
        suggestions = feedback.get("suggestions")
        if isinstance(issues, list):
            feedback["issues"] = _localize_list_to_zh(issues)
        if isinstance(suggestions, list):
            feedback["suggestions"] = _localize_list_to_zh(suggestions)
        out["feedback"] = feedback
    out["lang"] = "zh-CN"
    return out


def _friendly_issue_text(issue: str) -> str:
    text = str(issue or "").strip().lower()
    if "missing target customer" in text:
        return "You did not specify who this plan is for."
    if "missing pricing" in text:
        return "You did not include a pricing strategy."
    if "missing risk" in text:
        return "You did not include a risk analysis."
    if "missing milestones" in text or "missing timeline" in text:
        return "You did not provide a clear timeline."
    if "missing budget" in text:
        return "You did not include a budget."
    if "instruction too vague" in text or "very low clarity score" in text:
        return "Your instructions are too vague. Be more specific about goals and constraints."
    if "too few required constraint hits" in text:
        return "You missed several required task points."
    if "poor agent-task fit" in text:
        return "This task is a bit mismatched for your current setup."
    if "almost success" in text:
        return "Almost there. You only missed one or two key points."
    return str(issue).strip()


def _well_done_message_from_constraint(token: str) -> str:
    text = str(token or "").strip().lower()
    if "target customer" in text or "customer segment" in text:
        return "Clearly defined target customer"
    if "pricing" in text:
        return "Provided pricing strategy"
    if "risk" in text:
        return "Included risk analysis"
    if "timeline" in text or "milestone" in text:
        return "Provided clear timeline"
    if "budget" in text:
        return "Included budget planning"
    return f"Covered required point: {token}"


def suggestions_from_issues(issues: list[str]) -> list[str]:
    suggestions: list[str] = []
    for issue in issues:
        text = str(issue).lower()
        if "vague" in text:
            suggestions.append("Add concrete target customer, budget, timeline, and measurable goals.")
        elif "missing target customer" in text:
            suggestions.append(
                "Add a clear target customer segment (who they are, where they are, and why they need this).")
        elif "missing pricing" in text:
            suggestions.append("Add a pricing plan with at least one concrete price and package option.")
        elif "missing risk" in text:
            suggestions.append("Add a simple risk section with top risks and one mitigation per risk.")
        elif "missing milestones" in text or "missing timeline" in text:
            suggestions.append("Add a timeline with 2-3 milestones and expected dates.")
        elif "missing budget" in text:
            suggestions.append("Add a budget cap and a rough spending breakdown.")
        elif "constraint" in text or "missing" in text:
            suggestions.append("Explicitly include all required constraints in your instruction.")
        elif "almost success" in text:
            suggestions.append("Keep your structure, then explicitly cover the missing 1-2 constraints.")
        elif "timeout" in text:
            suggestions.append("Retry with shorter prompt scope or after checking provider latency.")
        elif "insufficient wallet" in text:
            suggestions.append("Choose a lower-cost task or increase wallet balance before retrying.")
        elif "output" in text:
            suggestions.append("Retry with clearer instructions and explicit expected format.")
    if not suggestions:
        suggestions.append("Retry with clearer and more specific instructions.")
    deduped: list[str] = []
    seen = set()
    for item in suggestions:
        if item not in seen:
            seen.add(item)
            deduped.append(item)
    return deduped[:3]


def _compact_failure_reasons(issues: list[str]) -> list[str]:
    deduped: list[str] = []
    seen = set()
    for issue in issues:
        text = str(issue or "").strip()
        if not text:
            continue
        if text not in seen:
            seen.add(text)
            deduped.append(text)
    return deduped[:3]


def _derive_success_reinforcement(result: dict) -> list[str]:
    semantic = result.get("semantic_analysis", {}) if isinstance(result, dict) else {}
    matches = semantic.get("constraint_matches", {}) if isinstance(semantic, dict) else {}
    matched = list(matches.get("matched", [])) if isinstance(matches, dict) else []
    output: list[str] = []
    for item in matched:
        msg = _well_done_message_from_constraint(str(item))
        if msg not in output:
            output.append(msg)
        if len(output) >= 3:
            break
    if not output:
        output.append("Followed instructions with a clear structure")
    return output[:3]


def _extract_agent_outputs(result: dict) -> list[dict]:
    workflow = result.get("workflow_results", []) if isinstance(result, dict) else []
    outputs: list[dict] = []
    if not isinstance(workflow, list):
        return outputs
    for idx, step in enumerate(workflow):
        if not isinstance(step, dict):
            continue
        outputs.append(
            {
                "step_index": int(step.get("step_index", idx)),
                "agent_name": str(step.get("agent_name", f"agent_{idx + 1}")),
                "output": str(step.get("raw_output", step.get("output", ""))),
            }
        )
    return outputs


def _extract_cost_breakdown(result: dict, charged_cost: float) -> dict:
    workflow = result.get("workflow_results", []) if isinstance(result, dict) else []
    if not isinstance(workflow, list):
        workflow = []
    fixed_cost = round(
        sum(float(step.get("fixed_agent_cost", 0.0) or 0.0) for step in workflow if isinstance(step, dict)),
        8,
    )
    step_total = round(
        sum(float(step.get("cost", 0.0) or 0.0) for step in workflow if isinstance(step, dict)),
        8,
    )
    model_cost = round(max(0.0, step_total - fixed_cost), 8)
    total_cost = round(float(charged_cost or step_total), 8)
    return {
        "model_cost": model_cost,
        "agent_cost": fixed_cost,
        "total_cost": total_cost,
    }


def _build_near_miss_hint(friendly_issues: list[str]) -> str:
    for item in friendly_issues:
        text = str(item).lower()
        if "pricing" in text:
            return "You are missing a pricing strategy."
        if "risk" in text:
            return "You are missing a risk analysis."
        if "target customer" in text or "plan is for" in text:
            return "You are missing a clear target customer."
        if "timeline" in text:
            return "You are missing a clear timeline."
    return "You are close. Add the missing required point and retry."


def _derive_short_insight(success: bool, near_miss: bool, issues: list[str], well: list[str]) -> str:
    if success:
        if any("target customer" in str(item).lower() for item in well):
            return "Clear audience targeting made the plan stronger."
        return "Clear instructions made the difference."
    if near_miss:
        return "Your structure is solid; one more missing point can push this over the line."
    if any("vague" in str(item).lower() for item in issues):
        return "Specific instructions usually convert into higher scores and rewards."
    return "Tightening key constraints is the fastest way to improve outcomes."


def build_run_task_user_response(result: dict, lang: str = "en") -> dict:
    player_result = result.get("player_result", {}) if isinstance(result, dict) else {}
    player_feedback = result.get("player_feedback", {}) if isinstance(result, dict) else {}
    issues = list(player_feedback.get("failure_reasons", []) or [])
    near_miss = bool(player_result.get("near_miss", False))
    if near_miss and "almost success" not in [str(x).lower() for x in issues]:
        issues.insert(0, "almost success")
    issues = [_friendly_issue_text(item) for item in _compact_failure_reasons(issues)]
    success = bool(player_result.get("success", False))
    if not success and not issues:
        issues = ["The output quality is below the task requirement."]
    summary = str(player_result.get("explanation") or ("Task succeeded." if success else "Task failed."))
    current_score = float(result.get("evaluation", {}).get("final_score", 0.0) or 0.0)
    previous_score = (
        float(player_result["previous_score"])
        if isinstance(player_result.get("previous_score"), (int, float))
        else None
    )
    score_delta = (
        float(player_result["score_delta"])
        if isinstance(player_result.get("score_delta"), (int, float))
        else None
    )
    what_you_did_well = _derive_success_reinforcement(result) if success else []
    message = "Good work!" if success else ("Almost there!" if near_miss else "Needs improvement.")
    headline = "Task Completed" if success else ("Almost There" if near_miss else "Task Failed")
    insight = _derive_short_insight(success=success, near_miss=near_miss, issues=issues, well=what_you_did_well)
    retry_suggestion = _build_near_miss_hint(issues) if near_miss else (
        suggestions_from_issues(issues)[0] if not success and suggestions_from_issues(issues) else None
    )
    improvement_message = (
        f"Great improvement: +{score_delta:.1f} points vs last attempt."
        if isinstance(score_delta, (int, float)) and score_delta > 0
        else None
    )
    semantic = result.get("semantic_analysis", {}) if isinstance(result, dict) else {}
    matches = semantic.get("constraint_matches", {}) if isinstance(semantic, dict) else {}
    matched = list(matches.get("matched", [])) if isinstance(matches, dict) else []
    what_you_got_right = [_well_done_message_from_constraint(str(item)) for item in matched[:3]]
    missing_focus = issues[0] if issues else None
    agent_outputs = _extract_agent_outputs(result)
    final_agent_output = agent_outputs[-1]["output"] if agent_outputs else ""

    charged_cost = float(player_result.get("cost_spent", result.get("total_cost", 0.0)) or 0.0)
    cost_breakdown = _extract_cost_breakdown(result, charged_cost=charged_cost)

    payload = {
        "success": success,
        "headline": headline,
        "run_id": str(result.get("storage", {}).get("run_id", "")),
        "score": current_score,
        "current_score": current_score,
        "reward": float(player_result.get("reward_gained", 0.0) or 0.0),
        "cost": charged_cost,
        "cost_breakdown": cost_breakdown,
        "previous_score": previous_score,
        "score_delta": score_delta,
        "delta": score_delta,
        "score_comparison": {
            "previous_score": previous_score,
            "current_score": current_score,
            "delta": score_delta,
        },
        "wallet_before": float(player_result.get("wallet_before", 0.0) or 0.0),
        "wallet_after": float(player_result.get("wallet_after", 0.0) or 0.0),
        "net_result": float(player_result.get("net_result", 0.0) or 0.0),
        "status": "success" if success else "failed",
        "near_miss": near_miss,
        "message": message,
        "summary": summary,
        "insight": insight,
        "improvement_message": improvement_message,
        "what_you_did_well": what_you_did_well,
        "what_you_got_right": what_you_got_right[:3],
        "missing_focus": missing_focus,
        "retry_suggestion": retry_suggestion,
        "agent_outputs": agent_outputs,
        "agent_output_full": final_agent_output,
        "failure_reasons": issues,
        "hint": _build_near_miss_hint(issues) if near_miss else None,
        "feedback": {
            "issues": issues,
            "suggestions": suggestions_from_issues(issues),
        },
    }
    return _localize_payload(payload, lang)


def build_failed_run_task_response(exc: ExecutionError, lang: str = "en") -> dict:
    details = dict(exc.details or {})
    run_id = str(details.get("run_id", ""))
    summary = str(exc.message or "Run failed.")
    if str(exc.code or "") == "insufficient_wallet":
        issues = ["insufficient balance"]
    elif str(exc.code or "") == "parsing_failed":
        issues = ["parsing failure"]
    elif str(exc.code or "") in {"evaluation_failed", "provider_call_failed"}:
        issues = ["provider/evaluation failure"]
    elif str(exc.code or "") == "invalid_model_output":
        issues = ["empty output"]
    else:
        issues = [summary]
    issues = [_friendly_issue_text(item) for item in _compact_failure_reasons(issues)]
    available_balance = float(details.get("available_balance", 0.0) or 0.0)
    payload = {
        "success": False,
        "headline": "Task Failed",
        "run_id": run_id,
        "score": 0.0,
        "current_score": 0.0,
        "previous_score": None,
        "score_delta": None,
        "delta": None,
        "score_comparison": {"previous_score": None, "current_score": 0.0, "delta": None},
        "reward": 0.0,
        "cost": 0.0,
        "wallet_before": available_balance,
        "wallet_after": available_balance,
        "net_result": 0.0,
        "status": "failed",
        "near_miss": False,
        "message": "Run failed.",
        "summary": summary,
        "insight": "Fix the key issue and retry. Every run is a learning signal.",
        "improvement_message": None,
        "error_reason": str(exc.code or "run_failed"),
        "failure_reasons": issues,
        "what_you_did_well": [],
        "what_you_got_right": [],
        "missing_focus": issues[0] if issues else None,
        "retry_suggestion": suggestions_from_issues([str(exc.code or ""), summary])[0],
        "hint": None,
        "feedback": {
            "issues": issues,
            "suggestions": suggestions_from_issues([str(exc.code or ""), summary]),
        },
    }
    return _localize_payload(payload, lang)
