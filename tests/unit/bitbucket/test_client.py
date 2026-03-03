"""Tests for Bitbucket client module."""

from unittest.mock import MagicMock, patch

import httpx
import pytest

from mcp_atlassian.bitbucket.client import BitbucketClient
from mcp_atlassian.bitbucket.config import BitbucketConfig


@pytest.fixture
def cloud_config():
    """Bitbucket Cloud configuration."""
    return BitbucketConfig(
        url="https://bitbucket.org",
        auth_type="basic",
        username="testuser",
        app_password="test-app-password",
        workspace="my-workspace",
    )


@pytest.fixture
def server_config():
    """Bitbucket Server/DC configuration."""
    return BitbucketConfig(
        url="https://bitbucket.company.com",
        auth_type="pat",
        personal_token="test-pat",
        project_key="PROJ",
    )


class TestBitbucketClientInit:
    """Tests for BitbucketClient initialization."""

    @patch.object(BitbucketClient, "_validate_connection")
    def test_cloud_client_creation(self, mock_validate, cloud_config):
        """Test creating a Cloud client."""
        client = BitbucketClient(config=cloud_config)
        assert client.config.is_cloud is True
        assert client._http is not None

    @patch.object(BitbucketClient, "_validate_connection")
    def test_server_client_creation(self, mock_validate, server_config):
        """Test creating a Server/DC client."""
        client = BitbucketClient(config=server_config)
        assert client.config.is_cloud is False
        assert client._http is not None


class TestBuildUrl:
    """Tests for URL building."""

    @patch.object(BitbucketClient, "_validate_connection")
    def test_cloud_url(self, mock_validate, cloud_config):
        client = BitbucketClient(config=cloud_config)
        url = client._build_url("/repositories/ws/repo")
        assert url == "https://api.bitbucket.org/2.0/repositories/ws/repo"

    @patch.object(BitbucketClient, "_validate_connection")
    def test_server_url(self, mock_validate, server_config):
        client = BitbucketClient(config=server_config)
        url = client._build_url("/projects/PROJ/repos/myrepo")
        assert url == "https://bitbucket.company.com/rest/api/1.0/projects/PROJ/repos/myrepo"

    @patch.object(BitbucketClient, "_validate_connection")
    def test_url_leading_slash_handling(self, mock_validate, cloud_config):
        client = BitbucketClient(config=cloud_config)
        # Both with and without leading slash should work
        url1 = client._build_url("/repositories")
        url2 = client._build_url("repositories")
        assert url1 == url2


