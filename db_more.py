"""
打卡 / Agent 日志 / 周复盘 / 清空数据。由 db.py 统一再导出。
"""

from __future__ import annotations

import json
from typing import Any

from db import _row_to_dict, _rows, get_conn


def upsert_checkin(
    task_id: int,
    date: str,
    status: str,
    note: str = "",
    actual_minutes: int = 0,
) -> int:
    with get_conn() as conn:
        existing = conn.execute(
            "SELECT id FROM checkins WHERE task_id=? AND date=?",
            (task_id, date),
        ).fetchone()
        if existing:
            conn.execute(
                """UPDATE checkins SET status=?, note=?, actual_minutes=? WHERE id=?""",
                (status, note, actual_minutes, existing["id"]),
            )
            conn.execute("UPDATE tasks SET status=? WHERE id=?", (status, task_id))
            conn.commit()
            return int(existing["id"])
        cur = conn.execute(
            """INSERT INTO checkins (task_id, date, status, note, actual_minutes)
               VALUES (?, ?, ?, ?, ?)""",
            (task_id, date, status, note, actual_minutes),
        )
        conn.execute("UPDATE tasks SET status=? WHERE id=?", (status, task_id))
        conn.commit()
        return int(cur.lastrowid)


def list_checkins_between(start: str, end: str) -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT * FROM checkins
               WHERE date >= ? AND date <= ? ORDER BY date, id""",
            (start, end),
        ).fetchall()
        return _rows(rows)


def goal_completion_rate(goal_id: int) -> float:
    """目标下 done 任务数 / 全部任务数；无任务返回 0。"""
    with get_conn() as conn:
        row = conn.execute(
            """SELECT COUNT(*) AS total,
                      SUM(CASE WHEN status='done' THEN 1 ELSE 0 END) AS done_cnt
               FROM tasks WHERE goal_id=?""",
            (goal_id,),
        ).fetchone()
        total = int(row["total"] or 0)
        if total == 0:
            return 0.0
        return float(row["done_cnt"] or 0) / total


def log_agent_run(
    agent_name: str,
    date: str,
    input_summary: str,
    output_summary: str,
    latency_ms: int,
    token_estimate: int,
    success: bool,
    error_msg: str = "",
) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO agent_runs
               (agent_name, date, input_summary, output_summary,
                latency_ms, token_estimate, success, error_msg)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                agent_name,
                date,
                input_summary[:500],
                output_summary[:800],
                latency_ms,
                token_estimate,
                1 if success else 0,
                error_msg[:500],
            ),
        )
        conn.commit()
        return int(cur.lastrowid)


def list_agent_runs(
    agent_name: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    with get_conn() as conn:
        if agent_name:
            rows = conn.execute(
                """SELECT * FROM agent_runs WHERE agent_name=?
                   ORDER BY id DESC LIMIT ?""",
                (agent_name, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM agent_runs ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return _rows(rows)


def upsert_weekly_review(week_start: str, review_json: dict | str) -> int:
    payload = (
        review_json
        if isinstance(review_json, str)
        else json.dumps(review_json, ensure_ascii=False)
    )
    with get_conn() as conn:
        existing = conn.execute(
            "SELECT id FROM weekly_reviews WHERE week_start=?", (week_start,)
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE weekly_reviews SET review_json=? WHERE id=?",
                (payload, existing["id"]),
            )
            conn.commit()
            return int(existing["id"])
        cur = conn.execute(
            "INSERT INTO weekly_reviews (week_start, review_json) VALUES (?, ?)",
            (week_start, payload),
        )
        conn.commit()
        return int(cur.lastrowid)


def get_weekly_review(week_start: str) -> dict[str, Any] | None:
    with get_conn() as conn:
        return _row_to_dict(
            conn.execute(
                "SELECT * FROM weekly_reviews WHERE week_start=?", (week_start,)
            ).fetchone()
        )


def list_weekly_reviews(limit: int = 20) -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM weekly_reviews ORDER BY week_start DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return _rows(rows)


def clear_all_data() -> None:
    with get_conn() as conn:
        for table in (
            "checkins",
            "tasks",
            "daily_plans",
            "agent_runs",
            "weekly_reviews",
            "goals",
        ):
            conn.execute(f"DELETE FROM {table}")
        # 重置自增，避免演示/测试里 goal_id 与预期错位
        try:
            conn.execute("DELETE FROM sqlite_sequence")
        except Exception:  # noqa: BLE001 — 无该表时忽略
            pass
        conn.commit()
