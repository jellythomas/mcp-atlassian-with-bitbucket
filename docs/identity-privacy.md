# Structured Identity Privacy

The server can protect structured Jira, Confluence, and Bitbucket identities
before a tool response leaves the FastMCP boundary. The feature is opt-in:
`MCP_ATLASSIAN_IDENTITY_PRIVACY_MODE=off` is the default and preserves existing
behavior.

The implementation supports two active modes:

- `anonymize`: replace identities with stable category labels for the response;
- `pseudonymize`: emit HMAC-based aliases that are stable within a configured
  UTC-aligned rotation period.

Pseudonymization reduces direct identity exposure, but it is not a guarantee
that data is legally anonymous. Classification rules, stable aliases, response
content, and deployment context may still permit re-identification.

## Quick Start

Generate a random key as Base64 text and keep the file outside version control:

```bash
python -c "import base64,secrets; print(base64.b64encode(secrets.token_bytes(32)).decode())" \
  > identity-privacy.key
chmod 600 identity-privacy.key
```

Create a private policy file:

```json
{
  "human_username_max_length": 8,
  "expose_service_display_name_and_login": false,
  "internal_logins": ["employee1"],
  "external_login_patterns": ["^customer-"],
  "jira_identity_text_rules": [
    {
      "field_id": "customfield_12345",
      "patterns": ["owner=(?P<identity>[a-z0-9._-]+)"]
    }
  ]
}
```

Enable pseudonymization:

```env
MCP_ATLASSIAN_IDENTITY_PRIVACY_MODE=pseudonymize
MCP_ATLASSIAN_IDENTITY_POLICY_FILE=/run/secrets/identity-policy.json
MCP_ATLASSIAN_PSEUDONYM_KEY_FILE=/run/secrets/identity-privacy.key
MCP_ATLASSIAN_PSEUDONYM_CORRELATION_SCOPE=deployment
MCP_ATLASSIAN_PSEUDONYM_CORRELATION_DOMAIN=my-mcp-deployment
MCP_ATLASSIAN_PSEUDONYM_ROTATION_HOURS=24
MCP_ATLASSIAN_IDENTITY_SELF_IDENTIFICATION_ENABLED=true
MCP_ATLASSIAN_IDENTITY_ALIAS_ROUNDTRIP_ENABLED=false
MCP_ATLASSIAN_UNSTRUCTURED_CONTENT_POLICY=allow
```

`anonymize` mode does not require a key or correlation domain.
`pseudonymize` mode requires exactly one of
`MCP_ATLASSIAN_PSEUDONYM_KEY` and
`MCP_ATLASSIAN_PSEUDONYM_KEY_FILE`, or a versioned
`MCP_ATLASSIAN_PSEUDONYM_KEYRING_FILE`.

## Configuration

| Variable | Default | Behavior |
|----------|---------|----------|
| `MCP_ATLASSIAN_IDENTITY_PRIVACY_MODE` | `off` | `off`, `anonymize`, or `pseudonymize` |
| `MCP_ATLASSIAN_IDENTITY_POLICY_FILE` | none | Validated JSON policy; invalid policies stop startup |
| `MCP_ATLASSIAN_PSEUDONYM_KEY` | none | Base64 key that decodes to at least 32 bytes |
| `MCP_ATLASSIAN_PSEUDONYM_KEY_FILE` | none | Path to a file containing the Base64 key |
| `MCP_ATLASSIAN_PSEUDONYM_KEYRING_FILE` | none | Versioned JSON keyring; mutually exclusive with direct and single-file keys |
| `MCP_ATLASSIAN_PSEUDONYM_CORRELATION_SCOPE` | `deployment` | `deployment`, `connector`, or `instance` |
| `MCP_ATLASSIAN_PSEUDONYM_CORRELATION_DOMAIN` | none | Required when pseudonymizing at deployment scope |
| `MCP_ATLASSIAN_PSEUDONYM_ROTATION_HOURS` | `24` | Unix-aligned UTC periods from 1 to 8,760 hours |
| `MCP_ATLASSIAN_IDENTITY_SELF_IDENTIFICATION_ENABLED` | `true` | Marks the caller without restoring raw identity data |
| `MCP_ATLASSIAN_IDENTITY_ALIAS_ROUNDTRIP_ENABLED` | `false` | Resolve caller- and tenant-bound aliases in supported writes; requires `pseudonymize` |
| `MCP_ATLASSIAN_UNSTRUCTURED_CONTENT_POLICY` | `allow` | `allow` or `deny` explicitly registered raw outputs |

