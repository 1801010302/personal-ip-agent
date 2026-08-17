"""
个人IP口播智能体工具集 — EdgeOne Makers
"""

import json
import os
import httpx
from typing import Annotated
from agents import function_tool

AI_GATEWAY_KEY = os.getenv("AI_GATEWAY_API_KEY")
AI_GATEWAY_URL = os.getenv("AI_GATEWAY_BASE_URL", "https://ai-gateway.edgeone.link/v1")
DEEPSEEK_MODEL = os.getenv("AI_GATEWAY_MODEL", "@makers/deepseek-v4-flash")

# 火山方舟 Image2
IMAGE2_KEY = os.getenv("IMAGE2_API_KEY", "")
IMAGE2_BASE = os.getenv("IMAGE2_API_BASE", "https://ark.cn-beijing.volces.com/api/v3")

# 益民居·数字人（闪剪）
CHUANSHEN_API_KEY = os.getenv("CHUANSHEN_API_KEY", "")
CHUANSHEN_API_BASE = os.getenv("CHUANSHEN_API_BASE", "https://szr.yiminju.xyz/api/v1")


def _deepseek(messages: list, max_tokens=800, temperature=0.72) -> str:
    """通过 EdgeOne AI Gateway 调用 DeepSeek"""
    if not AI_GATEWAY_KEY:
        return json.dumps({"error": "AI_GATEWAY_API_KEY 未配置，请在 EdgeOne Makers 控制台设置环境变量 AI_GATEWAY_API_KEY"})
    try:
        with httpx.AsyncClient(timeout=60.0) as client:
            resp = client.post(
                f"{AI_GATEWAY_URL}/chat/completions",
                headers={
                    "Authorization": f"Bearer {AI_GATEWAY_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": DEEPSEEK_MODEL,
                    "messages": messages,
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                },
            )
            data = resp.json()
            return data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        return json.dumps({"error": f"DeepSeek 调用失败: {str(e)}"})


# ========== Tool 1: 生成口播文案 ==========
@function_tool
def generate_script(
    ideas: Annotated[str, "用户的零散想法或主题"],
    tone: Annotated[str, "口吻风格，如'真诚、有经验感'"] = "真诚、有经验感",
    audience: Annotated[str, "目标受众"] = "普通短视频用户",
    duration_seconds: Annotated[int, "目标时长（秒）"] = 60,
) -> str:
    """
    根据用户的零散想法，调用 DeepSeek 生成可直接口播的短视频文案。
    返回 JSON：{title, content, hook, closing, estimatedSeconds}
    """
    system = (
        "你是一名中文短视频口播文案策划师。\n"
        "把用户的零散想法整理成可直接口播的稿子，开头必须有3秒钩子，中段逻辑清晰，结尾有自然行动召唤。\n"
        "句子要短，说人话，避免书面腔、空洞金句和夸张承诺。\n"
        "不要在口播正文中写出结构名称、章节标题、字数说明或创作解释。\n"
        f"正文去除空格和换行后不超过1300个字符。\n"
        "只返回 JSON，字段为 title、content、hook、closing、estimatedSeconds。"
    )

    length_guide = {
        30: "30秒内（约110-150字）",
        60: "60秒内（约220-260字）",
        90: "90秒内（约320-390字）",
        120: "120秒内（约480-560字）",
        180: "180秒内（约720-820字）",
    }
    dur = min(300, max(15, duration_seconds))
    guide = length_guide.get(dur, f"{dur}秒内")

    prompt = (
        f"零散想法：{ideas}\n"
        f"目标受众：{audience}\n"
        f"口吻：{tone}\n"
        f"目标时长：{guide}，去除空格和换行后不超过目标字数\n"
    )

    result = _deepseek([
        {"role": "system", "content": system},
        {"role": "user", "content": prompt},
    ])

    try:
        parsed = json.loads(result)
        # 简单验证
        if "title" in parsed and "content" in parsed:
            return json.dumps({
                "status": "success",
                **parsed,
            })
    except json.JSONDecodeError:
        pass

    return json.dumps({
        "status": "error",
        "message": "文案生成失败，请重试",
        "raw": result[:200],
    })


