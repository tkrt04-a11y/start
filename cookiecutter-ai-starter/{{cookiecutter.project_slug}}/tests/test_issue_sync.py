import pytest
import requests

from src import issue_sync


class DummyResponse:
    def __init__(self, payload=None, status_code=200, headers=None, text=""):
        self._payload = payload if payload is not None else []
        self.status_code = status_code
        self.headers = headers or {}
        self.text = text

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"status={self.status_code}")
        return None

    def json(self):
        return self._payload


@pytest.fixture(autouse=True)
def clear_issue_sync_retry_env(monkeypatch):
    monkeypatch.delenv("ISSUE_SYNC_RETRIES", raising=False)
    monkeypatch.delenv("ISSUE_SYNC_BACKOFF_SEC", raising=False)


def test_sync_promoted_actions_to_github_issues(monkeypatch):
    posted = []

    open_issues = [{"title": "[AI-STARTER] Existing"}]

    def fake_get(url, headers=None, params=None, timeout=0):
        return DummyResponse(payload=open_issues)

    def fake_post(url, headers=None, json=None, timeout=0):
        posted.append(json)
        return DummyResponse(payload={"id": 1})

    monkeypatch.setattr(issue_sync.requests, "get", fake_get)
    monkeypatch.setattr(issue_sync.requests, "post", fake_post)

    result = issue_sync.sync_promoted_actions_to_github_issues(
        ["Existing", "New action"],
        repo="owner/repo",
        token="token",
        period_key="2026-W09",
        source_period_type="weekly",
    )

    assert result == {"created": 1, "skipped_existing": 1}
    assert posted[0]["title"] == "[AI-STARTER] New action"
    assert "## Source Period" in posted[0]["body"]
    assert "## Action" in posted[0]["body"]
    assert "## Context" in posted[0]["body"]
    assert "## Metadata" in posted[0]["body"]
    assert "- Type: weekly" in posted[0]["body"]
    assert "- Key: 2026-W09" in posted[0]["body"]
    assert "<!-- ai-starter-meta: action_hash=" in posted[0]["body"]
    assert "; period_key=2026-W09 -->" in posted[0]["body"]


def test_sync_promoted_actions_to_github_issues_with_labels_and_assignees(monkeypatch):
    posted = []

    def fake_get(url, headers=None, params=None, timeout=0):
        return DummyResponse(payload=[])

    def fake_post(url, headers=None, json=None, timeout=0):
        posted.append(json)
        return DummyResponse(payload={"id": 1})

    monkeypatch.setattr(issue_sync.requests, "get", fake_get)
    monkeypatch.setattr(issue_sync.requests, "post", fake_post)

    issue_sync.sync_promoted_actions_to_github_issues(
        ["Action A"],
        repo="owner/repo",
        token="token",
        labels=["starter", "auto"],
        assignees=["octocat"],
    )

    assert posted[0]["labels"] == ["starter", "auto"]
    assert posted[0]["assignees"] == ["octocat"]


def test_sync_promoted_actions_skips_existing_by_meta_marker(monkeypatch):
    posted = []
    action = "Refine onboarding docs"
    action_hash = issue_sync._action_hash(action)
    open_issues = [
        {
            "title": "Some different title",
            "body": f"<!-- ai-starter-meta: action_hash={action_hash}; period_key=2026-W09 -->",
        }
    ]

    def fake_get(url, headers=None, params=None, timeout=0):
        return DummyResponse(payload=open_issues)

    def fake_post(url, headers=None, json=None, timeout=0):
        posted.append(json)
        return DummyResponse(payload={"id": 1})

    monkeypatch.setattr(issue_sync.requests, "get", fake_get)
    monkeypatch.setattr(issue_sync.requests, "post", fake_post)

    result = issue_sync.sync_promoted_actions_to_github_issues(
        [action],
        repo="owner/repo",
        token="token",
        period_key="2026-W09",
    )

    assert result == {"created": 0, "skipped_existing": 1}
    assert posted == []


