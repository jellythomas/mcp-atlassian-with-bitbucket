"""Tests for structured Bitbucket identity transformation."""

from datetime import datetime, timezone
from typing import Any

from mcp_atlassian_with_bitbucket_and_privacy.bitbucket.client import BitbucketClient
from mcp_atlassian_with_bitbucket_and_privacy.privacy import (
    BitbucketIdentityAdapter,
    CurrentIdentity,
    IdentityPolicy,
    IdentityPrivacyConfig,
    IdentityResponseTransformer,
    PrivacyMode,
    ResponseCategory,
    ToolResponsePolicy,
    ToolService,
    begin_identity_privacy_runtime,
    reset_identity_privacy_runtime,
)

_NOW = datetime(2026, 10, 5, 12, tzinfo=timezone.utc)


def _config() -> IdentityPrivacyConfig:
    return IdentityPrivacyConfig(
        mode=PrivacyMode.PSEUDONYMIZE,
        policy=IdentityPolicy.from_mapping(
            {
                "human_username_max_length": 8,
                "expose_service_display_name_and_login": True,
                "internal_logins": ["human01", "service-account"],
            }
        ),
        pseudonym_key=b"k" * 32,
        correlation_domain="test-deployment",
    )


def _adapter() -> BitbucketIdentityAdapter:
    return BitbucketIdentityAdapter(
        _config(),
        instance="https://bitbucket.example",
        clock=lambda: _NOW,
    )


def _transform(
    value: Any,
    *,
    current_identity: CurrentIdentity | None = None,
) -> Any:
    return _adapter().transform(
        tool_name="bitbucket_get_pull_request",
        policy=ToolResponsePolicy(
            service=ToolService.BITBUCKET,
            category=ResponseCategory.STRUCTURED,
        ),
        value=value,
        current_identity=current_identity,
    )


def _cloud_user(login: str = "human01") -> dict[str, Any]:
    return {
        "type": "user",
        "display_name": "CANARY Cloud Person",
        "nickname": login,
        "account_id": "cloud-account-id",
        "uuid": "{cloud-user-uuid}",
        "links": {
            "self": {"href": "https://api.example/user"},
            "html": {"href": "https://example/user"},
            "avatar": {"href": "https://example/avatar"},
        },
    }


def _dc_user(login: str = "human01") -> dict[str, Any]:
    return {
        "id": 42,
        "name": login,
        "slug": login,
        "displayName": "CANARY DC Person",
        "emailAddress": "canary@example.test",
        "active": True,
        "links": {"self": [{"href": "https://bitbucket.example/users/42"}]},
    }


def test_cloud_and_dc_user_shapes_are_protected() -> None:
    result = _transform(
        {
            "cloud": _cloud_user(),
            "dc": _dc_user(),
        }
    )

    cloud = result["cloud"]
    dc = result["dc"]
    assert cloud["nickname"].startswith("pid:v1:")
    assert cloud["account_id"].startswith("pid:v1:")
    assert cloud["uuid"].startswith("pid:v1:")
    assert cloud["links"] is None
    assert dc["name"].startswith("pid:v1:")
    assert dc["id"].startswith("pid:v1:")
    assert dc["slug"].startswith("pid:v1:")
    assert dc["emailAddress"] is None
    assert dc["links"] is None
    assert cloud["identity_class"]["actor_type"] == "human"
    assert dc["identity_class"]["actor_type"] == "human"
    assert "CANARY" not in str(result)


def test_service_keeps_only_display_and_login() -> None:
    result = _transform(_dc_user("service-account"))

    assert result["name"] == "service-account"
    assert result["displayName"] == "CANARY DC Person"
    assert result["id"] is None
    assert result["slug"] is None
    assert result["emailAddress"] is None
    assert result["links"] is None
    assert result["active"] is True
    assert result["identity_class"]["actor_type"] == "service"


def test_pr_participants_reviewers_and_activity_users() -> None:
    result = _transform(
        {
            "author": _cloud_user(),
            "reviewers": [_dc_user()],
            "participants": [
                {
                    "user": _dc_user(),
                    "role": "REVIEWER",
                    "approved": True,
                    "status": "APPROVED",
                }
            ],
            "activity": {
                "actor": _cloud_user(),
                "comment": {"author": _dc_user(), "text": "unchanged"},
            },
        }
    )

    assert result["author"]["nickname"].startswith("pid:v1:")
    assert result["reviewers"][0]["name"].startswith("pid:v1:")
    participant = result["participants"][0]
    assert participant["user"]["name"].startswith("pid:v1:")
    assert participant["role"] == "REVIEWER"
    assert participant["approved"] is True
    assert result["activity"]["comment"]["text"] == "unchanged"
    assert "CANARY" not in str(result)


def test_commit_author_wrapper_protects_raw_and_nested_user() -> None:
    result = _transform(
        {
            "hash": "abc123",
            "message": "Source content remains CANARY text",
            "author": {
                "raw": "CANARY Person <canary@example.test>",
                "user": _cloud_user(),
            },
            "committer": {"raw": "CANARY Committer <c@example.test>"},
        }
    )

    assert result["author"]["raw"].startswith("Internal human H-")
    assert result["author"]["user"]["nickname"].startswith("pid:v1:")
    assert result["committer"]["raw"].startswith("pid:v1:")
    assert result["message"] == "Source content remains CANARY text"


