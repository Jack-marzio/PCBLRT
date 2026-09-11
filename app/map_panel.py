# -*- coding: utf-8 -*-
"""
map_panel.py
Scheda "Mappa" del Registro comunicazioni radio: mappa OpenStreetMap della
provincia di Varese su cui posizionare icone di operatori e ostacoli
(un mini-GIS), con elenco laterale gestibile e persistenza su file JSON.

Usa la libreria tkintermapview (tile OpenStreetMap, nessuna configurazione
di account/chiave richiesta). Richiede una connessione Internet per
scaricare i tile della mappa: se assente, la mappa resta vuota/grigia ma
il resto del pannello (elenco, aggiunta/rimozione) continua a funzionare
normalmente, dato che le coordinate vengono comunque salvate.
"""

import json
import os
import queue
import re
import threading
import uuid
from datetime import datetime
from tkinter import filedialog, messagebox, simpledialog, ttk
import tkinter as tk

from tkintermapview import TkinterMapView
from geopy.geocoders import Nominatim

from kml_import import KMLParseError, parse_kml
from ui_utils import COLOR_ACCENT, add_vscrollbar

# Provincia di Varese: centro approssimativo e zoom che la mostra per intero.
VARESE_CENTER = (45.82, 8.85)
VARESE_ZOOM = 11
# Riquadro approssimativo che copre la provincia (e un margine attorno): usato
# per dare priorità ai risultati di ricerca indirizzo locali (es. "Via Roma"
# esiste in decine di comuni: senza questo, Nominatim potrebbe restituirne
# uno lontano). Non esclude risultati fuori zona, li mette solo in secondo piano.
VARESE_VIEWBOX = [(46.25, 8.35), (45.55, 9.25)]

_COORDS_RE = re.compile(
    # "lat, lon" o "lat lon": decimali col punto (per non confonderlo con la
    # virgola usata come separatore tra le due coordinate). Es. "45.8206, 8.8250".
    r"^\s*(-?\d{1,3}(?:\.\d+)?)\s*[,;\s]\s*(-?\d{1,3}(?:\.\d+)?)\s*$"
)

# Stile dei marker puntuali (operatori/ostacoli inseriti a mano, punti KML importati)
MARKER_STYLES = {
    "operatore": {"circle": "#1565c0", "outside": "#0d47a1", "glyph": "\U0001F464"},  # 👤
    "ostacolo":  {"circle": "#c0392b", "outside": "#8e2419", "glyph": "⚠"},       # ⚠
    "kml_point": {"circle": "#2e7d32", "outside": "#1b5e20", "glyph": "\U0001F4CD"},  # 📍
}
# Stile delle geometrie lineari/areali importate da KML
LINE_STYLE    = {"color": "#2e7d32", "width": 4}
POLYGON_STYLE = {"outline_color": "#2e7d32", "fill_color": "#a5d6a7"}

# Tipi di elemento che sono un singolo punto (usano _draw_marker) contro
# quelli con più vertici (linee/aree, usano _draw_line/_draw_polygon).
POINT_TYPES = ("operatore", "ostacolo", "kml_point")


