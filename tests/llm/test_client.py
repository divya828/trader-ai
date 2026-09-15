import inspect
import json

import pytest

from trader_ai.llm.client import ExplanationResult, HostedExplainer
from trader_ai.llm.redaction import RedactedFinding, RedactedSubject


def _redacted(rule_id="diversification.category_duplication"):
    return RedactedFinding(
        finding_key=f"{rule_id}#0",
        rule_id=rule_id,
        severity="MEDIUM",
        subjects=[RedactedSubject("SCHEME", "fund_1", 0.29)],
        metrics={"fund_count": 3.0},
        citation_source="SEBI circular",
        citation_claim="Schemes are assigned to defined categories and so on.",
    )


class _FakeMessages:
    def __init__(self, behaviour):
        self._behaviour = behaviour
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self._behaviour(kwargs)


class _FakeClient:
    def __init__(self, behaviour):
        self.messages = _FakeMessages(behaviour)


def _ok_response(payload):
    class _Block:
        type = "text"
        text = json.dumps(payload)

    class _Message:
        content = [_Block()]

    return lambda kwargs: _Message()


def test_explain_returns_text_keyed_by_finding_key():
    payload = {"explanations": [{"finding_key": "diversification.category_duplication#0",
                                 "text": "Three funds do the same job."}]}
    client = HostedExplainer(client=_FakeClient(_ok_response(payload)))
    result = client.explain([_redacted()])
    assert result.available
    assert result.explanations["diversification.category_duplication#0"].startswith("Three")


def test_explain_accepts_only_redacted_findings():
    """The invariant is enforced by the type signature, not by a runtime check."""
    annotation = str(
        inspect.signature(HostedExplainer.explain).parameters["findings"].annotation
    )
    assert "RedactedFinding" in annotation


def test_no_findings_short_circuits_without_calling_the_api():
    client = HostedExplainer(client=_FakeClient(_ok_response({"explanations": []})))
    result = client.explain([])
    assert result.available
    assert client._client.messages.calls == []


def _status_error(cls, status):
    """Build a real SDK exception.

    APIStatusError.__init__ dereferences response.request, .status_code and
    .headers, so a None response raises inside the fixture before the code
    under test ever runs. A real httpx2.Response is required.
    """
    import anthropic  # noqa: F401  (imported for the caller's cls)
    import httpx2

    request = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    return cls("boom", response=httpx2.Response(status, request=request), body=None)


def test_a_missing_credential_degrades_rather_than_raising():
    import anthropic

    def raise_auth(kwargs):
        raise _status_error(anthropic.AuthenticationError, 401)

    client = HostedExplainer(client=_FakeClient(raise_auth))
    result = client.explain([_redacted()])
    assert not result.available
    assert "credential" in result.reason.lower() or "auth" in result.reason.lower()


def test_a_rate_limit_degrades_after_the_sdk_has_retried():
    import anthropic

    def raise_rate_limit(kwargs):
        raise _status_error(anthropic.RateLimitError, 429)

    client = HostedExplainer(client=_FakeClient(raise_rate_limit))
    result = client.explain([_redacted()])
    assert not result.available
    assert "rate" in result.reason.lower()


def test_a_server_error_degrades_with_its_status_code():
    """RateLimitError subclasses APIStatusError, so clause order matters.

    If APIStatusError were caught first, a 429 would report as a bare status
    code instead of a rate limit.
    """
    import anthropic

    def raise_500(kwargs):
        raise _status_error(anthropic.APIStatusError, 500)

    client = HostedExplainer(client=_FakeClient(raise_500))
    result = client.explain([_redacted()])
    assert not result.available
    assert "500" in result.reason


def test_a_connection_error_degrades():
    import anthropic

    def raise_conn(kwargs):
        raise anthropic.APIConnectionError(request=None)

    client = HostedExplainer(client=_FakeClient(raise_conn))
    result = client.explain([_redacted()])
    assert not result.available
    assert result.explanations == {}


