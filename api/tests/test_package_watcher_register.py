"""Unit tests for watcher metadata registration HTTP call."""

import json
import os
import sys


_REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

import watcher.package_watcher as package_watcher


class _FakeResponse:
    def __init__(self, body: str):
        self._body = body.encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        return False

    def read(self):
        return self._body


def test_watcher_register_package_posts_metadata(monkeypatch):
    captured = {}

    def _fake_urlopen(request, timeout):
        captured["request"] = request
        captured["timeout"] = timeout
        return _FakeResponse('{"id": 42, "name": "watcher-agent", "version": "1.2.3"}')

    monkeypatch.setattr(package_watcher, "API_BASE_URL", "http://localhost:8080")
    monkeypatch.setattr(package_watcher, "API_TOKEN", "token-123")
    monkeypatch.setattr(package_watcher.urllib.request, "urlopen", _fake_urlopen)

    ok, error, data = package_watcher.register_package(
        {
            "name": "watcher-agent",
            "version": "1.2.3",
            "language": "python",
            "entrypoint": "main.py",
            "timeout_seconds": 90,
        },
        "watcher-agent.zip",
    )

    assert ok is True
    assert error is None
    assert data["id"] == 42

    request = captured["request"]
    assert request.full_url == "http://localhost:8080/packages/register"
    assert captured["timeout"] == 30

    payload = json.loads(request.data.decode("utf-8"))
    assert payload["name"] == "watcher-agent"
    assert payload["filename"] == "watcher-agent.zip"
    assert payload["timeout_seconds"] == 90
    assert payload["deployment"] == "local"


def test_watcher_register_package_extracts_schedule_and_secrets(monkeypatch):
    captured = {}

    def _fake_urlopen(request, timeout):
        captured["request"] = request
        captured["timeout"] = timeout
        return _FakeResponse('{"id": 77, "name": "schedule-secret-agent", "version": "1.0.0"}')

    monkeypatch.setattr(package_watcher, "API_BASE_URL", "http://localhost:8080")
    monkeypatch.setattr(package_watcher.urllib.request, "urlopen", _fake_urlopen)

    ok, error, data = package_watcher.register_package(
        {
            "name": "schedule-secret-agent",
            "version": "1.0.0",
            "schedule": {
                "type": "cron",
                "cron_expression": "*/10 * * * *",
                "enabled": True,
            },
            "expose": {"port": 8000},
            "environment": {
                "TAVILY_API_KEY": "{secrets.TAVILY_API_KEY}",
                "LOG_LEVEL": "INFO",
            },
            "secrets": ["EXTRA_SECRET"],
            "deployment": "container",
        },
        "schedule-secret-agent.zip",
    )

    assert ok is True
    assert error is None
    assert data["id"] == 77

    payload = json.loads(captured["request"].data.decode("utf-8"))
    assert payload["schedule_enabled"] is True
    assert payload["schedule_type"] == "cron"
    assert payload["schedule_config"]["cron_expr"] == "*/10 * * * *"
    assert payload["secret_keys"] == ["EXTRA_SECRET", "TAVILY_API_KEY"]
    assert payload["deployment"] == "container"
    assert payload["exposed_port"] == 8000



def test_watcher_register_package_requires_name(monkeypatch):
    def _unexpected_urlopen(_request, _timeout):
        raise AssertionError("urlopen should not be called when manifest name is missing")

    monkeypatch.setattr(package_watcher.urllib.request, "urlopen", _unexpected_urlopen)

    ok, error, data = package_watcher.register_package({"version": "1.0.0"}, "missing-name.zip")

    assert ok is False
    assert "name" in error.lower()
    assert data is None
