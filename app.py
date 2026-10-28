"""
LifeOS Agents — Streamlit 单入口。
五个 Tab：今日 / 目标 / 复盘 / Agent 日志 / 设置。
每日首次打开自动触发计划生成（session_state 防重复）。
"""

from __future__ import annotations

import os
from datetime import date

import streamlit as st
from dotenv import load_dotenv

import db
from agents.pipeline import get_available_minutes, run_daily_pipeline
from ui_goals import render_goals
from ui_logs import render_logs
from ui_review import render_review
from ui_settings import render_settings
from ui_today import render_today

load_dotenv()
st.set_page_config(page_title="LifeOS Agents", page_icon="🌱", layout="wide")


def _bootstrap() -> str:
    """初始化数据库与 session，返回今日日期字符串。"""
    db.init_db()
    today = date.today().isoformat()
    if "available_minutes" not in st.session_state:
        st.session_state["available_minutes"] = get_available_minutes()
    return today


def _maybe_auto_generate(today: str) -> None:
    """每日首次打开页面自动生成计划（有目标且当日尚未触发）。"""
    if st.session_state.get("plan_triggered_date") == today:
        return
    # 若库中已有当日计划，只标记已触发，避免重复烧 token
    if db.get_plan_by_date(today):
        st.session_state["plan_triggered_date"] = today
        return
    if not db.list_goals():
        st.session_state["plan_triggered_date"] = today
        return
    with st.spinner("首次打开：正在自动生成今日计划…"):
        out = run_daily_pipeline(
            today=today,
            available_minutes=int(st.session_state["available_minutes"]),
        )
    st.session_state["plan_triggered_date"] = today
    st.session_state["last_pipeline"] = out


def main() -> None:
    today = _bootstrap()
    st.title("LifeOS Agents")
    st.caption("目标 → 计划 → 执行 → 反馈 → 修正｜个人自用多 Agent 平台")

    # 自动触发放在渲染前；失败也不阻断页面
    try:
        _maybe_auto_generate(today)
    except Exception as e:  # noqa: BLE001
        st.warning(f"自动生成计划时降级：{e}")

    tab_today, tab_goals, tab_review, tab_logs, tab_settings = st.tabs(
        ["今日", "目标", "复盘", "Agent 日志", "设置"]
    )
    with tab_today:
        render_today(today, int(st.session_state["available_minutes"]))
    with tab_goals:
        render_goals()
    with tab_review:
        render_review(today)
    with tab_logs:
        render_logs()
    with tab_settings:
        render_settings(today)

    # 页脚提示当前模型（不含 key）
    st.divider()
    st.caption(
        f"模型={os.getenv('OPENAI_MODEL', 'deepseek-chat')}｜"
        f"base={os.getenv('OPENAI_BASE_URL', '')}｜"
        f"可用时长={st.session_state['available_minutes']} 分钟"
    )


if __name__ == "__main__":
    main()
