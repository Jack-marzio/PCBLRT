#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
deploy.py
Script interattivo per il deploy della dashboard RadioLog su Fly.io.

Uso:
    python deploy.py               → menu interattivo
    python deploy.py list          → elenca tutte le istanze deployate
    python deploy.py deploy <org>  → deploya una nuova org
    python deploy.py destroy <org> → rimuove un'istanza
    python deploy.py token <org>   → mostra/rinnova il token di un'org
    python deploy.py status        → stato di tutte le macchine
"""

import argparse
import json
import os
import re
import secrets
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional


# ── Configurazione globale ───────────────────────────────────────────────────

APP_PREFIX     = "radiolog"                    # prefisso del nome app su Fly.io
DEFAULT_REGION = "ams"                         # Amsterdam (vicino all'Italia)
REGISTRY_FILE  = Path("deploy_registry.json") # DB locale delle istanze
CONFIGURATOR   = Path("configurator.txt")      # file di config del progetto
FLY_BIN        = "flyctl"                      # o "fly" a seconda della versione installata


# ── ANSI colors ──────────────────────────────────────────────────────────────

class C:
    RESET  = "\033[0m"
    BOLD   = "\033[1m"
    DIM    = "\033[2m"
    GREEN  = "\033[92m"
    YELLOW = "\033[93m"
    RED    = "\033[91m"
    CYAN   = "\033[96m"
    BLUE   = "\033[94m"
    WHITE  = "\033[97m"

def ok(msg: str)    -> None: print(f"  {C.GREEN}✔{C.RESET}  {msg}")
def warn(msg: str)  -> None: print(f"  {C.YELLOW}⚠{C.RESET}  {msg}")
def err(msg: str)   -> None: print(f"  {C.RED}✘{C.RESET}  {msg}")
def info(msg: str)  -> None: print(f"  {C.CYAN}→{C.RESET}  {msg}")
def title(msg: str) -> None: print(f"\n{C.BOLD}{C.WHITE}{msg}{C.RESET}\n")
def sep()           -> None: print(f"  {C.DIM}{'─' * 60}{C.RESET}")


# ── Struttura dati istanza ────────────────────────────────────────────────────

@dataclass
class OrgInstance:
    org_name:   str
    app_name:   str
    token:      str
    region:     str
    deployed_at: str
    url:        str = field(init=False)

    def __post_init__(self):
        self.url = f"https://{self.app_name}.fly.dev?token={self.token}"

    def to_dict(self) -> dict:
        return {
            "org_name"   : self.org_name,
            "app_name"   : self.app_name,
            "token"      : self.token,
            "region"     : self.region,
            "deployed_at": self.deployed_at,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "OrgInstance":
        return cls(
            org_name    = d["org_name"],
            app_name    = d["app_name"],
            token       = d["token"],
            region      = d["region"],
            deployed_at = d["deployed_at"],
        )




# ── ConfiguratorUpdater ───────────────────────────────────────────────────────

class ConfiguratorUpdater:
    """
    Legge e aggiorna configurator.txt mantenendo intatta tutta la struttura
    esistente. Scrive o sovrascrive solo le chiavi gestite dal deploy:
      WS_TOKEN, FLY_APP_NAME, WS_PUBLIC_URL.

    Il formato del file è: chiave = valore  (una per riga, righe vuote ignorate).
    """

    MANAGED_KEYS = {"WS_TOKEN", "FLY_APP_NAME", "WS_PUBLIC_URL"}

    def __init__(self, path: Path = CONFIGURATOR):
        self._path = path

    def update(self, instance: "OrgInstance") -> None:
        """
        Aggiorna (o aggiunge in coda) le chiavi di deploy nel configurator.
        Crea il file se non esiste ancora.
        """
        values = {
            "WS_TOKEN"      : instance.token,
            "FLY_APP_NAME"  : instance.app_name,
            "WS_PUBLIC_URL" : instance.url,
        }

        if self._path.exists():
            lines = self._path.read_text(encoding="utf-8").splitlines()
        else:
            lines = []

        # Sostituisci le righe esistenti con le chiavi gestite
        updated_keys: set[str] = set()
        new_lines: list[str] = []

        for line in lines:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                new_lines.append(line)
                continue
            if "=" in stripped:
                key = stripped.split("=", 1)[0].strip()
                if key in values:
                    new_lines.append(f"{key} = {values[key]}")
                    updated_keys.add(key)
                    continue
            new_lines.append(line)

        # Aggiungi in coda le chiavi non ancora presenti
        missing = set(values) - updated_keys
        if missing:
            new_lines.append("")
            new_lines.append("# ── Deploy info (aggiornato automaticamente da deploy.py) ──")
            for key in sorted(missing):
                new_lines.append(f"{key} = {values[key]}")

        self._path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
        ok(f"configurator.txt aggiornato → {self._path.resolve()}")

    def clear(self) -> None:
        """Rimuove le chiavi di deploy dal configurator (usato da destroy)."""
        if not self._path.exists():
            return
        lines = self._path.read_text(encoding="utf-8").splitlines()
        new_lines = [
            l for l in lines
            if not any(l.strip().startswith(k) for k in self.MANAGED_KEYS)
        ]
        # Rimuovi commento rimasto orfano
        filtered: list[str] = []
        for line in new_lines:
            if line.strip() == "# ── Deploy info (aggiornato automaticamente da deploy.py) ──":
                continue
            filtered.append(line)
        self._path.write_text("\n".join(filtered) + "\n", encoding="utf-8")
        ok("Chiavi deploy rimosse da configurator.txt")


# ── Registry (persistenza locale) ────────────────────────────────────────────

class Registry:
    """
    Mantiene un file JSON locale con le istanze deployate.
    Funziona come fonte di verità lato programmatore.
    """

    def __init__(self, path: Path = REGISTRY_FILE):
        self._path = path
        self._data: dict[str, dict] = {}
        self._load()

    def _load(self) -> None:
        if self._path.exists():
            with open(self._path, "r", encoding="utf-8") as f:
                self._data = json.load(f)

    def _save(self) -> None:
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=2, ensure_ascii=False)
        ok(f"Registry aggiornato → {self._path}")

    def add(self, instance: OrgInstance) -> None:
        self._data[instance.org_name] = instance.to_dict()
        self._save()

    def remove(self, org_name: str) -> None:
        self._data.pop(org_name, None)
        self._save()

    def get(self, org_name: str) -> Optional[OrgInstance]:
        d = self._data.get(org_name)
        return OrgInstance.from_dict(d) if d else None

    def all(self) -> list[OrgInstance]:
        return [OrgInstance.from_dict(d) for d in self._data.values()]

    def exists(self, org_name: str) -> bool:
        return org_name in self._data

    def update_token(self, org_name: str, new_token: str) -> None:
        if org_name in self._data:
            self._data[org_name]["token"] = new_token
            self._save()


# ── Fly.io wrapper ────────────────────────────────────────────────────────────

class FlyClient:
    """Wrapper per i comandi flyctl via subprocess."""

    def __init__(self, binary: str = FLY_BIN):
        self._bin = binary
        self._check_installed()

    def _check_installed(self) -> None:
        result = subprocess.run(
            [self._bin, "version"],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            err(f"flyctl non trovato. Installalo con:")
            print(f"       curl -L https://fly.io/install.sh | sh")
            sys.exit(1)

    def _run(self, args: list[str], check: bool = True) -> subprocess.CompletedProcess:
        """Esegue un comando fly e mostra output in tempo reale."""
        cmd = [self._bin] + args
        info(f"$ {' '.join(cmd)}")
        result = subprocess.run(cmd, text=True)
        if check and result.returncode != 0:
            err(f"Comando fallito (exit {result.returncode})")
            raise RuntimeError(f"flyctl error: {' '.join(args)}")
        return result

    def _run_capture(self, args: list[str]) -> str:
        """Esegue un comando e cattura l'output."""
        cmd = [self._bin] + args
        result = subprocess.run(cmd, capture_output=True, text=True)
        return result.stdout.strip()

    def app_exists(self, app_name: str) -> bool:
        output = self._run_capture(["apps", "list"])
        return app_name in output

    def launch(self, app_name: str, region: str) -> None:
        self._run([
            "launch",
            "--name", app_name,
            "--region", region,
            "--no-deploy",
            "--yes",
        ])

    def set_secret(self, app_name: str, key: str, value: str) -> None:
        self._run([
            "secrets", "set",
            f"{key}={value}",
            "--app", app_name,
        ])

    def deploy(self, app_name: str) -> None:
        self._run(["deploy", "--app", app_name])

    def destroy(self, app_name: str) -> None:
        self._run(["apps", "destroy", app_name, "--yes"])

    def status(self, app_name: str) -> str:
        return self._run_capture(["status", "--app", app_name])

    def list_apps(self) -> str:
        return self._run_capture(["apps", "list"])


