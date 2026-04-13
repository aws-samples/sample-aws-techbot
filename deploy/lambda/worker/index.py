# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

"""TechBot Worker Lambda - processes Feishu message, calls AgentCore, patches card."""

import os
import json
import re
import time
import base64
import boto3
import requests

FEISHU_TOKEN_URL = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
FEISHU_REPLY_URL = "https://open.feishu.cn/open-apis/im/v1/messages/{message_id}/reply"
FEISHU_PATCH_URL = "https://open.feishu.cn/open-apis/im/v1/messages/{message_id}"
FEISHU_MSG_RESOURCE_URL = "https://open.feishu.cn/open-apis/im/v1/messages/{message_id}/resources/{file_key}"

AGENT_RUNTIME_ARN = os.environ.get("AGENT_RUNTIME_ARN", "")
REGION = os.environ.get("AGENTCORE_REGION") or os.environ.get("AWS_REGION", "us-west-2")
SECRET_ARN = os.environ.get("SECRET_ARN", "")

# Cache Feishu credentials from Secrets Manager
_feishu_creds = None

def get_feishu_creds() -> dict:
    global _feishu_creds
    if not _feishu_creds:
        sm = boto3.client("secretsmanager")
        resp = sm.get_secret_value(SecretId=SECRET_ARN)
        _feishu_creds = json.loads(resp["SecretString"])
    return _feishu_creds


# =========================
# Feishu helpers
# =========================
def get_tenant_token() -> str:
    creds = get_feishu_creds()
    res = requests.post(
        FEISHU_TOKEN_URL,
        json={"app_id": creds["APP_ID"], "app_secret": creds["APP_SECRET"]},
        timeout=5,
    )
    res.raise_for_status()
    data = res.json()
    token = data.get("tenant_access_token")
    if not token:
        raise RuntimeError(f"Feishu token missing: {data}")
    return token


def extract_post_text_and_images(content_obj: dict):
    image_keys = []
    texts = []
    blocks = content_obj.get("content", [])
    for line in blocks:
        if not isinstance(line, list):
            continue
        for node in line:
            if not isinstance(node, dict):
                continue
            tag = node.get("tag")
            if tag == "text":
                t = node.get("text", "")
                if t:
                    texts.append(t)
            elif tag == "img":
                k = node.get("image_key")
                if k:
                    image_keys.append(k)
    text = " ".join(t.strip() for t in texts if t and t.strip()).strip()
    return text, image_keys


def feishu_message_resource_to_base64(message_id: str, file_key: str, tenant_token: str, rtype: str = "image"):
    url = FEISHU_MSG_RESOURCE_URL.format(message_id=message_id, file_key=file_key)
    r = requests.get(
        url,
        headers={"Authorization": f"Bearer {tenant_token}"},
        params={"type": rtype},
        timeout=30,
    )
    r.raise_for_status()
    if len(r.content) > 5 * 1024 * 1024:
        raise ValueError("image_too_large")
    content_type = r.headers.get("Content-Type", "application/octet-stream")
    fmt = content_type.split("/")[-1].split(";")[0].strip()
    encoded = base64.b64encode(r.content).decode("utf-8")
    return {"format": fmt, "source": {"bytes": encoded}}


def build_card(markdown: str) -> str:
    card_v2 = {
        "schema": "2.0",
        "config": {"update_multi": True},
        "body": {"elements": [{"tag": "markdown", "content": markdown}]},
    }
    return json.dumps(card_v2, ensure_ascii=False)


def feishu_reply_card(token: str, message_id: str, uuid: str, markdown: str) -> str:
    r = requests.post(
        FEISHU_REPLY_URL.format(message_id=message_id),
        headers={"Authorization": f"Bearer {token}"},
        json={
            "msg_type": "interactive",
            "content": build_card(markdown),
            "uuid": uuid,
        },
        timeout=5,
    )
    r.raise_for_status()
    j = r.json()
    if j.get("code", 0) != 0:
        raise RuntimeError(f"Feishu reply failed: {j}")
    return j["data"]["message_id"]


def feishu_patch_card(token: str, message_id: str, markdown: str) -> None:
    r = requests.patch(
        FEISHU_PATCH_URL.format(message_id=message_id),
        headers={"Authorization": f"Bearer {token}"},
        json={"content": build_card(markdown)},
        timeout=5,
    )
    if r.status_code != 200:
        raise RuntimeError(f"Feishu patch HTTP {r.status_code}: {r.text}")
    j = r.json()
    if j.get("code", 0) != 0:
        raise RuntimeError(f"Feishu patch failed: {j}")


