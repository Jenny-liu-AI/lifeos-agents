"""
Reviewer（复盘 Agent）

职责：基于本周真实打卡数据做复盘，必须引用具体数字，禁止空泛鸡汤。
输入：本周每日计划 vs 完成、完成率、未完成清单、目标截止日。
输出：{"completion_rate","highlights","problems","next_week_adjustments","motivation"}
为什么独立：复盘是周期校验，与日常路由/排程解耦，避免「边计划边美化结果」。
"""

from __future__ import annotations

import json
from datetime import date
from typing import Any

import db
from llm import chat_json, pop_meta

SYSTEM_PROMPT = """你是 LifeOS 的复盘 Agent（Reviewer）。
基于本周真实数据做复盘，必须引用具体数字作为 evidence，禁止空泛表述。
要求：
1. completion_rate 为 0-1 小数，应与输入统计一致或极其接近。
2. highlights 1-3 条；problems 1-3 条，每条必须含 desc / root_cause / evidence。
3. next_week_adjustments 2-4 条可执行调整；motivation ≤40 字。
4. 只输出 JSON。"""

SCHEMA_HINT = (
    '{"completion_rate":0.72,"highlights":["..."],'
    '"problems":[{"desc":"...","root_cause":"...","evidence":"..."}],'
    '"next_week_adjustments":["..."],"motivation":"≤40字"}'
)


def _fallback(completion_rate: float) -> dict[str, Any]:
    return {
        "completion_rate": round(completion_rate, 2),
        "highlights": [],
        "problems": [
            {
                "desc": "复盘生成失败，仅保留完成率",
                "root_cause": "模型输出无法解析",
                "evidence": f"本周完成率={completion_rate:.0%}",
            }
        ],
        "next_week_adjustments": ["下周先手工回顾未完成任务再生成计划"],
        "motivation": "数据还在，下周继续。",
    }


def _normalize(data: dict[str, Any], fallback_rate: float) -> dict[str, Any]:
    try:
        rate = float(data.get("completion_rate", fallback_rate))
    except (TypeError, ValueError):
        rate = fallback_rate
    rate = max(0.0, min(1.0, rate))

    highlights = data.get("highlights") if isinstance(data.get("highlights"), list) else []
    highlights = [str(h)[:120] for h in highlights][:3]

    problems_in = data.get("problems") if isinstance(data.get("problems"), list) else []
    problems: list[dict[str, str]] = []
    for p in problems_in[:3]:
        if not isinstance(p, dict):
            continue
        problems.append(
            {
                "desc": str(p.get("desc") or "")[:120],
                "root_cause": str(p.get("root_cause") or "")[:120],
                "evidence": str(p.get("evidence") or "")[:160],
            }
        )
    if not problems:
        problems = _fallback(rate)["problems"]

    adjusts = data.get("next_week_adjustments")
    if not isinstance(adjusts, list):
        adjusts = []
    adjusts = [str(a)[:120] for a in adjusts][:4] or _fallback(rate)["next_week_adjustments"]
    motivation = str(data.get("motivation") or "")[:40] or "按数据微调，比感觉更可靠。"

    return {
        "completion_rate": round(rate, 2),
        "highlights": highlights,
        "problems": problems,
        "next_week_adjustments": adjusts,
        "motivation": motivation,
    }


def run(
    week_start: str,
    week_stats: dict[str, Any],
    unfinished_tasks: list[dict[str, Any]] | None = None,
    goals: list[dict[str, Any]] | None = None,
    today: str | None = None,
) -> dict[str, Any]:
    """
    week_stats 建议含：
      total_tasks, done_tasks, partial_tasks, skipped_tasks,
      completion_rate, daily_breakdown
    """
    today = today or date.today().isoformat()
    unfinished_tasks = unfinished_tasks or []
    goals = goals or []
    fallback_rate = float(week_stats.get("completion_rate") or 0.0)

    payload = {
        "week_start": week_start,
        "week_stats": week_stats,
        "unfinished_tasks": unfinished_tasks[:30],
        "goals": [
            {
                "id": g.get("id"),
                "title": g.get("title"),
                "target_date": g.get("target_date"),
                "domain": g.get("domain"),
            }
            for g in goals
        ],
    }
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": "请基于真实数据输出本周复盘 JSON：\n"
            + json.dumps(payload, ensure_ascii=False),
        },
    ]

    raw = chat_json(messages, SCHEMA_HINT)
    business, meta = pop_meta(raw)
    success = business is not None
    result = _normalize(business, fallback_rate) if success else _fallback(fallback_rate)

    db.log_agent_run(
        agent_name="reviewer",
        date=today,
        input_summary=f"week={week_start}, rate={fallback_rate:.2f}, unfinished={len(unfinished_tasks)}",
        output_summary=json.dumps(result, ensure_ascii=False)[:450],
        latency_ms=int(meta.get("latency_ms") or 0),
        token_estimate=int(meta.get("token_estimate") or 0),
        success=success,
        error_msg="" if success else "复盘解析失败，仅输出完成率与提示",
    )
    return result
