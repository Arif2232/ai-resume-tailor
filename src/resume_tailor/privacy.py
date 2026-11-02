"""Keep HTTP client diagnostics from logging private request details."""

import logging


def silence_http_logs():
    for name in ('httpx', 'httpcore'):
        logger = logging.getLogger(name)
        logger.setLevel(logging.CRITICAL + 1)
        logger.propagate = False
        if not any(isinstance(handler, logging.NullHandler) for handler in logger.handlers):
            logger.addHandler(logging.NullHandler())
