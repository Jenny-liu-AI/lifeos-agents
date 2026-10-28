"""
Planner（计划 Agent）

职责：把聚焦目标拆成当日可执行任务（具体、可完成、有时长）。
输入：focus 目标详情、本周剩余可用时间、昨日未完成、历史完成情况、plan_mode、每日上限分钟。
输出：{"tasks":[{goal_id,title,detail,est_minutes,priority,type}]}
为什么独立：任务拆解需要专注「可执行性」约束，与调度路由、学习辅导、生活建议分离更稳。
"""

from __future__ import annotations

import json
from datetime import date
from typing import Any

import db
from llm import chat_json, pop_meta

SYSTEM_PROMPT = """你是 LifeOS 的计划 Agent（Planner）。
把长期目标拆成「今天就能做完」的具体任务。
硬约束：
1. 单日任务总数 ≤ 6；单任务 est_minutes ≤ 90；总时长 ≤ daily_available_minutes。
2. 每个聚焦目标 1-3 条任务；title 要具体（动词开头），detail 写清怎么做。
3. priority 仅 high|mid|low；type 仅 study|life（学习类用 study，健康/其他生活用 life）。
4. catch_up 模式优先补昨日未完成；light 模式总任务 ≤ 3 且偏 mid/low。
5. 只输出 JSON。"""

SCHEMA_HINT = (
    '{"tasks":[{"goal_id":1,"title":"...","detail":"...",'
    '"est_minutes":45,"priority":"high|mid|low","type":"study|life"}]}'
)


def _fallback() -> dict[str, Any]:
    return {"tasks": []}


def _clamp_tasks(
    tasks: list[dict[str, Any]],
    available_minutes: int,
    focus_ids: set[int],
) -> list[dict[str, Any]]:
    """按约束裁剪任务列表。"""
    cleaned: list[dict[str, Any]] = []
    total = 0
    for t in tasks:
        if len(cleaned) >= 6:
            break
        try:
            minutes = int(t.get("est_minutes") or 30)
        except (TypeError, ValueError):
            minutes = 30
        minutes = max(5, min(90, minutes))
        if total + minutes > available_minutes and cleaned:
            break
        priority = t.get("priority") if t.get("priority") in ("high", "mid", "low") else "mid"
        typ = t.get("type") if t.get("type") in ("study", "life") else "study"
        gid = t.get("goal_id")
        try:
            gid_int = int(gid) if gid is not None else None
        except (TypeError, ValueError):
            gid_int = None
        if focus_ids and gid_int is not None and gid_int not in focus_ids:
            # 非聚焦目标仍可保留，但优先聚焦；此处不强制丢弃
            pass
        title = str(t.get("title") or "").strip() or "未命名任务"
        cleaned.append(
            {
                "goal_id": gid_int,
                "title": title[:80],
                "detail": str(t.get("detail") or "")[:300],
                "est_minutes": minutes,
                "priority": priority,
                "type": typ,
            }
        )
        total += minutes
    return cleaned


def run(
    focus_goals: list[dict[str, Any]],
    available_minutes: int = 240,
    yesterday_unfinished: list[dict[str, Any]] | None = None,
    history_summary: str = "",
    plan_mode: str = "normal",
    today: str | None = None,
) -> dict[str, Any]:
    today = today or date.today().isoformat()
    yesterday_unfinished = yesterday_unfinished or []
    focus_ids = {int(g["id"]) for g in focus_goals if g.get("id") is not None}

    user_payload = {
        "plan_mode": plan_mode,
        "daily_available_minutes": available_minutes,
        "focus_goals": focus_goals,
        "yesterday_unfinished": yesterday_unfinished,
        "history_summary": history_summary,
    }
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": "请生成今日任务 JSON：\n"
            + json.dumps(user_payload, ensure_ascii=False),
        },
    ]

    raw = chat_json(messages, SCHEMA_HINT)
    business, meta = pop_meta(raw)
    success = isinstance(business, dict) and isinstance(business.get("tasks"), list)
    if success:
        tasks = _clamp_tasks(business["tasks"], available_minutes, focus_ids)
        result = {"tasks": tasks}
        # 若裁剪后为空但仍算成功解析，保留空列表（页面可提示手动添加）
    else:
        result = _fallback()
        success = False

    db.log_agent_run(
        agent_name="planner",
        date=today,
        input_summary=f"mode={plan_mode}, focus={len(focus_goals)}, mins={available_minutes}",
        output_summary=f"tasks={len(result['tasks'])} "
        + json.dumps(result, ensure_ascii=False)[:350],
        latency_ms=int(meta.get("latency_ms") or 0),
        token_estimate=int(meta.get("token_estimate") or 0),
        success=success,
        error_msg="" if success else "计划生成失败，可手动添加任务",
    )
    return result