# ── DeployManager ─────────────────────────────────────────────────────────────

class DeployManager:
    """
    Orchestratore principale.
    Combina Registry e FlyClient per gestire il ciclo di vita
    delle istanze per organizzazione.
    """

    def __init__(self):
        self._registry     = Registry()
        self._fly          = FlyClient()
        self._configurator = ConfiguratorUpdater()

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def deploy(self, org_name: str, region: str = DEFAULT_REGION) -> OrgInstance:
        """
        Deploya una nuova istanza per l'organizzazione indicata.
        Se esiste già chiede conferma prima di sovrascrivere.
        """
        org_name  = self._sanitize_name(org_name)
        app_name  = f"{APP_PREFIX}-{org_name}"

        title(f"Deploy → {app_name}")

        if self._registry.exists(org_name):
            warn(f"Istanza '{org_name}' già presente nel registry.")
            if not self._confirm("Vuoi fare un re-deploy (aggiorna token)?"):
                info("Operazione annullata.")
                return self._registry.get(org_name)

        token = secrets.token_urlsafe(32)
        sep()
        info(f"App name : {app_name}")
        info(f"Region   : {region}")
        info(f"Token    : {token[:8]}... (nascosto)")
        sep()

        if not self._confirm("Procedo con il deploy?"):
            info("Operazione annullata.")
            sys.exit(0)

        # 1. Crea l'app su Fly.io (se non esiste già)
        if not self._fly.app_exists(app_name):
            info("Creazione app su Fly.io...")
            self._fly.launch(app_name, region)
        else:
            info("App già esistente su Fly.io, aggiorno il token...")

        # 2. Imposta il token segreto
        info("Impostazione WS_TOKEN...")
        self._fly.set_secret(app_name, "WS_TOKEN", token)

        # 3. Deploy del codice
        info("Deploy del codice...")
        self._fly.deploy(app_name)

        # 4. Salva nel registry
        instance = OrgInstance(
            org_name    = org_name,
            app_name    = app_name,
            token       = token,
            region      = region,
            deployed_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        )
        self._registry.add(instance)
        self._configurator.update(instance)

        sep()
        ok(f"Deploy completato!")
        self._print_instance_card(instance)
        return instance

    def destroy(self, org_name: str) -> None:
        """Rimuove un'istanza da Fly.io e dal registry."""
        org_name = self._sanitize_name(org_name)
        instance = self._registry.get(org_name)

        if not instance:
            err(f"Organizzazione '{org_name}' non trovata nel registry.")
            self._list_orgs_hint()
            return

        title(f"Destroy → {instance.app_name}")
        warn("Questa operazione è IRREVERSIBILE.")
        info(f"App     : {instance.app_name}")
        info(f"Org     : {instance.org_name}")
        info(f"Deploy  : {instance.deployed_at}")

        if not self._confirm(f"Sei sicuro di voler eliminare '{instance.app_name}'?"):
            info("Operazione annullata.")
            return

        self._fly.destroy(instance.app_name)
        self._registry.remove(org_name)
        self._configurator.clear()
        ok(f"Istanza '{org_name}' rimossa.")

    def rotate_token(self, org_name: str) -> None:
        """Genera un nuovo token e lo aggiorna su Fly.io e nel registry."""
        org_name = self._sanitize_name(org_name)
        instance = self._registry.get(org_name)

        if not instance:
            err(f"Organizzazione '{org_name}' non trovata nel registry.")
            self._list_orgs_hint()
            return

        title(f"Rinnovo token → {instance.app_name}")
        warn("Il vecchio link smetterà di funzionare immediatamente.")

        if not self._confirm("Procedo con il rinnovo del token?"):
            info("Operazione annullata.")
            return

        new_token = secrets.token_urlsafe(32)
        self._fly.set_secret(instance.app_name, "WS_TOKEN", new_token)
        self._registry.update_token(org_name, new_token)

        # Aggiorna l'istanza locale per la stampa e il configurator
        instance.token = new_token
        self._configurator.update(instance)

        ok("Token rinnovato.")
        self._print_instance_card(instance)

    def list_all(self) -> None:
        """Elenca tutte le istanze nel registry con URL."""
        instances = self._registry.all()
        title("Istanze deployate")

        if not instances:
            warn("Nessuna istanza nel registry.")
            info("Usa: python deploy.py deploy <nome-org>")
            return

        for inst in instances:
            sep()
            self._print_instance_card(inst)

        sep()
        info(f"Totale: {len(instances)} istanza/e")

    def status_all(self) -> None:
        """Mostra lo stato Fly.io di tutte le istanze."""
        instances = self._registry.all()
        title("Stato macchine Fly.io")

        if not instances:
            warn("Nessuna istanza nel registry.")
            return

        for inst in instances:
            sep()
            print(f"\n  {C.BOLD}{inst.org_name}{C.RESET} ({inst.app_name})")
            output = self._fly.status(inst.app_name)
            for line in output.splitlines():
                print(f"    {C.DIM}{line}{C.RESET}")

    def show_token(self, org_name: str) -> None:
        """Mostra il token e il link completo di un'organizzazione."""
        org_name = self._sanitize_name(org_name)
        instance = self._registry.get(org_name)

        if not instance:
            err(f"Organizzazione '{org_name}' non trovata nel registry.")
            self._list_orgs_hint()
            return

        title(f"Token → {org_name}")
        self._print_instance_card(instance)

    # ------------------------------------------------------------------
    # Interactive menu
    # ------------------------------------------------------------------

    def interactive(self) -> None:
        """Menu interattivo per chi non vuole usare argomenti CLI."""
        self._print_banner()

        while True:
            title("Menu principale")
            print(f"  {C.CYAN}1{C.RESET}  Deploy nuova organizzazione")
            print(f"  {C.CYAN}2{C.RESET}  Elenca tutte le istanze")
            print(f"  {C.CYAN}3{C.RESET}  Mostra token / link")
            print(f"  {C.CYAN}4{C.RESET}  Rinnova token")
            print(f"  {C.CYAN}5{C.RESET}  Stato macchine Fly.io")
            print(f"  {C.CYAN}6{C.RESET}  Rimuovi istanza")
            print(f"  {C.CYAN}0{C.RESET}  Esci")
            print()

            choice = input("  Scelta: ").strip()

            if choice == "1":
                org = input("  Nome organizzazione: ").strip()
                if not org:
                    err("Nome obbligatorio.")
                    continue
                region = input(f"  Regione [{DEFAULT_REGION}]: ").strip() or DEFAULT_REGION
                self.deploy(org, region)

            elif choice == "2":
                self.list_all()

            elif choice == "3":
                org = input("  Nome organizzazione: ").strip()
                self.show_token(org)

            elif choice == "4":
                org = input("  Nome organizzazione: ").strip()
                self.rotate_token(org)

            elif choice == "5":
                self.status_all()

            elif choice == "6":
                org = input("  Nome organizzazione: ").strip()
                self.destroy(org)

            elif choice == "0":
                info("Uscita.")
                sys.exit(0)

            else:
                warn("Scelta non valida.")

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _sanitize_name(name: str) -> str:
        """Normalizza il nome: minuscolo, solo lettere/numeri/trattini."""
        name = name.lower().strip()
        name = re.sub(r"[^a-z0-9-]", "-", name)
        name = re.sub(r"-+", "-", name).strip("-")
        if not name:
            err("Nome organizzazione non valido.")
            sys.exit(1)
        return name

    @staticmethod
    def _confirm(prompt: str) -> bool:
        answer = input(f"\n  {C.YELLOW}{prompt}{C.RESET} [s/N] ").strip().lower()
        return answer in ("s", "si", "sì", "y", "yes")

    def _list_orgs_hint(self) -> None:
        orgs = [i.org_name for i in self._registry.all()]
        if orgs:
            info(f"Organizzazioni disponibili: {', '.join(orgs)}")

    @staticmethod
    def _print_instance_card(instance: OrgInstance) -> None:
        print(f"\n  {C.BOLD}Organizzazione :{C.RESET} {C.GREEN}{instance.org_name}{C.RESET}")
        print(f"  {C.BOLD}App Fly.io      :{C.RESET} {instance.app_name}")
        print(f"  {C.BOLD}Regione         :{C.RESET} {instance.region}")
        print(f"  {C.BOLD}Deployato il    :{C.RESET} {instance.deployed_at}")
        print(f"  {C.BOLD}Token           :{C.RESET} {C.DIM}{instance.token}{C.RESET}")
        print(f"\n  {C.BOLD}🌐 Link da condividere:{C.RESET}")
        print(f"  {C.BLUE}{C.BOLD}{instance.url}{C.RESET}\n")

    @staticmethod
    def _print_banner() -> None:
        print(f"""
{C.CYAN}{C.BOLD}
  ██████╗  █████╗ ██████╗ ██╗ ██████╗ ██╗      ██████╗  ██████╗
  ██╔══██╗██╔══██╗██╔══██╗██║██╔═══██╗██║     ██╔═══██╗██╔════╝
  ██████╔╝███████║██║  ██║██║██║   ██║██║     ██║   ██║██║  ███╗
  ██╔══██╗██╔══██║██║  ██║██║██║   ██║██║     ██║   ██║██║   ██║
  ██║  ██║██║  ██║██████╔╝██║╚██████╔╝███████╗╚██████╔╝╚██████╔╝
  ╚═╝  ╚═╝╚═╝  ╚═╝╚═════╝ ╚═╝ ╚═════╝ ╚══════╝ ╚═════╝  ╚═════╝
{C.RESET}{C.DIM}  Dashboard Deploy Manager — ProcivBes Radio Team Tool{C.RESET}
""")


