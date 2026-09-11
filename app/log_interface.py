# -*- coding: utf-8 -*-
"""
log_interface.py
Splash screen e interfaccia principale di log delle comunicazioni radio.
"""

import os
import queue
import tkinter as tk
from datetime import datetime
from tkinter import messagebox, ttk

from PIL import Image, ImageTk

try:
    import qrcode
    _QRCODE_AVAILABLE = True
except ImportError:
    _QRCODE_AVAILABLE = False

from admin_panel import open_admin_panel
from directory_selector import ConnectionChecker
from map_panel import GisMapPanel
from recovery_manager import RecoveryManager
from report_creator import ReportCreator
from tlc_point import TLCPointPanel
from ui_utils import (
    AutocompleteCombobox, adaptive_geometry, add_vscrollbar, apply_theme,
    maximize_if_small_screen,
)
from web_dashboard import WebDashboard


# ======================================================================
# Splash Screen
# ======================================================================

class SplashScreen:
    """
    Mostra una finestra di benvenuto con logo, titolo, crediti e una barra
    di caricamento, che si chiude automaticamente dopo un intervallo
    configurabile.
    """

    DISPLAY_MS = 3000
    PROGRESS_STEP_MS = 30

    def __init__(self, firmware: str, logo_path: str, proprieties: str):
        self._firmware    = firmware
        self._logo_path   = logo_path
        self._proprieties = proprieties

    def show(self) -> None:
        """Apre la splash screen e attende che si chiuda."""
        root = tk.Tk()
        root.title("ProcivBesRadioTeamTool")
        apply_theme(root)
        adaptive_geometry(root, 1200, 800, min_w=500, min_h=400)
        root.resizable(True, True)

        try:
            img_raw  = Image.open(self._logo_path).resize((300, 300), Image.LANCZOS)
            img      = ImageTk.PhotoImage(img_raw)
            icon_raw = Image.open(self._logo_path).resize((32, 32), Image.LANCZOS)
            icon     = ImageTk.PhotoImage(icon_raw)
            root.iconphoto(False, icon)
            lbl_img = tk.Label(root, image=img)
            lbl_img.image = img
            lbl_img.pack(pady=10)
        except Exception as e:
            print(f"Errore caricamento immagine splash: {e}")

        tk.Label(
            root,
            text="Registro Comunicazioni Radio",
            font=("Helvetica", 20, "bold")
        ).pack(pady=10)

        tk.Label(
            root,
            text=(
                f"Created by Jacopo Marzio\n"
                f"proprieties of {self._proprieties} V{self._firmware}"
            ),
            font=("Helvetica", 8)
        ).pack(side="bottom", pady=10)

        progress = ttk.Progressbar(root, mode="determinate", maximum=100, length=280)
        progress.pack(pady=(5, 5))
        lbl_loading = tk.Label(root, text="Avvio in corso...", font=("Helvetica", 9), fg="#666666")
        lbl_loading.pack(pady=(0, 15))

        self._animate_progress(root, progress, elapsed=0)
        root.after(self.DISPLAY_MS, root.destroy)
        root.mainloop()

    def _animate_progress(self, root: tk.Tk, progress: ttk.Progressbar, elapsed: int) -> None:
        """Avanza la barra di caricamento in modo che raggiunga il 100%
        esattamente quando la splash screen si chiude."""
        # L'ultimo aggiornamento programmato può arrivare più o meno insieme
        # a root.destroy() (schedulato allo stesso istante DISPLAY_MS): se la
        # finestra è già stata distrutta non tocca né il widget né root.after,
        # altrimenti Tk solleverebbe un TclError "invalid command name".
        if not root.winfo_exists():
            return
        progress["value"] = min(100, elapsed / self.DISPLAY_MS * 100)
        if elapsed < self.DISPLAY_MS:
            root.after(
                self.PROGRESS_STEP_MS,
                lambda: self._animate_progress(root, progress, elapsed + self.PROGRESS_STEP_MS)
            )





# ======================================================================
# Main Log Interface
# ======================================================================

