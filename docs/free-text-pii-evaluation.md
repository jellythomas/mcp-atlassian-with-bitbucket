# Free-text PII/NER Evaluation

## Decision

General automatic name scanning remains disabled.

The best measured candidate still missed 2 of 22 expected identities and
redacted 7 non-person spans. That error rate is not acceptable for a mandatory
outbound privacy boundary: false negatives disclose identities, while false
positives alter Jira, Confluence, Bitbucket, code, and documentation content.

Continue to use:

- schema-aware structured identity protection;
- explicitly configured Jira custom text-field rules;
- `MCP_ATLASSIAN_UNSTRUCTURED_CONTENT_POLICY=deny` when raw output is not
  acceptable.

## Golden Set

The public synthetic set is
[`identity-privacy-free-text-golden.json`](identity-privacy-free-text-golden.json).
It contains:

- 36 documents: 20 German and 16 English;
- 22 annotated person/login entities;
- Unicode, hyphenated names, initials, apostrophes, and short logins;
- negative examples for companies, products, statuses, service accounts,
  class names, projects, and URL paths.

Matching uses one-to-one overlapping character spans. This avoids penalizing a
detector for including titles such as `Dr.` while still counting extra,
non-overlapping entities as false positives.

The set is intentionally synthetic and too small for production approval. A
confidential representative set needs DPO/CISO approval before a future
evaluation uses real content.

## Environment

- Ubuntu 24.04 / Python 3.12
- spaCy 3.8.16
- `de_core_news_sm` 3.8.0, 21.16 MiB
- `en_core_web_sm` 3.8.0, 14.54 MiB
- Presidio Analyzer 2.x using the same spaCy models
- 30 warm repetitions over all 36 documents

The combined benchmark process loaded both direct spaCy pipelines and a second
Presidio-managed pair. Peak RSS was 442.05 MiB. This exceeds the current
256 MiB limit used by the lightweight Atlassian MCP services.

## Results

| Candidate | TP | FP | FN | Precision | Recall | F1 | Mean ms/doc |
|-----------|---:|---:|---:|----------:|-------:|---:|------------:|
| Capitalized-name regex | 14 | 14 | 8 | 0.500 | 0.636 | 0.560 | 0.001 |
| spaCy small DE/EN | 16 | 7 | 6 | 0.696 | 0.727 | 0.711 | 3.16 |
| spaCy + exact login allowlist | 20 | 7 | 2 | 0.741 | 0.909 | 0.816 | 3.25 |
| Presidio + spaCy | 16 | 7 | 6 | 0.696 | 0.727 | 0.711 | 3.55 |

Language detail for the best candidate:

| Language | TP | FP | FN | Precision | Recall | F1 |
|----------|---:|---:|---:|----------:|-------:|---:|
| German | 12 | 3 | 1 | 0.800 | 0.923 | 0.857 |
| English | 8 | 4 | 1 | 0.667 | 0.889 | 0.762 |

Representative false positives:

- `Max Plus`
- `Done`
- `Techn User Customer`
- `Müller GmbH`
- `Brown`

Representative misses:

- `M. Schmidt`
- `O'Connor`

Presidio produced the same PERSON spans as its configured spaCy engine. It adds
recognizer orchestration but did not improve person-name accuracy in this set.

## Other Candidate

GLiNER-style multilingual PII models are promising for local deployment, but
were not added to the server or benchmarked in this run. Current candidates are
substantially larger than the spaCy small models and introduce model licensing,
supply-chain, memory, and update-governance requirements. They should be
evaluated only in an isolated follow-up after model and license approval.

## Required Release Gates for Any Future Scanner

A future implementation must use a confidential, representative Golden Set and
meet all of these per-language gates:

- person/login recall at least 0.99;
- precision at least 0.95;
- zero known human canaries in outbound responses and runtime logs;
- explicit allowlists for service identities, products, organizations, code
  symbols, and issue/project terminology;
- p95 latency and memory measured on production-size content;
- local-only inference with pinned model hashes and approved licenses;
- human review and documented residual risk for high-risk workflows.

Until those gates are met, general free text remains outside the automatic
privacy transformation.

## Sources

- [Microsoft Presidio language and NLP-engine documentation](https://github.com/data-privacy-stack/presidio/blob/main/docs/analyzer/languages.md)
- [Presidio transformer NLP-engine documentation](https://github.com/data-privacy-stack/presidio/blob/main/docs/analyzer/nlp_engines/transformers.md)
- [spaCy German models](https://spacy.io/models/de/)
- [spaCy model releases](https://github.com/explosion/spacy-models/releases)
- [GLiNER repository](https://github.com/urchade/GLiNER)
- [EDPB Guidelines 01/2025 on Pseudonymisation](https://www.edpb.europa.eu/public-consultations/guidelines-012025-on-pseudonymisation_en)
