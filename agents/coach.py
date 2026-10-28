"""
Coach（学习 Agent）

职责：针对学习类任务给出材料结构（读什么/练什么/怎么检验），并可出题自测。
输入：任务标题、目标描述、用户当前水平自述。
输出：{"brief","steps","quiz":[{q,options,answer}]}
为什么独立：学习辅导需要教学法与测验结构，和生活建议、任务排程不是同一技能面。
"""

from __future__ import annotations

import json
from datetime import date
from typing import Any

import db
from llm import chat_json, pop_meta

SYSTEM_PROMPT = """你是 LifeOS 的学习教练 Agent（Coach）。
针对一条学习任务，给出精炼学习要点、可执行步骤、以及 3 道四选一自测题。
要求：
1. brief ≤150 字；steps 3-5 条，每条可在 10-20 分钟内完成。
2. quiz 固定 3 题；options 长度 4；answer 为正确选项下标 0-3。
3. 题目紧扣本次任务，难度匹配用户自述水平。
4. 只输出 JSON。"""

SCHEMA_HINT = (
    '{"brief":"≤150字","steps":["..."],'
    '"quiz":[{"q":"...","options":["A","B","C","D"],"answer":0}]}'
)


def _fallback(task_title: str) -> dict[str, Any]:
    return {
        "brief": task_title or "请先明确学习主题后再开始",
        "steps": ["打开学习材料", "做 20 分钟练习", "用一句话总结收获"],
        "quiz": [],
    }


def _normalize(data: dict[str, Any], task_title: str) -> dict[str, Any]:
    brief = str(data.get("brief") or task_title)[:150]
    steps = data.get("steps") if isinstance(data.get("steps"), list) else []
    steps = [str(s)[:120] for s in steps][:5] or _fallback(task_title)["steps"]
    quiz_in = data.get("quiz") if isinstance(data.get("quiz"), list) else []
    quiz: list[dict[str, Any]] = []
    for item in quiz_in[:3]:
        if not isinstance(item, dict):
            continue
        opts = item.get("options") if isinstance(item.get("options"), list) else []
        opts = [str(o)[:80] for o in opts][:4]
        while len(opts) < 4:
            opts.append("（选项缺失）")
        try:
            ans = int(item.get("answer", 0))
        except (TypeError, ValueError):
            ans = 0
        ans = max(0, min(3, ans))
        quiz.append({"q": str(item.get("q") or "")[:200], "options": opts, "answer": ans})
    return {"brief": brief, "steps": steps, "quiz": quiz}


def run(
    task_title: str,
    goal_description: str = "",
    user_level: str = "初学者",
    today: str | None = None,
) -> dict[str, Any]:
    today = today or date.today().isoformat()
    payload = {
        "task_title": task_title,
        "goal_description": goal_description,
        "user_level": user_level,
    }
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": "请为以下学习任务输出辅导 JSON：\n"
            + json.dumps(payload, ensure_ascii=False),
        },
    ]

    raw = chat_json(messages, SCHEMA_HINT)
    business, meta = pop_meta(raw)
    success = business is not None
    result = _normalize(business, task_title) if success else _fallback(task_title)

    db.log_agent_run(
        agent_name="coach",
        date=today,
        input_summary=f"task={task_title[:60]}, level={user_level}",
        output_summary=json.dumps(
            {"brief": result["brief"], "steps": len(result["steps"]), "quiz": len(result["quiz"])},
            ensure_ascii=False,
        ),
        latency_ms=int(meta.get("latency_ms") or 0),
        token_estimate=int(meta.get("token_estimate") or 0),
        success=success,
        error_msg="" if success else "学习辅导降级为标题要点",
    )
    return result
