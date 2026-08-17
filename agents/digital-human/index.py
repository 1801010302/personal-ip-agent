"""
个人IP口播智能体 — EdgeOne Makers
"""

from typing import Any, AsyncGenerator
import asyncio
import json
import os

from dotenv import load_dotenv
from openai import AsyncOpenAI
from openai.types.responses import ResponseTextDeltaEvent
from agents import Agent, OpenAIChatCompletionsModel, Runner

from .._logger import create_logger
from .._tools import (
    generate_script,
    analyze_script,
    generate_cover_image,
    call_digital_human,
)

load_dotenv()

logger = create_logger("digital-human")

# ========== LLM Model ==========
llm_client = AsyncOpenAI(
    api_key=os.getenv("AI_GATEWAY_API_KEY"),
    base_url=os.getenv("AI_GATEWAY_BASE_URL"),
)

llm_model = OpenAIChatCompletionsModel(
    model=os.getenv("AI_GATEWAY_MODEL", "@makers/deepseek-v4-flash"),
    openai_client=llm_client,
)

# ========== Agent ==========
agent = Agent(
    name="个人IP口播助手",
    instructions=(
        "你是个人IP口播智能体，专门帮用户把零散想法变成可以直接录制的口播视频。\n\n"
        "你的工作流程（按顺序进行，不要跳步）：\n\n"
        "第一步：收集想法\n"
        "  - 用户输入主题或想法后，调用 generate_script 生成完整口播文案\n"
        "  - 生成后把完整文案展示给用户，让用户确认或修改\n"
        "  - 如果用户不满意，继续修改直到用户确认满意\n\n"
        "第二步：确认文案\n"
        "  - 用户确认文案后，调用 analyze_script 分析文案，得到标题和封面方向\n"
        "  - 把标题和封面方向告知用户\n\n"
        "第三步：生成封面（可选）\n"
        "  - 用户说'生成封面'后，调用 generate_cover_image 生成封面图\n\n"
        "第四步：生成视频（可选，API Key 配置后才可用）\n"
        "  - 用户说'生成视频'后，调用 call_digital_human 提交数字人视频任务\n"
        "  - 告知用户视频生成中，稍后可查看结果\n\n"
        "注意事项：\n"
        "  - generate_script 生成的是纯文案，不包含视频生成\n"
        "  - call_digital_human 需要用户配置益民居API Key，未配置时告知用户\n"
        "  - 每次完成文案后询问用户是否需要调整或继续\n"
        "  - 如果用户只是闲聊，先友好回应，再引导用户输入想做的视频主题"
    ),
    tools=[generate_script, analyze_script, generate_cover_image, call_digital_human],
    model=llm_model,
)

# ========== SSE Helper ==========
def sse_event(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

# ========== Event Stream Generator ==========
async def _event_stream(
    message: str,
    session=None,
    cancel_signal: asyncio.Event | None = None,
) -> AsyncGenerator[str, None]:
    result = Runner.run_streamed(agent, input=message, session=session)

    async for event in result.stream_events():
        if cancel_signal and cancel_signal.is_set():
            break

        if event.type == "raw_response_event" and isinstance(event.data, ResponseTextDeltaEvent):
            yield sse_event("text_delta", {"delta": event.data.delta})

        elif event.type == "run_item_stream_event":
            if event.name == "tool_called":
                tool_name = (
                    getattr(event.item, "name", None)
                    or getattr(getattr(event.item, "raw_item", None), "name", None)
                )
                if tool_name:
                    yield sse_event("tool_called", {"tool": tool_name})

# ========== Core Handler ==========
async def handler(context: Any) -> AsyncGenerator[str, None]:
    request = context.request
    body = request.body
    message = body.get("message") if isinstance(body, dict) else None

    if not message:
        yield sse_event("error", {"message": "'message' is required"})
        yield sse_event("done", {})
        return

    cid = context.conversation_id
    user_id = body.get("userId") or body.get("user_id") if isinstance(body, dict) else None
    logger.log(f"[request] cid={cid}, uid={user_id}, message={message[:50]!r}")

    session = context.store.openai_session(cid) if cid else None
    cancel_signal = request.signal
    stopped = False

    try:
        async for frame in _event_stream(message, session, cancel_signal):
            if cancel_signal.is_set():
                stopped = True
                break
            yield frame
    except asyncio.CancelledError:
        stopped = True
        logger.log("[stream] cancelled")
    except Exception as e:
        logger.error(f"[stream] error: {type(e).__name__}: {e}")
        yield sse_event("error", {"message": str(e)})
    finally:
        yield sse_event("done", {"stopped": stopped})
