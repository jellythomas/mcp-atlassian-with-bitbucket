"""Bitbucket FastMCP server instance and tool definitions."""

import json
import logging
from typing import Annotated

from fastmcp import Context, FastMCP
from pydantic import Field

from mcp_atlassian.servers.dependencies import get_bitbucket_fetcher
from mcp_atlassian.utils.decorators import check_write_access

logger = logging.getLogger(__name__)

bitbucket_mcp = FastMCP(
    name="Bitbucket MCP Service",
    instructions="Provides tools for interacting with Atlassian Bitbucket (Cloud and Server/Data Center).",
)


# ==================================================================
# Repository tools (toolset: bitbucket_repositories)
# ==================================================================


@bitbucket_mcp.tool(
    tags={"bitbucket", "read", "toolset:bitbucket_repositories"},
    annotations={"title": "List Repositories", "readOnlyHint": True},
)
async def list_repositories(
    ctx: Context,
    workspace: Annotated[
        str | None,
        Field(
            description="Workspace slug (Cloud) or omit to use default. Required for Cloud.",
            default=None,
        ),
    ] = None,
    project_key: Annotated[
        str | None,
        Field(
            description="Project key filter (Server/DC only).",
            default=None,
        ),
    ] = None,
    query: Annotated[
        str | None,
        Field(description="Search query to filter repositories.", default=None),
    ] = None,
    max_results: Annotated[
        int,
        Field(
            description="Maximum number of results to return.", ge=1, le=100, default=25
        ),
    ] = 25,
) -> str:
    """List repositories in a workspace (Cloud) or project (Server/DC)."""
    client = await get_bitbucket_fetcher(ctx)
    result = client.list_repositories(
        workspace=workspace,
        project_key=project_key,
        query=query,
        max_results=max_results,
    )
    return json.dumps(result, indent=2, ensure_ascii=False)


@bitbucket_mcp.tool(
    tags={"bitbucket", "read", "toolset:bitbucket_repositories"},
    annotations={"title": "Get Repository", "readOnlyHint": True},
)
async def get_repository(
    ctx: Context,
    repo_slug: Annotated[
        str, Field(description="Repository slug (URL-friendly name).")
    ],
    workspace: Annotated[
        str | None,
        Field(
            description="Workspace slug (Cloud). Uses default if omitted.", default=None
        ),
    ] = None,
    project_key: Annotated[
        str | None,
        Field(
            description="Project key (Server/DC). Uses default if omitted.",
            default=None,
        ),
    ] = None,
) -> str:
    """Get details of a specific repository."""
    client = await get_bitbucket_fetcher(ctx)
    result = client.get_repository(
        repo_slug=repo_slug,
        workspace=workspace,
        project_key=project_key,
    )
    return json.dumps(result, indent=2, ensure_ascii=False)


@bitbucket_mcp.tool(
    tags={"bitbucket", "write", "toolset:bitbucket_repositories"},
    annotations={
        "title": "Create Repository",
        "readOnlyHint": False,
        "destructiveHint": False,
    },
)
@check_write_access
async def create_repository(
    ctx: Context,
    repo_slug: Annotated[
        str, Field(description="Repository slug (URL-friendly name).")
    ],
    workspace: Annotated[
        str | None,
        Field(description="Workspace slug (Cloud).", default=None),
    ] = None,
    project_key: Annotated[
        str | None,
        Field(description="Project key (Server/DC).", default=None),
    ] = None,
    is_private: Annotated[
        bool, Field(description="Whether the repository is private.", default=True)
    ] = True,
    description: Annotated[
        str, Field(description="Repository description.", default="")
    ] = "",
) -> str:
    """Create a new repository."""
    client = await get_bitbucket_fetcher(ctx)
    result = client.create_repository(
        repo_slug=repo_slug,
        workspace=workspace,
        project_key=project_key,
        is_private=is_private,
        description=description,
    )
    return json.dumps(result, indent=2, ensure_ascii=False)


@bitbucket_mcp.tool(
    tags={"bitbucket", "write", "toolset:bitbucket_repositories"},
    annotations={
        "title": "Update Repository",
        "readOnlyHint": False,
        "destructiveHint": False,
    },
)
@check_write_access
async def update_repository(
    ctx: Context,
    repo_slug: Annotated[str, Field(description="Repository slug.")],
    workspace: Annotated[
        str | None,
        Field(description="Workspace slug (Cloud).", default=None),
    ] = None,
    project_key: Annotated[
        str | None,
        Field(description="Project key (Server/DC).", default=None),
    ] = None,
    description: Annotated[
        str | None,
        Field(description="New description.", default=None),
    ] = None,
    is_private: Annotated[
        bool | None,
        Field(description="Change visibility.", default=None),
    ] = None,
    language: Annotated[
        str | None,
        Field(description="Change programming language.", default=None),
    ] = None,
) -> str:
    """Update repository settings."""
    client = await get_bitbucket_fetcher(ctx)
    result = client.update_repository(
        repo_slug=repo_slug,
        workspace=workspace,
        project_key=project_key,
        description=description,
        is_private=is_private,
        language=language,
    )
    return json.dumps(result, indent=2, ensure_ascii=False)


@bitbucket_mcp.tool(
    tags={"bitbucket", "write", "toolset:bitbucket_repositories"},
    annotations={
        "title": "Delete Repository",
        "readOnlyHint": False,
        "destructiveHint": True,
    },
)
@check_write_access
async def delete_repository(
    ctx: Context,
    repo_slug: Annotated[str, Field(description="Repository slug.")],
    workspace: Annotated[
        str | None,
        Field(description="Workspace slug (Cloud).", default=None),
    ] = None,
    project_key: Annotated[
        str | None,
        Field(description="Project key (Server/DC).", default=None),
    ] = None,
) -> str:
    """Delete a repository. This action is irreversible."""
    client = await get_bitbucket_fetcher(ctx)
    client.delete_repository(
        repo_slug=repo_slug,
        workspace=workspace,
        project_key=project_key,
    )
    return json.dumps({"status": "Repository deleted successfully"}, indent=2)


@bitbucket_mcp.tool(
    tags={"bitbucket", "write", "toolset:bitbucket_repositories"},
    annotations={
        "title": "Fork Repository",
        "readOnlyHint": False,
        "destructiveHint": False,
    },
)
@check_write_access
async def fork_repository(
    ctx: Context,
    repo_slug: Annotated[str, Field(description="Source repository slug.")],
    workspace: Annotated[
        str | None,
        Field(description="Source workspace slug (Cloud).", default=None),
    ] = None,
    project_key: Annotated[
        str | None,
        Field(description="Source project key (Server/DC).", default=None),
    ] = None,
    new_name: Annotated[
        str | None,
        Field(description="Name for the forked repository.", default=None),
    ] = None,
    target_workspace: Annotated[
        str | None,
        Field(description="Target workspace for fork (Cloud only).", default=None),
    ] = None,
    target_project_key: Annotated[
        str | None,
        Field(description="Target project for fork (Server/DC only).", default=None),
    ] = None,
) -> str:
    """Fork a repository."""
    client = await get_bitbucket_fetcher(ctx)
    result = client.fork_repository(
        repo_slug=repo_slug,
        workspace=workspace,
        project_key=project_key,
        new_name=new_name,
        target_workspace=target_workspace,
        target_project_key=target_project_key,
    )
    return json.dumps(result, indent=2, ensure_ascii=False)


@bitbucket_mcp.tool(
    tags={"bitbucket", "read", "toolset:bitbucket_repositories"},
    annotations={"title": "List Forks", "readOnlyHint": True},
)
async def list_forks(
    ctx: Context,
    repo_slug: Annotated[str, Field(description="Repository slug.")],
    workspace: Annotated[
        str | None,
        Field(description="Workspace slug (Cloud).", default=None),
    ] = None,
    project_key: Annotated[
        str | None,
        Field(description="Project key (Server/DC).", default=None),
    ] = None,
    max_results: Annotated[
        int,
        Field(description="Maximum results.", ge=1, le=100, default=25),
    ] = 25,
) -> str:
    """List forks of a repository."""
    client = await get_bitbucket_fetcher(ctx)
    result = client.list_forks(
        repo_slug=repo_slug,
        workspace=workspace,
        project_key=project_key,
        max_results=max_results,
    )
    return json.dumps(result, indent=2, ensure_ascii=False)


# ==================================================================
# Pull Request tools (toolset: bitbucket_pull_requests)
# ==================================================================


