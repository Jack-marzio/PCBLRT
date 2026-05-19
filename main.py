# -*- coding: utf-8 -*-
"""
main.py
Entry point dell'applicazione Radio Communication Log.
Coordina le componenti tramite la classe Application.

Variabili d'ambiente riconosciute:
  WS_TOKEN      — token segreto per la dashboard remota (obbligatorio in produzione)
  FLY_APP_NAME  — impostato automaticamente da Fly.io; costruisce l'URL pubblico

Compatibile con PyInstaller (--onefile e --windowed):
  I path delle risorse vengono risolti rispetto a sys._MEIPASS quando
  l'applicazione gira come eseguibile congelato.
"""

import os
import secrets
import sys
from datetime import datetime
from pathlib import Path


# ── Path base (script normale vs eseguibile PyInstaller) ─────────────────────

def _base_path() -> Path:
    """
    Restituisce la cartella base per le risorse:
    - In esecuzione normale: cartella di main.py
    - In eseguibile PyInstaller (--onefile): sys._MEIPASS (cartella temporanea di estrazione)
    """
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return Path(__file__).parent.resolve()

BASE = _base_path()

# ── sys.path: aggiunge app/ per gli import dei moduli locali ─────────────────
# Necessario sia in sviluppo (dopo reorganize.py) che nell'exe (PyInstaller
# estrae tutto in _MEIPASS ma i moduli di app/ vanno cercati esplicitamente).

_app_dir = BASE / "app"
if str(_app_dir) not in sys.path:
    sys.path.insert(0, str(_app_dir))

# Fallback: se app/ non esiste (struttura piatta pre-reorganize) usa BASE
if not _app_dir.exists():
    if str(BASE) not in sys.path:
        sys.path.insert(0, str(BASE))


# ── Import moduli locali (dopo sys.path setup) ────────────────────────────────

from config_manager import ConfigManager                    # noqa: E402
from directory_selector import DirectorySelector            # noqa: E402
from log_interface import RadioLogInterface, ModeSelector, SplashScreen  # noqa: E402
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
        self._cfg      = ConfigManager(str(config_file))
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
        web_port      = int(cfg.get("Web_dashboard_port", 8080))
        login_dt      = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Risolvi i path delle risorse grafiche rispetto a BASE
        logo_path = _resolve_asset(cfg["Logo_path"])
        flag_list = _resolve_flag_list(cfg["Flags_logo"])

        # ── Remote enabled flag ──────────────────────────────────────
        remote_enabled = cfg.get("Remote_enabled", "false").strip().lower() == "true"

        # ── Token e host pubblico ────────────────────────────────────
        token = cfg.get("WS_TOKEN") or os.environ.get("WS_TOKEN")
        if not token:
            token = secrets.token_urlsafe(32)
            print(
                f"\n  ⚠️   WS_TOKEN non trovato — token di sessione generato: {token}\n"
                f"      Per uso stabile: python deploy/deploy.py deploy <org>\n"
            )

        fly_app         = cfg.get("FLY_APP_NAME") or os.environ.get("FLY_APP_NAME")
        configured_host = f"{fly_app}.fly.dev" if fly_app else None

        # ── Selezione modalità a runtime ─────────────────────────────
        public_host = None
        if remote_enabled and configured_host:
            mode        = ModeSelector(logo_path=logo_path, lang="it").run()
            public_host = configured_host if mode == "remote" else None
        elif remote_enabled and not configured_host:
            print(
                "  ⚠️   Remote_enabled = true ma FLY_APP_NAME non configurato.\n"
                "      Esegui: python deploy/deploy.py deploy <org>\n"
            )

        # 1. Splash screen
        SplashScreen(firmware, logo_path, proprieties).show()

        # 2. Dashboard WebSocket (thread daemon)
        dashboard = WebDashboard(
            port=web_port,
            token=token,
            public_host=public_host,
        )
        dashboard.start()

        # 3. Selezione directory di salvataggio
        directory = DirectorySelector(logo_path, flag_list, drive_path).run()
        if not directory:
            print("Directory non selezionata. Uscita dal programma.")
            sys.exit(0)

        # 4. Numero di protocollo
        n_protocol = self._reporter.count_files(directory, ".pdf")

        # 5. Interfaccia principale
        interface = RadioLogInterface(
            login_datetime=login_dt,
            directory=directory,
            n_files=n_protocol,
            logo_path=logo_path,
            flag_list=flag_list,
            program_title=program_title,
            dashboard=dashboard,
        )

        # 6. Wiring bidirezionale
        dashboard.set_response_callback(interface.handle_remote_response)

        interface.run()


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    Application().run()
