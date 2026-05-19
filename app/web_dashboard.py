# -*- coding: utf-8 -*-
"""
web_dashboard.py
Dashboard web (Flask + WebSocket) per il monitoraggio in tempo reale
delle comunicazioni radio.

Locale:  python web_dashboard.py
Fly.io:  fly deploy  (usa Dockerfile incluso nel progetto)

Accesso: https://<app>.fly.dev?token=<TOKEN>
"""

import json
import logging
import threading
import hmac
import secrets
import urllib.request
import urllib.error
from typing import Callable, Optional, Set

from flask import Flask, jsonify, request, Response
from flask_sock import Sock


# ── HTML della dashboard ────────────────────────────────────────────────────

_HTML = """<!DOCTYPE html>
<html lang="it">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Radio Log — Live Monitor</title>
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link href="https://fonts.googleapis.com/css2?family=Share+Tech+Mono&family=Barlow+Condensed:wght@300;600;800&display=swap" rel="stylesheet" />
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

    :root {
      --bg:        #080c10;
      --surface:   #0d1520;
      --border:    #1a2e44;
      --accent:    #00e5ff;
      --accent2:   #ff6b35;
      --green:     #39ff14;
      --red:       #ff2d55;
      --text:      #c8d8e8;
      --text-dim:  #4a6580;
      --mono:      'Share Tech Mono', monospace;
      --sans:      'Barlow Condensed', sans-serif;
      --row-enter: 0.35s;
    }

    html, body {
      height: 100%;
      background: var(--bg);
      color: var(--text);
      font-family: var(--mono);
      overflow: hidden;
    }

    body::before {
      content: '';
      position: fixed; inset: 0; z-index: 0; pointer-events: none;
      background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)' opacity='0.04'/%3E%3C/svg%3E");
      opacity: 0.4;
    }

    #app {
      position: relative; z-index: 1;
      display: grid;
      grid-template-rows: auto auto 1fr auto auto;
      height: 100vh;
    }

    /* ── Header ── */
    header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 14px 28px;
      border-bottom: 1px solid var(--border);
      background: linear-gradient(90deg, #0d1520 0%, #091420 100%);
      gap: 16px;
    }
    .header-left { display: flex; align-items: baseline; gap: 14px; }
    .logo-mark {
      font-family: var(--sans); font-weight: 800; font-size: 1.5rem;
      letter-spacing: 0.06em; color: var(--accent); text-transform: uppercase;
    }
    .logo-sub {
      font-family: var(--sans); font-weight: 300; font-size: 0.8rem;
      color: var(--text-dim); letter-spacing: 0.12em; text-transform: uppercase;
    }
    .status-pill {
      display: flex; align-items: center; gap: 7px;
      padding: 5px 14px; border: 1px solid var(--border); border-radius: 20px;
      font-size: 0.72rem; letter-spacing: 0.1em; text-transform: uppercase;
      transition: border-color 0.3s, color 0.3s;
    }
    .status-pill.live { border-color: var(--green); color: var(--green); }
    .status-pill.dead { border-color: var(--red);   color: var(--red);   }
    .pulse {
      width: 7px; height: 7px; border-radius: 50%; background: currentColor;
      animation: pulse-anim 1.4s ease-in-out infinite;
    }
    @keyframes pulse-anim {
      0%, 100% { opacity: 1; transform: scale(1); }
      50%       { opacity: 0.4; transform: scale(0.7); }
    }

    /* ── Stats bar ── */
    .stats-bar {
      display: flex; gap: 0;
      border-bottom: 1px solid var(--border);
      background: var(--surface);
    }
    .stat {
      flex: 1; padding: 10px 20px; border-right: 1px solid var(--border);
      display: flex; flex-direction: column; gap: 2px;
    }
    .stat:last-child { border-right: none; }
    .stat-label {
      font-size: 0.62rem; letter-spacing: 0.14em;
      color: var(--text-dim); text-transform: uppercase;
    }
    .stat-value {
      font-family: var(--sans); font-weight: 600; font-size: 1.3rem;
      color: var(--accent); letter-spacing: 0.04em; transition: color 0.4s;
    }
    .stat-value.flash { color: var(--green); }

    /* ── Table ── */
    .table-wrapper {
      overflow-y: auto; padding: 0 0 8px; scroll-behavior: smooth;
    }
    .table-wrapper::-webkit-scrollbar { width: 6px; }
    .table-wrapper::-webkit-scrollbar-track { background: transparent; }
    .table-wrapper::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; }

    table { width: 100%; border-collapse: collapse; font-size: 0.78rem; }
    thead { position: sticky; top: 0; z-index: 2; background: #0a1520; }
    th {
      padding: 10px 14px; text-align: left;
      font-family: var(--sans); font-weight: 600; font-size: 0.68rem;
      letter-spacing: 0.14em; text-transform: uppercase;
      color: var(--text-dim); border-bottom: 1px solid var(--border); white-space: nowrap;
    }
    th:first-child { padding-left: 28px; }
    th:last-child  { padding-right: 28px; }

    tbody tr {
      border-bottom: 1px solid rgba(26,46,68,0.5);
      animation: row-in var(--row-enter) cubic-bezier(.2,0,.2,1) both;
    }
    @keyframes row-in {
      from { opacity: 0; transform: translateX(-12px); background: rgba(0,229,255,0.07); }
      to   { opacity: 1; transform: translateX(0);     background: transparent; }
    }
    tbody tr:hover { background: rgba(255,255,255,0.025); }

    td {
      padding: 9px 14px; vertical-align: top;
      line-height: 1.5; word-break: break-word;
    }
    td:first-child { padding-left: 28px; }
    td:last-child  { padding-right: 28px; }

    .col-time     { color: var(--text-dim); white-space: nowrap; min-width: 150px; }
    .col-sender   { color: var(--accent);   font-weight: bold;   min-width: 100px; }
    .col-receiver { color: var(--accent2);  font-weight: bold;   min-width: 100px; }
    .col-rcv      { min-width: 200px; }
    .col-snt      { min-width: 200px; }

    .seq {
      display: inline-block; min-width: 26px; padding: 1px 6px;
      border: 1px solid var(--border); border-radius: 3px;
      color: var(--text-dim); font-size: 0.68rem; text-align: center; margin-right: 8px;
    }

    /* ── Empty state ── */
    .empty-state {
      display: flex; flex-direction: column;
      align-items: center; justify-content: center;
      height: 100%; gap: 12px; color: var(--text-dim); padding: 60px 0;
    }
    .empty-state .icon {
      font-size: 2.5rem; opacity: 0.3;
      animation: blink 2s step-start infinite;
    }
    @keyframes blink {
      0%, 100% { opacity: 0.3; }
      50%       { opacity: 0.08; }
    }
    .empty-state p {
      font-size: 0.8rem; letter-spacing: 0.1em; text-transform: uppercase;
    }

    /* ── Response bar ── */
    .response-bar {
      display: flex; align-items: center; gap: 10px;
      padding: 10px 28px;
      border-top: 1px solid var(--border);
      background: var(--surface);
    }
    .response-label {
      font-size: 0.65rem; letter-spacing: 0.14em; text-transform: uppercase;
      color: var(--text-dim); white-space: nowrap;
    }
    .response-input {
      flex: 1;
      background: #0a1520;
      border: 1px solid var(--border);
      border-radius: 4px;
      color: var(--text);
      font-family: var(--mono);
      font-size: 0.8rem;
      padding: 7px 12px;
      outline: none;
      transition: border-color 0.2s;
    }
    .response-input:focus { border-color: var(--accent); }
    .response-input::placeholder { color: var(--text-dim); }
    .response-btn {
      background: transparent;
      border: 1px solid var(--accent);
      color: var(--accent);
      font-family: var(--sans);
      font-weight: 600;
      font-size: 0.75rem;
      letter-spacing: 0.12em;
      text-transform: uppercase;
      padding: 7px 20px;
      border-radius: 4px;
      cursor: pointer;
      transition: background 0.2s, color 0.2s;
      white-space: nowrap;
    }
    .response-btn:hover { background: var(--accent); color: var(--bg); }
    .response-btn:disabled { opacity: 0.3; cursor: not-allowed; }
    .response-sent {
      font-size: 0.68rem; color: var(--green);
      opacity: 0; transition: opacity 0.3s;
      letter-spacing: 0.1em; text-transform: uppercase;
    }
    .response-sent.show { opacity: 1; }

    /* ── Footer ── */
    footer {
      border-top: 1px solid var(--border);
      background: var(--surface);
      padding: 8px 28px;
      display: flex; align-items: center; justify-content: space-between;
      font-size: 0.65rem; color: var(--text-dim);
      letter-spacing: 0.08em; text-transform: uppercase;
    }
    #clock { color: var(--text); }

    body::after {
      content: '';
      position: fixed; inset: 0; z-index: 999; pointer-events: none;
      background: repeating-linear-gradient(
        to bottom,
        transparent 0px, transparent 2px,
        rgba(0,0,0,0.03) 2px, rgba(0,0,0,0.03) 4px
      );
    }
  </style>
</head>
<body>
<div id="app">

  <header>
    <div class="header-left">
      <span class="logo-mark">&#9658; RadioLog</span>
      <span class="logo-sub">Live Monitor</span>
    </div>
    <div id="status" class="status-pill dead">
      <span class="pulse"></span>
      <span id="status-text">CONNESSIONE...</span>
    </div>
  </header>

  <div class="stats-bar">
    <div class="stat">
      <span class="stat-label">Comunicazioni</span>
      <span class="stat-value" id="stat-total">0</span>
    </div>
    <div class="stat">
      <span class="stat-label">Ultima voce</span>
      <span class="stat-value" id="stat-last" style="font-size:0.9rem">—</span>
    </div>
    <div class="stat">
      <span class="stat-label">Sessione avviata</span>
      <span class="stat-value" id="stat-session" style="font-size:0.9rem">—</span>
    </div>
    <div class="stat">
      <span class="stat-label">Mittenti unici</span>
      <span class="stat-value" id="stat-senders">0</span>
    </div>
  </div>

  <div class="table-wrapper" id="table-wrapper">
    <table>
      <thead>
        <tr>
          <th>#</th>
          <th>Data / Ora</th>
          <th>Mittente</th>
          <th>Ricevente</th>
          <th>Messaggio ricevuto</th>
          <th>Messaggio trasmesso</th>
        </tr>
      </thead>
      <tbody id="log-body"></tbody>
    </table>
    <div class="empty-state" id="empty">
      <span class="icon">&#9632;</span>
      <p>In attesa di comunicazioni...</p>
    </div>
  </div>

  <!-- Barra risposta -->
  <div class="response-bar">
    <span class="response-label">Risposta &#9654;</span>
    <input
      id="response-input"
      class="response-input"
      type="text"
      placeholder="Scrivi una risposta e premi Invio..."
      disabled
    />
    <button id="response-btn" class="response-btn" disabled>Invia</button>
    <span id="response-sent" class="response-sent">✓ inviato</span>
  </div>

  <footer>
    <span>ProcivBes Radio Team Tool &mdash; Dashboard remota</span>
    <span id="clock"></span>
  </footer>

</div>

<script>
  // ── Stato ─────────────────────────────────────────────────────────
  let logs    = [];
  let senders = new Set();
  let sessionStart = null;
  let ws = null;

  // Leggi il token dall'URL
  const TOKEN = new URLSearchParams(window.location.search).get('token') || '';

  // ── DOM ───────────────────────────────────────────────────────────
  const tbody       = document.getElementById('log-body');
  const empty       = document.getElementById('empty');
  const statTotal   = document.getElementById('stat-total');
  const statLast    = document.getElementById('stat-last');
  const statSession = document.getElementById('stat-session');
  const statSend    = document.getElementById('stat-senders');
  const statusEl    = document.getElementById('status');
  const statusText  = document.getElementById('status-text');
  const wrapper     = document.getElementById('table-wrapper');
  const input       = document.getElementById('response-input');
  const btn         = document.getElementById('response-btn');
  const sentBadge   = document.getElementById('response-sent');

  // ── Clock ─────────────────────────────────────────────────────────
  function tick() {
    document.getElementById('clock').textContent =
      new Date().toLocaleTimeString('it-IT', { hour12: false });
  }
  tick();
  setInterval(tick, 1000);

  // ── Helpers ───────────────────────────────────────────────────────
  function flash(el) {
    el.classList.add('flash');
    setTimeout(() => el.classList.remove('flash'), 600);
  }

  function updateStats() {
    statTotal.textContent = logs.length;
    flash(statTotal);
    if (logs.length > 0)
      statLast.textContent = logs[logs.length - 1].date_time.slice(11, 19);
    if (!sessionStart && logs.length > 0) {
      sessionStart = logs[0].date_time;
      statSession.textContent = sessionStart.slice(11, 19);
    }
    statSend.textContent = senders.size;
    empty.style.display = logs.length === 0 ? 'flex' : 'none';
  }

  function addRow(entry, animate = true) {
    const seq = logs.length - 1;
    const tr  = document.createElement('tr');
    if (!animate) tr.style.animation = 'none';
    tr.innerHTML = `
      <td><span class="seq">${seq}</span></td>
      <td class="col-time">${entry.date_time}</td>
      <td class="col-sender">${entry.sender}</td>
      <td class="col-receiver">${entry.receiver}</td>
      <td class="col-rcv">${entry.msg_received}</td>
      <td class="col-snt">${entry.msg_sent}</td>
    `;
    tbody.appendChild(tr);
    senders.add(entry.sender);
    if (animate) wrapper.scrollTop = wrapper.scrollHeight;
  }

  // ── Risposta ──────────────────────────────────────────────────────
  function sendResponse() {
    const text = input.value.trim();
    if (!text || !ws || ws.readyState !== WebSocket.OPEN) return;
    ws.send(JSON.stringify({ type: 'response', text }));
    input.value = '';
    sentBadge.classList.add('show');
    setTimeout(() => sentBadge.classList.remove('show'), 2000);
  }

  btn.addEventListener('click', sendResponse);
  input.addEventListener('keydown', e => { if (e.key === 'Enter') sendResponse(); });

  // ── WebSocket ─────────────────────────────────────────────────────
  function connect() {
    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    const url   = `${proto}://${location.host}/ws?token=${encodeURIComponent(TOKEN)}`;
    ws = new WebSocket(url);

    ws.onopen = () => {
      statusEl.className = 'status-pill live';
      statusText.textContent = 'LIVE';
      input.disabled = false;
      btn.disabled   = false;
    };

    ws.onmessage = (e) => {
      const msg = JSON.parse(e.data);

      if (msg.type === 'history') {
        // caricamento iniziale di tutti i log esistenti
        tbody.innerHTML = '';
        logs = [];
        senders.clear();
        sessionStart = null;
        msg.data.forEach(entry => {
          logs.push(entry);
          addRow(entry, false);
        });
        updateStats();
        wrapper.scrollTop = wrapper.scrollHeight;

      } else if (msg.type === 'entry') {
        logs.push(msg.data);
        addRow(msg.data, true);
        updateStats();
      }
    };

    ws.onclose = () => {
      statusEl.className = 'status-pill dead';
      statusText.textContent = 'DISCONNESSO';
      input.disabled = true;
      btn.disabled   = true;
      setTimeout(connect, 3000);
    };

    ws.onerror = () => ws.close();
  }

  connect();
</script>
</body>
</html>
"""


