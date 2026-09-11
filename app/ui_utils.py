# -*- coding: utf-8 -*-
"""
ui_utils.py
Helper per un'interfaccia Tkinter adattiva.

Le finestre dell'app usavano dimensioni fisse (es. 1300x950), pensate per
monitor grandi: su PC con schermo piccolo (netbook, monitor secondari a
bassa risoluzione, alcuni laptop) la finestra risultava più grande dello
schermo stesso, con l'effetto di avere pulsanti e altri controlli "fuori
sede" (posizionati oltre il bordo visibile, irraggiungibili senza spostare
manualmente la finestra).

Questo modulo fornisce:
  - adaptive_geometry()       → dimensiona/centra una finestra senza mai
                                 superare la risoluzione reale dello schermo
  - maximize_if_small_screen() → massimizza automaticamente su schermi piccoli,
                                 così tutto il contenuto resta raggiungibile
  - add_vscrollbar()           → aggiunge una scrollbar verticale a un
                                 Listbox/Treeview posizionato con .grid(),
                                 utile quando lo spazio verticale è ridotto
"""

import sys
import tkinter as tk
from tkinter import ttk

# ── Palette e font condivisi ──────────────────────────────────────────────
FONT_FAMILY         = "Segoe UI"
COLOR_ACCENT        = "#1565c0"
COLOR_ACCENT_HOVER  = "#0d47a1"
COLOR_MUTED         = "#666666"
COLOR_SUCCESS       = "#1b7a2f"
COLOR_ERROR         = "#b03030"


def apply_theme(root: tk.Tk) -> None:
    """
    Applica un aspetto coerente a tutte le finestre dell'app: stessa
    famiglia di font, stessi colori per i pulsanti principali/secondari,
    stesso stile per Entry/Treeview/Notebook. Va chiamata subito dopo aver
    creato ogni root/Toplevel (prima di costruire i widget al suo interno).

    Va richiamata su OGNI finestra (root Tk() o Toplevel) e non solo sulla
    prima: ttk.Style è per-interprete ma ripeterla è economico e innocuo,
    ed evita sorprese se in futuro una finestra viene aperta prima delle
    altre.
    """
    default_font = (FONT_FAMILY, 10)
    root.option_add("*Font", default_font)

    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass

    style.configure(".", font=default_font)
    style.configure("TButton", font=default_font, padding=(10, 5))
    style.configure("TEntry", padding=(4, 3))
    style.configure("TCheckbutton", font=default_font)
    style.configure("TRadiobutton", font=default_font)
    style.configure("TLabelframe.Label", font=(FONT_FAMILY, 10, "bold"))
    style.configure("Treeview", font=default_font, rowheight=24)
    style.configure("Treeview.Heading", font=(FONT_FAMILY, 10, "bold"))
    style.configure("TNotebook.Tab", font=default_font, padding=(12, 6))

    # Pulsante primario (azione principale della schermata: es. "Aggiungi Log")
    style.configure(
        "Accent.TButton", font=(FONT_FAMILY, 10, "bold"),
        padding=(12, 6), foreground="white", background=COLOR_ACCENT,
    )
    style.map(
        "Accent.TButton",
        background=[("active", COLOR_ACCENT_HOVER), ("disabled", "#9e9e9e")],
        foreground=[("disabled", "#f0f0f0")],
    )