def test_permissions_owners_creators_and_pipeline_targets() -> None:
    result = _transform(
        {
            "repository": {"name": "repo", "owner": _cloud_user()},
            "permission": {"user": _dc_user(), "permission": "PROJECT_READ"},
            "pipeline": {
                "creator": _cloud_user(),
                "target": {
                    "ref_name": "main",
                    "commit": {"author": _dc_user()},
                },
            },
            "deployment": {"creator": _dc_user()},
            "webhook": {"actor": _cloud_user(), "url": "https://callback.example"},
        }
    )

    assert result["repository"]["name"] == "repo"
    assert result["repository"]["owner"]["nickname"].startswith("pid:v1:")
    assert result["permission"]["permission"] == "PROJECT_READ"
    assert result["pipeline"]["target"]["ref_name"] == "main"
    assert result["webhook"]["url"] == "https://callback.example"
    assert "CANARY" not in str(result)


def test_unrelated_bitbucket_objects_are_unchanged() -> None:
    value = {
        "repository": {
            "name": "example-repo",
            "slug": "example-repo",
            "uuid": "{repo-uuid}",
            "links": {"html": {"href": "https://example/repo"}},
        },
        "branch": {"id": "refs/heads/main", "displayId": "main"},
        "status": {"name": "SUCCESSFUL", "key": "build"},
    }

    assert _transform(value) == value


def test_marks_current_user_without_unmasking() -> None:
    result = _transform(
        _cloud_user(),
        current_identity=CurrentIdentity.from_values(
            "human01",
            "cloud-account-id",
        ),
    )

    assert result["is_current_user"] is True
    assert result["display_name"] == "You"
    assert result["nickname"].startswith("pid:v1:")


def test_same_login_matches_jira_alias_in_deployment_scope() -> None:
    transformer = IdentityResponseTransformer.from_config(
        _config(),
        clock=lambda: _NOW,
    )
    bitbucket = transformer.transform(
        tool_name="bitbucket_get_pull_request",
        policy=ToolResponsePolicy(
            service=ToolService.BITBUCKET,
            category=ResponseCategory.STRUCTURED,
        ),
        value=_cloud_user(),
        current_identity=None,
    )
    jira = transformer.transform(
        tool_name="jira_get_user_profile",
        policy=ToolResponsePolicy(
            service=ToolService.JIRA,
            category=ResponseCategory.STRUCTURED,
        ),
        value={"name": "human01", "displayName": "CANARY Jira Person"},
        current_identity=None,
    )

    assert bitbucket["nickname"] == jira["name"]


def test_default_transformer_registers_bitbucket_adapter() -> None:
    transformer = IdentityResponseTransformer.from_config(
        _config(),
        clock=lambda: _NOW,
    )

    result = transformer.transform(
        tool_name="bitbucket_get_default_reviewers",
        policy=ToolResponsePolicy(
            service=ToolService.BITBUCKET,
            category=ResponseCategory.STRUCTURED,
        ),
        value=[_cloud_user()],
        current_identity=None,
    )

    assert result[0]["nickname"].startswith("pid:v1:")


def _pull_request_payload() -> dict[str, Any]:
    return {
        "id": 42,
        "title": "Privacy PR",
        "state": "OPEN",
        "author": _cloud_user(),
        "reviewers": [{"user": _dc_user()}],
        "participants": [
            {"user": _cloud_user(), "approved": True},
        ],
        "source": {
            "branch": {"name": "feature"},
            "repository": {"slug": "repo"},
            "commit": {"hash": "abcdef1234567890"},
        },
        "destination": {
            "branch": {"name": "main"},
            "repository": {"slug": "repo"},
            "commit": {"hash": "123456abcdef7890"},
        },
        "description": "Body remains unchanged",
    }


def test_compact_pr_off_mode_preserves_legacy_string_shape() -> None:
    compact = BitbucketClient._compact_pull_request(_pull_request_payload())

    assert compact["author"] == "CANARY Cloud Person"
    assert compact["reviewers"] == ["human01"]
    assert compact["approved_by"] == ["CANARY Cloud Person"]


def test_compact_pr_privacy_runtime_preserves_identity_sources() -> None:
    token = begin_identity_privacy_runtime()
    try:
        compact = BitbucketClient._compact_pull_request(_pull_request_payload())
    finally:
        reset_identity_privacy_runtime(token)

    assert compact["author"]["nickname"] == "human01"
    assert compact["reviewers"][0]["name"] == "human01"
    assert compact["approved_by"][0]["account_id"] == "cloud-account-id"
    assert compact["description"] == "Body remains unchanged"
    assert "workspace" not in compact["author"]


def test_compact_and_full_pr_use_same_aliases_and_classes() -> None:
    token = begin_identity_privacy_runtime()
    try:
        compact = BitbucketClient._compact_pull_request(_pull_request_payload())
    finally:
        reset_identity_privacy_runtime(token)

    protected_compact = _adapter().transform(
        tool_name="bitbucket_get_pull_request",
        policy=ToolResponsePolicy(
            service=ToolService.BITBUCKET,
            category=ResponseCategory.STRUCTURED,
        ),
        value=compact,
        current_identity=None,
    )
    protected_full = _transform(_pull_request_payload())

    assert (
        protected_compact["author"]["nickname"] == protected_full["author"]["nickname"]
    )
    assert (
        protected_compact["author"]["identity_class"]
        == protected_full["author"]["identity_class"]
    )
    assert (
        protected_compact["reviewers"][0]["name"]
        == protected_full["reviewers"][0]["user"]["name"]
    )
