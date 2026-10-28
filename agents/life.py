"""
Life（生活 Agent）

职责：管理健康/作息类目标，输出当日生活安排（运动、作息、饮食），并给户外不可用时的替代方案。
输入：生活类目标、昨日作息打卡、今日任务负载。
输出：{"suggestions":[{time_slot,action,minutes}],"note"}
为什么独立：生活建议要考虑节律与负载，和学习辅导、任务拆解的目标函数不同。
"""

from __future__ import annotations

import json
from datetime import date
from typing import Any

import db
from llm import chat_json, pop_meta

SYSTEM_PROMPT = """你是 LifeOS 的生活 Agent（Life）。
基于健康/作息类目标与今日任务负载，给出当日生活安排建议。
要求：
1. suggestions 2-4 条；time_slot 仅 morning|noon|evening。
2. 每条含 action（具体可做）与 minutes（5-60）。
3. 不接天气 API：在 note 中用常识给「天气不佳时的替代方案」（≤60 字）。
4. 今日任务负载高时，建议偏恢复/短时活动；负载低时可加强运动。
5. 只输出 JSON。"""

SCHEMA_HINT = (
    '{"suggestions":[{"time_slot":"morning|noon|evening",'
    '"action":"...","minutes":30}],"note":"≤60字"}'
)


def _fallback() -> dict[str, Any]:
    return {
        "suggestions": [
            {"time_slot": "evening", "action": "23:30 前入睡，睡前远离手机", "minutes": 30}
        ],
        "note": "默认兜底：优先保证睡眠",
    }


def _normalize(data: dict[str, Any]) -> dict[str, Any]:
    slots = {"morning", "noon", "evening"}
    suggestions_in = data.get("suggestions") if isinstance(data.get("suggestions"), list) else []
    suggestions: list[dict[str, Any]] = []
    for s in suggestions_in[:4]:
        if not isinstance(s, dict):
            continue
        slot = s.get("time_slot") if s.get("time_slot") in slots else "evening"
        try:
            minutes = int(s.get("minutes") or 30)
        except (TypeError, ValueError):
            minutes = 30
        minutes = max(5, min(60, minutes))
        action = str(s.get("action") or "").strip()
        if not action:
            continue
        suggestions.append(
            {"time_slot": slot, "action": action[:120], "minutes": minutes}
        )
    if not suggestions:
        return _fallback()
    note = str(data.get("note") or "")[:60]
    return {"suggestions": suggestions, "note": note}


def run(
    life_goals: list[dict[str, Any]] | None = None,
    yesterday_life_checkins: list[dict[str, Any]] | None = None,
    today_task_load_minutes: int = 0,
    today: str | None = None,
) -> dict[str, Any]:
    today = today or date.today().isoformat()
    life_goals = life_goals or []
    yesterday_life_checkins = yesterday_life_checkins or []

    payload = {
        "life_goals": life_goals,
        "yesterday_life_checkins": yesterday_life_checkins,
        "today_task_load_minutes": today_task_load_minutes,
    }
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": "请输出今日生活安排 JSON：\n"
            + json.dumps(payload, ensure_ascii=False),
        },
    ]

    raw = chat_json(messages, SCHEMA_HINT)
    business, meta = pop_meta(raw)
    success = business is not None
    result = _normalize(business) if success else _fallback()

    db.log_agent_run(
        agent_name="life",
        date=today,
        input_summary=f"life_goals={len(life_goals)}, load={today_task_load_minutes}",
        output_summary=json.dumps(result, ensure_ascii=False)[:400],
        latency_ms=int(meta.get("latency_ms") or 0),
        token_estimate=int(meta.get("token_estimate") or 0),
        success=success,
        error_msg="" if success else "生活建议降级为早睡提醒",
    )
    return result
