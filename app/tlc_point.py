# -*- coding: utf-8 -*-
"""
tlc_point.py
TLC Point — gestione carico/scarico degli apparati radio.

Un registro Excel (creato automaticamente al primo avvio se assente)
tiene traccia degli apparati e dei relativi movimenti di carico/scarico,
così i dati sopravvivono ai riavvii dell'app e restano comunque
consultabili/modificabili a mano in Excel.

Il pannello Tkinter è pensato per l'uso con un lettore di codici a
barre/QR USB (che si comporta come una tastiera: "digita" il codice e
preme Invio): basta lasciare il focus sul campo "codice" e scansionare,
l'app processa il codice non appena arriva l'Invio automatico del
lettore. Funziona ovviamente anche digitando il codice a mano.

Struttura del file Excel (due fogli):

  Apparati  → anagrafica + stato corrente di ogni apparato
              Codice | Modello | Numero_seriale | Note |
              Stato | Assegnato_a | Data_ultimo_movimento | Alias | ODV | Cellulare

  Movimenti → log storico di ogni carico/scarico
              Data_ora | Codice | Modello | Operazione | Persona | Operatore |
              Alias | ODV | Cellulare
"""

import os
import sys
import tkinter as tk
from datetime import datetime
from tkinter import filedialog, messagebox, ttk
from typing import Callable, Optional

from openpyxl import Workbook, load_workbook

from report_creator import ReportCreator
from ui_utils import Tooltip, add_vscrollbar, show_banner

try:
    import qrcode
    _QRCODE_AVAILABLE = True
except ImportError:
    _QRCODE_AVAILABLE = False

if sys.platform == "win32":
    try:
        import winsound
        _SOUND_AVAILABLE = True
    except ImportError:
        _SOUND_AVAILABLE = False
else:
    _SOUND_AVAILABLE = False


def _beep(kind: str = "ok") -> None:
    """
    Conferma sonora per scan/carico/scarico: utile perché durante una
    sessione di scansioni ripetute l'operatore spesso non guarda lo
    schermo. Solo Windows (unico target di distribuzione dell'app);
    fallisce silenziosamente altrove o se l'audio non è disponibile.
    """
    if not _SOUND_AVAILABLE:
        return
    try:
        if kind == "ok":
            winsound.Beep(1200, 90)
        else:
            winsound.Beep(400, 200)
    except Exception:
        pass


# ── Normalizzazione codici ──────────────────────────────────────────────────
# I lettori USB (tastiera emulata) spesso non riescono a "digitare"
# correttamente trattini tipografici come l'en dash "–" (spesso introdotto
# automaticamente dalla correzione automatica di Excel quando si scrive
# "TLC - 15"): il risultato è una lettura errata (es. "TLC !! 15" invece di
# "TLC – 15"), che non corrisponde più a nessun codice in anagrafica.
# Per evitare il problema, ogni codice viene normalizzato sostituendo questi
# caratteri con un trattino ASCII semplice "-", sia in fase di registrazione
# sia (con lo strumento "Correggi codici") sui codici già esistenti.
_DASH_LIKE_CHARS = "\u2010\u2011\u2012\u2013\u2014\u2015\u2212"
_DASH_TRANSLATION = str.maketrans({c: "-" for c in _DASH_LIKE_CHARS})


def normalize_code(codice: str) -> str:
    """Sostituisce i trattini tipografici in un codice con un trattino ASCII semplice."""
    if not codice:
        return codice
    return codice.translate(_DASH_TRANSLATION).strip()


# ══════════════════════════════════════════════════════════════════════════
# EquipmentManager — accesso al registro Excel
# ══════════════════════════════════════════════════════════════════════════

