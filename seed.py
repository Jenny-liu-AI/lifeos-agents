"""
造演示假数据：目标 + 近几天计划/任务/打卡。
用法：python seed.py
可选：python seed.py --reset   # 先清空再写入
"""

from __future__ import annotations

import argparse
import json
from datetime import date, timedelta

import db


def seed(reset: bool = False) -> None:
    db.init_db()
    if reset:
        db.clear_all_data()
        print("已清空旧数据")

    if db.list_goals():
        print("已有目标，跳过创建目标（可用 --reset 重建）")
        goals = db.list_goals()
    else:
        g_study = db.create_goal(
            title="系统学习 AI 人工智能",
            description="掌握大模型基础、Prompt 与 Agent 应用，能独立完成小实验与总结",
            domain="学习",
            target_date=(date.today() + timedelta(days=90)).isoformat(),
            weekly_hours=8,
        )
        g_health = db.create_goal(
            title="规律运动与睡眠",
            description="每周运动 3 次，工作日 23:30 前入睡",
            domain="健康",
            target_date=(date.today() + timedelta(days=60)).isoformat(),
            weekly_hours=4,
        )
        g_other = db.create_goal(
            title="每周深度阅读",
            description="非虚构类，每周至少 1 本/章节精读并做笔记",
            domain="其他",
            target_date=(date.today() + timedelta(days=120)).isoformat(),
            weekly_hours=3,
        )
        goals = [
            db.get_goal(g_study),
            db.get_goal(g_health),
            db.get_goal(g_other),
        ]
        print(f"已创建目标: {[g['title'] for g in goals]}")

    by_domain = {g["domain"]: g for g in goals}
    g_study = by_domain.get("学习") or goals[0]
    g_health = by_domain.get("健康") or goals[min(1, len(goals) - 1)]
    g_other = by_domain.get("其他") or goals[-1]

    today = date.today()
    # 写入「昨天往前」共 5 天历史（不含今天，留给现场生成）
    templates = [
        [
            (g_study["id"], "精读 Transformer 直觉", "对照图示复述注意力机制", 45, "high", "study"),
            (g_health["id"], "慢跑或快走 30 分钟", "小区或室内替代", 30, "mid", "life"),
        ],
        [
            (g_study["id"], "做一次 Prompt 对比实验", "同一任务写 2 版 Prompt 并记录差异", 50, "high", "study"),
            (g_other["id"], "精读一章并写 5 条笔记", "非虚构", 40, "mid", "study"),
        ],
        [
            (g_study["id"], "复习昨天概念坑点", "整理成 checklist", 35, "mid", "study"),
            (g_health["id"], "力量训练或拉伸", "家中徒手亦可", 25, "mid", "life"),
            (g_other["id"], "阅读 20 页", "通勤或睡前", 25, "low", "study"),
        ],
        [
            (g_study["id"], "画一张 Agent 协作示意图", "纸笔或白板均可", 45, "high", "study"),
            (g_health["id"], "23:10 开始睡前流程", "远离手机", 20, "high", "life"),
        ],
        [
            (g_study["id"], "写一小节 AI 学习总结", "发到笔记库", 30, "mid", "study"),
            (g_health["id"], "散步 25 分钟", "饭后", 25, "low", "life"),
        ],
    ]
    # 完成状态循环，制造「有完成有欠账」
    status_cycle = ["done", "done", "partial", "skipped", "done", "partial"]

    created_days = 0
    for i in range(5, 0, -1):
        d = (today - timedelta(days=i)).isoformat()
        if db.get_plan_by_date(d):
            continue
        decision = {
            "decision": {
                "date": d,
                "plan_mode": "normal" if i % 2 else "catch_up",
                "agents_to_call": ["planner", "life"],
                "reason": "seed 历史日",
                "focus_goal_ids": [g_study["id"], g_health["id"]],
            },
            "life": {
                "suggestions": [
                    {"time_slot": "evening", "action": "23:30 前入睡", "minutes": 20}
                ],
                "note": "seed",
            },
        }
        plan_id = db.upsert_daily_plan(d, decision)
        day_tasks = templates[(5 - i) % len(templates)]
        for j, (gid, title, detail, mins, pri, typ) in enumerate(day_tasks):
            tid = db.create_task(plan_id, gid, title, detail, mins, pri, typ)
            st = status_cycle[(5 - i + j) % len(status_cycle)]
            note = {"done": "按计划完成", "partial": "只做了一半", "skipped": "被会议打断"}.get(
                st, ""
            )
            db.upsert_checkin(tid, d, st, note, mins if st == "done" else mins // 2)
        created_days += 1

    print(f"历史计划天数新增: {created_days}")
    print("今日留空，便于演示「生成今日计划」。")
    print("完成。可执行: streamlit run app.py")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="LifeOS Agents 演示数据")
    parser.add_argument("--reset", action="store_true", help="先清空全部业务数据")
    args = parser.parse_args()
    seed(reset=args.reset)