@bitbucket_mcp.tool(
    tags={"bitbucket", "read", "toolset:bitbucket_pull_requests"},
    annotations={"title": "List Pull Requests", "readOnlyHint": True},
)
async def list_pull_requests(
    ctx: Context,
    repo_slug: Annotated[str, Field(description="Repository slug.")],
    workspace: Annotated[
        str | None,
        Field(description="Workspace slug (Cloud).", default=None),
    ] = None,
    project_key: Annotated[
        str | None,
        Field(description="Project key (Server/DC).", default=None),
    ] = None,
    state: Annotated[
        str,
        Field(
            description="Filter by state: OPEN, MERGED, DECLINED, SUPERSEDED.",
            default="OPEN",
        ),
    ] = "OPEN",
    max_results: Annotated[
        int,
        Field(description="Maximum results.", ge=1, le=100, default=25),
    ] = 25,
) -> str:
    """List pull requests for a repository."""
    client = await get_bitbucket_fetcher(ctx)
    result = client.list_pull_requests(
        repo_slug=repo_slug,
        workspace=workspace,
        project_key=project_key,
        state=state,
        max_results=max_results,
    )
    return json.dumps(result, indent=2, ensure_ascii=False)


@bitbucket_mcp.tool(
    tags={"bitbucket", "read", "toolset:bitbucket_pull_requests"},
    annotations={"title": "Get Pull Request", "readOnlyHint": True},
)
async def get_pull_request(
    ctx: Context,
    repo_slug: Annotated[str, Field(description="Repository slug.")],
    pr_id: Annotated[int, Field(description="Pull request ID.", ge=1)],
    workspace: Annotated[
        str | None,
        Field(description="Workspace slug (Cloud).", default=None),
    ] = None,
    project_key: Annotated[
        str | None,
        Field(description="Project key (Server/DC).", default=None),
    ] = None,
    compact: Annotated[
        bool,
        Field(
            description="Return only essential fields (title, author, branches, "
            "state, description, reviewers) instead of the full API response. "
            "Reduces output size by ~90%. Recommended for LLM consumption.",
            default=False,
        ),
    ] = False,
) -> str:
    """Get details of a specific pull request."""
    client = await get_bitbucket_fetcher(ctx)
    result = client.get_pull_request(
        repo_slug=repo_slug,
        pr_id=pr_id,
        workspace=workspace,
        project_key=project_key,
        compact=compact,
    )
    return json.dumps(result, indent=2, ensure_ascii=False)


@bitbucket_mcp.tool(
    tags={"bitbucket", "read", "toolset:bitbucket_pull_requests"},
    annotations={"title": "Get Pull Request Diff", "readOnlyHint": True},
)
async def get_pull_request_diff(
    ctx: Context,
    repo_slug: Annotated[str, Field(description="Repository slug.")],
    pr_id: Annotated[int, Field(description="Pull request ID.", ge=1)],
    workspace: Annotated[
        str | None,
        Field(description="Workspace slug (Cloud).", default=None),
    ] = None,
    project_key: Annotated[
        str | None,
        Field(description="Project key (Server/DC).", default=None),
    ] = None,
    save_to_file: Annotated[
        bool,
        Field(
            description="Save diff to a temporary file and return only the "
            "file path and metadata (size, line count) instead of the raw "
            "diff text. Use this for large diffs to avoid flooding the "
            "context window. Read the file separately with a file-read tool.",
            default=False,
        ),
    ] = False,
) -> str:
    """Get the diff for a pull request."""
    client = await get_bitbucket_fetcher(ctx)
    result = client.get_pull_request_diff(
        repo_slug=repo_slug,
        pr_id=pr_id,
        workspace=workspace,
        project_key=project_key,
        save_to_file=save_to_file,
    )
    if isinstance(result, dict):
        return json.dumps(result, indent=2, ensure_ascii=False)
    return result


@bitbucket_mcp.tool(
    tags={"bitbucket", "write", "toolset:bitbucket_pull_requests"},
    annotations={
        "title": "Create Pull Request",
        "readOnlyHint": False,
        "destructiveHint": False,
    },
)
@check_write_access
async def create_pull_request(
    ctx: Context,
    repo_slug: Annotated[str, Field(description="Repository slug.")],
    title: Annotated[str, Field(description="Pull request title.")],
    source_branch: Annotated[str, Field(description="Source branch name.")],
    destination_branch: Annotated[str, Field(description="Target branch name.")],
    description: Annotated[
        str, Field(description="Pull request description.", default="")
    ] = "",
    workspace: Annotated[
        str | None,
        Field(description="Workspace slug (Cloud).", default=None),
    ] = None,
    project_key: Annotated[
        str | None,
        Field(description="Project key (Server/DC).", default=None),
    ] = None,
    reviewers: Annotated[
        str | None,
        Field(
            description="Comma-separated list of reviewer usernames or UUIDs.",
            default=None,
        ),
    ] = None,
    close_source_branch: Annotated[
        bool,
        Field(description="Close source branch on merge (Cloud only).", default=False),
    ] = False,
) -> str:
    """Create a new pull request."""
    client = await get_bitbucket_fetcher(ctx)
    reviewer_list = [r.strip() for r in reviewers.split(",")] if reviewers else None
    result = client.create_pull_request(
        repo_slug=repo_slug,
        title=title,
        source_branch=source_branch,
        destination_branch=destination_branch,
        description=description,
        workspace=workspace,
        project_key=project_key,
        reviewers=reviewer_list,
        close_source_branch=close_source_branch,
    )
    return json.dumps(result, indent=2, ensure_ascii=False)


@bitbucket_mcp.tool(
    tags={"bitbucket", "write", "toolset:bitbucket_pull_requests"},
    annotations={
        "title": "Merge Pull Request",
        "readOnlyHint": False,
        "destructiveHint": True,
    },
)
@check_write_access
async def merge_pull_request(
    ctx: Context,
    repo_slug: Annotated[str, Field(description="Repository slug.")],
    pr_id: Annotated[int, Field(description="Pull request ID.", ge=1)],
    workspace: Annotated[
        str | None,
        Field(description="Workspace slug (Cloud).", default=None),
    ] = None,
    project_key: Annotated[
        str | None,
        Field(description="Project key (Server/DC).", default=None),
    ] = None,
    merge_strategy: Annotated[
        str | None,
        Field(
            description="Merge strategy: merge_commit, squash, or fast_forward (Cloud only).",
            default=None,
        ),
    ] = None,
    message: Annotated[
        str | None,
        Field(description="Merge commit message.", default=None),
    ] = None,
) -> str:
    """Merge a pull request."""
    client = await get_bitbucket_fetcher(ctx)
    result = client.merge_pull_request(
        repo_slug=repo_slug,
        pr_id=pr_id,
        workspace=workspace,
        project_key=project_key,
        merge_strategy=merge_strategy,
        message=message,
    )
    return json.dumps(result, indent=2, ensure_ascii=False)


@bitbucket_mcp.tool(
    tags={"bitbucket", "write", "toolset:bitbucket_pull_requests"},
    annotations={
        "title": "Add Pull Request Comment",
        "readOnlyHint": False,
        "destructiveHint": False,
    },
)
@check_write_access
async def add_pull_request_comment(
    ctx: Context,
    repo_slug: Annotated[str, Field(description="Repository slug.")],
    pr_id: Annotated[int, Field(description="Pull request ID.", ge=1)],
    content: Annotated[str, Field(description="Comment text content.")],
    workspace: Annotated[
        str | None,
        Field(description="Workspace slug (Cloud).", default=None),
    ] = None,
    project_key: Annotated[
        str | None,
        Field(description="Project key (Server/DC).", default=None),
    ] = None,
) -> str:
    """Add a comment to a pull request."""
    client = await get_bitbucket_fetcher(ctx)
    result = client.add_pull_request_comment(
        repo_slug=repo_slug,
        pr_id=pr_id,
        content=content,
        workspace=workspace,
        project_key=project_key,
    )
    return json.dumps(result, indent=2, ensure_ascii=False)


@bitbucket_mcp.tool(
    tags={"bitbucket", "write", "toolset:bitbucket_pull_requests"},
    annotations={
        "title": "Update Pull Request",
        "readOnlyHint": False,
        "destructiveHint": False,
    },
)
@check_write_access
async def update_pull_request(
    ctx: Context,
    repo_slug: Annotated[str, Field(description="Repository slug.")],
    pr_id: Annotated[int, Field(description="Pull request ID.", ge=1)],
    workspace: Annotated[
        str | None,
        Field(description="Workspace slug (Cloud).", default=None),
    ] = None,
    project_key: Annotated[
        str | None,
        Field(description="Project key (Server/DC).", default=None),
    ] = None,
    title: Annotated[
        str | None,
        Field(description="New title.", default=None),
    ] = None,
    description: Annotated[
        str | None,
        Field(description="New description.", default=None),
    ] = None,
    destination_branch: Annotated[
        str | None,
        Field(description="New destination branch.", default=None),
    ] = None,
    reviewers: Annotated[
        str | None,
        Field(
            description="Comma-separated list of new reviewer usernames/UUIDs.",
            default=None,
        ),
    ] = None,
) -> str:
    """Update a pull request's title, description, destination, or reviewers."""
    client = await get_bitbucket_fetcher(ctx)
    reviewer_list = [r.strip() for r in reviewers.split(",")] if reviewers else None
    result = client.update_pull_request(
        repo_slug=repo_slug,
        pr_id=pr_id,
        workspace=workspace,
        project_key=project_key,
        title=title,
        description=description,
        destination_branch=destination_branch,
        reviewers=reviewer_list,
    )
    return json.dumps(result, indent=2, ensure_ascii=False)


