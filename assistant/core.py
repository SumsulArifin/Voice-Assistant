"""The assistant: ties speech, NLU and actions together."""
from __future__ import annotations

import time
import webbrowser
from datetime import datetime
from typing import Callable, Optional

from .actions import basic
from .actions.custom import CustomCommands, is_safe_url, spoken_to_url
from .actions.email_sender import (EmailError, load_contacts, resolve_recipient, send_email)
from .actions.qa import KnowledgeBase
from .actions.reminders import MAX_SECONDS, ReminderManager, humanize_duration
from .actions.weather import WeatherError, fetch_weather
from .config import Config
from .nlu import Intent, IntentClassifier, find_durations
from .speech import NoSpeech, NotUnderstood, SpeechServiceError
from .text import parse_yes_no

MAX_SERVICE_ERRORS = 3


class Assistant:
    def __init__(self, config: Config, speaker, listener, *,
                 nlu: Optional[IntentClassifier] = None,
                 reminders: Optional[ReminderManager] = None,
                 custom: Optional[CustomCommands] = None,
                 kb: Optional[KnowledgeBase] = None,
                 session=None,
                 opener: Callable[[str], object] = webbrowser.open,
                 now: Callable[[], datetime] = datetime.now,
                 smtp_factory=None,
                 debug: bool = False):
        self.cfg = config
        self.speaker = speaker
        self.listener = listener
        self.nlu = nlu or IntentClassifier()
        self.reminders = reminders or ReminderManager()
        self.custom = custom or CustomCommands(config.custom_commands_path)
        self.kb = kb or KnowledgeBase.from_file(config.knowledge_base_path,
                                                config.enable_wikipedia, session)
        self.session = session
        self.opener = opener
        self.now = now
        self.smtp_factory = smtp_factory
        self.debug = debug
        self._service_errors = 0
        self._stop = False

    # ------------------------------------------------------------ I/O helpers
    def say(self, text: str) -> None:
        self.speaker.speak(text)

    def listen(self, retries: int = 3) -> Optional[str]:
        """Listen once; if speech wasn't understood, ask the user to repeat."""
        for attempt in range(retries):
            try:
                text = self.listener.listen()
                self._service_errors = 0
                return text
            except NoSpeech:
                return None
            except NotUnderstood:
                if attempt < retries - 1:
                    self.say("Sorry, I didn't catch that. Could you please repeat?")
                else:
                    self.say("I'm still having trouble understanding. Let's try again in a moment.")
            except SpeechServiceError:
                self._service_errors += 1
                if self._service_errors >= MAX_SERVICE_ERRORS:
                    self.say("I can't reach the speech recognition service. Please check your "
                             "internet connection, or run me with the text option. Shutting down.")
                    self._stop = True
                else:
                    self.say("I couldn't reach the speech recognition service. Trying again.")
                    time.sleep(1)
                return None
        return None

    def ask(self, prompt: str) -> Optional[str]:
        self.say(prompt)
        return self.listen()

    def confirm(self, prompt: str) -> bool:
        return parse_yes_no(self.ask(prompt)) is True

    # ------------------------------------------------------------- main loop
    def announce_reminders(self) -> None:
        for reminder in self.reminders.pop_due():
            self.say(reminder.spoken)

    def run(self) -> None:
        self.say("Voice assistant ready. Say help to hear what I can do.")
        try:
            while not self._stop:
                self.announce_reminders()
                text = self.listen()
                if text is None:
                    continue
                if not self.handle(text):
                    break
        finally:
            self.reminders.cancel_all()

    def handle(self, text: str) -> bool:
        """Process one utterance. Returns False when the assistant should quit."""
        text = text.strip()
        if not text:
            return True
        command = self.custom.match(text)
        if command:
            self._run_custom(command)
            return True
        intent = self.nlu.parse(text)
        if self.debug:
            print(f"[debug] {intent.name} ({intent.score}) {intent.slots}")
        handler = getattr(self, f"_do_{intent.name}", self._do_unknown)
        return handler(intent) is not False

    # --------------------------------------------------------------- intents
    def _do_greeting(self, intent: Intent) -> None:
        self.say(basic.greeting())

    def _do_smalltalk(self, intent: Intent) -> None:
        self.say(str(intent.slots["reply"]))

    def _do_help(self, intent: Intent) -> None:
        self.say(basic.HELP_TEXT)
        if self.custom.commands:
            self.say(self.custom.describe())

    def _do_exit(self, intent: Intent) -> bool:
        self.say("Goodbye!")
        return False

    def _do_unknown(self, intent: Intent) -> None:
        self.say("Sorry, I'm not sure how to help with that. Say help to hear what I can do.")

    def _do_time(self, intent: Intent) -> None:
        reply = basic.time_text(self.now())
        if "date" in intent.text.lower():
            reply += " " + basic.date_text(self.now())
        self.say(reply)

    def _do_date(self, intent: Intent) -> None:
        reply = basic.date_text(self.now())
        if "time" in intent.text.lower():
            reply += " " + basic.time_text(self.now())
        self.say(reply)

    def _do_web_search(self, intent: Intent) -> None:
        query = intent.slots.get("query") or self.ask("What would you like me to search for?")
        if not query:
            self.say("Okay, cancelled.")
            return
        self.say(basic.web_search(str(query), self.opener))

    def _do_weather(self, intent: Intent) -> None:
        city = intent.slots.get("city") or self.cfg.default_city
        try:
            self.say(fetch_weather(str(city), self.cfg.weather_api_key, self.cfg.units, self.session))
        except WeatherError as exc:
            self.say(str(exc))

    def _do_knowledge(self, intent: Intent) -> None:
        answer = self.kb.answer(intent.text)
        self.say(answer or "Sorry, I couldn't find a reliable answer to that. "
                           "You could say 'search for' followed by your question instead.")

    def _do_set_reminder(self, intent: Intent) -> None:
        seconds = intent.slots.get("seconds")
        if not seconds:
            reply = self.ask("How long from now should I set it for?")
            seconds = find_durations(reply or "")[0] or None
        if not seconds:
            self.say("Sorry, I couldn't work out the time. Please try again.")
            return
        if seconds > MAX_SECONDS:
            self.say("I can set reminders up to 24 hours ahead.")
            return
        message = intent.slots.get("message") or ""
        self.reminders.add(int(seconds), str(message))
        suffix = f" to {message}" if message else ""
        self.say(f"Okay, I'll remind you in {humanize_duration(seconds)}{suffix}.")

    def _do_send_email(self, intent: Intent) -> None:
        if not self.cfg.email_configured:
            self.say("Email isn't set up yet. Add your test email account details to the dot env file.")
            return
        contacts = load_contacts(self.cfg.contacts_path)
        to = resolve_recipient(str(intent.slots.get("recipient") or ""), contacts)
        if not to:
            reply = self.ask("Who should I send it to? Say a contact name, or spell the address "
                             "using 'at' and 'dot'.")
            from .nlu import spoken_to_email
            to = resolve_recipient(spoken_to_email(reply or ""), contacts)
        if not to:
            self.say("I couldn't get a valid recipient, so I've cancelled the email.")
            return
        subject = intent.slots.get("subject") or self.ask("What's the subject?")
        body = intent.slots.get("body") or self.ask("What should the message say?")
        if not subject or not body:
            self.say("I didn't get the whole message, so I've cancelled the email.")
            return
        if not self.confirm(f"I'll email {to} with subject {subject}, saying: {body}. Shall I send it?"):
            self.say("Okay, I won't send it.")
            return
        try:
            send_email(self.cfg, to, str(subject), str(body), self.smtp_factory)
            self.say("Your email has been sent.")
        except EmailError as exc:
            self.say(str(exc))

    def _do_add_command(self, intent: Intent) -> None:
        phrase = self.ask("What phrase should trigger the new command?")
        if not phrase:
            return self.say("Okay, cancelled.")
        kind = (self.ask("Should it say something back, or open a website? Say 'reply' or 'website'.") or "").lower()
        if any(w in kind for w in ("web", "site", "open", "url", "link")):
            action = "url"
            value = spoken_to_url(self.ask("Which website? For example, say example dot com.") or "")
            if not is_safe_url(value):
                return self.say("That doesn't sound like a valid website, so I've cancelled.")
        elif "reply" in kind or "say" in kind:
            action = "reply"
            value = self.ask("What should I say back?") or ""
        else:
            return self.say("I didn't understand that choice, so I've cancelled.")
        if not value:
            return self.say("I didn't catch that, so I've cancelled.")
        if not self.confirm(f"Add command: when you say {phrase}, I will "
                            f"{'open ' if action == 'url' else 'say '}{value}. Is that right?"):
            return self.say("Okay, I haven't added it.")
        try:
            self.custom.add(phrase, action, value)
            self.say("Done. Your new command is saved.")
        except ValueError as exc:
            self.say(str(exc))

    def _run_custom(self, command: dict) -> None:
        if command["action"] == "url":
            self.opener(command["value"])
            self.say("Opening it now.")
        else:
            self.say(command["value"])
