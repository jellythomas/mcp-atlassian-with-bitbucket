"""Jira mentions under privacy use aliases or a neutral placeholder, never raw IDs."""

from mcp_atlassian_with_bitbucket_and_privacy.preprocessing.jira import (
    JiraPreprocessor,
)
from mcp_atlassian_with_bitbucket_and_privacy.privacy.runtime import (
    begin_identity_privacy_runtime,
    begin_mention_alias_resolver,
    reset_identity_privacy_runtime,
    reset_mention_alias_resolver,
)


def _clean_under_privacy(alias_resolver, text: str) -> str:
    preprocessor = JiraPreprocessor(base_url="https://jira.example")
    privacy_token = begin_identity_privacy_runtime()
    resolver_token = begin_mention_alias_resolver(alias_resolver)
    try:
        return preprocessor.clean_jira_text(text)
    finally:
        reset_mention_alias_resolver(resolver_token)
        reset_identity_privacy_runtime(privacy_token)


def test_login_mention_becomes_alias_and_account_id_mention_is_neutral() -> None:
    result = _clean_under_privacy(
        lambda login: "pid:v1:TESTALIAS" if login == "human01" else None,
        "Bitte [~human01] und [~accountid:5f1234abcd] prüfen.",
    )

    assert "@pid:v1:TESTALIAS" in result
    assert "@Nutzer" in result
    assert "human01" not in result
    assert "5f1234abcd" not in result


def test_login_mention_without_alias_uses_neutral_placeholder() -> None:
    result = _clean_under_privacy(lambda login: None, "Siehe [~human01].")

    assert "@Nutzer" in result
    assert "human01" not in result
