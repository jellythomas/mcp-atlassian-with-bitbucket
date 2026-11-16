"""Identity privacy configuration and domain types."""

from .alias_roundtrip import (
    AliasResolutionError,
    AliasRoundtripRegistry,
    begin_alias_caller_scope,
    begin_alias_roundtrip_registry_scope,
    is_identity_alias,
    record_alias_caller,
    reset_alias_caller_scope,
    reset_alias_roundtrip_registry_scope,
    resolve_identity_alias,
)
from .bitbucket_adapter import BitbucketIdentityAdapter
from .classifier import IdentityClassifier
from .config import IdentityPrivacyConfig
from .confluence_adapter import ConfluenceIdentityAdapter
from .current_user import (
    CurrentIdentity,
    CurrentIdentityResolver,
    begin_current_identity_scope,
    record_current_identity,
    reset_current_identity_scope,
)
from .jira_adapter import JiraIdentityAdapter
from .keyring import PseudonymKeyring, PseudonymKeyVersion
from .middleware import PrivacyFilterMiddleware, install_identity_privacy
from .policy import IdentityPolicy, JiraIdentityTextRule, normalize_login
from .pseudonymizer import Pseudonymizer
from .registry import (
    TOOL_RESPONSE_POLICIES,
    ResponseCategory,
    ToolResponsePolicy,
    ToolService,
    UnknownToolResponsePolicyError,
    get_tool_response_policy,
)
from .resolver import CanonicalIdentityResolver
from .runtime import (
    begin_identity_privacy_runtime,
    is_identity_privacy_runtime_active,
    privacy_safe_exception_detail,
    privacy_safe_value,
    reset_identity_privacy_runtime,
)
from .transformer import (
    IdentityResponseAdapter,
    IdentityResponseTransformer,
    PrivacyTransformationError,
)
from .types import (
    ActorType,
    Affiliation,
    CanonicalIdentity,
    CorrelationScope,
    IdentityClass,
    IdentitySource,
    PrivacyMode,
    UnstructuredContentPolicy,
)

__all__ = [
    "ActorType",
    "Affiliation",
    "AliasResolutionError",
    "AliasRoundtripRegistry",
    "BitbucketIdentityAdapter",
    "CanonicalIdentity",
    "CanonicalIdentityResolver",
    "ConfluenceIdentityAdapter",
    "CorrelationScope",
    "CurrentIdentity",
    "CurrentIdentityResolver",
    "IdentityClass",
    "IdentityClassifier",
    "IdentityPolicy",
    "IdentityPrivacyConfig",
    "IdentityResponseAdapter",
    "IdentityResponseTransformer",
    "IdentitySource",
    "JiraIdentityAdapter",
    "JiraIdentityTextRule",
    "PrivacyFilterMiddleware",
    "PrivacyMode",
    "PrivacyTransformationError",
    "PseudonymKeyring",
    "PseudonymKeyVersion",
    "Pseudonymizer",
    "ResponseCategory",
    "TOOL_RESPONSE_POLICIES",
    "ToolResponsePolicy",
    "ToolService",
    "UnknownToolResponsePolicyError",
    "UnstructuredContentPolicy",
    "begin_current_identity_scope",
    "begin_alias_caller_scope",
    "begin_alias_roundtrip_registry_scope",
    "begin_identity_privacy_runtime",
    "get_tool_response_policy",
    "install_identity_privacy",
    "is_identity_privacy_runtime_active",
    "normalize_login",
    "privacy_safe_exception_detail",
    "privacy_safe_value",
    "record_current_identity",
    "record_alias_caller",
    "is_identity_alias",
    "resolve_identity_alias",
    "reset_alias_roundtrip_registry_scope",
    "reset_alias_caller_scope",
    "reset_current_identity_scope",
    "reset_identity_privacy_runtime",
]
