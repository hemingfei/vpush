#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""雪球加密协商所需的国密原语实现（App 包内权威副本，脚本侧 scripts/xq_app 转发过来）

逆向自 com.xueqiu.enc：
    b.a()   生成 SM2 密钥对（sm2p256v1）
    b.c()   ECDH 共享密钥 → 取 X 坐标
    b.d()   SM3 派生 SM4 密钥（取前 16 字节）
    c.b()   SM4/CBC/PKCS7 加密（key 同时用作 IV）
    a.b()   字节 → 大写 hex

纯 Python 实现 SM2 曲线运算（只用到点加/标量乘，足够），SM3/SM4 走 gmssl。
"""
from __future__ import annotations

import os

from gmssl import func, sm3, sm4

# sm2p256v1（GB/T 32918）
P = 0xFFFFFFFEFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF00000000FFFFFFFFFFFFFFFF
A = 0xFFFFFFFEFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF00000000FFFFFFFFFFFFFFFC
B = 0x28E9FA9E9D9F5E344D5A9E4BCF6509A7F39789F515AB8F92DDBCBD414D940E93
N = 0xFFFFFFFEFFFFFFFFFFFFFFFFFFFFFFFF7203DF6B21C6052B53BBF40939D54123
GX = 0x32C4AE2C1F1981195F9904466A39C9948FE30BBFF2660BE1715A4589334C74C7
GY = 0xBC3736A2F4F6779C59BDCEE36B692153D0A9877CC62A474002DF32E52139F0A0
G = (GX, GY)

Point = tuple[int, int] | None


def _inv(x: int) -> int:
    return pow(x, P - 2, P)


def point_add(p1: Point, p2: Point) -> Point:
    if p1 is None:
        return p2
    if p2 is None:
        return p1
    x1, y1 = p1
    x2, y2 = p2
    if x1 == x2 and (y1 + y2) % P == 0:
        return None
    if p1 == p2:
        lam = (3 * x1 * x1 + A) * _inv(2 * y1) % P
    else:
        lam = (y2 - y1) * _inv((x2 - x1) % P) % P
    x3 = (lam * lam - x1 - x2) % P
    return (x3, (lam * (x1 - x3) - y1) % P)


def point_mul(k: int, pt: Point) -> Point:
    result: Point = None
    addend = pt
    while k:
        if k & 1:
            result = point_add(result, addend)
        addend = point_add(addend, addend)
        k >>= 1
    return result


def to_bytes32(value: int) -> bytes:
    return value.to_bytes(32, "big")


def generate_keypair() -> tuple[int, Point]:
    """生成 SM2 私钥 d 与公钥点 Q。"""
    while True:
        d = int.from_bytes(os.urandom(32), "big") % N
        if d == 0:
            continue
        q = point_mul(d, G)
        if q is not None:
            return d, q


def encode_public_key(q: Point) -> str:
    """非压缩点编码 04||X||Y → 大写 hex（对应 EC point.getEncoded(false)）。"""
    x, y = q  # type: ignore[misc]
    return ("04" + to_bytes32(x).hex() + to_bytes32(y).hex()).upper()


def decode_public_key(pub: str) -> Point:
    """解析服务端返回的公钥（hex，可带 04 前缀）。"""
    s = pub.strip().replace(" ", "")
    if s.startswith("04"):
        s = s[2:]
    if len(s) != 128:
        raise ValueError(f"unexpected public key length: {len(s)}")
    return int(s[:64], 16), int(s[64:], 16)


def ecdh_shared_hex(d: int, peer_pub: Point) -> str:
    """ECDH：S = d·Q，取 X 坐标 → 大写 hex（对应 b.c()）。"""
    s = point_mul(d, peer_pub)
    if s is None:
        raise ValueError("ECDH produced point at infinity")
    return to_bytes32(s[0]).hex().upper()


def sm3_hex(data: bytes, size: int = 32) -> str:
    return sm3.sm3_hash(func.bytes_to_list(data))[: size * 2].upper()


def derive_sm4_key(shared_hex: str) -> str:
    """sm4Key = SM3(共享密钥的 hex 字符串)[前16字节] → 大写 hex（对应 b.d()）。"""
    return sm3_hex(shared_hex.encode("utf-8"), size=16)


def sm4_encrypt_b64(key_hex: str, plaintext: bytes) -> str:
    """SM4/CBC/PKCS7，key 同时作为 IV → Base64（对应 c.b() + a.b()）。"""
    import base64
    key = bytes.fromhex(key_hex)
    cipher = sm4.CryptSM4()
    cipher.set_key(key, sm4.SM4_ENCRYPT)
    # gmssl 的 crypt_cbc 需要 iv 参数，此处按客户端逻辑 key 即 IV
    ct = cipher.crypt_cbc(key, plaintext)
    return base64.b64encode(ct).decode()


def sm4_decrypt_b64(key_hex: str, b64: str) -> bytes:
    import base64
    key = bytes.fromhex(key_hex)
    cipher = sm4.CryptSM4()
    cipher.set_key(key, sm4.SM4_DECRYPT)
    return cipher.crypt_cbc(key, base64.b64decode(b64))


if __name__ == "__main__":
    # 自检：ECDH 对称性、点运算封闭性、SM4 往返
    d1, q1 = generate_keypair()
    d2, q2 = generate_keypair()
    s1 = ecdh_shared_hex(d1, q2)
    s2 = ecdh_shared_hex(d2, q1)
    print(f"ECDH 对称性: {'OK' if s1 == s2 else 'FAIL'}")
    print(f"公钥编码长度: {len(encode_public_key(q1))} (期望 130 = 04+64+64)")
    print(f"n*G == 无穷远点: {point_mul(N, G) is None}")
    k = derive_sm4_key(s1)
    print(f"SM4 key: {k} (len={len(k)})")
    ct = sm4_encrypt_b64(k, b"hello")
    print(f"SM4 往返: {sm4_decrypt_b64(k, ct)}")
