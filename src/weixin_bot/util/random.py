"""Random utilities for secure token and ID generation."""

import base64
import secrets
from uuid import uuid4


def generate_client_id() -> str:
    """Generate unique client ID.
    
    Returns:
        Client ID in format "weixinbot-{uuid4}"
    """
    return f"weixinbot-{uuid4()}"


def generate_filekey() -> str:
    """Generate random file key.
    
    Returns:
        16-byte random hex string
    """
    return secrets.token_hex(16)


def generate_wechat_uin() -> str:
    """Generate WeChat UIN for X-WECHAT-UIN header.
    
    Returns:
        Base64-encoded random uint32 as string
    """
    random_uint32 = secrets.randbits(32)
    return base64.b64encode(str(random_uint32).encode()).decode()