@bitbucket_mcp.tool(
    tags={"bitbucket", "write", "toolset:bitbucket_pull_requests"},
    annotations={
        "title": "Decline Pull Request",
        "readOnlyHint": False,
        "destructiveHint": True,
    },
)
@check_write_access
async def decline_pull_request(
    ctx: Context,
    repo_slug: Annotated[str, Field(description="Repository slug.")],
    pr_id: Annotated[int, Field(description="Pull request ID.", ge=1)],
    workspace: Annotated[
        str | None,
        Field(description="Workspace slug (Cloud).", default=None),
    ] = None,
    project_key: Annotated[
        str | None,
        Field(description="Project key (Server/DC).", default=None),
    ] = None,
) -> str:
    """Decline a pull request."""
    client = await get_bitbucket_fetcher(ctx)
    result = client.decline_pull_request(
        repo_slug=repo_slug,
        pr_id=pr_id,
        workspace=workspace,
        project_key=project_key,
    )
    return json.dumps(result, indent=2, ensure_ascii=False)


@bitbucket_mcp.tool(
    tags={"bitbucket", "write", "toolset:bitbucket_pull_requests"},
    annotations={
        "title": "Approve Pull Request",
        "readOnlyHint": False,
        "destructiveHint": False,
    },
)
@check_write_access
async def approve_pull_request(
    ctx: Context,
    repo_slug: Annotated[str, Field(description="Repository slug.")],
    pr_id: Annotated[int, Field(description="Pull request ID.", ge=1)],
    workspace: Annotated[
        str | None,
        Field(description="Workspace slug (Cloud).", default=None),
    ] = None,
    project_key: Annotated[
        str | None,
        Field(description="Project key (Server/DC).", default=None),
    ] = None,
) -> str:
    """Approve a pull request."""
    client = await get_bitbucket_fetcher(ctx)
    result = client.approve_pull_request(
        repo_slug=repo_slug,
        pr_id=pr_id,
        workspace=workspace,
        project_key=project_key,
    )
    return json.dumps(result, indent=2, ensure_ascii=False)


@bitbucket_mcp.tool(
    tags={"bitbucket", "write", "toolset:bitbucket_pull_requests"},
    annotations={
        "title": "Unapprove Pull Request",
        "readOnlyHint": False,
        "destructiveHint": False,
    },
)
@check_write_access
async def unapprove_pull_request(
    ctx: Context,
    repo_slug: Annotated[str, Field(description="Repository slug.")],
    pr_id: Annotated[int, Field(description="Pull request ID.", ge=1)],
    workspace: Annotated[
        str | None,
        Field(description="Workspace slug (Cloud).", default=None),
    ] = None,
    project_key: Annotated[
        str | None,
        Field(description="Project key (Server/DC).", default=None),
    ] = None,
) -> str:
    """Remove approval from a pull request."""
    client = await get_bitbucket_fetcher(ctx)
    client.unapprove_pull_request(
        repo_slug=repo_slug,
        pr_id=pr_id,
        workspace=workspace,
        project_key=project_key,
    )
    return json.dumps({"status": "Approval removed successfully"}, indent=2)


@bitbucket_mcp.tool(
    tags={"bitbucket", "write", "toolset:bitbucket_pull_requests"},
    annotations={
        "title": "Request Changes on Pull Request",
        "readOnlyHint": False,
        "destructiveHint": False,
    },
)
@check_write_access
async def request_changes_pull_request(
    ctx: Context,
    repo_slug: Annotated[str, Field(description="Repository slug.")],
    pr_id: Annotated[int, Field(description="Pull request ID.", ge=1)],
    workspace: Annotated[
        str | None,
        Field(description="Workspace slug (Cloud).", default=None),
    ] = None,
    project_key: Annotated[
        str | None,
        Field(description="Project key (Server/DC).", default=None),
    ] = None,
) -> str:
    """Request changes on a pull request."""
    client = await get_bitbucket_fetcher(ctx)
    result = client.request_changes_pull_request(
        repo_slug=repo_slug,
        pr_id=pr_id,
        workspace=workspace,
        project_key=project_key,
    )
    return json.dumps(result, indent=2, ensure_ascii=False)


@bitbucket_mcp.tool(
    tags={"bitbucket", "read", "toolset:bitbucket_pull_requests"},
    annotations={"title": "Get Pull Request Commits", "readOnlyHint": True},
)
async def get_pull_request_commits(
    ctx: Context,
    repo_slug: Annotated[str, Field(description="Repository slug.")],
    pr_id: Annotated[int, Field(description="Pull request ID.", ge=1)],
    workspace: Annotated[
        str | None,
        Field(description="Workspace slug (Cloud).", default=None),
    ] = None,
    project_key: Annotated[
        str | None,
        Field(description="Project key (Server/DC).", default=None),
    ] = None,
    max_results: Annotated[
        int,
        Field(description="Maximum results.", ge=1, le=100, default=100),
    ] = 100,
) -> str:
    """Get the list of commits in a pull request."""
    client = await get_bitbucket_fetcher(ctx)
    result = client.get_pull_request_commits(
        repo_slug=repo_slug,
        pr_id=pr_id,
        workspace=workspace,
        project_key=project_key,
        max_results=max_results,
    )
    return json.dumps(result, indent=2, ensure_ascii=False)


@bitbucket_mcp.tool(
    tags={"bitbucket", "read", "toolset:bitbucket_pull_requests"},
    annotations={"title": "List Pull Request Comments", "readOnlyHint": True},
)
async def list_pull_request_comments(
    ctx: Context,
    repo_slug: Annotated[str, Field(description="Repository slug.")],
    pr_id: Annotated[int, Field(description="Pull request ID.", ge=1)],
    workspace: Annotated[
        str | None,
        Field(description="Workspace slug (Cloud).", default=None),
    ] = None,
    project_key: Annotated[
        str | None,
        Field(description="Project key (Server/DC).", default=None),
    ] = None,
    max_results: Annotated[
        int,
        Field(description="Maximum results.", ge=1, le=100, default=100),
    ] = 100,
) -> str:
    """List all comments on a pull request."""
    client = await get_bitbucket_fetcher(ctx)
    result = client.list_pull_request_comments(
        repo_slug=repo_slug,
        pr_id=pr_id,
        workspace=workspace,
        project_key=project_key,
        max_results=max_results,
    )
    return json.dumps(result, indent=2, ensure_ascii=False)


@bitbucket_mcp.tool(
    tags={"bitbucket", "write", "toolset:bitbucket_pull_requests"},
    annotations={
        "title": "Add Inline Comment",
        "readOnlyHint": False,
        "destructiveHint": False,
    },
)
@check_write_access
async def add_inline_comment(
    ctx: Context,
    repo_slug: Annotated[str, Field(description="Repository slug.")],
    pr_id: Annotated[int, Field(description="Pull request ID.", ge=1)],
    content: Annotated[str, Field(description="Comment text.")],
    file_path: Annotated[str, Field(description="File path to comment on.")],
    line: Annotated[int, Field(description="Line number.", ge=1)],
    workspace: Annotated[
        str | None,
        Field(description="Workspace slug (Cloud).", default=None),
    ] = None,
    project_key: Annotated[
        str | None,
        Field(description="Project key (Server/DC).", default=None),
    ] = None,
    side: Annotated[
        str,
        Field(
            description="Diff side: 'new' (added) or 'old' (removed).", default="new"
        ),
    ] = "new",
) -> str:
    """Add an inline comment on a specific file and line in a pull request."""
    client = await get_bitbucket_fetcher(ctx)
    result = client.add_inline_comment(
        repo_slug=repo_slug,
        pr_id=pr_id,
        content=content,
        file_path=file_path,
        line=line,
        workspace=workspace,
        project_key=project_key,
        side=side,
    )
    return json.dumps(result, indent=2, ensure_ascii=False)


@bitbucket_mcp.tool(
    tags={"bitbucket", "write", "toolset:bitbucket_pull_requests"},
    annotations={
        "title": "Reply to Comment",
        "readOnlyHint": False,
        "destructiveHint": False,
    },
)
@check_write_access
async def reply_to_comment(
    ctx: Context,
    repo_slug: Annotated[str, Field(description="Repository slug.")],
    pr_id: Annotated[int, Field(description="Pull request ID.", ge=1)],
    comment_id: Annotated[
        int, Field(description="Parent comment ID to reply to.", ge=1)
    ],
    content: Annotated[str, Field(description="Reply text.")],
    workspace: Annotated[
        str | None,
        Field(description="Workspace slug (Cloud).", default=None),
    ] = None,
    project_key: Annotated[
        str | None,
        Field(description="Project key (Server/DC).", default=None),
    ] = None,
) -> str:
    """Reply to an existing pull request comment."""
    client = await get_bitbucket_fetcher(ctx)
    result = client.reply_to_comment(
        repo_slug=repo_slug,
        pr_id=pr_id,
        comment_id=comment_id,
        content=content,
        workspace=workspace,
        project_key=project_key,
    )
    return json.dumps(result, indent=2, ensure_ascii=False)


