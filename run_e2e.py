"""
端到端跑通：seed → 生成今日计划 → 打卡 → 周复盘 → 打印日志摘要。

默认：若 API Key 无效/缺失，自动切 mock LLM（仍走真实 Agent/DB 路径）。
强制真实调用：LIFEOS_E2E_REAL=1
"""

from __future__ import annotations

import json
import os
import time
from datetime import date, timedelta
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")

import db  # noqa: E402
import llm  # noqa: E402
from agents.pipeline import run_daily_pipeline  # noqa: E402
from agents.reviewer import run as run_reviewer  # noqa: E402
from seed import seed  # noqa: E402


def _api_usable() -> bool:
    key = (os.getenv("OPENAI_API_KEY") or "").strip()
    if not key or "your-api-key" in key.lower() or key.endswith("here"):
        return False
    probe = llm.chat([{"role": "user", "content": "回复OK两个字母"}])
    return not str(probe).startswith("[LLM错误]")


def _install_mock_llm() -> None:
    """用确定性 JSON 替换 chat_json，验证流水线与入库。"""

    def fake_chat_json(messages, schema_hint, model="default"):
        sys = (messages[0].get("content") or "") if messages else ""
        meta = {"latency_ms": 12, "token_estimate": 220, "attempts": 1, "raw": "mock"}
        goals = db.list_goals()
        g_study = next((g for g in goals if g["domain"] == "学习"), goals[0] if goals else {"id": None})
        g_health = next((g for g in goals if g["domain"] == "健康"), goals[-1] if goals else {"id": None})
        sid, hid = g_study.get("id"), g_health.get("id")
        if "调度" in sys:
            return {
                "date": date.today().isoformat(),
                "plan_mode": "normal",
                "agents_to_call": ["planner", "coach", "life"],
                "reason": "e2e mock：均衡推进学习与健康",
                "focus_goal_ids": [i for i in [sid, hid] if i is not None],
                "_meta": meta,
            }
        if "计划 Agent" in sys:
            return {
                "tasks": [
                    {
                        "goal_id": sid,
                        "title": "精读一节大模型基础（Transformer 直觉）",
                        "detail": "读完并用自己的话复述注意力机制",
                        "est_minutes": 45,
                        "priority": "high",
                        "type": "study",
                    },
                    {
                        "goal_id": hid,
                        "title": "快走或室内操 25 分钟",
                        "detail": "天气不佳则室内替代",
                        "est_minutes": 25,
                        "priority": "mid",
                        "type": "life",
                    },
                    {
                        "goal_id": sid,
                        "title": "写 5 条今日学习笔记",
                        "detail": "记录坑点与下一步",
                        "est_minutes": 20,
                        "priority": "mid",
                        "type": "study",
                    },
                ],
                "_meta": meta,
            }
        if "学习教练" in sys:
            return {
                "brief": "围绕大模型直觉：先建立概念，再动手做一个小 Prompt 实验，最后自测检验。",
                "steps": ["阅读注意力机制图示", "改写 2 个 Prompt 并对比效果", "用 3 道自测题检查理解"],
                "quiz": [
                    {
                        "q": "Self-Attention 主要解决什么问题？",
                        "options": ["降低显存", "建模序列内依赖关系", "替代全部卷积", "只用于图像"],
                        "answer": 1,
                    }
                ],
                "_meta": meta,
            }
        if "生活 Agent" in sys:
            return {
                "suggestions": [
                    {"time_slot": "morning", "action": "喝水+拉伸 5 分钟", "minutes": 5},
                    {"time_slot": "evening", "action": "23:20 开始睡前流程", "minutes": 20},
                ],
                "note": "下雨则室内操替代户外跑",
                "_meta": meta,
            }
        # reviewer
        return {
            "completion_rate": 0.6,
            "highlights": ["有连续学习打卡", "睡眠任务有推进"],
            "problems": [
                {
                    "desc": "部分任务 partial/skipped 偏多",
                    "root_cause": "单日任务估时偏满",
                    "evidence": "本周完成率约 60%，存在 partial/skipped",
                }
            ],
            "next_week_adjustments": ["每日任务总时长压到可用时长的 80%", "高优先级不超过 2 条"],
            "motivation": "用数据微调，比感觉可靠。",
            "_meta": meta,
        }

    llm.chat_json = fake_chat_json
    import agents.orchestrator as o
    import agents.planner as p
    import agents.coach as c
    import agents.life as li
    import agents.reviewer as r

    for m in (o, p, c, li, r):
        m.chat_json = fake_chat_json
    print("已启用 mock LLM（.env Key 无效或探测失败）")


