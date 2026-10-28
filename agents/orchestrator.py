"""
Orchestrator（调度 Agent / 主控）

职责：读取目标与近 7 天执行情况，决定今日 plan_mode 以及调用哪些专职 Agent。
输入：目标列表摘要、近期打卡统计、星期几、可用时长（分钟）。
输出：{"date","plan_mode","agents_to_call","reason","focus_goal_ids"}
为什么独立：路由决策与任务生成/复盘解耦，避免「计划 Agent」既定方向又写任务导致偏见。
"""

from __future__ import annotations

import json
from datetime import date
from typing import Any

import db
from llm import chat_json, pop_meta

SYSTEM_PROMPT = """你是 LifeOS 的调度 Agent（Orchestrator）。
根据用户长期目标与近一周执行情况，决定今天的计划模式与要调用的专职 Agent。
规则：
1. plan_mode：normal=正常；catch_up=欠账较多需追赶；light=负载高或周末宜减量。
2. agents_to_call 只能从 planner / coach / life 中选，至少包含 planner。
3. 有学习类目标且今日要推进时加入 coach；有健康/作息类目标时加入 life。
4. focus_goal_ids 选今日应聚焦的目标 id（可多选），reason ≤60 字。
5. 只输出 JSON，不要解释。"""

SCHEMA_HINT = (
    '{"date":"YYYY-MM-DD","plan_mode":"normal|catch_up|light",'
    '"agents_to_call":["planner","life"],"reason":"≤60字",'
    '"focus_goal_ids":[1,2]}'
)


def _fallback(today: str, goals: list[dict[str, Any]]) -> dict[str, Any]:
    """解析失败兜底：调用 planner+life，聚焦全部活跃目标。"""
    ids = [int(g["id"]) for g in goals]
    agents = ["planner", "life"]
    if any(g.get("domain") == "学习" for g in goals):
        agents = ["planner", "coach", "life"]
    return {
        "date": today,
        "plan_mode": "normal",
        "agents_to_call": agents,
        "reason": "调度解析失败，已降级为默认路由",
        "focus_goal_ids": ids,
    }


def run(
    goals: list[dict[str, Any]] | None = None,
    recent_stats: dict[str, Any] | None = None,
    weekday: int | None = None,
    available_minutes: int = 240,
    today: str | None = None,
) -> dict[str, Any]:
    """
    执行调度决策并写入 agent_runs。
    weekday: 0=周一 … 6=周日；缺省用今天。
    """
    today = today or date.today().isoformat()
    goals = goals if goals is not None else db.list_goals()
    if weekday is None:
        weekday = date.fromisoformat(today).weekday()
    recent_stats = recent_stats or {}

    user_payload = {
        "date": today,
        "weekday": weekday,  # 0=周一
        "available_minutes": available_minutes,
        "goals": [
            {
                "id": g["id"],
                "title": g["title"],
                "domain": g["domain"],
                "weekly_hours": g["weekly_hours"],
                "target_date": g.get("target_date"),
            }
            for g in goals
        ],
        "recent_stats": recent_stats,
    }
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": "请根据以下上下文输出今日调度 JSON：\n"
            + json.dumps(user_payload, ensure_ascii=False),
        },
    ]

    raw = chat_json(messages, SCHEMA_HINT)
    business, meta = pop_meta(raw)
    success = business is not None
    result = business if success else _fallback(today, goals)

    # 字段纠偏
    result.setdefault("date", today)
    if result.get("plan_mode") not in ("normal", "catch_up", "light"):
        result["plan_mode"] = "normal"
    allowed = {"planner", "coach", "life"}
    called = [a for a in (result.get("agents_to_call") or []) if a in allowed]
    if "planner" not in called:
        called.insert(0, "planner")
    result["agents_to_call"] = called
    if not isinstance(result.get("focus_goal_ids"), list) or not result["focus_goal_ids"]:
        result["focus_goal_ids"] = [int(g["id"]) for g in goals]
    result["reason"] = str(result.get("reason") or "")[:60]

    db.log_agent_run(
        agent_name="orchestrator",
        date=today,
        input_summary=f"goals={len(goals)}, weekday={weekday}, mins={available_minutes}",
        output_summary=json.dumps(result, ensure_ascii=False)[:400],
        latency_ms=int(meta.get("latency_ms") or 0),
        token_estimate=int(meta.get("token_estimate") or 0),
        success=success,
        error_msg="" if success else "JSON解析失败，已用兜底",
    )
    return result
