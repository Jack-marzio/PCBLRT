# -*- coding: utf-8 -*-
"""
directory_selector.py
Finestra Tkinter per la selezione della cartella di salvataggio.
"""

import os
import socket
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageTk

from ui_utils import adaptive_geometry


class ConnectionChecker:
    """Verifica la disponibilità della connessione a Internet."""

    HOST    = "8.8.8.8"
    PORT    = 53
    TIMEOUT = 2

    @classmethod
    def is_connected(cls) -> bool:
        try:
            socket.create_connection((cls.HOST, cls.PORT), timeout=cls.TIMEOUT)
            return True
        except OSError:
            return False


class DirectorySelector:
    """
    Finestra modale Tkinter per scegliere la directory di salvataggio dei report.
    Supporta tre modalità: Drive, Locale, Esterna.
    Supporta cambio lingua IT/EN e indicatore LED di connessione.
    """

    _TRANSLATIONS = {
        "it": {
            "window_title"  : "Seleziona una cartella di Salvataggio",
            "label_title"   : "Seleziona una cartella di Salvataggio",
            "rb_drive"      : "Salva nel Drive",
            "rb_local"      : "Salva nella cartella Locale",
            "rb_external"   : "Scegli cartella Esterna",
            "browse"        : "Sfoglia...",
            "proceed"       : "Avanti",
            "err_no_ext"    : "Per favore, seleziona una cartella esterna.",
            "err_no_drive"  : "Per favore, seleziona una cartella nel Drive.",
            "err_mkdir"     : "Impossibile creare la cartella: {}",
            "warn_flags"    : "Impossibile caricare le immagini delle bandiere: {}",
            "connected"     : "Connesso a Internet",
            "disconnected"  : "Non connesso a Internet",
            "waiting"       : "Attendo...",
        },
        "en": {
            "window_title"  : "Select Save Directory",
            "label_title"   : "Select Save Directory",
            "rb_drive"      : "Save to Drive",
            "rb_local"      : "Save to Local Directory",
            "rb_external"   : "Choose External Directory",
            "browse"        : "Browse...",
            "proceed"       : "Proceed",
            "err_no_ext"    : "Please select an external folder.",
            "err_no_drive"  : "Please select a Drive folder.",
            "err_mkdir"     : "Cannot create folder: {}",
            "warn_flags"    : "Cannot load flag images: {}",
            "connected"     : "Connected to Internet",
            "disconnected"  : "Not connected to Internet",
            "waiting"       : "Waiting...",
        },
    }

    LED_REFRESH_MS = 2000

    def __init__(self, logo_path: str, flag_list: list[str], drive_path: str):
        self._logo_path  = logo_path
        self._flag_list  = flag_list   # [it_flag_path, en_flag_path]
        self._drive_path = drive_path
        self._lang       = "it"
        self._result: str | None = None

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def run(self) -> str | None:
        """Apre la finestra e restituisce la directory selezionata (o None)."""
        self._build_window()
        self._root.mainloop()
        return self._result

    # ------------------------------------------------------------------
    # Window construction
    # ------------------------------------------------------------------

    def _build_window(self) -> None:
        t = self._t()
        root = tk.Tk()
        root.title(t["window_title"])
        adaptive_geometry(root, 1200, 800, min_w=650, min_h=550)
        root.resizable(True, True)
        self._root = root

        # Icona
        try:
            icon = ImageTk.PhotoImage(Image.open(self._logo_path).resize((32, 32), Image.LANCZOS))
            root.iconphoto(False, icon)
            self._icon = icon
        except Exception:
            pass

        # Titolo
        self._lbl_title = tk.Label(root, text=t["label_title"], font=("Helvetica", 16))
        self._lbl_title.pack(pady=20)

        # LED connessione
        self._build_led(root)

        # Opzioni di salvataggio
        self._var_option = tk.StringVar(value="drive")

        self._rb_drive = ttk.Radiobutton(
            root, text=t["rb_drive"], variable=self._var_option,
            value="drive", command=self._toggle_entry
        )
        self._rb_drive.pack(anchor="w", padx=20, pady=5)

        self._rb_local = ttk.Radiobutton(
            root, text=t["rb_local"], variable=self._var_option,
            value="local", command=self._toggle_entry
        )
        self._rb_local.pack(anchor="w", padx=20, pady=5)

        self._rb_external = ttk.Radiobutton(
            root, text=t["rb_external"], variable=self._var_option,
            value="external", command=self._toggle_entry
        )
        self._rb_external.pack(anchor="w", padx=20, pady=5)

        # Frame cartella esterna
        ext_frame = tk.Frame(root)
        ext_frame.pack(anchor="w", padx=40, pady=5)
        self._entry_ext = ttk.Entry(ext_frame, width=40, state="disabled")
        self._entry_ext.pack(side="left", padx=5)
        self._btn_browse = ttk.Button(ext_frame, text=t["browse"],
                                      command=self._browse, state="disabled")
        self._btn_browse.pack(side="left")

        # Pulsante Avanti
        self._btn_proceed = ttk.Button(root, text=t["proceed"], command=self._proceed)
        self._btn_proceed.pack(pady=20)

        # Bandiere
        self._build_flags(root)

    def _build_led(self, parent: tk.Widget) -> None:
        frame = tk.Frame(parent)
        frame.pack(fill="x", pady=5)

        canvas = tk.Canvas(frame, width=50, height=60)
        canvas.pack(side="left", padx=10)
        self._led     = canvas.create_oval(15, 15, 40, 40, fill="red")
        self._canvas  = canvas

        self._lbl_status = tk.Label(frame, text=self._t()["waiting"], font=("Helvetica", 10))
        self._lbl_status.pack(side="left", padx=10)

        self._refresh_led()

    def _build_flags(self, parent: tk.Widget) -> None:
        frame = tk.Frame(parent)
        frame.pack(pady=10)
        try:
            flag_it = self._load_image(self._flag_list[0], 50, 30)
            flag_en = self._load_image(self._flag_list[1], 50, 30)
            btn_it = tk.Button(frame, image=flag_it, command=lambda: self._change_language("it"))
            btn_en = tk.Button(frame, image=flag_en, command=lambda: self._change_language("en"))
            btn_it.image = flag_it
            btn_en.image = flag_en
            btn_it.pack(side="left", padx=10)
            btn_en.pack(side="left", padx=10)
        except Exception as e:
            messagebox.showwarning("Avviso", self._t()["warn_flags"].format(e))

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def _proceed(self) -> None:
        t   = self._t()
        opt = self._var_option.get()
        if opt == "external":
            directory = self._entry_ext.get()
            if not directory:
                messagebox.showerror("Errore", t["err_no_ext"])
                return
        elif opt == "drive":
            directory = self._drive_path
            if not directory:
                messagebox.showerror("Errore", t["err_no_drive"])
                return
        else:
            directory = os.path.join(os.getcwd(), "reports")
            if not os.path.exists(directory):
                try:
                    os.makedirs(directory)
                except Exception as e:
                    messagebox.showerror("Errore", t["err_mkdir"].format(e))
                    return
        self._result = directory
        self._root.destroy()

    def _browse(self) -> None:
        path = filedialog.askdirectory()
        if path:
            self._entry_ext.config(state="normal")
            self._entry_ext.delete(0, tk.END)
            self._entry_ext.insert(0, path)

    def _toggle_entry(self) -> None:
        opt = self._var_option.get()
        if opt == "external":
            self._entry_ext.config(state="normal")
            self._btn_browse.config(state="normal")
        else:
            self._entry_ext.config(state="disabled")
            self._entry_ext.delete(0, tk.END)
            self._btn_browse.config(state="disabled")

    def _change_language(self, lang: str) -> None:
        self._lang = lang
        t = self._t()
        self._root.title(t["window_title"])
        self._lbl_title.config(text=t["label_title"])
        self._rb_drive.config(text=t["rb_drive"])
        self._rb_local.config(text=t["rb_local"])
        self._rb_external.config(text=t["rb_external"])
        self._btn_browse.config(text=t["browse"])
        self._btn_proceed.config(text=t["proceed"])

    def _refresh_led(self) -> None:
        t = self._t()
        if ConnectionChecker.is_connected():
            self._canvas.itemconfig(self._led, fill="green")
            self._lbl_status.config(text=t["connected"])
        else:
            self._canvas.itemconfig(self._led, fill="red")
            self._lbl_status.config(text=t["disconnected"])
        self._root.after(self.LED_REFRESH_MS, self._refresh_led)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _t(self) -> dict:
        return self._TRANSLATIONS[self._lang]

    @staticmethod
    def _load_image(path: str, w: int, h: int) -> ImageTk.PhotoImage:
        return ImageTk.PhotoImage(Image.open(path).resize((w, h), Image.LANCZOS))
