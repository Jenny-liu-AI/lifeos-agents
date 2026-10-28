# LifeOS Agents 设计说明

## 1. 设计目标

个人自用、24 小时可交付的多 Agent 生活/学习管理平台。  
优先：**可运行、可读、可观测**；不为工程完备性引入多余框架。

## 2. 多 Agent 协作：三段式结构

> **主控路由 + 专职执行 + 周期校验**

```
┌─────────────┐     ┌──────────────────────────┐     ┌────────────┐
│ Orchestrator│ ──► │ Planner / Coach / Life   │ ──► │ 入库汇总   │
│ 主控路由     │     │ （ThreadPool 可并行）      │     │ plans/tasks│
└─────────────┘     └──────────────────────────┘     └────────────┘
                                                           │
                     白天打卡（人）                          │
                                                           ▼
                                              ┌────────────────────┐
                                              │ Reviewer 周期校验   │
                                              │ （周维度手动触发）   │
                                              └────────────────────┘
```

| 阶段 | Agent | 触发 | 产出 |
|------|-------|------|------|
| 主控路由 | Orchestrator | 每日首次打开 / 手动按钮 | `plan_mode`、`agents_to_call`、`focus_goal_ids`、`reason` |
| 专职执行 | Planner / Coach / Life | 由路由结果决定，并行调用 | 任务列表 / 学习辅导 / 生活建议 |
| 周期校验 | Reviewer | 复盘 Tab 选周后一键生成 | 带 evidence 的周报 JSON |

### 为什么这样拆

- **Orchestrator 独立**：只做「今天干什么、叫谁来」，避免计划 Agent 既定方向又写任务造成自我合理化。  
- **Planner / Coach / Life 专职**：任务可执行性、教学法、生活节律是不同目标函数，分权更稳。  
- **Reviewer 周期触发**：不掺进每日生成，减少「边计划边美化结果」；强制引用完成率等数字。

### 并行约定

- 使用 `concurrent.futures.ThreadPoolExecutor`（`agents/pipeline.py`）。  
- Coach 与 Planner 并行时，当日任务尚未落库：Coach 以「聚焦的学习目标」为输入。  
- Life 并行时用「可用时长」粗估负载；结果写入 `daily_plans.orchestrator_json` 一并展示。

## 3. 各 Agent 契约（摘要）

统一：输出严格 JSON（`llm.chat_json` + schema_hint + 最多 2 次解析重试）；失败写 `agent_runs` 并返回兜底，禁止抛异常中断 UI。

| Agent | 关键约束 | 兜底 |
|-------|----------|------|
| Orchestrator | 至少含 planner；reason≤60 字 | planner+life（有学习目标则加 coach），focus 全部目标 |
| Planner | ≤6 任务，单任务≤90 分钟，总时长≤可用 | 空列表 + 页面提示手动添加 |
| Coach | brief≤150；quiz 可选 | brief=任务标题 |
| Life | time_slot∈morning/noon/evening；note 含天气替代 | 「早睡 23:30 前」 |
| Reviewer | problems 1–3 条且必须有 evidence | 仅完成率 + 一条带数字的提示 |

## 4. 数据模型

见 `schema.sql`：

- `goals` — 长期目标（领域：学习/健康/其他）  
- `daily_plans` — 按日一份，`orchestrator_json` 存决策 + coach/life 汇总  
- `tasks` — 当日任务  
- `checkins` — 打卡；同步更新 `tasks.status`  
- `agent_runs` — 可观测面板数据源  
- `weekly_reviews` — 按周一 `week_start` 唯一  

## 5. 调度策略（非分布式）

不引入 Celery/定时进程。两种触发：

1. **自动**：`app.py` 用 `st.session_state["plan_triggered_date"]` 保证「每个会话日只自动跑一次」；若库中已有当日 plan 则跳过。  
2. **手动**：「今日」与「设置」页按钮调用同一 `run_daily_pipeline`。

## 6. LLM 与降级

- 唯一出口：`llm.py` 的 `chat` / `chat_json`。  
- Token 为启发式估算（中英混合），用于日志对比而非计费。  
- 无 Key / 断网 / 非 JSON：Agent 层兜底 + 中文提示，页面保持可操作（手动加任务、打卡、看历史）。

## 7. 前端结构

- 单入口 `app.py`，五个 `st.tabs`。  
- Tab 实现拆到 `ui_*.py`，满足「单文件 ≤300 行、可读优先」。  

## 8. 范围边界

- **P0 必做**：目标、日计划、打卡、周复盘、Agent 日志、五 Agent 真调 LLM。  
- **P1 可选**：出题自测深化、番茄钟、CSV 导出（时间不够可砍）。  
- **P2 不做**：账号体系、多租户、RAG、推送、Docker、全量 CI。
