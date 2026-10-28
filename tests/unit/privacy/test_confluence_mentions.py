"""Confluence page mentions under privacy use aliases, never REST name lookups."""

from unittest.mock import Mock

from bs4 import BeautifulSoup

from mcp_atlassian_with_bitbucket_and_privacy.preprocessing.confluence import (
    ConfluencePreprocessor,
)
from mcp_atlassian_with_bitbucket_and_privacy.privacy.runtime import (
    begin_identity_privacy_runtime,
    begin_mention_alias_resolver,
    reset_identity_privacy_runtime,
    reset_mention_alias_resolver,
)

_MENTION_WITH_LOGIN = '<ac:link><ri:user ri:username="human01" /></ac:link>'
_MENTION_WITH_USERKEY = '<ac:link><ri:user ri:userkey="abc123" /></ac:link>'
_PROFILE_MACRO = (
    '<ac:structured-macro ac:name="profile">'
    '<ac:parameter ac:name="user"><ri:user ri:username="human01" /></ac:parameter>'
    "</ac:structured-macro>"
)


def _client_must_not_be_used() -> Mock:
    client = Mock()
    client.get_user_details_by_username.side_effect = AssertionError("REST lookup")
    client.get_user_details_by_userkey.side_effect = AssertionError("REST lookup")
    return client


def _run_under_privacy(alias_resolver, fragment: str) -> str:
    preprocessor = ConfluencePreprocessor(base_url="https://confluence.example")
    privacy_token = begin_identity_privacy_runtime()
    resolver_token = begin_mention_alias_resolver(alias_resolver)
    try:
        soup = BeautifulSoup(fragment, "html.parser")
        preprocessor._process_user_mentions_in_soup(soup, _client_must_not_be_used())
        preprocessor._process_user_profile_macros_in_soup(
            soup, _client_must_not_be_used()
        )
        return str(soup)
    finally:
        reset_mention_alias_resolver(resolver_token)
        reset_identity_privacy_runtime(privacy_token)


def test_mention_with_login_is_replaced_by_alias_without_rest_lookup() -> None:
    text = _run_under_privacy(lambda login: "pid:v1:TESTALIAS", _MENTION_WITH_LOGIN)

    assert "@pid:v1:TESTALIAS" in text
    assert "human01" not in text


def test_mention_without_login_uses_neutral_placeholder() -> None:
    text = _run_under_privacy(lambda login: "pid:v1:TESTALIAS", _MENTION_WITH_USERKEY)

    assert "@Nutzer" in text
    assert "abc123" not in text


def test_mention_without_stable_alias_uses_neutral_placeholder() -> None:
    text = _run_under_privacy(lambda login: None, _MENTION_WITH_LOGIN)

    assert "@Nutzer" in text
    assert "human01" not in text


def test_profile_macro_is_replaced_without_rest_lookup() -> None:
    text = _run_under_privacy(lambda login: "pid:v1:TESTALIAS", _PROFILE_MACRO)

    assert "@pid:v1:TESTALIAS" in text
    assert "human01" not in text
    assert "structured-macro" not in text
