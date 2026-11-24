# Python Voice Assistant (Advanced Tier)

A voice assistant that listens through your microphone, works out what you mean from
free-form sentences, and answers out loud. It includes every Beginner and Advanced feature
from the checklist.

## Features

| Checklist item | Where / how |
|---|---|
| Voice input with `speech_recognition` | `assistant/speech.py` (`MicListener`) |
| "Hello" greeting | `actions/basic.py` |
| Current time and date | `actions/basic.py` |
| Web search (opens browser) | `actions/basic.py` |
| Ask to repeat when not understood | `core.py` `Assistant.listen()` (3 tries, then backs off) |
| Spoken replies with `pyttsx3` | `speech.py` (`Speaker`); every reply goes through it |
| Natural language understanding | `nlu.py`: TF-IDF similarity + slot extraction (not plain keyword matching) |
| Email by voice (`smtplib`) | `actions/email_sender.py`, with spoken confirmation before sending |
| Timed reminders with audible alert | `actions/reminders.py` |
| Live weather (OpenWeatherMap) | `actions/weather.py` |
| General-knowledge Q&A | `actions/qa.py`: local `knowledge_base.json`, then Wikipedia |
| Custom commands | `custom_commands.json` or by voice ("add a custom command") |
| Privacy documentation | see [Privacy](#privacy-what-data-is-processed-and-how) |

## Setup

Requires Python 3.9+.

```bash
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                   # then edit it
```

**PyAudio (microphone access) by OS**

- **Windows:** `pip install pyaudio` normally works. If it fails, use `pip install pipwin && pipwin install pyaudio`.
- **macOS:** `brew install portaudio` then `pip install pyaudio`.
- **Linux (Debian/Ubuntu):** `sudo apt install portaudio19-dev python3-pyaudio espeak-ng` then `pip install pyaudio`.
  (`espeak-ng` is the voice `pyttsx3` uses on Linux.)

See the [SpeechRecognition page on PyPI](https://pypi.org/project/SpeechRecognition/) for more detail.

**Free API keys / accounts**

1. **Weather:** register at [openweathermap.org](https://openweathermap.org), copy the key into
   `OPENWEATHER_API_KEY`. New keys can take up to ~2 hours to activate.
2. **Email:** use a **test or dummy account only**. For Gmail, enable 2-step verification and create an
   *app password*, or use a sandbox inbox such as Mailtrap or Ethereal. Fill in `SMTP_*` in `.env`.
   Add contacts by name in `contacts.json`.

## Running

```bash
python -m assistant              # microphone mode
python -m assistant --text       # type commands instead (no mic needed)
python -m assistant --mute       # print replies without speaking
python -m assistant --debug      # show detected intent + slots
python -m pytest                 # run the tests
```

## Things to say

- "Hello" / "Good morning"
- "What time is it?" / "What's today's date?"
- "Search for Python tutorials" / "Look up the Eiffel Tower"
- "Will I need an umbrella in Dhaka?" / "What's the weather like?" (uses `DEFAULT_CITY`)
- "Send an email to alice saying I'll be late". Missing details (subject, body) are asked for, and
  it reads the email back and waits for a yes before sending.
- "Remind me in ten minutes to stretch" / "Set a timer for an hour and a half"
- "Who invented the telephone?" / "What is the capital of France?"
- "Add a custom command", then follow the prompts. Say "what can you do" for the full list.
- "Goodbye"

## How the natural language understanding works

1. Durations ("in an hour and a half", "twenty five minutes") are detected and masked.
2. The sentence is compared with several example phrasings per intent using TF-IDF cosine
   similarity (tokenised, stop words removed, light stemming). "Will I need an umbrella in Dhaka"
   reaches the weather intent without containing the word "weather".
3. Small regex boosts add confidence when there is a strong signal (e.g. "remind" plus a duration).
4. Slots are extracted: city, search query, duration, reminder message, email recipient, subject and body.
   Spoken addresses like "john at example dot com" become `john@example.com`.
5. Low-confidence, question-shaped sentences go to the general-knowledge handler.

To add an intent, add example sentences to `INTENT_EXAMPLES` in `assistant/nlu.py` and a `_do_<intent>`
method in `assistant/core.py`. `nltk` or `transformers` could replace the classifier later without
touching the rest of the code, since `IntentClassifier.parse()` is the only interface.

## Custom commands

`custom_commands.json` holds a list like:

```json
{"phrases": ["tell me a joke"], "action": "reply", "value": "Why do programmers prefer dark mode? ..."}
{"phrases": ["open youtube"],   "action": "url",   "value": "https://www.youtube.com"}
```

Custom commands are checked before the built-in intents and tolerate small speech-recognition slips.
Only `reply` (speak text) and `url` (open an http/https site) are supported. Voice commands deliberately
cannot run shell commands.

## Privacy: what data is processed and how

| Data | Where it goes | Stored? |
|---|---|---|
| **Microphone audio** | Captured only while the assistant is listening (the "(listening...)" prompt). With the default `STT_ENGINE=google` each recording is sent to Google's free Web Speech API for transcription. With `STT_ENGINE=sphinx` (needs `pocketsphinx`) transcription happens fully offline. | Never saved to disk by this program. |
| **Transcribed text** | Processed in memory by the local NLU. Printed in your terminal. | Not logged or saved. |
| **City name** (weather) | Sent to OpenWeatherMap together with your API key. | Not stored by this program. |
| **Question text** (general knowledge) | Answered locally if possible. Otherwise the topic is sent to the Wikipedia API. Set `ENABLE_WIKIPEDIA=false` to keep questions fully local. | Not stored. |
| **Email recipient, subject, body** | Sent to your SMTP server only after you say yes to the read-back. | Not stored locally. |
| **Web searches** | Opens your browser on a Google search page. Google's own policies apply from there. | Browser history only. |
| **Credentials** (`.env`) | Read locally. Only sent to the matching service (OpenWeatherMap, your SMTP server). | Stored in `.env`. Keep it out of version control. |
| **Custom commands, contacts** | Plain JSON files on your machine. | Yes, until you delete them. |

Other notes:

- The assistant has no wake word: while running it records in short windows and sends each one for
  transcription. Quit with "goodbye" or Ctrl+C when you don't want it listening.
- Use a throwaway email account. Voice transcription can mishear recipients, which is why the
  assistant always reads the email back first.
- There is no telemetry, analytics or account system.

## Project layout

```
assistant/
  main.py          CLI entry point and flags
  core.py          Assistant: listen -> understand -> act -> speak
  nlu.py           intent classification and slot extraction
  text.py          tokenising, stemming, TF-IDF matcher
  speech.py        MicListener, TextListener, Speaker, beep
  config.py        .env loading
  actions/         basic, weather, email_sender, reminders, qa, custom
tests/             76 tests, none needing a microphone or network
```

## Known limitations

- Reminders sound a terminal beep immediately (winsound tone on Windows), and the spoken message follows
  as soon as the assistant is next free, usually within a few seconds. Text-to-speech engines are not
  thread-safe, so the timer thread does not speak directly. Reminders live in memory and are lost when you quit.
- Weather is current conditions only, not a forecast.
- Wikipedia answers are the opening sentences of the best-matching article. They are good for "what/who
  is" questions but can miss on tricky or multi-part ones.
- Microphone and text-to-speech were not exercised in automated tests (the build environment has no audio
  hardware). The tests cover everything else through a scripted listener.
