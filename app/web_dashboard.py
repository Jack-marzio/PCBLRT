# -*- coding: utf-8 -*-
"""
web_dashboard.py
Dashboard web in tempo reale — 100% locale, nessun servizio esterno.

Il tool Python espone un piccolo server Flask sulla rete locale.
Il browser si collega allo stesso server e riceve gli aggiornamenti
in tempo reale via Server-Sent Events (SSE): nessun cloud, nessun
SDK esterno, nessuna chiave API.

Flusso:
  [Tool Python] --push_entry()--> log in memoria --SSE--> [Browser]
  [Browser]     --POST /api/respond-------------------> [Tool Python]

Nessun setup richiesto: basta avviare l'app e condividere il link
mostrato (valido sulla stessa rete locale/LAN).

Utilizzo::

    dashboard = WebDashboard(port=8080)
    dashboard.start()
    print(dashboard.link)          # apri nel browser
    dashboard.push_entry(entry)    # invia una voce
    dashboard.set_response_callback(mia_funzione)
"""

import json
import logging
import queue
import secrets
import socket
import threading
from typing import Callable, Optional

from flask import Flask, Response, jsonify, request, stream_with_context


def _detect_lan_ip() -> str:
    """
    Rileva l'indirizzo IP della macchina sulla rete locale (LAN), così il
    link della dashboard è raggiungibile da altri dispositivi sulla stessa
    rete (es. smartphone). Non contatta alcun servizio esterno: sfrutta solo
    la tabella di routing del sistema operativo (nessun pacchetto UDP viene
    effettivamente inviato, "connect" su socket UDP è puramente locale).
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


# ── HTML template ─────────────────────────────────────────────────────────────
# Nessuna dipendenza esterna: font di sistema, nessun CDN, nessuna chiave API.
# Il parametro __SESSION_ID__ viene sostituito a runtime da _render_html().

_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="it">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>RadioLog — Live Monitor</title>
  <style>
    *,*::before,*::after{box-sizing:border-box;margin:0;padding:0}

    :root{
      --bg:#080c10;--surface:#0d1520;--border:#1a2e44;
      --accent:#00e5ff;--accent2:#ff6b35;--green:#39ff14;
      --red:#ff2d55;--text:#c8d8e8;--dim:#4a6580;
      --mono:'Consolas','Menlo','Monaco','Courier New',monospace;
      --sans:'Segoe UI','Helvetica Neue',Arial,sans-serif;
    }

    html,body{height:100%;background:var(--bg);color:var(--text);
      font-family:var(--mono);overflow:hidden}

    body::before{content:'';position:fixed;inset:0;z-index:0;pointer-events:none;
      background-image:url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)' opacity='0.04'/%3E%3C/svg%3E");
      opacity:.4}

    #app{position:relative;z-index:1;display:grid;
      grid-template-rows:auto auto 1fr auto auto;height:100vh}

    header{display:flex;align-items:center;justify-content:space-between;
      padding:14px 28px;border-bottom:1px solid var(--border);
      background:linear-gradient(90deg,#0d1520,#091420);gap:16px}
    .hdr-l{display:flex;align-items:baseline;gap:14px}
    .logo{font-family:var(--sans);font-weight:700;font-size:1.5rem;
      letter-spacing:.06em;color:var(--accent);text-transform:uppercase}
    .sub{font-family:var(--sans);font-weight:300;font-size:.8rem;
      color:var(--dim);letter-spacing:.12em;text-transform:uppercase}

    .pill{display:flex;align-items:center;gap:7px;padding:5px 14px;
      border:1px solid var(--border);border-radius:20px;font-size:.72rem;
      letter-spacing:.1em;text-transform:uppercase;transition:border-color .3s,color .3s}
    .pill.live{border-color:var(--green);color:var(--green)}
    .pill.dead{border-color:var(--red);color:var(--red)}
    .pill.wait{border-color:#f0a000;color:#f0a000}
    .dot{width:7px;height:7px;border-radius:50%;background:currentColor;
      animation:pulse 1.4s ease-in-out infinite}
    @keyframes pulse{0%,100%{opacity:1;transform:scale(1)}50%{opacity:.4;transform:scale(.7)}}

    .stats{display:flex;border-bottom:1px solid var(--border);background:var(--surface)}
    .stat{flex:1;padding:10px 20px;border-right:1px solid var(--border);
      display:flex;flex-direction:column;gap:2px}
    .stat:last-child{border-right:none}
    .sl{font-size:.62rem;letter-spacing:.14em;color:var(--dim);text-transform:uppercase}
    .sv{font-family:var(--sans);font-weight:700;font-size:1.3rem;
      color:var(--accent);letter-spacing:.04em;transition:color .4s}
    .sv.flash{color:var(--green)}

    .tbl-wrap{overflow-y:auto;padding:0 0 8px;scroll-behavior:smooth}
    .tbl-wrap::-webkit-scrollbar{width:6px}
    .tbl-wrap::-webkit-scrollbar-thumb{background:var(--border);border-radius:3px}

    table{width:100%;border-collapse:collapse;font-size:.78rem}
    thead{position:sticky;top:0;z-index:2;background:#0a1520}
    th{padding:10px 14px;text-align:left;font-family:var(--sans);font-weight:700;
      font-size:.68rem;letter-spacing:.14em;text-transform:uppercase;
      color:var(--dim);border-bottom:1px solid var(--border);white-space:nowrap}
    th:first-child,td:first-child{padding-left:28px}
    th:last-child,td:last-child{padding-right:28px}
    tbody tr{border-bottom:1px solid rgba(26,46,68,.5);
      animation:row-in .35s cubic-bezier(.2,0,.2,1) both}
    @keyframes row-in{from{opacity:0;transform:translateX(-12px);
      background:rgba(0,229,255,.07)}to{opacity:1;transform:translateX(0)}}
    tbody tr:hover{background:rgba(255,255,255,.025)}
    td{padding:9px 14px;vertical-align:top;line-height:1.5;word-break:break-word}
    .ct{color:var(--dim);white-space:nowrap;min-width:150px}
    .cs{color:var(--accent);font-weight:bold;min-width:100px}
    .cr{color:var(--accent2);font-weight:bold;min-width:100px}
    .seq{display:inline-block;min-width:26px;padding:1px 6px;
      border:1px solid var(--border);border-radius:3px;
      color:var(--dim);font-size:.68rem;text-align:center;margin-right:8px}

    .empty{display:flex;flex-direction:column;align-items:center;
      justify-content:center;height:100%;gap:12px;color:var(--dim);padding:60px 0}
    .empty .ic{font-size:2.5rem;opacity:.3;animation:blink 2s step-start infinite}
    @keyframes blink{0%,100%{opacity:.3}50%{opacity:.08}}
    .empty p{font-size:.8rem;letter-spacing:.1em;text-transform:uppercase}

    .rbar{display:flex;align-items:center;gap:10px;padding:10px 28px;
      border-top:1px solid var(--border);background:var(--surface)}
    .rlbl{font-size:.65rem;letter-spacing:.14em;text-transform:uppercase;
      color:var(--dim);white-space:nowrap}
    .rinp{flex:1;background:#0a1520;border:1px solid var(--border);border-radius:4px;
      color:var(--text);font-family:var(--mono);font-size:.8rem;padding:7px 12px;
      outline:none;transition:border-color .2s}
    .rinp:focus{border-color:var(--accent)}
    .rinp::placeholder{color:var(--dim)}
    .rinp:disabled{opacity:.4;cursor:not-allowed}
    .rbtn{background:transparent;border:1px solid var(--accent);color:var(--accent);
      font-family:var(--sans);font-weight:700;font-size:.75rem;letter-spacing:.12em;
      text-transform:uppercase;padding:7px 20px;border-radius:4px;cursor:pointer;
      transition:background .2s,color .2s;white-space:nowrap}
    .rbtn:hover{background:var(--accent);color:var(--bg)}
    .rbtn:disabled{opacity:.3;cursor:not-allowed}
    .rsent{font-size:.68rem;color:var(--green);opacity:0;
      transition:opacity .3s;letter-spacing:.1em;text-transform:uppercase}
    .rsent.show{opacity:1}

    footer{border-top:1px solid var(--border);background:var(--surface);
      padding:8px 28px;display:flex;align-items:center;justify-content:space-between;
      font-size:.65rem;color:var(--dim);letter-spacing:.08em;text-transform:uppercase}
    #clock{color:var(--text)}

    body::after{content:'';position:fixed;inset:0;z-index:999;pointer-events:none;
      background:repeating-linear-gradient(to bottom,transparent 0px,
        transparent 2px,rgba(0,0,0,.03) 2px,rgba(0,0,0,.03) 4px)}
  </style>
</head>
<body>
<div id="app">
  <header>
    <div class="hdr-l">
      <span class="logo">&#9658; RadioLog</span>
      <span class="sub">Live Monitor</span>
    </div>
    <div id="status" class="pill wait">
      <span class="dot"></span>
      <span id="status-text">CONNESSIONE...</span>
    </div>
  </header>

  <div class="stats">
    <div class="stat"><span class="sl">Comunicazioni</span><span class="sv" id="s-tot">0</span></div>
    <div class="stat"><span class="sl">Ultima voce</span><span class="sv" id="s-last" style="font-size:.9rem">—</span></div>
    <div class="stat"><span class="sl">Sessione avviata</span><span class="sv" id="s-sess" style="font-size:.9rem">—</span></div>
    <div class="stat"><span class="sl">Mittenti unici</span><span class="sv" id="s-send">0</span></div>
  </div>

  <div class="tbl-wrap" id="wrap">
    <table>
      <thead><tr>
        <th>#</th><th>Data / Ora</th><th>Mittente</th>
        <th>Ricevente</th><th>Messaggio ricevuto</th><th>Messaggio trasmesso</th>
      </tr></thead>
      <tbody id="tbody"></tbody>
    </table>
    <div class="empty" id="empty">
      <span class="ic">&#9632;</span>
      <p>In attesa di comunicazioni...</p>
    </div>
  </div>

  <div class="rbar">
    <span class="rlbl">Risposta &#9654;</span>
    <input id="rinp" class="rinp" type="text"
      placeholder="Scrivi una risposta e premi Invio..."/>
    <button id="rbtn" class="rbtn">Invia</button>
    <span id="rsent" class="rsent">✓ inviato</span>
  </div>

  <footer>
    <span>ProcivBes Radio Team Tool &mdash; Dashboard locale</span>
    <span id="clock"></span>
  </footer>
</div>

<script>
  // ── Config iniettata dal server ──────────────────────────────────
  const SESSION_ID = "__SESSION_ID__";
  const qs = (extra) => `session=${encodeURIComponent(SESSION_ID)}${extra || ''}`;

  // ── Stato ────────────────────────────────────────────────────────
  let logs = [], senders = new Set(), sessionStart = null;
  const tbody = document.getElementById('tbody');
  const empty = document.getElementById('empty');
  const wrap  = document.getElementById('wrap');
  const rinp  = document.getElementById('rinp');
  const rbtn  = document.getElementById('rbtn');
  const rsent = document.getElementById('rsent');
  const statusEl   = document.getElementById('status');
  const statusText = document.getElementById('status-text');

  // ── Clock ────────────────────────────────────────────────────────
  function tick(){
    document.getElementById('clock').textContent =
      new Date().toLocaleTimeString('it-IT',{hour12:false});
  }
  tick(); setInterval(tick, 1000);

  // ── Helpers ──────────────────────────────────────────────────────
  function flash(el){
    el.classList.add('flash');
    setTimeout(()=>el.classList.remove('flash'), 600);
  }

  function updateStats(){
    const tot = document.getElementById('s-tot');
    const lst = document.getElementById('s-last');
    const ses = document.getElementById('s-sess');
    const snd = document.getElementById('s-send');
    tot.textContent = logs.length; flash(tot);
    if(logs.length > 0) lst.textContent = (logs[logs.length-1].date_time || '').slice(11,19);
    if(!sessionStart && logs.length > 0){
      sessionStart = logs[0].date_time;
      ses.textContent = (sessionStart || '').slice(11,19);
    }
    snd.textContent = senders.size;
    empty.style.display = logs.length === 0 ? 'flex' : 'none';
  }

  function addRow(entry, animate=true){
    const seq = logs.length - 1;
    const tr  = document.createElement('tr');
    if(!animate) tr.style.animation = 'none';
    tr.innerHTML = `
      <td><span class="seq">${seq}</span></td>
      <td class="ct">${entry.date_time}</td>
      <td class="cs">${entry.sender}</td>
      <td class="cr">${entry.receiver}</td>
      <td>${entry.msg_received}</td>
      <td>${entry.msg_sent}</td>`;
    tbody.appendChild(tr);
    senders.add(entry.sender);
    if(animate) wrap.scrollTop = wrap.scrollHeight;
  }

  // ── Risposta ─────────────────────────────────────────────────────
  // L'invio è un semplice POST, indipendente dallo stato dello stream SSE:
  // il campo resta sempre utilizzabile, anche se il "LIVE" è momentaneamente
  // disconnesso (es. telefono che ha bloccato lo schermo).
  rinp.disabled = false;
  rbtn.disabled = false;

  function showSendFeedback(ok, message){
    rsent.textContent = ok ? '✓ inviato' : ('✗ ' + message);
    rsent.style.color = ok ? 'var(--green)' : 'var(--red)';
    rsent.classList.add('show');
    setTimeout(()=>rsent.classList.remove('show'), ok ? 2000 : 4000);
  }

  function sendResponse(){
    const text = rinp.value.trim();
    if(!text) return;
    rbtn.disabled = true;
    fetch(`/api/respond?${qs()}`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({text})
    })
      .then(r => {
        if(!r.ok) throw new Error('risposta server: ' + r.status);
        rinp.value = '';
        showSendFeedback(true);
      })
      .catch(err => {
        showSendFeedback(false, 'invio fallito, riprova');
        console.error('Errore invio risposta:', err);
      })
      .finally(() => { rbtn.disabled = false; });
  }
  rbtn.addEventListener('click', sendResponse);
  rinp.addEventListener('keydown', e=>{ if(e.key==='Enter') sendResponse(); });

  // ── Caricamento iniziale ────────────────────────────────────────
  fetch(`/api/logs?${qs()}`)
    .then(r => r.ok ? r.json() : [])
    .then(data => {
      data.forEach(entry => { logs.push(entry); addRow(entry, false); });
      updateStats();
    })
    .catch(() => {});

  // ── Aggiornamenti in tempo reale via Server-Sent Events ──────────
  function connectStream(){
    const es = new EventSource(`/stream?${qs()}`);

    es.onopen = () => {
      statusEl.className = 'pill live';
      statusText.textContent = 'LIVE';
    };

    es.onmessage = (ev) => {
      if(!ev.data) return;
      const entry = JSON.parse(ev.data);
      logs.push(entry);
      addRow(entry, true);
      updateStats();
    };

    es.onerror = () => {
      statusEl.className = 'pill dead';
      statusText.textContent = 'DISCONNESSO';
      // EventSource riprova automaticamente la connessione;
      // l'invio risposte resta comunque attivo (POST indipendente).
    };
  }
  connectStream();
</script>
</body>
</html>
"""


