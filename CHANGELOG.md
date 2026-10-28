# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased] — Bitbucket Integration

### Added

**Structured Identity Privacy (opt-in)**

- Final FastMCP response guard for Jira, Confluence, and Bitbucket structured
  identities, disabled by default
- Configurable anonymization or UTC-rotating HMAC pseudonymization with
  deployment-, connector-, or instance-scoped correlation
- Private policy file for affiliation, human/service classification, service
  clear-text exceptions, and selected Jira custom text fields
- Request-local self-identification, explicit raw/mixed response policies, and
  fail-closed transformation behavior
- Optional caller- and tenant-bound alias roundtrip for Jira assignee/watcher
  and Bitbucket reviewer writes, with epoch expiry and fail-closed rejection
- Versioned pseudonym keyring with one active key, bounded predecessor
  acceptance, `pid:v2` key IDs, and controlled key retirement
- Reproducible German/English free-text PII/NER evaluation and public synthetic
  Golden Set; general text scanning remains disabled because measured
  precision/recall did not meet the release gates
- Historical identity-log inventory and controlled retention/purge runbook;
  no production deletion is performed without CISO/DPO and operations approval

**Bitbucket Cloud & Server/DC Support (64 tools)**

- **Bitbucket client** (`bitbucket/client.py`) — Unified client supporting both Cloud (API 2.0) and Server/Data Center (API 1.0) with automatic platform detection
- **Authentication** — App passwords (Cloud), Personal Access Tokens (Server/DC), OAuth 2.0, and basic auth
- **Retry middleware** — Exponential backoff (3 attempts) for 429 rate limits and 5xx server errors with `Retry-After` header support
- **Connection pooling** — httpx with configurable limits (20 max connections, 10 keepalive)

**Repository Tools (7)**
- `list_repositories`, `get_repository`, `create_repository`, `update_repository`, `delete_repository`, `fork_repository`, `list_forks`

**Pull Request Tools (15)**
- `list_pull_requests` with server-side filtering (state, author, reviewer, branch)
- `get_pull_request`, `get_pull_request_diff` (paginated), `create_pull_request`
- `update_pull_request`, `merge_pull_request`, `decline_pull_request`
- `approve_pull_request`, `unapprove_pull_request`, `request_changes_pull_request`
- `get_pull_request_commits`, `list_pull_request_comments`, `list_pull_request_statuses`
- `add_pull_request_comment`, `add_inline_comment`

**PR Comment Tools (3)**
- `reply_to_comment`, `update_comment`, `delete_comment`

**Branch Tools (5)**
- `list_branches`, `create_branch`, `delete_branch`, `get_branching_model`, `list_branch_restrictions`

**Commit Tools (6)**
- `list_commits`, `get_commit`, `compare_commits`, `list_commit_statuses`, `create_commit_status`, `add_commit_comment`

**Source Browsing Tools (5)**
- `get_file_content` (with line range support), `browse_directory`, `search_code`, `get_file_blame`, `get_file_history`

**Tag Tools (3)**
- `list_tags`, `create_tag`, `delete_tag`

**Webhook Tools (4)**
- `list_webhooks`, `create_webhook`, `update_webhook`, `delete_webhook`

**Pipeline Tools — Cloud only (8)**
- `list_pipelines`, `get_pipeline`, `trigger_pipeline`, `stop_pipeline`
- `get_pipeline_step_log`, `list_pipeline_variables`, `create_pipeline_variable`, `get_pipeline_config`

**Deployment Tools — Cloud only (3)**
- `list_environments`, `get_deployment`, `list_deployment_releases`

**Workspace Tools (5)**
- `list_workspaces`, `get_workspace`, `list_workspace_members`, `get_default_reviewers`, `add_default_reviewer`

**Toolset System**
- 12 Bitbucket toolsets (5 default, 7 opt-in) integrated into existing toolset filtering
- Total: 33 toolsets across Jira (15), Confluence (6), and Bitbucket (12)
- Cloud-only toolsets (`bitbucket_pipelines`, `bitbucket_deployments`) with clear Server/DC error messages

### Fixed

- Identity privacy: Bitbucket blame and compare responses are parsed, so author
  and committer identities are pseudonymized instead of passing through as text
- Identity privacy: Confluence page mentions, profile macros, and Jira mentions use
  the pseudonymous alias or a neutral placeholder; no REST name lookup in privacy mode
- Identity privacy: Jira component lead and real assignee logins are pseudonymized
- Identity privacy: /healthz reports identity_privacy (off, anonymize or pseudonymize); the startup log shows mode, correlation scope and rotation without key material

### Changed

- Identity privacy: tool errors are returned and logged completely (exception
  class, message and, for known classes, a remedy hint) instead of being reduced
  to the exception type; response data stays pseudonymized. Set
  `IDENTITY_PRIVACY_REDACT_ERRORS=true` to restore the redacted error texts
- Renamed distribution, CLI, and Python import package to
  `mcp-atlassian-with-bitbucket-and-privacy`; retained the existing GitHub
  repository identity
- Existing OAuth tokens remain readable from the pre-rename keyring service
  and fallback directory
- Added `httpx` dependency for Bitbucket API communication
- Extended `MainAppContext` to include `BitbucketConfig`
- Updated `ALL_TOOLSETS` count from 21 to 33
- Updated `DEFAULT_TOOLSETS` count from 6 to 11

---

*Based on [sooperset/mcp-atlassian](https://github.com/sooperset/mcp-atlassian) — original Jira and Confluence functionality preserved.*
