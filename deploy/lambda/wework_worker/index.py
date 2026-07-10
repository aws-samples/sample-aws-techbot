# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

"""WeCom Smart-Robot Worker Lambda — calls AgentCore, replies via response_url.

Smart-robot flow (WeCom docs path/101138):
  1. Handler decrypts the callback and passes the `response_url` here.
  2. Invoke AgentCore Runtime (shared with Feishu, channel="wework"), 30-240s.
  3. POST the answer (plaintext JSON) to response_url — no access_token, no
     trusted-IP, no encryption needed.

Note: each response_url can be called only ONCE and expires in 1 hour, so we
send only the final answer (no separate "processing" message).
Smart-robot markdown supports tables and up to 20480 bytes.
"""

import os
import json
import boto3
import requests

AGENT_RUNTIME_ARN = os.environ.get("AGENT_RUNTIME_ARN", "")
REGION = os.environ.get("AGENTCORE_REGION") or os.environ.get("AWS_REGION", "us-west-2")

# Smart-robot markdown content limit: 20480 bytes
WECOM_MSG_MAX_BYTES = 20000  # headroom under 20480


def truncate_bytes(text: str, max_bytes: int = WECOM_MSG_MAX_BYTES) -> str:
    encoded = text.encode("utf-8")
    if len(encoded) <= max_bytes:
        return text
    return encoded[:max_bytes].decode("utf-8", errors="ignore") + "\n\n…（内容过长已截断）"


def reply_via_response_url(response_url: str, markdown: str) -> None:
    """Reply to the smart-robot callback by POSTing plaintext JSON to response_url."""
    payload = {
        "msgtype": "markdown",
        "markdown": {"content": truncate_bytes(markdown)},
    }
    r = requests.post(
        response_url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        timeout=10,
    )
    print(f"response_url reply status={r.status_code} body={r.text[:300]}")


def invoke_agentcore(payload: dict) -> str:
    from botocore.config import Config
    client = boto3.client(
        "bedrock-agentcore",
        region_name=REGION,
        config=Config(read_timeout=450, connect_timeout=10),
    )
    response = client.invoke_agent_runtime(
        agentRuntimeArn=AGENT_RUNTIME_ARN,
        payload=json.dumps(payload, ensure_ascii=False),
    )
    response_body = response["response"].read()
    if isinstance(response_body, (bytes, bytearray)):
        response_body = response_body.decode("utf-8", errors="replace")
    response_data = json.loads(response_body)
    return response_data.get("response", "")


def lambda_handler(event, context):
    print("Worker Event:", json.dumps(event, ensure_ascii=False)[:1000])

    response_url = event.get("response_url", "")
    prompt = event.get("prompt", "")
    from_userid = event.get("from_userid", "")
    chat_id = event.get("chat_id", "")
    if not response_url or not prompt:
        return {"statusCode": 200, "body": json.dumps({"msg": "missing_fields"})}

    # Invoke AgentCore (shared Runtime, channel=wework).
    # session_id: per-chat in group, per-user in single chat.
    agent_payload = {
        "channel": "wework",
        "actor_id": from_userid or "wecom-user",
        "session_id": chat_id or from_userid or "wecom-session",
        "prompt": prompt,
    }
    try:
        final_text = invoke_agentcore(agent_payload)
    except Exception as e:
        print(f"❌ AgentCore invoke failed: {e}")
        final_text = "❌ 处理失败，请稍后重试。"

    # Reply via response_url (once, within 1 hour)
    try:
        reply_via_response_url(response_url, final_text or "（无内容）")
    except Exception as e:
        print(f"❌ reply via response_url failed: {e}")

    return {"statusCode": 200, "body": json.dumps({"msg": "ok"})}
