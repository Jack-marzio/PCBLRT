"""
build.py — Script di compilazione per PCBLRT
Registro delle comunicazioni radio v6.0
Uso: python build.py [--onefile] [--debug]
"""

import subprocess
import sys
import os
import shutil
import argparse
from pathlib import Path

# Console Windows con codifica legacy (cp1252) manda in crash i print() con
# caratteri come "✔" o "❌". Forza UTF-8 sullo stream prima di qualunque output.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

# ──────────────────────────────────────────────
# CONFIGURAZIONE
# ──────────────────────────────────────────────
APP_NAME        = "Registro_comunicazioni_radio"
MAIN_SCRIPT     = "app/main.py"
ICON_PATH       = "assets/logo_provincia.ico"   # converti .png → .ico se necessario
VERSION_FILE    = "version.txt"
CONFIGURATOR    = "configurator.txt"

# Dati aggiuntivi da includere nell'eseguibile: (sorgente, destinazione_interna)
ADDED_DATA = [
    ("assets",         "assets"),
    ("configurator.txt", "."),
]

# Moduli nascosti che PyInstaller non rileva automaticamente
HIDDEN_IMPORTS = [
    "flask",
    "PIL",
    "PIL.Image",
    "openpyxl",
    "fpdf",
    "qrcode",
    "tkintermapview",
]

# ──────────────────────────────────────────────
# HELPERS
# ──────────────────────────────────────────────



def run(cmd: list[str], check=True):
    print(f"\n▶  {' '.join(cmd)}\n")
    result = subprocess.run(cmd, check=check)
    return result.returncode


def ensure_pyinstaller():
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("PyInstaller non trovato. Installazione in corso...")
        run([sys.executable, "-m", "pip", "install", "pyinstaller"])


def png_to_ico(png_path: str) -> str:
    """Converte PNG → ICO e restituisce il percorso .ico."""
    ico_path = png_path.replace(".png", ".ico")
    if os.path.exists(ico_path):
        return ico_path
    try:
        from PIL import Image
        img = Image.open(png_path)
        img.save(ico_path, format="ICO", sizes=[(256, 256), (128, 128), (64, 64), (32, 32), (16, 16)])
        print(f"✔  Icona convertita: {ico_path}")
        return ico_path
    except Exception as e:
        print(f"⚠️  Impossibile convertire icona ({e}). Compilazione senza icona.")
        return ""


def fix_configurator():
    """
    Ripulisce configurator.txt dai duplicati lasciati dalla sessione precedente
    e aggiunge Firebase_database_url se mancante.
    """
    path = Path(CONFIGURATOR)
    if not path.exists():
        print(f"⚠️  {CONFIGURATOR} non trovato, skip.")
        return

    lines = path.read_text(encoding="utf-8").splitlines()

    # Rimuovi blocco duplicato: tieni solo la sezione DOPO il '#'
    separator_idx = None
    for i, line in enumerate(lines):
        if line.strip() == "#":
            separator_idx = i
            break

    if separator_idx is not None:
        clean_lines = [l for l in lines[separator_idx + 1:] if l.strip()]
    else:
        clean_lines = [l for l in lines if l.strip()]

    # Assicura che Firebase_database_url sia presente
    keys_present = {l.split("=")[0].strip().lower() for l in clean_lines if "=" in l}
    if "firebase_database_url" not in keys_present:
        clean_lines.append(
            "Firebase_database_url=https://tlcvarese-default-rtdb.europe-west1.firebasedatabase.app"
        )
        print("✔  Aggiunto Firebase_database_url al configurator.")

    path.write_text("\n".join(clean_lines) + "\n", encoding="utf-8")
    print(f"✔  {CONFIGURATOR} ripulito ({len(clean_lines)} righe).")


def clean_build():
    for folder in ("build", "dist/__pycache__"):
        if os.path.exists(folder):
            shutil.rmtree(folder)
            print(f"✔  Rimossa cartella: {folder}")
    for spec in Path(".").glob("*.spec"):
        spec.unlink()
        print(f"✔  Rimosso: {spec}")


# ──────────────────────────────────────────────
# BUILD
# ──────────────────────────────────────────────

def build(onefile: bool = True, debug: bool = False):
    ensure_pyinstaller()

    # Icona
    icon_arg = []
    if os.path.exists(ICON_PATH):
        icon_arg = ["--icon", ICON_PATH]
    elif os.path.exists(ICON_PATH.replace(".ico", ".png")):
        ico = png_to_ico(ICON_PATH.replace(".ico", ".png"))
        if ico:
            icon_arg = ["--icon", ico]

    # Dati aggiuntivi
    sep = ";" if sys.platform == "win32" else ":"
    data_args = []
    for src, dst in ADDED_DATA:
        if os.path.exists(src):
            data_args += ["--add-data", f"{src}{sep}{dst}"]
        else:
            print(f"⚠️  Percorso non trovato, skip: {src}")

    # Hidden imports
    hidden_args = []
    for mod in HIDDEN_IMPORTS:
        hidden_args += ["--hidden-import", mod]

    # Versione (solo Windows)
    version_args = []
    if sys.platform == "win32" and os.path.exists(VERSION_FILE):
        version_args = ["--version-file", VERSION_FILE]

    # Modalità
    mode_arg = ["--onefile"] if onefile else ["--onedir"]

    # Finestra / console
    window_arg = ["--noconsole"] if not debug else ["--console"]

    cmd = (
        [sys.executable, "-m", "PyInstaller"]
        + mode_arg
        + window_arg
        + ["--name", APP_NAME]
        + ["--paths", "app"]          # ← AGGIUNGI QUESTA RIGA
        + icon_arg
        + data_args
        + hidden_args
        + version_args
        + [MAIN_SCRIPT]
    )

    return run(cmd)


# ──────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Build PCBLRT executable")
    parser.add_argument("--onefile",  action="store_true", default=True,
                        help="Crea un singolo .exe (default)")
    parser.add_argument("--onedir",   action="store_true",
                        help="Crea una cartella dist/ invece di un singolo .exe")
    parser.add_argument("--debug",    action="store_true",
                        help="Mantieni la finestra console per debug")
    parser.add_argument("--clean",    action="store_true",
                        help="Rimuovi artefatti di build precedenti prima di compilare")
    args = parser.parse_args()

    onefile = not args.onedir  # onefile è il default

    print("=" * 55)
    print(f"  Build: {APP_NAME}  v6.0")
    print(f"  Modalità: {'onefile' if onefile else 'onedir'}"
          f"  |  Debug console: {args.debug}")
    print("=" * 55)

    # 1. Ripulisci configurator
    fix_configurator()

    # 2. Pulisci build precedente
    if args.clean:
        clean_build()

    # 3. Verifica che main.py esista
    if not os.path.exists(MAIN_SCRIPT):
        print(f"\n❌  Errore: {MAIN_SCRIPT} non trovato.")
        print("   Assicurati di eseguire build.py dalla root del progetto (PCBLRT/).")
        sys.exit(1)

    # 4. Compila
    rc = build(onefile=onefile, debug=args.debug)

    if rc == 0:
        out = Path("dist") / (APP_NAME + (".exe" if sys.platform == "win32" else ""))
        print("\n" + "=" * 55)
        print(f"✅  Build completato!")
        print(f"   Output: {out.resolve()}")
        print("=" * 55)
    else:
        print("\n❌  Build fallita. Controlla i messaggi sopra.")
        sys.exit(rc)


if __name__ == "__main__":
    main()