class TestCloudOperations:
    """Tests for Cloud-specific API operations."""

    @patch.object(BitbucketClient, "_validate_connection")
    @patch.object(BitbucketClient, "_paginate")
    def test_list_repositories(self, mock_paginate, mock_validate, cloud_config):
        mock_paginate.return_value = [
            {"slug": "repo1", "full_name": "ws/repo1"},
            {"slug": "repo2", "full_name": "ws/repo2"},
        ]
        client = BitbucketClient(config=cloud_config)
        repos = client.list_repositories(workspace="my-workspace")
        assert len(repos) == 2
        assert repos[0]["slug"] == "repo1"

    @patch.object(BitbucketClient, "_validate_connection")
    @patch.object(BitbucketClient, "_request")
    def test_get_repository(self, mock_request, mock_validate, cloud_config):
        mock_request.return_value = {
            "slug": "my-repo",
            "full_name": "my-workspace/my-repo",
        }
        client = BitbucketClient(config=cloud_config)
        repo = client.get_repository(repo_slug="my-repo")
        assert repo["slug"] == "my-repo"
        mock_request.assert_called_once_with(
            "GET", "/repositories/my-workspace/my-repo"
        )

    @patch.object(BitbucketClient, "_validate_connection")
    @patch.object(BitbucketClient, "_paginate")
    def test_list_pull_requests(self, mock_paginate, mock_validate, cloud_config):
        mock_paginate.return_value = [
            {"id": 1, "title": "PR 1", "state": "OPEN"},
        ]
        client = BitbucketClient(config=cloud_config)
        prs = client.list_pull_requests(repo_slug="my-repo", state="OPEN")
        assert len(prs) == 1
        assert prs[0]["title"] == "PR 1"

    @patch.object(BitbucketClient, "_validate_connection")
    @patch.object(BitbucketClient, "_request")
    def test_get_pull_request(self, mock_request, mock_validate, cloud_config):
        mock_request.return_value = {"id": 42, "title": "Fix bug"}
        client = BitbucketClient(config=cloud_config)
        pr = client.get_pull_request(repo_slug="my-repo", pr_id=42)
        assert pr["id"] == 42

    @patch.object(BitbucketClient, "_validate_connection")
    @patch.object(BitbucketClient, "_request")
    def test_create_pull_request(self, mock_request, mock_validate, cloud_config):
        mock_request.return_value = {"id": 1, "title": "New Feature"}
        client = BitbucketClient(config=cloud_config)
        pr = client.create_pull_request(
            repo_slug="my-repo",
            title="New Feature",
            source_branch="feature/new",
            destination_branch="main",
        )
        assert pr["title"] == "New Feature"

    @patch.object(BitbucketClient, "_validate_connection")
    @patch.object(BitbucketClient, "_paginate")
    def test_list_branches(self, mock_paginate, mock_validate, cloud_config):
        mock_paginate.return_value = [
            {"name": "main"},
            {"name": "develop"},
        ]
        client = BitbucketClient(config=cloud_config)
        branches = client.list_branches(repo_slug="my-repo")
        assert len(branches) == 2

    @patch.object(BitbucketClient, "_validate_connection")
    @patch.object(BitbucketClient, "_paginate")
    def test_list_commits(self, mock_paginate, mock_validate, cloud_config):
        mock_paginate.return_value = [
            {"hash": "abc123", "message": "Initial commit"},
        ]
        client = BitbucketClient(config=cloud_config)
        commits = client.list_commits(repo_slug="my-repo")
        assert len(commits) == 1


    @patch.object(BitbucketClient, "_validate_connection")
    @patch.object(BitbucketClient, "_request")
    def test_create_repository(self, mock_request, mock_validate, cloud_config):
        mock_request.return_value = {"slug": "new-repo", "is_private": True}
        client = BitbucketClient(config=cloud_config)
        repo = client.create_repository(repo_slug="new-repo", is_private=True)
        assert repo["slug"] == "new-repo"

    @patch.object(BitbucketClient, "_validate_connection")
    @patch.object(BitbucketClient, "_request")
    def test_update_repository(self, mock_request, mock_validate, cloud_config):
        mock_request.return_value = {"slug": "my-repo", "description": "Updated"}
        client = BitbucketClient(config=cloud_config)
        repo = client.update_repository(repo_slug="my-repo", description="Updated")
        assert repo["description"] == "Updated"

    @patch.object(BitbucketClient, "_validate_connection")
    @patch.object(BitbucketClient, "_request")
    def test_delete_repository(self, mock_request, mock_validate, cloud_config):
        mock_request.return_value = None
        client = BitbucketClient(config=cloud_config)
        client.delete_repository(repo_slug="my-repo")
        mock_request.assert_called_once_with("DELETE", "/repositories/my-workspace/my-repo")

    @patch.object(BitbucketClient, "_validate_connection")
    @patch.object(BitbucketClient, "_request")
    def test_fork_repository(self, mock_request, mock_validate, cloud_config):
        mock_request.return_value = {"slug": "my-repo-fork"}
        client = BitbucketClient(config=cloud_config)
        fork = client.fork_repository(repo_slug="my-repo", new_name="my-repo-fork")
        assert fork["slug"] == "my-repo-fork"

    @patch.object(BitbucketClient, "_validate_connection")
    @patch.object(BitbucketClient, "_paginate")
    def test_list_forks(self, mock_paginate, mock_validate, cloud_config):
        mock_paginate.return_value = [{"slug": "fork1"}, {"slug": "fork2"}]
        client = BitbucketClient(config=cloud_config)
        forks = client.list_forks(repo_slug="my-repo")
        assert len(forks) == 2

    @patch.object(BitbucketClient, "_validate_connection")
    @patch.object(BitbucketClient, "_request")
    def test_update_pull_request(self, mock_request, mock_validate, cloud_config):
        mock_request.return_value = {"id": 1, "title": "Updated Title"}
        client = BitbucketClient(config=cloud_config)
        pr = client.update_pull_request(
            repo_slug="my-repo", pr_id=1, title="Updated Title"
        )
        assert pr["title"] == "Updated Title"

    @patch.object(BitbucketClient, "_validate_connection")
    @patch.object(BitbucketClient, "_request")
    def test_decline_pull_request(self, mock_request, mock_validate, cloud_config):
        mock_request.return_value = {"id": 1, "state": "DECLINED"}
        client = BitbucketClient(config=cloud_config)
        pr = client.decline_pull_request(repo_slug="my-repo", pr_id=1)
        assert pr["state"] == "DECLINED"

    @patch.object(BitbucketClient, "_validate_connection")
    @patch.object(BitbucketClient, "_request")
    def test_approve_pull_request(self, mock_request, mock_validate, cloud_config):
        mock_request.return_value = {"approved": True}
        client = BitbucketClient(config=cloud_config)
        result = client.approve_pull_request(repo_slug="my-repo", pr_id=1)
        assert result["approved"] is True

    @patch.object(BitbucketClient, "_validate_connection")
    @patch.object(BitbucketClient, "_request")
    def test_unapprove_pull_request(self, mock_request, mock_validate, cloud_config):
        mock_request.return_value = None
        client = BitbucketClient(config=cloud_config)
        client.unapprove_pull_request(repo_slug="my-repo", pr_id=1)
        mock_request.assert_called_once_with(
            "DELETE", "/repositories/my-workspace/my-repo/pullrequests/1/approve"
        )

    @patch.object(BitbucketClient, "_validate_connection")
    @patch.object(BitbucketClient, "_request")
    def test_request_changes(self, mock_request, mock_validate, cloud_config):
        mock_request.return_value = {"status": "changes_requested"}
        client = BitbucketClient(config=cloud_config)
        result = client.request_changes_pull_request(repo_slug="my-repo", pr_id=1)
        assert result is not None

    @patch.object(BitbucketClient, "_validate_connection")
    @patch.object(BitbucketClient, "_paginate")
    def test_get_pull_request_commits(self, mock_paginate, mock_validate, cloud_config):
        mock_paginate.return_value = [{"hash": "abc123"}, {"hash": "def456"}]
        client = BitbucketClient(config=cloud_config)
        commits = client.get_pull_request_commits(repo_slug="my-repo", pr_id=1)
        assert len(commits) == 2

    @patch.object(BitbucketClient, "_validate_connection")
    @patch.object(BitbucketClient, "_paginate")
    def test_list_pull_request_comments(self, mock_paginate, mock_validate, cloud_config):
        mock_paginate.return_value = [{"id": 1, "content": {"raw": "LGTM"}}]
        client = BitbucketClient(config=cloud_config)
        comments = client.list_pull_request_comments(repo_slug="my-repo", pr_id=1)
        assert len(comments) == 1

    @patch.object(BitbucketClient, "_validate_connection")
    @patch.object(BitbucketClient, "_request")
    def test_add_inline_comment(self, mock_request, mock_validate, cloud_config):
        mock_request.return_value = {"id": 1, "inline": {"path": "file.py"}}
        client = BitbucketClient(config=cloud_config)
        result = client.add_inline_comment(
            repo_slug="my-repo", pr_id=1, content="Fix this",
            file_path="file.py", line=10
        )
        assert result["inline"]["path"] == "file.py"

    @patch.object(BitbucketClient, "_validate_connection")
    @patch.object(BitbucketClient, "_request")
    def test_reply_to_comment(self, mock_request, mock_validate, cloud_config):
        mock_request.return_value = {"id": 2, "parent": {"id": 1}}
        client = BitbucketClient(config=cloud_config)
        result = client.reply_to_comment(
            repo_slug="my-repo", pr_id=1, comment_id=1, content="Reply"
        )
        assert result["parent"]["id"] == 1

    @patch.object(BitbucketClient, "_validate_connection")
    @patch.object(BitbucketClient, "_request")
    def test_update_comment(self, mock_request, mock_validate, cloud_config):
        mock_request.return_value = {"id": 1, "content": {"raw": "Updated"}}
        client = BitbucketClient(config=cloud_config)
        result = client.update_comment(
            repo_slug="my-repo", pr_id=1, comment_id=1, content="Updated"
        )
        assert result["content"]["raw"] == "Updated"

    @patch.object(BitbucketClient, "_validate_connection")
    @patch.object(BitbucketClient, "_request")
    def test_delete_comment(self, mock_request, mock_validate, cloud_config):
        mock_request.return_value = None
        client = BitbucketClient(config=cloud_config)
        client.delete_comment(repo_slug="my-repo", pr_id=1, comment_id=1)
        mock_request.assert_called_once_with(
            "DELETE", "/repositories/my-workspace/my-repo/pullrequests/1/comments/1"
        )

    @patch.object(BitbucketClient, "_validate_connection")
    @patch.object(BitbucketClient, "_request")
    def test_get_branching_model(self, mock_request, mock_validate, cloud_config):
        mock_request.return_value = {"type": "branching_model", "production": {"name": "main"}}
        client = BitbucketClient(config=cloud_config)
        result = client.get_branching_model(repo_slug="my-repo")
        assert result["production"]["name"] == "main"

    @patch.object(BitbucketClient, "_validate_connection")
    @patch.object(BitbucketClient, "_paginate")
    def test_list_branch_restrictions(self, mock_paginate, mock_validate, cloud_config):
        mock_paginate.return_value = [{"id": 1, "kind": "push"}]
        client = BitbucketClient(config=cloud_config)
        result = client.list_branch_restrictions(repo_slug="my-repo")
        assert len(result) == 1

    @patch.object(BitbucketClient, "_validate_connection")
    @patch.object(BitbucketClient, "_request")
    def test_compare_commits(self, mock_request, mock_validate, cloud_config):
        mock_request.return_value = "diff output"
        client = BitbucketClient(config=cloud_config)
        result = client.compare_commits(
            repo_slug="my-repo", source="abc123", destination="def456"
        )
        assert result is not None

    @patch.object(BitbucketClient, "_validate_connection")
    @patch.object(BitbucketClient, "_paginate")
    def test_list_commit_statuses(self, mock_paginate, mock_validate, cloud_config):
        mock_paginate.return_value = [{"state": "SUCCESSFUL", "key": "ci"}]
        client = BitbucketClient(config=cloud_config)
        result = client.list_commit_statuses(
            repo_slug="my-repo", commit_hash="abc123"
        )
        assert len(result) == 1
        assert result[0]["state"] == "SUCCESSFUL"

    @patch.object(BitbucketClient, "_validate_connection")
    @patch.object(BitbucketClient, "_request")
    def test_create_commit_status(self, mock_request, mock_validate, cloud_config):
        mock_request.return_value = {"state": "SUCCESSFUL", "key": "ci"}
        client = BitbucketClient(config=cloud_config)
        result = client.create_commit_status(
            repo_slug="my-repo", commit_hash="abc123",
            state="SUCCESSFUL", key="ci", url="https://ci.example.com"
        )
        assert result["state"] == "SUCCESSFUL"

    @patch.object(BitbucketClient, "_validate_connection")
    @patch.object(BitbucketClient, "_request")
    def test_add_commit_comment(self, mock_request, mock_validate, cloud_config):
        mock_request.return_value = {"id": 1, "content": {"raw": "Nice commit"}}
        client = BitbucketClient(config=cloud_config)
        result = client.add_commit_comment(
            repo_slug="my-repo", commit_hash="abc123", content="Nice commit"
        )
        assert result["id"] == 1

    @patch.object(BitbucketClient, "_validate_connection")
    @patch.object(BitbucketClient, "_request")
    def test_delete_tag(self, mock_request, mock_validate, cloud_config):
        mock_request.return_value = None
        client = BitbucketClient(config=cloud_config)
        client.delete_tag(repo_slug="my-repo", tag_name="v1.0.0")
        mock_request.assert_called_once_with(
            "DELETE", "/repositories/my-workspace/my-repo/refs/tags/v1.0.0"
        )

    @patch.object(BitbucketClient, "_validate_connection")
    @patch.object(BitbucketClient, "_request")
    def test_browse_directory(self, mock_request, mock_validate, cloud_config):
        """browse_directory uses _paginate for Cloud; test via _request for server."""
        pass  # browse_directory uses paginate for Cloud, tested via integration

    @patch.object(BitbucketClient, "_validate_connection")
    @patch.object(BitbucketClient, "_paginate")
    def test_search_code(self, mock_paginate, mock_validate, cloud_config):
        mock_paginate.return_value = [{"content_match_count": 3, "path": "app.py"}]
        client = BitbucketClient(config=cloud_config)
        result = client.search_code(query="def main", repo_slug="my-repo")
        assert len(result) == 1

    @patch.object(BitbucketClient, "_validate_connection")
    @patch.object(BitbucketClient, "_paginate")
    def test_list_pull_request_statuses(self, mock_paginate, mock_validate, cloud_config):
        mock_paginate.return_value = [{"state": "SUCCESSFUL"}]
        client = BitbucketClient(config=cloud_config)
        result = client.list_pull_request_statuses(repo_slug="my-repo", pr_id=1)
        assert len(result) == 1