Aliases do not include the tool name. At deployment scope, the same exact
normalized login can therefore receive the same alias across Jira, Confluence,
and Bitbucket during one rotation period. If no login is available, the
fallback identity is connector- and instance-local.

Changing a single master key changes aliases immediately. A versioned keyring
supports a controlled transition:

```json
{
  "version": 1,
  "active": {
    "id": "2026-10",
    "key": "<base64 key>"
  },
  "previous": [
    {
      "id": "2026-09",
      "key": "<base64 predecessor key>"
    }
  ]
}
```

Key IDs must contain 1-32 ASCII letters, digits, dots, underscores, or hyphens.
At most four predecessor keys are accepted. Keyring-based output uses
`pid:v2:<key-id>:<token>`, making the active key version observable without
revealing key material.

To rotate:

1. generate a new random active key and key ID;
2. move the previous active entry into `previous`;
3. deploy the same keyring to every replica;
4. keep the predecessor only for the approved transition period;
5. remove it to make its aliases fail closed.

Daily UTC alias epochs are still calculated independently. A predecessor key
does not add grace around the daily boundary. For alias roundtrip, a predecessor
alias is accepted only after the current process has observed and registered
the corresponding identity.

## Alias Roundtrip for Identity Writes

`MCP_ATLASSIAN_IDENTITY_ALIAS_ROUNDTRIP_ENABLED=true` allows aliases returned
by a read tool to be used in supported writes:

- Jira issue assignee fields and dedicated assignment;
- Jira watcher add/remove;
- Bitbucket pull-request reviewers and default reviewers.

The resolver stores the real writable identifier only in process memory until
the current alias epoch ends. Each entry is bound to:

- the Atlassian service;
- the effective instance/tenant;
- a one-way caller fingerprint derived from request credentials or the
  validated current identity.

An alias observed by another caller or tenant, an unknown alias, and an alias
from an expired rotation epoch are rejected fail closed. Raw identifiers are
never returned by the resolver or written to logs.

The cache is intentionally not persisted or shared between replicas. A write
that lands on a different replica from the preceding read is rejected rather
than resolved from another caller's state. Deployments that enable roundtrip
must use request affinity or a single replica until a dedicated shared,
encrypted alias store is configured.

## Policy File

The policy separates two classifications:

- affiliation: `internal`, `external`, or `unknown`;
- actor type: `human`, `service`, or `unknown`.

Supported policy fields:

| Field | Purpose |
|-------|---------|
| `human_username_max_length` | Logins at or below the threshold are human; longer logins are service accounts |
| `expose_service_display_name_and_login` | Allow only a classified service account's display name and selected login to remain clear |
| `internal_logins` / `external_logins` | Exact, case-insensitive normalized logins |
| `internal_login_patterns` / `external_login_patterns` | Case-insensitive regular expressions |
| `jira_identity_text_rules` | Explicit Jira custom text fields whose selected identity spans are protected |

The secure defaults leave both classifications `unknown` and do not expose
service names or logins. A length threshold is a deployment-specific heuristic:
if it classifies a human as a service account while the clear-text exception is
enabled, that human login and display name may be exposed.

Each Jira text rule must select exactly one `field_id` or
`field_name_pattern`. Every replacement regex must contain a named
`(?P<identity>...)` group. Exact field IDs take precedence over name patterns.
Invalid rules fail startup; overlapping identity spans block the response.
Unconfigured free-text fields are not scanned.

## Response Contract

When active, the final response guard:

- transforms structured identity objects and identity-bearing lists;
- removes or replaces email addresses, account IDs, keys, UUIDs, profile URLs,
  avatar URLs, and identity links;
- adds `identity_class` with affiliation and actor type;
- can mark the authenticated caller as `is_current_user: true` and `You`;
- applies the same transformed value to MCP text and structured response
  channels;
- leaves tool inputs and internal Atlassian API requests unchanged.

