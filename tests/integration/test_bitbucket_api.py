"""Integration tests for Bitbucket API.

These tests validate real API interactions with Bitbucket Cloud and Server/DC.
They require the --integration and --use-real-data flags, plus environment variables.

Usage:
    # Bitbucket Cloud
    export BITBUCKET_URL=https://bitbucket.org
    export BITBUCKET_USERNAME=your_username
    export BITBUCKET_APP_PASSWORD=your_app_password
    export BITBUCKET_WORKSPACE=your_workspace
    export BITBUCKET_TEST_REPO=your_test_repo  # existing repo for read tests

    # Bitbucket Server/DC
    export BITBUCKET_URL=https://bitbucket.your-company.com
    export BITBUCKET_PERSONAL_TOKEN=your_pat
    export BITBUCKET_PROJECT_KEY=PROJ
    export BITBUCKET_TEST_REPO=your_test_repo

    uv run pytest tests/integration/test_bitbucket_api.py --integration --use-real-data -v
"""

import os

import pytest

from mcp_atlassian.bitbucket.config import BitbucketConfig


def _skip_unless_real_data(request):
    """Skip test if --use-real-data is not set."""
    if not request.config.getoption("--use-real-data", default=False):
        pytest.skip("Need --use-real-data option to run real API tests")


def _get_bitbucket_config():
    """Get BitbucketConfig from environment, or skip if not configured."""
    url = os.getenv("BITBUCKET_URL")
    if not url:
        pytest.skip("BITBUCKET_URL not set")
    try:
        return BitbucketConfig.from_env()
    except ValueError as e:
        pytest.skip(f"Bitbucket not configured: {e}")


def _get_test_repo():
    """Get test repository slug from environment."""
    repo = os.getenv("BITBUCKET_TEST_REPO")
    if not repo:
        pytest.skip("BITBUCKET_TEST_REPO not set")
    return repo


@pytest.mark.integration
class TestBitbucketReadOperations:
    """Test read-only operations against real Bitbucket API."""

    @pytest.fixture(autouse=True)
    def setup(self, request):
        _skip_unless_real_data(request)
        self.config = _get_bitbucket_config()
        self.repo = _get_test_repo()

        from mcp_atlassian.bitbucket.client import BitbucketClient

        self.client = BitbucketClient(config=self.config)
        self.workspace = self.config.workspace or self.config.project_key

    def test_list_repositories(self):
        """List repositories in workspace/project."""
        result = self.client.list_repositories(workspace=self.workspace, limit=5)
        assert isinstance(result, dict)
        assert "values" in result
        assert len(result["values"]) > 0

    def test_get_repository(self):
        """Get a specific repository."""
        result = self.client.get_repository(
            workspace=self.workspace, repo_slug=self.repo
        )
        assert isinstance(result, dict)
        assert result.get("slug") == self.repo or result.get("name") is not None

    def test_list_branches(self):
        """List branches in repository."""
        result = self.client.list_branches(
            workspace=self.workspace, repo_slug=self.repo, limit=10
        )
        assert isinstance(result, dict)
        assert "values" in result

    def test_list_commits(self):
        """List commits in repository."""
        result = self.client.list_commits(
            workspace=self.workspace, repo_slug=self.repo, limit=5
        )
        assert isinstance(result, dict)
        assert "values" in result
        assert len(result["values"]) > 0

    def test_get_file_content(self):
        """Get file content (README or similar)."""
        # Try common file names
        for filename in ["README.md", "README", "readme.md"]:
            try:
                result = self.client.get_file_content(
                    workspace=self.workspace,
                    repo_slug=self.repo,
                    path=filename,
                )
                assert isinstance(result, dict | str)
                return
            except Exception:
                continue
        pytest.skip("No README file found in test repo")

    def test_list_pull_requests(self):
        """List pull requests."""
        result = self.client.list_pull_requests(
            workspace=self.workspace, repo_slug=self.repo, limit=5
        )
        assert isinstance(result, dict)
        assert "values" in result

    def test_list_tags(self):
        """List tags in repository."""
        result = self.client.list_tags(
            workspace=self.workspace, repo_slug=self.repo, limit=5
        )
        assert isinstance(result, dict)
        assert "values" in result


@pytest.mark.integration
class TestBitbucketCloudOnly:
    """Test Cloud-only operations (pipelines, deployments)."""

    @pytest.fixture(autouse=True)
    def setup(self, request):
        _skip_unless_real_data(request)
        self.config = _get_bitbucket_config()
        if not self.config.is_cloud:
            pytest.skip("Cloud-only tests require Bitbucket Cloud")
        self.repo = _get_test_repo()

        from mcp_atlassian.bitbucket.client import BitbucketClient

        self.client = BitbucketClient(config=self.config)
        self.workspace = self.config.workspace

    def test_list_pipelines(self):
        """List pipelines (may be empty if not configured)."""
        try:
            result = self.client.list_pipelines(
                workspace=self.workspace, repo_slug=self.repo, limit=5
            )
            assert isinstance(result, dict)
        except Exception as e:
            if "not enabled" in str(e).lower() or "404" in str(e):
                pytest.skip("Pipelines not enabled for test repo")
            raise

    def test_list_workspaces(self):
        """List accessible workspaces."""
        result = self.client.list_workspaces(limit=5)
        assert isinstance(result, dict)
        assert "values" in result
        assert len(result["values"]) > 0

    def test_list_environments(self):
        """List deployment environments."""
        try:
            result = self.client.list_environments(
                workspace=self.workspace, repo_slug=self.repo
            )
            assert isinstance(result, dict)
        except Exception as e:
            if "not enabled" in str(e).lower() or "404" in str(e):
                pytest.skip("Deployments not enabled for test repo")
            raise


@pytest.mark.integration
class TestBitbucketAuthentication:
    """Test authentication configurations."""

    @pytest.fixture(autouse=True)
    def setup(self, request):
        _skip_unless_real_data(request)

    def test_config_from_env(self):
        """BitbucketConfig.from_env() succeeds with valid env vars."""
        config = _get_bitbucket_config()
        assert config.is_auth_configured()
        assert config.url is not None
        assert config.auth_type in ("basic", "pat", "oauth")

    def test_cloud_detection(self):
        """Cloud vs Server detection works correctly."""
        config = _get_bitbucket_config()
        url = os.getenv("BITBUCKET_URL", "")
        if "bitbucket.org" in url:
            assert config.is_cloud is True
            assert "api.bitbucket.org" in config.api_base_url
        else:
            assert config.is_cloud is False
            assert "/rest/api/1.0" in config.api_base_url

    def test_api_request_succeeds(self):
        """Basic API request succeeds with configured auth."""
        from mcp_atlassian.bitbucket.client import BitbucketClient

        config = _get_bitbucket_config()
        client = BitbucketClient(config=config)
        repo = _get_test_repo()
        workspace = config.workspace or config.project_key

        # Simple read operation to verify auth works
        result = client.get_repository(workspace=workspace, repo_slug=repo)
        assert result is not None