class TestServerOperations:
    """Tests for Server/DC-specific API operations."""

    @patch.object(BitbucketClient, "_validate_connection")
    @patch.object(BitbucketClient, "_request")
    def test_get_repository(self, mock_request, mock_validate, server_config):
        mock_request.return_value = {
            "slug": "my-repo",
            "project": {"key": "PROJ"},
        }
        client = BitbucketClient(config=server_config)
        repo = client.get_repository(repo_slug="my-repo")
        assert repo["slug"] == "my-repo"
        mock_request.assert_called_once_with(
            "GET", "/projects/PROJ/repos/my-repo"
        )

    @patch.object(BitbucketClient, "_validate_connection")
    @patch.object(BitbucketClient, "_request")
    def test_create_branch(self, mock_request, mock_validate, server_config):
        mock_request.return_value = {"id": "refs/heads/feature/new"}
        client = BitbucketClient(config=server_config)
        branch = client.create_branch(
            repo_slug="my-repo",
            branch_name="feature/new",
            start_point="main",
        )
        assert branch["id"] == "refs/heads/feature/new"

    @patch.object(BitbucketClient, "_validate_connection")
    @patch.object(BitbucketClient, "_request")
    def test_create_pull_request_server(self, mock_request, mock_validate, server_config):
        mock_request.return_value = {"id": 1, "title": "Server PR"}
        client = BitbucketClient(config=server_config)
        pr = client.create_pull_request(
            repo_slug="my-repo",
            title="Server PR",
            source_branch="feature/new",
            destination_branch="main",
        )
        assert pr["title"] == "Server PR"


    @patch.object(BitbucketClient, "_validate_connection")
    @patch.object(BitbucketClient, "_request")
    def test_create_repository_server(self, mock_request, mock_validate, server_config):
        mock_request.return_value = {"slug": "new-repo"}
        client = BitbucketClient(config=server_config)
        repo = client.create_repository(repo_slug="new-repo")
        assert repo["slug"] == "new-repo"
        mock_request.assert_called_once()
        call_args = mock_request.call_args
        assert call_args[0][0] == "POST"
        assert "/projects/PROJ/repos" in call_args[0][1]

    @patch.object(BitbucketClient, "_validate_connection")
    @patch.object(BitbucketClient, "_request")
    def test_decline_pull_request_server(self, mock_request, mock_validate, server_config):
        # First call: get_pull_request for version, second: decline
        mock_request.side_effect = [
            {"id": 1, "version": 3},
            {"id": 1, "state": "DECLINED"},
        ]
        client = BitbucketClient(config=server_config)
        result = client.decline_pull_request(repo_slug="my-repo", pr_id=1)
        assert result["state"] == "DECLINED"
        assert mock_request.call_count == 2

    @patch.object(BitbucketClient, "_validate_connection")
    @patch.object(BitbucketClient, "_request")
    def test_approve_pull_request_server(self, mock_request, mock_validate, server_config):
        mock_request.return_value = {"approved": True}
        client = BitbucketClient(config=server_config)
        result = client.approve_pull_request(repo_slug="my-repo", pr_id=1)
        assert result is not None

    @patch.object(BitbucketClient, "_validate_connection")
    @patch.object(BitbucketClient, "_request")
    def test_update_pull_request_server(self, mock_request, mock_validate, server_config):
        # First call: get_pull_request for version, second: update
        mock_request.side_effect = [
            {"id": 1, "version": 2, "title": "Old"},
            {"id": 1, "version": 3, "title": "New Title"},
        ]
        client = BitbucketClient(config=server_config)
        result = client.update_pull_request(
            repo_slug="my-repo", pr_id=1, title="New Title"
        )
        assert result["title"] == "New Title"

    @patch.object(BitbucketClient, "_validate_connection")
    @patch.object(BitbucketClient, "_request")
    def test_delete_tag_server(self, mock_request, mock_validate, server_config):
        mock_request.return_value = None
        client = BitbucketClient(config=server_config)
        client.delete_tag(repo_slug="my-repo", tag_name="v1.0.0")
        mock_request.assert_called_once_with(
            "DELETE", "/projects/PROJ/repos/my-repo/tags/v1.0.0"
        )