Registered raw and mixed tools follow an explicit policy. Bitbucket blame and
compare responses are JSON: author, committer, and other identity fields are
pseudonymized, while source lines and diff content stay unchanged. Confluence page
mentions, profile macros, and Jira `[~login]` mentions are replaced by the alias for
the login; without a stable alias, or for mentions that carry only an internal key,
they become the neutral placeholder `@Nutzer`. No REST name lookup runs in privacy
mode. The raw Confluence storage format (`convert_to_markdown=false`) is unchanged. Code, diff,
log, snippet, page body, Storage-format, comment body, and other general free
text are not scanned in this release. `MCP_ATLASSIAN_UNSTRUCTURED_CONTENT_POLICY=deny`
blocks registered raw outputs instead of returning them.

See [Free-text PII/NER Evaluation](free-text-pii-evaluation.md) for measured
German/English precision, recall, false positives, resource cost, and the
decision not to enable general scanning.

## Fail-closed Behavior

With privacy enabled, the server does not return the original response when:

- a tool has no response policy;
- a protected response has an unsupported shape;
- an adapter or serialization step fails;
- configured Jira identity spans overlap.

The client receives a generic tool error, and runtime diagnostics avoid raw
exception details. This protects structured outputs but does not retroactively
remove identities from historical logs created before the feature was enabled.

See
[Historical Identity-bearing Logs Assessment](historical-identity-logs-assessment.md)
for storage sources, safe inventory steps, cleanup options, and the required
approval record.

## Docker

Mount both files read-only. Do not bake the policy or key into the image:

```bash
docker run --rm -p 9000:9000 \
  -e MCP_ATLASSIAN_IDENTITY_PRIVACY_MODE=pseudonymize \
  -e MCP_ATLASSIAN_IDENTITY_POLICY_FILE=/run/secrets/identity-policy.json \
  -e MCP_ATLASSIAN_PSEUDONYM_KEY_FILE=/run/secrets/identity-privacy.key \
  -e MCP_ATLASSIAN_PSEUDONYM_CORRELATION_SCOPE=deployment \
  -e MCP_ATLASSIAN_PSEUDONYM_CORRELATION_DOMAIN=my-mcp-deployment \
  -e MCP_ATLASSIAN_PSEUDONYM_ROTATION_HOURS=24 \
  -v "$PWD/identity-policy.json:/run/secrets/identity-policy.json:ro" \
  -v "$PWD/identity-privacy.key:/run/secrets/identity-privacy.key:ro" \
  <image> --transport streamable-http --stateless --port 9000
```

## Kubernetes and Helm

Create an existing Kubernetes Secret containing the Base64 text key and policy:

```bash
kubectl create secret generic mcp-atlassian-with-bitbucket-and-privacy-identity-privacy \
  --from-file=identity-policy.json=identity-policy.json \
  --from-file=identity-keyring.json=identity-keyring.json
```

The chart supports the deployment through `extraEnv`, `volumes`, and
`volumeMounts`:

```yaml
extraEnv:
  - name: MCP_ATLASSIAN_IDENTITY_PRIVACY_MODE
    value: pseudonymize
  - name: MCP_ATLASSIAN_IDENTITY_POLICY_FILE
    value: /run/secrets/identity-privacy/identity-policy.json
  - name: MCP_ATLASSIAN_PSEUDONYM_KEYRING_FILE
    value: /run/secrets/identity-privacy/identity-keyring.json
  - name: MCP_ATLASSIAN_PSEUDONYM_CORRELATION_SCOPE
    value: deployment
  - name: MCP_ATLASSIAN_PSEUDONYM_CORRELATION_DOMAIN
    value: my-mcp-deployment
  - name: MCP_ATLASSIAN_PSEUDONYM_ROTATION_HOURS
    value: "24"
  - name: MCP_ATLASSIAN_IDENTITY_SELF_IDENTIFICATION_ENABLED
    value: "true"
  - name: MCP_ATLASSIAN_IDENTITY_ALIAS_ROUNDTRIP_ENABLED
    value: "false"

volumes:
  - name: identity-privacy
    secret:
      secretName: mcp-atlassian-with-bitbucket-and-privacy-identity-privacy

volumeMounts:
  - name: identity-privacy
    mountPath: /run/secrets/identity-privacy
    readOnly: true
```

Keep the policy private when it contains real account mappings or
organization-specific classification rules.