@bitbucket_mcp.tool(
    tags={"bitbucket", "write", "toolset:bitbucket_pull_requests"},
    annotations={
        "title": "Update Comment",
        "readOnlyHint": False,
        "destructiveHint": False,
    },
)
@check_write_access
async def update_comment(
    ctx: Context,
    repo_slug: Annotated[str, Field(description="Repository slug.")],
    pr_id: Annotated[int, Field(description="Pull request ID.", ge=1)],
    comment_id: Annotated[int, Field(description="Comment ID to update.", ge=1)],
    content: Annotated[str, Field(description="New comment text.")],
    workspace: Annotated[
        str | None,
        Field(description="Workspace slug (Cloud).", default=None),
    ] = None,
    project_key: Annotated[
        str | None,
        Field(description="Project key (Server/DC).", default=None),
    ] = None,
) -> str:
    """Update an existing pull request comment."""
    client = await get_bitbucket_fetcher(ctx)
    result = client.update_comment(
        repo_slug=repo_slug,
        pr_id=pr_id,
        comment_id=comment_id,
        content=content,
        workspace=workspace,
        project_key=project_key,
    )
    return json.dumps(result, indent=2, ensure_ascii=False)


@bitbucket_mcp.tool(
    tags={"bitbucket", "write", "toolset:bitbucket_pull_requests"},
    annotations={
        "title": "Delete Comment",
        "readOnlyHint": False,
        "destructiveHint": True,
    },
)
@check_write_access
async def delete_comment(
    ctx: Context,
    repo_slug: Annotated[str, Field(description="Repository slug.")],
    pr_id: Annotated[int, Field(description="Pull request ID.", ge=1)],
    comment_id: Annotated[int, Field(description="Comment ID to delete.", ge=1)],
    workspace: Annotated[
        str | None,
        Field(description="Workspace slug (Cloud).", default=None),
    ] = None,
    project_key: Annotated[
        str | None,
        Field(description="Project key (Server/DC).", default=None),
    ] = None,
) -> str:
    """Delete a pull request comment."""
    client = await get_bitbucket_fetcher(ctx)
    client.delete_comment(
        repo_slug=repo_slug,
        pr_id=pr_id,
        comment_id=comment_id,
        workspace=workspace,
        project_key=project_key,
    )
    return json.dumps({"status": "Comment deleted successfully"}, indent=2)


@bitbucket_mcp.tool(
    tags={"bitbucket", "read", "toolset:bitbucket_pull_requests"},
    annotations={"title": "List Pull Request Statuses", "readOnlyHint": True},
)
async def list_pull_request_statuses(
    ctx: Context,
    repo_slug: Annotated[str, Field(description="Repository slug.")],
    pr_id: Annotated[int, Field(description="Pull request ID.", ge=1)],
    workspace: Annotated[
        str | None,
        Field(description="Workspace slug (Cloud).", default=None),
    ] = None,
    project_key: Annotated[
        str | None,
        Field(description="Project key (Server/DC).", default=None),
    ] = None,
    max_results: Annotated[
        int,
        Field(description="Maximum results.", ge=1, le=100, default=25),
    ] = 25,
) -> str:
    """List build statuses for a pull request."""
    client = await get_bitbucket_fetcher(ctx)
    result = client.list_pull_request_statuses(
        repo_slug=repo_slug,
        pr_id=pr_id,
        workspace=workspace,
        project_key=project_key,
        max_results=max_results,
    )
    return json.dumps(result, indent=2, ensure_ascii=False)


# ==================================================================
# Branch tools (toolset: bitbucket_branches)
# ==================================================================


@bitbucket_mcp.tool(
    tags={"bitbucket", "read", "toolset:bitbucket_branches"},
    annotations={"title": "List Branches", "readOnlyHint": True},
)
async def list_branches(
    ctx: Context,
    repo_slug: Annotated[str, Field(description="Repository slug.")],
    workspace: Annotated[
        str | None,
        Field(description="Workspace slug (Cloud).", default=None),
    ] = None,
    project_key: Annotated[
        str | None,
        Field(description="Project key (Server/DC).", default=None),
    ] = None,
    query: Annotated[
        str | None,
        Field(description="Filter branches by name.", default=None),
    ] = None,
    max_results: Annotated[
        int,
        Field(description="Maximum results.", ge=1, le=100, default=25),
    ] = 25,
) -> str:
    """List branches in a repository."""
    client = await get_bitbucket_fetcher(ctx)
    result = client.list_branches(
        repo_slug=repo_slug,
        workspace=workspace,
        project_key=project_key,
        query=query,
        max_results=max_results,
    )
    return json.dumps(result, indent=2, ensure_ascii=False)


@bitbucket_mcp.tool(
    tags={"bitbucket", "write", "toolset:bitbucket_branches"},
    annotations={
        "title": "Create Branch",
        "readOnlyHint": False,
        "destructiveHint": False,
    },
)
@check_write_access
async def create_branch(
    ctx: Context,
    repo_slug: Annotated[str, Field(description="Repository slug.")],
    branch_name: Annotated[str, Field(description="New branch name.")],
    start_point: Annotated[
        str, Field(description="Commit hash or branch name to branch from.")
    ],
    workspace: Annotated[
        str | None,
        Field(description="Workspace slug (Cloud).", default=None),
    ] = None,
    project_key: Annotated[
        str | None,
        Field(description="Project key (Server/DC).", default=None),
    ] = None,
) -> str:
    """Create a new branch in a repository."""
    client = await get_bitbucket_fetcher(ctx)
    result = client.create_branch(
        repo_slug=repo_slug,
        branch_name=branch_name,
        start_point=start_point,
        workspace=workspace,
        project_key=project_key,
    )
    return json.dumps(result, indent=2, ensure_ascii=False)


@bitbucket_mcp.tool(
    tags={"bitbucket", "write", "toolset:bitbucket_branches"},
    annotations={
        "title": "Delete Branch",
        "readOnlyHint": False,
        "destructiveHint": True,
    },
)
@check_write_access
async def delete_branch(
    ctx: Context,
    repo_slug: Annotated[str, Field(description="Repository slug.")],
    branch_name: Annotated[str, Field(description="Branch name to delete.")],
    workspace: Annotated[
        str | None,
        Field(description="Workspace slug (Cloud).", default=None),
    ] = None,
    project_key: Annotated[
        str | None,
        Field(description="Project key (Server/DC).", default=None),
    ] = None,
) -> str:
    """Delete a branch from a repository."""
    client = await get_bitbucket_fetcher(ctx)
    client.delete_branch(
        repo_slug=repo_slug,
        branch_name=branch_name,
        workspace=workspace,
        project_key=project_key,
    )
    return json.dumps({"status": "Branch deleted successfully"}, indent=2)


@bitbucket_mcp.tool(
    tags={"bitbucket", "read", "toolset:bitbucket_branches"},
    annotations={"title": "Get Branching Model", "readOnlyHint": True},
)
async def get_branching_model(
    ctx: Context,
    repo_slug: Annotated[str, Field(description="Repository slug.")],
    workspace: Annotated[
        str | None,
        Field(description="Workspace slug (Cloud).", default=None),
    ] = None,
    project_key: Annotated[
        str | None,
        Field(description="Project key (Server/DC).", default=None),
    ] = None,
) -> str:
    """Get the branching model configuration for a repository."""
    client = await get_bitbucket_fetcher(ctx)
    result = client.get_branching_model(
        repo_slug=repo_slug,
        workspace=workspace,
        project_key=project_key,
    )
    return json.dumps(result, indent=2, ensure_ascii=False)


@bitbucket_mcp.tool(
    tags={"bitbucket", "read", "toolset:bitbucket_branches"},
    annotations={"title": "List Branch Restrictions", "readOnlyHint": True},
)
async def list_branch_restrictions(
    ctx: Context,
    repo_slug: Annotated[str, Field(description="Repository slug.")],
    workspace: Annotated[
        str | None,
        Field(description="Workspace slug (Cloud).", default=None),
    ] = None,
    project_key: Annotated[
        str | None,
        Field(description="Project key (Server/DC).", default=None),
    ] = None,
    max_results: Annotated[
        int,
        Field(description="Maximum results.", ge=1, le=100, default=25),
    ] = 25,
) -> str:
    """List branch restrictions/permissions for a repository."""
    client = await get_bitbucket_fetcher(ctx)
    result = client.list_branch_restrictions(
        repo_slug=repo_slug,
        workspace=workspace,
        project_key=project_key,
        max_results=max_results,
    )
    return json.dumps(result, indent=2, ensure_ascii=False)


