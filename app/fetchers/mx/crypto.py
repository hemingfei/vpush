"""MX platform encryption/decryption module."""
from __future__ import annotations

import hashlib
import json
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import padding
import lzstring

logger = logging.getLogger(__name__)


# 北京时间时区
CN_TZ = timezone(timedelta(hours=8))


def get_beijing_date(offset_days: int = 0) -> datetime:
    """获取偏移后的北京时间日期（仅日期部分）。

    Args:
        offset_days: 偏移天数，正数是未来，负数是过去

    Returns:
        北京时间的 datetime 对象
    """
    now = datetime.now(timezone.utc)
    beijing_now = now.astimezone(CN_TZ)
    target_date = beijing_now.date() + timedelta(days=offset_days)
    return datetime.combine(target_date, datetime.min.time(), tzinfo=CN_TZ)


def get_local_date(offset_days: int = 0) -> datetime:
    """获取本地时间日期（仅日期部分）。

    Args:
        offset_days: 偏移天数，正数是未来，负数是过去

    Returns:
        本地时间的 datetime 对象
    """
    now = datetime.now()
    target_date = now.date() + timedelta(days=offset_days)
    return datetime.combine(target_date, datetime.min.time())


def generate_key(date_str: str) -> tuple[bytes, bytes]:
    """从日期字符串生成 AES 密钥和 IV。

    Args:
        date_str: 日期字符串，格式 "YYYY-MM-DD"

    Returns:
        (key_bytes, iv_bytes) 元组
    """
    md5_hash = hashlib.md5(date_str.encode("utf-8")).hexdigest()
    key = md5_hash[:16].encode("utf-8")
    iv_part = md5_hash[8:14].encode("utf-8")
    iv = iv_part + b"\x00" * (16 - len(iv_part))
    return key, iv


def aes_decrypt(ciphertext: bytes, key: bytes, iv: bytes) -> bytes:
    """AES-128-CBC 解密。

    Args:
        ciphertext: 密文数据
        key: 16字节密钥
        iv: 16字节IV

    Returns:
        解密后的明文
    """
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
    decryptor = cipher.decryptor()
    padded_plaintext = decryptor.update(ciphertext) + decryptor.finalize()
    unpadder = padding.PKCS7(128).unpadder()
    plaintext = unpadder.update(padded_plaintext) + unpadder.finalize()
    return plaintext


def lzstring_decompress(compressed: str) -> str:
    """LZ-String 解压。

    Args:
        compressed: 压缩字符串

    Returns:
        解压后的字符串
    """
    return lzstring.LZString.decompressFromBase64(compressed)


def try_decrypt_with_keys(
    encrypted_data: str,
    date_generator,
    key_offsets: list[int] = None
) -> Any | None:
    """尝试用多个密钥解密数据。

    Args:
        encrypted_data: 加密数据
        date_generator: 日期生成函数
        key_offsets: 密钥偏移天数列表，默认 [0, -1, 1]

    Returns:
        解密后的数据（JSON解析后），失败返回 None
    """
    if key_offsets is None:
        key_offsets = [0, -1, 1]
    
    for offset in key_offsets:
        try:
            date = date_generator(offset)
            date_str = date.strftime("%Y-%m-%d")
            key, iv = generate_key(date_str)
            
            decompressed = lzstring_decompress(encrypted_data)
            if not decompressed:
                continue
            
            ciphertext = decompressed.encode("utf-8")
            plaintext = aes_decrypt(ciphertext, key, iv)
            result = json.loads(plaintext.decode("utf-8"))
            logger.debug(f"Successfully decrypted with offset {offset}")
            return result
        except Exception as e:
            logger.debug(f"Decrypt failed with offset {offset}: {e}")
            continue
    
    return None


def decrypt_api_data(encrypted_data: str) -> dict | list | None:
    """解密 API 响应数据。

    Args:
        encrypted_data: 加密数据字符串

    Returns:
        解密并解析后的 JSON 数据，失败返回 None
    """
    return try_decrypt_with_keys(encrypted_data, get_beijing_date)


def decrypt_ws_data(encrypted_data: str) -> dict | None:
    """解密 WebSocket 消息数据。

    Args:
        encrypted_data: 加密数据字符串

    Returns:
        解密并解析后的 JSON 数据，失败返回 None
    """
    result = try_decrypt_with_keys(encrypted_data, get_local_date)
    if result is None:
        result = try_decrypt_with_keys(encrypted_data, get_beijing_date)
    return result


def decrypt_content(msg: dict) -> str:
    """从 MX 消息中获取内容。

    Args:
        msg: MX 消息字典

    Returns:
        内容字符串
    """
    content = msg.get("message", "") or msg.get("msg", "")
    if content:
        return content
    # 如果没有直接内容，尝试从其他字段获取
    return ""
