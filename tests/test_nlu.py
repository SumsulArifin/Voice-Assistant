import pytest

from assistant.nlu import IntentClassifier, find_durations, spoken_to_email

nlu = IntentClassifier()


@pytest.mark.parametrize("text,intent", [
    ("hello", "greeting"),
    ("hey there", "greeting"),
    ("good morning", "greeting"),
    ("what time is it", "time"),
    ("could you tell me the current time", "time"),
    ("what's today's date", "date"),
    ("what day is it", "date"),
    ("search for python tutorials", "web_search"),
    ("google best pizza recipes", "web_search"),
    ("what's the weather like in Dhaka", "weather"),
    ("will I need an umbrella in London", "weather"),
    ("how hot is it outside", "weather"),
    ("send an email to alice saying hello", "send_email"),
    ("I want to email bob about the meeting", "send_email"),
    ("remind me in 10 minutes to stretch", "set_reminder"),
    ("set a timer for 5 minutes", "set_reminder"),
    ("wake me up in an hour", "set_reminder"),
    ("add a custom command", "add_command"),
    ("goodbye", "exit"),
    ("stop listening", "exit"),
    ("what can you do", "help"),
    ("how are you", "smalltalk"),
    ("what is the capital of Peru", "knowledge"),
    ("who invented the telephone", "knowledge"),
    ("purple monkey dishwasher", "unknown"),
])
def test_intent(text, intent):
    assert nlu.parse(text).name == intent


def test_search_query_slot():
    assert nlu.parse("please search the web for best python tutorials").slots["query"] == "best python tutorials"
    assert nlu.parse("look up the eiffel tower").slots["query"] == "the eiffel tower"


@pytest.mark.parametrize("text,city", [
    ("what's the weather in New York today", "New York"),
    ("weather in dhaka", "Dhaka"),
    ("will I need an umbrella in London", "London"),
    ("how's the weather", None),
    ("what's the weather for today", None),
])
def test_city_slot(text, city):
    assert nlu.parse(text).slots["city"] == city


@pytest.mark.parametrize("text,seconds", [
    ("remind me in 10 minutes to stretch", 600),
    ("set a timer for 30 seconds", 30),
    ("wake me up in an hour", 3600),
    ("remind me in half an hour", 1800),
    ("timer for an hour and a half", 5400),
    ("remind me in 1 hour 30 minutes", 5400),
    ("set a timer for twenty five minutes", 1500),
    ("remind me in two hours to call mom", 7200),
])
def test_durations(text, seconds):
    assert find_durations(text)[0] == seconds


def test_reminder_message_slot():
    assert nlu.parse("remind me in 10 minutes to stretch").slots["message"] == "stretch"
    assert nlu.parse("remind me to call mom in 2 hours").slots["message"] == "call mom"
    assert nlu.parse("set a timer for 5 minutes").slots["message"] is None


def test_email_slots():
    s = nlu.parse("send an email to john at example dot com saying see you at noon").slots
    assert s["recipient"] == "john@example.com"
    assert s["body"] == "see you at noon"
    s = nlu.parse("email bob about the meeting").slots
    assert s.get("subject") == "the meeting"


def test_spoken_email():
    assert spoken_to_email("Jane Doe at Mail dot example dot com") == "janedoe@mail.example.com"