def test_sync_promoted_actions_adds_period_label_when_enabled(monkeypatch):
    posted = []

    def fake_get(url, headers=None, params=None, timeout=0):
        return DummyResponse(payload=[])

    def fake_post(url, headers=None, json=None, timeout=0):
        posted.append(json)
        return DummyResponse(payload={"id": 1})

    monkeypatch.setattr(issue_sync.requests, "get", fake_get)
    monkeypatch.setattr(issue_sync.requests, "post", fake_post)

    issue_sync.sync_promoted_actions_to_github_issues(
        ["Action A"],
        repo="owner/repo",
        token="token",
        labels=["starter"],
        source_period_type="monthly",
        include_period_label=True,
    )

    assert posted[0]["labels"] == ["starter", "ai-starter-monthly"]


def test_sync_promoted_actions_does_not_add_period_label_when_disabled(monkeypatch):
    posted = []

    def fake_get(url, headers=None, params=None, timeout=0):
        return DummyResponse(payload=[])

    def fake_post(url, headers=None, json=None, timeout=0):
        posted.append(json)
        return DummyResponse(payload={"id": 1})

    monkeypatch.setattr(issue_sync.requests, "get", fake_get)
    monkeypatch.setattr(issue_sync.requests, "post", fake_post)

    issue_sync.sync_promoted_actions_to_github_issues(
        ["Action A"],
        repo="owner/repo",
        token="token",
        labels=["starter"],
        source_period_type="monthly",
        include_period_label=False,
    )

    assert posted[0]["labels"] == ["starter"]


def test_parse_issue_assignee_rules():
    parsed = issue_sync.parse_issue_assignee_rules(
        "ai-starter-weekly:alice; ai-starter-monthly:bob,carol; default:teamlead"
    )

    assert parsed == {
        "ai-starter-weekly": ["alice"],
        "ai-starter-monthly": ["bob", "carol"],
        "default": ["teamlead"],
    }


@pytest.mark.parametrize(
    "raw_rules",
    [
        "broken",
        ":alice",
        "default:",
    ],
)
def test_parse_issue_assignee_rules_raises_on_invalid_syntax(raw_rules):
    with pytest.raises(ValueError):
        issue_sync.parse_issue_assignee_rules(raw_rules)


def test_resolve_issue_assignees_uses_period_label_rule_when_no_explicit():
    rules = issue_sync.parse_issue_assignee_rules(
        "ai-starter-weekly:alice;ai-starter-monthly:bob;default:teamlead"
    )

    weekly_assignees = issue_sync.resolve_issue_assignees(
        explicit_assignees=None,
        labels=["starter"],
        source_period_type="weekly",
        include_period_label=True,
        assignee_rules=rules,
    )
    monthly_assignees = issue_sync.resolve_issue_assignees(
        explicit_assignees=None,
        labels=["starter"],
        source_period_type="monthly",
        include_period_label=True,
        assignee_rules=rules,
    )

    assert weekly_assignees == ["alice"]
    assert monthly_assignees == ["bob"]


def test_resolve_issue_assignees_prioritizes_explicit_over_rules():
    rules = issue_sync.parse_issue_assignee_rules("ai-starter-weekly:alice;default:teamlead")

    assignees = issue_sync.resolve_issue_assignees(
        explicit_assignees=["octocat"],
        labels=["ai-starter-weekly"],
        source_period_type="weekly",
        include_period_label=True,
        assignee_rules=rules,
    )

    assert assignees == ["octocat"]


def test_sync_promoted_actions_retries_on_429_and_succeeds(monkeypatch):
    posted = []
    waits = []
    post_responses = [
        DummyResponse(payload={"message": "API rate limit exceeded"}, status_code=429, headers={"Retry-After": "0"}),
        DummyResponse(payload={"id": 1}, status_code=201),
    ]

    def fake_get(url, headers=None, params=None, timeout=0):
        return DummyResponse(payload=[])

    def fake_post(url, headers=None, json=None, timeout=0):
        posted.append(json)
        return post_responses.pop(0)

    monkeypatch.setattr(issue_sync.requests, "get", fake_get)
    monkeypatch.setattr(issue_sync.requests, "post", fake_post)
    monkeypatch.setattr(issue_sync.time, "sleep", waits.append)

    result = issue_sync.sync_promoted_actions_to_github_issues(
        ["Action A"],
        repo="owner/repo",
        token="token",
    )

    assert result == {"created": 1, "skipped_existing": 0}
    assert len(posted) == 2
    assert waits == [1.0]