# ==================================================================
# Commit tools (toolset: bitbucket_commits)
# ==================================================================


@bitbucket_mcp.tool(
    tags={"bitbucket", "read", "toolset:bitbucket_commits"},
    annotations={"title": "List Commits", "readOnlyHint": True},
)
async def list_commits(
    ctx: Context,
    repo_slug: Annotated[str, Field(description="Repository slug.")],
    workspace: Annotated[
        str | None,
        Field(description="Workspace slug (Cloud).", default=None),
    ] = None,
    project_key: Annotated[
        str | None,
        Field(description="Project key (Server/DC).", default=None),
    ] = None,
    branch: Annotated[
        str | None,
        Field(description="Branch to list commits from.", default=None),
    ] = None,
    max_results: Annotated[
        int,
        Field(description="Maximum results.", ge=1, le=100, default=25),
    ] = 25,
) -> str:
    """List commits for a repository."""
    client = await get_bitbucket_fetcher(ctx)
    result = client.list_commits(
        repo_slug=repo_slug,
        workspace=workspace,
        project_key=project_key,
        branch=branch,
        max_results=max_results,
    )
    return json.dumps(result, indent=2, ensure_ascii=False)


@bitbucket_mcp.tool(
    tags={"bitbucket", "read", "toolset:bitbucket_commits"},
    annotations={"title": "Get Commit", "readOnlyHint": True},
)
async def get_commit(
    ctx: Context,
    repo_slug: Annotated[str, Field(description="Repository slug.")],
    commit_hash: Annotated[
        str, Field(description="Full or abbreviated commit SHA hash.")
    ],
    workspace: Annotated[
        str | None,
        Field(description="Workspace slug (Cloud).", default=None),
    ] = None,
    project_key: Annotated[
        str | None,
        Field(description="Project key (Server/DC).", default=None),
    ] = None,
) -> str:
    """Get details of a specific commit."""
    client = await get_bitbucket_fetcher(ctx)
    result = client.get_commit(
        repo_slug=repo_slug,
        commit_hash=commit_hash,
        workspace=workspace,
        project_key=project_key,
    )
    return json.dumps(result, indent=2, ensure_ascii=False)


@bitbucket_mcp.tool(
    tags={"bitbucket", "read", "toolset:bitbucket_commits"},
    annotations={"title": "Compare Commits", "readOnlyHint": True},
)
async def compare_commits(
    ctx: Context,
    repo_slug: Annotated[str, Field(description="Repository slug.")],
    source: Annotated[str, Field(description="Source commit hash, branch, or tag.")],
    destination: Annotated[
        str, Field(description="Destination commit hash, branch, or tag.")
    ],
    workspace: Annotated[
        str | None,
        Field(description="Workspace slug (Cloud).", default=None),
    ] = None,
    project_key: Annotated[
        str | None,
        Field(description="Project key (Server/DC).", default=None),
    ] = None,
) -> str:
    """Compare two commits or refs (branches/tags) and get the diff."""
    client = await get_bitbucket_fetcher(ctx)
    result = client.compare_commits(
        repo_slug=repo_slug,
        source=source,
        destination=destination,
        workspace=workspace,
        project_key=project_key,
    )
    if isinstance(result, str):
        return result
    return json.dumps(result, indent=2, ensure_ascii=False)


@bitbucket_mcp.tool(
    tags={"bitbucket", "read", "toolset:bitbucket_commits"},
    annotations={"title": "List Commit Statuses", "readOnlyHint": True},
)
async def list_commit_statuses(
    ctx: Context,
    repo_slug: Annotated[str, Field(description="Repository slug.")],
    commit_hash: Annotated[str, Field(description="Commit SHA hash.")],
    workspace: Annotated[
        str | None,
        Field(description="Workspace slug (Cloud).", default=None),
    ] = None,
    project_key: Annotated[
        str | None,
        Field(description="Project key (Server/DC).", default=None),
    ] = None,
    max_results: Annotated[
        int,
        Field(description="Maximum results.", ge=1, le=100, default=25),
    ] = 25,
) -> str:
    """List build statuses for a specific commit."""
    client = await get_bitbucket_fetcher(ctx)
    result = client.list_commit_statuses(
        repo_slug=repo_slug,
        commit_hash=commit_hash,
        workspace=workspace,
        project_key=project_key,
        max_results=max_results,
    )
    return json.dumps(result, indent=2, ensure_ascii=False)


@bitbucket_mcp.tool(
    tags={"bitbucket", "write", "toolset:bitbucket_commits"},
    annotations={
        "title": "Create Commit Status",
        "readOnlyHint": False,
        "destructiveHint": False,
    },
)
@check_write_access
async def create_commit_status(
    ctx: Context,
    repo_slug: Annotated[str, Field(description="Repository slug.")],
    commit_hash: Annotated[str, Field(description="Commit SHA hash.")],
    state: Annotated[
        str,
        Field(description="Build state: SUCCESSFUL, FAILED, INPROGRESS, or STOPPED."),
    ],
    key: Annotated[str, Field(description="Unique key for this build status.")],
    url: Annotated[str, Field(description="URL for the build.")],
    workspace: Annotated[
        str | None,
        Field(description="Workspace slug (Cloud).", default=None),
    ] = None,
    project_key: Annotated[
        str | None,
        Field(description="Project key (Server/DC).", default=None),
    ] = None,
    name: Annotated[
        str, Field(description="Display name for the build.", default="")
    ] = "",
    description: Annotated[
        str, Field(description="Build description.", default="")
    ] = "",
) -> str:
    """Create a build status for a commit."""
    client = await get_bitbucket_fetcher(ctx)
    result = client.create_commit_status(
        repo_slug=repo_slug,
        commit_hash=commit_hash,
        state=state,
        key=key,
        url=url,
        workspace=workspace,
        project_key=project_key,
        name=name,
        description=description,
    )
    return json.dumps(result, indent=2, ensure_ascii=False)


@bitbucket_mcp.tool(
    tags={"bitbucket", "write", "toolset:bitbucket_commits"},
    annotations={
        "title": "Add Commit Comment",
        "readOnlyHint": False,
        "destructiveHint": False,
    },
)
@check_write_access
async def add_commit_comment(
    ctx: Context,
    repo_slug: Annotated[str, Field(description="Repository slug.")],
    commit_hash: Annotated[str, Field(description="Commit SHA hash.")],
    content: Annotated[str, Field(description="Comment text.")],
    workspace: Annotated[
        str | None,
        Field(description="Workspace slug (Cloud).", default=None),
    ] = None,
    project_key: Annotated[
        str | None,
        Field(description="Project key (Server/DC).", default=None),
    ] = None,
) -> str:
    """Add a comment to a specific commit."""
    client = await get_bitbucket_fetcher(ctx)
    result = client.add_commit_comment(
        repo_slug=repo_slug,
        commit_hash=commit_hash,
        content=content,
        workspace=workspace,
        project_key=project_key,
    )
    return json.dumps(result, indent=2, ensure_ascii=False)


# ==================================================================
# Source/File tools (toolset: bitbucket_source)
# ==================================================================


@bitbucket_mcp.tool(
    tags={"bitbucket", "read", "toolset:bitbucket_source"},
    annotations={"title": "Get File Content", "readOnlyHint": True},
)
async def get_file_content(
    ctx: Context,
    repo_slug: Annotated[str, Field(description="Repository slug.")],
    file_path: Annotated[str, Field(description="Path to the file in the repository.")],
    ref: Annotated[
        str | None,
        Field(
            description="Branch, tag, or commit hash. Defaults to default branch.",
            default=None,
        ),
    ] = None,
    workspace: Annotated[
        str | None,
        Field(description="Workspace slug (Cloud).", default=None),
    ] = None,
    project_key: Annotated[
        str | None,
        Field(description="Project key (Server/DC).", default=None),
    ] = None,
) -> str:
    """Get the content of a file from a repository."""
    client = await get_bitbucket_fetcher(ctx)
    return client.get_file_content(
        repo_slug=repo_slug,
        file_path=file_path,
        ref=ref,
        workspace=workspace,
        project_key=project_key,
    )


@bitbucket_mcp.tool(
    tags={"bitbucket", "read", "toolset:bitbucket_source"},
    annotations={"title": "Browse Directory", "readOnlyHint": True},
)
async def browse_directory(
    ctx: Context,
    repo_slug: Annotated[str, Field(description="Repository slug.")],
    path: Annotated[
        str, Field(description="Directory path (empty for root).", default="")
    ] = "",
    ref: Annotated[
        str | None,
        Field(description="Branch, tag, or commit hash.", default=None),
    ] = None,
    workspace: Annotated[
        str | None,
        Field(description="Workspace slug (Cloud).", default=None),
    ] = None,
    project_key: Annotated[
        str | None,
        Field(description="Project key (Server/DC).", default=None),
    ] = None,
    max_results: Annotated[
        int,
        Field(description="Maximum results.", ge=1, le=100, default=100),
    ] = 100,
) -> str:
    """Browse directory contents in a repository."""
    client = await get_bitbucket_fetcher(ctx)
    result = client.browse_directory(
        repo_slug=repo_slug,
        path=path,
        ref=ref,
        workspace=workspace,
        project_key=project_key,
        max_results=max_results,
    )
    return json.dumps(result, indent=2, ensure_ascii=False)


