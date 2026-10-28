"""目标 Tab：创建 / 编辑 / 归档 + 完成率进度条。"""

from __future__ import annotations

import streamlit as st

import db


def render_goals() -> None:
    st.subheader("长期目标")
    goals = db.list_goals(include_archived=st.checkbox("显示已归档", value=False))

    if not goals:
        st.info("还没有目标。请在下方新增。")
    for g in goals:
        rate = db.goal_completion_rate(int(g["id"]))
        with st.container(border=True):
            st.markdown(f"**#{g['id']} {g['title']}** · {g['domain']} · {g['status']}")
            st.caption(
                f"截止 {g.get('target_date') or '未设'}｜每周 {g.get('weekly_hours')} 小时"
            )
            st.write(g.get("description") or "")
            st.progress(min(1.0, rate), text=f"完成率 {rate:.0%}")
            c1, c2 = st.columns(2)
            if c1.button("编辑", key=f"edit_btn_{g['id']}"):
                st.session_state["editing_goal_id"] = g["id"]
            if g["status"] == "active" and c2.button("归档", key=f"arch_{g['id']}"):
                db.archive_goal(int(g["id"]))
                st.rerun()

    edit_id = st.session_state.get("editing_goal_id")
    editing = db.get_goal(int(edit_id)) if edit_id else None
    st.markdown("---")
    st.markdown("#### 新增 / 编辑目标" if editing else "#### 新增目标")

    default = editing or {}
    title = st.text_input("名称", value=default.get("title") or "", key="g_title")
    desc = st.text_area("描述", value=default.get("description") or "", key="g_desc")
    domain = st.selectbox(
        "领域",
        ["学习", "健康", "其他"],
        index=["学习", "健康", "其他"].index(default.get("domain") or "学习"),
        key="g_domain",
    )
    target = st.text_input(
        "截止日 YYYY-MM-DD",
        value=default.get("target_date") or "",
        key="g_date",
    )
    hours = st.number_input(
        "每周投入小时",
        min_value=0.5,
        max_value=40.0,
        value=float(default.get("weekly_hours") or 5),
        step=0.5,
        key="g_hours",
    )

    b1, b2 = st.columns(2)
    if b1.button("保存目标", type="primary"):
        if not title.strip():
            st.error("名称不能为空")
        elif editing:
            db.update_goal(
                int(editing["id"]),
                title.strip(),
                desc,
                domain,
                target.strip() or None,
                float(hours),
                editing.get("status") or "active",
            )
            st.session_state.pop("editing_goal_id", None)
            st.success("已更新")
            st.rerun()
        else:
            db.create_goal(title.strip(), desc, domain, target.strip() or None, float(hours))
            st.success("已创建")
            st.rerun()
    if editing and b2.button("取消编辑"):
        st.session_state.pop("editing_goal_id", None)
        st.rerun()