# ── WebDashboard ──────────────────────────────────────────────────────────────

class WebDashboard:
    """
    Dashboard web in tempo reale — completamente locale.

    Un server Flask (in un thread daemon) serve la pagina e sincronizza
    log/risposte via Server-Sent Events. Nessun dato lascia la rete locale.

    Endpoint esposti:
      GET  /?session=...           → pagina HTML della dashboard
      GET  /api/logs?session=...   → log accumulato finora (JSON)
      GET  /stream?session=...     → stream SSE delle nuove voci
      POST /api/respond?session=...→ invia una risposta dal browser al tool
      GET  /health                 → stato del servizio

    Utilizzo::

        dashboard = WebDashboard(port=8080, on_response=mia_funzione)
        dashboard.start()
        print(dashboard.link)          # apri nel browser (stessa rete locale)
        dashboard.push_entry(entry)    # invia una voce
    """

    def __init__(
        self,
        session_id:  Optional[str]                    = None,
        on_response: Optional[Callable[[str], None]]  = None,
        port:        int                              = 8080,
        host:        str                              = "0.0.0.0",
        token:       Optional[str]                    = None,
        public_host: Optional[str]                    = None,
        **_ignored,   # assorbe eventuali parametri legacy (es. firebase_*) senza errori
    ):
        # Usa token come session_id se fornito → stesso link ad ogni riavvio
        self._session_id  = session_id or token or secrets.token_urlsafe(20)
        self._on_response = on_response
        self._port        = port
        self._host        = host
        self._public_host = public_host

        self._log:         list[dict]        = []
        self._lock                            = threading.Lock()
        self._subscribers: list[queue.Queue]  = []

        self._app = Flask(__name__)
        self._setup_routes()

    # ── Public ────────────────────────────────────────────────────────

    def start(self) -> None:
        """Avvia il server Flask locale (thread daemon)."""
        t = threading.Thread(target=self._serve, daemon=True, name="WebDashboard")
        t.start()
        print(f"\n  📡  Dashboard (locale) → {self.link}\n")

    def push_entry(self, entry: tuple) -> None:
        """
        Aggiunge una voce al log e la invia in tempo reale a tutti i
        browser collegati (via Server-Sent Events).

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
            subscribers = list(self._subscribers)

        for q in subscribers:
            q.put(record)

    def set_response_callback(self, callback: Callable[[str], None]) -> None:
        """Imposta o aggiorna il callback per le risposte dal browser."""
        self._on_response = callback

    def clear_session(self) -> None:
        """Svuota tutti i dati della sessione corrente (solo in memoria locale)."""
        with self._lock:
            self._log.clear()

    @property
    def session_id(self) -> str:
        return self._session_id

    @property
    def token(self) -> str:
        """Compatibilità con main.py: restituisce session_id."""
        return self._session_id

    @property
    def link(self) -> str:
        if self._public_host:
            display_host = self._public_host
        elif self._host in ("0.0.0.0", ""):
            # In ascolto su tutte le interfacce: mostra l'IP LAN reale,
            # così il link funziona anche da altri dispositivi sulla stessa
            # rete (es. smartphone). "localhost" funzionerebbe solo sul PC.
            display_host = _detect_lan_ip()
        else:
            display_host = self._host
        return f"http://{display_host}:{self._port}?session={self._session_id}"

    # ── Private ───────────────────────────────────────────────────────

    def _authorized(self) -> bool:
        return request.args.get("session", "") == self._session_id

    def _serve(self) -> None:
        logging.getLogger("werkzeug").setLevel(logging.ERROR)
        try:
            self._app.run(host=self._host, port=self._port, threaded=True)
        except OSError as e:
            if "Address already in use" in str(e) or "10048" in str(e):
                print(f"  ℹ️  Porta {self._port} già in uso — "
                      f"il server precedente è ancora attivo. "
                      f"Riavvia il kernel Spyder per un avvio pulito.")
            else:
                raise

    def _render_html(self) -> str:
        """Inietta il session_id nell'HTML template."""
        return _HTML_TEMPLATE.replace("__SESSION_ID__", self._session_id)

    def _setup_routes(self) -> None:
        app = self._app

        @app.route("/")
        def index():
            if not self._authorized():
                return Response("Non autorizzato", status=401)
            return self._render_html()

        @app.route("/api/logs")
        def api_logs():
            if not self._authorized():
                return Response(status=401)
            with self._lock:
                return jsonify(list(self._log))

        @app.route("/stream")
        def stream():
            if not self._authorized():
                return Response(status=401)

            q: queue.Queue = queue.Queue()
            with self._lock:
                self._subscribers.append(q)

            def gen():
                try:
                    yield ": connected\n\n"
                    while True:
                        try:
                            record = q.get(timeout=15)
                            yield f"data: {json.dumps(record)}\n\n"
                        except queue.Empty:
                            # keep-alive: evita timeout su proxy/browser
                            yield ": ping\n\n"
                finally:
                    with self._lock:
                        if q in self._subscribers:
                            self._subscribers.remove(q)

            return Response(
                stream_with_context(gen()),
                mimetype="text/event-stream",
                headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
            )

        @app.route("/api/respond", methods=["POST"])
        def api_respond():
            if not self._authorized():
                return Response(status=401)
            data = request.get_json(silent=True) or {}
            text = str(data.get("text", "")).strip()
            if text and self._on_response:
                self._on_response(text)
            return jsonify({"ok": True})

        @app.route("/health")
        def health():
            return {"status": "ok"}