@bitbucket_mcp.tool(
    tags={"bitbucket", "read", "toolset:bitbucket_source"},
    annotations={"title": "Search Code", "readOnlyHint": True},
)
async def search_code(
    ctx: Context,
    query: Annotated[str, Field(description="Search query string.")],
    repo_slug: Annotated[
        str | None,
        Field(description="Optional repository slug to limit search.", default=None),
    ] = None,
    workspace: Annotated[
        str | None,
        Field(description="Workspace slug (Cloud).", default=None),
    ] = None,
    project_key: Annotated[
        str | None,
        Field(description="Project key (Server/DC).", default=None),
    ] = None,
    max_results: Annotated[
        int,
        Field(description="Maximum results.", ge=1, le=100, default=25),
    ] = 25,
) -> str:
    """Search for code across repositories."""
    client = await get_bitbucket_fetcher(ctx)
    result = client.search_code(
        query=query,
        repo_slug=repo_slug,
        workspace=workspace,
        project_key=project_key,
        max_results=max_results,
    )
    return json.dumps(result, indent=2, ensure_ascii=False)


@bitbucket_mcp.tool(
    tags={"bitbucket", "read", "toolset:bitbucket_source"},
    annotations={"title": "Get File Blame", "readOnlyHint": True},
)
async def get_file_blame(
    ctx: Context,
    repo_slug: Annotated[str, Field(description="Repository slug.")],
    file_path: Annotated[str, Field(description="Path to the file.")],
    ref: Annotated[
        str | None,
        Field(description="Branch, tag, or commit hash.", default=None),
    ] = None,
    workspace: Annotated[
        str | None,
        Field(description="Workspace slug (Cloud).", default=None),
    ] = None,
    project_key: Annotated[
        str | None,
        Field(description="Project key (Server/DC).", default=None),
    ] = None,
) -> str:
    """Get blame/annotation information for a file, showing line-by-line authorship."""
    client = await get_bitbucket_fetcher(ctx)
    result = client.get_file_blame(
        repo_slug=repo_slug,
        file_path=file_path,
        ref=ref,
        workspace=workspace,
        project_key=project_key,
    )
    if isinstance(result, str):
        return result
    return json.dumps(result, indent=2, ensure_ascii=False)


@bitbucket_mcp.tool(
    tags={"bitbucket", "read", "toolset:bitbucket_source"},
    annotations={"title": "Get File History", "readOnlyHint": True},
)
async def get_file_history(
    ctx: Context,
    repo_slug: Annotated[str, Field(description="Repository slug.")],
    file_path: Annotated[str, Field(description="Path to the file.")],
    ref: Annotated[
        str | None,
        Field(description="Branch, tag, or commit hash.", default=None),
    ] = None,
    workspace: Annotated[
        str | None,
        Field(description="Workspace slug (Cloud).", default=None),
    ] = None,
    project_key: Annotated[
        str | None,
        Field(description="Project key (Server/DC).", default=None),
    ] = None,
    max_results: Annotated[
        int,
        Field(description="Maximum results.", ge=1, le=100, default=25),
    ] = 25,
) -> str:
    """Get commit history for a specific file."""
    client = await get_bitbucket_fetcher(ctx)
    result = client.get_file_history(
        repo_slug=repo_slug,
        file_path=file_path,
        ref=ref,
        workspace=workspace,
        project_key=project_key,
        max_results=max_results,
    )
    return json.dumps(result, indent=2, ensure_ascii=False)


# ==================================================================
# Tag tools (toolset: bitbucket_tags)
# ==================================================================


@bitbucket_mcp.tool(
    tags={"bitbucket", "read", "toolset:bitbucket_tags"},
    annotations={"title": "List Tags", "readOnlyHint": True},
)
async def list_tags(
    ctx: Context,
    repo_slug: Annotated[str, Field(description="Repository slug.")],
    workspace: Annotated[
        str | None,
        Field(description="Workspace slug (Cloud).", default=None),
    ] = None,
    project_key: Annotated[
        str | None,
        Field(description="Project key (Server/DC).", default=None),
    ] = None,
    max_results: Annotated[
        int,
        Field(description="Maximum results.", ge=1, le=100, default=25),
    ] = 25,
) -> str:
    """List tags for a repository."""
    client = await get_bitbucket_fetcher(ctx)
    result = client.list_tags(
        repo_slug=repo_slug,
        workspace=workspace,
        project_key=project_key,
        max_results=max_results,
    )
    return json.dumps(result, indent=2, ensure_ascii=False)


@bitbucket_mcp.tool(
    tags={"bitbucket", "write", "toolset:bitbucket_tags"},
    annotations={
        "title": "Create Tag",
        "readOnlyHint": False,
        "destructiveHint": False,
    },
)
@check_write_access
async def create_tag(
    ctx: Context,
    repo_slug: Annotated[str, Field(description="Repository slug.")],
    tag_name: Annotated[str, Field(description="Tag name.")],
    target_hash: Annotated[str, Field(description="Commit hash to tag.")],
    message: Annotated[str, Field(description="Tag message.", default="")] = "",
    workspace: Annotated[
        str | None,
        Field(description="Workspace slug (Cloud).", default=None),
    ] = None,
    project_key: Annotated[
        str | None,
        Field(description="Project key (Server/DC).", default=None),
    ] = None,
) -> str:
    """Create a new tag."""
    client = await get_bitbucket_fetcher(ctx)
    result = client.create_tag(
        repo_slug=repo_slug,
        tag_name=tag_name,
        target_hash=target_hash,
        message=message,
        workspace=workspace,
        project_key=project_key,
    )
    return json.dumps(result, indent=2, ensure_ascii=False)


@bitbucket_mcp.tool(
    tags={"bitbucket", "write", "toolset:bitbucket_tags"},
    annotations={
        "title": "Delete Tag",
        "readOnlyHint": False,
        "destructiveHint": True,
    },
)
@check_write_access
async def delete_tag(
    ctx: Context,
    repo_slug: Annotated[str, Field(description="Repository slug.")],
    tag_name: Annotated[str, Field(description="Tag name to delete.")],
    workspace: Annotated[
        str | None,
        Field(description="Workspace slug (Cloud).", default=None),
    ] = None,
    project_key: Annotated[
        str | None,
        Field(description="Project key (Server/DC).", default=None),
    ] = None,
) -> str:
    """Delete a tag from a repository."""
    client = await get_bitbucket_fetcher(ctx)
    client.delete_tag(
        repo_slug=repo_slug,
        tag_name=tag_name,
        workspace=workspace,
        project_key=project_key,
    )
    return json.dumps({"status": "Tag deleted successfully"}, indent=2)


# ==================================================================
# Pipeline tools (toolset: bitbucket_pipelines) — Cloud only
# ==================================================================


@bitbucket_mcp.tool(
    tags={"bitbucket", "read", "toolset:bitbucket_pipelines"},
    annotations={"title": "List Pipelines", "readOnlyHint": True},
)
async def list_pipelines(
    ctx: Context,
    repo_slug: Annotated[str, Field(description="Repository slug.")],
    workspace: Annotated[
        str | None,
        Field(description="Workspace slug.", default=None),
    ] = None,
    max_results: Annotated[
        int,
        Field(description="Maximum results.", ge=1, le=100, default=25),
    ] = 25,
) -> str:
    """List pipeline runs for a repository (Cloud only)."""
    client = await get_bitbucket_fetcher(ctx)
    result = client.list_pipelines(
        repo_slug=repo_slug,
        workspace=workspace,
        max_results=max_results,
    )
    return json.dumps(result, indent=2, ensure_ascii=False)


@bitbucket_mcp.tool(
    tags={"bitbucket", "read", "toolset:bitbucket_pipelines"},
    annotations={"title": "Get Pipeline", "readOnlyHint": True},
)
async def get_pipeline(
    ctx: Context,
    repo_slug: Annotated[str, Field(description="Repository slug.")],
    pipeline_uuid: Annotated[str, Field(description="Pipeline UUID.")],
    workspace: Annotated[
        str | None,
        Field(description="Workspace slug.", default=None),
    ] = None,
) -> str:
    """Get details of a specific pipeline run (Cloud only)."""
    client = await get_bitbucket_fetcher(ctx)
    result = client.get_pipeline(
        repo_slug=repo_slug,
        pipeline_uuid=pipeline_uuid,
        workspace=workspace,
    )
    return json.dumps(result, indent=2, ensure_ascii=False)


