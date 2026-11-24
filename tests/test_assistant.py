"""End-to-end conversations using a scripted listener instead of a microphone."""
from datetime import datetime

from assistant.actions.custom import CustomCommands
from assistant.actions.qa import KnowledgeBase
from assistant.actions.reminders import ReminderManager
from assistant.config import Config
from assistant.core import Assistant
from assistant.speech import NoSpeech, NotUnderstood, SpeechServiceError
from tests.test_actions import FakeResponse, FakeSession, FakeSMTP, FakeTimer, WEATHER_JSON


class ScriptedListener:
    """Each item is text to return, or an exception class/instance to raise."""

    def __init__(self, *items):
        self.items = list(items)

    def listen(self):
        item = self.items.pop(0)
        if isinstance(item, type) and issubclass(item, Exception):
            raise item()
        if isinstance(item, Exception):
            raise item
        return item


class RecordingSpeaker:
    def __init__(self):
        self.said = []

    def speak(self, text):
        self.said.append(text)


def make(tmp_path, *script, **kw):
    cfg = Config(weather_api_key="KEY", default_city="Dhaka", smtp_host="h", smtp_user="me@test.dev",
                 smtp_password="pw", email_from="me@test.dev",
                 custom_commands_path=tmp_path / "cc.json", contacts_path=tmp_path / "contacts.json")
    (tmp_path / "contacts.json").write_text('{"alice": "alice@example.com"}')
    speaker = RecordingSpeaker()
    opened = []
    a = Assistant(cfg, speaker, ScriptedListener(*script),
                  kb=kw.pop("kb", KnowledgeBase([], wikipedia=False)),
                  reminders=ReminderManager(timer_factory=FakeTimer),
                  opener=opened.append, now=lambda: datetime(2026, 11, 24, 15, 30),
                  smtp_factory=FakeSMTP, **kw)
    a.opened = opened
    return a, speaker


def test_hello_time_date_search(tmp_path):
    a, sp = make(tmp_path)
    for phrase in ("hello", "what time is it", "what's the date", "search for cute cats"):
        a.handle(phrase)
    assert "Hello" in sp.said[0]
    assert sp.said[1] == "The time is 3:30 PM."
    assert sp.said[2] == "Today is Tuesday, November 24, 2026."
    assert a.opened == ["https://www.google.com/search?q=cute+cats"]


def test_search_asks_for_topic_when_missing(tmp_path):
    a, sp = make(tmp_path, "open source licences")
    a.handle("search the web")
    assert sp.said[0].startswith("What would you like")
    assert a.opened and "open+source+licences" in a.opened[0]


def test_repeat_prompt_when_not_understood(tmp_path):
    a, sp = make(tmp_path, NotUnderstood, NotUnderstood, "hello", "goodbye")
    a.run()
    assert sum("Could you please repeat" in s for s in sp.said) == 2
    assert any("Hello" in s for s in sp.said) and sp.said[-1] == "Goodbye!"


def test_gives_up_after_three_failures_and_silence_is_ignored(tmp_path):
    a, sp = make(tmp_path, NotUnderstood, NotUnderstood, NotUnderstood, NoSpeech, "bye")
    a.run()
    assert any("still having trouble" in s for s in sp.said)
    assert sp.said[-1] == "Goodbye!"


def test_service_outage_shuts_down(tmp_path, monkeypatch):
    monkeypatch.setattr("assistant.core.time.sleep", lambda s: None)
    a, sp = make(tmp_path, SpeechServiceError, SpeechServiceError, SpeechServiceError)
    a.run()
    assert "Shutting down" in sp.said[-1]


def test_weather_default_and_named_city(tmp_path):
    s = FakeSession(FakeResponse(200, WEATHER_JSON), FakeResponse(404))
    a, sp = make(tmp_path, session=s)
    a.handle("how's the weather")
    a.handle("weather in Atlantis")
    assert s.calls[0][1]["params"]["q"] == "Dhaka"
    assert s.calls[1][1]["params"]["q"] == "Atlantis"
    assert "light rain" in sp.said[0] and "couldn't find" in sp.said[1]


def test_reminder_set_and_announced(tmp_path):
    a, sp = make(tmp_path)
    a.handle("remind me in 10 minutes to stretch")
    assert sp.said[0] == "Okay, I'll remind you in 10 minutes to stretch."
    timer = a.reminders._timers[0]
    assert timer.seconds == 600
    timer.fn(*timer.args)
    a.announce_reminders()
    assert sp.said[-1] == "Reminder: stretch."


def test_reminder_asks_duration(tmp_path):
    a, sp = make(tmp_path, "twenty minutes")
    a.handle("set a reminder")
    assert a.reminders._timers[0].seconds == 1200


def test_email_full_flow_with_confirmation(tmp_path):
    FakeSMTP.sent.clear()
    a, sp = make(tmp_path, "yes")
    a.handle("send an email to alice about lunch saying are we still on for noon")
    assert FakeSMTP.sent[0]["To"] == "alice@example.com"
    assert FakeSMTP.sent[0]["Subject"] == "lunch"
    assert sp.said[-1] == "Your email has been sent."


def test_email_asks_for_missing_details_and_can_be_declined(tmp_path):
    FakeSMTP.sent.clear()
    a, sp = make(tmp_path, "alice", "Quick question", "Do you have a minute", "no")
    a.handle("send an email")
    assert FakeSMTP.sent == [] and sp.said[-1] == "Okay, I won't send it."


def test_email_not_configured(tmp_path):
    a, sp = make(tmp_path)
    a.cfg.smtp_host = ""
    a.handle("send an email to alice saying hi")
    assert "isn't set up" in sp.said[0]


def test_general_knowledge_local_and_unknown(tmp_path):
    kb = KnowledgeBase([{"questions": ["what is the capital of france"], "answer": "Paris."}], wikipedia=False)
    a, sp = make(tmp_path, kb=kb)
    a.handle("what's the capital of France?")
    a.handle("who won the 1987 chess olympiad")
    assert sp.said[0] == "Paris." and "couldn't find a reliable answer" in sp.said[1]


def test_add_and_use_custom_command_by_voice(tmp_path):
    a, sp = make(tmp_path, "good luck", "reply", "You've got this", "yes")
    a.handle("add a custom command")
    a.handle("good luck")
    assert sp.said[-1] == "You've got this"
    assert CustomCommands(tmp_path / "cc.json").match("good luck")


def test_custom_website_command(tmp_path):
    a, sp = make(tmp_path, "open my docs", "website", "docs dot python dot org", "yes")
    a.handle("create a new command")
    a.handle("open my docs")
    assert a.opened == ["https://docs.python.org"]


def test_unknown_and_exit(tmp_path):
    a, sp = make(tmp_path)
    assert a.handle("purple monkey dishwasher") is True
    assert "not sure" in sp.said[0]
    assert a.handle("goodbye") is False
