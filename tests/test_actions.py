import json
from datetime import datetime
from types import SimpleNamespace

import pytest
import requests

from assistant.actions import basic
from assistant.actions.custom import CustomCommands, is_safe_url, spoken_to_url
from assistant.actions.email_sender import (EmailError, is_valid_email, resolve_recipient, send_email)
from assistant.actions.qa import KnowledgeBase, extract_topic
from assistant.actions.reminders import ReminderManager, humanize_duration
from assistant.actions.weather import WeatherError, fetch_weather


class FakeResponse:
    def __init__(self, status=200, data=None):
        self.status_code, self._data = status, data or {}

    def json(self):
        return self._data


class FakeSession:
    def __init__(self, *responses):
        self.responses, self.calls = list(responses), []

    def get(self, url, **kw):
        self.calls.append((url, kw))
        r = self.responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


# ------------------------------------------------------------------ basics
def test_time_and_date():
    now = datetime(2026, 11, 24, 9, 5)
    assert basic.time_text(now) == "The time is 9:05 AM."
    assert basic.date_text(now) == "Today is Tuesday, November 24, 2026."


def test_web_search_opens_browser():
    opened = []
    msg = basic.web_search("python tutorials & more", opened.append)
    assert opened == ["https://www.google.com/search?q=python+tutorials+%26+more"]
    assert "python tutorials" in msg


# ----------------------------------------------------------------- weather
WEATHER_JSON = {"name": "Dhaka", "weather": [{"main": "Rain", "description": "light rain"}],
                "main": {"temp": 28.4, "feels_like": 32.1, "humidity": 80}}


def test_weather_ok():
    s = FakeSession(FakeResponse(200, WEATHER_JSON))
    text = fetch_weather("Dhaka", "KEY", "metric", s)
    assert "28 degrees Celsius" in text and "light rain" in text and "umbrella" in text
    assert s.calls[0][1]["params"]["q"] == "Dhaka"


@pytest.mark.parametrize("resp,fragment", [
    (FakeResponse(401), "rejected"),
    (FakeResponse(404), "couldn't find"),
    (FakeResponse(500), "error"),
    (requests.ConnectionError(), "couldn't reach"),
])
def test_weather_errors(resp, fragment):
    with pytest.raises(WeatherError, match=fragment):
        fetch_weather("Nowhere", "KEY", session=FakeSession(resp))


def test_weather_needs_key():
    with pytest.raises(WeatherError, match="API key"):
        fetch_weather("Dhaka", "")


# ------------------------------------------------------------------- email
class FakeSMTP:
    sent = []

    def __init__(self, host, port):
        self.host, self.port = host, port

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def login(self, user, pw):
        self.user = user

    def send_message(self, msg):
        FakeSMTP.sent.append(msg)


def test_send_email_builds_message():
    cfg = SimpleNamespace(smtp_host="h", smtp_port=587, smtp_user="me@test.dev",
                          smtp_password="pw", email_from="me@test.dev")
    FakeSMTP.sent.clear()
    send_email(cfg, "you@test.dev", "Hi", "Body text", FakeSMTP)
    msg = FakeSMTP.sent[0]
    assert msg["To"] == "you@test.dev" and msg["Subject"] == "Hi"
    assert "Body text" in msg.get_content()


def test_send_email_failure_is_wrapped():
    class Boom(FakeSMTP):
        def login(self, *a):
            raise OSError("down")
    cfg = SimpleNamespace(smtp_host="h", smtp_port=587, smtp_user="u", smtp_password="p", email_from="u")
    with pytest.raises(EmailError):
        send_email(cfg, "a@b.co", "s", "b", Boom)


def test_recipient_resolution():
    contacts = {"alice": "alice@example.com"}
    assert resolve_recipient("Alice", contacts) == "alice@example.com"
    assert resolve_recipient("x@y.com", contacts) == "x@y.com"
    assert resolve_recipient("bob", contacts) is None
    assert not is_valid_email("not-an-email")