@bitbucket_mcp.tool(
    tags={"bitbucket", "write", "toolset:bitbucket_pipelines"},
    annotations={
        "title": "Trigger Pipeline",
        "readOnlyHint": False,
        "destructiveHint": False,
    },
)
@check_write_access
async def trigger_pipeline(
    ctx: Context,
    repo_slug: Annotated[str, Field(description="Repository slug.")],
    branch: Annotated[str, Field(description="Branch to run pipeline on.")],
    workspace: Annotated[
        str | None,
        Field(description="Workspace slug.", default=None),
    ] = None,
    variables: Annotated[
        str | None,
        Field(
            description="Pipeline variables as 'key=value' pairs separated by commas (e.g. 'ENV=prod,DEBUG=false').",
            default=None,
        ),
    ] = None,
) -> str:
    """Trigger a new pipeline run on a branch (Cloud only)."""
    client = await get_bitbucket_fetcher(ctx)
    var_dict = None
    if variables:
        var_dict = {}
        for pair in variables.split(","):
            pair = pair.strip()
            if "=" in pair:
                k, v = pair.split("=", 1)
                var_dict[k.strip()] = v.strip()
    result = client.trigger_pipeline(
        repo_slug=repo_slug,
        branch=branch,
        workspace=workspace,
        variables=var_dict,
    )
    return json.dumps(result, indent=2, ensure_ascii=False)


@bitbucket_mcp.tool(
    tags={"bitbucket", "write", "toolset:bitbucket_pipelines"},
    annotations={
        "title": "Stop Pipeline",
        "readOnlyHint": False,
        "destructiveHint": True,
    },
)
@check_write_access
async def stop_pipeline(
    ctx: Context,
    repo_slug: Annotated[str, Field(description="Repository slug.")],
    pipeline_uuid: Annotated[str, Field(description="Pipeline UUID to stop.")],
    workspace: Annotated[
        str | None,
        Field(description="Workspace slug.", default=None),
    ] = None,
) -> str:
    """Stop a running pipeline (Cloud only)."""
    client = await get_bitbucket_fetcher(ctx)
    client.stop_pipeline(
        repo_slug=repo_slug,
        pipeline_uuid=pipeline_uuid,
        workspace=workspace,
    )
    return json.dumps({"status": "Pipeline stopped successfully"}, indent=2)


@bitbucket_mcp.tool(
    tags={"bitbucket", "read", "toolset:bitbucket_pipelines"},
    annotations={"title": "Get Pipeline Step Log", "readOnlyHint": True},
)
async def get_pipeline_step_log(
    ctx: Context,
    repo_slug: Annotated[str, Field(description="Repository slug.")],
    pipeline_uuid: Annotated[str, Field(description="Pipeline UUID.")],
    step_uuid: Annotated[str, Field(description="Step UUID.")],
    workspace: Annotated[
        str | None,
        Field(description="Workspace slug.", default=None),
    ] = None,
) -> str:
    """Get log output for a pipeline step (Cloud only)."""
    client = await get_bitbucket_fetcher(ctx)
    return client.get_pipeline_step_log(
        repo_slug=repo_slug,
        pipeline_uuid=pipeline_uuid,
        step_uuid=step_uuid,
        workspace=workspace,
    )


@bitbucket_mcp.tool(
    tags={"bitbucket", "read", "toolset:bitbucket_pipelines"},
    annotations={"title": "List Pipeline Variables", "readOnlyHint": True},
)
async def list_pipeline_variables(
    ctx: Context,
    repo_slug: Annotated[str, Field(description="Repository slug.")],
    workspace: Annotated[
        str | None,
        Field(description="Workspace slug.", default=None),
    ] = None,
    max_results: Annotated[
        int,
        Field(description="Maximum results.", ge=1, le=100, default=25),
    ] = 25,
) -> str:
    """List pipeline variables for a repository (Cloud only)."""
    client = await get_bitbucket_fetcher(ctx)
    result = client.list_pipeline_variables(
        repo_slug=repo_slug,
        workspace=workspace,
        max_results=max_results,
    )
    return json.dumps(result, indent=2, ensure_ascii=False)


@bitbucket_mcp.tool(
    tags={"bitbucket", "write", "toolset:bitbucket_pipelines"},
    annotations={
        "title": "Create Pipeline Variable",
        "readOnlyHint": False,
        "destructiveHint": False,
    },
)
@check_write_access
async def create_pipeline_variable(
    ctx: Context,
    repo_slug: Annotated[str, Field(description="Repository slug.")],
    key: Annotated[str, Field(description="Variable key name.")],
    value: Annotated[str, Field(description="Variable value.")],
    secured: Annotated[
        bool,
        Field(description="Whether the variable is encrypted/hidden.", default=False),
    ] = False,
    workspace: Annotated[
        str | None,
        Field(description="Workspace slug.", default=None),
    ] = None,
) -> str:
    """Create a pipeline variable for a repository (Cloud only)."""
    client = await get_bitbucket_fetcher(ctx)
    result = client.create_pipeline_variable(
        repo_slug=repo_slug,
        key=key,
        value=value,
        secured=secured,
        workspace=workspace,
    )
    return json.dumps(result, indent=2, ensure_ascii=False)


@bitbucket_mcp.tool(
    tags={"bitbucket", "read", "toolset:bitbucket_pipelines"},
    annotations={"title": "Get Pipeline Config", "readOnlyHint": True},
)
async def get_pipeline_config(
    ctx: Context,
    repo_slug: Annotated[str, Field(description="Repository slug.")],
    workspace: Annotated[
        str | None,
        Field(description="Workspace slug.", default=None),
    ] = None,
) -> str:
    """Get pipeline configuration for a repository (Cloud only)."""
    client = await get_bitbucket_fetcher(ctx)
    result = client.get_pipeline_config(
        repo_slug=repo_slug,
        workspace=workspace,
    )
    return json.dumps(result, indent=2, ensure_ascii=False)


# ==================================================================
# Deployment tools (toolset: bitbucket_deployments) — Cloud only
# ==================================================================


@bitbucket_mcp.tool(
    tags={"bitbucket", "read", "toolset:bitbucket_deployments"},
    annotations={"title": "List Environments", "readOnlyHint": True},
)
async def list_environments(
    ctx: Context,
    repo_slug: Annotated[str, Field(description="Repository slug.")],
    workspace: Annotated[
        str | None,
        Field(description="Workspace slug.", default=None),
    ] = None,
) -> str:
    """List deployment environments for a repository (Cloud only)."""
    client = await get_bitbucket_fetcher(ctx)
    result = client.list_environments(
        repo_slug=repo_slug,
        workspace=workspace,
    )
    return json.dumps(result, indent=2, ensure_ascii=False)


@bitbucket_mcp.tool(
    tags={"bitbucket", "read", "toolset:bitbucket_deployments"},
    annotations={"title": "Get Deployment", "readOnlyHint": True},
)
async def get_deployment(
    ctx: Context,
    repo_slug: Annotated[str, Field(description="Repository slug.")],
    environment_uuid: Annotated[str, Field(description="Environment UUID.")],
    workspace: Annotated[
        str | None,
        Field(description="Workspace slug.", default=None),
    ] = None,
) -> str:
    """Get deployment details for an environment (Cloud only)."""
    client = await get_bitbucket_fetcher(ctx)
    result = client.get_deployment(
        repo_slug=repo_slug,
        environment_uuid=environment_uuid,
        workspace=workspace,
    )
    return json.dumps(result, indent=2, ensure_ascii=False)


@bitbucket_mcp.tool(
    tags={"bitbucket", "read", "toolset:bitbucket_deployments"},
    annotations={"title": "List Deployment Releases", "readOnlyHint": True},
)
async def list_deployment_releases(
    ctx: Context,
    repo_slug: Annotated[str, Field(description="Repository slug.")],
    environment_uuid: Annotated[str, Field(description="Environment UUID.")],
    workspace: Annotated[
        str | None,
        Field(description="Workspace slug.", default=None),
    ] = None,
    max_results: Annotated[
        int,
        Field(description="Maximum results.", ge=1, le=100, default=25),
    ] = 25,
) -> str:
    """List deployment releases for an environment (Cloud only)."""
    client = await get_bitbucket_fetcher(ctx)
    result = client.list_deployment_releases(
        repo_slug=repo_slug,
        environment_uuid=environment_uuid,
        workspace=workspace,
        max_results=max_results,
    )
    return json.dumps(result, indent=2, ensure_ascii=False)


# ==================================================================
# Webhook tools (toolset: bitbucket_webhooks)
# ==================================================================