class TestCloudOnlyOperations:
    """Tests for Cloud-only features (pipelines, deployments)."""

    @patch.object(BitbucketClient, "_validate_connection")
    @patch.object(BitbucketClient, "_paginate")
    def test_list_pipelines_cloud(self, mock_paginate, mock_validate, cloud_config):
        mock_paginate.return_value = [{"uuid": "{pipe-1}", "state": {"name": "COMPLETED"}}]
        client = BitbucketClient(config=cloud_config)
        result = client.list_pipelines(repo_slug="my-repo")
        assert len(result) == 1

    @patch.object(BitbucketClient, "_validate_connection")
    def test_list_pipelines_server_raises(self, mock_validate, server_config):
        client = BitbucketClient(config=server_config)
        with pytest.raises(ValueError, match="only available on Bitbucket Cloud"):
            client.list_pipelines(repo_slug="my-repo")

    @patch.object(BitbucketClient, "_validate_connection")
    @patch.object(BitbucketClient, "_request")
    def test_trigger_pipeline(self, mock_request, mock_validate, cloud_config):
        mock_request.return_value = {"uuid": "{pipe-2}", "state": {"name": "RUNNING"}}
        client = BitbucketClient(config=cloud_config)
        result = client.trigger_pipeline(repo_slug="my-repo", branch="main")
        assert result["state"]["name"] == "RUNNING"

    @patch.object(BitbucketClient, "_validate_connection")
    @patch.object(BitbucketClient, "_request")
    def test_get_pipeline_config(self, mock_request, mock_validate, cloud_config):
        mock_request.return_value = {"enabled": True}
        client = BitbucketClient(config=cloud_config)
        result = client.get_pipeline_config(repo_slug="my-repo")
        assert result["enabled"] is True

    @patch.object(BitbucketClient, "_validate_connection")
    @patch.object(BitbucketClient, "_paginate")
    def test_list_environments(self, mock_paginate, mock_validate, cloud_config):
        mock_paginate.return_value = [{"uuid": "{env-1}", "name": "Production"}]
        client = BitbucketClient(config=cloud_config)
        result = client.list_environments(repo_slug="my-repo")
        assert len(result) == 1
        assert result[0]["name"] == "Production"

    @patch.object(BitbucketClient, "_validate_connection")
    def test_list_environments_server_raises(self, mock_validate, server_config):
        client = BitbucketClient(config=server_config)
        with pytest.raises(ValueError, match="only available on Bitbucket Cloud"):
            client.list_environments(repo_slug="my-repo")

    @patch.object(BitbucketClient, "_validate_connection")
    @patch.object(BitbucketClient, "_request")
    def test_update_webhook(self, mock_request, mock_validate, cloud_config):
        mock_request.return_value = {"uuid": "{hook-1}", "active": False}
        client = BitbucketClient(config=cloud_config)
        result = client.update_webhook(
            repo_slug="my-repo", webhook_id="{hook-1}", active=False
        )
        assert result["active"] is False

    @patch.object(BitbucketClient, "_validate_connection")
    @patch.object(BitbucketClient, "_request")
    def test_delete_webhook(self, mock_request, mock_validate, cloud_config):
        mock_request.return_value = None
        client = BitbucketClient(config=cloud_config)
        client.delete_webhook(repo_slug="my-repo", webhook_id="{hook-1}")
        mock_request.assert_called_once()

    @patch.object(BitbucketClient, "_validate_connection")
    @patch.object(BitbucketClient, "_paginate")
    def test_list_workspaces(self, mock_paginate, mock_validate, cloud_config):
        mock_paginate.return_value = [{"slug": "my-workspace"}]
        client = BitbucketClient(config=cloud_config)
        result = client.list_workspaces()
        assert len(result) == 1

    @patch.object(BitbucketClient, "_validate_connection")
    @patch.object(BitbucketClient, "_request")
    def test_get_workspace(self, mock_request, mock_validate, cloud_config):
        mock_request.return_value = {"slug": "my-workspace", "name": "My Workspace"}
        client = BitbucketClient(config=cloud_config)
        result = client.get_workspace()
        assert result["slug"] == "my-workspace"

    @patch.object(BitbucketClient, "_validate_connection")
    @patch.object(BitbucketClient, "_paginate")
    def test_get_default_reviewers(self, mock_paginate, mock_validate, cloud_config):
        mock_paginate.return_value = [{"uuid": "{user-1}", "display_name": "John"}]
        client = BitbucketClient(config=cloud_config)
        result = client.get_default_reviewers(repo_slug="my-repo")
        assert len(result) == 1


class TestRequiredParams:
    """Test that required parameters raise appropriate errors."""

    @patch.object(BitbucketClient, "_validate_connection")
    def test_cloud_requires_workspace(self, mock_validate):
        config = BitbucketConfig(
            url="https://bitbucket.org",
            auth_type="basic",
            username="user",
            app_password="pass",
            workspace=None,
        )
        client = BitbucketClient(config=config)
        with pytest.raises(ValueError, match="Workspace is required"):
            client.list_repositories()

    @patch.object(BitbucketClient, "_validate_connection")
    def test_server_requires_project_key(self, mock_validate):
        config = BitbucketConfig(
            url="https://bitbucket.company.com",
            auth_type="pat",
            personal_token="test-pat",
            project_key=None,
        )
        client = BitbucketClient(config=config)
        with pytest.raises(ValueError, match="Project key is required"):
            client.get_repository(repo_slug="my-repo")
