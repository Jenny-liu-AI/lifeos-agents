"""
LLM 统一封装：所有 Agent 只能通过本模块调用模型，禁止直接使用 openai。

提供：
- chat(messages, model="default") -> str
- chat_json(messages, schema_hint) -> dict | None
  （强制 JSON 输出，最多重试 2 次解析，失败返回 None）
"""

from __future__ import annotations

import json
import os
import re
import time
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI

# 加载项目根目录 .env（若无在则静默跳过）
load_dotenv()

# ---------- 配置（可被环境变量覆盖） ----------
DEFAULT_BASE_URL = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-chat"
MAX_JSON_RETRIES = 2  # 解析失败后的额外重试次数（共最多 1+2=3 次调用）


def _get_client() -> OpenAI:
    """根据 .env 创建 OpenAI 兼容客户端。"""
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    base_url = os.getenv("OPENAI_BASE_URL", DEFAULT_BASE_URL).strip() or DEFAULT_BASE_URL
    if not api_key:
        # 无 key 时仍创建客户端，调用时会失败并由上层兜底
        api_key = "missing-api-key"
    return OpenAI(api_key=api_key, base_url=base_url)


def _resolve_model(model: str) -> str:
    if model and model != "default":
        return model
    return os.getenv("OPENAI_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL


def estimate_tokens(text: str) -> int:
    """
    粗略估算 token 数（不做真实 tokenizer）。
    规则：中文约 1.5 字/token，英文约 4 字符/token，取混合近似。
    """
    if not text:
        return 0
    chinese = len(re.findall(r"[\u4e00-\u9fff]", text))
    other = max(0, len(text) - chinese)
    return max(1, int(chinese / 1.5 + other / 4))


def estimate_messages_tokens(messages: list[dict[str, str]]) -> int:
    """估算 messages 总 token。"""
    return sum(estimate_tokens(m.get("content", "") or "") for m in messages)


def chat(messages: list[dict[str, str]], model: str = "default") -> str:
    """
    普通对话调用，返回助手文本。
    失败时返回以「[LLM错误]」开头的中文说明，不抛异常。
    """
    model_name = _resolve_model(model)
    try:
        client = _get_client()
        resp = client.chat.completions.create(
            model=model_name,
            messages=messages,
            temperature=0.3,
        )
        content = (resp.choices[0].message.content or "").strip()
        return content
    except Exception as e:  # noqa: BLE001 — 页面侧不允许中断
        return f"[LLM错误] 调用失败：{type(e).__name__}: {e}"


def _extract_json_object(text: str) -> dict[str, Any] | None:
    """从模型输出中提取第一个 JSON 对象并解析。"""
    if not text:
        return None
    text = text.strip()
    # 去掉常见 markdown 代码围栏
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
        text = text.strip()
    # 直接解析
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass
    # 截取最外层 {...}
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        try:
            data = json.loads(text[start : end + 1])
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            return None
    return None


def chat_json(
    messages: list[dict[str, str]],
    schema_hint: str,
    model: str = "default",
) -> dict[str, Any] | None:
    """
    要求模型只输出 JSON。内部解析失败最多重试 MAX_JSON_RETRIES 次。
    全部失败返回 None（由各 Agent 自行兜底）。

    额外约定：返回值中会附带 _meta（调用方若不想要可忽略）：
      {_meta: {latency_ms, token_estimate, attempts, raw}}
    若最终失败则返回 None，不附带 _meta。
    """
    model_name = _resolve_model(model)
    # 在末尾追加 schema 约束，避免污染调用方原 messages
    constrained = list(messages) + [
        {
            "role": "user",
            "content": (
                "请严格只输出一个 JSON 对象，不要 markdown，不要解释。"
                f"输出结构示意：{schema_hint}"
            ),
        }
    ]

    last_raw = ""
    total_latency = 0
    attempts = 0
    input_tokens = estimate_messages_tokens(constrained)

    for attempt in range(MAX_JSON_RETRIES + 1):
        attempts = attempt + 1
        call_messages = constrained
        if attempt > 0:
            # 重试时提醒上次输出不合法
            call_messages = constrained + [
                {
                    "role": "user",
                    "content": (
                        "上一次输出无法解析为合法 JSON，请重新输出。"
                        "只输出 JSON 对象本身，不要加任何前后缀。"
                        f"上次片段：{last_raw[:300]}"
                    ),
                }
            ]

        t0 = time.time()
        try:
            client = _get_client()
            resp = client.chat.completions.create(
                model=model_name,
                messages=call_messages,
                temperature=0.2,
                # 部分兼容接口支持 response_format；不支持时忽略错误再裸调
                response_format={"type": "json_object"},
            )
            last_raw = (resp.choices[0].message.content or "").strip()
        except Exception as first_err:  # noqa: BLE001
            # 某些兼容 API 不支持 response_format，降级普通调用
            try:
                client = _get_client()
                resp = client.chat.completions.create(
                    model=model_name,
                    messages=call_messages,
                    temperature=0.2,
                )
                last_raw = (resp.choices[0].message.content or "").strip()
            except Exception as e:  # noqa: BLE001
                last_raw = f"[LLM错误] {type(e).__name__}: {e} (first={first_err})"
                total_latency += int((time.time() - t0) * 1000)
                continue

        total_latency += int((time.time() - t0) * 1000)
        parsed = _extract_json_object(last_raw)
        if parsed is not None:
            out_tokens = estimate_tokens(last_raw)
            parsed["_meta"] = {
                "latency_ms": total_latency,
                "token_estimate": input_tokens + out_tokens,
                "attempts": attempts,
                "raw": last_raw[:500],
            }
            return parsed

    return None


def strip_meta(data: dict[str, Any] | None) -> dict[str, Any] | None:
    """去掉 chat_json 附带的 _meta，便于 Agent 返回干净业务 JSON。"""
    if data is None:
        return None
    clean = {k: v for k, v in data.items() if k != "_meta"}
    return clean


def pop_meta(data: dict[str, Any] | None) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    """
    分离业务 JSON 与 _meta。
    返回 (业务dict或None, meta字典)；meta 缺省字段补 0。
    """
    empty_meta = {"latency_ms": 0, "token_estimate": 0, "attempts": 0, "raw": ""}
    if data is None:
        return None, empty_meta
    meta = data.get("_meta") or empty_meta
    business = {k: v for k, v in data.items() if k != "_meta"}
    return business, meta
