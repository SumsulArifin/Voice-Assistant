"""Command-line entry point:  python -m assistant [--text] [--mute] [--debug]"""
from __future__ import annotations

import argparse
import sys

from .actions.reminders import Reminder, ReminderManager
from .config import Config
from .core import Assistant
from .speech import MicListener, Speaker, TextListener, beep


def _alert(reminder: Reminder) -> None:
    print(f"\n*** {reminder.spoken} ***")
    beep()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Python voice assistant (advanced tier)")
    parser.add_argument("--text", action="store_true", help="type commands instead of using the microphone")
    parser.add_argument("--mute", action="store_true", help="print replies without speaking them")
    parser.add_argument("--debug", action="store_true", help="show the detected intent for each command")
    parser.add_argument("--env", help="path to a .env file (default: ./.env)")
    args = parser.parse_args(argv)

    cfg = Config.load(args.env)
    if args.text:
        listener = TextListener()
    else:
        try:
            listener = MicListener(cfg.language, cfg.stt_engine)
        except Exception as exc:
            print(f"Could not start the microphone: {exc}\n"
                  "Install SpeechRecognition and PyAudio (see README), or run with --text.",
                  file=sys.stderr)
            return 2

    assistant = Assistant(cfg, Speaker(enabled=not args.mute), listener,
                          reminders=ReminderManager(alert=_alert), debug=args.debug)
    try:
        assistant.run()
    except KeyboardInterrupt:
        print("\nGoodbye!")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
