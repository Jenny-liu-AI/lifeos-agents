"""今日 Tab：生成计划、打卡、展示 Orchestrator 决策。"""

from __future__ import annotations

import json

import streamlit as st

import db
from agents.pipeline import run_daily_pipeline


def _status_label(s: str) -> str:
    return {"done": "完成", "partial": "部分完成", "skipped": "未完成", "pending": "待做"}.get(
        s, s
    )


def render_today(today: str, available_minutes: int) -> None:
    st.subheader(f"今日计划 · {today}")

    col_a, col_b = st.columns([1, 2])
    with col_a:
        if st.button("生成今日计划", type="primary", use_container_width=True):
            with st.spinner("多 Agent 协作生成中…"):
                out = run_daily_pipeline(today=today, available_minutes=available_minutes)
            st.session_state["plan_triggered_date"] = today
            st.session_state["last_pipeline"] = out
            if out.get("ok"):
                st.success(out.get("message") or "已生成")
            else:
                st.warning(out.get("message") or out.get("error") or "生成失败")
            st.rerun()

    plan = db.get_plan_by_date(today)
    decision = None
    life = None
    coach = None
    if plan and plan.get("orchestrator_json"):
        try:
            bundle = json.loads(plan["orchestrator_json"])
            decision = bundle.get("decision") or bundle
            life = bundle.get("life")
            coach = bundle.get("coach")
        except json.JSONDecodeError:
            decision = None

    last = st.session_state.get("last_pipeline") or {}
    if not decision and last.get("decision"):
        decision = last["decision"]
        life = last.get("life")
        coach = last.get("coach")

    with col_b:
        if decision:
            st.info(
                f"**调度**：{decision.get('plan_mode', '-')}｜"
                f"{decision.get('reason', '')}\n\n"
                f"调用：{', '.join(decision.get('agents_to_call') or [])}"
            )
        else:
            st.caption("尚未生成今日计划。可点击左侧按钮，或等待首次打开自动触发。")

    tasks = db.list_tasks_by_date(today)
    if not tasks:
        st.warning("今日暂无任务。可点「生成今日计划」，或在下方手动添加。")
    else:
        for t in tasks:
            with st.container(border=True):
                c1, c2, c3 = st.columns([3, 2, 1])
                c1.markdown(f"**{t['title']}**  \n{t.get('detail') or ''}")
                c2.caption(
                    f"{t.get('est_minutes')} 分钟 · {t.get('priority')} · {t.get('type')} · {_status_label(t.get('status'))}"
                )
                status = c3.selectbox(
                    "状态",
                    ["pending", "done", "partial", "skipped"],
                    index=["pending", "done", "partial", "skipped"].index(
                        t.get("status") or "pending"
                    ),
                    key=f"st_{t['id']}",
                    format_func=_status_label,
                    label_visibility="collapsed",
                )
                note = st.text_input("备注", value="", key=f"note_{t['id']}")
                mins = st.number_input(
                    "实际分钟",
                    min_value=0,
                    max_value=300,
                    value=int(t.get("est_minutes") or 0),
                    key=f"mins_{t['id']}",
                )
                b1, b2 = st.columns(2)
                if b1.button("保存打卡", key=f"chk_{t['id']}"):
                    if status == "pending":
                        st.warning("请选择完成/部分完成/未完成后再保存")
                    else:
                        db.upsert_checkin(t["id"], today, status, note, int(mins))
                        st.success("已打卡")
                        st.rerun()
                if b2.button("删除任务", key=f"del_{t['id']}"):
                    db.delete_task(t["id"])
                    st.rerun()

    with st.expander("手动添加任务"):
        title = st.text_input("标题", key="manual_title")
        detail = st.text_area("详情", key="manual_detail")
        est = st.number_input("预计分钟", 5, 90, 30, key="manual_est")
        pri = st.selectbox("优先级", ["high", "mid", "low"], key="manual_pri")
        typ = st.selectbox("类型", ["study", "life"], key="manual_typ")
        goals = db.list_goals()
        gmap = {f"{g['id']} · {g['title']}": g["id"] for g in goals}
        gsel = st.selectbox("关联目标", list(gmap.keys()) or ["（无）"], key="manual_goal")
        if st.button("添加") and title.strip():
            plan_id = db.upsert_daily_plan(today, decision or {"manual": True})
            db.create_task(
                plan_id,
                gmap.get(gsel),
                title.strip(),
                detail,
                int(est),
                pri,
                typ,
            )
            st.success("已添加")
            st.rerun()

    if life and life.get("suggestions"):
        st.markdown("#### 生活建议")
        for s in life["suggestions"]:
            st.write(f"- [{s.get('time_slot')}] {s.get('action')}（{s.get('minutes')} 分钟）")
        if life.get("note"):
            st.caption(life["note"])

    if coach and coach.get("brief"):
        with st.expander("学习辅导（Coach）"):
            st.write(coach["brief"])
            for step in coach.get("steps") or []:
                st.write(f"- {step}")
