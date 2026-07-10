# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

"""WeCom (Enterprise WeChat) message encryption/decryption.

Implements the official WeCom callback crypto scheme:
- AES-256-CBC with PKCS#7 padding
- Signature: sha1(sorted([token, timestamp, nonce, encrypt]))
- Plaintext frame: random(16B) + msg_len(4B network order) + msg + receiveid

Ported from the official WXBizMsgCrypt reference. Depends on `cryptography`.
"""

import base64
import hashlib
import socket
import struct
import xml.etree.ElementTree as ET

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend


class WeComCryptError(Exception):
    pass


def _sha1_signature(token: str, timestamp: str, nonce: str, encrypt: str) -> str:
    """Compute msg_signature = sha1 of sorted 4 values joined."""
    items = sorted([token, timestamp, nonce, encrypt])
    return hashlib.sha1("".join(items).encode("utf-8")).hexdigest()


def _pkcs7_unpad(data: bytes) -> bytes:
    pad = data[-1]
    if pad < 1 or pad > 32:
        return data
    return data[:-pad]


def _pkcs7_pad(data: bytes, block_size: int = 32) -> bytes:
    pad = block_size - (len(data) % block_size)
    return data + bytes([pad] * pad)


class WeComCrypt:
    def __init__(self, token: str, encoding_aes_key: str, receive_id: str):
        """
        token: 自建应用「接收消息」里设置的 Token
        encoding_aes_key: 43 位 EncodingAESKey
        receive_id: 企业 CorpID
        """
        self.token = token
        self.receive_id = receive_id
        # EncodingAESKey is 43 chars; append '=' to make valid base64 -> 32 bytes
        self.aes_key = base64.b64decode(encoding_aes_key + "=")
        if len(self.aes_key) != 32:
            raise WeComCryptError(f"Invalid AESKey length: {len(self.aes_key)} (expected 32)")
        self.iv = self.aes_key[:16]

    def _decrypt(self, encrypt_b64: str) -> str:
        """AES-CBC decrypt -> parse frame -> verify receiveid -> return message XML."""
        cipher_data = base64.b64decode(encrypt_b64)
        decryptor = Cipher(
            algorithms.AES(self.aes_key), modes.CBC(self.iv), backend=default_backend()
        ).decryptor()
        plain = decryptor.update(cipher_data) + decryptor.finalize()
        plain = _pkcs7_unpad(plain)

        # frame: random(16) + msg_len(4, network order) + msg + receiveid
        content = plain[16:]
        msg_len = socket.ntohl(struct.unpack("I", content[:4])[0])
        msg = content[4 : 4 + msg_len].decode("utf-8")
        receive_id = content[4 + msg_len :].decode("utf-8")

        if receive_id != self.receive_id:
            raise WeComCryptError("receive_id mismatch — possible forged request")
        return msg

    def _encrypt(self, plain_msg: str) -> str:
        """Wrap message in frame + AES-CBC encrypt -> base64."""
        import os as _os
        random16 = _os.urandom(16)
        msg_bytes = plain_msg.encode("utf-8")
        frame = (
            random16
            + struct.pack("I", socket.htonl(len(msg_bytes)))
            + msg_bytes
            + self.receive_id.encode("utf-8")
        )
        frame = _pkcs7_pad(frame)
        encryptor = Cipher(
            algorithms.AES(self.aes_key), modes.CBC(self.iv), backend=default_backend()
        ).encryptor()
        cipher_data = encryptor.update(frame) + encryptor.finalize()
        return base64.b64encode(cipher_data).decode("utf-8")

    def verify_url(self, msg_signature: str, timestamp: str, nonce: str, echostr: str) -> str:
        """URL 验证：校验签名 -> 解密 echostr -> 返回明文（用于回调 GET 验证）。"""
        sig = _sha1_signature(self.token, timestamp, nonce, echostr)
        if sig != msg_signature:
            raise WeComCryptError("URL verify signature mismatch")
        return self._decrypt(echostr)

    def decrypt_message(self, post_body: str, msg_signature: str, timestamp: str, nonce: str) -> str:
        """解密 POST 回调消息：从 XML 取 Encrypt -> 校验签名 -> 解密 -> 返回明文 XML。"""
        root = ET.fromstring(post_body)
        encrypt = root.find("Encrypt").text
        sig = _sha1_signature(self.token, timestamp, nonce, encrypt)
        if sig != msg_signature:
            raise WeComCryptError("POST message signature mismatch")
        return self._decrypt(encrypt)

    def decrypt_json_message(self, post_body: str, msg_signature: str, timestamp: str, nonce: str) -> str:
        """智能机器人：从 JSON body {"encrypt": "..."} 取 encrypt -> 校验签名 -> 解密 -> 返回明文 JSON。"""
        import json as _json
        data = _json.loads(post_body)
        encrypt = data["encrypt"]
        sig = _sha1_signature(self.token, timestamp, nonce, encrypt)
        if sig != msg_signature:
            raise WeComCryptError("POST message signature mismatch")
        return self._decrypt(encrypt)


def parse_text_message(xml_str: str) -> dict:
    """解析解密后的明文 XML，提取常用字段。"""
    root = ET.fromstring(xml_str)

    def _t(tag):
        el = root.find(tag)
        return el.text if el is not None else ""

    return {
        "from_user": _t("FromUserName"),   # 发消息的成员 UserID
        "to_user": _t("ToUserName"),       # CorpID
        "msg_type": _t("MsgType"),
        "content": _t("Content"),          # 文本内容
        "msg_id": _t("MsgId"),             # 用于幂等去重
        "agent_id": _t("AgentID"),
        "create_time": _t("CreateTime"),
    }