def main() -> None:
    print("=== 0) API 探测 ===")
    force_real = os.getenv("LIFEOS_E2E_REAL", "").strip() == "1"
    use_real = force_real or _api_usable()
    if use_real:
        print("使用真实 LLM")
    else:
        print("真实 API 不可用（示例 Key / 401 / 断网）→ mock")
        _install_mock_llm()

    print("\n=== 1) seed ===")
    seed(reset=True)

    today = date.today().isoformat()
    print("\n=== 2) 生成今日计划 ===")
    t0 = time.time()
    out = run_daily_pipeline(today=today, available_minutes=240)
    elapsed = time.time() - t0
    print(f"耗时 {elapsed:.1f}s ok={out.get('ok')} message={out.get('message')}")
    print("decision=", json.dumps(out.get("decision"), ensure_ascii=False))
    tasks = db.list_tasks_by_date(today)
    print(f"入库任务数={len(tasks)}")
    for t in tasks:
        print(f"  - [{t['priority']}] {t['title']} ({t['est_minutes']}m)")
    assert tasks, "验收失败：今日任务为空"

    print("\n=== 3) 打卡 ===")
    db.upsert_checkin(tasks[0]["id"], today, "done", "e2e 打卡", int(tasks[0]["est_minutes"]))
    if len(tasks) > 1:
        db.upsert_checkin(tasks[1]["id"], today, "partial", "做了一半", 15)
    refreshed = db.list_tasks_by_date(today)
    print("打卡后:", [(t["title"][:20], t["status"]) for t in refreshed])

    print("\n=== 4) 周复盘 ===")
    monday = date.today() - timedelta(days=date.today().weekday())
    week_start, week_end = monday.isoformat(), (monday + timedelta(days=6)).isoformat()
    week_tasks = db.list_tasks_between(week_start, week_end)
    total = len(week_tasks)
    done = sum(1 for t in week_tasks if t["status"] == "done")
    stats = {
        "total_tasks": total,
        "done_tasks": done,
        "partial_tasks": sum(1 for t in week_tasks if t["status"] == "partial"),
        "skipped_tasks": sum(1 for t in week_tasks if t["status"] == "skipped"),
        "completion_rate": round((done / total) if total else 0.0, 2),
        "daily_breakdown": {},
    }
    review = run_reviewer(
        week_start=week_start,
        week_stats=stats,
        unfinished_tasks=[t for t in week_tasks if t["status"] != "done"],
        goals=db.list_goals(include_archived=True),
        today=today,
    )
    db.upsert_weekly_review(week_start, review)
    print(json.dumps(review, ensure_ascii=False, indent=2))
    assert review.get("problems") and review["problems"][0].get("evidence")

    print("\n=== 5) Agent 日志 ===")
    runs = db.list_agent_runs(limit=50)
    names = [r["agent_name"] for r in runs]
    print(f"共 {len(runs)} 条:", names)
    for r in runs[:15]:
        print(
            f"  #{r['id']} {r['agent_name']} success={r['success']} "
            f"{r['latency_ms']}ms token≈{r['token_estimate']}"
        )
    need = {"orchestrator", "planner", "life"}
    missing = need - set(names)
    assert not missing, f"缺日志: {missing}"

    # 降级抽检：强制失败不应抛异常
    print("\n=== 6) API 失败降级抽检 ===")
    llm.chat_json = lambda *a, **k: None
    import agents.planner as p

    p.chat_json = llm.chat_json
    degraded = p.run(focus_goals=db.list_goals(), today=today)
    assert degraded == {"tasks": []}
    print("planner 失败兜底 OK:", degraded)

    print("\n=== 验收检查表 ===")
    checks = [
        ("1 空库启动链路可初始化", True),
        ("2 生成今日计划 ≥1 条并入库", len(tasks) >= 1),
        ("3 打卡后今日状态联动", refreshed[0]["status"] == "done"),
        ("4 周复盘 problems 带数字证据", "完成率" in review["problems"][0]["evidence"] or "%" in review["problems"][0]["evidence"] or any(ch.isdigit() for ch in review["problems"][0]["evidence"])),
        ("5 日志含 orchestrator/planner/life", not missing),
        ("6 API 失败不中断（兜底）", degraded == {"tasks": []}),
        ("7 Agent 文件头职责注释", all(
            "职责" in Path(f"agents/{n}.py").read_text(encoding="utf-8")[:400]
            for n in ("orchestrator", "planner", "coach", "life", "reviewer")
        )),
    ]
    for name, ok in checks:
        print(("PASS" if ok else "FAIL"), "-", name)
    assert all(ok for _, ok in checks)

    out_path = Path("e2e_report.txt")
    out_path.write_text(
        "\n".join(
            [
                f"mode={'real' if use_real else 'mock'}",
                f"elapsed_s={elapsed:.1f}",
                f"tasks={len(tasks)}",
                f"review_rate={review.get('completion_rate')}",
                f"agent_runs={len(runs)}",
                f"agents={names}",
                f"db={db.DB_PATH}",
            ]
        ),
        encoding="utf-8",
    )
    print(f"\nE2E ALL PASS → 报告: {out_path.resolve()}")


if __name__ == "__main__":
    main()
