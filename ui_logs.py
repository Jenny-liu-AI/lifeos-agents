"""Agent 日志 Tab：筛选与翻看 agent_runs。"""

from __future__ import annotations

import pandas as pd
import streamlit as st

import db


def render_logs() -> None:
    st.subheader("Agent 运行日志")
    names = ["全部", "orchestrator", "planner", "coach", "life", "reviewer"]
    pick = st.selectbox("按 Agent 筛选", names, index=0)
    limit = st.slider("条数", 20, 300, 100, step=20)

    agent = None if pick == "全部" else pick
    rows = db.list_agent_runs(agent_name=agent, limit=limit)
    if not rows:
        st.info("暂无日志。生成计划或复盘后会出现记录。")
        return

    df = pd.DataFrame(rows)
    show_cols = [
        "id",
        "created_at",
        "agent_name",
        "date",
        "success",
        "latency_ms",
        "token_estimate",
        "input_summary",
        "output_summary",
        "error_msg",
    ]
    for c in show_cols:
        if c not in df.columns:
            df[c] = ""
    df["success"] = df["success"].map(lambda x: "成功" if x else "失败")
    st.dataframe(df[show_cols], use_container_width=True, hide_index=True)

    st.caption("点击下方展开查看单条详情")
    for r in rows[:30]:
        flag = "✅" if r.get("success") else "❌"
        with st.expander(
            f"{flag} #{r['id']} {r['agent_name']} · {r.get('created_at')} · {r.get('latency_ms')}ms"
        ):
            st.write("输入摘要：", r.get("input_summary"))
            st.write("输出摘要：", r.get("output_summary"))
            if r.get("error_msg"):
                st.error(r["error_msg"])
            st.caption(f"token≈{r.get('token_estimate')}")
