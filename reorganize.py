#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
reorganize.py
Riorganizza automaticamente la cartella del progetto ProcivBes Radio Team Tool.

Struttura risultante:
  PCBLRT/
  ├── app/                  ← moduli Python (non entry-point)
  │   ├── config_manager.py
  │   ├── log_interface.py
  │   ├── web_dashboard.py
  │   ├── recovery_manager.py
  │   ├── report_creator.py
  │   └── directory_selector.py
  ├── deploy/               ← strumenti di deploy
  │   ├── deploy.py
  │   └── deploy_registry.json
  ├── assets/               ← (rinominata da img/)
  ├── recovery/             ← invariata
  ├── reports/              ← invariata
  ├── main.py               ← entry point (rimane in root)
  ├── wsgi.py               ← entry point gunicorn (rimane in root)
  ├── Dockerfile            ← rimane in root (fly deploy lo richiede)
  ├── fly.toml              ← rimane in root
  ├── requirements.txt      ← rimane in root
  ├── configurator.txt
  ├── version.txt
  └── README.md

Uso:
    python reorganize.py          → anteprima (dry-run)
    python reorganize.py --apply  → esegue le modifiche
    python reorganize.py --undo   → ripristina il backup

Il backup viene creato in .backup_reorganize/ prima di qualsiasi modifica.
"""

import argparse
import json
import os
import re
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable


# ── Palette console ───────────────────────────────────────────────────────────

class C:
    RESET  = "\033[0m"
    BOLD   = "\033[1m"
    DIM    = "\033[2m"
    GREEN  = "\033[92m"
    YELLOW = "\033[93m"
    RED    = "\033[91m"
    CYAN   = "\033[96m"
    WHITE  = "\033[97m"

def ok(m):   print(f"  {C.GREEN}✔{C.RESET}  {m}")
def warn(m): print(f"  {C.YELLOW}⚠{C.RESET}  {m}")
def err(m):  print(f"  {C.RED}✘{C.RESET}  {m}")
def info(m): print(f"  {C.CYAN}→{C.RESET}  {m}")
def dry(m):  print(f"  {C.DIM}[DRY]{C.RESET} {m}")
def sep():   print(f"  {C.DIM}{'─' * 58}{C.RESET}")
def title(m):print(f"\n{C.BOLD}{C.WHITE}{m}{C.RESET}\n")


# ── Struttura del piano di riorganizzazione ───────────────────────────────────

ROOT        = Path(__file__).parent.resolve()
BACKUP_DIR  = ROOT / ".backup_reorganize"

# Cartelle da creare
NEW_DIRS = [
    ROOT / "app",
    ROOT / "deploy",
    ROOT / "assets",
]

# File da spostare: (sorgente relativa a ROOT, destinazione relativa a ROOT)
MOVES: list[tuple[str, str]] = [
    # → app/
    ("config_manager.py",    "app/config_manager.py"),
    ("log_interface.py",     "app/log_interface.py"),
    ("web_dashboard.py",     "app/web_dashboard.py"),
    ("recovery_manager.py",  "app/recovery_manager.py"),
    ("report_creator.py",    "app/report_creator.py"),
    ("directory_selector.py","app/directory_selector.py"),
    # → deploy/
    ("deploy.py",            "deploy/deploy.py"),
    ("deploy_registry.json", "deploy/deploy_registry.json"),
]

# Cartelle da rinominare: (vecchio nome, nuovo nome)
RENAMES: list[tuple[str, str]] = [
    ("img", "assets"),
]

# ── Patch da applicare ai file dopo lo spostamento ───────────────────────────
#
# Ogni patch è (file_relativo_a_ROOT, lista_di_(old_str, new_str))
# Le sostituzioni sono applicate nell'ordine indicato.

PATCHES: list[tuple[str, list[tuple[str, str]]]] = [

    # ── main.py ───────────────────────────────────────────────────────────────
    # Aggiunge app/ al sys.path e aggiorna gli import
    ("main.py", [
        (
            # Inserisce sys.path prima degli import locali
            "from config_manager import ConfigManager",
            (
                "# Aggiunto da reorganize.py — consente import da app/\n"
                "import sys as _sys\n"
                "_sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'app'))\n"
                "\n"
                "from config_manager import ConfigManager"
            ),
        ),
    ]),

    # ── wsgi.py ───────────────────────────────────────────────────────────────
    # Aggiunge app/ al sys.path prima dell'import di web_dashboard
    ("wsgi.py", [
        (
            "from web_dashboard import WebDashboard",
            (
                "import sys as _sys, os as _os\n"
                "_sys.path.insert(0, _os.path.join(_os.path.dirname(__file__), 'app'))\n"
                "\n"
                "from web_dashboard import WebDashboard"
            ),
        ),
    ]),

    # ── deploy/deploy.py ─────────────────────────────────────────────────────
    # Nota: in apply il file è già in deploy/; in dry-run punta al sorgente
    # La patch viene applicata sul file già spostato (step 4 precede step 5)
    ("deploy/deploy.py", [
        (
            'CONFIGURATOR   = Path("configurator.txt")      # file di config del progetto',
            'CONFIGURATOR   = Path(__file__).parent.parent / "configurator.txt"  # un livello sopra deploy/',
        ),
        # Aggiorna anche la costante REGISTRY_FILE per puntare a deploy/
        (
            'REGISTRY_FILE  = Path("deploy_registry.json") # DB locale delle istanze',
            'REGISTRY_FILE  = Path(__file__).parent / "deploy_registry.json"  # nella cartella deploy/',
        ),
    ]),

    # ── app/web_dashboard.py ─────────────────────────────────────────────────
    # Nessuna patch necessaria: web_dashboard non importa altri moduli locali

    # ── app/log_interface.py ─────────────────────────────────────────────────
    # Gli import sono già relativi (from recovery_manager import ...) e
    # funzionano perché app/ è in sys.path — nessuna patch necessaria

]


# ── ConfiguratorPatcher ───────────────────────────────────────────────────────

class ConfiguratorPatcher:
    """
    Aggiorna i path nel configurator.txt dopo la riorganizzazione.
    Sostituisce i riferimenti a img/ con assets/ nelle chiavi Logo_path e Flags_logo.
    """

    def __init__(self, path: Path):
        self._path = path

    def patch(self, dry_run: bool = False) -> list[str]:
        """
        Restituisce la lista delle righe modificate (per il report).
        Se dry_run=False applica le modifiche.
        """
        if not self._path.exists():
            warn(f"configurator.txt non trovato: {self._path}")
            return []

        lines     = self._path.read_text(encoding="utf-8").splitlines()
        new_lines = []
        changed   = []

        for line in lines:
            # Sostituisce img/ e img\ (Windows) con assets/ e assets\
            new_line = line.replace('img/', 'assets/')
            new_line = new_line.replace('img\\', 'assets\\')
            new_line = new_line.replace('img\\\\', 'assets\\\\')
            if new_line != line:
                changed.append((line.strip(), new_line.strip()))
            new_lines.append(new_line)

        if not dry_run and changed:
            self._path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")

        return changed


# ── Reorganizer ───────────────────────────────────────────────────────────────

class Reorganizer:
    """
    Esegue (o simula) la riorganizzazione della cartella di progetto.
    """

    def __init__(self, root: Path, dry_run: bool = True):
        self._root    = root
        self._dry_run = dry_run
        self._errors: list[str] = []

    # ── Public ────────────────────────────────────────────────────────────────

    def run(self) -> bool:
        """Esegue il piano completo. Restituisce True se tutto ok."""
        title("Piano di riorganizzazione" + (" [DRY RUN — nessuna modifica]" if self._dry_run else ""))

        if not self._dry_run:
            self._backup()

        self._create_dirs()
        self._rename_folders()
        self._move_files()
        self._apply_patches()
        self._patch_configurator()
        self._create_app_init()
        self._cleanup_pycache()

        sep()
        if self._errors:
            err(f"Completato con {len(self._errors)} errori:")
            for e in self._errors:
                print(f"    {C.RED}• {e}{C.RESET}")
            return False
        else:
            if self._dry_run:
                print(f"\n  {C.YELLOW}Usa --apply per applicare le modifiche.{C.RESET}\n")
            else:
                ok("Riorganizzazione completata con successo.")
                info(f"Backup disponibile in: {BACKUP_DIR.name}/")
                print(f"\n  {C.CYAN}Avvia il tool con:{C.RESET} python main.py")
                print(f"  {C.CYAN}Gestisci deploy con:{C.RESET} python deploy/deploy.py\n")
            return True

    def undo(self) -> bool:
        """Ripristina il backup."""
        title("Ripristino backup")
        if not BACKUP_DIR.exists():
            err(f"Backup non trovato: {BACKUP_DIR}")
            return False

        if not self._confirm("Ripristinare il backup? Tutti i file correnti verranno sovrascritti."):
            info("Operazione annullata.")
            return False

        # Ripristina ogni file dal backup
        restored = 0
        for backup_file in BACKUP_DIR.rglob("*"):
            if backup_file.is_file():
                rel    = backup_file.relative_to(BACKUP_DIR)
                target = self._root / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(backup_file, target)
                restored += 1

        ok(f"{restored} file ripristinati.")

        # Rimuovi cartelle create dalla riorganizzazione (se vuote o solo __init__)
        for d in ["app", "deploy"]:
            dpath = self._root / d
            if dpath.exists():
                # rimuovi solo se contiene solo file che erano stati spostati
                try:
                    shutil.rmtree(dpath)
                    info(f"Rimossa cartella: {d}/")
                except Exception as e:
                    warn(f"Non riuscito a rimuovere {d}/: {e}")

        # Ripristina img/ se assets/ era la rinomina
        assets = self._root / "assets"
        img    = self._root / "img"
        if assets.exists() and not img.exists():
            assets.rename(img)
            info("assets/ → img/ (ripristinato)")

        ok("Ripristino completato.")
        return True

    # ── Private: steps ────────────────────────────────────────────────────────

    def _backup(self) -> None:
        title("1. Backup")
        if BACKUP_DIR.exists():
            shutil.rmtree(BACKUP_DIR)

        # Backup dei soli file che verranno modificati/spostati
        files_to_backup = (
            [src for src, _ in MOVES]
            + ["main.py", "wsgi.py", "configurator.txt"]
            + [old for old, _ in RENAMES]
        )

        backed = 0
        for rel in files_to_backup:
            src = self._root / rel
            if src.exists():
                dst = BACKUP_DIR / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                if src.is_dir():
                    shutil.copytree(src, dst)
                else:
                    shutil.copy2(src, dst)
                backed += 1

        ok(f"Backup di {backed} file/cartelle → {BACKUP_DIR.name}/")

    def _create_dirs(self) -> None:
        title("2. Creazione cartelle")
        for d in NEW_DIRS:
            rel = d.relative_to(self._root)
            if d.exists():
                info(f"Già esistente: {rel}/")
            else:
                if not self._dry_run:
                    d.mkdir(parents=True, exist_ok=True)
                dry(f"mkdir {rel}/") if self._dry_run else ok(f"Creata: {rel}/")

    def _rename_folders(self) -> None:
        title("3. Rinomina cartelle")
        for old_name, new_name in RENAMES:
            old = self._root / old_name
            new = self._root / new_name
            if not old.exists():
                warn(f"Cartella non trovata, skip: {old_name}/")
                continue
            if new.exists():
                warn(f"Destinazione già esistente, skip: {new_name}/")
                continue
            if self._dry_run:
                dry(f"{old_name}/ → {new_name}/")
            else:
                old.rename(new)
                ok(f"{old_name}/ → {new_name}/")

    def _move_files(self) -> None:
        title("4. Spostamento file")
        for src_rel, dst_rel in MOVES:
            src = self._root / src_rel
            dst = self._root / dst_rel
            if not src.exists():
                warn(f"File non trovato, skip: {src_rel}")
                continue
            if self._dry_run:
                dry(f"{src_rel} → {dst_rel}")
            else:
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(src), str(dst))
                ok(f"{src_rel} → {dst_rel}")

    def _apply_patches(self) -> None:
        title("5. Aggiornamento import e path nei file Python")
        for file_rel, replacements in PATCHES:
            fpath = self._root / file_rel
            # In dry-run deploy/deploy.py non esiste ancora: prova il path originale
            if not fpath.exists():
                alt = self._root / Path(file_rel).name
                if alt.exists():
                    fpath = alt
                else:
                    warn(f"File non trovato, skip patch: {file_rel}")
                    continue

            text = fpath.read_text(encoding="utf-8")
            applied = []

            for old, new in replacements:
                if old in text:
                    if not self._dry_run:
                        text = text.replace(old, new, 1)
                    applied.append(old.splitlines()[0][:60] + "…")
                else:
                    warn(f"Stringa non trovata in {file_rel}: {old[:50]}…")

            if applied:
                if not self._dry_run:
                    fpath.write_text(text, encoding="utf-8")
                for a in applied:
                    dry(f"patch {file_rel}: {a}") if self._dry_run else ok(f"Patchato {file_rel}")

    def _patch_configurator(self) -> None:
        title("6. Aggiornamento configurator.txt (img/ → assets/)")
        patcher = ConfiguratorPatcher(self._root / "configurator.txt")
        changes = patcher.patch(dry_run=self._dry_run)
        if changes:
            for old, new in changes:
                dry(f"  {old}  →  {new}") if self._dry_run else ok(f"  {old}  →  {new}")
        else:
            info("Nessuna occorrenza di img/ trovata nel configurator.")

    def _create_app_init(self) -> None:
        title("7. Creazione app/__init__.py")
        init = self._root / "app" / "__init__.py"
        content = "# Pacchetto app — moduli Python del progetto ProcivBes Radio Team Tool\n"
        if self._dry_run:
            dry("app/__init__.py")
        else:
            init.write_text(content, encoding="utf-8")
            ok("app/__init__.py creato")

    def _cleanup_pycache(self) -> None:
        title("8. Pulizia __pycache__")
        for pycache in self._root.rglob("__pycache__"):
            if BACKUP_DIR in pycache.parents:
                continue
            if self._dry_run:
                dry(f"rm -rf {pycache.relative_to(self._root)}")
            else:
                shutil.rmtree(pycache)
                ok(f"Rimosso: {pycache.relative_to(self._root)}")

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _confirm(prompt: str) -> bool:
        ans = input(f"\n  {C.YELLOW}{prompt}{C.RESET} [s/N] ").strip().lower()
        return ans in ("s", "si", "sì", "y", "yes")

    def _record_error(self, msg: str) -> None:
        self._errors.append(msg)
        err(msg)


# ── Verifica post-riorganizzazione ────────────────────────────────────────────

class PostCheck:
    """
    Verifica che la struttura risultante sia coerente.
    Controlla la sintassi Python e la presenza dei file chiave.
    """

    REQUIRED = [
        "main.py", "wsgi.py", "Dockerfile", "fly.toml",
        "requirements.txt", "configurator.txt",
        "app/config_manager.py", "app/log_interface.py",
        "app/web_dashboard.py", "app/recovery_manager.py",
        "app/report_creator.py", "app/directory_selector.py",
        "deploy/deploy.py",
    ]

    def __init__(self, root: Path):
        self._root = root

    def run(self) -> bool:
        title("Verifica post-riorganizzazione")
        ok_count  = 0
        err_count = 0

        # 1. File presenti
        for rel in self.REQUIRED:
            p = self._root / rel
            if p.exists():
                ok(f"Presente: {rel}")
                ok_count += 1
            else:
                err(f"Mancante: {rel}")
                err_count += 1

        # 2. Sintassi Python
        sep()
        import ast
        py_files = list((self._root / "app").glob("*.py")) + [
            self._root / "main.py",
            self._root / "wsgi.py",
            self._root / "deploy" / "deploy.py",
        ]
        for pyf in py_files:
            if not pyf.exists():
                continue
            try:
                ast.parse(pyf.read_text(encoding="utf-8"))
                ok(f"Sintassi OK: {pyf.relative_to(self._root)}")
                ok_count += 1
            except SyntaxError as e:
                err(f"Errore sintassi {pyf.relative_to(self._root)}: {e}")
                err_count += 1

        sep()
        print(f"\n  {C.GREEN}{ok_count} check OK{C.RESET}  "
              f"{C.RED}{err_count} errori{C.RESET}\n")
        return err_count == 0


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Riorganizza la struttura del progetto ProcivBes Radio Team Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Esempi:
  python reorganize.py            # anteprima (dry-run)
  python reorganize.py --apply    # esegue le modifiche con backup automatico
  python reorganize.py --check    # verifica la struttura attuale
  python reorganize.py --undo     # ripristina il backup
        """
    )
    parser.add_argument("--apply", action="store_true",
                        help="Applica le modifiche (default: dry-run)")
    parser.add_argument("--check", action="store_true",
                        help="Verifica la struttura senza modificare nulla")
    parser.add_argument("--undo",  action="store_true",
                        help="Ripristina il backup precedente")

    args = parser.parse_args()

    # Banner
    print(f"""
{C.CYAN}{C.BOLD}  ┌─────────────────────────────────────────────────┐
  │  ProcivBes Radio Team Tool — Reorganizer v1.0   │
  └─────────────────────────────────────────────────┘{C.RESET}""")
    info(f"Cartella progetto: {ROOT}")

    if args.undo:
        Reorganizer(ROOT, dry_run=False).undo()

    elif args.check:
        PostCheck(ROOT).run()

    elif args.apply:
        r = Reorganizer(ROOT, dry_run=False)
        success = r.run()
        if success:
            PostCheck(ROOT).run()

    else:
        # Dry run di default
        Reorganizer(ROOT, dry_run=True).run()


if __name__ == "__main__":
    main()
