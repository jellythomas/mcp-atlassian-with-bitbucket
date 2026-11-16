"""Explicit response policies for every protected Atlassian MCP tool."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Final


class ToolService(str, Enum):
    """Atlassian service that owns a tool."""

    JIRA = "jira"
    CONFLUENCE = "confluence"
    BITBUCKET = "bitbucket"


class ResponseCategory(str, Enum):
    """How the final-response guard must interpret a tool result."""

    STRUCTURED = "structured"
    MIXED = "mixed"
    RAW = "raw"
    METADATA = "metadata"


@dataclass(frozen=True, slots=True)
class ToolResponsePolicy:
    """Service and response-shape contract for one MCP tool."""

    service: ToolService
    category: ResponseCategory
    opaque_string_result: bool = False


class UnknownToolResponsePolicyError(LookupError):
    """Raised when an enabled privacy guard encounters an unclassified tool."""


_BITBUCKET_RAW = (
    "bitbucket_get_file_content",
    "bitbucket_get_pipeline_step_log",
)

_BITBUCKET_MIXED = (
    "bitbucket_compare_commits",
    "bitbucket_get_file_blame",
    "bitbucket_get_pull_request_diff",
    "bitbucket_search_code",
)

_BITBUCKET_METADATA = ("bitbucket_browse_directory",)

_BITBUCKET_OPAQUE_TEXT = (
    "bitbucket_get_pull_request_diff",
    "bitbucket_search_code",
)

_BITBUCKET_STRUCTURED = (
    "bitbucket_add_commit_comment",
    "bitbucket_add_default_reviewer",
    "bitbucket_add_inline_comment",
    "bitbucket_add_pull_request_comment",
    "bitbucket_approve_pull_request",
    "bitbucket_create_branch",
    "bitbucket_create_commit_status",
    "bitbucket_create_pipeline_variable",
    "bitbucket_create_pull_request",
    "bitbucket_create_repository",
    "bitbucket_create_tag",
    "bitbucket_create_webhook",
    "bitbucket_decline_pull_request",
    "bitbucket_delete_branch",
    "bitbucket_delete_comment",
    "bitbucket_delete_repository",
    "bitbucket_delete_tag",
    "bitbucket_delete_webhook",
    "bitbucket_fork_repository",
    "bitbucket_get_branching_model",
    "bitbucket_get_commit",
    "bitbucket_get_default_reviewers",
    "bitbucket_get_deployment",
    "bitbucket_get_file_history",
    "bitbucket_get_pipeline",
    "bitbucket_get_pipeline_config",
    "bitbucket_get_pull_request",
    "bitbucket_get_pull_request_commits",
    "bitbucket_get_repository",
    "bitbucket_get_workspace",
    "bitbucket_list_branch_restrictions",
    "bitbucket_list_branches",
    "bitbucket_list_commit_statuses",
    "bitbucket_list_commits",
    "bitbucket_list_deployment_releases",
    "bitbucket_list_environments",
    "bitbucket_list_forks",
    "bitbucket_list_pipeline_variables",
    "bitbucket_list_pipelines",
    "bitbucket_list_pull_request_comments",
    "bitbucket_list_pull_request_statuses",
    "bitbucket_list_pull_requests",
    "bitbucket_list_repositories",
    "bitbucket_list_tags",
    "bitbucket_list_webhooks",
    "bitbucket_list_workspace_members",
    "bitbucket_list_workspaces",
    "bitbucket_merge_pull_request",
    "bitbucket_reply_to_comment",
    "bitbucket_request_changes_pull_request",
    "bitbucket_stop_pipeline",
    "bitbucket_trigger_pipeline",
    "bitbucket_unapprove_pull_request",
    "bitbucket_update_comment",
    "bitbucket_update_pull_request",
    "bitbucket_update_repository",
    "bitbucket_update_webhook",
)

_CONFLUENCE_RAW = (
    "confluence_download_attachment",
    "confluence_download_content_attachments",
)

_CONFLUENCE_MIXED = (
    "confluence_add_comment",
    "confluence_add_inline_comment",
    "confluence_copy_page",
    "confluence_create_page",
    "confluence_create_page_from_template",
    "confluence_get_comments",
    "confluence_get_inline_comments",
    "confluence_get_page",
    "confluence_get_page_diff",
    "confluence_get_page_history",
    "confluence_get_page_images",
    "confluence_get_page_template",
    "confluence_list_page_templates",
    "confluence_move_page",
    "confluence_reply_to_comment",
    "confluence_search",
    "confluence_update_page",
    "confluence_update_page_section",
)

_CONFLUENCE_METADATA = (
    "confluence_get_attachments",
    "confluence_upload_attachment",
    "confluence_upload_attachments",
)

_CONFLUENCE_STRUCTURED = (
    "confluence_add_label",
    "confluence_check_content_permissions",
    "confluence_delete_attachment",
    "confluence_delete_page",
    "confluence_get_labels",
    "confluence_get_page_children",
    "confluence_get_page_restrictions",
    "confluence_get_page_views",
    "confluence_get_space_page_tree",
    "confluence_get_space_permissions",
    "confluence_search_user",
    "confluence_set_page_restrictions",
)

_JIRA_RAW = ("jira_download_attachments",)

_JIRA_MIXED = (
    "jira_add_comment",
    "jira_add_worklog",
    "jira_assign_issue",
    "jira_batch_create_issues",
    "jira_batch_create_versions",
    "jira_batch_get_changelogs",
    "jira_create_customer_request",
    "jira_create_issue",
    "jira_create_sprint",
    "jira_create_version",
    "jira_edit_comment",
    "jira_get_all_projects",
    "jira_get_board_issues",
    "jira_get_cross_project_dependencies",
    "jira_get_issue",
    "jira_get_issue_development_info",
    "jira_get_issue_images",
    "jira_get_issue_proforma_forms",
    "jira_get_issues_development_info",
    "jira_get_proforma_form_details",
    "jira_get_project_components",
    "jira_get_project_epic_hierarchy",
    "jira_get_project_issue_types",
    "jira_get_project_issues",
    "jira_get_project_versions",
    "jira_get_queue_issues",
    "jira_get_request_type_fields",
    "jira_get_request_types",
    "jira_get_sprint_issues",
    "jira_get_sprints_from_board",
    "jira_get_worklog",
    "jira_link_to_epic",
    "jira_move_issue",
    "jira_search",
    "jira_transition_issue",
    "jira_update_issue",
    "jira_update_proforma_form_answers",
    "jira_update_sprint",
    "jira_update_version",
)

_JIRA_STRUCTURED = (
    "jira_add_issues_to_sprint",
    "jira_add_watcher",
    "jira_create_issue_link",
    "jira_create_remote_issue_link",
    "jira_delete_issue",
    "jira_get_agile_boards",
    "jira_get_create_fields",
    "jira_get_field_options",
    "jira_get_issue_dates",
    "jira_get_issue_sla",
    "jira_get_issue_watchers",
    "jira_get_link_types",
    "jira_get_project_fields",
    "jira_get_service_desk_for_project",
    "jira_get_service_desk_queues",
    "jira_get_transitions",
    "jira_get_user_profile",
    "jira_move_issues_to_backlog",
    "jira_remove_issue_link",
    "jira_remove_watcher",
    "jira_search_assignable_users",
    "jira_search_fields",
    "jira_search_projects",
)


def _build_registry() -> dict[str, ToolResponsePolicy]:
    groups = (
        (ToolService.BITBUCKET, ResponseCategory.RAW, _BITBUCKET_RAW),
        (ToolService.BITBUCKET, ResponseCategory.MIXED, _BITBUCKET_MIXED),
        (
            ToolService.BITBUCKET,
            ResponseCategory.METADATA,
            _BITBUCKET_METADATA,
        ),
        (
            ToolService.BITBUCKET,
            ResponseCategory.STRUCTURED,
            _BITBUCKET_STRUCTURED,
        ),
        (ToolService.CONFLUENCE, ResponseCategory.RAW, _CONFLUENCE_RAW),
        (ToolService.CONFLUENCE, ResponseCategory.MIXED, _CONFLUENCE_MIXED),
        (
            ToolService.CONFLUENCE,
            ResponseCategory.METADATA,
            _CONFLUENCE_METADATA,
        ),
        (
            ToolService.CONFLUENCE,
            ResponseCategory.STRUCTURED,
            _CONFLUENCE_STRUCTURED,
        ),
        (ToolService.JIRA, ResponseCategory.RAW, _JIRA_RAW),
        (ToolService.JIRA, ResponseCategory.MIXED, _JIRA_MIXED),
        (ToolService.JIRA, ResponseCategory.STRUCTURED, _JIRA_STRUCTURED),
    )
    result: dict[str, ToolResponsePolicy] = {}
    for service, category, names in groups:
        expected_prefix = f"{service.value}_"
        for name in names:
            if not name.startswith(expected_prefix):
                message = (
                    f"Tool policy {name!r} does not match service {service.value!r}"
                )
                raise RuntimeError(message)
            if name in result:
                message = f"Duplicate tool response policy: {name}"
                raise RuntimeError(message)
            result[name] = ToolResponsePolicy(
                service=service,
                category=category,
                opaque_string_result=(
                    service is ToolService.BITBUCKET and name in _BITBUCKET_OPAQUE_TEXT
                ),
            )
    return result


TOOL_RESPONSE_POLICIES: Final = MappingProxyType(_build_registry())


def get_tool_response_policy(tool_name: str) -> ToolResponsePolicy:
    """Return the explicit policy or fail closed for an unknown tool."""
    try:
        return TOOL_RESPONSE_POLICIES[tool_name]
    except KeyError as exc:
        message = f"No identity privacy response policy for tool: {tool_name}"
        raise UnknownToolResponsePolicyError(message) from exc