class EquipmentManager:
    """
    Accesso al registro Excel degli apparati radio e ai relativi movimenti
    di carico/scarico.

    Se il file indicato non esiste viene creato automaticamente con le
    sole intestazioni: può essere compilato a mano in Excel (aggiungendo
    righe con Codice/Modello/Numero_seriale) oppure tramite il pulsante
    "Registra nuovo apparato" del pannello TLC Point.
    """

    SHEET_APPARATI  = "Apparati"
    SHEET_MOVIMENTI = "Movimenti"

    APPARATI_HEADERS = ["Codice", "Modello", "Numero_seriale", "Note",
                        "Stato", "Assegnato_a", "Data_ultimo_movimento", "Alias",
                        "ODV", "Cellulare"]
    MOVIMENTI_HEADERS = ["Data_ora", "Codice", "Modello", "Operazione",
                         "Persona", "Operatore", "Alias", "ODV", "Cellulare"]

    STATO_DISPONIBILE = "Disponibile"
    STATO_IN_CARICO    = "In carico"

    def __init__(self, path: str):
        self._path = path
        self._wb: Workbook | None = None
        self.load()

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    @property
    def path(self) -> str:
        return self._path

    def load(self) -> None:
        """Carica il workbook da disco, creandolo se non esiste."""
        if not os.path.exists(self._path):
            self._create_empty()
        self._wb = load_workbook(self._path)
        self._ensure_sheets()

    def reload(self) -> None:
        """Ricarica il file da disco (utile se modificato esternamente)."""
        self.load()

    def normalize_all_codes(self) -> int:
        """
        Sostituisce i trattini tipografici (es. "–" introdotto da Excel) con
        trattini ASCII semplici in tutti i codici già presenti in anagrafica.
        Restituisce il numero di codici corretti.

        IMPORTANTE: dopo questa correzione, i QR/etichette già stampati con
        il vecchio codice non corrispondono più — vanno rigenerati e ristampati.
        """
        ws = self._wb[self.SHEET_APPARATI]
        fixed = 0
        for row in ws.iter_rows(min_row=2):
            cell = row[0]  # colonna Codice
            if cell.value is None:
                continue
            normalized = normalize_code(str(cell.value))
            if normalized != cell.value:
                cell.value = normalized
                fixed += 1
        if fixed:
            self._save()
        return fixed

    def all_apparati(self) -> list[dict]:
        """Restituisce tutte le righe del foglio Apparati come dizionari."""
        ws = self._wb[self.SHEET_APPARATI]
        rows = []
        for row in ws.iter_rows(min_row=2, values_only=True):
            if row[0] is None:
                continue
            rows.append(dict(zip(self.APPARATI_HEADERS, row)))
        return rows

    def recent_movements(self, limit: int = 80) -> list[dict]:
        """Restituisce gli ultimi movimenti (più recente per primo)."""
        return self.all_movements()[:limit]

    def all_movements(self) -> list[dict]:
        """Restituisce TUTTI i movimenti registrati (più recente per primo), senza limite — usato per il report completo."""
        ws = self._wb[self.SHEET_MOVIMENTI]
        rows = []
        for row in ws.iter_rows(min_row=2, values_only=True):
            if row[0] is None:
                continue
            rows.append(dict(zip(self.MOVIMENTI_HEADERS, row)))
        return list(reversed(rows))

    def find(self, codice: str) -> Optional[dict]:
        """
        Cerca un apparato per codice (case-insensitive). Oltre alla
        corrispondenza esatta, tenta anche il confronto normalizzato
        (trattini tipografici → trattino semplice), per tollerare eventuali
        codici in anagrafica non ancora corretti con "Correggi codici".
        """
        codice = (codice or "").strip()
        if not codice:
            return None
        codice_norm = normalize_code(codice).lower()
        for row in self.all_apparati():
            stored = str(row.get("Codice", "")).strip()
            if stored.lower() == codice.lower() or normalize_code(stored).lower() == codice_norm:
                return row
        return None

    def register_new(self, codice: str, modello: str,
                     numero_seriale: str = "", note: str = "") -> None:
        """Aggiunge un nuovo apparato al registro (stato Disponibile)."""
        codice = normalize_code(codice)
        if self.find(codice):
            raise ValueError(f"Codice '{codice}' già presente in anagrafica.")
        if not modello:
            raise ValueError("Il modello è obbligatorio.")
        ws = self._wb[self.SHEET_APPARATI]
        ws.append([codice, modello, numero_seriale, note,
                  self.STATO_DISPONIBILE, "", "", ""])
        self._save()

    def carico(self, codice: str, persona: str, operatore: str, alias: str = "",
              odv: str = "", cellulare: str = "") -> None:
        """Assegna un apparato disponibile a una persona (carico), con alias, ODV e cellulare opzionali."""
        if not persona:
            raise ValueError("Il nome della persona è obbligatorio.")
        row_idx = self._find_row_index(codice)
        if row_idx is None:
            raise ValueError(f"Codice '{codice}' non trovato in anagrafica.")

        ws = self._wb[self.SHEET_APPARATI]
        stato = ws.cell(row=row_idx, column=5).value or self.STATO_DISPONIBILE
        if stato == self.STATO_IN_CARICO:
            assegnato = ws.cell(row=row_idx, column=6).value
            raise ValueError(f"Apparato già in carico a '{assegnato}'.")

        now     = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        modello = ws.cell(row=row_idx, column=2).value
        ws.cell(row=row_idx, column=5, value=self.STATO_IN_CARICO)
        ws.cell(row=row_idx, column=6, value=persona)
        ws.cell(row=row_idx, column=7, value=now)
        ws.cell(row=row_idx, column=8, value=alias or "")
        ws.cell(row=row_idx, column=9, value=odv or "")
        ws.cell(row=row_idx, column=10, value=cellulare or "")

        self._append_movimento(now, codice, modello, "Carico", persona, operatore, alias, odv, cellulare)
        self._save()

    def scarico(self, codice: str, operatore: str) -> None:
        """Restituisce un apparato in carico, rendendolo di nuovo disponibile."""
        row_idx = self._find_row_index(codice)
        if row_idx is None:
            raise ValueError(f"Codice '{codice}' non trovato in anagrafica.")

        ws = self._wb[self.SHEET_APPARATI]
        stato = ws.cell(row=row_idx, column=5).value or self.STATO_DISPONIBILE
        if stato != self.STATO_IN_CARICO:
            raise ValueError("Apparato già disponibile (non risulta in carico).")

        now       = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        modello   = ws.cell(row=row_idx, column=2).value
        persona   = ws.cell(row=row_idx, column=6).value
        alias     = ws.cell(row=row_idx, column=8).value
        odv       = ws.cell(row=row_idx, column=9).value
        cellulare = ws.cell(row=row_idx, column=10).value
        ws.cell(row=row_idx, column=5, value=self.STATO_DISPONIBILE)
        ws.cell(row=row_idx, column=6, value="")
        ws.cell(row=row_idx, column=7, value=now)
        ws.cell(row=row_idx, column=8, value="")
        ws.cell(row=row_idx, column=9, value="")
        ws.cell(row=row_idx, column=10, value="")

        self._append_movimento(now, codice, modello, "Scarico", persona, operatore, alias, odv, cellulare)
        self._save()

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    def _find_row_index(self, codice: str) -> Optional[int]:
        codice = (codice or "").strip().lower()
        codice_norm = normalize_code(codice)
        ws = self._wb[self.SHEET_APPARATI]
        for i, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
            if row[0] is None:
                continue
            stored = str(row[0]).strip().lower()
            if stored == codice or normalize_code(stored) == codice_norm:
                return i
        return None

    def _append_movimento(self, data_ora, codice, modello, operazione, persona, operatore,
                          alias="", odv="", cellulare="") -> None:
        ws = self._wb[self.SHEET_MOVIMENTI]
        ws.append([data_ora, codice, modello, operazione, persona or "", operatore or "",
                  alias or "", odv or "", cellulare or ""])

    def _ensure_sheets(self) -> None:
        if self.SHEET_APPARATI not in self._wb.sheetnames:
            ws = self._wb.create_sheet(self.SHEET_APPARATI)
            ws.append(self.APPARATI_HEADERS)
        else:
            self._migrate_headers(self._wb[self.SHEET_APPARATI], self.APPARATI_HEADERS)
        if self.SHEET_MOVIMENTI not in self._wb.sheetnames:
            ws = self._wb.create_sheet(self.SHEET_MOVIMENTI)
            ws.append(self.MOVIMENTI_HEADERS)
        else:
            self._migrate_headers(self._wb[self.SHEET_MOVIMENTI], self.MOVIMENTI_HEADERS)
        # Rimuove l'eventuale foglio di default vuoto creato da Excel/openpyxl
        if "Sheet" in self._wb.sheetnames and len(self._wb.sheetnames) > 2:
            default = self._wb["Sheet"]
            if default.max_row == 1 and default.max_column == 1 and default["A1"].value is None:
                self._wb.remove(default)

    @staticmethod
    def _migrate_headers(ws, expected_headers: list) -> None:
        """
        Aggiunge in coda eventuali colonne nuove rispetto ai file creati con
        versioni precedenti dell'app (es. la colonna "Alias" introdotta
        successivamente), senza toccare le colonne/dati già esistenti —
        mantiene compatibilità con i database Excel già in uso.
        """
        current_len = ws.max_column if ws.max_row >= 1 else 0
        for i, header in enumerate(expected_headers, start=1):
            if i > current_len:
                ws.cell(row=1, column=i, value=header)

    def _create_empty(self) -> None:
        wb = Workbook()
        wb.remove(wb.active)
        ws1 = wb.create_sheet(self.SHEET_APPARATI)
        ws1.append(self.APPARATI_HEADERS)
        ws2 = wb.create_sheet(self.SHEET_MOVIMENTI)
        ws2.append(self.MOVIMENTI_HEADERS)
        parent_dir = os.path.dirname(os.path.abspath(self._path))
        os.makedirs(parent_dir, exist_ok=True)
        wb.save(self._path)
        print(f"Database apparati creato: {self._path}")

    def _save(self) -> None:
        self._wb.save(self._path)