# ── CLI entrypoint ────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Deploy manager per RadioLog Dashboard su Fly.io",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Esempi:
  python deploy.py                        # menu interattivo
  python deploy.py deploy prociv-torino   # deploya org
  python deploy.py deploy prociv-milano --region cdg  # con regione custom
  python deploy.py list                   # elenca istanze
  python deploy.py token prociv-torino    # mostra link e token
  python deploy.py rotate prociv-torino   # rinnova token
  python deploy.py status                 # stato macchine
  python deploy.py destroy prociv-torino  # rimuovi istanza
        """,
    )

    subparsers = parser.add_subparsers(dest="command")

    # deploy
    p_deploy = subparsers.add_parser("deploy", help="Deploya una nuova org")
    p_deploy.add_argument("org", help="Nome organizzazione (es. prociv-torino)")
    p_deploy.add_argument("--region", default=DEFAULT_REGION, help=f"Regione Fly.io (default: {DEFAULT_REGION})")

    # list
    subparsers.add_parser("list", help="Elenca tutte le istanze")

    # token
    p_token = subparsers.add_parser("token", help="Mostra token e link di un'org")
    p_token.add_argument("org", help="Nome organizzazione")

    # rotate
    p_rotate = subparsers.add_parser("rotate", help="Rinnova il token di un'org")
    p_rotate.add_argument("org", help="Nome organizzazione")

    # status
    subparsers.add_parser("status", help="Stato macchine Fly.io")

    # destroy
    p_destroy = subparsers.add_parser("destroy", help="Rimuovi un'istanza")
    p_destroy.add_argument("org", help="Nome organizzazione")

    args = parser.parse_args()
    manager = DeployManager()

    if args.command == "deploy":
        manager.deploy(args.org, args.region)
    elif args.command == "list":
        manager.list_all()
    elif args.command == "token":
        manager.show_token(args.org)
    elif args.command == "rotate":
        manager.rotate_token(args.org)
    elif args.command == "status":
        manager.status_all()
    elif args.command == "destroy":
        manager.destroy(args.org)
    else:
        manager.interactive()


if __name__ == "__main__":
    main()
