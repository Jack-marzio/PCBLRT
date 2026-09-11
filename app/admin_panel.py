# -*- coding: utf-8 -*-
"""
admin_panel.py
Pannello di amministrazione protetto da password.

Permette di modificare tutti i parametri di configurazione dell'app
(configurator.txt) da interfaccia grafica — incluso dove salvare il
database dispositivi (Apparati_db_path) — senza doverlo editare a mano.

La password non viene mai salvata in chiaro: ne viene conservato solo
l'hash SHA-256 (chiave Admin_password_hash in configurator.txt). Al primo
accesso, se non è ancora impostata, viene richiesto di sceglierne una.
"""

import hashlib
import subprocess
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

from config_manager import ConfigManager
from ui_utils import COLOR_ERROR, adaptive_geometry, apply_theme


def _hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def open_admin_panel(parent: tk.Tk, config_path: str) -> None:
    """Punto d'ingresso: verifica la password admin e apre il pannello."""
    cfg = ConfigManager(config_path)
    stored_hash = cfg.get("Admin_password_hash")

    if not stored_hash:
        _first_time_setup(parent, cfg)
        return

    password = simpledialog.askstring(
        "Accesso amministratore", "Password amministratore:",
        show="*", parent=parent
    )
    if password is None:
        return
    if _hash_password(password) != stored_hash:
        messagebox.showerror("Accesso negato", "Password errata.", parent=parent)
        return

    _AdminWindow(parent, cfg)


def _first_time_setup(parent: tk.Tk, cfg: ConfigManager) -> None:
    messagebox.showinfo(
        "Imposta password amministratore",
        "Nessuna password amministratore è ancora configurata.\n"
        "Impostane una ora: verrà richiesta per accedere a questo pannello "
        "in futuro.",
        parent=parent,
    )
    while True:
        pw1 = simpledialog.askstring(
            "Nuova password", "Nuova password amministratore:",
            show="*", parent=parent
        )
        if pw1 is None:
            return
        if len(pw1) < 4:
            messagebox.showwarning(
                "Password troppo corta", "Usa almeno 4 caratteri.", parent=parent
            )
            continue
        pw2 = simpledialog.askstring(
            "Conferma password", "Ripeti la password:",
            show="*", parent=parent
        )
        if pw2 is None:
            return
        if pw1 != pw2:
            messagebox.showerror(
                "Errore", "Le due password non coincidono. Riprova.", parent=parent
            )
            continue
        break

    cfg.set("Admin_password_hash", _hash_password(pw1))
    cfg.save()
    messagebox.showinfo(
        "Fatto",
        "Password amministratore impostata. Riapri il pannello per accedere.",
        parent=parent,
    )