# ══════════════════════════════════════════════════════════════════════════
# TLCPointPanel — interfaccia Tkinter (da inserire come scheda/tab)
# ══════════════════════════════════════════════════════════════════════════

class TLCPointPanel(tk.Frame):
    """
    Pannello TLC Point: scansione/inserimento codice, scheda apparato con
    azioni di carico/scarico, elenco apparati filtrabile e storico movimenti.

    Utilizzo::

        panel = TLCPointPanel(parent, db_path="apparati.xlsx",
                              get_operator=lambda: entry_operatore.get())
        panel.pack(fill="both", expand=True)
    """

    _TRANSLATIONS = {
        "it": {
            "scan_label"      : "Scansiona o digita il codice apparato e premi Invio:",
            "scan_placeholder": "Codice apparato...",
            "not_found"       : "Codice non censito in anagrafica.",
            "register_new"    : "Registra nuovo apparato",
            "model"           : "Modello:",
            "serial"          : "Numero seriale:",
            "notes"           : "Note:",
            "register_btn"    : "Registra",
            "code_label"      : "Codice:",
            "model_label"     : "Modello:",
            "serial_label"    : "Seriale:",
            "status_label"    : "Stato:",
            "assigned_label"  : "Assegnato a:",
            "last_move_label" : "Ultimo movimento:",
            "person_label"    : "Persona:",
            "alias_label"     : "Alias (nominativo missione):",
            "odv_label"       : "ODV:",
            "cellulare_label" : "Cellulare:",
            "load_btn"        : "Carica (assegna)",
            "unload_btn"      : "Scarica (restituisci)",
            "status_available": "Disponibile",
            "status_loaded"   : "In carico",
            "search_placeholder": "Cerca per codice, modello o persona...",
            "col_code"        : "Codice",
            "col_model"       : "Modello",
            "col_status"      : "Stato",
            "col_assigned"    : "Assegnato a",
            "col_alias"       : "Alias",
            "col_odv"         : "ODV",
            "col_cellulare"   : "Cellulare",
            "list_header"     : "Elenco apparati",
            "use_selected"    : "Usa selezionato",
            "history_header"  : "Storico movimenti",
            "col_datetime"    : "Data/Ora",
            "col_operation"   : "Operazione",
            "col_person"      : "Persona",
            "col_operator"    : "Operatore",
            "reload_btn"      : "Ricarica database",
            "db_path_label"   : "Database:",
            "error_title"     : "Errore",
            "warning_title"   : "Avviso",
            "success_title"   : "Fatto",
            "load_success"    : "Apparato '{}' assegnato a {}.",
            "unload_success"  : "Apparato '{}' restituito.",
            "register_success": "Apparato '{}' registrato in anagrafica.",
            "empty_code"      : "Inserisci o scansiona un codice.",
            "person_required" : "Il nome della persona è obbligatorio.",
            "model_required"  : "Il modello è obbligatorio.",
            "load_error_title": "Impossibile caricare il database apparati",
            "reload_success"  : "Database apparati ricaricato ({} apparati).",
            "gen_qr_btn"        : "Genera QR",
            "gen_qr_sheet_btn"  : "Foglio QR stampabile",
            "assignments_report_btn": "Report assegnazioni",
            "qr_saved"          : "QR code salvato in:\n{}",
            "qr_sheet_saved"    : "Foglio QR generato in:\n{}",
            "assignments_saved" : "Report assegnazioni generato in:\n{}\ne\n{}",
            "no_assignments"    : "Nessun apparato attualmente in carico: report non generato.",
            "no_apparati_for_qr": "Nessun apparato nell'elenco per cui generare i QR.",
            "qr_unavailable"    : "Generazione QR non disponibile: libreria 'qrcode' non installata.",
            "save_qr_dialog"    : "Salva QR code come",
            "normalize_btn"     : "Correggi codici",
            "normalize_result"  : "{} codice/i corretto/i (trattini speciali sostituiti con '-').\n\n"
                                  "Attenzione: i QR/etichette già stampati per questi apparati non "
                                  "corrispondono più al nuovo codice — vanno rigenerati e ristampati.",
            "normalize_none"    : "Nessun codice da correggere: sono già tutti in formato standard.",
            "tlc_log_report_btn": "Report log TLC Point",
            "no_movements"      : "Nessun movimento registrato: report non generato.",
            "tlc_log_saved"     : "Report log TLC Point generato in:\n{}\ne\n{}",
        },
        "en": {
            "scan_label"      : "Scan or type the equipment code and press Enter:",
            "scan_placeholder": "Equipment code...",
            "not_found"       : "Code not found in registry.",
            "register_new"    : "Register new equipment",
            "model"           : "Model:",
            "serial"          : "Serial number:",
            "notes"           : "Notes:",
            "register_btn"    : "Register",
            "code_label"      : "Code:",
            "model_label"     : "Model:",
            "serial_label"    : "Serial:",
            "status_label"    : "Status:",
            "assigned_label"  : "Assigned to:",
            "last_move_label" : "Last movement:",
            "person_label"    : "Person:",
            "alias_label"     : "Alias (mission callsign):",
            "odv_label"       : "Volunteer org (ODV):",
            "cellulare_label" : "Mobile phone:",
            "load_btn"        : "Check out (assign)",
            "unload_btn"      : "Check in (return)",
            "status_available": "Available",
            "status_loaded"   : "Checked out",
            "search_placeholder": "Search by code, model or person...",
            "col_code"        : "Code",
            "col_model"       : "Model",
            "col_status"      : "Status",
            "col_assigned"    : "Assigned to",
            "col_alias"       : "Alias",
            "col_odv"         : "Volunteer org (ODV)",
            "col_cellulare"   : "Mobile phone",
            "list_header"     : "Equipment list",
            "use_selected"    : "Use selected",
            "history_header"  : "Movement history",
            "col_datetime"    : "Date/Time",
            "col_operation"   : "Operation",
            "col_person"      : "Person",
            "col_operator"    : "Operator",
            "reload_btn"      : "Reload database",
            "db_path_label"   : "Database:",
            "error_title"     : "Error",
            "warning_title"   : "Warning",
            "success_title"   : "Done",
            "load_success"    : "Equipment '{}' assigned to {}.",
            "unload_success"  : "Equipment '{}' returned.",
            "register_success": "Equipment '{}' registered in the registry.",
            "empty_code"      : "Enter or scan a code.",
            "person_required" : "The person's name is required.",
            "model_required"  : "The model is required.",
            "load_error_title": "Could not load the equipment database",
            "reload_success"  : "Equipment database reloaded ({} items).",
            "gen_qr_btn"        : "Generate QR",
            "gen_qr_sheet_btn"  : "Printable QR sheet",
            "assignments_report_btn": "Assignments report",
            "qr_saved"          : "QR code saved to:\n{}",
            "qr_sheet_saved"    : "QR sheet generated at:\n{}",
            "assignments_saved" : "Assignments report generated at:\n{}\nand\n{}",
            "no_assignments"    : "No equipment currently checked out: report not generated.",
            "no_apparati_for_qr": "No equipment in the list to generate QR codes for.",
            "qr_unavailable"    : "QR generation unavailable: 'qrcode' library not installed.",
            "save_qr_dialog"    : "Save QR code as",
            "normalize_btn"     : "Fix codes",
            "normalize_result"  : "{} code(s) fixed (special dashes replaced with '-').\n\n"
                                  "Note: QR codes/labels already printed for these items no longer "
                                  "match — they need to be regenerated and reprinted.",
            "normalize_none"    : "No codes to fix: all already in standard format.",
            "tlc_log_report_btn": "TLC Point log report",
            "no_movements"      : "No movements recorded: report not generated.",
            "tlc_log_saved"     : "TLC Point log report generated at:\n{}\nand\n{}",
        },
    }

    def __init__(self, parent: tk.Widget, db_path: str,
                get_operator: Callable[[], str], lang: str = "it",
                directory: str = ".", logo_path: str = "",
                push_assignments: Optional[Callable[[list], None]] = None,
                on_aliases_changed: Optional[Callable[[list], None]] = None):
        super().__init__(parent)
        self._db_path         = db_path
        self._get_operator    = get_operator
        self._lang            = lang
        self._directory       = directory
        self._logo_path       = logo_path
        self._push_assignments = push_assignments
        self._on_aliases_changed = on_aliases_changed
        self._reporter         = ReportCreator()
        self._current_code: Optional[str] = None
        self._manager: Optional[EquipmentManager] = None

        try:
            self._manager = EquipmentManager(db_path)
        except Exception as e:
            self._manager = None
            self._load_error = str(e)

        self._build_ui()
        if self._manager:
            self._refresh_all()
        else:
            messagebox.showerror(
                self._t()["load_error_title"],
                f"{self._db_path}\n\n{getattr(self, '_load_error', '')}"
            )

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def set_language(self, lang: str) -> None:
        """Aggiorna tutte le etichette del pannello nella lingua indicata."""
        self._lang = lang
        t = self._t()
        self._lbl_scan.config(text=t["scan_label"])
        self._btn_gen_qr.config(text=t["gen_qr_btn"])
        self._btn_gen_qr_sheet.config(text=t["gen_qr_sheet_btn"])
        self._btn_assignments_report.config(text=t["assignments_report_btn"])
        self._btn_normalize.config(text=t["normalize_btn"])
        self._btn_reload.config(text=t["reload_btn"])
        self._lbl_db_path.config(text=f"{t['db_path_label']} {self._db_path}")
        self._lbl_list_header.config(text=t["list_header"])
        self._lbl_history_header.config(text=t["history_header"])
        self._btn_tlc_log_report.config(text=t["tlc_log_report_btn"])
        self._btn_use_selected.config(text=t["use_selected"])
        self._tree_apparati.heading("codice", text=t["col_code"])
        self._tree_apparati.heading("modello", text=t["col_model"])
        self._tree_apparati.heading("stato", text=t["col_status"])
        self._tree_apparati.heading("assegnato", text=t["col_assigned"])
        self._tree_apparati.heading("alias", text=t["col_alias"])
        self._tree_apparati.heading("odv", text=t["col_odv"])
        self._tree_apparati.heading("cellulare", text=t["col_cellulare"])
        self._tree_movimenti.heading("data", text=t["col_datetime"])
        self._tree_movimenti.heading("codice", text=t["col_code"])
        self._tree_movimenti.heading("modello", text=t["col_model"])
        self._tree_movimenti.heading("operazione", text=t["col_operation"])
        self._tree_movimenti.heading("persona", text=t["col_person"])
        self._tree_movimenti.heading("alias", text=t["col_alias"])
        self._tree_movimenti.heading("odv", text=t["col_odv"])
        self._tree_movimenti.heading("cellulare", text=t["col_cellulare"])
        self._tree_movimenti.heading("operatore", text=t["col_operator"])
        self._clear_scheda()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        t = self._t()

        # ── Barra di scansione ──────────────────────────────────────
        scan_frame = tk.Frame(self)
        scan_frame.pack(fill="x", padx=10, pady=(10, 5))

        self._lbl_scan = tk.Label(scan_frame, text=t["scan_label"], font=("Helvetica", 11, "bold"))
        self._lbl_scan.pack(anchor="w")

        self._entry_code = ttk.Entry(scan_frame, font=("Courier", 16, "bold"))
        self._entry_code.pack(side="left", fill="x", expand=True, pady=5, ipady=6)
        self._entry_code.bind("<Return>", self._on_scan)
        self._entry_code.focus_set()

        self._btn_gen_qr = tk.Button(scan_frame, text=t["gen_qr_btn"], command=self._generate_single_qr)
        self._btn_gen_qr.pack(side="left", padx=(8, 0), pady=5)

        # ── Scheda apparato + storico affiancati ───────────────────
        mid = tk.Frame(self)
        mid.pack(fill="both", expand=True, padx=10, pady=5)
        mid.columnconfigure(0, weight=1)
        mid.columnconfigure(1, weight=1)
        mid.rowconfigure(0, weight=1)

        self._build_scheda(mid)
        self._build_apparati_list(mid)

        self._build_movimenti(self)

        # ── Barra inferiore: percorso database + ricarica ──────────
        bottom = tk.Frame(self)
        bottom.pack(fill="x", padx=10, pady=(0, 10))
        self._lbl_db_path = tk.Label(
            bottom, text=f"{t['db_path_label']} {self._db_path}",
            font=("Helvetica", 8), fg="#555555"
        )
        self._lbl_db_path.pack(side="left")
        self._btn_normalize = tk.Button(bottom, text=t["normalize_btn"], command=self._do_normalize_codes)
        self._btn_normalize.pack(side="right", padx=(8, 0))
        self._btn_assignments_report = tk.Button(
            bottom, text=t["assignments_report_btn"], command=self._generate_assignments_report
        )
        self._btn_assignments_report.pack(side="right", padx=(8, 0))
        self._btn_reload = tk.Button(bottom, text=t["reload_btn"], command=self._on_reload)
        self._btn_reload.pack(side="right")

    def _build_scheda(self, parent: tk.Widget) -> None:
        """Scheda apparato: dettagli + azioni di carico/scarico/registrazione."""
        t = self._t()
        frame = tk.Frame(parent, bd=1, relief="groove")
        frame.grid(row=0, column=0, sticky="nsew", padx=(0, 5))
        self._scheda_frame = frame

        self._scheda_info = tk.Label(
            frame, text="", justify="left", anchor="w",
            font=("Courier", 10), padx=10, pady=10
        )
        self._scheda_info.pack(fill="x")

        # -- Sotto-frame per azione "Carico" (persona + pulsante) --
        self._frame_carico = tk.Frame(frame)
        tk.Label(self._frame_carico, text=t["person_label"]).grid(row=0, column=0, padx=5, pady=5, sticky="e")
        self._entry_persona = ttk.Entry(self._frame_carico)
        self._entry_persona.grid(row=0, column=1, padx=5, pady=5, sticky="ew")
        tk.Label(self._frame_carico, text=t["alias_label"]).grid(row=1, column=0, padx=5, pady=5, sticky="e")
        self._entry_alias = ttk.Entry(self._frame_carico)
        self._entry_alias.grid(row=1, column=1, padx=5, pady=5, sticky="ew")
        tk.Label(self._frame_carico, text=t["odv_label"]).grid(row=2, column=0, padx=5, pady=5, sticky="e")
        self._entry_odv = ttk.Entry(self._frame_carico)
        self._entry_odv.grid(row=2, column=1, padx=5, pady=5, sticky="ew")
        tk.Label(self._frame_carico, text=t["cellulare_label"]).grid(row=3, column=0, padx=5, pady=5, sticky="e")
        self._entry_cellulare = ttk.Entry(self._frame_carico)
        self._entry_cellulare.grid(row=3, column=1, padx=5, pady=5, sticky="ew")
        self._frame_carico.columnconfigure(1, weight=1)
        self._btn_carico = tk.Button(self._frame_carico, text=t["load_btn"], command=self._do_carico)
        self._btn_carico.grid(row=4, column=0, columnspan=2, pady=(0, 10))

        # -- Sotto-frame per azione "Scarico" --
        self._frame_scarico = tk.Frame(frame)
        self._btn_scarico = tk.Button(self._frame_scarico, text=t["unload_btn"], command=self._do_scarico)
        self._btn_scarico.pack(pady=10)

        # -- Sotto-frame "codice non censito" → registrazione --
        self._frame_register = tk.Frame(frame)
        tk.Label(self._frame_register, text=t["not_found"], fg="#b03030",
                font=("Helvetica", 9, "bold")).grid(row=0, column=0, columnspan=2, padx=5, pady=(5, 8))
        tk.Label(self._frame_register, text=t["model"]).grid(row=1, column=0, padx=5, pady=3, sticky="e")
        self._entry_new_modello = ttk.Entry(self._frame_register)
        self._entry_new_modello.grid(row=1, column=1, padx=5, pady=3, sticky="ew")
        tk.Label(self._frame_register, text=t["serial"]).grid(row=2, column=0, padx=5, pady=3, sticky="e")
        self._entry_new_seriale = ttk.Entry(self._frame_register)
        self._entry_new_seriale.grid(row=2, column=1, padx=5, pady=3, sticky="ew")
        tk.Label(self._frame_register, text=t["notes"]).grid(row=3, column=0, padx=5, pady=3, sticky="e")
        self._entry_new_note = ttk.Entry(self._frame_register)
        self._entry_new_note.grid(row=3, column=1, padx=5, pady=3, sticky="ew")
        self._frame_register.columnconfigure(1, weight=1)
        self._btn_register = tk.Button(self._frame_register, text=t["register_btn"], command=self._do_register)
        self._btn_register.grid(row=4, column=0, columnspan=2, pady=10)

    def _build_apparati_list(self, parent: tk.Widget) -> None:
        """Elenco filtrabile di tutti gli apparati censiti (alternativa manuale allo scanner)."""
        t = self._t()
        frame = tk.Frame(parent, bd=1, relief="groove")
        frame.grid(row=0, column=1, sticky="nsew", padx=(5, 0))
        frame.rowconfigure(2, weight=1)
        frame.columnconfigure(0, weight=1)

        self._lbl_list_header = tk.Label(frame, text=t["list_header"], font=("Helvetica", 11, "bold"))
        self._lbl_list_header.grid(row=0, column=0, sticky="w", padx=8, pady=(8, 2))

        self._entry_search = ttk.Entry(frame)
        self._entry_search.grid(row=1, column=0, sticky="ew", padx=8, pady=(0, 5))
        self._entry_search.bind("<KeyRelease>", lambda e: self._refresh_apparati_list())

        columns = ("codice", "modello", "stato", "assegnato", "alias", "odv", "cellulare")
        tree = ttk.Treeview(frame, columns=columns, show="headings", height=8)
        for col, key in zip(columns, ("col_code", "col_model", "col_status", "col_assigned",
                                      "col_alias", "col_odv", "col_cellulare")):
            tree.heading(col, text=t[key])
        tree.column("codice", width=100)
        tree.column("modello", width=120)
        tree.column("stato", width=90)
        tree.column("assegnato", width=100)
        tree.column("alias", width=90)
        tree.column("odv", width=90)
        tree.column("cellulare", width=100)
        tree.grid(row=2, column=0, sticky="nsew", padx=(8, 0), pady=(0, 5))
        tree.bind("<Double-1>", lambda e: self._use_selected())
        add_vscrollbar(frame, tree)
        self._tree_apparati = tree
        self._notes_by_code: dict[str, str] = {}
        self._codice_by_item: dict[str, str] = {}
        Tooltip(tree, self._apparati_row_tooltip_text)

        btns_frame = tk.Frame(frame)
        btns_frame.grid(row=3, column=0, pady=(0, 8))
        self._btn_use_selected = tk.Button(btns_frame, text=t["use_selected"], command=self._use_selected)
        self._btn_use_selected.pack(side="left", padx=4)
        self._btn_gen_qr_sheet = tk.Button(btns_frame, text=t["gen_qr_sheet_btn"], command=self._generate_qr_sheet)
        self._btn_gen_qr_sheet.pack(side="left", padx=4)

    def _build_movimenti(self, parent: tk.Widget) -> None:
        """Storico movimenti (ultimi N, più recenti in alto)."""
        t = self._t()
        frame = tk.Frame(parent, bd=1, relief="groove")
        frame.pack(fill="both", expand=False, padx=10, pady=(5, 5))

        header_frame = tk.Frame(frame)
        header_frame.pack(fill="x", padx=8, pady=(8, 2))
        self._lbl_history_header = tk.Label(header_frame, text=t["history_header"], font=("Helvetica", 11, "bold"))
        self._lbl_history_header.pack(side="left")
        self._btn_tlc_log_report = tk.Button(header_frame, text=t["tlc_log_report_btn"], command=self._generate_tlc_log_report)
        self._btn_tlc_log_report.pack(side="right")

        columns = ("data", "codice", "modello", "operazione", "persona", "alias",
                  "odv", "cellulare", "operatore")
        tree = ttk.Treeview(frame, columns=columns, show="headings", height=6)
        headers_map = {
            "data": "col_datetime", "codice": "col_code", "modello": "col_model",
            "operazione": "col_operation", "persona": "col_person", "alias": "col_alias",
            "odv": "col_odv", "cellulare": "col_cellulare", "operatore": "col_operator",
        }
        for col, key in headers_map.items():
            tree.heading(col, text=t[key])
        tree.column("data", width=140)
        tree.column("codice", width=90)
        tree.column("modello", width=110)
        tree.column("operazione", width=80)
        tree.column("persona", width=100)
        tree.column("alias", width=90)
        tree.column("odv", width=90)
        tree.column("cellulare", width=100)
        tree.column("operatore", width=100)

        tree_wrap = tk.Frame(frame)
        tree_wrap.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        tree.pack(in_=tree_wrap, side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(tree_wrap, orient="vertical", command=tree.yview)
        sb.pack(side="right", fill="y")
        tree.configure(yscrollcommand=sb.set)
        self._tree_movimenti = tree

    # ------------------------------------------------------------------
    # Scan / lookup
    # ------------------------------------------------------------------

    def _on_scan(self, event=None) -> None:
        if not self._manager:
            return
        codice = self._entry_code.get().strip()
        if not codice:
            return
        self._show_apparato(codice)
        # Conferma sonora dello scan: chi usa il lettore USB spesso non
        # guarda lo schermo, il suono dice subito se il codice è censito.
        _beep("ok" if self._manager.find(codice) else "error")

    def _use_selected(self) -> None:
        sel = self._tree_apparati.selection()
        if not sel:
            return
        # Non si usa tree.item(sel[0])["values"][0]: Tk/Tcl converte in intero
        # i valori che "sembrano" numeri, perdendo gli zeri iniziali (es. "053"
        # diventerebbe 53). Si usa invece la mappa item->codice popolata in
        # fase di inserimento, che conserva il codice come stringa esatta.
        codice = self._codice_by_item.get(sel[0], self._tree_apparati.item(sel[0])["values"][0])
        self._entry_code.delete(0, tk.END)
        self._entry_code.insert(0, codice)
        self._show_apparato(str(codice))

    def _show_apparato(self, codice: str) -> None:
        t = self._t()
        self._current_code = codice
        row = self._manager.find(codice) if self._manager else None

        # Nasconde tutti i sotto-frame di azione, poi mostra solo quello utile
        for f in (self._frame_carico, self._frame_scarico, self._frame_register):
            f.pack_forget()

        if row is None:
            self._scheda_info.config(
                text=f"{t['code_label']} {codice}\n\n{t['not_found']}"
            )
            self._entry_new_modello.delete(0, tk.END)
            self._entry_new_seriale.delete(0, tk.END)
            self._entry_new_note.delete(0, tk.END)
            self._frame_register.pack(fill="x")
            return

        stato     = row.get("Stato") or self._manager.STATO_DISPONIBILE
        assegnato = row.get("Assegnato_a") or "—"
        alias     = row.get("Alias") or ""
        odv       = row.get("ODV") or ""
        cellulare = row.get("Cellulare") or ""
        ultimo    = row.get("Data_ultimo_movimento") or "—"

        assegnato_riga = f"{assegnato} ({alias})" if (assegnato != "—" and alias) else assegnato

        info = (
            f"{t['code_label']} {row.get('Codice')}\n"
            f"{t['model_label']} {row.get('Modello')}\n"
            f"{t['serial_label']} {row.get('Numero_seriale') or '—'}\n"
            f"{t['status_label']} {stato}\n"
            f"{t['assigned_label']} {assegnato_riga}\n"
            f"{t['last_move_label']} {ultimo}"
        )
        if stato == self._manager.STATO_IN_CARICO and (odv or cellulare):
            info += f"\n{t['odv_label']} {odv or '—'}\n{t['cellulare_label']} {cellulare or '—'}"
        self._scheda_info.config(text=info)

        if stato == self._manager.STATO_IN_CARICO:
            self._frame_scarico.pack(fill="x")
        else:
            self._entry_persona.delete(0, tk.END)
            self._entry_alias.delete(0, tk.END)
            self._entry_odv.delete(0, tk.END)
            self._entry_cellulare.delete(0, tk.END)
            self._frame_carico.pack(fill="x")

    def _clear_scheda(self) -> None:
        self._current_code = None
        self._scheda_info.config(text="")
        for f in (self._frame_carico, self._frame_scarico, self._frame_register):
            f.pack_forget()

    # ------------------------------------------------------------------
    # Azioni
    # ------------------------------------------------------------------

    def _do_carico(self) -> None:
        t = self._t()
        persona   = self._entry_persona.get().strip()
        alias     = self._entry_alias.get().strip()
        odv       = self._entry_odv.get().strip()
        cellulare = self._entry_cellulare.get().strip()
        if not persona:
            messagebox.showerror(t["error_title"], t["person_required"])
            return
        try:
            self._manager.carico(self._current_code, persona, self._get_operator() or "Operatore",
                                 alias, odv, cellulare)
            _beep("ok")
            show_banner(self.winfo_toplevel(), t["load_success"].format(self._current_code, persona))
            self._after_action()
        except ValueError as e:
            _beep("error")
            messagebox.showerror(t["error_title"], str(e))

    def _do_scarico(self) -> None:
        t = self._t()
        try:
            self._manager.scarico(self._current_code, self._get_operator() or "Operatore")
            _beep("ok")
            show_banner(self.winfo_toplevel(), t["unload_success"].format(self._current_code))
            self._after_action()
        except ValueError as e:
            _beep("error")
            messagebox.showerror(t["error_title"], str(e))

    def _do_register(self) -> None:
        t = self._t()
        modello = self._entry_new_modello.get().strip()
        if not modello:
            messagebox.showerror(t["error_title"], t["model_required"])
            return
        seriale = self._entry_new_seriale.get().strip()
        note    = self._entry_new_note.get().strip()
        try:
            self._manager.register_new(self._current_code, modello, seriale, note)
            _beep("ok")
            show_banner(self.winfo_toplevel(), t["register_success"].format(self._current_code))
            self._refresh_all()
            self._show_apparato(self._current_code)
        except ValueError as e:
            _beep("error")
            messagebox.showerror(t["error_title"], str(e))

    def _after_action(self) -> None:
        """Ripulisce i campi e ricarica le viste dopo un'azione riuscita."""
        self._entry_code.delete(0, tk.END)
        self._clear_scheda()
        self._refresh_all()
        self._entry_code.focus_set()

    def _on_reload(self) -> None:
        t = self._t()
        if not self._manager:
            try:
                self._manager = EquipmentManager(self._db_path)
            except Exception as e:
                messagebox.showerror(t["load_error_title"], str(e))
                return
        else:
            self._manager.reload()
        self._refresh_all()
        messagebox.showinfo(t["success_title"], t["reload_success"].format(len(self._manager.all_apparati())))

    def _do_normalize_codes(self) -> None:
        """
        Corregge i codici già presenti in anagrafica sostituendo trattini
        tipografici (es. "–" introdotto da Excel) con un trattino ASCII
        semplice: risolve i casi in cui il lettore USB legge male il QR
        (es. "TLC !! 15" invece di "TLC – 15") perché non riesce a
        "digitare" correttamente quel carattere speciale.
        """
        t = self._t()
        if not self._manager:
            return
        fixed = self._manager.normalize_all_codes()
        self._refresh_all()
        if fixed:
            messagebox.showinfo(t["success_title"], t["normalize_result"].format(fixed))
        else:
            messagebox.showinfo(t["success_title"], t["normalize_none"])

    # ------------------------------------------------------------------
    # QR code
    # ------------------------------------------------------------------

    def _generate_single_qr(self) -> None:
        """Genera il QR code del codice attualmente nel campo di scansione e lo salva su file."""
        t = self._t()
        if not _QRCODE_AVAILABLE:
            messagebox.showerror(t["error_title"], t["qr_unavailable"])
            return
        codice = self._entry_code.get().strip()
        if not codice:
            messagebox.showerror(t["error_title"], t["empty_code"])
            return

        qr_dir = os.path.join(ReportCreator.local_backup_dir(), "..", "qr_codes")
        qr_dir = os.path.normpath(qr_dir)
        os.makedirs(qr_dir, exist_ok=True)
        default_name = f"qr_{ReportCreator.sanitize_filename(codice)}.png"

        path = filedialog.asksaveasfilename(
            title=t["save_qr_dialog"],
            initialdir=qr_dir,
            initialfile=default_name,
            defaultextension=".png",
            filetypes=[("PNG", "*.png")],
        )
        if not path:
            return

        img = qrcode.make(codice)
        img = img.get_image() if hasattr(img, "get_image") else img
        img.save(path)
        messagebox.showinfo(t["success_title"], t["qr_saved"].format(path))

    def _generate_qr_sheet(self) -> None:
        """Genera un foglio PDF stampabile con i QR code degli apparati attualmente in elenco (rispetta il filtro)."""
        t = self._t()
        if not self._manager:
            return
        entries = self._filtered_apparati()
        if not entries:
            messagebox.showwarning(t["warning_title"], t["no_apparati_for_qr"])
            return
        try:
            path = self._reporter.create_qr_sheet_pdf(entries, self._directory)
            messagebox.showinfo(t["success_title"], t["qr_sheet_saved"].format(path))
        except RuntimeError as e:
            messagebox.showerror(t["error_title"], str(e))
        except Exception as e:
            messagebox.showerror(t["error_title"], str(e))

    # ------------------------------------------------------------------
    # Report assegnazioni
    # ------------------------------------------------------------------

    def _generate_assignments_report(self) -> None:
        """Genera il report PDF+XLSX delle assegnazioni correnti (fotografia di chi ha cosa adesso)."""
        t = self._t()
        if not self._manager:
            return

        rows = [
            (
                row.get("Codice", ""),
                row.get("Modello") or "",
                row.get("Numero_seriale") or "",
                row.get("Assegnato_a") or "",
                row.get("Alias") or "",
                row.get("ODV") or "",
                row.get("Cellulare") or "",
                row.get("Data_ultimo_movimento") or "",
            )
            for row in self._manager.all_apparati()
            if (row.get("Stato") or self._manager.STATO_DISPONIBILE) == self._manager.STATO_IN_CARICO
        ]
        if not rows:
            messagebox.showinfo(t["warning_title"], t["no_assignments"])
            return

        operatore = self._get_operator() or "Operatore"
        now       = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        n_pdf  = self._reporter.count_files(self._directory, ".pdf", prefix="rapporto_assegnazioni_")
        n_xlsx = self._reporter.count_files(self._directory, ".xlsx", prefix="rapporto_assegnazioni_")

        try:
            pdf_path  = self._reporter.create_assignments_pdf(
                operatore, now, rows, self._directory, n_pdf, self._logo_path
            )
            xlsx_path = self._reporter.create_assignments_xlsx(
                operatore, now, rows, self._directory, n_xlsx, self._logo_path
            )
            messagebox.showinfo(t["success_title"], t["assignments_saved"].format(pdf_path, xlsx_path))
        except Exception as e:
            messagebox.showerror(t["error_title"], str(e))

    def _generate_tlc_log_report(self) -> None:
        """Genera il report PDF+XLSX con l'intero storico movimenti TLC Point (carichi/scarichi)."""
        t = self._t()
        if not self._manager:
            return

        rows = [
            (
                m.get("Data_ora", ""),
                m.get("Codice", ""),
                m.get("Modello") or "",
                m.get("Operazione", ""),
                m.get("Persona") or "",
                m.get("Alias") or "",
                m.get("ODV") or "",
                m.get("Cellulare") or "",
                m.get("Operatore") or "",
            )
            for m in self._manager.all_movements()
        ]
        if not rows:
            messagebox.showinfo(t["warning_title"], t["no_movements"])
            return

        operatore = self._get_operator() or "Operatore"
        now       = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        n_pdf  = self._reporter.count_files(self._directory, ".pdf", prefix="rapporto_tlc_point_")
        n_xlsx = self._reporter.count_files(self._directory, ".xlsx", prefix="rapporto_tlc_point_")

        try:
            pdf_path  = self._reporter.create_tlc_log_pdf(
                operatore, now, rows, self._directory, n_pdf, self._logo_path
            )
            xlsx_path = self._reporter.create_tlc_log_xlsx(
                operatore, now, rows, self._directory, n_xlsx, self._logo_path
            )
            messagebox.showinfo(t["success_title"], t["tlc_log_saved"].format(pdf_path, xlsx_path))
        except Exception as e:
            messagebox.showerror(t["error_title"], str(e))

    # ------------------------------------------------------------------
    # Refresh viste
    # ------------------------------------------------------------------

    def _refresh_all(self) -> None:
        self._refresh_apparati_list()
        self._refresh_movimenti()
        self._notify_assignments()
        self._notify_aliases()

    def get_known_aliases(self) -> list[str]:
        """
        Restituisce gli alias (nominativi missione) attualmente in uso, cioè
        quelli di apparati al momento in carico — usati per suggerirli nel
        registro comunicazioni.

        Volutamente NON include lo storico movimenti: un alias resta
        suggerito solo finché l'apparato a cui è associato è in carico. Non
        appena viene scaricato, il nominativo va "dimenticato" dai
        suggerimenti (scarico() svuota già il campo Alias in anagrafica).
        """
        if not self._manager:
            return []
        aliases = {
            str(row["Alias"])
            for row in self._manager.all_apparati()
            if row.get("Alias")
        }
        return sorted(aliases)

    def _notify_aliases(self) -> None:
        if self._on_aliases_changed:
            self._on_aliases_changed(self.get_known_aliases())

    def _notify_assignments(self) -> None:
        """Invia il riepilogo assegnazioni correnti alla dashboard web (se collegata)."""
        if not self._push_assignments or not self._manager:
            return
        items = [
            {
                "codice"   : row.get("Codice", ""),
                "modello"  : row.get("Modello") or "",
                "persona"  : row.get("Assegnato_a") or "",
                "alias"    : row.get("Alias") or "",
                "odv"      : row.get("ODV") or "",
                "cellulare": row.get("Cellulare") or "",
                "dal"      : row.get("Data_ultimo_movimento") or "",
            }
            for row in self._manager.all_apparati()
            if (row.get("Stato") or self._manager.STATO_DISPONIBILE) == self._manager.STATO_IN_CARICO
        ]
        self._push_assignments(items)

    def _filtered_apparati(self) -> list[dict]:
        """Restituisce gli apparati che corrispondono al filtro di ricerca corrente."""
        if not self._manager:
            return []
        query = self._entry_search.get().strip().lower() if hasattr(self, "_entry_search") else ""
        result = []
        for row in self._manager.all_apparati():
            haystack = " ".join(str(row.get(k) or "") for k in
                               ("Codice", "Modello", "Assegnato_a", "ODV", "Cellulare")).lower()
            if query and query not in haystack:
                continue
            result.append(row)
        return result

    def _refresh_apparati_list(self) -> None:
        if not self._manager:
            return
        self._tree_apparati.delete(*self._tree_apparati.get_children())
        self._notes_by_code = {}
        self._codice_by_item = {}
        for row in self._filtered_apparati():
            codice = str(row.get("Codice", ""))
            item_id = self._tree_apparati.insert("", tk.END, values=(
                codice, row.get("Modello", ""),
                row.get("Stato") or self._manager.STATO_DISPONIBILE,
                row.get("Assegnato_a") or "—",
                row.get("Alias") or "—",
                row.get("ODV") or "—",
                row.get("Cellulare") or "—",
            ))
            self._codice_by_item[item_id] = codice
            if row.get("Note"):
                self._notes_by_code[codice] = str(row["Note"])

    def _apparati_row_tooltip_text(self, event) -> str:
        """Testo del tooltip per la riga sotto il cursore: le Note complete
        dell'apparato (non mostrate in nessuna colonna dell'elenco)."""
        row_id = self._tree_apparati.identify_row(event.y)
        if not row_id:
            return ""
        codice = self._codice_by_item.get(row_id)
        if codice is None:
            return ""
        return self._notes_by_code.get(codice, "")

    def _refresh_movimenti(self) -> None:
        if not self._manager:
            return
        self._tree_movimenti.delete(*self._tree_movimenti.get_children())
        for m in self._manager.recent_movements():
            self._tree_movimenti.insert("", tk.END, values=(
                m.get("Data_ora", ""), m.get("Codice", ""), m.get("Modello", ""),
                m.get("Operazione", ""), m.get("Persona", ""),
                m.get("Alias") or "—", m.get("ODV") or "—", m.get("Cellulare") or "—",
                m.get("Operatore", ""),
            ))

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _t(self) -> dict:
        return self._TRANSLATIONS[self._lang]
