# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

"""WeCom Smart-Robot Handler Lambda — verifies signature, decrypts JSON callback,
triggers worker async.

Smart-robot (智能机器人) flow, per WeCom docs (path/101033, 101138):
- GET  (URL verification): decrypt echostr, return plaintext (same as before)
- POST (message callback):  body is JSON {"encrypt": "..."}, decrypt to plaintext
        JSON containing the message + a `response_url`. We async-invoke the worker
        with that response_url, and return empty 200 immediately. The worker later
        POSTs the answer to response_url (no access_token / trusted-IP needed).

Note: for internal smart robots, the crypto receive_id must be "" (empty string).
"""

import os
import re
import json
import boto3

from wecom_crypt import WeComCrypt, WeComCryptError

lambda_client = boto3.client("lambda")
sm_client = boto3.client("secretsmanager")

WORKER_FUNCTION_NAME = os.environ.get("WEWORK_WORKER_FUNCTION_NAME", "")
SECRET_ARN = os.environ.get("WEWORK_SECRET_ARN", "")

_cached_secret = None


def get_secret() -> dict:
    global _cached_secret
    if not _cached_secret:
        resp = sm_client.get_secret_value(SecretId=SECRET_ARN)
        _cached_secret = json.loads(resp["SecretString"])
    return _cached_secret


def _text_response(code: int, body: str):
    """WeCom expects plain text (not JSON) for callback responses."""
    return {
        "statusCode": code,
        "headers": {"Content-Type": "text/plain; charset=utf-8"},
        "body": body,
    }


def lambda_handler(event, context):
    print("Raw Event:", json.dumps(event, ensure_ascii=False)[:2000])

    secret = get_secret()
    token = secret.get("TOKEN", "")
    aes_key = secret.get("ENCODING_AES_KEY", "")
    # Internal smart robot: receive_id must be empty string
    crypto = WeComCrypt(token, aes_key, "")

    method = event.get("httpMethod", "")
    params = event.get("queryStringParameters") or {}
    msg_signature = params.get("msg_signature", "")
    timestamp = params.get("timestamp", "")
    nonce = params.get("nonce", "")

    # === GET: URL verification ===
    if method == "GET":
        echostr = params.get("echostr", "")
        try:
            plain = crypto.verify_url(msg_signature, timestamp, nonce, echostr)
            return _text_response(200, plain)
        except WeComCryptError as e:
            print(f"URL verify failed: {e}")
            return _text_response(403, "verify failed")

    # === POST: message callback (JSON) ===
    body = event.get("body") or ""
    try:
        plain = crypto.decrypt_json_message(body, msg_signature, timestamp, nonce)
    except (WeComCryptError, KeyError, ValueError) as e:
        print(f"Decrypt failed: {e}")
        return _text_response(403, "decrypt failed")

    try:
        msg = json.loads(plain)
    except ValueError:
        print(f"Plaintext not JSON: {plain[:200]}")
        return _text_response(200, "")
    print("Decrypted message:", json.dumps(msg, ensure_ascii=False)[:1000])

    # Extract text + response_url (defensive across possible schemas)
    msgtype = msg.get("msgtype", "")
    text = ""
    if msgtype == "text":
        text = (msg.get("text", {}).get("content") or "").strip()
        # Strip leading "@RobotName" mention added when @-ing the bot in a group
        text = re.sub(r"^@\S+\s*", "", text).strip()
    response_url = msg.get("response_url", "")
    from_userid = (msg.get("from", {}) or {}).get("userid", "") or msg.get("from_userid", "")
    chat_id = msg.get("chatid", "")
    chat_type = msg.get("chattype", "")

    # Only handle text messages that carry a response_url
    if not text or not response_url:
        return _text_response(200, "")

    # Async-invoke worker; return empty 200 immediately. Worker replies via response_url.
    worker_payload = {
        "channel": "wework",
        "response_url": response_url,
        "from_userid": from_userid,
        "chat_id": chat_id,
        "chat_type": chat_type,
        "prompt": text,
    }
    lambda_client.invoke(
        FunctionName=WORKER_FUNCTION_NAME,
        InvocationType="Event",
        Payload=json.dumps(worker_payload, ensure_ascii=False).encode("utf-8"),
    )
    return _text_response(200, "")