# ========== Tool 2: 分析文案提炼标题/封面 ==========
@function_tool
def analyze_script(
    content: Annotated[str, "已确认的口播文案内容"],
) -> str:
    """
    对已确认的口播文案进行深度分析，提炼出视频标题、封面文案、关键词等。
    返回 JSON：{coreTitle, alternativeTitles, coverSubtitle, keywords, contentType, emotion}
    """
    system = (
        "你是中文短视频内容总监，负责把已经定稿的口播文案提炼成视频标题和封面文案。\n"
        "核心标题必须能准确概括内容，又能制造好奇、冲突或明确利益点；不允许标题党与虚假承诺。\n"
        "只返回JSON：coreTitle、alternativeTitles、coverSubtitle、keywords、contentType、emotion。"
    )

    result = _deepseek([
        {"role": "system", "content": system},
        {"role": "user", "content": f"定稿口播文案：\n{content}"},
    ], max_tokens=600)

    try:
        parsed = json.loads(result)
        if "coreTitle" in parsed:
            return json.dumps({"status": "success", **parsed})
    except json.JSONDecodeError:
        pass

    return json.dumps({
        "status": "error",
        "message": "文案分析失败，请重试",
        "raw": result[:200],
    })


# ========== Tool 3: 生成封面图 ==========
@function_tool
def generate_cover_image(
    prompt: Annotated[str, "封面图片的描述或标题"],
    size: Annotated[str, "画幅比例，9:16 或 16:9"] = "9:16",
) -> str:
    """
    根据标题/描述，调用火山引擎 Image2 API 生成短视频封面图。
    """
    if not IMAGE2_KEY:
        return json.dumps({
            "status": "error",
            "message": "IMAGE2_API_KEY 未配置，请在 EdgeOne Makers 控制台设置环境变量 IMAGE2_API_KEY",
            "hint": "Image2 API Key 可在火山引擎申请：https://www.volcengine.com/product/imagex",
        })

    try:
        payload = {
            "model": "image-2",
            "prompt": f"中文短视频封面，{prompt}，高质量，真实感人",
            "aspect_ratio": size,
            "return_url": True,
        }

        with httpx.AsyncClient(timeout=60.0) as client:
            resp = client.post(
                f"{IMAGE2_BASE}/image_generation",
                headers={
                    "Authorization": f"Bearer {IMAGE2_KEY}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            result = resp.json()

            if resp.status_code == 200 and result.get("data", {}).get("image_urls"):
                urls = result["data"]["image_urls"]
                return json.dumps({"status": "success", "image_url": urls[0], "all_urls": urls})
            else:
                return json.dumps({
                    "status": "error",
                    "message": result.get("message", "封面图生成失败"),
                    "detail": result,
                })
    except Exception as e:
        return json.dumps({"status": "error", "message": f"封面图生成失败: {str(e)}"})


# ========== Tool 4: 生成数字人口播视频 ==========
@function_tool
def call_digital_human(
    script: Annotated[str, "口播文案内容"],
    voice_asset_id: Annotated[str, "声音素材ID（益民居平台）"] = "",
    template_id: Annotated[str, "数字人模板ID（益民居平台）"] = "",
) -> str:
    """
    调用益民居·数字人（闪剪）API 生成口播视频。
    当前 API Key 未配置时，返回提示信息。
    """
    if not CHUANSHEN_API_KEY:
        return json.dumps({
            "status": "pending",
            "message": "益民居·数字人 API Key 未配置，请在 EdgeOne Makers 控制台设置环境变量 CHUANSHEN_API_KEY",
            "hint": "数字人 API Key 可在 https://szr.yiminju.xyz/account 申请",
        })

    try:
        with httpx.AsyncClient(timeout=30.0) as client:
            resp = client.post(
                f"{CHUANSHEN_API_BASE}/generation-jobs",
                headers={
                    "Authorization": f"Bearer {CHUANSHEN_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "script": script,
                    "voice_asset_id": voice_asset_id,
                    "template_id": template_id,
                },
            )
            result = resp.json()

            if resp.status_code == 200:
                job_id = result.get("data", {}).get("id") or result.get("id")
                if job_id:
                    return json.dumps({
                        "status": "success",
                        "job_id": job_id,
                        "message": "数字人视频生成任务已提交，请等待完成",
                    })
            return json.dumps({
                "status": "error",
                "message": result.get("error", {}).get("message", "数字人API调用失败"),
                "detail": result,
            })
    except Exception as e:
        return json.dumps({"status": "error", "message": f"数字人API调用失败: {str(e)}"})
