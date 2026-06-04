# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import json
import os
import re
import base64
import logging

from dotenv import load_dotenv
from strands import Agent
from strands.models import BedrockModel
from strands.handlers.callback_handler import PrintingCallbackHandler
from bedrock_agentcore.runtime import BedrockAgentCoreApp

from bedrock_agentcore.memory.integrations.strands.config import AgentCoreMemoryConfig
from bedrock_agentcore.memory.integrations.strands.session_manager import AgentCoreMemorySessionManager

from mcp.client.streamable_http import streamablehttp_client
from strands.tools.mcp.mcp_client import MCPClient
from gateway_cognito import token

# =========================
# 基础配置
# =========================
load_dotenv()
gateway_url = os.getenv("GATEWAY_URL")
region = os.getenv("AWS_REGION")
memory_id = os.getenv("MEMORY_ID")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("techbot")

# =========================
# MCP + AgentCore 初始化
# =========================
def create_streamable_http_transport():
    return streamablehttp_client(gateway_url, headers={"Authorization": f"Bearer {token}"})

app = BedrockAgentCoreApp()

model_id = os.getenv("MODEL_ID")
bedrock_model = BedrockModel(
    model_id=model_id,
)

MAIN_SYSTEM_PROMPT = """
Your Background:
You are TechBot, an AWS technical assistant that answers questions about AWS services, architecture, pricing, and customer cases.
Users may ask in Chinese or English. By default, assume questions are about AWS Global regions unless explicitly specified as China/Beijing/Ningxia regions.
AWS services vary significantly between China and Global regions - ensure you use the correct skills. Switching between China and Global region tools without explicit specification will produce incorrect answers. China region special consideration: Services mentioned in China Blogs does not guarantee availability in AWS China region. Always check and declare service availability in AWS China region when relevant, rather than asking the user to check themselves.

Your Available Tools:

1. **AWS Global Region Documentation & Blogs** — For AWS docs, best practices, and solutions
   Tools: `TechbotGlobalKnowledge___aws___search_documentation`, `TechbotGlobalKnowledge___aws___read_documentation`, `TechbotGlobalKnowledge___aws___recommend`

2. **AWS China Region Documentation** — For AWS China region docs and service availability
   Tools: `TechbotChinaKnowledge___get_China_available_services`, `TechbotChinaKnowledge___read_China_documentation`

3. **AWS Pricing** (both China and Global regions) — Follow this sequence:
   Step 1: `TechbotPricing___get_pricing_service_codes` → current service codes
   Step 2: `TechbotPricing___get_pricing_service_attributes` → filter attributes (e.g., instanceType, region)
   Step 3: `TechbotPricing___get_pricing_attribute_values` → valid values (params: service_code, attribute_name)
   Step 4: `TechbotPricing___get_pricing` → actual pricing using validated parameters
   Optional: `TechbotPricing___get_price_list_urls`, `TechbotPricing___generate_cost_report` (only when user explicitly requests)
   WARNING: Service codes and attributes change frequently. Always follow Steps 1-3 before calling get_pricing.

4. **AWS Customer Stories** — Customer success stories and case studies
   Tools: `TechbotCustomerStory___search_stories`, `TechbotCustomerStory___read_story`

5. **Kiro Knowledge** — For questions about Kiro (AWS's AI-powered IDE and CLI), including features, setup, specs, hooks, steering, and MCP
   Tools: `TechbotKiroKnowledge___kiro_search`, `TechbotKiroKnowledge___kiro_read`

6. **AWS Account Operations** — Query, create, and modify resources in the user's AWS account
   Tools: `aws___call_aws`, `aws___suggest_aws_commands`, `aws___run_script`, `aws___retrieve_skill`

   Use cases: list EC2 instances, view S3 buckets, check CloudWatch alarms, query cost/usage, list Lambda functions, create S3 buckets, start/stop EC2 instances, modify resource tags and configurations.

   Rules:
   - Read operations (Describe*, List*, Get*) can be executed freely
   - Create and modify operations (Create*, Put*, Start*, Stop*, Tag*, Update*) are allowed
   - NEVER execute delete or destructive operations (Delete*, Terminate*, Remove*, Destroy*)
   - If user requests a destructive operation, politely explain that delete operations are not supported for safety reasons
   - Use `aws___suggest_aws_commands` first if unsure about the correct API syntax
   - Always specify the region parameter when calling AWS APIs
   - When creating or modifying resources, confirm the action with the user before executing
   - For complex multi-step operations where you are unsure about best practices, use search_documentation to find a skill, then retrieve_skill to get the step-by-step procedure
   - For simple operations (listing resources, checking status, adding a tag, querying costs), execute directly
   - If a tool call fails, do NOT give up. Try an alternative approach or answer based on information already gathered

Efficiency Rules:
- When answering simple questions, reply briefly but keep necessary details
- When searching documentation/blogs, use the right AWS service name. If unsure, search with user terms directly instead of guessing.
- Immediately stop when you have sufficient information to answer
- User doesn't need to code directly, so don't search for unnecessary "additional/detailed information". Efficiency over comprehensiveness.
- Answer directly - users will follow up if needed
- Minimize tool calls: if you can answer from context or previous results, do not call tools again
- IMPORTANT: Limit to 5 tool calls maximum per response. If the task needs more, summarize what you found so far and ask the user if they want you to continue.
- ALWAYS prefer aws___run_script (write a Python script to do everything in one call) over multiple aws___call_aws calls. For example, to query costs by service, write one Python script that calls Cost Explorer API and formats the result, instead of calling aws___call_aws 10+ times.
- Never call more than 2 tools for a simple factual question
- When asked about a product/service and you're uncertain if it's an AWS service:
  - First use `TechbotGlobalKnowledge___aws___search_documentation` to verify if it exists in AWS
  - If found, proceed; if not, politely clarify you only assist with AWS questions
- DO NOT answer questions about other cloud providers or technology companies.

Output Requirements and Format:
- Be concise and direct
- DO NOT use any heading symbols (#, ##, ###, etc.)
- Use bold text (**text**) for section titles
- Maintain clean, compact and readable structure
- Use at most 2 tables per response. If more data needs to be presented, use bullet lists instead of additional tables.
- Match the user's language (English/Chinese)
- When including code examples, use proper code fences with language specification
- Include reference links at the end of responses for sources you cited. Each case study, doc page, or blog post mentioned should have its own link — avoid merging into one generic link.
- Use a horizontal rule (---) to separate main content from references
- When presenting multiple customer stories, group by topic using bold section titles, list each as a bullet with company name in bold. Do NOT merge stories into a single paragraph.

For Chinese responses:
---
参考链接：
- [链接标题](URL)
- [链接标题](URL)
- [链接标题](URL)

IMPORTANT: Never output <thinking> tags or any internal reasoning blocks in your response. Respond directly to the user.
"""