# ── WebDashboard ────────────────────────────────────────────────────────────

class WebDashboard:
    """
    Server Flask + WebSocket per la dashboard radio.

    Endpoint:
      GET  /          → HTML della dashboard (richiede ?token=)
      GET  /ws        → WebSocket sicuro (richiede ?token=)
      GET  /health    → health-check per Fly.io
      POST /push      → riceve una voce dal tool locale e la broadcast ai client

    Protocollo WebSocket server → client:
      {"type": "history", "data": [...]}   al momento della connessione
      {"type": "entry",   "data": {...}}   per ogni nuova voce

    Protocollo WebSocket client → server:
      {"type": "response", "text": "..."}  risposta dall'utente remoto

    Utilizzo::

        import secrets

        TOKEN = secrets.token_urlsafe(32)
        dashboard = WebDashboard(token=TOKEN, on_response=mia_funzione)
        dashboard.start()
        print(dashboard.link)            # URL da condividere
        dashboard.push_entry(entry)      # invia una voce alla dashboard
    """

    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 8080,
        token: Optional[str] = None,
        on_response: Optional[Callable[[str], None]] = None,
        public_host: Optional[str] = None,   # es. "mia-app.fly.dev"
    ):
        self._host        = host
        self._port        = port
        self._token       = token or secrets.token_urlsafe(32)
        self._on_response = on_response
        self._public_host = public_host

        self._log: list[dict]      = []
        self._clients: Set         = set()
        self._response_queue: list = []   # risposte remote in attesa (modalità Fly.io)
        self._lock                 = threading.Lock()

        self._app  = Flask(__name__)
        self._sock = Sock(self._app)
        self._setup_routes()

    # ── Public ────────────────────────────────────────────────────────

    def start(self) -> None:
        """Avvia il server in un thread daemon e, se remoto, il poller delle risposte."""
        t = threading.Thread(target=self._serve, daemon=True, name="WebDashboard")
        t.start()
        if self._public_host:
            p = threading.Thread(target=self._poll_responses, daemon=True, name="ResponsePoller")
            p.start()
        print(f"\n  📡  Dashboard → {self.link}\n")

    def push_entry(self, entry: tuple) -> None:
        """
        Aggiunge una voce al log, la invia ai client WebSocket locali
        e, se configurato, la inoltra al server remoto su Fly.io via HTTP POST.

        Args:
            entry: tupla (date_time, sender, receiver, msg_received, msg_sent)
        """
        record = {
            "date_time"   : entry[0],
            "sender"      : entry[1],
            "receiver"    : entry[2],
            "msg_received": entry[3],
            "msg_sent"    : entry[4],
        }
        with self._lock:
            self._log.append(record)
            payload = json.dumps({"type": "entry", "data": record})
            dead = set()
            for ws in self._clients:
                try:
                    ws.send(payload)
                except Exception:
                    dead.add(ws)
            self._clients -= dead

        # Se è configurato un server remoto, invia la voce in background
        if self._public_host:
            threading.Thread(
                target=self._push_remote,
                args=(record,),
                daemon=True
            ).start()

    def _poll_responses(self, interval: float = 2.0) -> None:
        """
        Thread daemon: interroga GET /responses sul server Fly.io ogni `interval` secondi.
        Per ogni risposta ricevuta chiama self._on_response (thread-safe via callback).
        """
        import time
        while True:
            time.sleep(interval)
            try:
                url = f"https://{self._public_host}/responses?token={self._token}"
                req = urllib.request.Request(url)
                with urllib.request.urlopen(req, timeout=5) as resp:
                    data = json.loads(resp.read())
                    for text in data.get("responses", []):
                        if self._on_response:
                            self._on_response(text)
            except Exception:
                pass   # ignora errori di rete silenziosamente

    def _push_remote(self, record: dict) -> None:
        """Invia una voce al server remoto Fly.io via HTTP POST (thread daemon)."""
        try:
            url  = f"https://{self._public_host}/push?token={self._token}"
            data = json.dumps(record).encode("utf-8")
            req  = urllib.request.Request(
                url, data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            urllib.request.urlopen(req, timeout=5)
        except urllib.error.URLError as e:
            print(f"  ⚠️  Push remoto fallito: {e.reason}")
        except Exception as e:
            print(f"  ⚠️  Push remoto errore: {e}")

    def set_response_callback(self, callback: Callable[[str], None]) -> None:
        """
        Imposta (o aggiorna) il callback chiamato quando il client remoto
        invia una risposta. Può essere chiamato dopo l'avvio del server.
        """
        self._on_response = callback

    @property
    def token(self) -> str:
        return self._token

    @property
    def link(self) -> str:
        host = self._public_host or f"{self._host}:{self._port}"
        proto = "https" if self._public_host else "http"
        return f"{proto}://{host}?token={self._token}"

    # ── Private ───────────────────────────────────────────────────────

    def _auth(self) -> bool:
        """Verifica il token nella query string."""
        provided = request.args.get("token", "")
        return hmac.compare_digest(provided, self._token)

    def _serve(self) -> None:
        logging.getLogger("werkzeug").setLevel(logging.ERROR)
        self._app.run(host=self._host, port=self._port, threaded=True)

    def _setup_routes(self) -> None:
        app  = self._app
        sock = self._sock

        @app.route("/health")
        def health():
            return jsonify({"status": "ok"})

        @app.route("/")
        def index():
            if not self._auth():
                return Response("Non autorizzato", status=401)
            return _HTML

        @app.route("/push", methods=["POST"])
        def push_remote():
            """
            Riceve una voce dal tool locale (autenticato via token)
            e la broadcast a tutti i client WebSocket connessi.
            """
            if not self._auth():
                return Response("Non autorizzato", status=401)
            try:
                record = request.get_json(force=True)
                if not record:
                    return jsonify({"error": "payload vuoto"}), 400
            except Exception:
                return jsonify({"error": "JSON non valido"}), 400

            with self._lock:
                self._log.append(record)
                payload = json.dumps({"type": "entry", "data": record})
                dead = set()
                for ws in self._clients:
                    try:
                        ws.send(payload)
                    except Exception:
                        dead.add(ws)
                self._clients -= dead

            return jsonify({"ok": True})

        @app.route("/responses", methods=["GET"])
        def get_responses():
            """
            Restituisce e svuota la coda delle risposte remote.
            Chiamato dal tool locale via polling ogni 2 secondi.
            """
            if not self._auth():
                return Response("Non autorizzato", status=401)
            with self._lock:
                pending = list(self._response_queue)
                self._response_queue.clear()
            return jsonify({"responses": pending})

        @sock.route("/ws")
        def ws_handler(ws):
            # autenticazione WebSocket
            if not self._auth():
                ws.close(message=b"401 Non autorizzato")
                return

            # invia history al client appena connesso
            with self._lock:
                history = list(self._log)
                self._clients.add(ws)

            try:
                ws.send(json.dumps({"type": "history", "data": history}))

                # loop: ricevi messaggi dal client (risposte)
                while True:
                    raw = ws.receive()
                    if raw is None:
                        break
                    try:
                        msg = json.loads(raw)
                        if msg.get("type") == "response":
                            response_text = msg.get("text", "")
                            with self._lock:
                                self._response_queue.append(response_text)
                            # in locale chiama subito il callback (nessun polling)
                            if self._on_response and not self._public_host:
                                self._on_response(response_text)
                    except (json.JSONDecodeError, Exception):
                        pass

            finally:
                with self._lock:
                    self._clients.discard(ws)


# ── Esempio di utilizzo standalone ─────────────────────────────────────────

if __name__ == "__main__":
    import time, secrets

    def handle_response(text: str):
        print(f"\n  💬  Risposta ricevuta: {text}\n")

    TOKEN = secrets.token_urlsafe(32)
    dashboard = WebDashboard(token=TOKEN, on_response=handle_response)
    dashboard.start()

    # Simula alcune voci
    import random
    entries = [
        ("2025-01-15 10:23:01", "IU2ABC", "IU2XYZ", "Pronto, mi senti?", "Ti sento bene, 5 e 9"),
        ("2025-01-15 10:24:15", "IU2XYZ", "IU2ABC", "Situazione tranquilla", "Ricevuto, continua monitoraggio"),
    ]
    for e in entries:
        time.sleep(2)
        dashboard.push_entry(e)
        print(f"  → Voce aggiunta: {e[1]} → {e[2]}")

    print("\n  (Ctrl+C per uscire)\n")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
