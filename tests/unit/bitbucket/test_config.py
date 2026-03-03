"""Tests for Bitbucket configuration module."""

import os

import pytest

from mcp_atlassian.bitbucket.config import BitbucketConfig, _is_bitbucket_cloud_url
from tests.utils.mocks import MockEnvironment


class TestIsBitbucketCloudUrl:
    """Tests for _is_bitbucket_cloud_url helper."""

    @pytest.mark.parametrize(
        "url,expected",
        [
            ("https://bitbucket.org", True),
            ("https://bitbucket.org/workspace/repo", True),
            ("https://api.bitbucket.org/2.0", True),
            ("https://bitbucket.company.com", False),
            ("https://git.company.com", False),
            ("http://localhost:7990", False),
            (None, False),
            ("", False),
        ],
    )
    def test_cloud_url_detection(self, url, expected):
        assert _is_bitbucket_cloud_url(url) == expected


class TestBitbucketConfig:
    """Tests for BitbucketConfig dataclass."""

    def test_cloud_basic_auth_from_env(self):
        """Test Cloud config with app password auth."""
        with MockEnvironment.clean_env():
            os.environ["BITBUCKET_URL"] = "https://bitbucket.org"
            os.environ["BITBUCKET_USERNAME"] = "testuser"
            os.environ["BITBUCKET_APP_PASSWORD"] = "test-app-password"

            config = BitbucketConfig.from_env()

            assert config.url == "https://bitbucket.org"
            assert config.auth_type == "basic"
            assert config.username == "testuser"
            assert config.app_password == "test-app-password"
            assert config.is_cloud is True
            assert config.api_base_url == "https://api.bitbucket.org/2.0"
            assert config.is_auth_configured() is True

    def test_server_pat_from_env(self):
        """Test Server/DC config with PAT."""
        with MockEnvironment.clean_env():
            os.environ["BITBUCKET_URL"] = "https://bitbucket.company.com"
            os.environ["BITBUCKET_PERSONAL_TOKEN"] = "test-pat"

            config = BitbucketConfig.from_env()

            assert config.url == "https://bitbucket.company.com"
            assert config.auth_type == "pat"
            assert config.personal_token == "test-pat"
            assert config.is_cloud is False
            assert config.api_base_url == "https://bitbucket.company.com/rest/api/1.0"
            assert config.is_auth_configured() is True

    def test_server_basic_auth_from_env(self):
        """Test Server/DC config with basic auth."""
        with MockEnvironment.clean_env():
            os.environ["BITBUCKET_URL"] = "https://bitbucket.company.com"
            os.environ["BITBUCKET_USERNAME"] = "admin"
            os.environ["BITBUCKET_APP_PASSWORD"] = "password"

            config = BitbucketConfig.from_env()

            assert config.auth_type == "basic"
            assert config.is_cloud is False
            assert config.is_auth_configured() is True

    def test_missing_url_raises(self):
        """Test that missing URL raises ValueError."""
        with MockEnvironment.clean_env():
            with pytest.raises(ValueError, match="Missing required BITBUCKET_URL"):
                BitbucketConfig.from_env()

    def test_cloud_missing_credentials_raises(self):
        """Test that Cloud without credentials raises ValueError."""
        with MockEnvironment.clean_env():
            os.environ["BITBUCKET_URL"] = "https://bitbucket.org"
            with pytest.raises(ValueError, match="BITBUCKET_USERNAME"):
                BitbucketConfig.from_env()

    def test_server_missing_credentials_raises(self):
        """Test that Server/DC without credentials raises ValueError."""
        with MockEnvironment.clean_env():
            os.environ["BITBUCKET_URL"] = "https://bitbucket.company.com"
            with pytest.raises(ValueError, match="BITBUCKET_PERSONAL_TOKEN"):
                BitbucketConfig.from_env()

    def test_workspace_from_env(self):
        """Test workspace configuration."""
        with MockEnvironment.clean_env():
            os.environ["BITBUCKET_URL"] = "https://bitbucket.org"
            os.environ["BITBUCKET_USERNAME"] = "testuser"
            os.environ["BITBUCKET_APP_PASSWORD"] = "test-app-password"
            os.environ["BITBUCKET_WORKSPACE"] = "my-workspace"

            config = BitbucketConfig.from_env()
            assert config.workspace == "my-workspace"

    def test_project_key_from_env(self):
        """Test project key configuration."""
        with MockEnvironment.clean_env():
            os.environ["BITBUCKET_URL"] = "https://bitbucket.company.com"
            os.environ["BITBUCKET_PERSONAL_TOKEN"] = "test-pat"
            os.environ["BITBUCKET_PROJECT_KEY"] = "PROJ"

            config = BitbucketConfig.from_env()
            assert config.project_key == "PROJ"

    def test_timeout_from_env(self):
        """Test timeout configuration."""
        with MockEnvironment.clean_env():
            os.environ["BITBUCKET_URL"] = "https://bitbucket.org"
            os.environ["BITBUCKET_USERNAME"] = "testuser"
            os.environ["BITBUCKET_APP_PASSWORD"] = "test-app-password"
            os.environ["BITBUCKET_TIMEOUT"] = "120"

            config = BitbucketConfig.from_env()
            assert config.timeout == 120

    def test_ssl_verify_from_env(self):
        """Test SSL verification configuration."""
        with MockEnvironment.clean_env():
            os.environ["BITBUCKET_URL"] = "https://bitbucket.company.com"
            os.environ["BITBUCKET_PERSONAL_TOKEN"] = "test-pat"
            os.environ["BITBUCKET_SSL_VERIFY"] = "false"

            config = BitbucketConfig.from_env()
            assert config.ssl_verify is False

    def test_proxy_from_env(self):
        """Test proxy configuration."""
        with MockEnvironment.clean_env():
            os.environ["BITBUCKET_URL"] = "https://bitbucket.org"
            os.environ["BITBUCKET_USERNAME"] = "testuser"
            os.environ["BITBUCKET_APP_PASSWORD"] = "test-app-password"
            os.environ["BITBUCKET_HTTPS_PROXY"] = "https://proxy.company.com:8080"

            config = BitbucketConfig.from_env()
            assert config.https_proxy == "https://proxy.company.com:8080"

    def test_is_auth_configured_no_auth(self):
        """Test is_auth_configured with incomplete auth."""
        config = BitbucketConfig(
            url="https://bitbucket.org",
            auth_type="basic",
            username=None,
            app_password=None,
        )
        assert config.is_auth_configured() is False

    def test_is_auth_configured_pat(self):
        """Test is_auth_configured with PAT."""
        config = BitbucketConfig(
            url="https://bitbucket.company.com",
            auth_type="pat",
            personal_token="test-token",
        )
        assert config.is_auth_configured() is True