# =========================
# Event parsing
# =========================
def parse_event(event: dict):
    ev = event.get("event", {}) or {}
    header = event.get("header", {}) or {}
    msg = ev.get("message", {}) or {}
    sender = ev.get("sender", {}) or {}
    sender_id = sender.get("sender_id", {}) or {}

    event_id = header.get("event_id") or str(time.time())
    user_message_id = msg.get("message_id", "")
    chat_id = msg.get("chat_id", "")
    root_id = msg.get("root_id")
    content_raw = msg.get("content", "{}")
    msg_type = msg.get("message_type", "")
    sender_open_id = sender_id.get("open_id") or "anonymous"

    text = ""
    image_keys = []

    try:
        content_obj = json.loads(content_raw)
    except Exception:
        content_obj = {}

    if msg_type == "post":
        text, image_keys = extract_post_text_and_images(content_obj)
    else:
        text = (content_obj.get("text") or "").strip()

    text = re.sub(r"^@_user_\d+\s*", "", text).strip()
    if not text:
        text = "你好"

    thread_id = root_id or user_message_id or "unknown_thread"
    actor_id = sender_open_id
    session_id = thread_id

    return event_id, user_message_id, chat_id, actor_id, session_id, text, image_keys


# =========================
# AgentCore invocation
# =========================
def invoke_agentcore(payload: dict) -> str:
    client = boto3.client("bedrock-agentcore", region_name=REGION)
    response = client.invoke_agent_runtime(
        agentRuntimeArn=AGENT_RUNTIME_ARN,
        payload=json.dumps(payload, ensure_ascii=False),
    )
    response_body = response["response"].read()
    if isinstance(response_body, (bytes, bytearray)):
        response_body = response_body.decode("utf-8", errors="replace")
    response_data = json.loads(response_body)
    print("Agent Response:", response_data)
    return response_data.get("response", "")


# =========================
# Lambda entry
# =========================
def lambda_handler(event, context):
    print("Raw Event:", json.dumps(event, ensure_ascii=False))

    if event.get("header", {}).get("event_type") != "im.message.receive_v1":
        return {"statusCode": 200, "body": json.dumps({"msg": "ignored"})}

    # 1) Parse event
    event_id, user_msg_id, chat_id, actor_id, session_id, text, image_keys = parse_event(event)
    if not user_msg_id or not chat_id:
        return {"statusCode": 200, "body": json.dumps({"msg": "missing_ids"})}

    # 2) Feishu token
    try:
        token = get_tenant_token()
    except Exception as e:
        print(f"❌ get_tenant_token failed: {e}")
        return {"statusCode": 200, "body": json.dumps({"msg": "token_failed"})}

    # 3) Reply placeholder card
    try:
        bot_msg_id = feishu_reply_card(
            token=token,
            message_id=user_msg_id,
            uuid=event_id,
            markdown="正在生成中 🤖",
        )
    except Exception as e:
        print(f"❌ Feishu reply failed: {e}")
        return {"statusCode": 200, "body": json.dumps({"msg": "reply_failed"})}

    # 4) Download images to base64
    encoded_images = []
    for k in image_keys:
        try:
            encoded_images.append(
                feishu_message_resource_to_base64(user_msg_id, k, token, rtype="image")
            )
        except ValueError as e:
            if str(e) == "image_too_large":
                feishu_patch_card(token, bot_msg_id, "❌ 图片过大：单张图片不能超过 5MB，请压缩后重试。")
                return {"statusCode": 200, "body": json.dumps({"msg": "image_too_large"})}
            raise
        except Exception as e:
            print(f"⚠️ download image failed: {k}, err={e}")

    # 5) Invoke AgentCore runtime
    agent_payload = {
        "actor_id": actor_id,
        "session_id": session_id,
        "channel_id": chat_id,
        "prompt": text,
        "event_id": event_id,
        "bot_message_id": bot_msg_id,
        "encoded_images": encoded_images,
    }
    print("Agent Payload:", json.dumps(agent_payload, ensure_ascii=False))

    try:
        final_text = invoke_agentcore(agent_payload)
        feishu_patch_card(token, bot_msg_id, final_text)
    except Exception as e:
        print(f"❌ AgentCore invoke failed: {e}")
        err_str = str(e)
        if "doesn't support the image" in err_str or "image content block" in err_str:
            user_msg = "❌ 当前模型不支持图片输入。请切换模型或仅发送文字提问。"
        elif "500" in err_str or "RuntimeClientError" in err_str:
            user_msg = "❌ 服务暂时不可用，AgentCore Runtime 可能正在启动中，请稍后重试。"
        elif "timeout" in err_str.lower() or "timed out" in err_str.lower():
            user_msg = "❌ 请求超时，问题可能比较复杂，请稍后重试或简化问题。"
        elif "ThrottlingException" in err_str or "429" in err_str:
            user_msg = "❌ 请求过于频繁，请稍后再试。"
        else:
            user_msg = "❌ 处理失败，请稍后重试。如持续出现请联系管理员。"
        try:
            feishu_patch_card(token, bot_msg_id, user_msg)
        except Exception as e2:
            print(f"❌ Feishu patch error message failed: {e2}")
        return {"statusCode": 200, "body": json.dumps({"msg": "agentcore_invoke_failed"})}

    return {"statusCode": 200, "body": json.dumps({"msg": "ok"})}