class RadioLogInterface:
    """
    Finestra principale dell'applicazione.
    Gestisce l'inserimento dei log radio, il recovery automatico,
    la generazione dei report PDF/XLSX e la ricezione di risposte
    dall'operatore remoto connesso via dashboard WebSocket.
    """

    _TRANSLATIONS = {
        "it": {
            "operator"        : "Operatore:",
            "event"           : "Evento:",
            "auto_datetime"   : "Data/Ora Automatica",
            "manual_datetime" : "Data/Ora (Manuale):",
            "sender"          : "Mittente:",
            "receiver"        : "Destinatario:",
            "msg_received"    : "Messaggio Ricevuto:",
            "msg_sent"        : "Messaggio Inviato:",
            "add_log"         : "Aggiungi Log",
            "generate_pdf"    : "Genera PDF",
            "operator_error"  : "Il nome dell'operatore è obbligatorio!",
            "event_error"     : "Il nome dell'evento è obbligatorio!",
            "fields_error"    : "Tutti i campi devono essere compilati!",
            "error_title"     : "Errore",
            "warning_title"   : "Avviso",
            "logo_error"      : "Impossibile caricare il logo: {}",
            "pdf_success"     : "Rapporto PDF generato in {}",
            "pdf_title"       : "Registro Comunicazioni Radio",
            "listbox_header"  : "Log comunicazioni",
            "xlsx_success"    : "Rapporto XLSX generato in {}",
            "chat_pdf_success" : "Rapporto chat PDF generato in {}",
            "chat_xlsx_success": "Rapporto chat XLSX generato in {}",
            "chat_report_empty": "Nessun messaggio in chat: report chat non generato.",
            "connected"       : "Connesso a Internet",
            "disconnected"    : "Non connesso a Internet",
            "waiting"         : "Attendo...",
            "mkdir_error"     : "Impossibile creare la directory: {}",
            "pdf_gen_error"   : "Errore nella generazione del report: {}",
            "chat_header"     : "Chat",
            "chat_send"       : "Invia",
            "dashboard_link"  : "Link dashboard:",
            "copy_link"       : "Copia link",
            "link_copied"     : "Link copiato!",
            "show_qr"         : "Mostra QR",
            "qr_window_title" : "QR dashboard",
            "qr_hint"         : "Inquadra con la fotocamera del telefono per aprire la dashboard.",
            "qr_unavailable"  : "Generazione QR non disponibile: libreria 'qrcode' non installata.",
            "tab_log"         : "Log Comunicazioni",
            "tab_tlc"         : "TLC Point",
            "tab_map"         : "Mappa",
            "menu_settings"   : "Impostazioni",
            "menu_admin"      : "Pannello amministratore...",
            "menu_language"   : "Lingua",
            "form_header"     : "Dati comunicazione",
            "empty_log"       : "Nessun log ancora. Compila il modulo sopra e premi \"Aggiungi Log\".",
            "empty_chat"      : "Nessun messaggio in chat.",
            "generating"      : "Generazione in corso...",
        },
        "en": {
            "operator"        : "Operator:",
            "event"           : "Event:",
            "auto_datetime"   : "Automatic Date/Time",
            "manual_datetime" : "Date/Time (Manual):",
            "sender"          : "Sender:",
            "receiver"        : "Receiver:",
            "msg_received"    : "Message Received:",
            "msg_sent"        : "Message Sent:",
            "add_log"         : "Add Log",
            "generate_pdf"    : "Generate PDF",
            "operator_error"  : "Operator name is required!",
            "event_error"     : "Event name is required!",
            "fields_error"    : "All fields must be filled out!",
            "error_title"     : "Error",
            "warning_title"   : "Warning",
            "logo_error"      : "Could not load logo: {}",
            "pdf_success"     : "PDF report generated at {}",
            "pdf_title"       : "Radio Communication Log",
            "listbox_header"  : "Communication log",
            "xlsx_success"    : "XLSX report generated at {}",
            "chat_pdf_success" : "Chat PDF report generated at {}",
            "chat_xlsx_success": "Chat XLSX report generated at {}",
            "chat_report_empty": "No chat messages: chat report not generated.",
            "connected"       : "Connected to Internet",
            "disconnected"    : "Not connected to Internet",
            "waiting"         : "Waiting...",
            "mkdir_error"     : "Cannot create directory: {}",
            "pdf_gen_error"   : "Error generating report: {}",
            "chat_header"     : "Chat",
            "chat_send"       : "Send",
            "dashboard_link"  : "Dashboard link:",
            "copy_link"       : "Copy link",
            "link_copied"     : "Link copied!",
            "show_qr"         : "Show QR",
            "qr_window_title" : "Dashboard QR",
            "qr_hint"         : "Scan with your phone's camera to open the dashboard.",
            "qr_unavailable"  : "QR generation unavailable: 'qrcode' library not installed.",
            "tab_log"         : "Communication Log",
            "tab_tlc"         : "TLC Point",
            "tab_map"         : "Map",
            "menu_settings"   : "Settings",
            "menu_admin"      : "Administrator panel...",
            "menu_language"   : "Language",
            "form_header"     : "Communication data",
            "empty_log"       : "No log entries yet. Fill out the form above and press \"Add Log\".",
            "empty_chat"      : "No chat messages.",
            "generating"      : "Generating...",
        },
    }

    LED_REFRESH_MS = 2000
    DASHBOARD_LINK_REFRESH_MS = 5000

    def __init__(
        self,
        login_datetime: str,
        directory: str,
        n_files: int,
        logo_path: str,
        program_title: str = "Radio Communication Log",
        dashboard: WebDashboard | None = None,
        apparati_db_path: str = "apparati.xlsx",
        map_data_path: str = "mappa_gis.json",
        config_path: str = "configurator.txt",
    ):
        self._login_datetime   = login_datetime
        self._directory        = directory
        self._n_files          = n_files
        self._logo_path        = logo_path
        self._program_title    = program_title
        self._apparati_db_path = apparati_db_path
        self._map_data_path    = map_data_path
        self._config_path      = config_path
        self._lang             = "it"
        # Alias TLC Point noti, suggeriti in mittente/destinatario del log:
        # popolata/aggiornata da TLCPointPanel tramite on_aliases_changed.
        self._alias_suggestions: list[str] = []
        self._communication_log: list[tuple] = []
        self._chat_log: list[tuple] = []  # (date_time, sender, origin, text)
        self._recovery         = RecoveryManager()
        self._reporter         = ReportCreator()
        self._dashboard        = dashboard
        self._root: tk.Tk | None = None
        # Coda thread-safe: il thread Flask vi deposita le risposte remote,
        # il thread Tkinter (main loop) le preleva periodicamente.
        # Tkinter non è thread-safe: non si possono chiamare i suoi metodi
        # (es. root.after) da un thread diverso da quello della mainloop.
        self._remote_queue: queue.Queue = queue.Queue()

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def run(self) -> None:
        """Costruisce l'interfaccia e avvia il loop Tkinter."""
        self._build_window()
        self._load_recovery()
        self._root.mainloop()

    def handle_remote_message(self, sender: str, text: str) -> None:
        """
        Riceve un messaggio chat dal client remoto (chiamato dal thread
        Flask della dashboard). Si limita a mettere (sender, text) in una
        coda thread-safe: l'aggiornamento della UI Tkinter avviene sempre e
        solo nel thread principale, tramite _poll_remote_queue().
        """
        self._remote_queue.put((sender, text))

    def _push_assignments_to_dashboard(self, assignments: list) -> None:
        """
        Inoltra il riepilogo assegnazioni apparati correnti alla dashboard
        web (se attiva), chiamato da TLCPointPanel dopo ogni carico/scarico.
        """
        if self._dashboard:
            self._dashboard.push_assignments(assignments)

    def _update_alias_suggestions(self, aliases: list) -> None:
        """
        Aggiorna l'elenco di alias suggeriti in mittente/destinatario,
        chiamato da TLCPointPanel ogni volta che un alias viene assegnato,
        restituito o registrato (carico/scarico/nuovo apparato).
        """
        self._alias_suggestions = aliases
        self._entry_sender.set_completion_list(aliases)
        self._entry_receiver.set_completion_list(aliases)

    # ------------------------------------------------------------------
    # Window construction
    # ------------------------------------------------------------------

    def _build_window(self) -> None:
        root = tk.Tk()
        root.title(self._program_title)
        apply_theme(root)
        adaptive_geometry(root, 1300, 950, min_w=900, min_h=650)
        root.resizable(True, True)
        # Su schermi piccoli (netbook, monitor secondari) massimizza subito:
        # evita che pulsanti e pannelli restino fuori dall'area visibile.
        maximize_if_small_screen(root)
        self._root = root

        self._build_menu_bar(root)
        self._build_top_bar(root)
        self._build_led(root)

        notebook = ttk.Notebook(root)
        notebook.pack(fill="both", expand=True, padx=10, pady=(5, 0))
        self._notebook = notebook

        tab_log = tk.Frame(notebook)
        tab_tlc = tk.Frame(notebook)
        tab_map = tk.Frame(notebook)
        notebook.add(tab_log, text=self._t()["tab_log"])
        notebook.add(tab_tlc, text=self._t()["tab_tlc"])
        notebook.add(tab_map, text=self._t()["tab_map"])

        # ── Scheda "Log Comunicazioni" (contenuto storico dell'app) ──
        self._build_input_frame(tab_log)

        panels = tk.Frame(tab_log)
        panels.pack(pady=5, padx=20, fill="both", expand=True)
        panels.columnconfigure(0, weight=3)
        panels.columnconfigure(1, weight=1)

        self._build_listbox(panels)
        self._build_chat_panel(panels)

        self._build_dashboard_bar(tab_log)
        self._build_buttons(tab_log)
        self._update_empty_placeholders()

        # ── Scheda "TLC Point" (carico/scarico apparati) ─────────────
        self._tlc_panel = TLCPointPanel(
            tab_tlc,
            db_path=self._apparati_db_path,
            get_operator=lambda: self._entry_operator.get(),
            lang=self._lang,
            directory=self._directory,
            logo_path=self._logo_path,
            push_assignments=self._push_assignments_to_dashboard,
            on_aliases_changed=self._update_alias_suggestions,
        )
        self._tlc_panel.pack(fill="both", expand=True)

        # ── Scheda "Mappa" (GIS: operatori/ostacoli su OpenStreetMap) ──
        self._map_panel = GisMapPanel(tab_map, data_path=self._map_data_path, lang=self._lang)
        self._map_panel.pack(fill="both", expand=True)

        # Avvia il polling periodico della coda risposte remote.
        # Va schedulato qui (thread principale) e non richiamato dal thread
        # Flask, altrimenti Tkinter solleva "main thread is not in main loop".
        self._poll_remote_queue()

    def _build_top_bar(self, parent: tk.Widget) -> None:
        frame = tk.Frame(parent)
        frame.pack(pady=10)

        if os.path.exists(self._logo_path):
            try:
                logo_img = self._load_image(self._logo_path, 100, 100)
                icon_img = self._load_image(self._logo_path, 32, 32)
                lbl_logo = tk.Label(frame, image=logo_img)
                lbl_logo.image = logo_img
                lbl_logo.pack(side="left", padx=10)
                self._root.iconphoto(False, icon_img)
            except Exception as e:
                print(self._t()["logo_error"].format(e))

        self._title_label = tk.Label(
            frame,
            text=self._t()["pdf_title"],
            font=("Helvetica", 16, "bold")
        )
        self._title_label.pack(side="left", padx=10)

    def _build_menu_bar(self, root: tk.Tk) -> None:
        """
        Barra menu con le azioni poco frequenti (pannello amministratore,
        cambio lingua): le toglie di mezzo dal corpo della finestra
        (prima erano un pulsante + due bandiere sempre visibili), liberando
        spazio verticale utile su schermi piccoli.
        """
        t = self._t()
        if getattr(self, "_menubar", None) is not None:
            self._menubar.destroy()

        menubar = tk.Menu(root)

        settings_menu = tk.Menu(menubar, tearoff=False)
        settings_menu.add_command(label=t["menu_admin"], command=self._open_admin_panel)

        lang_menu = tk.Menu(settings_menu, tearoff=False)
        lang_menu.add_command(label="Italiano", command=lambda: self._change_language("it"))
        lang_menu.add_command(label="English", command=lambda: self._change_language("en"))
        settings_menu.add_cascade(label=t["menu_language"], menu=lang_menu)

        menubar.add_cascade(label=t["menu_settings"], menu=settings_menu)
        root.config(menu=menubar)
        self._menubar       = menubar
        self._settings_menu = settings_menu
        self._lang_menu     = lang_menu

    def _open_admin_panel(self) -> None:
        open_admin_panel(self._root, self._config_path)

    def _build_led(self, parent: tk.Widget) -> None:
        frame = tk.Frame(parent)
        frame.pack(fill="x", pady=5)

        canvas = tk.Canvas(frame, width=50, height=60)
        canvas.pack(side="left", padx=10)
        self._led    = canvas.create_oval(15, 15, 40, 40, fill="red")
        self._canvas = canvas

        self._lbl_status = tk.Label(frame, text=self._t()["waiting"], font=("Helvetica", 10))
        self._lbl_status.pack(side="left", padx=10)

        self._refresh_led()

    def _build_input_frame(self, parent: tk.Widget) -> None:
        t = self._t()
        self._form_labelframe = ttk.LabelFrame(parent, text=t["form_header"])
        frame = self._form_labelframe
        frame.pack(pady=10, padx=20, fill="x")
        frame.grid_columnconfigure(1, weight=1)
        self._input_frame = frame
        self._labels: dict[str, tk.Widget] = {}

        def _row(key: str, row: int) -> ttk.Entry:
            lbl = tk.Label(frame, text=t[key])
            lbl.grid(row=row, column=0, sticky="e", pady=5, padx=5)
            self._labels[key] = lbl
            entry = ttk.Entry(frame)
            entry.grid(row=row, column=1, sticky="ew", pady=5, padx=5)
            # Invio in un campo del form conferma il log, come premere
            # "Aggiungi Log": evita di dover sempre afferrare il mouse.
            entry.bind("<Return>", lambda e: self._add_log())
            return entry

        def _row_alias_combo(key: str, row: int) -> AutocompleteCombobox:
            """
            Come _row(), ma con suggerimenti mentre si digita: mittente e
            destinatario vengono spesso indicati con l'alias/nominativo
            missione assegnato in TLC Point, che qui viene proposto per
            evitare di doverlo ricordare/ridigitare a mano.
            """
            lbl = tk.Label(frame, text=t[key])
            lbl.grid(row=row, column=0, sticky="e", pady=5, padx=5)
            self._labels[key] = lbl
            combo = AutocompleteCombobox(frame, completion_list=self._alias_suggestions)
            combo.grid(row=row, column=1, sticky="ew", pady=5, padx=5)
            combo.bind("<Return>", lambda e: self._add_log())
            return combo

        self._entry_operator     = _row("operator", 0)
        self._entry_event        = _row("event", 1)

        self._var_auto_dt = tk.BooleanVar(value=True)
        chk = ttk.Checkbutton(
            frame, text=t["auto_datetime"],
            variable=self._var_auto_dt, command=self._toggle_manual_dt
        )
        chk.grid(row=2, column=0, columnspan=2, sticky="w", pady=5, padx=5)
        self._labels["auto_datetime"] = chk

        self._entry_manual_dt    = _row("manual_datetime", 3)
        self._entry_manual_dt.config(state="disabled")
        self._entry_sender       = _row_alias_combo("sender", 4)
        self._entry_receiver     = _row_alias_combo("receiver", 5)
        self._entry_msg_received = _row("msg_received", 6)
        self._entry_msg_sent     = _row("msg_sent", 7)

    def _build_listbox(self, parent: tk.Widget) -> None:
        """
        Pannello sinistro: log comunicazioni.
        Le frecce Su/Giù spostano la selezione anche quando il focus
        è altrove (es. nei campi di input).
        """
        frame = tk.Frame(parent)
        frame.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        frame.rowconfigure(1, weight=1)
        frame.columnconfigure(0, weight=1)

        self._listbox_label = tk.Label(
            frame, text=self._t()["listbox_header"], font=("Helvetica", 12, "bold")
        )
        self._listbox_label.grid(row=0, column=0, columnspan=2, sticky="w")

        self._listbox = tk.Listbox(frame, width=80, height=10)
        self._listbox.grid(row=1, column=0, sticky="nsew", pady=5)
        add_vscrollbar(frame, self._listbox)

        # Messaggio guida mostrato sopra la lista finché è vuota (stato
        # iniziale prima del primo log), nascosto non appena c'è una voce.
        self._lbl_log_empty = tk.Label(
            self._listbox, text=self._t()["empty_log"], fg="#888888",
            bg=self._listbox.cget("bg"), wraplength=420, justify="center",
        )
        self._lbl_log_empty.place(relx=0.5, rely=0.5, anchor="center")

        # Binding globale sulla finestra: frecce spostano il cursore nel listbox
        # indipendentemente da dove sia il focus in quel momento.
        self._root.bind("<Up>",   self._listbox_move_up)
        self._root.bind("<Down>", self._listbox_move_down)

    def _build_chat_panel(self, parent: tk.Widget) -> None:
        """
        Pannello destro: chat libera a due vie con chi è collegato da remoto.
        I messaggi mostrano mittente e provenienza (locale/remoto) con
        colori diversi. L'operatore può scrivere dal campo in basso.
        """
        frame = tk.Frame(parent, bd=1, relief="sunken")
        frame.grid(row=0, column=1, sticky="nsew")
        frame.rowconfigure(1, weight=1)
        frame.columnconfigure(0, weight=1)

        self._response_label = tk.Label(
            frame, text=self._t()["chat_header"],
            font=("Helvetica", 12, "bold")
        )
        self._response_label.grid(row=0, column=0, columnspan=2, sticky="w", padx=5, pady=(5, 0))

        # Text invece di Listbox: una voce di chat lunga va così a capo su
        # più righe invece di restare troncata su una singola riga senza
        # scorrimento orizzontale (limite del Listbox, che non fa wrap).
        self._chat_listbox = tk.Text(
            frame, width=35, height=10, wrap="word",
            bg="#1a1a2e", fg="#00e5ff",
            selectbackground="#0d3b66",
            font=("Courier", 9), state="disabled",
            relief="flat", padx=4, pady=2,
        )
        self._chat_listbox.tag_config("locale", foreground="#00e5ff")
        self._chat_listbox.tag_config("remoto", foreground="#ff6b35")
        self._chat_listbox.grid(row=1, column=0, sticky="nsew", padx=(5, 0), pady=5)
        add_vscrollbar(frame, self._chat_listbox)

        self._lbl_chat_empty = tk.Label(
            self._chat_listbox, text=self._t()["empty_chat"], fg="#5a7a80",
            bg=self._chat_listbox.cget("bg"), wraplength=180, justify="center",
        )
        self._lbl_chat_empty.place(relx=0.5, rely=0.5, anchor="center")

        self._entry_chat = ttk.Entry(frame)
        self._entry_chat.grid(row=2, column=0, sticky="ew", padx=(5, 0), pady=(0, 5))
        self._entry_chat.bind("<Return>", lambda e: self._send_chat_message())

        self._btn_chat_send = ttk.Button(
            frame, text=self._t()["chat_send"], command=self._send_chat_message
        )
        self._btn_chat_send.grid(row=2, column=1, padx=(5, 5), pady=(0, 5))

    def _build_dashboard_bar(self, parent: tk.Widget) -> None:
        """
        Barra informativa con il link della dashboard da condividere
        e pulsante copia-negli-appunti.
        """
        if not self._dashboard:
            return

        frame = tk.Frame(parent, bd=1, relief="groove")
        frame.pack(fill="x", padx=20, pady=(0, 5))

        tk.Label(
            frame, text=self._t()["dashboard_link"],
            font=("Helvetica", 9, "bold")
        ).pack(side="left", padx=(8, 4))

        self._lbl_link = tk.Label(
            frame, text=self._dashboard.link,
            font=("Courier", 9), fg="#0066cc",
            cursor="hand2"
        )
        self._lbl_link.pack(side="left", padx=4)
        self._refresh_dashboard_link()

        self._lbl_copied = tk.Label(frame, text="", font=("Helvetica", 8), fg="green")
        self._lbl_copied.pack(side="right", padx=8)

        tk.Button(
            frame, text=self._t()["copy_link"],
            command=self._copy_dashboard_link, font=("Helvetica", 8)
        ).pack(side="right", padx=4, pady=3)

        self._btn_show_qr = tk.Button(
            frame, text=self._t()["show_qr"],
            command=self._show_dashboard_qr, font=("Helvetica", 8)
        )
        self._btn_show_qr.pack(side="right", padx=4, pady=3)

    def _show_dashboard_qr(self) -> None:
        """
        Apre una finestrella con il QR code del link dashboard, comodo per
        farlo inquadrare al volo da un telefono senza dover leggere/digitare
        l'URL a mano.
        """
        t = self._t()
        if not _QRCODE_AVAILABLE:
            messagebox.showerror(t["error_title"], t["qr_unavailable"])
            return

        link = self._dashboard.link
        qr_img = qrcode.make(link)
        qr_img = qr_img.get_image() if hasattr(qr_img, "get_image") else qr_img
        qr_img = qr_img.resize((320, 320), Image.NEAREST)
        photo = ImageTk.PhotoImage(qr_img)

        win = tk.Toplevel(self._root)
        win.title(t["qr_window_title"])
        win.resizable(False, False)
        win.transient(self._root)

        lbl_img = tk.Label(win, image=photo, padx=15, pady=15)
        lbl_img.image = photo  # riferimento forte: evita che il GC cancelli l'immagine
        lbl_img.pack()
        tk.Label(win, text=t["qr_hint"], font=("Helvetica", 9), wraplength=300,
                justify="center").pack(padx=15, pady=(0, 10))
        tk.Label(win, text=link, font=("Courier", 8), fg="#555555").pack(pady=(0, 10))

    def _build_buttons(self, parent: tk.Widget) -> None:
        t = self._t()
        frame = tk.Frame(parent)
        frame.pack(pady=10)

        # Azione primaria (la più frequente) in evidenza, quella secondaria
        # (generazione report, meno frequente) in stile normale.
        self._btn_add_log = ttk.Button(
            frame, text=t["add_log"], style="Accent.TButton", command=self._add_log
        )
        self._btn_add_log.grid(row=0, column=0, padx=10)

        self._btn_gen_pdf = ttk.Button(frame, text=t["generate_pdf"], command=self._generate_reports)
        self._btn_gen_pdf.grid(row=0, column=1, padx=10)

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def _add_log(self) -> None:
        t = self._t()
        date_time = (
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            if self._var_auto_dt.get()
            else self._entry_manual_dt.get()
        )
        sender       = self._entry_sender.get()
        receiver     = self._entry_receiver.get()
        msg_received = self._entry_msg_received.get()
        msg_sent     = self._entry_msg_sent.get()

        if not all([date_time, sender, receiver, msg_received, msg_sent]):
            messagebox.showerror(t["error_title"], t["fields_error"])
            return

        entry = (date_time, sender, receiver, msg_received, msg_sent)
        self._communication_log.append(entry)
        self._recovery.append(*entry)

        if self._dashboard:
            self._dashboard.push_entry(entry)

        self._listbox.insert(
            tk.END,
            f"{date_time} - {sender} → {receiver} : {msg_received} | {msg_sent}"
        )
        self._update_empty_placeholders()

        # Reset campi
        if not self._var_auto_dt.get():
            self._entry_manual_dt.delete(0, tk.END)
        for e in (self._entry_sender, self._entry_receiver,
                  self._entry_msg_received, self._entry_msg_sent):
            e.delete(0, tk.END)

    def _generate_reports(self) -> None:
        t        = self._t()
        operator = self._entry_operator.get()
        event    = self._entry_event.get()

        if not operator:
            messagebox.showerror(t["error_title"], t["operator_error"])
            return
        if not event:
            messagebox.showerror(t["error_title"], t["event_error"])
            return

        if not os.path.exists(self._directory):
            try:
                os.makedirs(self._directory)
            except Exception as e:
                messagebox.showerror(t["error_title"], t["mkdir_error"].format(e))
                return

        # La generazione PDF/XLSX può richiedere qualche istante: disabilita
        # il pulsante e mostra un testo di avanzamento, così l'app non
        # sembra "bloccata" senza feedback durante l'operazione.
        original_text = self._btn_gen_pdf.cget("text")
        self._btn_gen_pdf.config(state="disabled", text=t["generating"])
        self._root.update_idletasks()
        try:
            n_pdf  = self._reporter.count_files(
                self._directory, ".pdf", prefix="rapporto_comunicazioni_radio_"
            )
            n_xlsx = self._reporter.count_files(
                self._directory, ".xlsx", prefix="rapporto_comunicazioni_radio_"
            )

            # Report log comunicazioni — salvato sia nella directory scelta
            # sia nel backup locale fisso (report_creator se ne occupa).
            pdf_path  = self._reporter.create_pdf(
                operator, event, self._login_datetime,
                self._communication_log, self._directory, n_pdf, self._logo_path
            )
            xlsx_path = self._reporter.create_xlsx(
                operator, event, self._login_datetime,
                self._communication_log, self._directory, n_xlsx, self._logo_path
            )
            messagebox.showinfo("Success", t["pdf_success"].format(pdf_path))
            messagebox.showinfo("Success", t["xlsx_success"].format(xlsx_path))

            # Report chat — stessa logica, generato solo se ci sono messaggi.
            if self._chat_log:
                n_chat_pdf  = self._reporter.count_files(
                    self._directory, ".pdf", prefix="rapporto_chat_"
                )
                n_chat_xlsx = self._reporter.count_files(
                    self._directory, ".xlsx", prefix="rapporto_chat_"
                )
                chat_pdf_path  = self._reporter.create_chat_pdf(
                    operator, event, self._login_datetime,
                    self._chat_log, self._directory, n_chat_pdf, self._logo_path
                )
                chat_xlsx_path = self._reporter.create_chat_xlsx(
                    operator, event, self._login_datetime,
                    self._chat_log, self._directory, n_chat_xlsx, self._logo_path
                )
                messagebox.showinfo("Success", t["chat_pdf_success"].format(chat_pdf_path))
                messagebox.showinfo("Success", t["chat_xlsx_success"].format(chat_xlsx_path))
            else:
                messagebox.showinfo(t["warning_title"], t["chat_report_empty"])
        except Exception as e:
            messagebox.showerror(t["error_title"], t["pdf_gen_error"].format(e))
        finally:
            self._btn_gen_pdf.config(state="normal", text=original_text)

    def _toggle_manual_dt(self) -> None:
        state = "disabled" if self._var_auto_dt.get() else "normal"
        self._entry_manual_dt.config(state=state)

    def _change_language(self, lang: str) -> None:
        self._lang = lang
        t = self._t()
        self._root.title(t["pdf_title"])
        self._title_label.config(text=t["pdf_title"])
        self._listbox_label.config(text=t["listbox_header"])
        self._response_label.config(text=t["chat_header"])
        self._btn_add_log.config(text=t["add_log"])
        self._btn_gen_pdf.config(text=t["generate_pdf"])
        self._btn_chat_send.config(text=t["chat_send"])
        self._notebook.tab(0, text=t["tab_log"])
        self._notebook.tab(1, text=t["tab_tlc"])
        self._notebook.tab(2, text=t["tab_map"])
        self._tlc_panel.set_language(lang)
        self._map_panel.set_language(lang)
        for key in ("operator", "event", "manual_datetime",
                    "sender", "receiver", "msg_received", "msg_sent"):
            self._labels[key].config(text=t[key])
        self._labels["auto_datetime"].config(text=t["auto_datetime"])
        self._form_labelframe.config(text=t["form_header"])
        if self._dashboard:
            self._btn_show_qr.config(text=t["show_qr"])
        # Su Windows le voci di primo livello della barra menu (quella
        # assegnata con root.config(menu=...)) non supportano l'aggiornamento
        # dinamico dell'etichetta via entryconfig (limitazione nativa Win32
        # esposta da Tk): la barra viene semplicemente ricreata da capo.
        self._build_menu_bar(self._root)
        self._update_empty_placeholders()

    def _refresh_led(self) -> None:
        t = self._t()
        if ConnectionChecker.is_connected():
            self._canvas.itemconfig(self._led, fill="green")
            self._lbl_status.config(text=t["connected"])
        else:
            self._canvas.itemconfig(self._led, fill="red")
            self._lbl_status.config(text=t["disconnected"])
        self._root.after(self.LED_REFRESH_MS, self._refresh_led)

    def _refresh_dashboard_link(self) -> None:
        """
        Rilegge il link dashboard (l'IP LAN rilevato può cambiare durante
        l'esecuzione, es. passaggio da Wi-Fi a cavo) e aggiorna l'etichetta
        solo se è davvero cambiato, per non far "lampeggiare" il testo.
        Il QR code invece è già sempre aggiornato: viene generato al volo
        ogni volta che si apre la finestrella, rileggendo il link fresco.
        """
        current = self._dashboard.link
        if self._lbl_link.cget("text") != current:
            self._lbl_link.config(text=current)
        self._root.after(self.DASHBOARD_LINK_REFRESH_MS, self._refresh_dashboard_link)

    def _copy_dashboard_link(self) -> None:
        """Copia il link della dashboard negli appunti e mostra conferma."""
        if not self._dashboard:
            return
        self._root.clipboard_clear()
        self._root.clipboard_append(self._dashboard.link)
        self._lbl_copied.config(text=self._t()["link_copied"])
        self._root.after(2000, lambda: self._lbl_copied.config(text=""))

    REMOTE_POLL_MS = 200

    def _poll_remote_queue(self) -> None:
        """
        Preleva tutti i messaggi chat remoti accumulati nella coda e li
        mostra nel pannello. Eseguito esclusivamente nel thread Tkinter
        (schedulato con root.after, mai chiamato da altri thread).
        """
        while True:
            try:
                sender, text = self._remote_queue.get_nowait()
            except queue.Empty:
                break
            self._append_chat_message(sender, text, origin="remoto")
        self._root.after(self.REMOTE_POLL_MS, self._poll_remote_queue)

    def _send_chat_message(self) -> None:
        """
        Invia un messaggio chat dall'operatore locale: lo mostra subito nel
        pannello e lo inoltra alla dashboard (che lo trasmette in tempo
        reale a tutti i browser collegati via SSE).
        """
        text = self._entry_chat.get().strip()
        if not text:
            return
        sender = self._entry_operator.get().strip() or "Operatore"

        self._append_chat_message(sender, text, origin="locale")
        if self._dashboard:
            self._dashboard.push_chat_message(sender, text, origin="locale")

        self._entry_chat.delete(0, tk.END)

    def _append_chat_message(self, sender: str, text: str, origin: str) -> None:
        """
        Aggiunge un messaggio al pannello chat (eseguito nel thread Tkinter)
        e lo registra nella cronologia usata per generare il report chat.
        origin: "locale" (operatore, dall'app) oppure "remoto" (dal browser).
        """
        now = datetime.now()
        timestamp = now.strftime("%H:%M:%S")
        full_datetime = now.strftime("%Y-%m-%d %H:%M:%S")

        tag = "locale" if origin == "locale" else "remoto"
        needs_newline = self._chat_listbox.index("end-1c") != "1.0"
        self._chat_listbox.config(state="normal")
        if needs_newline:
            self._chat_listbox.insert(tk.END, "\n")
        self._chat_listbox.insert(tk.END, f"[{timestamp}] {sender}: {text}", tag)
        self._chat_listbox.config(state="disabled")
        self._chat_listbox.see(tk.END)

        self._chat_log.append((full_datetime, sender, origin, text))
        self._update_empty_placeholders()

    def _load_recovery(self) -> None:
        """
        Carica l'eventuale sessione di recovery e ripristina i log.
        Le voci ripristinate vengono anche inviate alla dashboard remota.
        """
        recovered = self._recovery.load_latest()
        if not recovered:
            return
        for log in recovered:
            self._communication_log.append(log)
            self._listbox.insert(
                tk.END,
                f"{log[0]} - {log[1]} → {log[2]} : {log[3]} | {log[4]}"
            )
            if self._dashboard:
                self._dashboard.push_entry(log)
        self._update_empty_placeholders()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _update_empty_placeholders(self) -> None:
        """Mostra/nasconde i messaggi guida sopra le liste log/chat vuote."""
        if self._listbox.size() == 0:
            self._lbl_log_empty.place(relx=0.5, rely=0.5, anchor="center")
        else:
            self._lbl_log_empty.place_forget()
        if self._chat_listbox.index("end-1c") == "1.0":
            self._lbl_chat_empty.place(relx=0.5, rely=0.5, anchor="center")
        else:
            self._lbl_chat_empty.place_forget()

    def _listbox_move_up(self, event=None) -> str:
        """Sposta la selezione del listbox di una riga verso l'alto."""
        sel = self._listbox.curselection()
        if sel:
            idx = max(0, sel[0] - 1)
        else:
            idx = self._listbox.size() - 1
        self._listbox.selection_clear(0, tk.END)
        self._listbox.selection_set(idx)
        self._listbox.see(idx)
        return "break"   # impedisce che la freccia sposti anche il cursore del campo attivo

    def _listbox_move_down(self, event=None) -> str:
        """Sposta la selezione del listbox di una riga verso il basso."""
        sel = self._listbox.curselection()
        last = self._listbox.size() - 1
        if sel:
            idx = min(last, sel[0] + 1)
        else:
            idx = 0
        self._listbox.selection_clear(0, tk.END)
        self._listbox.selection_set(idx)
        self._listbox.see(idx)
        return "break"

    def _t(self) -> dict:
        return self._TRANSLATIONS[self._lang]

    @staticmethod
    def _load_image(path: str, w: int, h: int) -> ImageTk.PhotoImage:
        return ImageTk.PhotoImage(Image.open(path).resize((w, h), Image.LANCZOS))
