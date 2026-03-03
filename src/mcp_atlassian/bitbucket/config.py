"""Configuration module for Bitbucket API interactions."""

import logging
import os
from dataclasses import dataclass
from typing import Literal

from ..utils.env import get_custom_headers, is_env_ssl_verify
from ..utils.oauth import (
    BYOAccessTokenOAuthConfig,
    OAuthConfig,
    get_oauth_config_from_env,
)

logger = logging.getLogger("mcp-atlassian.bitbucket.config")


def _is_bitbucket_cloud_url(url: str | None) -> bool:
    """Check if a URL points to Bitbucket Cloud.

    Args:
        url: The URL to check.

    Returns:
        True if the URL is a Bitbucket Cloud URL (bitbucket.org).
    """
    if not url:
        return False
    url_lower = url.lower().rstrip("/")
    return "bitbucket.org" in url_lower


@dataclass
class BitbucketConfig:
    """Bitbucket API configuration.

    Handles authentication for Bitbucket Cloud and Server/Data Center:
    - Cloud: App passwords (username + app_password), OAuth 2.0, or workspace access tokens
    - Server/DC: Personal access tokens, HTTP access tokens, or basic auth
    """

    url: str  # Base URL (https://api.bitbucket.org/2.0 for Cloud, instance URL for Server)
    auth_type: Literal["basic", "pat", "oauth"]  # Authentication type
    username: str | None = None  # Username (Cloud app password or API token auth)
    app_password: str | None = None  # App password or API token (Cloud)
    personal_token: str | None = None  # Personal/HTTP access token (Server/DC)
    oauth_config: OAuthConfig | BYOAccessTokenOAuthConfig | None = None
    ssl_verify: bool = True  # Whether to verify SSL certificates
    workspace: str | None = None  # Default workspace slug (Cloud)
    project_key: str | None = None  # Default project key (Server/DC)
    http_proxy: str | None = None  # HTTP proxy URL
    https_proxy: str | None = None  # HTTPS proxy URL
    no_proxy: str | None = None  # Comma-separated list of hosts to bypass proxy
    socks_proxy: str | None = None  # SOCKS proxy URL
    custom_headers: dict[str, str] | None = None  # Custom HTTP headers
    timeout: int = 75  # Connection timeout in seconds

    @property
    def is_cloud(self) -> bool:
        """Check if this is a Bitbucket Cloud instance.

        Returns:
            True if this is Bitbucket Cloud (bitbucket.org), False for Server/DC.
        """
        if (
            self.auth_type == "oauth"
            and self.oauth_config
            and self.oauth_config.cloud_id
        ):
            return True

        if (
            self.auth_type == "oauth"
            and self.oauth_config
            and hasattr(self.oauth_config, "base_url")
            and self.oauth_config.base_url
            and not self.oauth_config.cloud_id
        ):
            return False

        return _is_bitbucket_cloud_url(self.url)

    @property
    def verify_ssl(self) -> bool:
        """Compatibility property."""
        return self.ssl_verify

    @property
    def api_base_url(self) -> str:
        """Get the base URL for API requests.

        Returns:
            For Cloud: https://api.bitbucket.org/2.0
            For Server/DC: {url}/rest/api/1.0
        """
        if self.is_cloud:
            return "https://api.bitbucket.org/2.0"
        return f"{self.url.rstrip('/')}/rest/api/1.0"

    @classmethod
    def from_env(cls) -> "BitbucketConfig":
        """Create configuration from environment variables.

        Returns:
            BitbucketConfig with values from environment variables.

        Raises:
            ValueError: If required environment variables are missing or invalid.
        """
        url = os.getenv("BITBUCKET_URL")
        if not url:
            error_msg = (
                "Missing required BITBUCKET_URL environment variable. "
                "Set BITBUCKET_URL to your Bitbucket URL, for example "
                "https://bitbucket.org (Cloud) or "
                "https://bitbucket.your-company.com (Server/DC)."
            )
            raise ValueError(error_msg)

        username = os.getenv("BITBUCKET_USERNAME")
        # Support both legacy app passwords and new API tokens (Sep 2025+)
        app_password = os.getenv("BITBUCKET_APP_PASSWORD") or os.getenv(
            "BITBUCKET_API_TOKEN"
        )
        personal_token = os.getenv("BITBUCKET_PERSONAL_TOKEN")

        oauth_config = get_oauth_config_from_env(
            service_url=url, service_type="bitbucket"
        )
        auth_type = None

        is_cloud = _is_bitbucket_cloud_url(url)

        if is_cloud:
            if oauth_config:
                auth_type = "oauth"
            elif username and app_password:
                auth_type = "basic"
            else:
                missing_fields: list[str] = []
                if not username:
                    missing_fields.append("BITBUCKET_USERNAME")
                if not app_password:
                    missing_fields.append(
                        "BITBUCKET_API_TOKEN (or BITBUCKET_APP_PASSWORD)"
                    )
                missing_text = ", ".join(missing_fields)
                error_msg = (
                    "Bitbucket Cloud authentication requires "
                    "BITBUCKET_USERNAME and BITBUCKET_API_TOKEN "
                    "(or BITBUCKET_APP_PASSWORD), "
                    "or OAuth configuration. "
                    f"Missing: {missing_text}."
                )
                raise ValueError(error_msg)
        else:
            if personal_token:
                if oauth_config:
                    logger.warning(
                        "Both PAT and OAuth configured for Bitbucket Server/DC. Using PAT."
                    )
                auth_type = "pat"
            elif oauth_config:
                auth_type = "oauth"
            elif username and app_password:
                auth_type = "basic"
            else:
                error_msg = (
                    "Bitbucket Server/Data Center authentication requires "
                    "BITBUCKET_PERSONAL_TOKEN, or "
                    "BITBUCKET_USERNAME and BITBUCKET_APP_PASSWORD."
                )
                raise ValueError(error_msg)

        ssl_verify = is_env_ssl_verify("BITBUCKET_SSL_VERIFY")

        workspace = os.getenv("BITBUCKET_WORKSPACE")
        project_key = os.getenv("BITBUCKET_PROJECT_KEY")

        http_proxy = os.getenv("BITBUCKET_HTTP_PROXY", os.getenv("HTTP_PROXY"))
        https_proxy = os.getenv("BITBUCKET_HTTPS_PROXY", os.getenv("HTTPS_PROXY"))
        no_proxy = os.getenv("BITBUCKET_NO_PROXY", os.getenv("NO_PROXY"))
        socks_proxy = os.getenv("BITBUCKET_SOCKS_PROXY", os.getenv("SOCKS_PROXY"))

        custom_headers = get_custom_headers("BITBUCKET_CUSTOM_HEADERS")

        timeout = 75
        timeout_str = os.getenv("BITBUCKET_TIMEOUT", "")
        if timeout_str.isdigit():
            timeout = int(timeout_str)

        return cls(
            url=url,
            auth_type=auth_type,
            username=username,
            app_password=app_password,
            personal_token=personal_token,
            oauth_config=oauth_config,
            ssl_verify=ssl_verify,
            workspace=workspace,
            project_key=project_key,
            http_proxy=http_proxy,
            https_proxy=https_proxy,
            no_proxy=no_proxy,
            socks_proxy=socks_proxy,
            custom_headers=custom_headers,
            timeout=timeout,
        )

    def is_auth_configured(self) -> bool:
        """Check if the current authentication configuration is complete.

        Returns:
            True if authentication is fully configured, False otherwise.
        """
        if self.auth_type == "oauth":
            if self.oauth_config:
                if isinstance(self.oauth_config, OAuthConfig):
                    if (
                        not self.oauth_config.client_id
                        and not self.oauth_config.client_secret
                    ):
                        logger.debug(
                            "Minimal OAuth config detected - "
                            "expecting user-provided tokens via headers"
                        )
                        return True
                    if hasattr(self.oauth_config, "is_data_center"):
                        if self.oauth_config.is_data_center:
                            return bool(
                                self.oauth_config.client_id
                                and self.oauth_config.client_secret
                            )
                    if (
                        self.oauth_config.client_id
                        and self.oauth_config.client_secret
                        and self.oauth_config.redirect_uri
                        and self.oauth_config.scope
                    ):
                        return True
                elif isinstance(self.oauth_config, BYOAccessTokenOAuthConfig):
                    if self.oauth_config.access_token:
                        return True

            logger.warning("Incomplete Bitbucket OAuth configuration detected")
            return False
        elif self.auth_type == "pat":
            return bool(self.personal_token)
        elif self.auth_type == "basic":
            return bool(self.username and self.app_password)

        logger.warning(
            f"Unknown or unsupported auth_type: {self.auth_type} in BitbucketConfig"
        )
        return False
