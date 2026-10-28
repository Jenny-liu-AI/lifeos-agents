"""
每日多 Agent 流水线：Orchestrator 路由 → Planner/Coach/Life 并行 → 结果入库。

协作结构（主控路由 + 专职执行 + 周期校验）：
- 本模块负责前两段；Reviewer 由周复盘入口单独触发。
"""

from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta
from typing import Any

import db
from agents import coach, life, orchestrator, planner


def get_available_minutes() -> int:
    try:
        return max(30, int(os.getenv("DAILY_AVAILABLE_MINUTES", "240")))
    except ValueError:
        return 240


def collect_recent_stats(today: str, days: int = 7) -> dict[str, Any]:
    """近 N 天任务完成概况，供 Orchestrator 决策。"""
    end = date.fromisoformat(today)
    start = (end - timedelta(days=days - 1)).isoformat()
    tasks = db.list_tasks_between(start, today)
    total = len(tasks)
    done = sum(1 for t in tasks if t.get("status") == "done")
    partial = sum(1 for t in tasks if t.get("status") == "partial")
    skipped = sum(1 for t in tasks if t.get("status") == "skipped")
    pending = sum(1 for t in tasks if t.get("status") == "pending")
    rate = (done / total) if total else 0.0
    return {
        "window_start": start,
        "window_end": today,
        "total_tasks": total,
        "done": done,
        "partial": partial,
        "skipped": skipped,
        "pending": pending,
        "completion_rate": round(rate, 2),
    }


def _yesterday_unfinished(today: str) -> list[dict[str, Any]]:
    yday = (date.fromisoformat(today) - timedelta(days=1)).isoformat()
    return [
        t
        for t in db.list_tasks_by_date(yday)
        if t.get("status") in ("pending", "partial", "skipped")
    ]


def _focus_goals(
    goals: list[dict[str, Any]], focus_ids: list[Any]
) -> list[dict[str, Any]]:
    id_set = {int(x) for x in focus_ids}
    focused = [g for g in goals if int(g["id"]) in id_set]
    return focused or goals


def run_daily_pipeline(
    today: str | None = None,
    available_minutes: int | None = None,
    replace_tasks: bool = True,
) -> dict[str, Any]:
    """
    跑通一日：调度 → 并行专职 Agent → 写入 daily_plans / tasks。
    任何异常都吞掉并返回带 error 字段的结果，保证页面不中断。
    """
    today = today or date.today().isoformat()
    available_minutes = available_minutes or get_available_minutes()
    result: dict[str, Any] = {
        "ok": True,
        "date": today,
        "decision": None,
        "tasks": [],
        "coach": None,
        "life": None,
        "plan_id": None,
        "message": "",
        "error": "",
    }

    try:
        goals = db.list_goals()
        if not goals:
            result["ok"] = False
            result["message"] = "尚无活跃目标，请先在「目标」页创建"
            return result

        stats = collect_recent_stats(today)
        decision = orchestrator.run(
            goals=goals,
            recent_stats=stats,
            weekday=date.fromisoformat(today).weekday(),
            available_minutes=available_minutes,
            today=today,
        )
        result["decision"] = decision

        focus = _focus_goals(goals, decision.get("focus_goal_ids") or [])
        agents_to_call = set(decision.get("agents_to_call") or ["planner"])
        unfinished = _yesterday_unfinished(today)
        history = (
            f"近7天完成率{stats['completion_rate']:.0%}，"
            f"完成{stats['done']}/总{stats['total_tasks']}"
        )
        life_goals = [g for g in goals if g.get("domain") in ("健康", "其他")]
        study_goal = next((g for g in focus if g.get("domain") == "学习"), None)
        # 并行前用「可用时长」粗估负载；Life 与 Planner 同时跑时还不知道最终任务总时长
        estimated_load = available_minutes if decision.get("plan_mode") != "light" else available_minutes // 2

        futures = {}
        with ThreadPoolExecutor(max_workers=3) as pool:
            if "planner" in agents_to_call:
                futures[pool.submit(
                    planner.run,
                    focus_goals=focus,
                    available_minutes=available_minutes,
                    yesterday_unfinished=unfinished,
                    history_summary=history,
                    plan_mode=decision.get("plan_mode", "normal"),
                    today=today,
                )] = "planner"
            if "coach" in agents_to_call and study_goal:
                futures[pool.submit(
                    coach.run,
                    task_title=f"推进目标：{study_goal['title']}",
                    goal_description=study_goal.get("description") or "",
                    user_level="按目标自行把握",
                    today=today,
                )] = "coach"
            if "life" in agents_to_call:
                futures[pool.submit(
                    life.run,
                    life_goals=life_goals or focus,
                    yesterday_life_checkins=[],
                    today_task_load_minutes=estimated_load,
                    today=today,
                )] = "life"

            outputs: dict[str, Any] = {}
            for fut in as_completed(futures):
                name = futures[fut]
                try:
                    outputs[name] = fut.result()
                except Exception as e:  # noqa: BLE001
                    outputs[name] = {"_error": f"{type(e).__name__}: {e}"}

        plan_out = outputs.get("planner") or {"tasks": []}
        tasks = plan_out.get("tasks") if isinstance(plan_out, dict) else []
        if not isinstance(tasks, list):
            tasks = []
        result["coach"] = outputs.get("coach")
        result["life"] = outputs.get("life")

        # 汇总写入：orchestrator_json 含决策 + coach/life 摘要
        bundle = {
            "decision": decision,
            "coach": result["coach"],
            "life": result["life"],
            "generated_at": datetime.now().isoformat(timespec="seconds"),
        }
        plan_id = db.upsert_daily_plan(today, bundle)
        result["plan_id"] = plan_id
        if replace_tasks:
            db.clear_tasks_for_plan(plan_id)

        valid_goal_ids = {int(g["id"]) for g in goals}
        saved = []
        for t in tasks:
            raw_gid = t.get("goal_id")
            try:
                gid = int(raw_gid) if raw_gid is not None else None
            except (TypeError, ValueError):
                gid = None
            if gid is not None and gid not in valid_goal_ids:
                gid = None
            tid = db.create_task(
                plan_id=plan_id,
                goal_id=gid,
                title=t.get("title") or "未命名",
                detail=t.get("detail") or "",
                est_minutes=int(t.get("est_minutes") or 30),
                priority=t.get("priority") or "mid",
                type_=t.get("type") or "study",
            )
            saved.append({**t, "id": tid, "goal_id": gid})
        result["tasks"] = saved

        if not saved:
            result["message"] = "计划生成失败，可手动添加任务"
            result["ok"] = bool(result["life"] or result["coach"])
        else:
            result["message"] = (
                f"已生成 {len(saved)} 条任务｜{decision.get('reason', '')}"
            )
        return result
    except Exception as e:  # noqa: BLE001
        result["ok"] = False
        result["error"] = f"{type(e).__name__}: {e}"
        result["message"] = f"流水线异常：{e}"
        return result