def test_an_unparseable_response_degrades():
    class _Block:
        type = "text"
        text = "not json at all"

    class _Message:
        content = [_Block()]

    client = HostedExplainer(client=_FakeClient(lambda kwargs: _Message()))
    result = client.explain([_redacted()])
    assert not result.available
    assert "parse" in result.reason.lower() or "format" in result.reason.lower()


def test_a_response_missing_the_expected_key_degrades():
    client = HostedExplainer(client=_FakeClient(_ok_response({"wrong": []})))
    result = client.explain([_redacted()])
    assert not result.available


def test_retries_are_left_to_the_sdk():
    """The SDK already retries 429/5xx/connection errors with backoff.

    A hand-rolled loop would double-retry and slow every failure.
    """
    source = inspect.getsource(HostedExplainer)
    assert "for attempt in range" not in source
    assert "max_retries" in source


def test_the_model_is_the_pinned_id():
    payload = {"explanations": []}
    client = HostedExplainer(client=_FakeClient(_ok_response(payload)))
    client.explain([_redacted()])
    assert client._client.messages.calls[0]["model"] == "claude-opus-5"


def test_structured_output_is_requested():
    payload = {"explanations": []}
    client = HostedExplainer(client=_FakeClient(_ok_response(payload)))
    client.explain([_redacted()])
    config = client._client.messages.calls[0]["output_config"]
    assert config["format"]["type"] == "json_schema"


def test_an_unexpected_rule_id_in_the_response_is_dropped():
    """A response must not introduce findings that were never sent."""
    payload = {"explanations": [{"finding_key": "made.up.rule#0", "text": "..."}]}
    client = HostedExplainer(client=_FakeClient(_ok_response(payload)))
    result = client.explain([_redacted()])
    assert "made.up.rule#0" not in result.explanations


def test_a_non_string_explanation_is_dropped():
    payload = {"explanations": [
        {"finding_key": "diversification.category_duplication#0", "text": 123}
    ]}
    client = HostedExplainer(client=_FakeClient(_ok_response(payload)))
    result = client.explain([_redacted()])
    assert result.explanations == {}


def test_no_credential_at_all_degrades_instead_of_crashing():
    """With NO key configured, the SDK raises TypeError from the REQUEST.

    Credential resolution is lazy: the constructor succeeds and the failure
    surfaces on the first call, never as AuthenticationError (which means a
    key was present and rejected). Letting the TypeError escape would crash a
    report whose numbers were all computed locally -- the exact opposite of
    the degradation this class promises. Found by running the live test on a
    machine with no credential.
    """
    def raise_type_error(kwargs):
        raise TypeError("Could not resolve authentication method.")

    client = HostedExplainer(client=_FakeClient(raise_type_error))
    result = client.explain([_redacted()])

    assert not result.available
    assert "credential" in result.reason.lower()


def test_no_findings_short_circuits_before_any_auth_resolution():
    def raise_type_error(kwargs):
        raise TypeError("Could not resolve authentication method.")

    result = HostedExplainer(client=_FakeClient(raise_type_error)).explain([])
    assert result.available


def test_a_status_error_surfaces_the_api_message():
    """A bare status code hid "your credit balance is too low".

    That is an actionable error, and it was indistinguishable from a
    malformed request until the message was included. Found by running the
    live test against a real key on an account with no credit.
    """
    import anthropic

    def raise_billing(kwargs):
        exc = _status_error(anthropic.APIStatusError, 400)
        exc.body = {
            "type": "error",
            "error": {
                "type": "invalid_request_error",
                "message": "Your credit balance is too low to access the Anthropic API.",
            },
        }
        raise exc

    result = HostedExplainer(client=_FakeClient(raise_billing)).explain([_redacted()])
    assert not result.available
    assert "400" in result.reason
    assert "credit balance" in result.reason


def test_a_status_error_without_a_body_still_reports_its_code():
    import anthropic

    def raise_bare(kwargs):
        raise _status_error(anthropic.APIStatusError, 503)

    result = HostedExplainer(client=_FakeClient(raise_bare)).explain([_redacted()])
    assert not result.available
    assert "503" in result.reason
