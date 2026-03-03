"""Base client module for Bitbucket API interactions.

Supports both Bitbucket Cloud (REST API 2.0) and Server/Data Center (REST API 1.0)
with automatic platform detection based on URL.
"""

import logging
import tempfile
import time
from pathlib import Path
from typing import Any

import httpx

from .config import BitbucketConfig

# Retry configuration
_MAX_RETRIES = 3
_RETRY_STATUS_CODES = {429, 500, 502, 503, 504}
_RETRY_BASE_DELAY = 1.0  # seconds

logger = logging.getLogger("mcp-atlassian.bitbucket.client")


class BitbucketClient:
    """Unified Bitbucket API client supporting Cloud and Server/DC.

    Uses httpx for HTTP requests. Automatically routes requests to the
    correct API version based on configuration.
    """

    config: BitbucketConfig
    _http: httpx.Client

    def __init__(self, config: BitbucketConfig | None = None) -> None:
        """Initialize the Bitbucket client.

        Args:
            config: Optional configuration (uses env vars if not provided).

        Raises:
            ValueError: If configuration is invalid.
        """
        self.config = config or BitbucketConfig.from_env()
        self._http = self._create_http_client()
        self._validate_connection()

    def _create_http_client(self) -> httpx.Client:
        """Create an httpx client with proper authentication and settings."""
        headers: dict[str, str] = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

        if self.config.custom_headers:
            headers.update(self.config.custom_headers)

        auth: httpx.BasicAuth | None = None
        if self.config.auth_type == "basic":
            auth = httpx.BasicAuth(
                username=self.config.username or "",
                password=self.config.app_password or "",
            )
        elif self.config.auth_type == "pat":
            headers["Authorization"] = f"Bearer {self.config.personal_token}"
        elif self.config.auth_type == "oauth" and self.config.oauth_config:
            access_token = getattr(self.config.oauth_config, "access_token", None)
            if access_token:
                headers["Authorization"] = f"Bearer {access_token}"

        proxy_url = (
            self.config.https_proxy or self.config.http_proxy or self.config.socks_proxy
        )

        # Connection pooling for performance
        pool_limits = httpx.Limits(
            max_connections=20,
            max_keepalive_connections=10,
            keepalive_expiry=30,
        )

        return httpx.Client(
            auth=auth,
            headers=headers,
            timeout=httpx.Timeout(self.config.timeout),
            verify=self.config.ssl_verify,
            proxy=proxy_url,
            follow_redirects=True,
            limits=pool_limits,
        )

    def _validate_connection(self) -> None:
        """Validate connection by making a lightweight API call."""
        try:
            if self.config.is_cloud:
                self.get_current_user()
            else:
                # Server/DC: check application properties
                self._request("GET", "/application-properties")
            logger.debug("Bitbucket connection validated successfully")
        except Exception as e:
            logger.warning(f"Bitbucket connection validation failed: {e}")

    def _build_url(self, path: str) -> str:
        """Build full URL from relative path.

        Args:
            path: API path (e.g., /repositories/{workspace}/{repo_slug}).

        Returns:
            Full URL with base API path prepended.
        """
        base = self.config.api_base_url.rstrip("/")
        path = path.lstrip("/")
        return f"{base}/{path}"

    def _request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        json_data: dict[str, Any] | None = None,
        raw_response: bool = False,
    ) -> Any:
        """Make an HTTP request to the Bitbucket API.

        Args:
            method: HTTP method (GET, POST, PUT, DELETE).
            path: API path relative to base URL.
            params: Query parameters.
            json_data: JSON body for POST/PUT requests.
            raw_response: If True, return the httpx.Response object.

        Returns:
            Parsed JSON response or raw response object.

        Raises:
            httpx.HTTPStatusError: On HTTP error responses.
        """
        url = self._build_url(path)
        logger.debug(f"Bitbucket API {method} {url}")

        last_exc: Exception | None = None
        for attempt in range(_MAX_RETRIES):
            try:
                response = self._http.request(
                    method=method,
                    url=url,
                    params=params,
                    json=json_data,
                )
                if (
                    response.status_code in _RETRY_STATUS_CODES
                    and attempt < _MAX_RETRIES - 1
                ):
                    delay = _RETRY_BASE_DELAY * (2**attempt)
                    # Respect Retry-After header if present
                    retry_after = response.headers.get("Retry-After")
                    if retry_after:
                        try:
                            delay = max(delay, float(retry_after))
                        except ValueError:
                            pass
                    logger.warning(
                        f"Bitbucket API {method} {url} returned {response.status_code}, "
                        f"retrying in {delay:.1f}s (attempt {attempt + 1}/{_MAX_RETRIES})"
                    )
                    time.sleep(delay)
                    continue

                response.raise_for_status()

                if raw_response:
                    return response

                if response.status_code == 204:
                    return None

                content_type = response.headers.get("content-type", "")
                if "application/json" in content_type:
                    return response.json()
                return response.text

            except httpx.ConnectError as e:
                last_exc = e
                if attempt < _MAX_RETRIES - 1:
                    delay = _RETRY_BASE_DELAY * (2**attempt)
                    logger.warning(
                        f"Bitbucket API connection error: {e}, "
                        f"retrying in {delay:.1f}s (attempt {attempt + 1}/{_MAX_RETRIES})"
                    )
                    time.sleep(delay)
                    continue
                raise

        # Should not reach here, but just in case
        if last_exc:
            raise last_exc
        raise RuntimeError("Retry loop exhausted without result")

    def _paginate(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        max_results: int = 100,
    ) -> list[dict[str, Any]]:
        """Paginate through API results.

        Handles both Cloud (next URL) and Server/DC (start/limit) pagination.

        Args:
            path: API path.
            params: Query parameters.
            max_results: Maximum total results to return.

        Returns:
            List of result items.
        """
        params = dict(params or {})
        results: list[dict[str, Any]] = []

        if self.config.is_cloud:
            params.setdefault("pagelen", min(max_results, 100))
            url = self._build_url(path)

            while url and len(results) < max_results:
                response = self._http.get(url, params=params)
                response.raise_for_status()
                data = response.json()

                values = data.get("values", [])
                results.extend(values)

                url = data.get("next")
                params = {}  # Next URL already includes params
        else:
            # Server/DC uses start/limit pagination
            params.setdefault("limit", min(max_results, 25))
            start = params.get("start", 0)

            while len(results) < max_results:
                params["start"] = start
                data = self._request("GET", path, params=params)

                values = data.get("values", [])
                if not values:
                    break

                results.extend(values)

                if data.get("isLastPage", True):
                    break

                start = data.get("nextPageStart", start + len(values))

        return results[:max_results]

    def close(self) -> None:
        """Close the underlying HTTP client."""
        self._http.close()

    # ------------------------------------------------------------------
    # User operations
    # ------------------------------------------------------------------

    def get_current_user(self) -> dict[str, Any]:
        """Get the currently authenticated user.

        Returns:
            User profile data.
        """
        if self.config.is_cloud:
            return self._request("GET", "/user")
        return self._request("GET", "/users", params={"filter": "@me"})

    # ------------------------------------------------------------------
    # Repository operations
    # ------------------------------------------------------------------

    def list_repositories(
        self,
        workspace: str | None = None,
        project_key: str | None = None,
        query: str | None = None,
        max_results: int = 25,
    ) -> list[dict[str, Any]]:
        """List repositories.

        Args:
            workspace: Workspace slug (Cloud) or project key (Server/DC).
            project_key: Project key filter (Server/DC).
            query: Search query string.
            max_results: Maximum results to return.

        Returns:
            List of repository objects.
        """
        workspace = workspace or self.config.workspace
        params: dict[str, Any] = {}

        if self.config.is_cloud:
            if not workspace:
                raise ValueError("Workspace is required for Bitbucket Cloud")
            path = f"/repositories/{workspace}"
            if query:
                params["q"] = query
        else:
            project = project_key or self.config.project_key
            if project:
                path = f"/projects/{project}/repos"
            else:
                path = "/repos"
            if query:
                params["name"] = query

        return self._paginate(path, params=params, max_results=max_results)

    def create_repository(
        self,
        repo_slug: str,
        workspace: str | None = None,
        project_key: str | None = None,
        is_private: bool = True,
        description: str = "",
        fork_policy: str = "allow_forks",
        language: str = "",
        has_wiki: bool = False,
        has_issues: bool = False,
    ) -> dict[str, Any]:
        """Create a new repository.

        Args:
            repo_slug: Repository slug (URL-friendly name).
            workspace: Workspace slug (Cloud).
            project_key: Project key (Server/DC).
            is_private: Whether the repository is private.
            description: Repository description.
            fork_policy: Fork policy (Cloud: allow_forks, no_public_forks, no_forks).
            language: Programming language.
            has_wiki: Enable wiki (Cloud only).
            has_issues: Enable issue tracker (Cloud only).

        Returns:
            Created repository details.
        """
        workspace = workspace or self.config.workspace

        if self.config.is_cloud:
            if not workspace:
                raise ValueError("Workspace is required for Bitbucket Cloud")
            body: dict[str, Any] = {
                "scm": "git",
                "is_private": is_private,
                "description": description,
                "fork_policy": fork_policy,
                "has_wiki": has_wiki,
                "has_issues": has_issues,
            }
            if language:
                body["language"] = language
            return self._request(
                "POST",
                f"/repositories/{workspace}/{repo_slug}",
                json_data=body,
            )
        else:
            project = project_key or self.config.project_key
            if not project:
                raise ValueError("Project key is required for Bitbucket Server/DC")
            body = {
                "name": repo_slug,
                "scmId": "git",
                "public": not is_private,
                "description": description,
            }
            return self._request(
                "POST",
                f"/projects/{project}/repos",
                json_data=body,
            )

    def update_repository(
        self,
        repo_slug: str,
        workspace: str | None = None,
        project_key: str | None = None,
        description: str | None = None,
        is_private: bool | None = None,
        fork_policy: str | None = None,
        language: str | None = None,
        has_wiki: bool | None = None,
        has_issues: bool | None = None,
    ) -> dict[str, Any]:
        """Update repository settings.

        Args:
            repo_slug: Repository slug.
            workspace: Workspace slug (Cloud).
            project_key: Project key (Server/DC).
            description: New description.
            is_private: Change visibility.
            fork_policy: Change fork policy (Cloud only).
            language: Change language.
            has_wiki: Toggle wiki (Cloud only).
            has_issues: Toggle issues (Cloud only).

        Returns:
            Updated repository details.
        """
        workspace = workspace or self.config.workspace
        body: dict[str, Any] = {}

        if self.config.is_cloud:
            if not workspace:
                raise ValueError("Workspace is required for Bitbucket Cloud")
            if description is not None:
                body["description"] = description
            if is_private is not None:
                body["is_private"] = is_private
            if fork_policy is not None:
                body["fork_policy"] = fork_policy
            if language is not None:
                body["language"] = language
            if has_wiki is not None:
                body["has_wiki"] = has_wiki
            if has_issues is not None:
                body["has_issues"] = has_issues
            return self._request(
                "PUT",
                f"/repositories/{workspace}/{repo_slug}",
                json_data=body,
            )
        else:
            project = project_key or self.config.project_key
            if not project:
                raise ValueError("Project key is required for Bitbucket Server/DC")
            if description is not None:
                body["description"] = description
            if is_private is not None:
                body["public"] = not is_private
            return self._request(
                "PUT",
                f"/projects/{project}/repos/{repo_slug}",
                json_data=body,
            )

    def delete_repository(
        self,
        repo_slug: str,
        workspace: str | None = None,
        project_key: str | None = None,
    ) -> None:
        """Delete a repository.

        Args:
            repo_slug: Repository slug.
            workspace: Workspace slug (Cloud).
            project_key: Project key (Server/DC).
        """
        workspace = workspace or self.config.workspace

        if self.config.is_cloud:
            if not workspace:
                raise ValueError("Workspace is required for Bitbucket Cloud")
            self._request("DELETE", f"/repositories/{workspace}/{repo_slug}")
        else:
            project = project_key or self.config.project_key
            if not project:
                raise ValueError("Project key is required for Bitbucket Server/DC")
            self._request("DELETE", f"/projects/{project}/repos/{repo_slug}")

    def fork_repository(
        self,
        repo_slug: str,
        workspace: str | None = None,
        project_key: str | None = None,
        new_name: str | None = None,
        target_workspace: str | None = None,
        target_project_key: str | None = None,
    ) -> dict[str, Any]:
        """Fork a repository.

        Args:
            repo_slug: Source repository slug.
            workspace: Source workspace slug (Cloud).
            project_key: Source project key (Server/DC).
            new_name: Name for the forked repo (defaults to same name).
            target_workspace: Target workspace for fork (Cloud only).
            target_project_key: Target project for fork (Server/DC only).

        Returns:
            Forked repository details.
        """
        workspace = workspace or self.config.workspace

        if self.config.is_cloud:
            if not workspace:
                raise ValueError("Workspace is required for Bitbucket Cloud")
            body: dict[str, Any] = {}
            if new_name:
                body["name"] = new_name
            if target_workspace:
                body["workspace"] = {"slug": target_workspace}
            return self._request(
                "POST",
                f"/repositories/{workspace}/{repo_slug}/forks",
                json_data=body,
            )
        else:
            project = project_key or self.config.project_key
            if not project:
                raise ValueError("Project key is required for Bitbucket Server/DC")
            body = {}
            if new_name:
                body["name"] = new_name
            if target_project_key:
                body["project"] = {"key": target_project_key}
            slug = new_name or repo_slug
            body["slug"] = slug
            return self._request(
                "POST",
                f"/projects/{project}/repos/{repo_slug}",
                json_data=body,
            )

    def list_forks(
        self,
        repo_slug: str,
        workspace: str | None = None,
        project_key: str | None = None,
        max_results: int = 25,
    ) -> list[dict[str, Any]]:
        """List forks of a repository.

        Args:
            repo_slug: Repository slug.
            workspace: Workspace slug (Cloud).
            project_key: Project key (Server/DC).
            max_results: Maximum results.

        Returns:
            List of forked repository objects.
        """
        workspace = workspace or self.config.workspace

        if self.config.is_cloud:
            if not workspace:
                raise ValueError("Workspace is required for Bitbucket Cloud")
            return self._paginate(
                f"/repositories/{workspace}/{repo_slug}/forks",
                max_results=max_results,
            )
        else:
            project = project_key or self.config.project_key
            if not project:
                raise ValueError("Project key is required for Bitbucket Server/DC")
            return self._paginate(
                f"/projects/{project}/repos/{repo_slug}/forks",
                max_results=max_results,
            )

    def get_repository(
        self,
        repo_slug: str,
        workspace: str | None = None,
        project_key: str | None = None,
    ) -> dict[str, Any]:
        """Get a single repository.

        Args:
            repo_slug: Repository slug/name.
            workspace: Workspace slug (Cloud).
            project_key: Project key (Server/DC).

        Returns:
            Repository details.
        """
        workspace = workspace or self.config.workspace
        if self.config.is_cloud:
            if not workspace:
                raise ValueError("Workspace is required for Bitbucket Cloud")
            return self._request("GET", f"/repositories/{workspace}/{repo_slug}")
        else:
            project = project_key or self.config.project_key
            if not project:
                raise ValueError("Project key is required for Bitbucket Server/DC")
            return self._request("GET", f"/projects/{project}/repos/{repo_slug}")

    # ------------------------------------------------------------------
    # Pull Request operations
    # ------------------------------------------------------------------

    def list_pull_requests(
        self,
        repo_slug: str,
        workspace: str | None = None,
        project_key: str | None = None,
        state: str = "OPEN",
        max_results: int = 25,
    ) -> list[dict[str, Any]]:
        """List pull requests for a repository.

        Args:
            repo_slug: Repository slug.
            workspace: Workspace slug (Cloud).
            project_key: Project key (Server/DC).
            state: Filter by state (OPEN, MERGED, DECLINED, SUPERSEDED).
            max_results: Maximum results.

        Returns:
            List of pull request objects.
        """
        workspace = workspace or self.config.workspace
        params: dict[str, Any] = {"state": state}

        if self.config.is_cloud:
            if not workspace:
                raise ValueError("Workspace is required for Bitbucket Cloud")
            path = f"/repositories/{workspace}/{repo_slug}/pullrequests"
        else:
            project = project_key or self.config.project_key
            if not project:
                raise ValueError("Project key is required for Bitbucket Server/DC")
            path = f"/projects/{project}/repos/{repo_slug}/pull-requests"

        return self._paginate(path, params=params, max_results=max_results)

    @staticmethod
    def _compact_pull_request(data: dict[str, Any]) -> dict[str, Any]:
        """Extract essential PR fields, stripping verbose nested objects."""

        def _user_name(user_obj: Any) -> str | None:
            if not user_obj or not isinstance(user_obj, dict):
                return None
            return (
                user_obj.get("display_name")
                or user_obj.get("nickname")
                or user_obj.get("name")
            )

        def _branch_info(ref: Any) -> dict[str, str | None] | None:
            if not ref or not isinstance(ref, dict):
                return None
            branch = ref.get("branch", {})
            repo = ref.get("repository", {})
            return {
                "branch": branch.get("name") if isinstance(branch, dict) else None,
                "repo": repo.get("full_name") or repo.get("slug")
                if isinstance(repo, dict)
                else None,
                "commit": (ref.get("commit", {}) or {}).get("hash", "")[:12],
            }

        reviewers = data.get("reviewers") or []
        participants = data.get("participants") or []

        return {
            "id": data.get("id"),
            "title": data.get("title"),
            "state": data.get("state"),
            "author": _user_name(
                data.get("author", {}).get("user") or data.get("author")
            ),
            "source": _branch_info(data.get("source")),
            "destination": _branch_info(data.get("destination")),
            "description": data.get("description")
            or data.get("summary", {}).get("raw", ""),
            "created_on": data.get("created_on"),
            "updated_on": data.get("updated_on"),
            "comment_count": data.get("comment_count"),
            "task_count": data.get("task_count"),
            "reviewers": [_user_name(r.get("user") or r) for r in reviewers],
            "approved_by": [
                _user_name(p.get("user") or p)
                for p in participants
                if p.get("approved") or p.get("status") == "approved"
            ],
            "merge_commit": (data.get("merge_commit") or {}).get("hash"),
            "close_source_branch": data.get("close_source_branch"),
            "draft": data.get("draft"),
            "links": {
                "html": (data.get("links", {}).get("html", {}) or {}).get("href"),
            },
        }

    @staticmethod
    def _save_content_to_file(
        content: str,
        prefix: str = "bitbucket",
        suffix: str = ".txt",
    ) -> dict[str, Any]:
        """Write content to a temp file, return metadata instead of content."""
        tmp = Path(tempfile.gettempdir()) / f"{prefix}{suffix}"
        tmp.write_text(content, encoding="utf-8")
        line_count = content.count("\n") + (
            1 if content and not content.endswith("\n") else 0
        )
        return {
            "file_path": str(tmp),
            "size_bytes": tmp.stat().st_size,
            "lines": line_count,
            "message": f"Content saved to {tmp}. Use Read tool to access it.",
        }

    def get_pull_request(
        self,
        repo_slug: str,
        pr_id: int,
        workspace: str | None = None,
        project_key: str | None = None,
        compact: bool = False,
    ) -> dict[str, Any]:
        """Get a single pull request.

        Args:
            repo_slug: Repository slug.
            pr_id: Pull request ID.
            workspace: Workspace slug (Cloud).
            project_key: Project key (Server/DC).
            compact: If True, return only essential fields (title, author,
                     branches, state, description, reviewers) instead of the
                     full API response.  Reduces token usage by ~90%.

        Returns:
            Pull request details (full or compact).
        """
        workspace = workspace or self.config.workspace
        if self.config.is_cloud:
            if not workspace:
                raise ValueError("Workspace is required for Bitbucket Cloud")
            result = self._request(
                "GET",
                f"/repositories/{workspace}/{repo_slug}/pullrequests/{pr_id}",
            )
        else:
            project = project_key or self.config.project_key
            if not project:
                raise ValueError("Project key is required for Bitbucket Server/DC")
            result = self._request(
                "GET",
                f"/projects/{project}/repos/{repo_slug}/pull-requests/{pr_id}",
            )

        if compact:
            return self._compact_pull_request(result)
        return result

    def create_pull_request(
        self,
        repo_slug: str,
        title: str,
        source_branch: str,
        destination_branch: str,
        description: str = "",
        workspace: str | None = None,
        project_key: str | None = None,
        reviewers: list[str] | None = None,
        close_source_branch: bool = False,
    ) -> dict[str, Any]:
        """Create a pull request.

        Args:
            repo_slug: Repository slug.
            title: PR title.
            source_branch: Source branch name.
            destination_branch: Target branch name.
            description: PR description.
            workspace: Workspace slug (Cloud).
            project_key: Project key (Server/DC).
            reviewers: List of reviewer usernames/UUIDs.
            close_source_branch: Whether to close source branch on merge.

        Returns:
            Created pull request details.
        """
        workspace = workspace or self.config.workspace

        if self.config.is_cloud:
            if not workspace:
                raise ValueError("Workspace is required for Bitbucket Cloud")
            body: dict[str, Any] = {
                "title": title,
                "description": description,
                "source": {"branch": {"name": source_branch}},
                "destination": {"branch": {"name": destination_branch}},
                "close_source_branch": close_source_branch,
            }
            if reviewers:
                body["reviewers"] = [{"uuid": r} for r in reviewers]
            return self._request(
                "POST",
                f"/repositories/{workspace}/{repo_slug}/pullrequests",
                json_data=body,
            )
        else:
            project = project_key or self.config.project_key
            if not project:
                raise ValueError("Project key is required for Bitbucket Server/DC")
            body = {
                "title": title,
                "description": description,
                "fromRef": {
                    "id": f"refs/heads/{source_branch}",
                    "repository": {"slug": repo_slug, "project": {"key": project}},
                },
                "toRef": {
                    "id": f"refs/heads/{destination_branch}",
                    "repository": {"slug": repo_slug, "project": {"key": project}},
                },
            }
            if reviewers:
                body["reviewers"] = [{"user": {"name": r}} for r in reviewers]
            return self._request(
                "POST",
                f"/projects/{project}/repos/{repo_slug}/pull-requests",
                json_data=body,
            )

    def merge_pull_request(
        self,
        repo_slug: str,
        pr_id: int,
        workspace: str | None = None,
        project_key: str | None = None,
        merge_strategy: str | None = None,
        message: str | None = None,
    ) -> dict[str, Any]:
        """Merge a pull request.

        Args:
            repo_slug: Repository slug.
            pr_id: Pull request ID.
            workspace: Workspace slug (Cloud).
            project_key: Project key (Server/DC).
            merge_strategy: Merge strategy (merge_commit, squash, fast_forward).
            message: Merge commit message.

        Returns:
            Merged pull request details.
        """
        workspace = workspace or self.config.workspace
        body: dict[str, Any] = {}

        if self.config.is_cloud:
            if not workspace:
                raise ValueError("Workspace is required for Bitbucket Cloud")
            if merge_strategy:
                body["merge_strategy"] = merge_strategy
            if message:
                body["message"] = message
            return self._request(
                "POST",
                f"/repositories/{workspace}/{repo_slug}/pullrequests/{pr_id}/merge",
                json_data=body,
            )
        else:
            project = project_key or self.config.project_key
            if not project:
                raise ValueError("Project key is required for Bitbucket Server/DC")
            # Get current PR version for optimistic locking
            pr = self.get_pull_request(repo_slug, pr_id, project_key=project)
            body["version"] = pr.get("version", 0)
            if message:
                body["message"] = message
            return self._request(
                "POST",
                f"/projects/{project}/repos/{repo_slug}/pull-requests/{pr_id}/merge",
                json_data=body,
            )

    def add_pull_request_comment(
        self,
        repo_slug: str,
        pr_id: int,
        content: str,
        workspace: str | None = None,
        project_key: str | None = None,
    ) -> dict[str, Any]:
        """Add a comment to a pull request.

        Args:
            repo_slug: Repository slug.
            pr_id: Pull request ID.
            content: Comment text.
            workspace: Workspace slug (Cloud).
            project_key: Project key (Server/DC).

        Returns:
            Created comment details.
        """
        workspace = workspace or self.config.workspace

        if self.config.is_cloud:
            if not workspace:
                raise ValueError("Workspace is required for Bitbucket Cloud")
            body: dict[str, Any] = {"content": {"raw": content}}
            return self._request(
                "POST",
                f"/repositories/{workspace}/{repo_slug}/pullrequests/{pr_id}/comments",
                json_data=body,
            )
        else:
            project = project_key or self.config.project_key
            if not project:
                raise ValueError("Project key is required for Bitbucket Server/DC")
            body_server: dict[str, Any] = {"text": content}
            return self._request(
                "POST",
                f"/projects/{project}/repos/{repo_slug}/pull-requests/{pr_id}/comments",
                json_data=body_server,
            )

    def update_pull_request(
        self,
        repo_slug: str,
        pr_id: int,
        workspace: str | None = None,
        project_key: str | None = None,
        title: str | None = None,
        description: str | None = None,
        destination_branch: str | None = None,
        reviewers: list[str] | None = None,
    ) -> dict[str, Any]:
        """Update a pull request.

        Args:
            repo_slug: Repository slug.
            pr_id: Pull request ID.
            workspace: Workspace slug (Cloud).
            project_key: Project key (Server/DC).
            title: New title.
            description: New description.
            destination_branch: New destination branch.
            reviewers: New list of reviewer usernames/UUIDs.

        Returns:
            Updated pull request details.
        """
        workspace = workspace or self.config.workspace
        body: dict[str, Any] = {}

        if self.config.is_cloud:
            if not workspace:
                raise ValueError("Workspace is required for Bitbucket Cloud")
            if title is not None:
                body["title"] = title
            if description is not None:
                body["description"] = description
            if destination_branch is not None:
                body["destination"] = {"branch": {"name": destination_branch}}
            if reviewers is not None:
                body["reviewers"] = [{"uuid": r} for r in reviewers]
            return self._request(
                "PUT",
                f"/repositories/{workspace}/{repo_slug}/pullrequests/{pr_id}",
                json_data=body,
            )
        else:
            project = project_key or self.config.project_key
            if not project:
                raise ValueError("Project key is required for Bitbucket Server/DC")
            # Get current version for optimistic locking
            pr = self.get_pull_request(repo_slug, pr_id, project_key=project)
            body["version"] = pr.get("version", 0)
            if title is not None:
                body["title"] = title
            if description is not None:
                body["description"] = description
            if destination_branch is not None:
                body["toRef"] = {"id": f"refs/heads/{destination_branch}"}
            if reviewers is not None:
                body["reviewers"] = [{"user": {"name": r}} for r in reviewers]
            return self._request(
                "PUT",
                f"/projects/{project}/repos/{repo_slug}/pull-requests/{pr_id}",
                json_data=body,
            )

    def decline_pull_request(
        self,
        repo_slug: str,
        pr_id: int,
        workspace: str | None = None,
        project_key: str | None = None,
    ) -> dict[str, Any]:
        """Decline a pull request.

        Args:
            repo_slug: Repository slug.
            pr_id: Pull request ID.
            workspace: Workspace slug (Cloud).
            project_key: Project key (Server/DC).

        Returns:
            Declined pull request details.
        """
        workspace = workspace or self.config.workspace

        if self.config.is_cloud:
            if not workspace:
                raise ValueError("Workspace is required for Bitbucket Cloud")
            return self._request(
                "POST",
                f"/repositories/{workspace}/{repo_slug}/pullrequests/{pr_id}/decline",
            )
        else:
            project = project_key or self.config.project_key
            if not project:
                raise ValueError("Project key is required for Bitbucket Server/DC")
            pr = self.get_pull_request(repo_slug, pr_id, project_key=project)
            return self._request(
                "POST",
                f"/projects/{project}/repos/{repo_slug}/pull-requests/{pr_id}/decline",
                json_data={"version": pr.get("version", 0)},
            )

    def approve_pull_request(
        self,
        repo_slug: str,
        pr_id: int,
        workspace: str | None = None,
        project_key: str | None = None,
    ) -> dict[str, Any]:
        """Approve a pull request.

        Args:
            repo_slug: Repository slug.
            pr_id: Pull request ID.
            workspace: Workspace slug (Cloud).
            project_key: Project key (Server/DC).

        Returns:
            Approval details.
        """
        workspace = workspace or self.config.workspace

        if self.config.is_cloud:
            if not workspace:
                raise ValueError("Workspace is required for Bitbucket Cloud")
            return self._request(
                "POST",
                f"/repositories/{workspace}/{repo_slug}/pullrequests/{pr_id}/approve",
            )
        else:
            project = project_key or self.config.project_key
            if not project:
                raise ValueError("Project key is required for Bitbucket Server/DC")
            return self._request(
                "POST",
                f"/projects/{project}/repos/{repo_slug}/pull-requests/{pr_id}/approve",
            )

    def unapprove_pull_request(
        self,
        repo_slug: str,
        pr_id: int,
        workspace: str | None = None,
        project_key: str | None = None,
    ) -> None:
        """Remove approval from a pull request.

        Args:
            repo_slug: Repository slug.
            pr_id: Pull request ID.
            workspace: Workspace slug (Cloud).
            project_key: Project key (Server/DC).
        """
        workspace = workspace or self.config.workspace

        if self.config.is_cloud:
            if not workspace:
                raise ValueError("Workspace is required for Bitbucket Cloud")
            self._request(
                "DELETE",
                f"/repositories/{workspace}/{repo_slug}/pullrequests/{pr_id}/approve",
            )
        else:
            project = project_key or self.config.project_key
            if not project:
                raise ValueError("Project key is required for Bitbucket Server/DC")
            self._request(
                "DELETE",
                f"/projects/{project}/repos/{repo_slug}/pull-requests/{pr_id}/approve",
            )

    def request_changes_pull_request(
        self,
        repo_slug: str,
        pr_id: int,
        workspace: str | None = None,
        project_key: str | None = None,
    ) -> dict[str, Any]:
        """Request changes on a pull request.

        Args:
            repo_slug: Repository slug.
            pr_id: Pull request ID.
            workspace: Workspace slug (Cloud).
            project_key: Project key (Server/DC).

        Returns:
            Request changes details.
        """
        workspace = workspace or self.config.workspace

        if self.config.is_cloud:
            if not workspace:
                raise ValueError("Workspace is required for Bitbucket Cloud")
            return self._request(
                "POST",
                f"/repositories/{workspace}/{repo_slug}/pullrequests/{pr_id}/request-changes",
            )
        else:
            project = project_key or self.config.project_key
            if not project:
                raise ValueError("Project key is required for Bitbucket Server/DC")
            # Server/DC uses "needs work" status
            return self._request(
                "PUT",
                f"/projects/{project}/repos/{repo_slug}/pull-requests/{pr_id}/participants/@me",
                json_data={"status": "NEEDS_WORK"},
            )

    def get_pull_request_commits(
        self,
        repo_slug: str,
        pr_id: int,
        workspace: str | None = None,
        project_key: str | None = None,
        max_results: int = 100,
    ) -> list[dict[str, Any]]:
        """Get commits in a pull request.

        Args:
            repo_slug: Repository slug.
            pr_id: Pull request ID.
            workspace: Workspace slug (Cloud).
            project_key: Project key (Server/DC).
            max_results: Maximum results.

        Returns:
            List of commit objects.
        """
        workspace = workspace or self.config.workspace

        if self.config.is_cloud:
            if not workspace:
                raise ValueError("Workspace is required for Bitbucket Cloud")
            return self._paginate(
                f"/repositories/{workspace}/{repo_slug}/pullrequests/{pr_id}/commits",
                max_results=max_results,
            )
        else:
            project = project_key or self.config.project_key
            if not project:
                raise ValueError("Project key is required for Bitbucket Server/DC")
            return self._paginate(
                f"/projects/{project}/repos/{repo_slug}/pull-requests/{pr_id}/commits",
                max_results=max_results,
            )

    def list_pull_request_comments(
        self,
        repo_slug: str,
        pr_id: int,
        workspace: str | None = None,
        project_key: str | None = None,
        max_results: int = 100,
    ) -> list[dict[str, Any]]:
        """List comments on a pull request.

        Args:
            repo_slug: Repository slug.
            pr_id: Pull request ID.
            workspace: Workspace slug (Cloud).
            project_key: Project key (Server/DC).
            max_results: Maximum results.

        Returns:
            List of comment objects.
        """
        workspace = workspace or self.config.workspace

        if self.config.is_cloud:
            if not workspace:
                raise ValueError("Workspace is required for Bitbucket Cloud")
            return self._paginate(
                f"/repositories/{workspace}/{repo_slug}/pullrequests/{pr_id}/comments",
                max_results=max_results,
            )
        else:
            project = project_key or self.config.project_key
            if not project:
                raise ValueError("Project key is required for Bitbucket Server/DC")
            # Server/DC: activities endpoint includes comments
            return self._paginate(
                f"/projects/{project}/repos/{repo_slug}/pull-requests/{pr_id}/activities",
                max_results=max_results,
            )

    def add_inline_comment(
        self,
        repo_slug: str,
        pr_id: int,
        content: str,
        file_path: str,
        line: int,
        workspace: str | None = None,
        project_key: str | None = None,
        side: str = "new",
    ) -> dict[str, Any]:
        """Add an inline comment to a pull request on a specific file/line.

        Args:
            repo_slug: Repository slug.
            pr_id: Pull request ID.
            content: Comment text.
            file_path: File path to comment on.
            line: Line number.
            workspace: Workspace slug (Cloud).
            project_key: Project key (Server/DC).
            side: Which side of the diff: 'new' or 'old' (Cloud only).

        Returns:
            Created comment details.
        """
        workspace = workspace or self.config.workspace

        if self.config.is_cloud:
            if not workspace:
                raise ValueError("Workspace is required for Bitbucket Cloud")
            body: dict[str, Any] = {
                "content": {"raw": content},
                "inline": {
                    "path": file_path,
                    "to": line if side == "new" else None,
                    "from": line if side == "old" else None,
                },
            }
            return self._request(
                "POST",
                f"/repositories/{workspace}/{repo_slug}/pullrequests/{pr_id}/comments",
                json_data=body,
            )
        else:
            project = project_key or self.config.project_key
            if not project:
                raise ValueError("Project key is required for Bitbucket Server/DC")
            body = {
                "text": content,
                "anchor": {
                    "path": file_path,
                    "line": line,
                    "lineType": "ADDED" if side == "new" else "REMOVED",
                    "fileType": "TO" if side == "new" else "FROM",
                },
            }
            return self._request(
                "POST",
                f"/projects/{project}/repos/{repo_slug}/pull-requests/{pr_id}/comments",
                json_data=body,
            )

    def reply_to_comment(
        self,
        repo_slug: str,
        pr_id: int,
        comment_id: int,
        content: str,
        workspace: str | None = None,
        project_key: str | None = None,
    ) -> dict[str, Any]:
        """Reply to a pull request comment.

        Args:
            repo_slug: Repository slug.
            pr_id: Pull request ID.
            comment_id: Parent comment ID to reply to.
            content: Reply text.
            workspace: Workspace slug (Cloud).
            project_key: Project key (Server/DC).

        Returns:
            Created reply details.
        """
        workspace = workspace or self.config.workspace

        if self.config.is_cloud:
            if not workspace:
                raise ValueError("Workspace is required for Bitbucket Cloud")
            body: dict[str, Any] = {
                "content": {"raw": content},
                "parent": {"id": comment_id},
            }
            return self._request(
                "POST",
                f"/repositories/{workspace}/{repo_slug}/pullrequests/{pr_id}/comments",
                json_data=body,
            )
        else:
            project = project_key or self.config.project_key
            if not project:
                raise ValueError("Project key is required for Bitbucket Server/DC")
            body = {
                "text": content,
                "parent": {"id": comment_id},
            }
            return self._request(
                "POST",
                f"/projects/{project}/repos/{repo_slug}/pull-requests/{pr_id}/comments",
                json_data=body,
            )

    def update_comment(
        self,
        repo_slug: str,
        pr_id: int,
        comment_id: int,
        content: str,
        workspace: str | None = None,
        project_key: str | None = None,
    ) -> dict[str, Any]:
        """Update a pull request comment.

        Args:
            repo_slug: Repository slug.
            pr_id: Pull request ID.
            comment_id: Comment ID to update.
            content: New comment text.
            workspace: Workspace slug (Cloud).
            project_key: Project key (Server/DC).

        Returns:
            Updated comment details.
        """
        workspace = workspace or self.config.workspace

        if self.config.is_cloud:
            if not workspace:
                raise ValueError("Workspace is required for Bitbucket Cloud")
            body: dict[str, Any] = {"content": {"raw": content}}
            return self._request(
                "PUT",
                f"/repositories/{workspace}/{repo_slug}/pullrequests/{pr_id}/comments/{comment_id}",
                json_data=body,
            )
        else:
            project = project_key or self.config.project_key
            if not project:
                raise ValueError("Project key is required for Bitbucket Server/DC")
            # Get current version for optimistic locking
            comment = self._request(
                "GET",
                f"/projects/{project}/repos/{repo_slug}/pull-requests/{pr_id}/comments/{comment_id}",
            )
            body = {
                "text": content,
                "version": comment.get("version", 0),
            }
            return self._request(
                "PUT",
                f"/projects/{project}/repos/{repo_slug}/pull-requests/{pr_id}/comments/{comment_id}",
                json_data=body,
            )

    def delete_comment(
        self,
        repo_slug: str,
        pr_id: int,
        comment_id: int,
        workspace: str | None = None,
        project_key: str | None = None,
    ) -> None:
        """Delete a pull request comment.

        Args:
            repo_slug: Repository slug.
            pr_id: Pull request ID.
            comment_id: Comment ID to delete.
            workspace: Workspace slug (Cloud).
            project_key: Project key (Server/DC).
        """
        workspace = workspace or self.config.workspace

        if self.config.is_cloud:
            if not workspace:
                raise ValueError("Workspace is required for Bitbucket Cloud")
            self._request(
                "DELETE",
                f"/repositories/{workspace}/{repo_slug}/pullrequests/{pr_id}/comments/{comment_id}",
            )
        else:
            project = project_key or self.config.project_key
            if not project:
                raise ValueError("Project key is required for Bitbucket Server/DC")
            # Get current version for optimistic locking
            comment = self._request(
                "GET",
                f"/projects/{project}/repos/{repo_slug}/pull-requests/{pr_id}/comments/{comment_id}",
            )
            self._request(
                "DELETE",
                f"/projects/{project}/repos/{repo_slug}/pull-requests/{pr_id}/comments/{comment_id}",
                params={"version": comment.get("version", 0)},
            )

    def list_pull_request_statuses(
        self,
        repo_slug: str,
        pr_id: int,
        workspace: str | None = None,
        project_key: str | None = None,
        max_results: int = 25,
    ) -> list[dict[str, Any]]:
        """List build statuses for a pull request.

        Args:
            repo_slug: Repository slug.
            pr_id: Pull request ID.
            workspace: Workspace slug (Cloud).
            project_key: Project key (Server/DC).
            max_results: Maximum results.

        Returns:
            List of build status objects.
        """
        workspace = workspace or self.config.workspace

        if self.config.is_cloud:
            if not workspace:
                raise ValueError("Workspace is required for Bitbucket Cloud")
            return self._paginate(
                f"/repositories/{workspace}/{repo_slug}/pullrequests/{pr_id}/statuses",
                max_results=max_results,
            )
        else:
            project = project_key or self.config.project_key
            if not project:
                raise ValueError("Project key is required for Bitbucket Server/DC")
            # Server/DC: get merge status which includes build info
            pr = self.get_pull_request(repo_slug, pr_id, project_key=project)
            source_hash = pr.get("fromRef", {}).get("latestCommit") or pr.get(
                "fromRef", {}
            ).get("id", "")
            if source_hash:
                return self._paginate(
                    f"/projects/{project}/repos/{repo_slug}/commits/{source_hash}/builds",
                    max_results=max_results,
                )
            return []

    def get_pull_request_diff(
        self,
        repo_slug: str,
        pr_id: int,
        workspace: str | None = None,
        project_key: str | None = None,
        save_to_file: bool = False,
    ) -> str | dict[str, Any]:
        """Get the diff for a pull request.

        Args:
            repo_slug: Repository slug.
            pr_id: Pull request ID.
            workspace: Workspace slug (Cloud).
            project_key: Project key (Server/DC).
            save_to_file: If True, write the diff to a temp file and return
                          a small metadata dict (file_path, size, lines)
                          instead of the raw diff text.  Avoids flooding the
                          LLM context with large diffs.

        Returns:
            Diff text, or file metadata dict when save_to_file is True.
        """
        workspace = workspace or self.config.workspace

        if self.config.is_cloud:
            if not workspace:
                raise ValueError("Workspace is required for Bitbucket Cloud")
            response = self._http.get(
                self._build_url(
                    f"/repositories/{workspace}/{repo_slug}/pullrequests/{pr_id}/diff"
                ),
            )
            response.raise_for_status()
            diff_text = response.text
        else:
            project = project_key or self.config.project_key
            if not project:
                raise ValueError("Project key is required for Bitbucket Server/DC")
            diff_text = self._request(
                "GET",
                f"/projects/{project}/repos/{repo_slug}/pull-requests/{pr_id}/diff",
            )

        if save_to_file:
            if isinstance(diff_text, dict):
                import json

                diff_text = json.dumps(diff_text, indent=2)
            return self._save_content_to_file(
                content=diff_text,
                prefix=f"bitbucket-pr-{pr_id}-diff",
                suffix=".txt",
            )
        return diff_text

    # ------------------------------------------------------------------
    # Branch operations
    # ------------------------------------------------------------------

    def list_branches(
        self,
        repo_slug: str,
        workspace: str | None = None,
        project_key: str | None = None,
        query: str | None = None,
        max_results: int = 25,
    ) -> list[dict[str, Any]]:
        """List branches for a repository.

        Args:
            repo_slug: Repository slug.
            workspace: Workspace slug (Cloud).
            project_key: Project key (Server/DC).
            query: Filter by branch name.
            max_results: Maximum results.

        Returns:
            List of branch objects.
        """
        workspace = workspace or self.config.workspace
        params: dict[str, Any] = {}

        if self.config.is_cloud:
            if not workspace:
                raise ValueError("Workspace is required for Bitbucket Cloud")
            path = f"/repositories/{workspace}/{repo_slug}/refs/branches"
            if query:
                params["q"] = f'name ~ "{query}"'
        else:
            project = project_key or self.config.project_key
            if not project:
                raise ValueError("Project key is required for Bitbucket Server/DC")
            path = f"/projects/{project}/repos/{repo_slug}/branches"
            if query:
                params["filterText"] = query

        return self._paginate(path, params=params, max_results=max_results)

    def create_branch(
        self,
        repo_slug: str,
        branch_name: str,
        start_point: str,
        workspace: str | None = None,
        project_key: str | None = None,
    ) -> dict[str, Any]:
        """Create a branch.

        Args:
            repo_slug: Repository slug.
            branch_name: New branch name.
            start_point: Commit hash or branch name to branch from.
            workspace: Workspace slug (Cloud).
            project_key: Project key (Server/DC).

        Returns:
            Created branch details.
        """
        workspace = workspace or self.config.workspace

        if self.config.is_cloud:
            if not workspace:
                raise ValueError("Workspace is required for Bitbucket Cloud")
            body = {
                "name": branch_name,
                "target": {"hash": start_point},
            }
            return self._request(
                "POST",
                f"/repositories/{workspace}/{repo_slug}/refs/branches",
                json_data=body,
            )
        else:
            project = project_key or self.config.project_key
            if not project:
                raise ValueError("Project key is required for Bitbucket Server/DC")
            body = {
                "name": branch_name,
                "startPoint": start_point,
            }
            return self._request(
                "POST",
                f"/projects/{project}/repos/{repo_slug}/branches",
                json_data=body,
            )

    def delete_branch(
        self,
        repo_slug: str,
        branch_name: str,
        workspace: str | None = None,
        project_key: str | None = None,
    ) -> None:
        """Delete a branch.

        Args:
            repo_slug: Repository slug.
            branch_name: Branch name to delete.
            workspace: Workspace slug (Cloud).
            project_key: Project key (Server/DC).
        """
        workspace = workspace or self.config.workspace

        if self.config.is_cloud:
            if not workspace:
                raise ValueError("Workspace is required for Bitbucket Cloud")
            self._request(
                "DELETE",
                f"/repositories/{workspace}/{repo_slug}/refs/branches/{branch_name}",
            )
        else:
            project = project_key or self.config.project_key
            if not project:
                raise ValueError("Project key is required for Bitbucket Server/DC")
            self._request(
                "DELETE",
                f"/projects/{project}/repos/{repo_slug}/branches",
                json_data={"name": branch_name},
            )

    def get_branching_model(
        self,
        repo_slug: str,
        workspace: str | None = None,
        project_key: str | None = None,
    ) -> dict[str, Any]:
        """Get the branching model for a repository.

        Args:
            repo_slug: Repository slug.
            workspace: Workspace slug (Cloud).
            project_key: Project key (Server/DC).

        Returns:
            Branching model configuration.
        """
        workspace = workspace or self.config.workspace

        if self.config.is_cloud:
            if not workspace:
                raise ValueError("Workspace is required for Bitbucket Cloud")
            return self._request(
                "GET",
                f"/repositories/{workspace}/{repo_slug}/branching-model",
            )
        else:
            project = project_key or self.config.project_key
            if not project:
                raise ValueError("Project key is required for Bitbucket Server/DC")
            return self._request(
                "GET",
                f"/projects/{project}/repos/{repo_slug}/settings/branching-model",
            )

    def list_branch_restrictions(
        self,
        repo_slug: str,
        workspace: str | None = None,
        project_key: str | None = None,
        max_results: int = 25,
    ) -> list[dict[str, Any]]:
        """List branch restrictions/permissions for a repository.

        Args:
            repo_slug: Repository slug.
            workspace: Workspace slug (Cloud).
            project_key: Project key (Server/DC).
            max_results: Maximum results.

        Returns:
            List of branch restriction objects.
        """
        workspace = workspace or self.config.workspace

        if self.config.is_cloud:
            if not workspace:
                raise ValueError("Workspace is required for Bitbucket Cloud")
            return self._paginate(
                f"/repositories/{workspace}/{repo_slug}/branch-restrictions",
                max_results=max_results,
            )
        else:
            project = project_key or self.config.project_key
            if not project:
                raise ValueError("Project key is required for Bitbucket Server/DC")
            return self._paginate(
                f"/projects/{project}/repos/{repo_slug}/restrictions",
                max_results=max_results,
            )

    # ------------------------------------------------------------------
    # Commit operations
    # ------------------------------------------------------------------

    def list_commits(
        self,
        repo_slug: str,
        workspace: str | None = None,
        project_key: str | None = None,
        branch: str | None = None,
        max_results: int = 25,
    ) -> list[dict[str, Any]]:
        """List commits for a repository.

        Args:
            repo_slug: Repository slug.
            workspace: Workspace slug (Cloud).
            project_key: Project key (Server/DC).
            branch: Branch to list commits from.
            max_results: Maximum results.

        Returns:
            List of commit objects.
        """
        workspace = workspace or self.config.workspace
        params: dict[str, Any] = {}

        if self.config.is_cloud:
            if not workspace:
                raise ValueError("Workspace is required for Bitbucket Cloud")
            path = f"/repositories/{workspace}/{repo_slug}/commits"
            if branch:
                path = f"/repositories/{workspace}/{repo_slug}/commits/{branch}"
        else:
            project = project_key or self.config.project_key
            if not project:
                raise ValueError("Project key is required for Bitbucket Server/DC")
            path = f"/projects/{project}/repos/{repo_slug}/commits"
            if branch:
                params["until"] = branch

        return self._paginate(path, params=params, max_results=max_results)

    def get_commit(
        self,
        repo_slug: str,
        commit_hash: str,
        workspace: str | None = None,
        project_key: str | None = None,
    ) -> dict[str, Any]:
        """Get a single commit.

        Args:
            repo_slug: Repository slug.
            commit_hash: Commit SHA hash.
            workspace: Workspace slug (Cloud).
            project_key: Project key (Server/DC).

        Returns:
            Commit details.
        """
        workspace = workspace or self.config.workspace

        if self.config.is_cloud:
            if not workspace:
                raise ValueError("Workspace is required for Bitbucket Cloud")
            return self._request(
                "GET",
                f"/repositories/{workspace}/{repo_slug}/commit/{commit_hash}",
            )
        else:
            project = project_key or self.config.project_key
            if not project:
                raise ValueError("Project key is required for Bitbucket Server/DC")
            return self._request(
                "GET",
                f"/projects/{project}/repos/{repo_slug}/commits/{commit_hash}",
            )

    def compare_commits(
        self,
        repo_slug: str,
        source: str,
        destination: str,
        workspace: str | None = None,
        project_key: str | None = None,
    ) -> dict[str, Any]:
        """Compare two commits or refs (branches/tags).

        Args:
            repo_slug: Repository slug.
            source: Source commit hash, branch, or tag.
            destination: Destination commit hash, branch, or tag.
            workspace: Workspace slug (Cloud).
            project_key: Project key (Server/DC).

        Returns:
            Comparison details with diff stats.
        """
        workspace = workspace or self.config.workspace

        if self.config.is_cloud:
            if not workspace:
                raise ValueError("Workspace is required for Bitbucket Cloud")
            return self._request(
                "GET",
                f"/repositories/{workspace}/{repo_slug}/diff/{source}..{destination}",
            )
        else:
            project = project_key or self.config.project_key
            if not project:
                raise ValueError("Project key is required for Bitbucket Server/DC")
            return self._request(
                "GET",
                f"/projects/{project}/repos/{repo_slug}/compare/diff",
                params={"from": source, "to": destination},
            )

    def list_commit_statuses(
        self,
        repo_slug: str,
        commit_hash: str,
        workspace: str | None = None,
        project_key: str | None = None,
        max_results: int = 25,
    ) -> list[dict[str, Any]]:
        """List build statuses for a specific commit.

        Args:
            repo_slug: Repository slug.
            commit_hash: Commit SHA hash.
            workspace: Workspace slug (Cloud).
            project_key: Project key (Server/DC).
            max_results: Maximum results.

        Returns:
            List of build status objects.
        """
        workspace = workspace or self.config.workspace

        if self.config.is_cloud:
            if not workspace:
                raise ValueError("Workspace is required for Bitbucket Cloud")
            return self._paginate(
                f"/repositories/{workspace}/{repo_slug}/commit/{commit_hash}/statuses",
                max_results=max_results,
            )
        else:
            project = project_key or self.config.project_key
            if not project:
                raise ValueError("Project key is required for Bitbucket Server/DC")
            return self._paginate(
                f"/projects/{project}/repos/{repo_slug}/commits/{commit_hash}/builds",
                max_results=max_results,
            )

    def create_commit_status(
        self,
        repo_slug: str,
        commit_hash: str,
        state: str,
        key: str,
        url: str,
        workspace: str | None = None,
        project_key: str | None = None,
        name: str = "",
        description: str = "",
    ) -> dict[str, Any]:
        """Create a build status for a commit.

        Args:
            repo_slug: Repository slug.
            commit_hash: Commit SHA hash.
            state: Build state (SUCCESSFUL, FAILED, INPROGRESS, STOPPED).
            key: Unique key for this build status.
            url: URL for the build.
            workspace: Workspace slug (Cloud).
            project_key: Project key (Server/DC).
            name: Display name for the build.
            description: Build description.

        Returns:
            Created build status details.
        """
        workspace = workspace or self.config.workspace
        body: dict[str, Any] = {
            "state": state,
            "key": key,
            "url": url,
        }
        if name:
            body["name"] = name
        if description:
            body["description"] = description

        if self.config.is_cloud:
            if not workspace:
                raise ValueError("Workspace is required for Bitbucket Cloud")
            return self._request(
                "POST",
                f"/repositories/{workspace}/{repo_slug}/commit/{commit_hash}/statuses/build",
                json_data=body,
            )
        else:
            project = project_key or self.config.project_key
            if not project:
                raise ValueError("Project key is required for Bitbucket Server/DC")
            return self._request(
                "POST",
                f"/projects/{project}/repos/{repo_slug}/commits/{commit_hash}/builds",
                json_data=body,
            )

    def add_commit_comment(
        self,
        repo_slug: str,
        commit_hash: str,
        content: str,
        workspace: str | None = None,
        project_key: str | None = None,
    ) -> dict[str, Any]:
        """Add a comment to a commit.

        Args:
            repo_slug: Repository slug.
            commit_hash: Commit SHA hash.
            content: Comment text.
            workspace: Workspace slug (Cloud).
            project_key: Project key (Server/DC).

        Returns:
            Created comment details.
        """
        workspace = workspace or self.config.workspace

        if self.config.is_cloud:
            if not workspace:
                raise ValueError("Workspace is required for Bitbucket Cloud")
            body: dict[str, Any] = {"content": {"raw": content}}
            return self._request(
                "POST",
                f"/repositories/{workspace}/{repo_slug}/commit/{commit_hash}/comments",
                json_data=body,
            )
        else:
            project = project_key or self.config.project_key
            if not project:
                raise ValueError("Project key is required for Bitbucket Server/DC")
            body = {"text": content}
            return self._request(
                "POST",
                f"/projects/{project}/repos/{repo_slug}/commits/{commit_hash}/comments",
                json_data=body,
            )

    # ------------------------------------------------------------------
    # Tag operations
    # ------------------------------------------------------------------

    def list_tags(
        self,
        repo_slug: str,
        workspace: str | None = None,
        project_key: str | None = None,
        max_results: int = 25,
    ) -> list[dict[str, Any]]:
        """List tags for a repository.

        Args:
            repo_slug: Repository slug.
            workspace: Workspace slug (Cloud).
            project_key: Project key (Server/DC).
            max_results: Maximum results.

        Returns:
            List of tag objects.
        """
        workspace = workspace or self.config.workspace

        if self.config.is_cloud:
            if not workspace:
                raise ValueError("Workspace is required for Bitbucket Cloud")
            path = f"/repositories/{workspace}/{repo_slug}/refs/tags"
        else:
            project = project_key or self.config.project_key
            if not project:
                raise ValueError("Project key is required for Bitbucket Server/DC")
            path = f"/projects/{project}/repos/{repo_slug}/tags"

        return self._paginate(path, max_results=max_results)

    def create_tag(
        self,
        repo_slug: str,
        tag_name: str,
        target_hash: str,
        message: str = "",
        workspace: str | None = None,
        project_key: str | None = None,
    ) -> dict[str, Any]:
        """Create a tag.

        Args:
            repo_slug: Repository slug.
            tag_name: Tag name.
            target_hash: Commit hash to tag.
            message: Tag message.
            workspace: Workspace slug (Cloud).
            project_key: Project key (Server/DC).

        Returns:
            Created tag details.
        """
        workspace = workspace or self.config.workspace

        if self.config.is_cloud:
            if not workspace:
                raise ValueError("Workspace is required for Bitbucket Cloud")
            body = {
                "name": tag_name,
                "target": {"hash": target_hash},
            }
            if message:
                body["message"] = message
            return self._request(
                "POST",
                f"/repositories/{workspace}/{repo_slug}/refs/tags",
                json_data=body,
            )
        else:
            project = project_key or self.config.project_key
            if not project:
                raise ValueError("Project key is required for Bitbucket Server/DC")
            body = {
                "name": tag_name,
                "startPoint": target_hash,
                "message": message,
            }
            return self._request(
                "POST",
                f"/projects/{project}/repos/{repo_slug}/tags",
                json_data=body,
            )

    def delete_tag(
        self,
        repo_slug: str,
        tag_name: str,
        workspace: str | None = None,
        project_key: str | None = None,
    ) -> None:
        """Delete a tag.

        Args:
            repo_slug: Repository slug.
            tag_name: Tag name to delete.
            workspace: Workspace slug (Cloud).
            project_key: Project key (Server/DC).
        """
        workspace = workspace or self.config.workspace

        if self.config.is_cloud:
            if not workspace:
                raise ValueError("Workspace is required for Bitbucket Cloud")
            self._request(
                "DELETE",
                f"/repositories/{workspace}/{repo_slug}/refs/tags/{tag_name}",
            )
        else:
            project = project_key or self.config.project_key
            if not project:
                raise ValueError("Project key is required for Bitbucket Server/DC")
            self._request(
                "DELETE",
                f"/projects/{project}/repos/{repo_slug}/tags/{tag_name}",
            )

    # ------------------------------------------------------------------
    # File/Source operations
    # ------------------------------------------------------------------

    def get_file_content(
        self,
        repo_slug: str,
        file_path: str,
        ref: str | None = None,
        workspace: str | None = None,
        project_key: str | None = None,
    ) -> str:
        """Get file content from a repository.

        Args:
            repo_slug: Repository slug.
            file_path: Path to the file.
            ref: Branch, tag, or commit hash (defaults to default branch).
            workspace: Workspace slug (Cloud).
            project_key: Project key (Server/DC).

        Returns:
            File content as string.
        """
        workspace = workspace or self.config.workspace
        params: dict[str, Any] = {}

        if self.config.is_cloud:
            if not workspace:
                raise ValueError("Workspace is required for Bitbucket Cloud")
            path = f"/repositories/{workspace}/{repo_slug}/src"
            if ref:
                path = f"{path}/{ref}/{file_path}"
            else:
                path = f"{path}/HEAD/{file_path}"
            response = self._http.get(self._build_url(path), params=params)
            response.raise_for_status()
            return response.text
        else:
            project = project_key or self.config.project_key
            if not project:
                raise ValueError("Project key is required for Bitbucket Server/DC")
            path = f"/projects/{project}/repos/{repo_slug}/browse/{file_path}"
            if ref:
                params["at"] = ref
            data = self._request("GET", path, params=params)
            # Server returns lines array
            if isinstance(data, dict) and "lines" in data:
                return "\n".join(line.get("text", "") for line in data["lines"])
            return str(data)

    def browse_directory(
        self,
        repo_slug: str,
        path: str = "",
        ref: str | None = None,
        workspace: str | None = None,
        project_key: str | None = None,
        max_results: int = 100,
    ) -> list[dict[str, Any]]:
        """Browse directory contents in a repository.

        Args:
            repo_slug: Repository slug.
            path: Directory path (empty for root).
            ref: Branch, tag, or commit hash.
            workspace: Workspace slug (Cloud).
            project_key: Project key (Server/DC).
            max_results: Maximum results.

        Returns:
            List of file/directory entry objects.
        """
        workspace = workspace or self.config.workspace
        params: dict[str, Any] = {}

        if self.config.is_cloud:
            if not workspace:
                raise ValueError("Workspace is required for Bitbucket Cloud")
            src_path = f"/repositories/{workspace}/{repo_slug}/src"
            if ref:
                src_path = f"{src_path}/{ref}/{path}" if path else f"{src_path}/{ref}/"
            else:
                src_path = f"{src_path}/HEAD/{path}" if path else f"{src_path}/HEAD/"
            return self._paginate(src_path, params=params, max_results=max_results)
        else:
            project = project_key or self.config.project_key
            if not project:
                raise ValueError("Project key is required for Bitbucket Server/DC")
            browse_path = f"/projects/{project}/repos/{repo_slug}/browse"
            if path:
                browse_path = f"{browse_path}/{path}"
            if ref:
                params["at"] = ref
            data = self._request("GET", browse_path, params=params)
            # Server returns children.values or files.values
            if isinstance(data, dict):
                children = data.get("children", {})
                return children.get("values", [])[:max_results]
            return []

    def search_code(
        self,
        query: str,
        repo_slug: str | None = None,
        workspace: str | None = None,
        project_key: str | None = None,
        max_results: int = 25,
    ) -> list[dict[str, Any]]:
        """Search for code in repositories.

        Args:
            query: Search query string.
            repo_slug: Optional repository slug to limit search.
            workspace: Workspace slug (Cloud).
            project_key: Project key (Server/DC).
            max_results: Maximum results.

        Returns:
            List of search result objects.
        """
        workspace = workspace or self.config.workspace
        params: dict[str, Any] = {"search_query": query}

        if self.config.is_cloud:
            if not workspace:
                raise ValueError("Workspace is required for Bitbucket Cloud")
            if repo_slug:
                path = f"/repositories/{workspace}/{repo_slug}/search/code"
            else:
                path = f"/workspaces/{workspace}/search/code"
            return self._paginate(path, params=params, max_results=max_results)
        else:
            project = project_key or self.config.project_key
            if not project:
                raise ValueError("Project key is required for Bitbucket Server/DC")
            # Server/DC code search requires the code-search plugin
            search_params: dict[str, Any] = {"query": query, "type": "content"}
            if repo_slug:
                search_params["repository"] = repo_slug
            search_params["project"] = project
            return self._paginate(
                "/search",
                params=search_params,
                max_results=max_results,
            )

    def get_file_blame(
        self,
        repo_slug: str,
        file_path: str,
        ref: str | None = None,
        workspace: str | None = None,
        project_key: str | None = None,
    ) -> Any:
        """Get blame information for a file.

        Args:
            repo_slug: Repository slug.
            file_path: Path to the file.
            ref: Branch, tag, or commit hash.
            workspace: Workspace slug (Cloud).
            project_key: Project key (Server/DC).

        Returns:
            Blame data with line-by-line authorship.
        """
        workspace = workspace or self.config.workspace
        params: dict[str, Any] = {}

        if self.config.is_cloud:
            if not workspace:
                raise ValueError("Workspace is required for Bitbucket Cloud")
            # Cloud: annotation endpoint for blame
            path = f"/repositories/{workspace}/{repo_slug}/src"
            if ref:
                path = f"{path}/{ref}/{file_path}"
            else:
                path = f"{path}/HEAD/{file_path}"
            params["annotate"] = "true"
            return self._request("GET", path, params=params)
        else:
            project = project_key or self.config.project_key
            if not project:
                raise ValueError("Project key is required for Bitbucket Server/DC")
            path = f"/projects/{project}/repos/{repo_slug}/browse/{file_path}"
            if ref:
                params["at"] = ref
            params["blame"] = ""
            return self._request("GET", path, params=params)

    def get_file_history(
        self,
        repo_slug: str,
        file_path: str,
        ref: str | None = None,
        workspace: str | None = None,
        project_key: str | None = None,
        max_results: int = 25,
    ) -> list[dict[str, Any]]:
        """Get commit history for a specific file.

        Args:
            repo_slug: Repository slug.
            file_path: Path to the file.
            ref: Branch, tag, or commit hash.
            workspace: Workspace slug (Cloud).
            project_key: Project key (Server/DC).
            max_results: Maximum results.

        Returns:
            List of commits that modified the file.
        """
        workspace = workspace or self.config.workspace
        params: dict[str, Any] = {"path": file_path}

        if self.config.is_cloud:
            if not workspace:
                raise ValueError("Workspace is required for Bitbucket Cloud")
            path = f"/repositories/{workspace}/{repo_slug}/filehistory"
            if ref:
                path = f"{path}/{ref}/{file_path}"
            else:
                path = f"{path}/HEAD/{file_path}"
            # filehistory endpoint doesn't use path param, it's in the URL
            return self._paginate(path, max_results=max_results)
        else:
            project = project_key or self.config.project_key
            if not project:
                raise ValueError("Project key is required for Bitbucket Server/DC")
            commit_path = f"/projects/{project}/repos/{repo_slug}/commits"
            if ref:
                params["until"] = ref
            return self._paginate(commit_path, params=params, max_results=max_results)

    # ------------------------------------------------------------------
    # Webhook operations (Cloud only)
    # ------------------------------------------------------------------

    def list_webhooks(
        self,
        repo_slug: str,
        workspace: str | None = None,
        project_key: str | None = None,
    ) -> list[dict[str, Any]]:
        """List webhooks for a repository.

        Args:
            repo_slug: Repository slug.
            workspace: Workspace slug (Cloud).
            project_key: Project key (Server/DC).

        Returns:
            List of webhook objects.
        """
        workspace = workspace or self.config.workspace

        if self.config.is_cloud:
            if not workspace:
                raise ValueError("Workspace is required for Bitbucket Cloud")
            return self._paginate(
                f"/repositories/{workspace}/{repo_slug}/hooks",
            )
        else:
            project = project_key or self.config.project_key
            if not project:
                raise ValueError("Project key is required for Bitbucket Server/DC")
            return self._paginate(
                f"/projects/{project}/repos/{repo_slug}/webhooks",
            )

    def create_webhook(
        self,
        repo_slug: str,
        url: str,
        events: list[str],
        description: str = "",
        active: bool = True,
        workspace: str | None = None,
        project_key: str | None = None,
    ) -> dict[str, Any]:
        """Create a webhook.

        Args:
            repo_slug: Repository slug.
            url: Webhook URL.
            events: List of event types to trigger on.
            description: Webhook description.
            active: Whether the webhook is active.
            workspace: Workspace slug (Cloud).
            project_key: Project key (Server/DC).

        Returns:
            Created webhook details.
        """
        workspace = workspace or self.config.workspace

        if self.config.is_cloud:
            if not workspace:
                raise ValueError("Workspace is required for Bitbucket Cloud")
            body = {
                "description": description,
                "url": url,
                "active": active,
                "events": events,
            }
            return self._request(
                "POST",
                f"/repositories/{workspace}/{repo_slug}/hooks",
                json_data=body,
            )
        else:
            project = project_key or self.config.project_key
            if not project:
                raise ValueError("Project key is required for Bitbucket Server/DC")
            body = {
                "name": description,
                "url": url,
                "active": active,
                "events": events,
            }
            return self._request(
                "POST",
                f"/projects/{project}/repos/{repo_slug}/webhooks",
                json_data=body,
            )

    def update_webhook(
        self,
        repo_slug: str,
        webhook_id: str,
        workspace: str | None = None,
        project_key: str | None = None,
        url: str | None = None,
        events: list[str] | None = None,
        description: str | None = None,
        active: bool | None = None,
    ) -> dict[str, Any]:
        """Update a webhook.

        Args:
            repo_slug: Repository slug.
            webhook_id: Webhook UUID (Cloud) or ID (Server).
            workspace: Workspace slug (Cloud).
            project_key: Project key (Server/DC).
            url: New webhook URL.
            events: New event list.
            description: New description.
            active: Enable/disable webhook.

        Returns:
            Updated webhook details.
        """
        workspace = workspace or self.config.workspace
        body: dict[str, Any] = {}
        if url is not None:
            body["url"] = url
        if active is not None:
            body["active"] = active

        if self.config.is_cloud:
            if not workspace:
                raise ValueError("Workspace is required for Bitbucket Cloud")
            if events is not None:
                body["events"] = events
            if description is not None:
                body["description"] = description
            return self._request(
                "PUT",
                f"/repositories/{workspace}/{repo_slug}/hooks/{webhook_id}",
                json_data=body,
            )
        else:
            project = project_key or self.config.project_key
            if not project:
                raise ValueError("Project key is required for Bitbucket Server/DC")
            if events is not None:
                body["events"] = events
            if description is not None:
                body["name"] = description
            return self._request(
                "PUT",
                f"/projects/{project}/repos/{repo_slug}/webhooks/{webhook_id}",
                json_data=body,
            )

    def delete_webhook(
        self,
        repo_slug: str,
        webhook_id: str,
        workspace: str | None = None,
        project_key: str | None = None,
    ) -> None:
        """Delete a webhook.

        Args:
            repo_slug: Repository slug.
            webhook_id: Webhook UUID (Cloud) or ID (Server).
            workspace: Workspace slug (Cloud).
            project_key: Project key (Server/DC).
        """
        workspace = workspace or self.config.workspace

        if self.config.is_cloud:
            if not workspace:
                raise ValueError("Workspace is required for Bitbucket Cloud")
            self._request(
                "DELETE",
                f"/repositories/{workspace}/{repo_slug}/hooks/{webhook_id}",
            )
        else:
            project = project_key or self.config.project_key
            if not project:
                raise ValueError("Project key is required for Bitbucket Server/DC")
            self._request(
                "DELETE",
                f"/projects/{project}/repos/{repo_slug}/webhooks/{webhook_id}",
            )

    # ------------------------------------------------------------------
    # Pipeline operations (Cloud only)
    # ------------------------------------------------------------------

    def _require_cloud(self, operation: str) -> None:
        """Raise error if not connected to Cloud."""
        if not self.config.is_cloud:
            raise ValueError(f"{operation} is only available on Bitbucket Cloud")

    def list_pipelines(
        self,
        repo_slug: str,
        workspace: str | None = None,
        max_results: int = 25,
    ) -> list[dict[str, Any]]:
        """List pipeline runs for a repository (Cloud only).

        Args:
            repo_slug: Repository slug.
            workspace: Workspace slug.
            max_results: Maximum results.

        Returns:
            List of pipeline run objects.
        """
        self._require_cloud("list_pipelines")
        ws = workspace or self.config.workspace
        if not ws:
            raise ValueError("Workspace is required for Bitbucket Cloud")
        return self._paginate(
            f"/repositories/{ws}/{repo_slug}/pipelines",
            params={"sort": "-created_on"},
            max_results=max_results,
        )

    def get_pipeline(
        self,
        repo_slug: str,
        pipeline_uuid: str,
        workspace: str | None = None,
    ) -> dict[str, Any]:
        """Get a specific pipeline run (Cloud only).

        Args:
            repo_slug: Repository slug.
            pipeline_uuid: Pipeline UUID.
            workspace: Workspace slug.

        Returns:
            Pipeline run details.
        """
        self._require_cloud("get_pipeline")
        ws = workspace or self.config.workspace
        if not ws:
            raise ValueError("Workspace is required for Bitbucket Cloud")
        return self._request(
            "GET",
            f"/repositories/{ws}/{repo_slug}/pipelines/{pipeline_uuid}",
        )

    def trigger_pipeline(
        self,
        repo_slug: str,
        branch: str,
        workspace: str | None = None,
        variables: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Trigger a new pipeline run (Cloud only).

        Args:
            repo_slug: Repository slug.
            branch: Branch to run pipeline on.
            workspace: Workspace slug.
            variables: Pipeline variables as key-value pairs.

        Returns:
            Triggered pipeline run details.
        """
        self._require_cloud("trigger_pipeline")
        ws = workspace or self.config.workspace
        if not ws:
            raise ValueError("Workspace is required for Bitbucket Cloud")
        body: dict[str, Any] = {
            "target": {
                "type": "pipeline_ref_target",
                "ref_type": "branch",
                "ref_name": branch,
            }
        }
        if variables:
            body["variables"] = [{"key": k, "value": v} for k, v in variables.items()]
        return self._request(
            "POST",
            f"/repositories/{ws}/{repo_slug}/pipelines",
            json_data=body,
        )

    def stop_pipeline(
        self,
        repo_slug: str,
        pipeline_uuid: str,
        workspace: str | None = None,
    ) -> None:
        """Stop a running pipeline (Cloud only).

        Args:
            repo_slug: Repository slug.
            pipeline_uuid: Pipeline UUID.
            workspace: Workspace slug.
        """
        self._require_cloud("stop_pipeline")
        ws = workspace or self.config.workspace
        if not ws:
            raise ValueError("Workspace is required for Bitbucket Cloud")
        self._request(
            "POST",
            f"/repositories/{ws}/{repo_slug}/pipelines/{pipeline_uuid}/stopPipeline",
        )

    def get_pipeline_step_log(
        self,
        repo_slug: str,
        pipeline_uuid: str,
        step_uuid: str,
        workspace: str | None = None,
    ) -> str:
        """Get log output for a pipeline step (Cloud only).

        Args:
            repo_slug: Repository slug.
            pipeline_uuid: Pipeline UUID.
            step_uuid: Step UUID.
            workspace: Workspace slug.

        Returns:
            Log output as text.
        """
        self._require_cloud("get_pipeline_step_log")
        ws = workspace or self.config.workspace
        if not ws:
            raise ValueError("Workspace is required for Bitbucket Cloud")
        response = self._http.get(
            self._build_url(
                f"/repositories/{ws}/{repo_slug}/pipelines/{pipeline_uuid}"
                f"/steps/{step_uuid}/log"
            ),
        )
        response.raise_for_status()
        return response.text

    def list_pipeline_variables(
        self,
        repo_slug: str,
        workspace: str | None = None,
        max_results: int = 25,
    ) -> list[dict[str, Any]]:
        """List pipeline variables for a repository (Cloud only).

        Args:
            repo_slug: Repository slug.
            workspace: Workspace slug.
            max_results: Maximum results.

        Returns:
            List of pipeline variable objects.
        """
        self._require_cloud("list_pipeline_variables")
        ws = workspace or self.config.workspace
        if not ws:
            raise ValueError("Workspace is required for Bitbucket Cloud")
        return self._paginate(
            f"/repositories/{ws}/{repo_slug}/pipelines_config/variables",
            max_results=max_results,
        )

    def create_pipeline_variable(
        self,
        repo_slug: str,
        key: str,
        value: str,
        secured: bool = False,
        workspace: str | None = None,
    ) -> dict[str, Any]:
        """Create a pipeline variable (Cloud only).

        Args:
            repo_slug: Repository slug.
            key: Variable key.
            value: Variable value.
            secured: Whether the variable is encrypted.
            workspace: Workspace slug.

        Returns:
            Created variable details.
        """
        self._require_cloud("create_pipeline_variable")
        ws = workspace or self.config.workspace
        if not ws:
            raise ValueError("Workspace is required for Bitbucket Cloud")
        body = {"key": key, "value": value, "secured": secured}
        return self._request(
            "POST",
            f"/repositories/{ws}/{repo_slug}/pipelines_config/variables",
            json_data=body,
        )

    def get_pipeline_config(
        self,
        repo_slug: str,
        workspace: str | None = None,
    ) -> dict[str, Any]:
        """Get pipeline configuration for a repository (Cloud only).

        Args:
            repo_slug: Repository slug.
            workspace: Workspace slug.

        Returns:
            Pipeline configuration details.
        """
        self._require_cloud("get_pipeline_config")
        ws = workspace or self.config.workspace
        if not ws:
            raise ValueError("Workspace is required for Bitbucket Cloud")
        return self._request(
            "GET",
            f"/repositories/{ws}/{repo_slug}/pipelines_config",
        )

    # ------------------------------------------------------------------
    # Deployment operations (Cloud only)
    # ------------------------------------------------------------------

    def list_environments(
        self,
        repo_slug: str,
        workspace: str | None = None,
    ) -> list[dict[str, Any]]:
        """List deployment environments (Cloud only).

        Args:
            repo_slug: Repository slug.
            workspace: Workspace slug.

        Returns:
            List of environment objects.
        """
        self._require_cloud("list_environments")
        ws = workspace or self.config.workspace
        if not ws:
            raise ValueError("Workspace is required for Bitbucket Cloud")
        return self._paginate(
            f"/repositories/{ws}/{repo_slug}/environments",
        )

    def get_deployment(
        self,
        repo_slug: str,
        environment_uuid: str,
        workspace: str | None = None,
    ) -> dict[str, Any]:
        """Get deployment details for an environment (Cloud only).

        Args:
            repo_slug: Repository slug.
            environment_uuid: Environment UUID.
            workspace: Workspace slug.

        Returns:
            Latest deployment details for the environment.
        """
        self._require_cloud("get_deployment")
        ws = workspace or self.config.workspace
        if not ws:
            raise ValueError("Workspace is required for Bitbucket Cloud")
        return self._request(
            "GET",
            f"/repositories/{ws}/{repo_slug}/environments/{environment_uuid}",
        )

    def list_deployment_releases(
        self,
        repo_slug: str,
        environment_uuid: str,
        workspace: str | None = None,
        max_results: int = 25,
    ) -> list[dict[str, Any]]:
        """List deployment releases for an environment (Cloud only).

        Args:
            repo_slug: Repository slug.
            environment_uuid: Environment UUID.
            workspace: Workspace slug.
            max_results: Maximum results.

        Returns:
            List of deployment release objects.
        """
        self._require_cloud("list_deployment_releases")
        ws = workspace or self.config.workspace
        if not ws:
            raise ValueError("Workspace is required for Bitbucket Cloud")
        return self._paginate(
            f"/repositories/{ws}/{repo_slug}/deployments",
            params={"environment": environment_uuid},
            max_results=max_results,
        )

    # ------------------------------------------------------------------
    # Workspace/Project operations
    # ------------------------------------------------------------------

    def list_workspaces(
        self,
        max_results: int = 25,
    ) -> list[dict[str, Any]]:
        """List workspaces (Cloud) or projects (Server/DC).

        Args:
            max_results: Maximum results.

        Returns:
            List of workspace/project objects.
        """
        if self.config.is_cloud:
            return self._paginate("/workspaces", max_results=max_results)
        else:
            return self._paginate("/projects", max_results=max_results)

    def get_workspace(
        self,
        workspace: str | None = None,
        project_key: str | None = None,
    ) -> dict[str, Any]:
        """Get workspace (Cloud) or project (Server/DC) details.

        Args:
            workspace: Workspace slug (Cloud).
            project_key: Project key (Server/DC).

        Returns:
            Workspace/project details.
        """
        if self.config.is_cloud:
            ws = workspace or self.config.workspace
            if not ws:
                raise ValueError("Workspace is required for Bitbucket Cloud")
            return self._request("GET", f"/workspaces/{ws}")
        else:
            project = project_key or self.config.project_key
            if not project:
                raise ValueError("Project key is required for Bitbucket Server/DC")
            return self._request("GET", f"/projects/{project}")

    def list_workspace_members(
        self,
        workspace: str | None = None,
        project_key: str | None = None,
        max_results: int = 25,
    ) -> list[dict[str, Any]]:
        """List workspace members (Cloud) or project permissions (Server/DC).

        Args:
            workspace: Workspace slug (Cloud).
            project_key: Project key (Server/DC).
            max_results: Maximum results.

        Returns:
            List of member/permission objects.
        """
        if self.config.is_cloud:
            ws = workspace or self.config.workspace
            if not ws:
                raise ValueError("Workspace is required for Bitbucket Cloud")
            return self._paginate(
                f"/workspaces/{ws}/members",
                max_results=max_results,
            )
        else:
            project = project_key or self.config.project_key
            if not project:
                raise ValueError("Project key is required for Bitbucket Server/DC")
            return self._paginate(
                f"/projects/{project}/permissions/users",
                max_results=max_results,
            )

    def get_default_reviewers(
        self,
        repo_slug: str,
        workspace: str | None = None,
        project_key: str | None = None,
    ) -> list[dict[str, Any]]:
        """Get default reviewers for a repository.

        Args:
            repo_slug: Repository slug.
            workspace: Workspace slug (Cloud).
            project_key: Project key (Server/DC).

        Returns:
            List of default reviewer objects.
        """
        workspace = workspace or self.config.workspace

        if self.config.is_cloud:
            if not workspace:
                raise ValueError("Workspace is required for Bitbucket Cloud")
            return self._paginate(
                f"/repositories/{workspace}/{repo_slug}/default-reviewers",
            )
        else:
            project = project_key or self.config.project_key
            if not project:
                raise ValueError("Project key is required for Bitbucket Server/DC")
            return self._paginate(
                f"/projects/{project}/repos/{repo_slug}/conditions",
            )

    def add_default_reviewer(
        self,
        repo_slug: str,
        username: str,
        workspace: str | None = None,
        project_key: str | None = None,
    ) -> dict[str, Any]:
        """Add a default reviewer to a repository.

        Args:
            repo_slug: Repository slug.
            username: Username or UUID of the reviewer.
            workspace: Workspace slug (Cloud).
            project_key: Project key (Server/DC).

        Returns:
            Added reviewer details.
        """
        workspace = workspace or self.config.workspace

        if self.config.is_cloud:
            if not workspace:
                raise ValueError("Workspace is required for Bitbucket Cloud")
            return self._request(
                "PUT",
                f"/repositories/{workspace}/{repo_slug}/default-reviewers/{username}",
            )
        else:
            project = project_key or self.config.project_key
            if not project:
                raise ValueError("Project key is required for Bitbucket Server/DC")
            body = {
                "reviewers": [{"name": username}],
                "sourceMatcher": {"id": "any", "type": {"id": "ANY_REF"}},
                "targetMatcher": {"id": "any", "type": {"id": "ANY_REF"}},
                "requiredApprovals": 0,
            }
            return self._request(
                "POST",
                f"/projects/{project}/repos/{repo_slug}/conditions",
                json_data=body,
            )