class Tooltip:
    """
    Tooltip minimale: mostra il testo restituito da 'text_func(evento)' in
    una finestrella senza bordi vicino al cursore quando ci si sofferma su
    'widget'. Usato ad esempio per mostrare le Note complete di una riga
    nell'elenco apparati di TLC Point.
    """

    def __init__(self, widget: tk.Widget, text_func, delay_ms: int = 400):
        self._widget    = widget
        self._text_func = text_func
        self._delay_ms  = delay_ms
        self._after_id  = None
        self._tip: tk.Toplevel | None = None
        widget.bind("<Motion>", self._on_motion, add="+")
        widget.bind("<Leave>", self._on_leave, add="+")

    def _on_motion(self, event) -> None:
        self._cancel()
        self._after_id = self._widget.after(self._delay_ms, lambda: self._show(event))

    def _cancel(self) -> None:
        if self._after_id:
            self._widget.after_cancel(self._after_id)
            self._after_id = None

    def _show(self, event) -> None:
        text = self._text_func(event)
        self._hide()
        if not text:
            return
        tip = tk.Toplevel(self._widget)
        tip.wm_overrideredirect(True)
        tip.wm_geometry(f"+{event.x_root + 12}+{event.y_root + 12}")
        tk.Label(
            tip, text=text, justify="left", background="#ffffe0",
            relief="solid", borderwidth=1, font=(FONT_FAMILY, 9), padx=6, pady=3,
            wraplength=320,
        ).pack()
        self._tip = tip

    def _on_leave(self, _event=None) -> None:
        self._cancel()
        self._hide()

    def _hide(self) -> None:
        if self._tip is not None:
            self._tip.destroy()
            self._tip = None


def show_banner(root: tk.Widget, message: str, kind: str = "success", duration_ms: int = 2500) -> None:
    """
    Notifica non bloccante: appare in alto a destra della finestra e
    scompare da sola dopo 'duration_ms'. Pensata per conferme frequenti
    (es. carico/scarico apparato in TLC Point) dove un popup modale
    interromperebbe inutilmente un flusso di scansione rapido.
    """
    colors = {
        "success": (COLOR_SUCCESS, "#e8f5e9"),
        "error":   (COLOR_ERROR, "#fdecea"),
    }
    fg, bg = colors.get(kind, colors["success"])

    banner = tk.Label(
        root, text=message, font=(FONT_FAMILY, 10, "bold"),
        fg=fg, bg=bg, padx=14, pady=8, relief="solid", borderwidth=1,
    )
    banner.place(relx=1.0, rely=0.0, x=-15, y=15, anchor="ne")
    banner.after(duration_ms, banner.destroy)


class AutocompleteCombobox(ttk.Combobox):
    """
    Combobox che filtra i suggerimenti mentre si digita (case-insensitive,
    corrispondenza per sottostringa) e apre automaticamente il menu a
    tendina con i risultati. Usata per suggerire mittente/destinatario nel
    registro comunicazioni in base agli alias già assegnati in TLC Point.

    L'elenco completo si aggiorna con set_completion_list() senza perdere
    il testo eventualmente già digitato dall'utente.
    """

    def __init__(self, master=None, completion_list=None, **kwargs):
        super().__init__(master, **kwargs)
        self._all_values: list[str] = []
        self.set_completion_list(completion_list or [])
        self.bind("<KeyRelease>", self._on_keyrelease)

    def set_completion_list(self, completion_list: list[str]) -> None:
        self._all_values = sorted(set(completion_list))
        self["values"] = self._all_values

    def _on_keyrelease(self, event) -> None:
        if event.keysym in ("Up", "Down", "Return", "Escape", "Tab",
                            "Shift_L", "Shift_R", "Left", "Right"):
            return
        text = self.get().strip().lower()
        if not text:
            self["values"] = self._all_values
            return
        matches = [v for v in self._all_values if text in v.lower()]
        self["values"] = matches
        if matches:
            self.event_generate("<Down>")


