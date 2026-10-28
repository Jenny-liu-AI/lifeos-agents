"""
SQLite 数据访问层：建表、连接、目标/计划/任务 CRUD。
checkins / agent_runs / weekly_reviews 见 db_more.py（本模块再导出）。
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

DB_PATH = Path(__file__).resolve().parent / "lifeos.db"
SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    sql = SCHEMA_PATH.read_text(encoding="utf-8")
    with get_conn() as conn:
        conn.executescript(sql)
        conn.commit()


def _row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return None if row is None else dict(row)


def _rows(rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
    return [dict(r) for r in rows]


# ---------- goals ----------

def create_goal(
    title: str,
    description: str,
    domain: str,
    target_date: str | None,
    weekly_hours: float,
) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO goals (title, description, domain, target_date, weekly_hours)
               VALUES (?, ?, ?, ?, ?)""",
            (title, description, domain, target_date, weekly_hours),
        )
        conn.commit()
        return int(cur.lastrowid)


def update_goal(
    goal_id: int,
    title: str,
    description: str,
    domain: str,
    target_date: str | None,
    weekly_hours: float,
    status: str = "active",
) -> None:
    with get_conn() as conn:
        conn.execute(
            """UPDATE goals
               SET title=?, description=?, domain=?, target_date=?, weekly_hours=?, status=?
               WHERE id=?""",
            (title, description, domain, target_date, weekly_hours, status, goal_id),
        )
        conn.commit()


def archive_goal(goal_id: int) -> None:
    with get_conn() as conn:
        conn.execute("UPDATE goals SET status='archived' WHERE id=?", (goal_id,))
        conn.commit()


def list_goals(include_archived: bool = False) -> list[dict[str, Any]]:
    with get_conn() as conn:
        if include_archived:
            rows = conn.execute("SELECT * FROM goals ORDER BY id").fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM goals WHERE status='active' ORDER BY id"
            ).fetchall()
        return _rows(rows)


def get_goal(goal_id: int) -> dict[str, Any] | None:
    with get_conn() as conn:
        return _row_to_dict(
            conn.execute("SELECT * FROM goals WHERE id=?", (goal_id,)).fetchone()
        )


# ---------- daily_plans / tasks ----------

def get_plan_by_date(date: str) -> dict[str, Any] | None:
    with get_conn() as conn:
        return _row_to_dict(
            conn.execute("SELECT * FROM daily_plans WHERE date=?", (date,)).fetchone()
        )


def upsert_daily_plan(date: str, orchestrator_json: dict | str) -> int:
    payload = (
        orchestrator_json
        if isinstance(orchestrator_json, str)
        else json.dumps(orchestrator_json, ensure_ascii=False)
    )
    with get_conn() as conn:
        existing = conn.execute(
            "SELECT id FROM daily_plans WHERE date=?", (date,)
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE daily_plans SET orchestrator_json=? WHERE id=?",
                (payload, existing["id"]),
            )
            conn.commit()
            return int(existing["id"])
        cur = conn.execute(
            "INSERT INTO daily_plans (date, orchestrator_json) VALUES (?, ?)",
            (date, payload),
        )
        conn.commit()
        return int(cur.lastrowid)


def clear_tasks_for_plan(plan_id: int) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM tasks WHERE plan_id=?", (plan_id,))
        conn.commit()


def create_task(
    plan_id: int,
    goal_id: int | None,
    title: str,
    detail: str,
    est_minutes: int,
    priority: str,
    type_: str,
    status: str = "pending",
) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO tasks
               (plan_id, goal_id, title, detail, est_minutes, priority, type, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (plan_id, goal_id, title, detail, est_minutes, priority, type_, status),
        )
        conn.commit()
        return int(cur.lastrowid)


def update_task(
    task_id: int,
    title: str | None = None,
    detail: str | None = None,
    est_minutes: int | None = None,
    priority: str | None = None,
    status: str | None = None,
) -> None:
    mapping = {
        "title": title,
        "detail": detail,
        "est_minutes": est_minutes,
        "priority": priority,
        "status": status,
    }
    fields = [f"{k}=?" for k, v in mapping.items() if v is not None]
    vals = [v for v in mapping.values() if v is not None]
    if not fields:
        return
    vals.append(task_id)
    with get_conn() as conn:
        conn.execute(f"UPDATE tasks SET {', '.join(fields)} WHERE id=?", vals)
        conn.commit()


def delete_task(task_id: int) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM tasks WHERE id=?", (task_id,))
        conn.commit()


def list_tasks_by_date(date: str) -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT t.* FROM tasks t
               JOIN daily_plans p ON p.id = t.plan_id
               WHERE p.date=?
               ORDER BY CASE t.priority
                 WHEN 'high' THEN 0 WHEN 'mid' THEN 1 ELSE 2 END, t.id""",
            (date,),
        ).fetchall()
        return _rows(rows)


def list_tasks_between(start: str, end: str) -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT t.*, p.date AS plan_date FROM tasks t
               JOIN daily_plans p ON p.id = t.plan_id
               WHERE p.date >= ? AND p.date <= ?
               ORDER BY p.date, t.id""",
            (start, end),
        ).fetchall()
        return _rows(rows)


# 再导出其余 CRUD，对外仍只 import db
from db_more import (  # noqa: E402
    clear_all_data,
    get_weekly_review,
    goal_completion_rate,
    list_agent_runs,
    list_checkins_between,
    list_weekly_reviews,
    log_agent_run,
    upsert_checkin,
    upsert_weekly_review,
)

__all__ = [
    "DB_PATH",
    "init_db",
    "get_conn",
    "create_goal",
    "update_goal",
    "archive_goal",
    "list_goals",
    "get_goal",
    "get_plan_by_date",
    "upsert_daily_plan",
    "clear_tasks_for_plan",
    "create_task",
    "update_task",
    "delete_task",
    "list_tasks_by_date",
    "list_tasks_between",
    "upsert_checkin",
    "list_checkins_between",
    "goal_completion_rate",
    "log_agent_run",
    "list_agent_runs",
    "upsert_weekly_review",
    "get_weekly_review",
    "list_weekly_reviews",
    "clear_all_data",
]
