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

import tkinter as tk
from tkinter import ttk


def adaptive_geometry(
    root: tk.Tk,
    desired_w: int,
    desired_h: int,
    min_w: int = 800,
    min_h: int = 500,
    screen_margin_w: float = 0.95,
    screen_margin_h: float = 0.90,
) -> None:
    """
    Imposta geometry e minsize di 'root' in modo che la finestra non superi
    mai la risoluzione reale dello schermo (con un margine di sicurezza per
    barra del titolo/taskbar del sistema operativo), centrandola.

    Su schermi grandi si comporta come una geometry fissa (usa desired_w x
    desired_h). Su schermi piccoli riduce automaticamente le dimensioni
    invece di lasciare la finestra più grande dello schermo.
    """
    root.update_idletasks()
    screen_w = root.winfo_screenwidth()
    screen_h = root.winfo_screenheight()

    max_w = int(screen_w * screen_margin_w)
    max_h = int(screen_h * screen_margin_h)

    w = min(desired_w, max_w)
    h = min(desired_h, max_h)

    eff_min_w = min(min_w, screen_w)
    eff_min_h = min(min_h, screen_h)
    w = max(w, eff_min_w)
    h = max(h, eff_min_h)

    x = max(0, (screen_w - w) // 2)
    y = max(0, (screen_h - h) // 2)

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
