"""AES-128-ECB 加解密

微信 CDN 媒体传输使用 AES-128-ECB + PKCS7 填充。
"""

from __future__ import annotations

import base64
import secrets

from Crypto.Cipher import AES


BLOCK_SIZE = 16  # AES block size in bytes


def generate_aes_key() -> bytes:
    """生成随机 16 字节 AES 密钥"""
    return secrets.token_bytes(BLOCK_SIZE)


def pkcs7_pad(data: bytes) -> bytes:
    """PKCS7 填充到 AES 块大小"""
    pad_len = BLOCK_SIZE - (len(data) % BLOCK_SIZE)
    return data + bytes([pad_len] * pad_len)


def pkcs7_unpad(data: bytes) -> bytes:
    """去除 PKCS7 填充"""
    if not data:
        return data
    pad_len = data[-1]
    if pad_len < 1 or pad_len > BLOCK_SIZE:
        return data  # 无效填充，返回原数据
    if data[-pad_len:] != bytes([pad_len] * pad_len):
        return data  # 填充不一致
    return data[:-pad_len]


def aes_ecb_encrypt(plaintext: bytes, key: bytes) -> bytes:
    """AES-128-ECB 加密 + PKCS7 填充"""
    cipher = AES.new(key, AES.MODE_ECB)
    return cipher.encrypt(pkcs7_pad(plaintext))


def aes_ecb_decrypt(ciphertext: bytes, key: bytes) -> bytes:
    """AES-128-ECB 解密 + 去 PKCS7 填充"""
    cipher = AES.new(key, AES.MODE_ECB)
    return pkcs7_unpad(cipher.decrypt(ciphertext))


def encrypted_size(plaintext_size: int) -> int:
    """计算加密后的密文大小（含 PKCS7 填充）"""
    # PKCS7 至少填充 1 字节
    return ((plaintext_size + 1 + BLOCK_SIZE - 1) // BLOCK_SIZE) * BLOCK_SIZE


def parse_aes_key(raw_key: str) -> bytes:
    """解析 CDN 消息中的 AES 密钥

    微信 CDN 消息中的 aes_key 有多种编码格式：
    - 格式 A: base64(raw 16 bytes) → 直接解码
    - 格式 B: base64(32 ASCII hex chars) → 解码后再 hex→bytes
    - 格式 C: 32 字符 hex string → 直接 hex→bytes
    """
    raw = raw_key.strip()
    if not raw:
        raise ValueError("Empty AES key")

    # 格式 C: 直接是 hex string（32 字符 = 16 字节）
    if len(raw) == 32 and all(c in "0123456789abcdefABCDEF" for c in raw):
        return bytes.fromhex(raw)

    # 尝试 base64 解码
    try:
        # 补齐 padding
        padded = raw + "=" * (-len(raw) % 4)
        decoded = base64.b64decode(padded)
    except Exception as exc:
        raise ValueError(f"Cannot decode AES key: {raw!r}") from exc

    # 格式 A: base64(raw 16 bytes)
    if len(decoded) == BLOCK_SIZE:
        return decoded

    # 格式 B: base64(hex string)
    try:
        hex_str = decoded.decode("ascii")
        if len(hex_str) == 32 and all(c in "0123456789abcdefABCDEF" for c in hex_str):
            return bytes.fromhex(hex_str)
    except (UnicodeDecodeError, ValueError):
        pass

    # 其他长度的 base64 解码结果，可能是更长的 hex
    if len(decoded) in (32, 48, 64):
        try:
            hex_str = decoded.decode("ascii")
            if all(c in "0123456789abcdefABCDEF" for c in hex_str):
                return bytes.fromhex(hex_str)[:BLOCK_SIZE]
        except (UnicodeDecodeError, ValueError):
            pass

    raise ValueError(f"Unrecognized AES key format (decoded {len(decoded)} bytes)")


def key_to_hex(key: bytes) -> str:
    """密钥转 hex 字符串（用于 getUploadUrl 请求）"""
    return key.hex()


def key_to_base64(key: bytes) -> str:
    """密钥转 base64 字符串（用于出站消息 CDNMedia.aes_key）"""
    return base64.b64encode(key).decode("ascii")
