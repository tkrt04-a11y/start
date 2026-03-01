from pathlib import Path
import json

from src import connectors


class DummyResponse:
    def __init__(self, payload=None, text="", status_code=200, headers=None):
        self._payload = payload
        self.text = text
        self.status_code = status_code
        self.headers = headers or {}

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def test_fetch_github_issues(monkeypatch):
    payload = [
        {"title": "Issue A", "body": "Body A", "html_url": "https://example/a"},
        {"title": "PR", "body": "skip", "html_url": "https://example/pr", "pull_request": {}},
    ]

    def fake_get(url, params=None, headers=None, timeout=0):
        return DummyResponse(payload=payload)

    monkeypatch.setattr(connectors.requests, "get", fake_get)
    entries = connectors.fetch_github_issues("owner/repo")
    assert len(entries) == 1
    assert entries[0]["source"] == "github:owner/repo"
    assert "Issue A" in entries[0]["content"]


def test_fetch_rss_feed(monkeypatch):
    xml = """
    <rss><channel>
      <item><title>T1</title><description>D1</description><link>L1</link></item>
      <item><title>T2</title><description>D2</description><link>L2</link></item>
    </channel></rss>
    """

    def fake_get(url, params=None, headers=None, timeout=0):
        return DummyResponse(text=xml)

    monkeypatch.setattr(connectors.requests, "get", fake_get)
    entries = connectors.fetch_rss_feed("https://example.com/rss", limit=1)
    assert len(entries) == 1
    assert entries[0]["source"] == "rss:https://example.com/rss"
    assert "T1" in entries[0]["content"]


def test_fetch_survey_json(tmp_path: Path):
    data = [{"source": "survey", "content": "need better docs"}, {"source": "x", "note": "ignored"}]
    path = tmp_path / "survey.json"
    path.write_text(json.dumps(data), encoding="utf-8")

    entries = connectors.fetch_survey_json(path)
    assert len(entries) == 1
    assert entries[0]["source"] == "survey"


def test_fetch_github_issues_retries(monkeypatch):
    payload = [{"title": "Issue A", "body": "Body A", "html_url": "https://example/a"}]
    calls = {"count": 0}

    def flaky_get(url, params=None, headers=None, timeout=0):
        calls["count"] += 1
        if calls["count"] == 1:
            raise RuntimeError("temporary")
        return DummyResponse(payload=payload)

    monkeypatch.setattr(connectors.time, "sleep", lambda _: None)
    monkeypatch.setattr(connectors.requests, "get", flaky_get)
    entries = connectors.fetch_github_issues("owner/repo")
    assert len(entries) == 1
    assert calls["count"] == 2


def test_fetch_rss_feed_returns_empty_on_304_and_only_touches_accessed_at(monkeypatch, tmp_path: Path):
    meta_path = tmp_path / "logs" / "fetch_meta.json"
    key = "https://example.com/rss"
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    meta_path.write_text(
        json.dumps({key: {"etag": "abc", "last_modified": "Mon, 01 Jan 2024 00:00:00 GMT"}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(connectors, "FETCH_META_PATH", meta_path)

    def fake_get(url, params=None, headers=None, timeout=0):
        assert headers["If-None-Match"] == "abc"
        assert headers["If-Modified-Since"] == "Mon, 01 Jan 2024 00:00:00 GMT"
        return DummyResponse(text="", status_code=304)

    monkeypatch.setattr(connectors.requests, "get", fake_get)
    entries = connectors.fetch_rss_feed("https://example.com/rss")
    assert entries == []

    saved = json.loads(meta_path.read_text(encoding="utf-8"))
    assert saved[key]["etag"] == "abc"
    assert saved[key]["last_modified"] == "Mon, 01 Jan 2024 00:00:00 GMT"
    assert "accessed_at" in saved[key]


def test_fetch_github_updates_meta_on_200(monkeypatch, tmp_path: Path):
    meta_path = tmp_path / "logs" / "fetch_meta.json"
    monkeypatch.setattr(connectors, "FETCH_META_PATH", meta_path)
    payload = [{"title": "Issue A", "body": "Body A", "html_url": "https://example/a"}]

    def fake_get(url, params=None, headers=None, timeout=0):
        return DummyResponse(
            payload=payload,
            status_code=200,
            headers={"ETag": '"new-tag"', "Last-Modified": "Tue, 02 Jan 2024 00:00:00 GMT"},
        )

    monkeypatch.setattr(connectors.requests, "get", fake_get)
    entries = connectors.fetch_github_issues("owner/repo", state="open", limit=20)
    assert len(entries) == 1

    key = "https://api.github.com/repos/owner/repo/issues?per_page=20&state=open"
    saved = json.loads(meta_path.read_text(encoding="utf-8"))
    assert saved[key]["etag"] == '"new-tag"'
    assert saved[key]["last_modified"] == "Tue, 02 Jan 2024 00:00:00 GMT"
    assert "accessed_at" in saved[key]


def test_fetch_github_waits_on_429_retry_after(monkeypatch):
    responses = iter(
        [
            DummyResponse(status_code=429, headers={"Retry-After": "7"}),
            DummyResponse(payload=[{"title": "Issue A", "body": "Body", "html_url": "https://example/a"}], status_code=200),
        ]
    )
    sleeps: list[float] = []

    def fake_get(url, params=None, headers=None, timeout=0):
        return next(responses)

    monkeypatch.setattr(connectors.requests, "get", fake_get)
    monkeypatch.setattr(connectors.time, "sleep", lambda sec: sleeps.append(sec))
    entries = connectors.fetch_github_issues("owner/repo")

    assert len(entries) == 1
    assert sleeps == [7.0]


def test_fetch_github_waits_on_remaining_zero_with_reset(monkeypatch):
    responses = iter(
        [
            DummyResponse(status_code=200, headers={"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": "1015"}),
            DummyResponse(payload=[{"title": "Issue A", "body": "Body", "html_url": "https://example/a"}], status_code=200),
        ]
    )
    sleeps: list[float] = []

    def fake_get(url, params=None, headers=None, timeout=0):
        return next(responses)

    monkeypatch.setenv("CONNECTOR_MAX_WAIT_SEC", "30")
    monkeypatch.setattr(connectors.time, "time", lambda: 1000.0)
    monkeypatch.setattr(connectors.requests, "get", fake_get)
    monkeypatch.setattr(connectors.time, "sleep", lambda sec: sleeps.append(sec))
    entries = connectors.fetch_github_issues("owner/repo")

    assert len(entries) == 1
    assert sleeps == [15.0]
