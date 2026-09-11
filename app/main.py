# -*- coding: utf-8 -*-
"""
main.py
Entry point dell'applicazione Radio Communication Log.
Coordina le componenti tramite la classe Application.

Variabili d'ambiente riconosciute:
  WS_TOKEN — token/session_id fisso per la dashboard locale (opzionale;
             se assente ne viene generato uno nuovo ad ogni avvio).

Compatibile con PyInstaller (--onefile e --windowed):
  I path delle risorse vengono risolti rispetto a sys._MEIPASS quando
  l'applicazione gira come eseguibile congelato.
"""

import os
import secrets
import sys
from datetime import datetime
from pathlib import Path


# ── Sicurezza I/O standard ────────────────────────────────────────────────────

def _ensure_safe_stdio() -> None:
    """
    Garantisce che sys.stdout/stderr esistano sempre e non sollevino mai
    un'eccezione per problemi di codifica. Protegge da due problemi
    frequenti in produzione, specialmente su Windows:

    1. Console con codifica legacy (es. cp1252, tipica dei terminali
       Windows non-UTF-8): un print() con un'emoji o un carattere come
       "→" solleva UnicodeEncodeError e manda in crash l'intera app
       (è quanto capitato con "📡" nel messaggio di avvio della dashboard).

    2. Eseguibile PyInstaller in modalità --windowed (nessuna console):
       sys.stdout/sys.stderr possono essere None, quindi qualunque
       print() nel codice solleverebbe AttributeError.

    Va chiamata il prima possibile, prima che qualunque altro modulo
    dell'app esegua un print().
    """
    import io

    if sys.stdout is None:
        sys.stdout = io.StringIO()
    if sys.stderr is None:
        sys.stderr = io.StringIO()

    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


_ensure_safe_stdio()


# ── Path base (script normale vs eseguibile PyInstaller) ─────────────────────

def _base_path() -> Path:
    """
    Restituisce la cartella ROOT del progetto (dove si trova configurator.txt).

    Casi gestiti:
    - Eseguibile PyInstaller (--onefile): sys._MEIPASS
    - main.py in root del progetto (struttura piatta): cartella di main.py
    - main.py in app/ (dopo reorganize.py): cartella genitore di app/
    """
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)

    here = Path(__file__).parent.resolve()

    # Se siamo dentro app/, risali alla root del progetto
    if here.name == "app":
        return here.parent

    return here

BASE = _base_path()

# ── sys.path: aggiunge app/ per gli import dei moduli locali ─────────────────
_app_dir = BASE / "app"
if _app_dir.exists() and str(_app_dir) not in sys.path:
    sys.path.insert(0, str(_app_dir))

# Fallback struttura piatta (pre-reorganize)
if not _app_dir.exists() and str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))


# ── Import moduli locali (dopo sys.path setup) ────────────────────────────────

from config_manager import ConfigManager                    # noqa: E402
from directory_selector import DirectorySelector            # noqa: E402
from log_interface import RadioLogInterface, SplashScreen  # noqa: E402
from report_creator import ReportCreator                    # noqa: E402
from web_dashboard import WebDashboard                      # noqa: E402


# ── Helpers path risorse ──────────────────────────────────────────────────────

def _resolve_asset(raw_path: str) -> str:
    """
    Risolve un path di risorsa (logo, bandiera, ecc.) letto dal configurator.

    Strategia:
      1. Se il path è assoluto ed esiste → usalo direttamente
      2. Se il path è relativo → prova BASE / path
      3. Se il file è in assets/ ma il path dice img/ → correggi automaticamente
      4. Se ancora non trovato → restituisce il path originale (gestione errore a monte)
    """
    p = Path(raw_path)

    # Assoluto e esistente
    if p.is_absolute() and p.exists():
        return str(p)

    # Relativo rispetto a BASE
    candidate = BASE / p
    if candidate.exists():
        return str(candidate)

    # Correzione automatica img/ → assets/ (retrocompatibilità)
    corrected = Path(str(p).replace("img" + os.sep, "assets" + os.sep)
                            .replace("img/", "assets/"))
    candidate2 = BASE / corrected
    if candidate2.exists():
        return str(candidate2)

    # Ultima risorsa: nome file in assets/
    candidate3 = BASE / "assets" / p.name
    if candidate3.exists():
        return str(candidate3)

    return str(BASE / p)   # restituisce il path atteso anche se non esiste


