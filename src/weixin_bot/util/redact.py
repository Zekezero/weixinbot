"""Utilities for redacting sensitive information."""

from urllib.parse import parse_qs, urlencode, urlparse, urlunparse


def redact_token(token: str) -> str:
    """Redact token for safe logging.
    
    Args:
        token: Token string to redact
        
    Returns:
        Redacted token with first 8 chars + "***" + last 4 chars,
        or "***" if token is too short
    """
    if len(token) <= 12:
        return "***"
    return token[:8] + "***" + token[-4:]


def redact_url(url: str) -> str:
    """Redact sensitive query parameters in URL.
    
    Args:
        url: URL string to redact
        
    Returns:
        URL with sensitive parameter values replaced with "***"
    """
    parsed = urlparse(url)
    
    if not parsed.query:
        return url
    
    params = parse_qs(parsed.query, keep_blank_values=True)
    sensitive_keys = {"token", "key", "secret", "param"}
    
    redacted_params = {}
    for key, values in params.items():
        if key.lower() in sensitive_keys:
            redacted_params[key] = ["***"]
        else:
            redacted_params[key] = values
    
    new_query = urlencode(redacted_params, doseq=True)
    redacted = urlunparse((
        parsed.scheme,
        parsed.netloc,
        parsed.path,
        parsed.params,
        new_query,
        parsed.fragment
    ))
    
    return redacted