class _AdminWindow:
    """Finestra con tutti i parametri di configurazione modificabili."""

    # (chiave, etichetta, tipo campo, valore di default se lasciato vuoto)
    _FIELDS = [
        ("Program_title",     "Titolo applicazione",                    "text",      ""),
        ("Firmware_version",  "Versione firmware",                      "text",      ""),
        ("Proprieties",       "Proprietà / Ente",                       "text",      ""),
        ("Drive_path",        "Cartella di salvataggio predefinita",    "folder",    ""),
        ("Apparati_db_path",  "Database dispositivi (.xlsx)",           "save_file", "apparati.xlsx"),
        ("Map_data_path",     "Database mappa GIS (.json)",             "save_json", "mappa_gis.json"),
        ("Logo_path",         "Logo",                                   "file",      ""),
        ("Web_dashboard_port","Porta dashboard web",                    "text",      "8080"),
        ("WS_TOKEN",          "Token sessione dashboard (vuoto = automatico)", "text", ""),
    ]

    def __init__(self, parent: tk.Tk, cfg: ConfigManager):
        self._cfg = cfg
        self._entries: dict[str, ttk.Entry] = {}

        self._dirty = False

        win = tk.Toplevel(parent)
        win.title("Pannello amministratore")
        apply_theme(win)
        adaptive_geometry(win, 700, 680, min_w=520, min_h=480)
        win.resizable(True, True)
        win.transient(parent)
        win.grab_set()
        win.protocol("WM_DELETE_WINDOW", self._cancel)
        win.bind("<Escape>", lambda e: self._cancel())
        self._win = win

        canvas = tk.Canvas(win, highlightthickness=0)
        vsb = ttk.Scrollbar(win, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)
        canvas.pack(side="left", fill="both", expand=True, padx=(20, 0), pady=15)
        vsb.pack(side="right", fill="y")

        container = tk.Frame(canvas)
        container.columnconfigure(1, weight=1)
        canvas_window = canvas.create_window((0, 0), window=container, anchor="nw")

        def _on_configure(_event=None):
            canvas.configure(scrollregion=canvas.bbox("all"))
            canvas.itemconfigure(canvas_window, width=canvas.winfo_width())

        container.bind("<Configure>", _on_configure)
        canvas.bind("<Configure>", _on_configure)

        row = 0
        for key, label, kind, default in self._FIELDS:
            value = str(cfg.get(key, "") or default)
            row = self._add_row(container, row, label, value, kind, store_as=key)

        # Validazione dal vivo della porta: rossa appena non è un numero,
        # invece di scoprirlo solo al click su "Salva".
        self._lbl_port_error = tk.Label(container, text="", fg=COLOR_ERROR, font=("Segoe UI", 8))
        self._lbl_port_error.grid(row=row, column=1, sticky="w", padx=(10, 0))
        self._entries["Web_dashboard_port"].bind("<KeyRelease>", self._validate_port, add="+")
        row += 1

        flags = cfg.get("Flags_logo", ["", ""])
        row = self._add_row(container, row, "Bandiera IT", flags[0] if len(flags) > 0 else "",
                             "file", store_as="_flag_it")
        row = self._add_row(container, row, "Bandiera EN", flags[1] if len(flags) > 1 else "",
                             "file", store_as="_flag_en")

        self._var_remote = tk.BooleanVar(
            value=str(cfg.get("Remote_enabled", "false")).strip().lower() == "true"
        )
        self._var_remote.trace_add("write", lambda *a: self._mark_dirty())
        tk.Checkbutton(
            container, text="Abilita dashboard web locale (Remote_enabled)",
            variable=self._var_remote
        ).grid(row=row, column=0, columnspan=2, sticky="w", pady=10)
        row += 1

        ttk.Separator(container, orient="horizontal").grid(
            row=row, column=0, columnspan=2, sticky="ew", pady=10
        )
        row += 1

        ttk.Button(
            container, text="Cambia password amministratore",
            command=self._change_password
        ).grid(row=row, column=0, columnspan=2, sticky="w", pady=5)

        btn_frame = tk.Frame(win)
        btn_frame.pack(side="bottom", pady=15)
        ttk.Button(btn_frame, text="Salva", style="Accent.TButton", command=self._save).pack(side="left", padx=10)
        ttk.Button(btn_frame, text="Annulla", command=self._cancel).pack(side="left", padx=10)

    # ------------------------------------------------------------------
    # Costruzione righe
    # ------------------------------------------------------------------

    def _add_row(self, container: tk.Widget, row: int, label: str, value: str,
                 kind: str, store_as: str) -> int:
        tk.Label(container, text=label + ":").grid(row=row, column=0, sticky="w", pady=6)

        entry_frame = tk.Frame(container)
        entry_frame.grid(row=row, column=1, sticky="ew", pady=6, padx=(10, 0))
        entry_frame.columnconfigure(0, weight=1)

        entry = ttk.Entry(entry_frame)
        entry.insert(0, value)
        entry.grid(row=0, column=0, sticky="ew")
        entry.bind("<KeyRelease>", lambda e: self._mark_dirty())
        self._entries[store_as] = entry

        if kind == "folder":
            ttk.Button(entry_frame, text="Sfoglia...",
                       command=lambda e=entry: self._browse_folder(e)).grid(row=0, column=1, padx=(5, 0))
        elif kind == "file":
            ttk.Button(entry_frame, text="Sfoglia...",
                       command=lambda e=entry: self._browse_file(e)).grid(row=0, column=1, padx=(5, 0))
        elif kind == "save_file":
            ttk.Button(entry_frame, text="Sfoglia...",
                       command=lambda e=entry: self._browse_save_file(e, ".xlsx", "Excel")
                       ).grid(row=0, column=1, padx=(5, 0))
        elif kind == "save_json":
            ttk.Button(entry_frame, text="Sfoglia...",
                       command=lambda e=entry: self._browse_save_file(e, ".json", "JSON")
                       ).grid(row=0, column=1, padx=(5, 0))

        return row + 1

    # ------------------------------------------------------------------
    # Browse dialogs
    # ------------------------------------------------------------------

    def _browse_folder(self, entry: ttk.Entry) -> None:
        path = filedialog.askdirectory(parent=self._win)
        if path:
            entry.delete(0, tk.END)
            entry.insert(0, path)
            self._mark_dirty()

    def _browse_file(self, entry: ttk.Entry) -> None:
        path = filedialog.askopenfilename(parent=self._win)
        if path:
            entry.delete(0, tk.END)
            entry.insert(0, path)
            self._mark_dirty()

    def _browse_save_file(self, entry: ttk.Entry, extension: str, filetype_label: str) -> None:
        path = filedialog.asksaveasfilename(
            parent=self._win, defaultextension=extension,
            filetypes=[(filetype_label, f"*{extension}")]
        )
        if path:
            entry.delete(0, tk.END)
            entry.insert(0, path)
            self._mark_dirty()

    # ------------------------------------------------------------------
    # Modifiche non salvate / validazione dal vivo
    # ------------------------------------------------------------------

    def _mark_dirty(self) -> None:
        self._dirty = True

    def _validate_port(self, _event=None) -> bool:
        port_value = self._entries["Web_dashboard_port"].get().strip()
        if port_value and not port_value.isdigit():
            self._lbl_port_error.config(text="deve essere un numero")
            return False
        self._lbl_port_error.config(text="")
        return True

    def _cancel(self) -> None:
        """Chiude il pannello, chiedendo conferma se ci sono modifiche non salvate."""
        if self._dirty:
            discard = messagebox.askyesno(
                "Modifiche non salvate",
                "Ci sono modifiche non salvate. Chiudere comunque senza salvare?",
                parent=self._win,
            )
            if not discard:
                return
        self._win.destroy()

    # ------------------------------------------------------------------
    # Password
    # ------------------------------------------------------------------

    def _change_password(self) -> None:
        current = simpledialog.askstring(
            "Verifica", "Password amministratore attuale:", show="*", parent=self._win
        )
        if current is None:
            return
        if _hash_password(current) != self._cfg.get("Admin_password_hash"):
            messagebox.showerror("Errore", "Password attuale errata.", parent=self._win)
            return
        new1 = simpledialog.askstring(
            "Nuova password", "Nuova password:", show="*", parent=self._win
        )
        if not new1:
            return
        new2 = simpledialog.askstring(
            "Conferma", "Ripeti la nuova password:", show="*", parent=self._win
        )
        if new1 != new2:
            messagebox.showerror("Errore", "Le due password non coincidono.", parent=self._win)
            return
        self._cfg.set("Admin_password_hash", _hash_password(new1))
        self._cfg.save()
        messagebox.showinfo("Fatto", "Password amministratore aggiornata.", parent=self._win)

    # ------------------------------------------------------------------
    # Salvataggio
    # ------------------------------------------------------------------

    def _save(self) -> None:
        if not self._validate_port():
            messagebox.showerror(
                "Errore",
                "La porta dashboard web deve essere un numero (es. 8080).",
                parent=self._win,
            )
            return

        for key, _label, _kind, default in self._FIELDS:
            self._cfg.set(key, self._entries[key].get().strip() or default)

        self._cfg.set("Flags_logo", [
            self._entries["_flag_it"].get().strip(),
            self._entries["_flag_en"].get().strip(),
        ])
        self._cfg.set("Remote_enabled", "true" if self._var_remote.get() else "false")

        try:
            self._cfg.save()
        except Exception as e:
            messagebox.showerror(
                "Errore", f"Impossibile salvare la configurazione: {e}", parent=self._win
            )
            return

        self._dirty = False
        root = self._win.master
        restart = messagebox.askyesno(
            "Configurazione salvata",
            "Le modifiche sono state salvate.\n"
            "Diventano effettive solo dopo un riavvio dell'applicazione.\n\n"
            "Riavviare ora?",
            parent=self._win,
        )
        self._win.destroy()
        if restart:
            self._restart_app(root)

    @staticmethod
    def _restart_app(root: tk.Tk) -> None:
        try:
            if getattr(sys, "frozen", False):
                subprocess.Popen([sys.executable])
            else:
                subprocess.Popen([sys.executable] + sys.argv)
        except Exception as e:
            messagebox.showwarning(
                "Riavvio manuale richiesto",
                f"Non è stato possibile riavviare automaticamente ({e}).\n"
                "Chiudi e riapri l'applicazione manualmente.",
            )
            return
        root.destroy()