def _resolve_flag_list(raw: list) -> list:
    """Risolve ogni elemento di Flags_logo tramite _resolve_asset."""
    return [_resolve_asset(f) for f in raw]


# ── Application ───────────────────────────────────────────────────────────────

class Application:
    """
    Coordina l'intero ciclo di vita dell'applicazione:
      1. Carica la configurazione
      2. Mostra la splash screen
      3. Avvia la dashboard WebSocket (thread daemon)
      4. Chiede la directory di salvataggio
      5. Collega il callback bidirezionale (risposte remote → UI)
      6. Avvia l'interfaccia di log (Tkinter)
    """

    def __init__(self):
        config_file = BASE / "configurator.txt"
        self._config_path = str(config_file)
        self._cfg      = ConfigManager(self._config_path)
        self._reporter = ReportCreator()

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def run(self) -> None:
        cfg = self._cfg

        firmware      = cfg["Firmware_version"]
        drive_path    = cfg["Drive_path"]
        program_title = cfg["Program_title"]
        proprieties   = cfg["Proprieties"]
        web_port      = int(cfg.get("Web_dashboard_port") or 8080)
        login_dt      = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Risolvi i path delle risorse grafiche rispetto a BASE
        logo_path = _resolve_asset(cfg["Logo_path"])
        flag_list = _resolve_flag_list(cfg["Flags_logo"])

        # ── Database apparati (TLC Point) ─────────────────────────────
        # File Excel con anagrafica apparati e storico carico/scarico.
        # Se non esiste viene creato automaticamente al primo avvio.
        apparati_db_path = str(BASE / (cfg.get("Apparati_db_path") or "apparati.xlsx"))

        # ── Database mappa GIS (operatori/ostacoli) ───────────────────
        map_data_path = str(BASE / (cfg.get("Map_data_path") or "mappa_gis.json"))

        # ── Token sessione ───────────────────────────────────────────
        # Usato come session_id della dashboard. Se fisso nel configurator
        # il link non cambia mai tra un riavvio e l'altro.
        token = cfg.get("WS_TOKEN") or secrets.token_urlsafe(32)

        # ── Dashboard locale ─────────────────────────────────────────
        # Se true → dashboard web disponibile via browser sulla rete locale
        # (nessun servizio esterno: nessun account, nessuna chiave API).
        # Se false → WebDashboard non viene avviata.
        remote_enabled = cfg.get("Remote_enabled", "false").strip().lower() == "true"

        # 1. Splash screen
        SplashScreen(firmware, logo_path, proprieties).show()

        # 2. Dashboard locale (solo se Remote_enabled = true)
        dashboard = None
        if remote_enabled:
            dashboard = WebDashboard(
                token = token,
                port  = web_port,
            )
            dashboard.start()

        # 3. Selezione directory di salvataggio
        directory_state_path = str(BASE / ".last_directory_choice.json")
        directory = DirectorySelector(
            logo_path, flag_list, drive_path, state_path=directory_state_path
        ).run()
        if not directory:
            print("Directory non selezionata. Uscita dal programma.")
            sys.exit(0)

        # 4. Numero di protocollo
        n_protocol = self._reporter.count_files(
            directory, ".pdf", prefix="rapporto_comunicazioni_radio_"
        )

        # 5. Interfaccia principale
        interface = RadioLogInterface(
            login_datetime   = login_dt,
            directory        = directory,
            n_files          = n_protocol,
            logo_path        = logo_path,
            program_title    = program_title,
            dashboard        = dashboard,  # None se remote_enabled = false
            apparati_db_path = apparati_db_path,
            map_data_path    = map_data_path,
            config_path      = self._config_path,
        )

        # 6. Wiring bidirezionale della chat (solo se la dashboard locale è attiva)
        if dashboard:
            dashboard.set_message_callback(interface.handle_remote_message)

        interface.run()


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    Application().run()