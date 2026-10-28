# LifeOS Agents

一句话：用一组分工明确的 AI Agent 帮你管理长期目标的执行——每天生成可执行计划、白天记录执行情况、晚上/周末做复盘与纠偏。

## 核心用户价值

把「目标 → 计划 → 执行 → 反馈 → 修正」的闭环自动化，人只需要打卡和做决策，不需要自己维护表格和复盘文档。

## 用户痛点

1. 计划做不出来或做完就忘  
2. 执行过程无反馈，偏离了也不知道  
3. 复盘靠感觉，没有数据  

## 技术栈

| 层 | 选型 |
|----|------|
| 前端 | Streamlit（单入口 `app.py` + `st.tabs`） |
| 存储 | SQLite（`sqlite3` + 原生 SQL，无 ORM） |
| LLM | OpenAI 兼容接口（默认 DeepSeek，经 `llm.py` 统一封装） |
| 调度 | 每日首次打开自动触发 + 手动按钮；`ThreadPoolExecutor` 并行专职 Agent |

依赖（≤10）：`streamlit` / `openai` / `python-dotenv` / `pandas` / `altair` / `pydantic`

## 在线演示（静态页）

- 仓库：https://github.com/Jenny-liu-AI/lifeos-agents  
- 可点击演示：开启 GitHub Pages 后访问  
  `https://jenny-liu-ai.github.io/lifeos-agents/`  
  （仓库 Settings → Pages → Source 选 `main` / `/docs`）

## 快速开始

```bash
cd lifeos-agents
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env               # 填入 OPENAI_API_KEY 等
streamlit run app.py
```

浏览器打开终端提示的本地地址（默认 `http://localhost:8501`）。

### 环境变量（`.env`）

```env
OPENAI_API_KEY=sk-xxx
OPENAI_BASE_URL=https://api.deepseek.com
OPENAI_MODEL=deepseek-chat
DAILY_AVAILABLE_MINUTES=240
```

也可在应用「设置」页写入上述配置。

### 演示数据（可选）

```bash
source .venv/bin/activate
python seed.py
streamlit run app.py
```

## 页面说明

| Tab | 功能 |
|-----|------|
| 今日 | 生成/查看当日任务、打卡、看调度理由与生活/学习建议 |
| 目标 | 长期目标增改归档 + 完成率进度条 |
| 复盘 | 选周次一键生成带数字证据的周复盘 |
| Agent 日志 | 每次 Agent 调用的输入/输出摘要、耗时、token 估算 |
| 设置 | 可用时长、API、手动触发、清空数据（需输入 `CLEAR`） |

## 架构速览

```
用户打开页面
    ↓
Orchestrator（路由：plan_mode + 调用谁）
    ↓
ThreadPoolExecutor 并行
  ├─ Planner → 写入 tasks
  ├─ Coach   → 学习辅导（汇总进 daily_plans）
  └─ Life    → 生活建议（汇总进 daily_plans）
    ↓
白天打卡 → checkins / tasks.status
    ↓
周末 Reviewer → weekly_reviews（周期校验）
```

更细的设计见 [DESIGN.md](./DESIGN.md)。五分钟演示脚本见 [demo.md](./demo.md)。

## 目录结构

```
lifeos-agents/
  app.py              # Streamlit 入口
  llm.py              # chat / chat_json
  db.py / db_more.py  # SQLite 访问
  schema.sql
  agents/             # 五个 Agent + pipeline
  ui_*.py             # 五个 Tab 的 UI
  seed.py
  .env.example
  requirements.txt
```

## 降级与可观测

- 所有 LLM 调用走 `llm.py`；JSON 解析最多重试 2 次，失败返回兜底，不抛穿页面  
- 断网 / API 失败时页面仍可打开，中文提示 + 可手动加任务  
- 「Agent 日志」可核对 orchestrator / planner / life 等每次调用  

## 明确不做（P2）

登录注册、多用户、移动端适配、向量库/RAG、语音、推送、Docker、全量单测、CI/CD。
