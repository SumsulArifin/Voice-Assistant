"""WSGI entrypoint for hosts that only run WSGI (e.g. PythonAnywhere free tier).

Point your host's WSGI config at this module's `application`. It just wraps
the real ASGI app (assistant.api.app) with a2wsgi's adapter.
"""
from a2wsgi import ASGIMiddleware

from assistant.api import app as _asgi_app

application = ASGIMiddleware(_asgi_app)