class GisMapPanel(tk.Frame):
    """
    Pannello mappa/GIS: mappa a sinistra, elenco marker gestibile a destra.

    Utilizzo::

        panel = GisMapPanel(parent, data_path="mappa_gis.json")
        panel.pack(fill="both", expand=True)
    """

    _TRANSLATIONS = {
        "it": {
            "mode_label"      : "Aggiungi:",
            "add_operator"    : "+ Operatore",
            "add_obstacle"    : "+ Ostacolo",
            "center_btn"      : "Centra su Varese",
            "hint_idle"       : "Scegli \"+ Operatore\" o \"+ Ostacolo\", poi clicca sulla mappa oppure cerca un indirizzo/coordinate per posizionarlo.",
            "hint_armed_op"   : "Clicca sulla mappa, oppure cerca un indirizzo/coordinate, per posizionare un operatore...",
            "hint_armed_obs"  : "Clicca sulla mappa, oppure cerca un indirizzo/coordinate, per posizionare un ostacolo...",
            "search_label"    : "Cerca via o coordinate GPS:",
            "search_placeholder": "es. Via Roma 1, Varese  —  oppure  45.8206, 8.8250",
            "search_btn"      : "Cerca",
            "searching"       : "Ricerca...",
            "search_not_found": "Nessun risultato per \"{}\".",
            "search_error"    : "Errore durante la ricerca (verifica la connessione Internet):\n{}",
            "ask_label_op"    : "Nome/nominativo dell'operatore:",
            "ask_label_obs"   : "Descrizione dell'ostacolo:",
            "ask_title"       : "Nuovo elemento",
            "list_header"     : "Elementi sulla mappa",
            "col_type"        : "Tipo",
            "col_label"       : "Etichetta",
            "col_coords"      : "Coordinate",
            "goto_btn"        : "Vai sulla mappa",
            "select_all_btn"  : "Seleziona tutto",
            "multiselect_hint": "Ctrl+clic o Maiusc+clic per selezionarne più di uno.",
            "remove_btn"      : "Rimuovi selezionati",
            "remove_confirm"  : "Rimuovere \"{}\"?",
            "remove_confirm_multi": "Rimuovere questi {} elementi?\n{}",
            "type_operator"   : "Operatore",
            "type_obstacle"   : "Ostacolo",
            "type_kml_point"  : "Punto (KML)",
            "type_kml_line"   : "Linea (KML)",
            "type_kml_polygon": "Area (KML)",
            "save_error"      : "Impossibile salvare la mappa: {}",
            "import_kml_btn"  : "Importa KML...",
            "import_kml_dialog_title": "Importa file KML/KMZ",
            "kml_import_error": "Impossibile leggere il file:\n{}",
            "kml_import_empty": "Nessun elemento geografico (punto/linea/area) trovato nel file.",
            "kml_import_summary": "Importati {} elementi da \"{}\":\n{} punti, {} linee, {} aree.",
        },
        "en": {
            "mode_label"      : "Add:",
            "add_operator"    : "+ Operator",
            "add_obstacle"    : "+ Obstacle",
            "center_btn"      : "Center on Varese",
            "hint_idle"       : "Choose \"+ Operator\" or \"+ Obstacle\", then click the map or search an address/coordinates to place it.",
            "hint_armed_op"   : "Click the map, or search an address/coordinates, to place an operator...",
            "hint_armed_obs"  : "Click the map, or search an address/coordinates, to place an obstacle...",
            "search_label"    : "Search address or GPS coordinates:",
            "search_placeholder": "e.g. 1 Main St, Varese  —  or  45.8206, 8.8250",
            "search_btn"      : "Search",
            "searching"       : "Searching...",
            "search_not_found": "No result for \"{}\".",
            "search_error"    : "Search error (check your Internet connection):\n{}",
            "ask_label_op"    : "Operator name/callsign:",
            "ask_label_obs"   : "Obstacle description:",
            "ask_title"       : "New item",
            "list_header"     : "Items on the map",
            "col_type"        : "Type",
            "col_label"       : "Label",
            "col_coords"      : "Coordinates",
            "goto_btn"        : "Go to on map",
            "select_all_btn"  : "Select all",
            "multiselect_hint": "Ctrl+click or Shift+click to select more than one.",
            "remove_btn"      : "Remove selected",
            "remove_confirm"  : "Remove \"{}\"?",
            "remove_confirm_multi": "Remove these {} items?\n{}",
            "type_operator"   : "Operator",
            "type_obstacle"   : "Obstacle",
            "type_kml_point"  : "Point (KML)",
            "type_kml_line"   : "Line (KML)",
            "type_kml_polygon": "Area (KML)",
            "save_error"      : "Could not save the map: {}",
            "import_kml_btn"  : "Import KML...",
            "import_kml_dialog_title": "Import KML/KMZ file",
            "kml_import_error": "Could not read the file:\n{}",
            "kml_import_empty": "No geographic elements (point/line/area) found in the file.",
            "kml_import_summary": "Imported {} items from \"{}\":\n{} points, {} lines, {} areas.",
        },
    }

    def __init__(self, parent: tk.Widget, data_path: str, lang: str = "it"):
        super().__init__(parent)
        self._data_path = data_path
        self._lang = lang
        self._add_mode: str | None = None   # None | "operatore" | "ostacolo"
        self._items: list[dict] = []        # record persistiti: id/type/label/lat/lon/created
        self._marker_by_id: dict[str, object] = {}
        self._item_by_tree_id: dict[str, str] = {}
        # Il geocoding gira in un thread separato per non bloccare la UI;
        # Tkinter non è thread-safe, quindi il thread deposita il risultato
        # qui e il thread principale lo preleva con il polling periodico
        # (stesso pattern già usato per i messaggi chat remoti).
        self._geocode_queue: queue.Queue = queue.Queue()

        self._build_ui()
        self._load_items()
        self._poll_geocode_queue()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        t = self._t()

        toolbar = tk.Frame(self)
        toolbar.pack(fill="x", padx=10, pady=(10, 5))

        tk.Label(toolbar, text=t["mode_label"], font=("Segoe UI", 10, "bold")).pack(side="left", padx=(0, 6))
        self._btn_add_operator = ttk.Button(
            toolbar, text=t["add_operator"], command=lambda: self._set_add_mode("operatore")
        )
        self._btn_add_operator.pack(side="left", padx=3)
        self._btn_add_obstacle = ttk.Button(
            toolbar, text=t["add_obstacle"], command=lambda: self._set_add_mode("ostacolo")
        )
        self._btn_add_obstacle.pack(side="left", padx=3)
        ttk.Button(toolbar, text=t["center_btn"], command=self._center_on_varese).pack(side="left", padx=(15, 3))
        self._btn_import_kml = ttk.Button(toolbar, text=t["import_kml_btn"], command=self._import_kml)
        self._btn_import_kml.pack(side="left", padx=3)

        search_bar = tk.Frame(self)
        search_bar.pack(fill="x", padx=10, pady=(0, 5))

        self._lbl_search = tk.Label(search_bar, text=t["search_label"])
        self._lbl_search.pack(side="left", padx=(0, 6))
        self._entry_search = ttk.Entry(search_bar)
        self._entry_search.pack(side="left", fill="x", expand=True)
        self._entry_search.bind("<Return>", self._on_search)
        self._entry_search.bind("<FocusIn>", self._clear_search_placeholder)
        self._entry_search.bind("<FocusOut>", self._restore_search_placeholder)
        self._show_search_placeholder()
        self._btn_search = ttk.Button(search_bar, text=t["search_btn"], command=self._on_search)
        self._btn_search.pack(side="left", padx=(6, 0))

        self._lbl_hint = tk.Label(toolbar, text=t["hint_idle"], fg="#555555", wraplength=500, justify="left")
        self._lbl_hint.pack(side="left", padx=15)

        body = tk.Frame(self)
        body.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        body.columnconfigure(0, weight=3)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)

        map_frame = tk.Frame(body, bd=1, relief="groove")
        map_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 5))
        self._map_widget = TkinterMapView(map_frame, corner_radius=0)
        self._map_widget.pack(fill="both", expand=True)
        self._map_widget.add_left_click_map_command(self._on_map_click)
        self._center_on_varese()

        self._build_list_panel(body)

    def _build_list_panel(self, parent: tk.Widget) -> None:
        t = self._t()
        frame = tk.Frame(parent, bd=1, relief="groove")
        frame.grid(row=0, column=1, sticky="nsew", padx=(5, 0))
        frame.rowconfigure(1, weight=1)
        frame.columnconfigure(0, weight=1)

        self._lbl_list_header = tk.Label(frame, text=t["list_header"], font=("Segoe UI", 11, "bold"))
        self._lbl_list_header.grid(row=0, column=0, sticky="w", padx=8, pady=(8, 2))

        columns = ("tipo", "etichetta", "coords")
        tree = ttk.Treeview(frame, columns=columns, show="headings", height=10)
        tree.heading("tipo", text=t["col_type"])
        tree.heading("etichetta", text=t["col_label"])
        tree.heading("coords", text=t["col_coords"])
        tree.column("tipo", width=80)
        tree.column("etichetta", width=140)
        tree.column("coords", width=130)
        tree.grid(row=1, column=0, sticky="nsew", padx=(8, 0), pady=(0, 5))
        tree.bind("<Double-1>", lambda e: self._goto_selected())
        # Selezione multipla di serie (Ctrl+clic / Maiusc+clic, come Esplora
        # File); Ctrl+A seleziona tutto per una rimozione di gruppo rapida.
        tree.bind("<Control-a>", lambda e: self._select_all())
        tree.bind("<Delete>", lambda e: self._remove_selected())
        add_vscrollbar(frame, tree)
        self._tree_items = tree

        self._lbl_multiselect_hint = tk.Label(
            frame, text=t["multiselect_hint"], font=("Segoe UI", 8), fg="#777777"
        )
        self._lbl_multiselect_hint.grid(row=2, column=0, sticky="w", padx=8)

        btns = tk.Frame(frame)
        btns.grid(row=3, column=0, pady=(2, 8))
        ttk.Button(btns, text=t["goto_btn"], command=self._goto_selected).pack(side="left", padx=4)
        self._btn_select_all = ttk.Button(btns, text=t["select_all_btn"], command=self._select_all)
        self._btn_select_all.pack(side="left", padx=4)
        self._btn_remove_selected = ttk.Button(btns, text=t["remove_btn"], command=self._remove_selected)
        self._btn_remove_selected.pack(side="left", padx=4)

    # ------------------------------------------------------------------
    # Modalità aggiunta / interazione mappa
    # ------------------------------------------------------------------

    def _set_add_mode(self, mode: str | None) -> None:
        t = self._t()
        self._add_mode = mode
        if mode == "operatore":
            self._lbl_hint.config(text=t["hint_armed_op"], fg=COLOR_ACCENT)
        elif mode == "ostacolo":
            self._lbl_hint.config(text=t["hint_armed_obs"], fg=MARKER_STYLES["ostacolo"]["circle"])
        else:
            self._lbl_hint.config(text=t["hint_idle"], fg="#555555")

    def _on_map_click(self, coords) -> None:
        if not self._add_mode:
            return
        lat, lon = coords
        self._prompt_and_add(self._add_mode, lat, lon)

    def _prompt_and_add(self, mode: str, lat: float, lon: float, initial_label: str = "") -> None:
        """Chiede l'etichetta e aggiunge un operatore/ostacolo in (lat, lon).
        Condivisa da click sulla mappa e da ricerca indirizzo/coordinate."""
        t = self._t()
        prompt = t["ask_label_op"] if mode == "operatore" else t["ask_label_obs"]
        label = simpledialog.askstring(t["ask_title"], prompt, initialvalue=initial_label, parent=self)
        self._set_add_mode(None)  # un solo posizionamento per "+"; evita aggiunte accidentali
        if not label:
            return
        self._add_item(mode, label.strip(), lat, lon)

    def _center_on_varese(self) -> None:
        self._map_widget.set_position(*VARESE_CENTER)
        self._map_widget.set_zoom(VARESE_ZOOM)

    # ------------------------------------------------------------------
    # Ricerca per indirizzo o coordinate GPS
    # ------------------------------------------------------------------

    @staticmethod
    def _try_parse_coords(text: str) -> tuple[float, float] | None:
        match = _COORDS_RE.match(text)
        if not match:
            return None
        lat, lon = float(match.group(1)), float(match.group(2))
        if -90 <= lat <= 90 and -180 <= lon <= 180:
            return lat, lon
        return None

    def _show_search_placeholder(self) -> None:
        self._entry_search.delete(0, tk.END)
        self._entry_search.insert(0, self._t()["search_placeholder"])
        self._entry_search.config(foreground="#999999")
        self._search_placeholder_shown = True

    def _clear_search_placeholder(self, _event=None) -> None:
        if getattr(self, "_search_placeholder_shown", False):
            self._entry_search.delete(0, tk.END)
            self._entry_search.config(foreground="black")
            self._search_placeholder_shown = False

    def _restore_search_placeholder(self, _event=None) -> None:
        if not self._entry_search.get().strip():
            self._show_search_placeholder()

    def _on_search(self, event=None) -> None:
        if getattr(self, "_search_placeholder_shown", False):
            return
        query = self._entry_search.get().strip()
        if not query:
            return

        coords = self._try_parse_coords(query)
        if coords is not None:
            self._handle_search_result(coords[0], coords[1], initial_label="")
            return

        # Non sono coordinate: prova come indirizzo, in un thread separato
        # per non bloccare l'interfaccia durante la richiesta di rete.
        t = self._t()
        self._btn_search.config(state="disabled", text=t["searching"])
        self._entry_search.config(state="disabled")
        threading.Thread(target=self._geocode_worker, args=(query,), daemon=True).start()

    def _geocode_worker(self, query: str) -> None:
        location = None
        error = None
        try:
            geolocator = Nominatim(user_agent="PCBLRT-RegistroComunicazioniRadio/1.0")
            location = geolocator.geocode(query, timeout=8, viewbox=VARESE_VIEWBOX, bounded=False)
        except Exception as e:
            error = str(e)
        # Chiamare .after()/metodi Tkinter da qui (thread in background) non è
        # sicuro: si deposita solo il risultato in coda, lo applica il thread
        # principale tramite _poll_geocode_queue().
        self._geocode_queue.put((query, location, error))

    def _poll_geocode_queue(self) -> None:
        try:
            while True:
                query, location, error = self._geocode_queue.get_nowait()
                self._on_geocode_done(query, location, error)
        except queue.Empty:
            pass
        self.after(150, self._poll_geocode_queue)

    def _on_geocode_done(self, query: str, location, error: str | None) -> None:
        t = self._t()
        self._btn_search.config(state="normal", text=t["search_btn"])
        self._entry_search.config(state="normal")

        if error is not None:
            messagebox.showerror(t["ask_title"], t["search_error"].format(error), parent=self)
            return
        if location is None:
            messagebox.showwarning(t["ask_title"], t["search_not_found"].format(query), parent=self)
            return

        self._handle_search_result(location.latitude, location.longitude, initial_label=location.address)

    def _handle_search_result(self, lat: float, lon: float, initial_label: str) -> None:
        """Centra la mappa sul risultato trovato e, se una modalità
        Operatore/Ostacolo è attiva, propone subito di posizionarlo lì."""
        self._map_widget.set_position(lat, lon)
        self._map_widget.set_zoom(16)
        if self._add_mode:
            self._prompt_and_add(self._add_mode, lat, lon, initial_label=initial_label)

    # ------------------------------------------------------------------
    # Import KML/KMZ
    # ------------------------------------------------------------------

    def _import_kml(self) -> None:
        t = self._t()
        path = filedialog.askopenfilename(
            title=t["import_kml_dialog_title"],
            filetypes=[("KML/KMZ", "*.kml *.kmz")],
            parent=self,
        )
        if not path:
            return
        try:
            features = parse_kml(path)
        except KMLParseError as e:
            messagebox.showerror(t["ask_title"], t["kml_import_error"].format(e), parent=self)
            return
        if not features:
            messagebox.showwarning(t["ask_title"], t["kml_import_empty"], parent=self)
            return

        counts = {"Point": 0, "LineString": 0, "Polygon": 0}
        for feature in features:
            geometry = feature["geometry"]
            counts[geometry] += 1
            if geometry == "Point":
                lat, lon = feature["coords"][0]
                self._add_item("kml_point", feature["name"], lat, lon, save=False)
            elif geometry == "LineString":
                self._add_geometry_item("kml_line", feature["name"], feature["coords"], save=False)
            elif geometry == "Polygon":
                self._add_geometry_item("kml_polygon", feature["name"], feature["coords"], save=False)
        self._save_items()

        messagebox.showinfo(
            t["ask_title"],
            t["kml_import_summary"].format(
                len(features), os.path.basename(path),
                counts["Point"], counts["LineString"], counts["Polygon"],
            ),
            parent=self,
        )

    # ------------------------------------------------------------------
    # CRUD elementi
    # ------------------------------------------------------------------

    def _add_item(self, item_type: str, label: str, lat: float, lon: float, save: bool = True) -> None:
        """Aggiunge un elemento puntuale (operatore/ostacolo/punto KML)."""
        record = {
            "id": uuid.uuid4().hex,
            "type": item_type,
            "label": label,
            "lat": lat,
            "lon": lon,
            "created": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        self._items.append(record)
        self._draw_item(record)
        self._refresh_tree()
        if save:
            self._save_items()

    def _add_geometry_item(self, item_type: str, label: str,
                           coords: list[tuple[float, float]], save: bool = True) -> None:
        """Aggiunge un elemento con più vertici (linea/area importata da KML)."""
        record = {
            "id": uuid.uuid4().hex,
            "type": item_type,
            "label": label,
            "coords": [list(c) for c in coords],
            "created": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        self._items.append(record)
        self._draw_item(record)
        self._refresh_tree()
        if save:
            self._save_items()

    def _draw_item(self, record: dict) -> None:
        """Smista il disegno sulla mappa in base al tipo di geometria."""
        item_type = record["type"]
        if item_type in POINT_TYPES:
            self._draw_marker(record)
        elif item_type == "kml_line":
            self._draw_line(record)
        elif item_type == "kml_polygon":
            self._draw_polygon(record)

    def _draw_marker(self, record: dict) -> None:
        style = MARKER_STYLES[record["type"]]
        marker = self._map_widget.set_marker(
            record["lat"], record["lon"],
            text=f"{style['glyph']} {record['label']}",
            marker_color_circle=style["circle"],
            marker_color_outside=style["outside"],
            command=lambda m, rec=record: self._on_item_click(rec),
        )
        self._marker_by_id[record["id"]] = marker

    def _draw_line(self, record: dict) -> None:
        path = self._map_widget.set_path(
            [tuple(c) for c in record["coords"]],
            color=LINE_STYLE["color"], width=LINE_STYLE["width"],
            name=record["label"],
            command=lambda p, rec=record: self._on_item_click(rec),
        )
        self._marker_by_id[record["id"]] = path

    def _draw_polygon(self, record: dict) -> None:
        polygon = self._map_widget.set_polygon(
            [tuple(c) for c in record["coords"]],
            outline_color=POLYGON_STYLE["outline_color"], fill_color=POLYGON_STYLE["fill_color"],
            name=record["label"],
            command=lambda p, rec=record: self._on_item_click(rec),
        )
        self._marker_by_id[record["id"]] = polygon

    def _on_item_click(self, record: dict) -> None:
        t = self._t()
        if messagebox.askyesno(t["ask_title"], t["remove_confirm"].format(record["label"]), parent=self):
            self._remove_item(record["id"])

    def _remove_items(self, item_ids: list[str]) -> None:
        """Rimuove uno o più elementi in un colpo solo: un solo refresh
        dell'elenco e un solo salvataggio su file, anche per una rimozione
        di gruppo (invece di ripeterli per ciascun elemento)."""
        ids_set = set(item_ids)
        for item_id in ids_set:
            marker = self._marker_by_id.pop(item_id, None)
            if marker is not None:
                marker.delete()
        self._items = [r for r in self._items if r["id"] not in ids_set]
        self._refresh_tree()
        self._save_items()

    def _remove_item(self, item_id: str) -> None:
        self._remove_items([item_id])

    def _remove_selected(self) -> None:
        """
        Rimuove tutti gli elementi selezionati nell'elenco (non solo il
        primo): il Treeview supporta già la selezione multipla con
        Ctrl+clic o Maiusc+clic, oppure "Seleziona tutto".
        """
        sel = self._tree_items.selection()
        if not sel:
            return
        records = []
        for tree_id in sel:
            item_id = self._item_by_tree_id.get(tree_id)
            record = next((r for r in self._items if r["id"] == item_id), None)
            if record:
                records.append(record)
        if not records:
            return

        t = self._t()
        if len(records) == 1:
            message = t["remove_confirm"].format(records[0]["label"])
        else:
            preview = ", ".join(r["label"] for r in records[:5])
            if len(records) > 5:
                preview += ", ..."
            message = t["remove_confirm_multi"].format(len(records), preview)

        if messagebox.askyesno(t["ask_title"], message, parent=self):
            self._remove_items([r["id"] for r in records])

    def _select_all(self) -> None:
        self._tree_items.selection_set(self._tree_items.get_children())

    def _goto_selected(self) -> None:
        sel = self._tree_items.selection()
        if not sel:
            return
        item_id = self._item_by_tree_id.get(sel[0])
        record = next((r for r in self._items if r["id"] == item_id), None)
        if not record:
            return
        if "coords" in record:
            lat = sum(c[0] for c in record["coords"]) / len(record["coords"])
            lon = sum(c[1] for c in record["coords"]) / len(record["coords"])
            self._map_widget.set_position(lat, lon)
            self._map_widget.set_zoom(13)
        else:
            self._map_widget.set_position(record["lat"], record["lon"])
            self._map_widget.set_zoom(15)

    def _refresh_tree(self) -> None:
        t = self._t()
        self._tree_items.delete(*self._tree_items.get_children())
        self._item_by_tree_id = {}
        type_label = {
            "operatore": t["type_operator"], "ostacolo": t["type_obstacle"],
            "kml_point": t["type_kml_point"], "kml_line": t["type_kml_line"],
            "kml_polygon": t["type_kml_polygon"],
        }
        for record in self._items:
            if "coords" in record:
                coords_text = f"({len(record['coords'])} vertici)"
            else:
                coords_text = f"{record['lat']:.5f}, {record['lon']:.5f}"
            tree_id = self._tree_items.insert("", tk.END, values=(
                type_label.get(record["type"], record["type"]),
                record["label"],
                coords_text,
            ))
            self._item_by_tree_id[tree_id] = record["id"]

    # ------------------------------------------------------------------
    # Persistenza
    # ------------------------------------------------------------------

    def _load_items(self) -> None:
        if not os.path.exists(self._data_path):
            return
        try:
            with open(self._data_path, "r", encoding="utf-8") as f:
                items = json.load(f)
        except Exception:
            return  # file assente/corrotto: si parte da una mappa vuota
        for record in items:
            self._items.append(record)
            self._draw_item(record)
        self._refresh_tree()

    def _save_items(self) -> None:
        try:
            parent_dir = os.path.dirname(os.path.abspath(self._data_path))
            if parent_dir:
                os.makedirs(parent_dir, exist_ok=True)
            with open(self._data_path, "w", encoding="utf-8") as f:
                json.dump(self._items, f, ensure_ascii=False, indent=2)
        except Exception as e:
            messagebox.showerror(self._t()["ask_title"], self._t()["save_error"].format(e), parent=self)

    # ------------------------------------------------------------------
    # Lingua
    # ------------------------------------------------------------------

    def set_language(self, lang: str) -> None:
        self._lang = lang
        t = self._t()
        self._btn_add_operator.config(text=t["add_operator"])
        self._btn_add_obstacle.config(text=t["add_obstacle"])
        self._btn_import_kml.config(text=t["import_kml_btn"])
        self._lbl_search.config(text=t["search_label"])
        self._btn_search.config(text=t["search_btn"])
        if getattr(self, "_search_placeholder_shown", False):
            self._show_search_placeholder()
        self._set_add_mode(None)
        self._lbl_list_header.config(text=t["list_header"])
        self._lbl_multiselect_hint.config(text=t["multiselect_hint"])
        self._btn_select_all.config(text=t["select_all_btn"])
        self._btn_remove_selected.config(text=t["remove_btn"])
        self._tree_items.heading("tipo", text=t["col_type"])
        self._tree_items.heading("etichetta", text=t["col_label"])
        self._tree_items.heading("coords", text=t["col_coords"])
        self._refresh_tree()

    def _t(self) -> dict:
        return self._TRANSLATIONS[self._lang]