@bitbucket_mcp.tool(
    tags={"bitbucket", "read", "toolset:bitbucket_webhooks"},
    annotations={"title": "List Webhooks", "readOnlyHint": True},
)
async def list_webhooks(
    ctx: Context,
    repo_slug: Annotated[str, Field(description="Repository slug.")],
    workspace: Annotated[
        str | None,
        Field(description="Workspace slug (Cloud).", default=None),
    ] = None,
    project_key: Annotated[
        str | None,
        Field(description="Project key (Server/DC).", default=None),
    ] = None,
) -> str:
    """List webhooks configured for a repository."""
    client = await get_bitbucket_fetcher(ctx)
    result = client.list_webhooks(
        repo_slug=repo_slug,
        workspace=workspace,
        project_key=project_key,
    )
    return json.dumps(result, indent=2, ensure_ascii=False)


@bitbucket_mcp.tool(
    tags={"bitbucket", "write", "toolset:bitbucket_webhooks"},
    annotations={
        "title": "Create Webhook",
        "readOnlyHint": False,
        "destructiveHint": False,
    },
)
@check_write_access
async def create_webhook(
    ctx: Context,
    repo_slug: Annotated[str, Field(description="Repository slug.")],
    url: Annotated[str, Field(description="Webhook callback URL.")],
    events: Annotated[
        str,
        Field(
            description="Comma-separated list of event types (e.g. 'repo:push,pullrequest:created')."
        ),
    ],
    description: Annotated[
        str, Field(description="Webhook description.", default="")
    ] = "",
    active: Annotated[
        bool, Field(description="Whether the webhook is active.", default=True)
    ] = True,
    workspace: Annotated[
        str | None,
        Field(description="Workspace slug (Cloud).", default=None),
    ] = None,
    project_key: Annotated[
        str | None,
        Field(description="Project key (Server/DC).", default=None),
    ] = None,
) -> str:
    """Create a webhook for a repository."""
    client = await get_bitbucket_fetcher(ctx)
    event_list = [e.strip() for e in events.split(",")]
    result = client.create_webhook(
        repo_slug=repo_slug,
        url=url,
        events=event_list,
        description=description,
        active=active,
        workspace=workspace,
        project_key=project_key,
    )
    return json.dumps(result, indent=2, ensure_ascii=False)


@bitbucket_mcp.tool(
    tags={"bitbucket", "write", "toolset:bitbucket_webhooks"},
    annotations={
        "title": "Update Webhook",
        "readOnlyHint": False,
        "destructiveHint": False,
    },
)
@check_write_access
async def update_webhook(
    ctx: Context,
    repo_slug: Annotated[str, Field(description="Repository slug.")],
    webhook_id: Annotated[
        str, Field(description="Webhook UUID (Cloud) or ID (Server).")
    ],
    workspace: Annotated[
        str | None,
        Field(description="Workspace slug (Cloud).", default=None),
    ] = None,
    project_key: Annotated[
        str | None,
        Field(description="Project key (Server/DC).", default=None),
    ] = None,
    url: Annotated[
        str | None,
        Field(description="New webhook URL.", default=None),
    ] = None,
    events: Annotated[
        str | None,
        Field(description="Comma-separated list of new event types.", default=None),
    ] = None,
    description: Annotated[
        str | None,
        Field(description="New description.", default=None),
    ] = None,
    active: Annotated[
        bool | None,
        Field(description="Enable or disable the webhook.", default=None),
    ] = None,
) -> str:
    """Update an existing webhook."""
    client = await get_bitbucket_fetcher(ctx)
    event_list = [e.strip() for e in events.split(",")] if events else None
    result = client.update_webhook(
        repo_slug=repo_slug,
        webhook_id=webhook_id,
        workspace=workspace,
        project_key=project_key,
        url=url,
        events=event_list,
        description=description,
        active=active,
    )
    return json.dumps(result, indent=2, ensure_ascii=False)


@bitbucket_mcp.tool(
    tags={"bitbucket", "write", "toolset:bitbucket_webhooks"},
    annotations={
        "title": "Delete Webhook",
        "readOnlyHint": False,
        "destructiveHint": True,
    },
)
@check_write_access
async def delete_webhook(
    ctx: Context,
    repo_slug: Annotated[str, Field(description="Repository slug.")],
    webhook_id: Annotated[
        str, Field(description="Webhook UUID (Cloud) or ID (Server).")
    ],
    workspace: Annotated[
        str | None,
        Field(description="Workspace slug (Cloud).", default=None),
    ] = None,
    project_key: Annotated[
        str | None,
        Field(description="Project key (Server/DC).", default=None),
    ] = None,
) -> str:
    """Delete a webhook from a repository."""
    client = await get_bitbucket_fetcher(ctx)
    client.delete_webhook(
        repo_slug=repo_slug,
        webhook_id=webhook_id,
        workspace=workspace,
        project_key=project_key,
    )
    return json.dumps({"status": "Webhook deleted successfully"}, indent=2)


# ==================================================================
# Workspace/Project tools (toolset: bitbucket_workspace)
# ==================================================================


@bitbucket_mcp.tool(
    tags={"bitbucket", "read", "toolset:bitbucket_workspace"},
    annotations={"title": "List Workspaces", "readOnlyHint": True},
)
async def list_workspaces(
    ctx: Context,
    max_results: Annotated[
        int,
        Field(description="Maximum results.", ge=1, le=100, default=25),
    ] = 25,
) -> str:
    """List workspaces (Cloud) or projects (Server/DC)."""
    client = await get_bitbucket_fetcher(ctx)
    result = client.list_workspaces(max_results=max_results)
    return json.dumps(result, indent=2, ensure_ascii=False)


@bitbucket_mcp.tool(
    tags={"bitbucket", "read", "toolset:bitbucket_workspace"},
    annotations={"title": "Get Workspace", "readOnlyHint": True},
)
async def get_workspace(
    ctx: Context,
    workspace: Annotated[
        str | None,
        Field(
            description="Workspace slug (Cloud). Uses default if omitted.", default=None
        ),
    ] = None,
    project_key: Annotated[
        str | None,
        Field(
            description="Project key (Server/DC). Uses default if omitted.",
            default=None,
        ),
    ] = None,
) -> str:
    """Get workspace (Cloud) or project (Server/DC) details."""
    client = await get_bitbucket_fetcher(ctx)
    result = client.get_workspace(
        workspace=workspace,
        project_key=project_key,
    )
    return json.dumps(result, indent=2, ensure_ascii=False)


@bitbucket_mcp.tool(
    tags={"bitbucket", "read", "toolset:bitbucket_workspace"},
    annotations={"title": "List Workspace Members", "readOnlyHint": True},
)
async def list_workspace_members(
    ctx: Context,
    workspace: Annotated[
        str | None,
        Field(description="Workspace slug (Cloud).", default=None),
    ] = None,
    project_key: Annotated[
        str | None,
        Field(description="Project key (Server/DC).", default=None),
    ] = None,
    max_results: Annotated[
        int,
        Field(description="Maximum results.", ge=1, le=100, default=25),
    ] = 25,
) -> str:
    """List members of a workspace (Cloud) or project permissions (Server/DC)."""
    client = await get_bitbucket_fetcher(ctx)
    result = client.list_workspace_members(
        workspace=workspace,
        project_key=project_key,
        max_results=max_results,
    )
    return json.dumps(result, indent=2, ensure_ascii=False)


@bitbucket_mcp.tool(
    tags={"bitbucket", "read", "toolset:bitbucket_workspace"},
    annotations={"title": "Get Default Reviewers", "readOnlyHint": True},
)
async def get_default_reviewers(
    ctx: Context,
    repo_slug: Annotated[str, Field(description="Repository slug.")],
    workspace: Annotated[
        str | None,
        Field(description="Workspace slug (Cloud).", default=None),
    ] = None,
    project_key: Annotated[
        str | None,
        Field(description="Project key (Server/DC).", default=None),
    ] = None,
) -> str:
    """Get default reviewers configured for a repository."""
    client = await get_bitbucket_fetcher(ctx)
    result = client.get_default_reviewers(
        repo_slug=repo_slug,
        workspace=workspace,
        project_key=project_key,
    )
    return json.dumps(result, indent=2, ensure_ascii=False)


@bitbucket_mcp.tool(
    tags={"bitbucket", "write", "toolset:bitbucket_workspace"},
    annotations={
        "title": "Add Default Reviewer",
        "readOnlyHint": False,
        "destructiveHint": False,
    },
)
@check_write_access
async def add_default_reviewer(
    ctx: Context,
    repo_slug: Annotated[str, Field(description="Repository slug.")],
    username: Annotated[str, Field(description="Username or UUID of the reviewer.")],
    workspace: Annotated[
        str | None,
        Field(description="Workspace slug (Cloud).", default=None),
    ] = None,
    project_key: Annotated[
        str | None,
        Field(description="Project key (Server/DC).", default=None),
    ] = None,
) -> str:
    """Add a default reviewer to a repository."""
    client = await get_bitbucket_fetcher(ctx)
    result = client.add_default_reviewer(
        repo_slug=repo_slug,
        username=username,
        workspace=workspace,
        project_key=project_key,
    )
    return json.dumps(result, indent=2, ensure_ascii=False)
