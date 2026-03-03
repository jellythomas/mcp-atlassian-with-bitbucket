# MCP Atlassian + Bitbucket

![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![License](https://img.shields.io/github/license/sooperset/mcp-atlassian)

Model Context Protocol (MCP) server for Atlassian products — **Jira**, **Confluence**, and **Bitbucket**. Supports both Cloud and Server/Data Center deployments.

**136 tools** across 33 toolsets: 49 Jira + 23 Confluence + 64 Bitbucket.

> Fork of [sooperset/mcp-atlassian](https://github.com/sooperset/mcp-atlassian) with comprehensive Bitbucket Cloud and Server/DC integration.

## Quick Start

### 1. Install

**From GitHub (recommended for this fork):**

```bash
# Clone the repository
git clone https://github.com/jellythomas/mcp-atlassian-with-bitbucket.git
cd mcp-atlassian-with-bitbucket

# Install dependencies with uv
uv sync --frozen --all-extras
```

**From PyPI (when published):**

```bash
# Using uvx (runs without installing)
uvx mcp-atlassian-with-bitbucket

# Or install with pip/uv
uv pip install mcp-atlassian-with-bitbucket
```

### 2. Configure

Add to your Claude Desktop, Cursor, or VS Code MCP configuration.

**For local development** (when running from a cloned repository):

```json
{
  "mcpServers": {
    "mcp-atlassian-with-bitbucket": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/mcp-atlassian-with-bitbucket", "mcp-atlassian"],
      "env": {
        "JIRA_URL": "https://your-company.atlassian.net",
        "JIRA_USERNAME": "your.email@company.com",
        "JIRA_API_TOKEN": "your_api_token",
        "CONFLUENCE_URL": "https://your-company.atlassian.net/wiki",
        "CONFLUENCE_USERNAME": "your.email@company.com",
        "CONFLUENCE_API_TOKEN": "your_api_token",
        "BITBUCKET_URL": "https://bitbucket.org",
        "BITBUCKET_USERNAME": "your.email@company.com",
        "BITBUCKET_API_TOKEN": "your_api_token",
        "BITBUCKET_WORKSPACE": "your_workspace"
      }
    }
  }
}
```

**For published package** (when installed via uvx/pip):

```json
{
  "mcpServers": {
    "mcp-atlassian-with-bitbucket": {
      "command": "uvx",
      "args": ["mcp-atlassian-with-bitbucket"],
      "env": {
        "JIRA_URL": "https://your-company.atlassian.net",
        "JIRA_USERNAME": "your.email@company.com",
        "JIRA_API_TOKEN": "your_api_token",
        "CONFLUENCE_URL": "https://your-company.atlassian.net/wiki",
        "CONFLUENCE_USERNAME": "your.email@company.com",
        "CONFLUENCE_API_TOKEN": "your_api_token",
        "BITBUCKET_URL": "https://bitbucket.org",
        "BITBUCKET_USERNAME": "your.email@company.com",
        "BITBUCKET_API_TOKEN": "your_api_token",
        "BITBUCKET_WORKSPACE": "your_workspace"
      }
    }
  }
}
```

> **Tip**: If you already have Jira/Confluence API tokens, the same token works for Bitbucket Cloud — no need to create a separate app password.

### 3. Start Using

Ask your AI assistant to:
- **"Find issues assigned to me in PROJ project"** (Jira)
- **"Search Confluence for onboarding docs"** (Confluence)
- **"List open PRs in the backend repo"** (Bitbucket)
- **"Show the diff for PR #42"** (Bitbucket)
- **"Approve PR #42 and add a comment"** (Bitbucket)
- **"Trigger a pipeline on the main branch"** (Bitbucket Cloud)

## Compatibility

| Product | Deployment | Support |
|---------|------------|---------|
| Jira | Cloud | Fully supported |
| Jira | Server/Data Center | Supported (v8.14+) |
| Confluence | Cloud | Fully supported |
| Confluence | Server/Data Center | Supported (v6.0+) |
| **Bitbucket** | **Cloud** | **Fully supported** |
| **Bitbucket** | **Server/Data Center** | **Supported (v7.0+)** |

## Authentication

### Jira & Confluence (Cloud)

**How to get your API token:**

1. Go to [id.atlassian.com/manage-profile/security/api-tokens](https://id.atlassian.com/manage-profile/security/api-tokens)
2. Click **Create API token**
3. Give it a label (e.g., "MCP Server") and click **Create**
4. Copy the token immediately — it won't be shown again

```env
JIRA_URL=https://your-company.atlassian.net
JIRA_USERNAME=your.email@company.com        # Your Atlassian account email
JIRA_API_TOKEN=ATATT3x...                   # Token from step above

CONFLUENCE_URL=https://your-company.atlassian.net/wiki
CONFLUENCE_USERNAME=your.email@company.com   # Same email as Jira
CONFLUENCE_API_TOKEN=ATATT3x...              # Same token works for both
```

> **Tip**: One Atlassian API token works for both Jira and Confluence — you don't need separate tokens.

### Jira & Confluence (Server/DC)

Create a Personal Access Token from your Jira/Confluence profile settings.

```env
JIRA_URL=https://jira.your-company.com
JIRA_PERSONAL_TOKEN=your_pat

CONFLUENCE_URL=https://confluence.your-company.com
CONFLUENCE_PERSONAL_TOKEN=your_pat
```

### Bitbucket Cloud

Two authentication methods are supported. **Bitbucket API Token is recommended** — it supports granular scopes so you only grant the permissions you need.

#### Option A: Bitbucket API Token (Recommended)

Bitbucket now has its own scoped API tokens, separate from Atlassian API tokens. This lets you grant only Bitbucket-specific permissions.

**How to create a Bitbucket API token with scopes:**

1. Go to [bitbucket.org](https://bitbucket.org) and click your avatar → **Personal settings**
2. Under **Security**, select **Create and manage API tokens**
3. Click **Create API token with scopes**
4. Name the token (e.g., "MCP Server")
5. Set an expiry date (or leave blank for no expiry)
6. Select **Bitbucket** as the app
7. Select the scopes below based on which toolsets you plan to use:

| Scope | Required for | Toolset |
|-------|-------------|---------|
| **Repositories: Read** | Browsing repos, source code, file content | `bitbucket_repositories`, `bitbucket_source` |
| **Repositories: Write** | Creating/updating repos, forks | `bitbucket_repositories` |
| **Pull requests: Read** | Listing and viewing PRs, diffs, comments | `bitbucket_pull_requests` |
| **Pull requests: Write** | Creating, approving, merging PRs, comments | `bitbucket_pull_requests` |
| **Webhooks: Read** | Listing webhooks | `bitbucket_webhooks` |
| **Webhooks: Write** | Creating/updating webhooks | `bitbucket_webhooks` |
| **Pipelines: Read** | Viewing pipeline runs, logs, variables | `bitbucket_pipelines` |
| **Pipelines: Write** | Triggering/stopping pipelines | `bitbucket_pipelines` |
| **Projects: Read** | Viewing project details | `bitbucket_workspace` |
| **Workspace membership: Read** | Listing workspace members | `bitbucket_workspace` |

**Minimum scopes for read-only PR monitoring**: Repositories: Read + Pull requests: Read

8. Click **Create** and copy the token — it's only shown once

```env
BITBUCKET_URL=https://bitbucket.org
BITBUCKET_USERNAME=your.email@company.com    # Your Atlassian account email
BITBUCKET_API_TOKEN=bb_pat_xxxxxxxxxxxx      # Bitbucket API token from step above
BITBUCKET_WORKSPACE=your_workspace           # Your workspace slug (from URL: bitbucket.org/{workspace})
```

#### Option B: App Password (Deprecated)

> **Warning**: Bitbucket is [deprecating app passwords](https://www.atlassian.com/blog/bitbucket/bitbucket-cloud-transitions-to-api-tokens-enhancing-security-with-app-password-deprecation). New app passwords cannot be created after **September 9, 2025**, and existing ones stop working on **June 9, 2026**. Migrate to API tokens (Option A).

Create an [App Password](https://bitbucket.org/account/settings/app-passwords/) with these permissions:
- **Repositories**: Read, Write
- **Pull requests**: Read, Write
- **Pipelines**: Read, Write (if using pipeline tools)
- **Webhooks**: Read, Write (if using webhook tools)

```env
BITBUCKET_URL=https://bitbucket.org
BITBUCKET_USERNAME=your_username             # Your Bitbucket username (not email)
BITBUCKET_APP_PASSWORD=your_app_password     # App password from step above
BITBUCKET_WORKSPACE=your_workspace
```

> **Note**: When using an API token, set `BITBUCKET_API_TOKEN`. When using an app password, set `BITBUCKET_APP_PASSWORD`. Both use the same username + secret authentication under the hood.

### Bitbucket Server/Data Center

Create a [Personal Access Token](https://confluence.atlassian.com/bitbucketserver/personal-access-tokens-939515499.html) with **Project Read** and **Repository Admin** permissions.

```env
BITBUCKET_URL=https://bitbucket.your-company.com
BITBUCKET_PERSONAL_TOKEN=your_pat
BITBUCKET_PROJECT_KEY=PROJ
```

### Finding Your Workspace Slug

Your workspace slug is the part after `bitbucket.org/` in your repository URLs:

```
https://bitbucket.org/my-company/my-repo
                      ^^^^^^^^^^
                      This is your workspace slug
```

You can also find it at: [bitbucket.org/account/workspaces](https://bitbucket.org/account/workspaces/)

## Configuration Reference

### Bitbucket Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `BITBUCKET_URL` | Yes | — | `https://bitbucket.org` (Cloud) or your Server URL |
| `BITBUCKET_USERNAME` | Cloud | — | Bitbucket username (email for API token, username for app password) |
| `BITBUCKET_APP_PASSWORD` | Cloud | — | App password (Cloud) |
| `BITBUCKET_API_TOKEN` | Cloud | — | API token (Cloud) — alternative to app password, reusable from Jira/Confluence |
| `BITBUCKET_PERSONAL_TOKEN` | Server | — | Personal Access Token (Server/DC) |
| `BITBUCKET_WORKSPACE` | No | — | Default workspace slug (Cloud) |
| `BITBUCKET_PROJECT_KEY` | No | — | Default project key (Server/DC) |
| `BITBUCKET_SSL_VERIFY` | No | `true` | SSL certificate verification |
| `BITBUCKET_TIMEOUT` | No | `75` | Request timeout in seconds |

### Global Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `TOOLSETS` | `all` | Comma-separated toolsets to enable (see Toolset Reference) |
| `READ_ONLY_MODE` | `false` | Block all write operations |
| `MCP_VERBOSE` | `false` | Enable verbose logging |

## Toolset Reference

Tools are organized into **33 toolsets** controlled via the `TOOLSETS` env var. Default toolsets are enabled when `TOOLSETS=default`.

### Bitbucket Toolsets (12)

| Toolset | Tools | Default | Description |
|---------|------:|---------|-------------|
| `bitbucket_repositories` | 7 | Yes | Repository CRUD, search, fork |
| `bitbucket_pull_requests` | 15 | Yes | PR lifecycle, review, merge, diff, comments |
| `bitbucket_branches` | 5 | Yes | Branch management, branching model, restrictions |
| `bitbucket_commits` | 6 | Yes | Commit history, compare, statuses, comments |
| `bitbucket_source` | 5 | Yes | File browsing, code search, blame, history |
| `bitbucket_tags` | 3 | No | Tag listing, creation, deletion |
| `bitbucket_webhooks` | 4 | No | Webhook CRUD and event management |
| `bitbucket_pipelines` | 8 | No | CI/CD pipelines (Cloud only) |
| `bitbucket_deployments` | 3 | No | Deployment environments (Cloud only) |
| `bitbucket_downloads` | — | No | Repository downloads (placeholder) |
| `bitbucket_snippets` | — | No | Code snippets (placeholder) |
| `bitbucket_workspace` | 5 | No | Workspace/project members, default reviewers |

### Jira Toolsets (15)

| Toolset | Default | Description |
|---------|---------|-------------|
| `jira_issues` | Yes | Core issue CRUD, search, batch, changelogs |
| `jira_fields` | Yes | Field search and options |
| `jira_comments` | Yes | Issue comments |
| `jira_transitions` | Yes | Workflow transitions |
| `jira_projects` | No | Project, version, component management |
| `jira_agile` | No | Boards, sprints, backlog |
| `jira_links` | No | Issue links, epic links, remote links |
| `jira_worklog` | No | Time tracking |
| `jira_attachments` | No | Attachments and images |
| `jira_users` | No | User profiles |
| `jira_watchers` | No | Issue watchers |
| `jira_service_desk` | No | JSM queues and service desks |
| `jira_forms` | No | ProForma forms |
| `jira_metrics` | No | Issue dates and SLA metrics |
| `jira_development` | No | Dev info (branches, PRs, commits) |

### Confluence Toolsets (6)

| Toolset | Default | Description |
|---------|---------|-------------|
| `confluence_pages` | Yes | Page CRUD, search, children, history |
| `confluence_comments` | Yes | Page comments |
| `confluence_labels` | No | Page labels |
| `confluence_users` | No | User search |
| `confluence_analytics` | No | Page view analytics |
| `confluence_attachments` | No | Attachment management |

### Toolset Configuration Examples

```bash
# All tools (default when TOOLSETS is unset)
TOOLSETS=all

# Only default toolsets (11 toolsets: 4 Jira + 2 Confluence + 5 Bitbucket)
TOOLSETS=default

# Defaults + pipelines and agile
TOOLSETS=default,bitbucket_pipelines,jira_agile

# Only Bitbucket tools
TOOLSETS=bitbucket_repositories,bitbucket_pull_requests,bitbucket_branches,bitbucket_commits,bitbucket_source

# Only Jira and Confluence (no Bitbucket)
TOOLSETS=jira_issues,jira_fields,jira_comments,jira_transitions,confluence_pages,confluence_comments
```

## Bitbucket Tool Catalog (64 tools)

<details>
<summary><b>Repositories (7 tools)</b></summary>

| Tool | Type | Description |
|------|------|-------------|
| `list_repositories` | read | List repositories in a workspace/project |
| `get_repository` | read | Get repository details |
| `create_repository` | write | Create a new repository |
| `update_repository` | write | Update repository settings |
| `delete_repository` | write | Delete a repository |
| `fork_repository` | write | Fork a repository |
| `list_forks` | read | List forks of a repository |

</details>

<details>
<summary><b>Pull Requests (15 tools)</b></summary>

| Tool | Type | Description |
|------|------|-------------|
| `list_pull_requests` | read | List PRs with filtering (state, author, reviewer, branch) |
| `get_pull_request` | read | Get PR details |
| `get_pull_request_diff` | read | Get PR diff (paginated) |
| `create_pull_request` | write | Create a new PR |
| `update_pull_request` | write | Update PR title, description, reviewers |
| `merge_pull_request` | write | Merge a PR |
| `decline_pull_request` | write | Decline/close a PR |
| `approve_pull_request` | write | Approve a PR |
| `unapprove_pull_request` | write | Remove approval from a PR |
| `request_changes_pull_request` | write | Request changes on a PR |
| `get_pull_request_commits` | read | List commits in a PR |
| `add_pull_request_comment` | write | Add a general comment |
| `list_pull_request_comments` | read | List all PR comments |
| `list_pull_request_statuses` | read | List PR build statuses |
| `add_inline_comment` | write | Add inline comment on a specific line |

</details>

<details>
<summary><b>PR Comments (3 tools)</b></summary>

| Tool | Type | Description |
|------|------|-------------|
| `reply_to_comment` | write | Reply to an existing comment |
| `update_comment` | write | Update a comment |
| `delete_comment` | write | Delete a comment |

</details>

<details>
<summary><b>Branches (5 tools)</b></summary>

| Tool | Type | Description |
|------|------|-------------|
| `list_branches` | read | List branches with filtering |
| `create_branch` | write | Create a new branch |
| `delete_branch` | write | Delete a branch |
| `get_branching_model` | read | Get branching model configuration |
| `list_branch_restrictions` | read | List branch restrictions |

</details>

<details>
<summary><b>Commits (6 tools)</b></summary>

| Tool | Type | Description |
|------|------|-------------|
| `list_commits` | read | List commits with author filtering |
| `get_commit` | read | Get commit details |
| `compare_commits` | read | Compare two commits/branches |
| `list_commit_statuses` | read | List build statuses for a commit |
| `create_commit_status` | write | Set build status on a commit |
| `add_commit_comment` | write | Add a comment on a commit |

</details>

<details>
<summary><b>Source (5 tools)</b></summary>

| Tool | Type | Description |
|------|------|-------------|
| `get_file_content` | read | Get file content with line range support |
| `browse_directory` | read | Browse directory listing |
| `search_code` | read | Search code across repository |
| `get_file_blame` | read | Get blame/annotate for a file |
| `get_file_history` | read | Get commit history for a file |

</details>

<details>
<summary><b>Tags (3 tools)</b></summary>

| Tool | Type | Description |
|------|------|-------------|
| `list_tags` | read | List repository tags |
| `create_tag` | write | Create a tag |
| `delete_tag` | write | Delete a tag |

</details>

<details>
<summary><b>Webhooks (4 tools)</b></summary>

| Tool | Type | Description |
|------|------|-------------|
| `list_webhooks` | read | List configured webhooks |
| `create_webhook` | write | Create a webhook |
| `update_webhook` | write | Update a webhook |
| `delete_webhook` | write | Delete a webhook |

</details>

<details>
<summary><b>Pipelines — Cloud only (8 tools)</b></summary>

| Tool | Type | Description |
|------|------|-------------|
| `list_pipelines` | read | List pipeline runs |
| `get_pipeline` | read | Get pipeline run details |
| `trigger_pipeline` | write | Trigger a new pipeline run |
| `stop_pipeline` | write | Stop a running pipeline |
| `get_pipeline_step_log` | read | Get step logs from a pipeline |
| `list_pipeline_variables` | read | List pipeline variables |
| `create_pipeline_variable` | write | Create a pipeline variable |
| `get_pipeline_config` | read | Get pipeline configuration |

</details>

<details>
<summary><b>Deployments — Cloud only (3 tools)</b></summary>

| Tool | Type | Description |
|------|------|-------------|
| `list_environments` | read | List deployment environments |
| `get_deployment` | read | Get deployment details |
| `list_deployment_releases` | read | List releases for an environment |

</details>

<details>
<summary><b>Workspace (5 tools)</b></summary>

| Tool | Type | Description |
|------|------|-------------|
| `list_workspaces` | read | List accessible workspaces (Cloud) / projects (Server) |
| `get_workspace` | read | Get workspace/project details |
| `list_workspace_members` | read | List workspace/project members |
| `get_default_reviewers` | read | Get default reviewers for a repository |
| `add_default_reviewer` | write | Add a default reviewer |

</details>

## Client Setup Guides

### Claude Desktop

Add to `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) or `%APPDATA%/Claude/claude_desktop_config.json` (Windows):

```json
{
  "mcpServers": {
    "mcp-atlassian-with-bitbucket": {
      "command": "uvx",
      "args": ["mcp-atlassian-with-bitbucket"],
      "env": {
        "BITBUCKET_URL": "https://bitbucket.org",
        "BITBUCKET_USERNAME": "your_username",
        "BITBUCKET_APP_PASSWORD": "your_app_password",
        "BITBUCKET_WORKSPACE": "your_workspace"
      }
    }
  }
}
```

### Claude Code

The recommended approach is to add the server directly in `~/.claude/settings.json` (user-level) so environment variables are bundled with the config:

```json
{
  "mcpServers": {
    "mcp-atlassian-with-bitbucket": {
      "command": "uvx",
      "args": ["mcp-atlassian-with-bitbucket"],
      "env": {
        "JIRA_URL": "https://your-company.atlassian.net",
        "JIRA_USERNAME": "your.email@company.com",
        "JIRA_API_TOKEN": "your_api_token",
        "CONFLUENCE_URL": "https://your-company.atlassian.net/wiki",
        "CONFLUENCE_USERNAME": "your.email@company.com",
        "CONFLUENCE_API_TOKEN": "your_api_token",
        "BITBUCKET_URL": "https://bitbucket.org",
        "BITBUCKET_USERNAME": "your.email@company.com",
        "BITBUCKET_API_TOKEN": "your_api_token",
        "BITBUCKET_WORKSPACE": "your_workspace"
      }
    }
  }
}
```

**For local development** (running from source instead of published package):

```json
{
  "mcpServers": {
    "mcp-atlassian-with-bitbucket": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/mcp-atlassian-with-bitbucket", "mcp-atlassian"],
      "env": {
        "BITBUCKET_URL": "https://bitbucket.org",
        "BITBUCKET_USERNAME": "your.email@company.com",
        "BITBUCKET_API_TOKEN": "your_api_token",
        "BITBUCKET_WORKSPACE": "your_workspace"
      }
    }
  }
}
```

> **Note**: The `claude mcp add` CLI command works too, but doesn't support inline `env` — you'd need to export variables in your shell profile instead.

### Cursor / VS Code

Add to `.cursor/mcp.json` or `.vscode/mcp.json`:

```json
{
  "servers": {
    "mcp-atlassian-with-bitbucket": {
      "command": "uvx",
      "args": ["mcp-atlassian-with-bitbucket"],
      "env": {
        "BITBUCKET_URL": "https://bitbucket.org",
        "BITBUCKET_USERNAME": "your_username",
        "BITBUCKET_APP_PASSWORD": "your_app_password",
        "BITBUCKET_WORKSPACE": "your_workspace"
      }
    }
  }
}
```

## Architecture

```
src/mcp_atlassian/
├── bitbucket/
│   ├── config.py          # BitbucketConfig with Cloud/Server detection
│   └── client.py          # Unified client with dual Cloud/Server API support
├── jira/                   # Jira client (existing)
├── confluence/             # Confluence client (existing)
├── servers/
│   ├── main.py            # Main MCP server mounting all sub-servers
│   ├── jira.py            # 49 Jira tool definitions
│   ├── confluence.py      # 23 Confluence tool definitions
│   └── bitbucket.py       # 64 Bitbucket tool definitions
└── utils/
    ├── toolsets.py         # 33 toolset definitions and filtering
    └── tools.py            # Tool-level filtering utilities
```

### Key Design Decisions

- **Unified client**: Single `BitbucketClient` handles both Cloud (API 2.0) and Server/DC (API 1.0) with automatic detection
- **Retry middleware**: Exponential backoff (3 attempts) for 429 rate limits and 5xx server errors, with `Retry-After` header support
- **Connection pooling**: httpx with 20 max connections, 10 keepalive, 30s expiry
- **Cloud-only guard**: Pipeline and deployment tools raise clear errors on Server/DC instead of silently failing
- **Toolset filtering**: Tag-based system lets users enable only the tools they need

## Troubleshooting

| Issue | Solution |
|-------|----------|
| `Missing BITBUCKET_URL` | Set `BITBUCKET_URL` env var |
| `401 Unauthorized` (Cloud) | Verify app password/API token has correct permissions. If using API token, ensure `BITBUCKET_API_TOKEN` is set (not `BITBUCKET_APP_PASSWORD`) |
| `401 Unauthorized` (Server) | Check PAT hasn't expired |
| Pipeline tools error on Server | Pipelines are Cloud-only; use `TOOLSETS` to disable |
| `429 Too Many Requests` | Built-in retry handles this; increase `BITBUCKET_TIMEOUT` if persistent |
| SSL errors (Server/DC) | Set `BITBUCKET_SSL_VERIFY=false` for self-signed certs |
| Server name shows old name in `/mcp` | The name shown is the JSON key in your config, not the package name. Rename the key (e.g., `"mcp-atlassian"` → `"mcp-atlassian-with-bitbucket"`) and restart |
| Bitbucket tools not appearing | Ensure `BITBUCKET_URL` and credentials are set. The server auto-detects available services based on which env vars are present |

## LLM Context Optimization

This fork includes features to reduce LLM context usage when working with large responses:

### Compact PR Details

Use `compact: true` when calling `get_pull_request` to return only essential fields instead of the full API response. Reduces output size by ~90%.

**Essential fields returned:**
- `id`, `title`, `state`, `description`
- `author` (display name, account ID)
- `source_branch`, `destination_branch`
- `reviewers` (list with names and approval status)
- `created_on`, `updated_on`

**Example usage in your AI assistant:**
> "Get PR #42 details in compact mode"

### Save Diff to File

Use `save_to_file: true` when calling `get_pull_request_diff` to write the diff to a temporary file (`/tmp/bitbucket.diff`) instead of returning the raw text. Returns a metadata object with:

```json
{
  "file_path": "/tmp/bitbucket.diff",
  "size_bytes": 125432,
  "line_count": 2847,
  "hint": "Use a file-read tool to view the diff content"
}
```

This prevents large diffs from flooding the LLM context window. Read the file separately when needed.

**Example usage in your AI assistant:**
> "Get the diff for PR #42 and save it to a file"

## Security

Never share API tokens or app passwords. Keep `.env` files secure and out of version control. See [SECURITY.md](SECURITY.md).

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup.

## License

MIT - See [LICENSE](LICENSE). Not an official Atlassian product.
