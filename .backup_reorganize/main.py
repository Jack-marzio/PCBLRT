# -*- coding: utf-8 -*-
"""
main.py
Entry point dell'applicazione Radio Communication Log.
Coordina le componenti tramite la classe Application.

Variabili d'ambiente riconosciute:
  WS_TOKEN      — token segreto per la dashboard remota (obbligatorio in produzione)
  FLY_APP_NAME  — impostato automaticamente da Fly.io; costruisce l'URL pubblico
"""

import os
import secrets
import sys
from datetime import datetime

from config_manager import ConfigManager
from directory_selector import DirectorySelector
from log_interface import RadioLogInterface, ModeSelector, SplashScreen
from report_creator import ReportCreator
from web_dashboard import WebDashboard


class Application:
    """
    Coordina l'intero ciclo di vita dell'applicazione:
      1. Carica la configurazione
      2. Mostra la splash screen
      3. Avvia la dashboard WebSocket remota (thread daemon)
      4. Chiede la directory di salvataggio
      5. Collega il callback bidirezionale (risposte remote → UI)
      6. Avvia l'interfaccia di log (Tkinter)
    """

    def __init__(self, config_path: str = "configurator.txt"):
        self._cfg      = ConfigManager(config_path)
        self._reporter = ReportCreator()

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def run(self) -> None:
        cfg = self._cfg

        firmware      = cfg["Firmware_version"]
        drive_path    = cfg["Drive_path"]
        logo_path     = cfg["Logo_path"]
        program_title = cfg["Program_title"]
        flag_list     = cfg["Flags_logo"]
        proprieties   = cfg["Proprieties"]
        web_port      = int(cfg.get("Web_dashboard_port", 8080))
        login_dt      = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # ── Remote enabled flag ──────────────────────────────────────
        # Impostare Remote_enabled = true nel configuratore per abilitare
        # la funzionalità di dashboard remota su Fly.io.
        # Se false (o assente) il tool funziona solo in locale.
        remote_enabled = cfg.get("Remote_enabled", "false").strip().lower() == "true"

        # ── Token e host pubblico ────────────────────────────────────
        # Priorità: configurator.txt  >  variabile d'ambiente  >  generato
        # deploy.py scrive automaticamente WS_TOKEN e FLY_APP_NAME.
        token = (
            cfg.get("WS_TOKEN")
            or os.environ.get("WS_TOKEN")
        )
        if not token:
            token = secrets.token_urlsafe(32)
            print(
                f"\n  ⚠️   WS_TOKEN non trovato — token di sessione generato: {token}\n"
                f"      Per uso stabile: python deploy.py deploy <org>\n"
            )

        fly_app = (
            cfg.get("FLY_APP_NAME")
            or os.environ.get("FLY_APP_NAME")
        )
        configured_host = f"{fly_app}.fly.dev" if fly_app else None

        # ── Selezione modalità a runtime ─────────────────────────────
        # Mostrata solo se Remote_enabled = true E un host remoto è configurato.
        public_host = None
        if remote_enabled and configured_host:
            mode = ModeSelector(logo_path=logo_path, lang="it").run()
            public_host = configured_host if mode == "remote" else None
        elif remote_enabled and not configured_host:
            print(
                "  ⚠️   Remote_enabled = true ma FLY_APP_NAME non configurato.\n"
                "      Esegui: python deploy.py deploy <org>\n"
            )

        # 1. Splash screen
        SplashScreen(firmware, logo_path, proprieties).show()

        # 2. Dashboard WebSocket (thread daemon, callback aggiunto dopo)
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

        # 4. Numero di protocollo (conta i PDF già presenti)
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

        # 6. Wiring bidirezionale: risposte remote → metodo thread-safe dell'interfaccia
        dashboard.set_response_callback(interface.handle_remote_response)

        interface.run()


if __name__ == "__main__":
    Application().run()
