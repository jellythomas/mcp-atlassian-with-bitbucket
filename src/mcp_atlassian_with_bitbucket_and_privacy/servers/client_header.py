"""Optional check of a client identification header on the HTTP transports.

Some deployments want to know which requests come from a current, known client
(for example a company wrapper that sends ``X-Example-Client: example/1.4.2``)
and, after a transition period, reject the rest. This module provides an opt-in
ASGI middleware for that. It is disabled unless ``MCP_CLIENT_HEADER_NAME`` is set.

The header is **not a security control**: any caller can set it. It only
distinguishes clients that announce themselves from those that do not.

Configuration (environment):

* ``MCP_CLIENT_HEADER_NAME``: header to check; unset or empty disables the check.
* ``MCP_CLIENT_HEADER_MODE``: ``count`` (default) lets every request through and
  logs the announced value; ``enforce`` answers requests without a valid value
  with HTTP 426.
* ``MCP_CLIENT_HEADER_PATTERN``: regular expression a valid value must match
  completely (default: a short token such as ``name/1.2.3``).
* ``MCP_CLIENT_HEADER_REJECT_MESSAGE``: text of the 426 response.

The log line contains only the validated value, ``missing`` or ``invalid``: no
address, no other header, no credentials. ``/healthz`` is never checked.
"""

from __future__ import annotations

import logging
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

logger = logging.getLogger(__name__)

ENV_NAME = "MCP_CLIENT_HEADER_NAME"
ENV_MODE = "MCP_CLIENT_HEADER_MODE"
ENV_PATTERN = "MCP_CLIENT_HEADER_PATTERN"
ENV_REJECT_MESSAGE = "MCP_CLIENT_HEADER_REJECT_MESSAGE"

MODE_COUNT = "count"
MODE_ENFORCE = "enforce"
DEFAULT_PATTERN = r"[0-9A-Za-z][0-9A-Za-z._+-]{0,31}/[0-9A-Za-z][0-9A-Za-z._+-]{0,31}"
DEFAULT_REJECT_MESSAGE = "Unsupported or outdated client."
STATUS_REJECTED = 426  # Upgrade Required; deliberately neither 401 nor 403

VALUE_MISSING = "missing"
VALUE_INVALID = "invalid"

# Probes of the container must work without the header.
_EXEMPT_PATHS = frozenset({"/healthz"})


@dataclass(frozen=True)
class ClientHeaderConfig:
    """Settings of the client header check.

    Attributes:
        header_name: Lower-case header name as it appears in ASGI scopes.
        mode: ``count`` or ``enforce``.
        pattern: Compiled pattern a valid value must match completely.
        reject_message: Text of the rejection response.
    """

    header_name: bytes
    mode: str
    pattern: re.Pattern[str]
    reject_message: str

    @classmethod
    def from_env(
        cls, environ: Mapping[str, str] | None = None
    ) -> ClientHeaderConfig | None:
        """Reads the settings; returns ``None`` when the check is disabled.

        An unknown mode or an invalid pattern never enables enforcement: the
        mode falls back to ``count`` and the pattern to the default, each with
        a warning.

        Args:
            environ: Environment to read; defaults to ``os.environ``.

        Returns:
            The configuration, or ``None`` if ``MCP_CLIENT_HEADER_NAME`` is not set.
        """
        env = environ if environ is not None else os.environ
        name = env.get(ENV_NAME, "").strip()
        if not name:
            return None
        mode = env.get(ENV_MODE, MODE_COUNT).strip().lower() or MODE_COUNT
        if mode not in (MODE_COUNT, MODE_ENFORCE):
            logger.warning("%s=%r is unknown; using %s.", ENV_MODE, mode, MODE_COUNT)
            mode = MODE_COUNT
        raw_pattern = env.get(ENV_PATTERN, "").strip() or DEFAULT_PATTERN
        try:
            pattern = re.compile(raw_pattern)
        except re.error:
            logger.warning(
                "%s is not a valid regular expression; using default.", ENV_PATTERN
            )
            pattern = re.compile(DEFAULT_PATTERN)
        message = env.get(ENV_REJECT_MESSAGE, "").strip() or DEFAULT_REJECT_MESSAGE
        return cls(name.lower().encode("latin-1"), mode, pattern, message)


def _route_path(scope: Scope) -> str:
    """Returns the path the router matches (``path`` without ``root_path``)."""
    path: str = scope.get("path", "")
    root_path: str = scope.get("root_path", "") or ""
    if not root_path or not path.startswith(root_path):
        return path
    if path == root_path:
        return ""
    if path[len(root_path)] == "/":
        return path[len(root_path) :]
    return path


class ClientHeaderMiddleware:
    """ASGI middleware that counts or enforces the client identification header."""

    def __init__(self, app: ASGIApp, config: ClientHeaderConfig) -> None:
        """Wraps ``app``.

        Args:
            app: The ASGI application to protect.
            config: The settings of the check.
        """
        self.app = app
        self.config = config

    def _classify(self, scope: Scope) -> str:
        for name, value in scope.get("headers", []):
            if name.lower() == self.config.header_name:
                text: str = value.decode("latin-1").strip()
                if self.config.pattern.fullmatch(text):
                    return text
                return VALUE_INVALID
        return VALUE_MISSING

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Handles one ASGI call."""
        if scope["type"] != "http" or _route_path(scope) in _EXEMPT_PATHS:
            await self.app(scope, receive, send)
            return
        value = self._classify(scope)
        valid = value not in (VALUE_MISSING, VALUE_INVALID)
        if self.config.mode == MODE_ENFORCE and not valid:
            logger.info("Client header %s: rejected", value)
            response = JSONResponse(
                {
                    "error": {
                        "code": "client_rejected",
                        "message": self.config.reject_message,
                    }
                },
                status_code=STATUS_REJECTED,
            )
            await response(scope, receive, send)
            return
        logger.info("Client header %s", value)
        await self.app(scope, receive, send)
