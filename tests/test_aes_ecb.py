"""19.1 测试 AES-128-ECB 加解密（已知向量）"""

from weixin_bot.cdn import (
    aes_ecb_decrypt,
    aes_ecb_encrypt,
    encrypted_size,
    generate_aes_key,
    key_to_base64,
    key_to_hex,
    parse_aes_key,
    pkcs7_pad,
    pkcs7_unpad,
)


class TestPKCS7:
    def test_pad_exact_block(self) -> None:
        data = b"0123456789abcdef"  # 16 bytes
        padded = pkcs7_pad(data)
        assert len(padded) == 32  # full block of padding added
        assert padded[-1] == 16

    def test_pad_short(self) -> None:
        data = b"hello"  # 5 bytes → 16 - 5 = 11 padding
        padded = pkcs7_pad(data)
        assert len(padded) == 16
        assert padded[-1] == 11

    def test_unpad_roundtrip(self) -> None:
        data = b"test data here!"
        assert pkcs7_unpad(pkcs7_pad(data)) == data

    def test_unpad_empty(self) -> None:
        assert pkcs7_unpad(b"") == b""


class TestAESECB:
    def test_encrypt_decrypt_roundtrip(self) -> None:
        key = generate_aes_key()
        plaintext = b"Hello, WeChat CDN!"
        ciphertext = aes_ecb_encrypt(plaintext, key)
        assert ciphertext != plaintext
        assert aes_ecb_decrypt(ciphertext, key) == plaintext

    def test_encrypt_decrypt_large(self) -> None:
        key = generate_aes_key()
        plaintext = b"x" * 10000
        ct = aes_ecb_encrypt(plaintext, key)
        assert aes_ecb_decrypt(ct, key) == plaintext

    def test_encrypted_size_calculation(self) -> None:
        assert encrypted_size(0) == 16  # empty → 16 bytes padding
        assert encrypted_size(15) == 16
        assert encrypted_size(16) == 32  # exact block → full padding block
        assert encrypted_size(17) == 32

    def test_known_vector(self) -> None:
        """已知密钥 + 明文 → 加解密一致性"""
        key = b"\x00" * 16
        plaintext = b"AES-128-ECB test"
        ct = aes_ecb_encrypt(plaintext, key)
        assert len(ct) == 32  # 16 bytes + 16 bytes padding
        assert aes_ecb_decrypt(ct, key) == plaintext


class TestKeyParsing:
    def test_parse_hex_32_chars(self) -> None:
        key = generate_aes_key()
        hex_str = key.hex()
        assert parse_aes_key(hex_str) == key

    def test_parse_base64_raw(self) -> None:
        key = generate_aes_key()
        b64 = key_to_base64(key)
        assert parse_aes_key(b64) == key

    def test_parse_base64_hex(self) -> None:
        """base64(hex string) 格式"""
        import base64

        key = generate_aes_key()
        hex_str = key.hex()
        b64_hex = base64.b64encode(hex_str.encode("ascii")).decode()
        assert parse_aes_key(b64_hex) == key

    def test_key_to_hex_roundtrip(self) -> None:
        key = generate_aes_key()
        assert parse_aes_key(key_to_hex(key)) == key

    def test_empty_raises(self) -> None:
        import pytest

        with pytest.raises(ValueError, match="Empty"):
            parse_aes_key("")
