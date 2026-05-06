"""Logging configuration utilities."""

import logging
from typing import Optional


def setup_logging(level: str = "INFO") -> None:
    """Configure root logger with specified level.
    
    Args:
        level: Logging level as string (e.g., "DEBUG", "INFO", "WARNING")
    """
    formatter = logging.Formatter(
        "%(asctime)s %(levelname)-8s %(name)s %(message)s"
    )
    
    handler = logging.StreamHandler()
    handler.setFormatter(formatter)
    
    root_logger = logging.getLogger()
    root_logger.setLevel(level.upper())
    root_logger.addHandler(handler)


def get_logger(name: str) -> logging.Logger:
    """Get logger instance for module.
    
    Args:
        name: Logger name (typically __name__)
        
    Returns:
        Logger instance
    """
    return logging.getLogger(name)
