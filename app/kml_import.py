# -*- coding: utf-8 -*-
"""
kml_import.py
Lettura di file KML/KMZ (Google Earth / GIS) per estrarne gli elementi
geografici: punti, linee e aree (poligoni).

Usa solo la libreria standard (xml.etree, zipfile): niente dipendenze
aggiuntive per un formato che è, in fondo, solo XML.

Limiti noti (scelta deliberata per restare semplice):
  - i poligoni con "buchi" (inner boundaries) vengono importati come il
    solo perimetro esterno, il buco viene ignorato;
  - lo stile/colore definito nel KML (<Style>, <LineStyle>, <PolyStyle>)
    non viene letto: gli elementi importati usano lo stile standard
    dell'app in base al tipo di geometria;
  - MultiGeometry viene "appiattita": ogni geometria contenuta diventa un
    elemento separato con lo stesso nome del Placemark.
"""

import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path


class KMLParseError(Exception):
    pass


def _local(tag: str) -> str:
    """Nome del tag senza namespace, es. '{...}Placemark' → 'Placemark'."""
    return tag.rsplit("}", 1)[-1]


def _find_child(elem, name: str):
    for child in elem:
        if _local(child.tag) == name:
            return child
    return None


def _find_all(elem, name: str):
    return [child for child in elem.iter() if _local(child.tag) == name]


def _parse_coordinates(text: str) -> list[tuple[float, float]]:
    """
    Converte il testo di un tag <coordinates> KML ("lon,lat[,alt] ...") in
    una lista di tuple (lat, lon) — in KML la longitudine viene sempre
    prima, l'opposto della convenzione (lat, lon) usata nel resto dell'app.
    """
    points = []
    for token in text.split():
        parts = token.split(",")
        if len(parts) < 2:
            continue
        lon, lat = float(parts[0]), float(parts[1])
        points.append((lat, lon))
    return points


def _extract_geometries(placemark) -> list[dict]:
    """Estrae tutte le geometrie (Point/LineString/Polygon) di un Placemark."""
    geometries = []

    for point in _find_all(placemark, "Point"):
        coords_el = _find_child(point, "coordinates")
        if coords_el is not None and coords_el.text:
            pts = _parse_coordinates(coords_el.text)
            if pts:
                geometries.append({"geometry": "Point", "coords": [pts[0]]})

    for line in _find_all(placemark, "LineString"):
        coords_el = _find_child(line, "coordinates")
        if coords_el is not None and coords_el.text:
            pts = _parse_coordinates(coords_el.text)
            if len(pts) >= 2:
                geometries.append({"geometry": "LineString", "coords": pts})

    for polygon in _find_all(placemark, "Polygon"):
        outer = _find_child(polygon, "outerBoundaryIs")
        if outer is None:
            continue
        ring = _find_child(outer, "LinearRing")
        if ring is None:
            continue
        coords_el = _find_child(ring, "coordinates")
        if coords_el is not None and coords_el.text:
            pts = _parse_coordinates(coords_el.text)
            if len(pts) >= 3:
                geometries.append({"geometry": "Polygon", "coords": pts})

    return geometries


def parse_kml(file_path: str) -> list[dict]:
    """
    Legge un file .kml o .kmz e restituisce una lista di elementi:
    [{"name": str, "geometry": "Point"|"LineString"|"Polygon",
      "coords": [(lat, lon), ...]}, ...]

    Solleva KMLParseError con un messaggio comprensibile se il file non è
    un KML/KMZ valido.
    """
    path = Path(file_path)
    try:
        if path.suffix.lower() == ".kmz":
            with zipfile.ZipFile(path) as zf:
                kml_names = [n for n in zf.namelist() if n.lower().endswith(".kml")]
                if not kml_names:
                    raise KMLParseError("Il file .kmz non contiene nessun documento .kml al suo interno.")
                # Preferisce "doc.kml" (nome convenzionale usato da Google Earth) se presente
                kml_names.sort(key=lambda n: (Path(n).name.lower() != "doc.kml", n))
                content = zf.read(kml_names[0])
        else:
            content = path.read_bytes()

        root = ET.fromstring(content)
    except KMLParseError:
        raise
    except (ET.ParseError, zipfile.BadZipFile) as e:
        raise KMLParseError(f"File non leggibile come KML/KMZ: {e}") from e
    except OSError as e:
        raise KMLParseError(f"Impossibile aprire il file: {e}") from e

    items = []
    for i, placemark in enumerate(_find_all(root, "Placemark"), start=1):
        name_el = _find_child(placemark, "name")
        name = (name_el.text or "").strip() if name_el is not None else ""
        if not name:
            name = f"Elemento importato {i}"

        for geo in _extract_geometries(placemark):
            items.append({"name": name, "geometry": geo["geometry"], "coords": geo["coords"]})

    return items