def _work_area(root: tk.Tk) -> tuple[int, int, int, int]:
    """
    Restituisce (x, y, larghezza, altezza) dell'area di lavoro dello schermo,
    cioè lo schermo esclusa la barra delle applicazioni.

    winfo_screenwidth()/winfo_screenheight() restituiscono la risoluzione
    TOTALE dello schermo, taskbar inclusa: su schermi piccoli questo porta a
    posizionare la finestra (bordo inferiore compreso, cioè la maniglia per
    il resize verticale) parzialmente sotto la taskbar, rendendola
    irraggiungibile col mouse. Su Windows usiamo l'API nativa per l'area di
    lavoro reale; sulle altre piattaforme ricadiamo sulla risoluzione piena.
    """
    if sys.platform == "win32":
        try:
            import ctypes
            from ctypes import wintypes

            SPI_GETWORKAREA = 0x0030
            rect = wintypes.RECT()
            ok = ctypes.windll.user32.SystemParametersInfoW(
                SPI_GETWORKAREA, 0, ctypes.byref(rect), 0
            )
            if ok and rect.right > rect.left and rect.bottom > rect.top:
                return rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top
        except Exception:
            pass

    return 0, 0, root.winfo_screenwidth(), root.winfo_screenheight()


def adaptive_geometry(
    root: tk.Tk,
    desired_w: int,
    desired_h: int,
    min_w: int = 800,
    min_h: int = 500,
    screen_margin_w: float = 0.95,
    screen_margin_h: float = 0.95,
) -> None:
    """
    Imposta geometry e minsize di 'root' in modo che la finestra non superi
    mai l'area di lavoro reale dello schermo (taskbar esclusa, con un
    margine di sicurezza per la barra del titolo), centrandola.

    Su schermi grandi si comporta come una geometry fissa (usa desired_w x
    desired_h). Su schermi piccoli riduce automaticamente le dimensioni
    invece di lasciare la finestra più grande dello schermo o con il bordo
    inferiore nascosto sotto la taskbar.
    """
    root.update_idletasks()
    work_x, work_y, work_w, work_h = _work_area(root)

    max_w = int(work_w * screen_margin_w)
    max_h = int(work_h * screen_margin_h)

    w = min(desired_w, max_w)
    h = min(desired_h, max_h)

    eff_min_w = min(min_w, work_w)
    eff_min_h = min(min_h, work_h)
    w = max(w, eff_min_w)
    h = max(h, eff_min_h)

    x = work_x + max(0, (work_w - w) // 2)
    y = work_y + max(0, (work_h - h) // 2)

    root.geometry(f"{w}x{h}+{x}+{y}")
    root.minsize(eff_min_w, eff_min_h)


def maximize_if_small_screen(
    root: tk.Tk,
    width_threshold: int = 1440,
    height_threshold: int = 850,
) -> bool:
    """
    Se lo schermo è più piccolo della soglia indicata, massimizza la
    finestra così tutti i controlli restano raggiungibili senza bisogno di
    ridimensionare manualmente. Restituisce True se la finestra è stata
    massimizzata.
    """
    root.update_idletasks()
    screen_w = root.winfo_screenwidth()
    screen_h = root.winfo_screenheight()
    if screen_w > width_threshold and screen_h > height_threshold:
        return False
    try:
        root.state("zoomed")  # Windows, e alcune build di Tk su Linux
        return True
    except tk.TclError:
        try:
            root.attributes("-zoomed", True)  # Linux/X11
            return True
        except tk.TclError:
            return False  # piattaforma senza supporto (es. alcune build macOS)


def add_vscrollbar(container: tk.Widget, widget: tk.Widget) -> ttk.Scrollbar:
    """
    Aggiunge una scrollbar verticale a un Listbox/Treeview già posizionato
    con .grid() dentro 'container', occupando la colonna subito a destra.
    Necessario perché su schermi piccoli le liste (log, chat, apparati,
    storico movimenti) possono contenere più righe di quante ne stiano
    nello spazio visibile.
    """
    info = widget.grid_info()
    col = int(info["column"]) + 1
    sb = ttk.Scrollbar(container, orient="vertical", command=widget.yview)
    sb.grid(row=info["row"], column=col, rowspan=int(info.get("rowspan", 1)), sticky="ns")
    widget.configure(yscrollcommand=sb.set)
    return sb
