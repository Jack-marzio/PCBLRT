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

from directory_selector import ConnectionChecker
from recovery_manager import RecoveryManager
from report_creator import ReportCreator
from tlc_point import TLCPointPanel
from ui_utils import adaptive_geometry, add_vscrollbar, maximize_if_small_screen
from web_dashboard import WebDashboard


# ======================================================================
# Splash Screen
# ======================================================================

class SplashScreen:
    """
    Mostra una finestra di benvenuto con logo, titolo e crediti,
    che si chiude automaticamente dopo un intervallo configurabile.
    """

    DISPLAY_MS = 3000

    def __init__(self, firmware: str, logo_path: str, proprieties: str):
        self._firmware    = firmware
        self._logo_path   = logo_path
        self._proprieties = proprieties

    def show(self) -> None:
        """Apre la splash screen e attende che si chiuda."""
        root = tk.Tk()
        root.title("ProcivBesRadioTeamTool")
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

        root.after(self.DISPLAY_MS, root.destroy)
        root.mainloop()





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
            "tab_log"         : "Log Comunicazioni",
            "tab_tlc"         : "TLC Point",
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
            "tab_log"         : "Communication Log",
            "tab_tlc"         : "TLC Point",
        },
    }

    LED_REFRESH_MS = 2000

    def __init__(
        self,
        login_datetime: str,
        directory: str,
        n_files: int,
        logo_path: str,
        flag_list: list[str],
        program_title: str = "Radio Communication Log",
        dashboard: WebDashboard | None = None,
        apparati_db_path: str = "apparati.xlsx",
    ):
        self._login_datetime   = login_datetime
        self._directory        = directory
        self._n_files          = n_files
        self._logo_path        = logo_path
        self._flag_list        = flag_list
        self._program_title    = program_title
        self._apparati_db_path = apparati_db_path
        self._lang             = "it"
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

    # ------------------------------------------------------------------
    # Window construction
    # ------------------------------------------------------------------

    def _build_window(self) -> None:
        root = tk.Tk()
        root.title(self._program_title)
        adaptive_geometry(root, 1300, 950, min_w=900, min_h=650)
        root.resizable(True, True)
        # Su schermi piccoli (netbook, monitor secondari) massimizza subito:
        # evita che pulsanti e pannelli restino fuori dall'area visibile.
        maximize_if_small_screen(root)
        self._root = root

        self._build_top_bar(root)
        self._build_led(root)

        notebook = ttk.Notebook(root)
        notebook.pack(fill="both", expand=True, padx=10, pady=(5, 0))
        self._notebook = notebook

        tab_log = tk.Frame(notebook)
        tab_tlc = tk.Frame(notebook)
        notebook.add(tab_log, text=self._t()["tab_log"])
        notebook.add(tab_tlc, text=self._t()["tab_tlc"])

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
        self._build_flags(tab_log)

        # ── Scheda "TLC Point" (carico/scarico apparati) ─────────────
        self._tlc_panel = TLCPointPanel(
            tab_tlc,
            db_path=self._apparati_db_path,
            get_operator=lambda: self._entry_operator.get(),
            lang=self._lang,
            directory=self._directory,
            logo_path=self._logo_path,
            push_assignments=self._push_assignments_to_dashboard,
        )
        self._tlc_panel.pack(fill="both", expand=True)

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
        frame = tk.Frame(parent)
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
            return entry

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
        self._entry_sender       = _row("sender", 4)
        self._entry_receiver     = _row("receiver", 5)
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

        self._chat_listbox = tk.Listbox(
            frame, width=35, height=10,
            bg="#1a1a2e", fg="#00e5ff",
            selectbackground="#0d3b66",
            font=("Courier", 9)
        )
        self._chat_listbox.grid(row=1, column=0, sticky="nsew", padx=(5, 0), pady=5)
        add_vscrollbar(frame, self._chat_listbox)

        self._entry_chat = ttk.Entry(frame)
        self._entry_chat.grid(row=2, column=0, sticky="ew", padx=(5, 0), pady=(0, 5))
        self._entry_chat.bind("<Return>", lambda e: self._send_chat_message())

        self._btn_chat_send = tk.Button(
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

        self._lbl_copied = tk.Label(frame, text="", font=("Helvetica", 8), fg="green")
        self._lbl_copied.pack(side="right", padx=8)

        tk.Button(
            frame, text=self._t()["copy_link"],
            command=self._copy_dashboard_link, font=("Helvetica", 8)
        ).pack(side="right", padx=4, pady=3)

    def _build_buttons(self, parent: tk.Widget) -> None:
        t = self._t()
        frame = tk.Frame(parent)
        frame.pack(pady=10)

        self._btn_add_log = tk.Button(frame, text=t["add_log"], command=self._add_log)
        self._btn_add_log.grid(row=0, column=0, padx=10)

        self._btn_gen_pdf = tk.Button(frame, text=t["generate_pdf"], command=self._generate_reports)
        self._btn_gen_pdf.grid(row=0, column=1, padx=10)

    def _build_flags(self, parent: tk.Widget) -> None:
        frame = tk.Frame(parent)
        frame.pack(pady=5)
        try:
            flag_it = self._load_image(self._flag_list[0], 50, 30)
            flag_en = self._load_image(self._flag_list[1], 50, 30)
            btn_it  = tk.Button(frame, image=flag_it, command=lambda: self._change_language("it"))
            btn_en  = tk.Button(frame, image=flag_en, command=lambda: self._change_language("en"))
            btn_it.image = flag_it
            btn_en.image = flag_en
            btn_it.pack(side="left", padx=10)
            btn_en.pack(side="left", padx=10)
        except Exception as e:
            messagebox.showwarning(self._t()["warning_title"], self._t()["logo_error"].format(e))

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
        self._tlc_panel.set_language(lang)
        for key in ("operator", "event", "manual_datetime",
                    "sender", "receiver", "msg_received", "msg_sent"):
            self._labels[key].config(text=t[key])
        self._labels["auto_datetime"].config(text=t["auto_datetime"])

    def _refresh_led(self) -> None:
        t = self._t()
        if ConnectionChecker.is_connected():
            self._canvas.itemconfig(self._led, fill="green")
            self._lbl_status.config(text=t["connected"])
        else:
            self._canvas.itemconfig(self._led, fill="red")
            self._lbl_status.config(text=t["disconnected"])
        self._root.after(self.LED_REFRESH_MS, self._refresh_led)

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

        idx = self._chat_listbox.size()
        self._chat_listbox.insert(tk.END, f"[{timestamp}] {sender}: {text}")
        color = "#00e5ff" if origin == "locale" else "#ff6b35"
        self._chat_listbox.itemconfig(idx, foreground=color)
        self._chat_listbox.see(tk.END)

        self._chat_log.append((full_datetime, sender, origin, text))

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

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

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