# =========================
# 工具函数
# =========================
def fix_tool_use_result_mismatch(messages: list) -> list:
    """Fix Memory-restored messages where toolResult/toolUse pairs are broken.

    Handles:
    1. toolResult in user message but previous assistant has no toolUse → remove toolResult
    2. toolResult count exceeds toolUse count → keep only matching ones
    3. user message with only toolResult and no preceding toolUse → remove entire message

    See: https://github.com/strands-agents/sdk-python/issues/1111
    """
    for i, msg in enumerate(messages):
        if msg.get("role") == "user":
            has_tool_results = any("toolResult" in c for c in msg.get("content", []))
            if not has_tool_results:
                continue

            # Find the preceding assistant message's toolUse IDs
            tool_use_ids = set()
            if i > 0:
                prev_msg = messages[i - 1]
                if prev_msg.get("role") == "assistant":
                    tool_use_ids = {
                        c["toolUse"]["toolUseId"]
                        for c in prev_msg.get("content", [])
                        if "toolUse" in c
                    }

            # Remove toolResults that don't have a matching toolUse
            msg["content"] = [
                c for c in msg.get("content", [])
                if "toolResult" not in c or c["toolResult"].get("toolUseId") in tool_use_ids
            ]

    return [m for m in messages if m.get("content")]


def extract_text_from_agent_message(message: dict) -> str:
    """Extract visible text blocks from agent response message."""
    if not message:
        return ""
    parts = []
    for block in (message.get("content") or []):
        if isinstance(block, dict) and "text" in block and block["text"]:
            parts.append(block["text"])
    return "\n".join(parts).strip()


# =========================
# Ping
# =========================
class PingResponse:
    def __init__(self):
        self.value = "healthy"

healthy_status = PingResponse()


