"""Tests for complete Atlassian tool response policy coverage."""

import asyncio
from collections import Counter

import pytest

from mcp_atlassian_with_bitbucket_and_privacy.privacy import (
    TOOL_RESPONSE_POLICIES,
    ResponseCategory,
    ToolService,
    UnknownToolResponsePolicyError,
    get_tool_response_policy,
)
from mcp_atlassian_with_bitbucket_and_privacy.servers.main import main_mcp


def _registered_tool_names() -> set[str]:
    async def load() -> set[str]:
        return {tool.name for tool in await main_mcp.list_tools()}

    return asyncio.run(load())


def test_registry_exactly_matches_registered_tools() -> None:
    assert set(TOOL_RESPONSE_POLICIES) == _registered_tool_names()


def test_registry_covers_every_service_and_category() -> None:
    service_counts = Counter(
        policy.service for policy in TOOL_RESPONSE_POLICIES.values()
    )
    category_counts = Counter(
        policy.category for policy in TOOL_RESPONSE_POLICIES.values()
    )

    assert service_counts == {
        ToolService.JIRA: 63,
        ToolService.CONFLUENCE: 35,
        ToolService.BITBUCKET: 64,
    }
    assert set(category_counts) == set(ResponseCategory)


@pytest.mark.parametrize(
    "tool_name,service,category",
    [
        (
            "bitbucket_get_file_content",
            ToolService.BITBUCKET,
            ResponseCategory.RAW,
        ),
        (
            "bitbucket_get_pull_request_diff",
            ToolService.BITBUCKET,
            ResponseCategory.MIXED,
        ),
        (
            "bitbucket_browse_directory",
            ToolService.BITBUCKET,
            ResponseCategory.METADATA,
        ),
        (
            "confluence_download_attachment",
            ToolService.CONFLUENCE,
            ResponseCategory.RAW,
        ),
        (
            "confluence_get_page",
            ToolService.CONFLUENCE,
            ResponseCategory.MIXED,
        ),
        (
            "jira_download_attachments",
            ToolService.JIRA,
            ResponseCategory.RAW,
        ),
        (
            "jira_get_issue",
            ToolService.JIRA,
            ResponseCategory.MIXED,
        ),
        (
            "jira_get_user_profile",
            ToolService.JIRA,
            ResponseCategory.STRUCTURED,
        ),
    ],
)
def test_representative_tool_policies(
    tool_name: str,
    service: ToolService,
    category: ResponseCategory,
) -> None:
    policy = get_tool_response_policy(tool_name)

    assert policy.service is service
    assert policy.category is category


def test_unknown_tool_fails_closed() -> None:
    with pytest.raises(UnknownToolResponsePolicyError, match="no_such_tool"):
        get_tool_response_policy("jira_no_such_tool")


def test_only_bitbucket_text_tools_have_opaque_string_contract() -> None:
    opaque_tools = {
        name
        for name, policy in TOOL_RESPONSE_POLICIES.items()
        if policy.opaque_string_result
    }

    assert opaque_tools == {
        "bitbucket_get_pull_request_diff",
        "bitbucket_search_code",
    }
    assert get_tool_response_policy("jira_get_issue").opaque_string_result is False
