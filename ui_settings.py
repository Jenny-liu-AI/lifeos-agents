"""设置 Tab：可用时长、API 配置、手动触发、清空数据。"""

from __future__ import annotations

import os
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv, set_key

import db
from agents.pipeline import run_daily_pipeline

ENV_PATH = Path(__file__).resolve().parent / ".env"


def _ensure_env() -> None:
    if not ENV_PATH.exists():
        example = ENV_PATH.with_name(".env.example")
        if example.exists():
            ENV_PATH.write_text(example.read_text(encoding="utf-8"), encoding="utf-8")
        else:
            ENV_PATH.write_text("", encoding="utf-8")
    load_dotenv(ENV_PATH, override=True)


def render_settings(today: str) -> None:
    st.subheader("设置")
    _ensure_env()

    st.markdown("#### 每日可用时长")
    cur_mins = int(os.getenv("DAILY_AVAILABLE_MINUTES", "240") or 240)
    mins = st.number_input("分钟", min_value=30, max_value=720, value=cur_mins, step=15)
    if st.button("保存可用时长"):
        set_key(str(ENV_PATH), "DAILY_AVAILABLE_MINUTES", str(int(mins)))
        load_dotenv(ENV_PATH, override=True)
        st.session_state["available_minutes"] = int(mins)
        st.success("已写入 .env")

    st.markdown("#### 模型与 API（OpenAI 兼容）")
    api_key = st.text_input(
        "OPENAI_API_KEY",
        value=os.getenv("OPENAI_API_KEY", ""),
        type="password",
    )
    base_url = st.text_input(
        "OPENAI_BASE_URL",
        value=os.getenv("OPENAI_BASE_URL", "https://api.deepseek.com"),
    )
    model = st.text_input(
        "OPENAI_MODEL",
        value=os.getenv("OPENAI_MODEL", "deepseek-chat"),
    )
    if st.button("保存 API 配置"):
        set_key(str(ENV_PATH), "OPENAI_API_KEY", api_key.strip())
        set_key(str(ENV_PATH), "OPENAI_BASE_URL", base_url.strip())
        set_key(str(ENV_PATH), "OPENAI_MODEL", model.strip())
        load_dotenv(ENV_PATH, override=True)
        st.success("已保存。下次 LLM 调用将使用新配置。")

    st.markdown("#### 手动触发")
    if st.button("立即生成今日计划", type="primary"):
        with st.spinner("生成中…"):
            out = run_daily_pipeline(
                today=today,
                available_minutes=int(st.session_state.get("available_minutes") or mins),
            )
        st.session_state["plan_triggered_date"] = today
        st.session_state["last_pipeline"] = out
        if out.get("ok"):
            st.success(out.get("message") or "完成")
        else:
            st.warning(out.get("message") or out.get("error") or "失败（页面未中断）")

    st.markdown("#### 危险操作")
    st.caption("清空全部业务数据（目标/计划/打卡/日志/复盘），不可恢复。")
    confirm = st.text_input("输入 CLEAR 确认清空", key="clear_confirm")
    if st.button("清空全部数据", type="secondary"):
        if confirm.strip() == "CLEAR":
            db.clear_all_data()
            st.session_state.pop("plan_triggered_date", None)
            st.session_state.pop("last_pipeline", None)
            st.success("已清空")
            st.rerun()
        else:
            st.error("请输入 CLEAR 以二次确认")