# =========================
# AgentCore 入口
# =========================
@app.entrypoint
async def invoke(payload):
    """AgentCore entrypoint. Payload from worker Lambda:
    {
        "actor_id": "...",
        "session_id": "...",
        "channel_id": "...",
        "prompt": "...",
        "encoded_images": [{"format":"png","source":{"bytes":"<base64>"}}]
    }
    """
    client = MCPClient(create_streamable_http_transport)
    with client:
        user_text = (payload.get("prompt") or "").strip() or "你好"
        actor_id = payload.get("actor_id", "anonymous")
        session_id = payload.get("session_id") or payload.get("channel_id", "default")

        tools = client.list_tools_sync()

        # Memory session manager (optional, controlled by MEMORY_ID env var)
        session_manager = None
        if memory_id:
            config = AgentCoreMemoryConfig(
                memory_id=memory_id,
                session_id=session_id,
                actor_id=actor_id,
            )
            session_manager = AgentCoreMemorySessionManager(
                agentcore_memory_config=config,
                region_name=region,
            )

        agent = Agent(
            system_prompt=MAIN_SYSTEM_PROMPT,
            session_manager=session_manager,
            model=bedrock_model,
            tools=tools,
            record_direct_tool_call=False,
            callback_handler=PrintingCallbackHandler(),
        )

        # Fix Memory-restored messages before each model call (after session_manager restores history)
        from strands.hooks import BeforeToolCallEvent, BeforeModelCallEvent

        def fix_history_before_model_call(event: BeforeModelCallEvent):
            if agent.messages:
                agent.messages = fix_tool_use_result_mismatch(agent.messages)

        agent.hooks.add_callback(BeforeModelCallEvent, fix_history_before_model_call)

        # Limit tool calls — use cancel_tool instead of RuntimeError to prevent memory corruption
        tool_call_count = {"n": 0}

        def check_tool_limit(event: BeforeToolCallEvent):
            tool_call_count["n"] += 1
            if tool_call_count["n"] >= 20:
                logger.warning(f"⚠️ Tool call limit reached (20)")
                event.cancel_tool = "工具调用次数超过上限（20次），请用已有信息回答用户。"

        agent.hooks.add_callback(BeforeToolCallEvent, check_tool_limit)

        healthy_status.value = "HealthyBusy"
        logger.info(f"🚀 Agent job starts | actor={actor_id} session={session_id}")

        final_text = ""
        try:
            # Handle image inputs
            images = payload.get("image") or payload.get("encoded_images") or []
            images = list(images) if isinstance(images, (list, tuple)) else []

            if images:
                logger.info(f"🖼️ text & image request. images={len(images)}")
                full_prompt = [{"text": user_text}]
                ok_images = 0
                for idx, img in enumerate(images):
                    try:
                        b64 = img.get("source", {}).get("bytes")
                        if isinstance(b64, str) and b64:
                            img["source"]["bytes"] = base64.b64decode(b64)
                            full_prompt.append({"image": img})
                            ok_images += 1
                        elif isinstance(b64, (bytes, bytearray)) and len(b64) > 0:
                            full_prompt.append({"image": img})
                            ok_images += 1
                    except Exception as e:
                        logger.warning(f"⚠️ image[{idx}] decode failed: {e}")
                result = await agent.invoke_async(full_prompt if ok_images > 0 else user_text)
            else:
                logger.info("📝 plain text request")
                result = await agent.invoke_async(user_text)

            msg = getattr(result, "message", None)
            if isinstance(msg, dict):
                final_text = extract_text_from_agent_message(msg)

        except Exception as e:
            logger.exception("Agent invoke failed")
            final_text = f"发生错误：{str(e)}"

        # Token usage logging
        try:
            metrics = getattr(agent, "event_loop_metrics", None)
            if metrics and hasattr(metrics, "accumulated_usage"):
                usage = metrics.accumulated_usage
                input_t = usage.get("inputTokens", 0) if isinstance(usage, dict) else getattr(usage, "inputTokens", 0)
                output_t = usage.get("outputTokens", 0) if isinstance(usage, dict) else getattr(usage, "outputTokens", 0)
                total_t = usage.get("totalTokens", 0) if isinstance(usage, dict) else getattr(usage, "totalTokens", 0)
                logger.info(f"📊 Token usage | input={input_t} output={output_t} total={total_t}")
            else:
                logger.info("📊 Token usage | metrics not available")
        except Exception as e:
            logger.warning(f"📊 Token usage | failed to read metrics: {e}")

        healthy_status.value = "Healthy"
        logger.info("agent job ends")

        return {
            "status": "completed",
            "response": final_text,
            "length": len(final_text or ""),
        }


@app.ping
def ping():
    return healthy_status


if __name__ == "__main__":
    logger.info("🚀 Starting TechBot Agent...")
    logger.info(f"📍 Gateway URL: {gateway_url}")
    logger.info(f"📍 Memory ID: {memory_id}")
    app.run()
