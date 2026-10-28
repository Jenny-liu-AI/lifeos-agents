"""复盘 Tab：选择周次 → 生成/查看周复盘。"""

from __future__ import annotations

import json
from datetime import date, timedelta

import streamlit as st

import db
from agents.reviewer import run as run_reviewer


def _monday_of(d: date) -> date:
    return d - timedelta(days=d.weekday())


def _week_stats(week_start: str, week_end: str) -> tuple[dict, list]:
    tasks = db.list_tasks_between(week_start, week_end)
    total = len(tasks)
    done = sum(1 for t in tasks if t.get("status") == "done")
    partial = sum(1 for t in tasks if t.get("status") == "partial")
    skipped = sum(1 for t in tasks if t.get("status") == "skipped")
    unfinished = [t for t in tasks if t.get("status") != "done"]
    rate = (done / total) if total else 0.0
    by_day: dict[str, dict] = {}
    for t in tasks:
        day = t.get("plan_date") or ""
        bucket = by_day.setdefault(day, {"total": 0, "done": 0})
        bucket["total"] += 1
        if t.get("status") == "done":
            bucket["done"] += 1
    stats = {
        "total_tasks": total,
        "done_tasks": done,
        "partial_tasks": partial,
        "skipped_tasks": skipped,
        "completion_rate": round(rate, 2),
        "daily_breakdown": by_day,
    }
    return stats, unfinished


def render_review(today: str) -> None:
    st.subheader("周复盘")
    today_d = date.fromisoformat(today)
    this_monday = _monday_of(today_d)
    options = []
    for i in range(0, 8):
        m = this_monday - timedelta(weeks=i)
        options.append(m.isoformat())

    week_start = st.selectbox("选择周（周一）", options, index=0)
    week_end = (date.fromisoformat(week_start) + timedelta(days=6)).isoformat()
    st.caption(f"区间：{week_start} ~ {week_end}")

    if st.button("生成本周复盘", type="primary"):
        stats, unfinished = _week_stats(week_start, week_end)
        with st.spinner("Reviewer 分析中…"):
            review = run_reviewer(
                week_start=week_start,
                week_stats=stats,
                unfinished_tasks=unfinished,
                goals=db.list_goals(include_archived=True),
                today=today,
            )
        db.upsert_weekly_review(week_start, review)
        st.success("复盘已生成")
        st.rerun()

    row = db.get_weekly_review(week_start)
    if not row:
        st.info("该周尚无复盘，点击上方按钮生成。")
        return

    try:
        data = json.loads(row["review_json"])
    except json.JSONDecodeError:
        st.error("复盘数据损坏")
        return

    st.metric("完成率", f"{float(data.get('completion_rate') or 0):.0%}")
    if data.get("motivation"):
        st.write(f"💬 {data['motivation']}")

    st.markdown("#### 亮点")
    for h in data.get("highlights") or []:
        st.write(f"- {h}")
    if not data.get("highlights"):
        st.caption("暂无亮点")

    st.markdown("#### 问题（含证据）")
    for p in data.get("problems") or []:
        with st.container(border=True):
            st.markdown(f"**{p.get('desc')}**")
            st.write(f"根因：{p.get('root_cause')}")
            st.caption(f"证据：{p.get('evidence')}")

    st.markdown("#### 下周调整")
    for a in data.get("next_week_adjustments") or []:
        st.write(f"- {a}")
