"""19.2 测试 CDN 上传/下载管道（mock HTTP）"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from weixin_bot.cdn import aes_ecb_encrypt, generate_aes_key, key_to_base64, key_to_hex
from weixin_bot.cdn.download import download_and_decrypt
from weixin_bot.cdn.upload import upload_media
from weixin_bot.errors import CdnError


class TestCDNDownload:
    @pytest.mark.asyncio
    async def test_download_and_decrypt_success(self) -> None:
        key = generate_aes_key()
        plaintext = b"test image data here"
        ciphertext = aes_ecb_encrypt(plaintext, key)

        client = MagicMock()
        client.get_binary = AsyncMock(return_value=ciphertext)

        result = await download_and_decrypt(
            client,
            encrypt_query_param="fake_eqp",
            aes_key_raw=key_to_base64(key),
        )
        assert result == plaintext

    @pytest.mark.asyncio
    async def test_download_with_full_url(self) -> None:
        key = generate_aes_key()
        plaintext = b"full url test"
        ciphertext = aes_ecb_encrypt(plaintext, key)

        client = MagicMock()
        client.get_binary = AsyncMock(return_value=ciphertext)

        result = await download_and_decrypt(
            client,
            encrypt_query_param="",
            aes_key_raw=key_to_hex(key),
            full_url="https://cdn.example.com/download?x=1",
        )
        assert result == plaintext
        # Verify full_url was used
        client.get_binary.assert_called_once()
        call_url = client.get_binary.call_args[0][0]
        assert "cdn.example.com" in call_url

    @pytest.mark.asyncio
    async def test_download_empty_key_raises(self) -> None:
        client = MagicMock()
        with pytest.raises(CdnError, match="无法解析"):
            await download_and_decrypt(client, "eqp", "")

    @pytest.mark.asyncio
    async def test_download_empty_data_raises(self) -> None:
        key = generate_aes_key()
        client = MagicMock()
        client.get_binary = AsyncMock(return_value=b"")

        with pytest.raises(CdnError, match="空数据"):
            await download_and_decrypt(client, "eqp", key_to_base64(key))
