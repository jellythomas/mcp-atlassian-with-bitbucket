# Historical Identity-bearing Logs Assessment

## Status

Inventory and cleanup procedure are prepared. No historical production log was
read, copied, or deleted during this assessment. Retention or deletion requires
an explicit CISO/DPO and operations decision.

## Storage Sources

The application configures a stream handler only. It writes to stderr by
default, or stdout when `MCP_LOGGING_STDOUT=true`. Persistent copies therefore
come from the surrounding runtime:

| Source | Potential identity content | Current repository control |
|--------|----------------------------|----------------------------|
| Docker container stdout/stderr | Tool errors, lookup identifiers, user-search queries, attachment paths | `mcp-tooling` has no explicit `logging` driver limits, `max-size`, or `max-file` |
| Jenkins build console | Up to 200 Compose log lines for the `logs` action; last 60 container lines after a failed health check | No repository-level `buildDiscarder` / retention rule found |
| Interactive STDIO/HTTP launch | Terminal capture, IDE MCP diagnostics, shell transcripts | Controlled by each client/host, outside this repository |
| OAuth setup and fallback storage diagnostics | Keyring usernames, token-file paths, endpoint/error details | Stored only when operators retain process output |

Docker's effective log location and retention depend on the daemon. For the
default `json-file` driver, logs are usually below
`/var/lib/docker/containers/<container-id>/`, but operators must inspect the
daemon instead of assuming that path.

## Historical Risk Windows

Identity privacy sanitizes known diagnostics only while privacy mode is active.
Historical logs from before rollout, or from runs where privacy remained
`off`, may contain:

- Jira current-user payloads at debug level;
- usernames, account IDs, emails, assignee/reporter values, and user-search
  queries;
- Confluence user-search CQL and API exception text;
- user mentions processed from Jira/Confluence content;
- attachment source/target paths containing workstation or server usernames;
- exception strings or tracebacks containing request/response fragments.

Representative source areas include:

- `jira/users.py`
- `jira/fields.py`
- `jira/formatting.py`
- `preprocessing/base.py`
- `preprocessing/jira.py`
- `servers/confluence.py`
- Jira/Confluence attachment modules
- OAuth setup and token-storage diagnostics

The list identifies possible sources, not proof that a specific historical log
contains personal data.

## Safe Inventory Procedure

Do not begin by grepping for real names. Broad searches can create additional
copies in shell history, CI output, SIEM queries, or exported reports.

1. Record the server, service, container/build identifier, time range, storage
   owner, access group, and approximate byte size.
2. Determine retention metadata without displaying content:

   ```bash
   docker inspect --format '{{.HostConfig.LogConfig.Type}} {{.LogPath}}' <container>
   sudo du -h <resolved-log-path>
   ```

3. In Jenkins, inventory builds that executed the `logs` action or failed a
   health check. Record build IDs and retention metadata; do not download
   consoles during the first pass.
4. Check for legal hold, active incident response, audit requirements, and
   backups/snapshots before deletion.
5. If content sampling is approved, use the smallest possible sample, named
   reviewers, an access-controlled workspace, and a documented deletion date.

## Decision Options

### A. Retain until existing expiry

Use only when a legal, audit, or incident requirement applies.

- restrict access to named operations/security roles;
- document the lawful purpose and expiry;
- prevent new exports;
- delete at the approved expiry.

### B. Targeted purge

Recommended when only known rollout, canary, verbose-debug, or failed-health
windows are at risk.

- delete the identified Docker log files through an approved daemon/logging
  procedure, not by editing active files in place;
- expire the identified Jenkins builds/consoles;
- include replicas, backups, and exported diagnostics in the scope;
- record identifiers, timestamps, operator, and result without copying content.

### C. Full historical purge

Use when no retention obligation exists and the affected time range cannot be
bounded reliably.

- stop or rotate affected services first;
- purge Docker/Jenkins/SIEM copies using platform-supported operations;
- verify that services restart with the current privacy configuration;
- retain only a non-content deletion record.

## Forward Retention Recommendation

Subject to operations approval:

- configure a bounded Docker logging driver, for example `json-file` with
  `max-size: 10m` and `max-file: 5`, or the organization's managed local
  logging driver;
- add an approved Jenkins build-discard policy;
- keep `MCP_VERBOSE` and `MCP_VERY_VERBOSE` disabled in routine production;
- alert on privacy fail-closed blocks and counts, not raw payloads;
- prohibit log shipping rules that copy complete MCP tool responses.

These are proposed operating controls. They have not been applied because they
change production retention.

## Required Approval Record

| Field | Required value |
|-------|----------------|
| Decision | Retain / targeted purge / full purge |
| Time range and systems | Docker hosts, services, Jenkins jobs, SIEM/backups |
| Legal/audit hold checked | Yes/no plus reference |
| CISO/DPO approver | Name and date |
| Operations owner | Name and execution window |
| Verification | Non-content evidence that retention/deletion completed |

Until this record is approved, historical cleanup remains blocked.
