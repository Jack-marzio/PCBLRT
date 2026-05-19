# -*- coding: utf-8 -*-
"""
wsgi.py
Entry point per gunicorn su Fly.io.

Gunicorn avvia questo modulo; qui inizializziamo WebDashboard
(che crea l'app Flask internamente) e esponiamo `app` a gunicorn.

Avvio locale di test:
    gunicorn -k geventwebsocket.gunicorn.workers.GeventWebSocketWorker \
             -w 1 -b 0.0.0.0:8080 wsgi:app

Fly.io usa il CMD del Dockerfile che punta qui.
"""

import os
import secrets

import sys as _sys, os as _os
_sys.path.insert(0, _os.path.join(_os.path.dirname(__file__), 'app'))

from web_dashboard import WebDashboard

# ── Inizializzazione dashboard ────────────────────────────────────────────
TOKEN       = os.environ.get("WS_TOKEN") or secrets.token_urlsafe(32)
PORT        = int(os.environ.get("PORT", 8080))
FLY_APP     = os.environ.get("FLY_APP_NAME")
PUBLIC_HOST = f"{FLY_APP}.fly.dev" if FLY_APP else None

_dashboard = WebDashboard(
    host        = "0.0.0.0",
    port        = PORT,
    token       = TOKEN,
    public_host = PUBLIC_HOST,
)

# ── Esponi l'app Flask a gunicorn ─────────────────────────────────────────
# gunicorn cerca la variabile `app` in questo modulo
app = _dashboard._app

if not os.environ.get("WS_TOKEN"):
    print(
        f"\n  ⚠️  WS_TOKEN non impostato — token generato: {TOKEN}\n"
        f"     Usa: fly secrets set WS_TOKEN=\"{TOKEN}\"\n"
    )

print(f"\n  📡  Dashboard → {_dashboard.link}\n")