# --------------------------------------------------------------- reminders
class FakeTimer:
    def __init__(self, seconds, fn, args=()):
        self.seconds, self.fn, self.args, self.cancelled = seconds, fn, args, False
        self.daemon = False

    def start(self):
        pass

    def cancel(self):
        self.cancelled = True


def test_reminder_fires_and_alerts():
    alerts, timers = [], []

    def factory(*a, **k):
        t = FakeTimer(*a, **k)
        timers.append(t)
        return t
    mgr = ReminderManager(alert=alerts.append, timer_factory=factory)
    mgr.add(600, "stretch")
    assert mgr.pop_due() == [] and not alerts
    timers[0].fn(*timers[0].args)                       # simulate the timer elapsing
    assert alerts[0].spoken == "Reminder: stretch."
    assert [r.message for r in mgr.pop_due()] == ["stretch"]
    assert mgr.pop_due() == []
    mgr.cancel_all()
    assert timers[0].cancelled


def test_reminder_limits_and_humanize():
    mgr = ReminderManager(timer_factory=FakeTimer)
    for bad in (0, -5, 24 * 3600 + 1):
        with pytest.raises(ValueError):
            mgr.add(bad)
    assert humanize_duration(5400) == "1 hour and 30 minutes"
    assert humanize_duration(61) == "1 minute and 1 second"


def test_real_timer_fires():
    import time
    fired = []
    mgr = ReminderManager(alert=fired.append)
    mgr.add(1, "x")
    time.sleep(1.4)
    assert len(fired) == 1 and mgr.pop_due()[0].message == "x"


# --------------------------------------------------------------------- QA
KB = [{"questions": ["what is the capital of france"], "answer": "Paris."}]


def test_local_answer_preferred_no_network():
    s = FakeSession()
    kb = KnowledgeBase(KB, wikipedia=True, session=s)
    assert kb.answer("what's the capital city of France?") == "Paris."
    assert s.calls == []


def test_wikipedia_fallback():
    s = FakeSession(FakeResponse(200, {"query": {"search": [{"title": "Alexander Graham Bell"}]}}),
                    FakeResponse(200, {"extract": "Bell was an inventor. He patented the telephone. More text."}))
    kb = KnowledgeBase(KB, wikipedia=True, session=s)
    assert kb.answer("who invented the telephone") == "Bell was an inventor. He patented the telephone."
    assert s.calls[0][1]["params"]["srsearch"] == "invented the telephone"


def test_wikipedia_failures_and_disabled():
    assert KnowledgeBase(KB, True, FakeSession(requests.ConnectionError())).answer("who is zzz") is None
    s = FakeSession()
    assert KnowledgeBase(KB, False, s).answer("who is zzz") is None and s.calls == []
    assert extract_topic("what is the speed of sound?") == "speed of sound"


# ---------------------------------------------------------- custom commands
def test_custom_commands_match_add_persist(tmp_path):
    path = tmp_path / "cc.json"
    path.write_text(json.dumps([{"phrases": ["tell me a joke"], "action": "reply", "value": "Ha"}]))
    cc = CustomCommands(path)
    assert cc.match("Please tell me a joke!")["value"] == "Ha"
    assert cc.match("tell me a jokes")["value"] == "Ha"                # fuzzy (speech-to-text slips)
    assert cc.match("what is the weather") is None
    cc.add("open my blog", "url", spoken_to_url("example dot com slash blog"))
    assert CustomCommands(path).match("open my blog")["value"] == "https://example.com/blog"


def test_custom_commands_reject_unsafe(tmp_path):
    cc = CustomCommands(tmp_path / "cc.json")
    with pytest.raises(ValueError):
        cc.add("hack", "url", "file:///etc/passwd")
    with pytest.raises(ValueError):
        cc.add("run it", "shell", "rm -rf /")
    assert not is_safe_url("javascript:alert(1)")
    (tmp_path / "bad.json").write_text("not json")
    assert CustomCommands(tmp_path / "bad.json").commands == []
