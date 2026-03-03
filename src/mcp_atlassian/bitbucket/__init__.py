"""Bitbucket API module for mcp_atlassian.

Provides Bitbucket Cloud (API 2.0) and Server/Data Center (API 1.0)
client implementations.
"""

from .client import BitbucketClient
from .config import BitbucketConfig

__all__ = [
    "BitbucketClient",
    "BitbucketConfig",
]
