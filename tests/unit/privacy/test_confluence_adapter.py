"""Tests for structured Confluence identity protection."""

from datetime import datetime, timezone
from typing import Any

from mcp_atlassian_with_bitbucket_and_privacy.models.confluence.comment import (
    ConfluenceComment,
)
from mcp_atlassian_with_bitbucket_and_privacy.models.confluence.common import (
    ConfluenceAttachment,
    ConfluenceUser,
)
from mcp_atlassian_with_bitbucket_and_privacy.models.confluence.page import (
    ConfluencePage,
)
from mcp_atlassian_with_bitbucket_and_privacy.models.confluence.user_search import (
    ConfluenceUserSearchResult,
)
from mcp_atlassian_with_bitbucket_and_privacy.privacy import (
    ConfluenceIdentityAdapter,
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


def _adapter() -> ConfluenceIdentityAdapter:
    return ConfluenceIdentityAdapter(
        _config(),
        instance="https://confluence.example",
        clock=lambda: _NOW,
    )


def _transform(
    value: Any,
    *,
    current_identity: CurrentIdentity | None = None,
) -> Any:
    return _adapter().transform(
        tool_name="confluence_get_page",
        policy=ToolResponsePolicy(
            service=ToolService.CONFLUENCE,
            category=ResponseCategory.MIXED,
        ),
        value=value,
        current_identity=current_identity,
    )


def _cloud_user(login: str = "human01") -> dict[str, Any]:
    return {
        "accountId": "cloud-account",
        "username": login,
        "displayName": "CANARY Cloud Person",
        "email": "canary@example.test",
        "profilePicture": {"path": "/avatar/canary"},
        "accountStatus": "active",
    }


def _dc_user(login: str = "human01") -> dict[str, Any]:
    return {
        "name": login,
        "userKey": "DC-USER-KEY",
        "displayName": "CANARY DC Person",
        "email": "canary@example.test",
        "profilePicture": {"path": "/avatar/canary"},
    }


def _privacy_output(model: Any) -> dict[str, Any]:
    token = begin_identity_privacy_runtime()
    try:
        return model.to_simplified_dict()
    finally:
        reset_identity_privacy_runtime(token)


def test_confluence_user_off_mode_output_is_unchanged() -> None:
    user = ConfluenceUser.from_api_response(_dc_user())

    assert user.to_simplified_dict() == {
        "account_id": None,
        "display_name": "CANARY DC Person",
        "email": "canary@example.test",
        "profile_picture": "/avatar/canary",
    }


def test_cloud_and_dc_identity_dicts_are_protected() -> None:
    cloud = ConfluenceUser.from_api_response(_cloud_user()).to_identity_dict()
    dc = ConfluenceUser.from_api_response(_dc_user()).to_identity_dict()

    result = _transform({"cloud": cloud, "dc": dc})

    assert result["cloud"]["username"].startswith("pid:v1:")
    assert result["cloud"]["account_id"].startswith("pid:v1:")
    assert result["dc"]["username"].startswith("pid:v1:")
    assert result["dc"]["user_key"].startswith("pid:v1:")
    assert result["cloud"]["email"] is None
    assert result["dc"]["profile_picture"] is None
    assert "CANARY" not in str(result)


def test_page_and_comment_models_preserve_content_but_structure_authors() -> None:
    page = ConfluencePage.from_api_response(
        {
            "id": "1",
            "title": "Page title",
            "body": {"view": {"value": "<p>CANARY content displayName remains</p>"}},
            "author": _dc_user(),
            "version": {
                "number": 2,
                "when": "2026-10-05T12:00:00Z",
                "by": _dc_user(),
            },
        }
    )
    comment = ConfluenceComment.from_api_response(
        {
            "id": "2",
            "body": {"view": {"value": "CANARY comment body remains"}},
            "author": _dc_user(),
        }
    )

    protected_page = _transform(_privacy_output(page))
    protected_comment = _transform(_privacy_output(comment))

    assert protected_page["author"]["username"].startswith("pid:v1:")
    assert protected_page["version_author"]["username"].startswith("pid:v1:")
    assert (
        protected_page["content"]["value"]
        == "<p>CANARY content displayName remains</p>"
    )
    assert protected_comment["author"]["username"].startswith("pid:v1:")
    assert protected_comment["body"] == "CANARY comment body remains"


def test_history_and_restriction_shapes_are_protected() -> None:
    result = _transform(
        {
            "history": {
                "createdBy": _dc_user(),
                "lastUpdated": {"by": _cloud_user(), "when": "now"},
            },
            "read": {
                "users": ["human01", "service-account"],
                "groups": ["confluence-users"],
            },
        }
    )

    assert result["history"]["createdBy"]["name"].startswith("pid:v1:")
    assert result["history"]["lastUpdated"]["by"]["username"].startswith("pid:v1:")
    assert result["read"]["users"][0].startswith("pid:v1:")
    assert result["read"]["users"][1] == "service-account"
    assert result["read"]["groups"] == ["confluence-users"]


def test_user_search_title_and_profile_url_are_protected() -> None:
    search = ConfluenceUserSearchResult.from_api_response(
        {
            "user": _dc_user(),
            "title": "CANARY DC Person",
            "url": "/people/human01",
            "entityType": "user",
        }
    )

    result = _transform(_privacy_output(search))

    assert result["user"]["username"].startswith("pid:v1:")
    assert result["title"].startswith("Internal human H-")
    assert result["url"] is None
    assert "CANARY" not in str(result)


def test_attachment_author_is_structured_only_in_privacy_runtime() -> None:
    attachment = ConfluenceAttachment.from_api_response(
        {
            "id": "a1",
            "title": "file.txt",
            "version": {
                "number": 1,
                "by": _cloud_user(),
            },
        }
    )

    off = attachment.to_simplified_dict()
    protected = _transform(_privacy_output(attachment))

    assert off["author_display_name"] == "CANARY Cloud Person"
    assert "author" not in off
    assert protected["author"]["account_id"].startswith("pid:v1:")
    assert "author_display_name" not in protected


def test_service_keeps_only_display_and_login() -> None:
    result = _transform(
        ConfluenceUser.from_api_response(_dc_user("service-account")).to_identity_dict()
    )

    assert result["username"] == "service-account"
    assert result["display_name"] == "CANARY DC Person"
    assert result["user_key"] is None
    assert result["email"] is None
    assert result["profile_picture"] is None
    assert result["identity_class"]["actor_type"] == "service"


def test_current_user_is_marked_without_unmasking() -> None:
    result = _transform(
        ConfluenceUser.from_api_response(_dc_user()).to_identity_dict(),
        current_identity=CurrentIdentity.from_values("human01"),
    )

    assert result["is_current_user"] is True
    assert result["display_name"] == "You"
    assert result["username"].startswith("pid:v1:")


def test_same_login_matches_jira_and_bitbucket_aliases() -> None:
    transformer = IdentityResponseTransformer.from_config(
        _config(),
        clock=lambda: _NOW,
    )
    confluence = transformer.transform(
        tool_name="confluence_search_user",
        policy=ToolResponsePolicy(
            service=ToolService.CONFLUENCE,
            category=ResponseCategory.STRUCTURED,
        ),
        value=ConfluenceUser.from_api_response(_dc_user()).to_identity_dict(),
        current_identity=None,
    )
    jira = transformer.transform(
        tool_name="jira_get_user_profile",
        policy=ToolResponsePolicy(
            service=ToolService.JIRA,
            category=ResponseCategory.STRUCTURED,
        ),
        value={"name": "human01", "displayName": "Jira Person"},
        current_identity=None,
    )
    bitbucket = transformer.transform(
        tool_name="bitbucket_get_default_reviewers",
        policy=ToolResponsePolicy(
            service=ToolService.BITBUCKET,
            category=ResponseCategory.STRUCTURED,
        ),
        value={
            "name": "human01",
            "displayName": "Bitbucket Person",
            "id": 1,
        },
        current_identity=None,
    )

    assert confluence["username"] == jira["name"] == bitbucket["name"]


def test_unrelated_space_and_content_metadata_remain_unchanged() -> None:
    value = {
        "space": {"key": "DOC", "name": "Documentation"},
        "title": "CANARY page title is content",
        "content": {"value": '{"displayName":"CANARY"}', "format": "storage"},
    }

    assert _transform(value) == value