def test_fetch_open_issue_index_retries_on_secondary_rate_limit_and_succeeds(monkeypatch):
    waits = []
    get_responses = [
        DummyResponse(
            payload={"message": "You have exceeded a secondary rate limit. Please wait a few minutes before you try again."},
            status_code=403,
            headers={"X-RateLimit-Reset": "101"},
        ),
        DummyResponse(payload=[{"title": "[AI-STARTER] Existing"}], status_code=200),
    ]

    def fake_get(url, headers=None, params=None, timeout=0):
        return get_responses.pop(0)

    monkeypatch.setattr(issue_sync.requests, "get", fake_get)
    monkeypatch.setattr(issue_sync.time, "sleep", waits.append)
    monkeypatch.setattr(issue_sync.time, "time", lambda: 100.0)

    titles, meta_keys = issue_sync._fetch_open_issue_index("owner/repo", headers={"Authorization": "Bearer token"})

    assert titles == {"[AI-STARTER] Existing"}
    assert meta_keys == set()
    assert waits == [2.0]


def test_sync_promoted_actions_raises_runtime_error_when_rate_limit_retries_exhausted(monkeypatch):
    waits = []

    def fake_get(url, headers=None, params=None, timeout=0):
        return DummyResponse(payload=[])

    def fake_post(url, headers=None, json=None, timeout=0):
        return DummyResponse(payload={"message": "secondary rate limit"}, status_code=429)

    monkeypatch.setattr(issue_sync.requests, "get", fake_get)
    monkeypatch.setattr(issue_sync.requests, "post", fake_post)
    monkeypatch.setattr(issue_sync.time, "sleep", waits.append)

    with pytest.raises(RuntimeError) as exc_info:
        issue_sync.sync_promoted_actions_to_github_issues(
            ["Action A"],
            repo="owner/repo",
            token="token",
        )

    message = str(exc_info.value)
    assert "failed after retries" in message
    assert "method=POST" in message
    assert "status=429" in message
    assert waits == [1.0, 2.0, 4.0]


def test_request_with_rate_limit_retry_uses_env_retry_and_backoff(monkeypatch):
    waits = []
    call_count = 0

    def fake_request(url, **kwargs):
        nonlocal call_count
        call_count += 1
        return DummyResponse(payload={"message": "secondary rate limit"}, status_code=429)

    monkeypatch.setenv("ISSUE_SYNC_RETRIES", "1")
    monkeypatch.setenv("ISSUE_SYNC_BACKOFF_SEC", "0.25")
    monkeypatch.setattr(issue_sync.time, "sleep", waits.append)

    with pytest.raises(RuntimeError) as exc_info:
        issue_sync._request_with_rate_limit_retry(fake_request, "GET", "https://example.invalid/issues")

    message = str(exc_info.value)
    assert "attempt=2/2" in message
    assert call_count == 2
    assert waits == [0.25]


def test_request_with_rate_limit_retry_invalid_env_falls_back_with_warning(monkeypatch, caplog):
    waits = []
    call_count = 0

    def fake_request(url, **kwargs):
        nonlocal call_count
        call_count += 1
        return DummyResponse(payload={"message": "secondary rate limit"}, status_code=429)

    monkeypatch.setenv("ISSUE_SYNC_RETRIES", "-1")
    monkeypatch.setenv("ISSUE_SYNC_BACKOFF_SEC", "oops")
    monkeypatch.setattr(issue_sync.time, "sleep", waits.append)

    with caplog.at_level("WARNING"):
        with pytest.raises(RuntimeError) as exc_info:
            issue_sync._request_with_rate_limit_retry(fake_request, "GET", "https://example.invalid/issues")

    message = str(exc_info.value)
    assert "attempt=4/4" in message
    assert call_count == 4
    assert waits == [1.0, 2.0, 4.0]
    assert "Invalid issue sync env value; using default" in caplog.text
    assert "ISSUE_SYNC_RETRIES" in caplog.text
    assert "ISSUE_SYNC_BACKOFF_SEC" in caplog.text
