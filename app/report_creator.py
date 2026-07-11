# -*- coding: utf-8 -*-
"""
report_creator.py
Creazione di report PDF e XLSX per il log delle comunicazioni radio
e per la chat. Ogni report viene salvato sia nella directory scelta
dall'utente sia in una cartella di backup locale fissa accanto all'app
(così una copia resta sempre disponibile in locale, indipendentemente
da dove è stata scelta la destinazione principale: Drive, esterna, ecc.).
"""

import os
import re
import textwrap
from datetime import datetime

from fpdf import FPDF
from openpyxl import Workbook
from openpyxl.drawing.image import Image as XLImage
from openpyxl.styles import Alignment, Font


class ReportCreator:
    """
    Crea report PDF e XLSX a partire dal log delle comunicazioni radio
    e dalla cronologia della chat. Fornisce anche metodi di utilità per
    contare file esistenti e gestire il salvataggio multi-destinazione.
    """

    # Cartella di backup locale, sempre accanto all'app — indipendente
    # dalla directory scelta dall'utente (Drive/Locale/Esterna) in avvio.
    LOCAL_BACKUP_DIR = "report_locale"

    # ------------------------------------------------------------------
    # Static / class helpers
    # ------------------------------------------------------------------

    @staticmethod
    def count_files(directory: str, extension: str, prefix: str = "") -> int:
        """
        Conta i file con una data estensione (ed eventuale prefisso nel nome)
        nella directory e restituisce il prossimo indice progressivo.
        """
        try:
            files = [
                f for f in os.listdir(directory)
                if f.endswith(extension) and f.startswith(prefix)
            ]
            return len(files) + 1
        except FileNotFoundError:
            print(f"Directory '{directory}' non trovata.")
            return 1

    @staticmethod
    def sanitize_filename(name: str) -> str:
        """Rimuove i caratteri non validi dal nome del file."""
        return re.sub(r'[<>:"/\\|?*]', "", name)

    @staticmethod
    def make_directory(directory: str) -> str | None:
        """Crea la directory se non esiste. Restituisce il percorso o None in caso di errore."""
        if not os.path.exists(directory):
            try:
                os.makedirs(directory)
                print(f"Directory creata: {directory}")
            except OSError as e:
                print(f"Errore creazione directory {directory}: {e}")
                return None
        return directory

    @staticmethod
    def local_backup_dir() -> str:
        """
        Restituisce (creandola se necessario) la cartella di backup locale
        fissa, accanto all'eseguibile/script. Ogni report viene sempre
        salvato anche qui, oltre che nella directory scelta dall'utente.
        """
        path = os.path.join(os.getcwd(), ReportCreator.LOCAL_BACKUP_DIR)
        os.makedirs(path, exist_ok=True)
        return path

    @classmethod
    def _destination_dirs(cls, primary_directory: str) -> list:
        """
        Restituisce l'elenco delle directory in cui salvare un report:
        la directory scelta dall'utente + il backup locale fisso,
        senza duplicati se coincidono.
        """
        primary = os.path.abspath(primary_directory)
        local   = os.path.abspath(cls.local_backup_dir())
        dirs    = [primary]
        if os.path.normcase(local) != os.path.normcase(primary):
            dirs.append(local)
        return dirs

    # ------------------------------------------------------------------
    # PDF — log comunicazioni radio
    # ------------------------------------------------------------------

    def create_pdf(self, operator: str, event: str, login_datetime: str,
                   communication_log: list, directory: str,
                   n_files: int, logo_path: str) -> str:
        """
        Genera il report PDF del log comunicazioni e lo salva sia nella
        directory indicata sia nel backup locale fisso.
        Restituisce il percorso del file nella directory indicata.
        """
        headers    = ["Data/Time", "Mittente", "Ricevente",
                      "Messaggio ricevuto", "Messaggio trasmesso"]
        col_widths = [35, 30, 30, 90, 90]
        align_from = 3  # colonne >= questo indice allineate a sinistra

        title = (
            f"Rapporto registrazione comunicazioni radio "
            f"n° {n_files}/{login_datetime[:4]}"
        )
        file_name = (
            f"rapporto_comunicazioni_radio_"
            f"{self.sanitize_filename(operator)}_{n_files}_{login_datetime[:4]}.pdf"
        )

        pdf = self._build_table_pdf(
            title, operator, event, logo_path,
            headers, col_widths, communication_log, align_from
        )
        return self._save_pdf_multi(pdf, directory, file_name)

    # ------------------------------------------------------------------
    # PDF — chat
    # ------------------------------------------------------------------

    def create_chat_pdf(self, operator: str, event: str, login_datetime: str,
                        chat_log: list, directory: str,
                        n_files: int, logo_path: str) -> str:
        """
        Genera il report PDF della chat e lo salva sia nella directory
        indicata sia nel backup locale fisso.
        Ogni voce di chat_log è una tupla (date_time, sender, origin, text).
        Restituisce il percorso del file nella directory indicata.
        """
        headers    = ["Data/Ora", "Mittente", "Origine", "Messaggio"]
        col_widths = [35, 45, 30, 165]
        align_from = 3

        # Rende "locale"/"remoto" più leggibili nel report
        rows = [
            (dt, sender, "Operatore (locale)" if origin == "locale" else "Remoto", text)
            for dt, sender, origin, text in chat_log
        ]

        title = (
            f"Rapporto chat n° {n_files}/{login_datetime[:4]}"
        )
        file_name = (
            f"rapporto_chat_"
            f"{self.sanitize_filename(operator)}_{n_files}_{login_datetime[:4]}.pdf"
        )

        pdf = self._build_table_pdf(
            title, operator, event, logo_path,
            headers, col_widths, rows, align_from
        )
        return self._save_pdf_multi(pdf, directory, file_name)

    # ------------------------------------------------------------------
    # PDF — helpers condivisi
    # ------------------------------------------------------------------

    @staticmethod
    def _build_table_pdf(title: str, operator: str, event: str, logo_path: str,
                         headers: list, col_widths: list, rows: list,
                         align_from: int) -> FPDF:
        """Costruisce un documento PDF tabellare (log o chat) pronto per il salvataggio."""

        class _PDF(FPDF):
            HEADERS    = headers
            COL_WIDTHS = col_widths

            def header(self):
                if hasattr(self, "logo_path") and os.path.exists(self.logo_path):
                    self.image(self.logo_path, 10, 8, 25)
                self.set_font("Arial", "B", 16)
                self.set_xy(0, 15)
                self.cell(0, 10, self.title_report, border=0, ln=True, align="C")
                self.ln(10)
                self.set_font("Arial", "", 10)
                self.cell(0, 6, f"Operatore: {self.operator}", ln=True)
                self.cell(0, 6, f"Evento: {self.event}", ln=True)
                self.ln(5)
                self._draw_table_header()

            def footer(self):
                self.set_y(-12)
                self.set_font("Arial", "I", 8)
                self.cell(0, 5, f"Pagina {self.page_no()}", align="C")

            def _draw_table_header(self):
                self.set_font("Arial", "B", 9)
                self.set_fill_color(230, 230, 230)
                for w, h in zip(self.COL_WIDTHS, self.HEADERS):
                    self.cell(w, 8, h, border=1, align="C", fill=True)
                self.ln()

        pdf = _PDF(orientation="L")
        pdf.logo_path    = logo_path
        pdf.operator     = operator
        pdf.event        = event
        pdf.title_report = title
        pdf.add_page()
        pdf.set_font("Arial", "", 9)

        line_height = 5

        for entry in rows:
            row = ["\n".join(textwrap.wrap(str(x), 40)) for x in entry]
            max_lines  = max(r.count("\n") + 1 for r in row)
            row_height = line_height * max_lines

            if pdf.get_y() + row_height > pdf.page_break_trigger:
                pdf.add_page()

            x_start = pdf.get_x()
            y_start = pdf.get_y()
            for i, (cell_text, w) in enumerate(zip(row, col_widths)):
                pdf.set_xy(x_start, y_start)
                pdf.multi_cell(w, line_height, cell_text,
                               border=1, align="C" if i < align_from else "L")
                x_start += w
            pdf.set_y(y_start + row_height)

        return pdf

    @classmethod
    def _save_pdf_multi(cls, pdf: FPDF, primary_directory: str, file_name: str) -> str:
        """
        Salva il PDF già costruito in tutte le destinazioni previste
        (directory scelta + backup locale). Restituisce il percorso
        nella directory principale.
        """
        primary_path = os.path.join(primary_directory, file_name)
        for dest_dir in cls._destination_dirs(primary_directory):
            cls.make_directory(dest_dir)
            path = os.path.join(dest_dir, file_name)
            try:
                pdf.output(path)
                print(f"PDF salvato: {path}")
            except Exception as e:
                print(f"Errore salvataggio PDF in {dest_dir}: {e}")
        return primary_path

    # ------------------------------------------------------------------
    # XLSX — log comunicazioni radio
    # ------------------------------------------------------------------

    def create_xlsx(self, operator: str, event: str, login_datetime: str,
                    communication_log: list, directory: str,
                    n_files: int, logo_path: str) -> str:
        """
        Genera il report XLSX del log comunicazioni e lo salva sia nella
        directory indicata sia nel backup locale fisso.
        Restituisce il percorso del file nella directory indicata.
        """
        headers = ["Data/Ora", "Mittente", "Ricevente",
                   "Messaggio ricevuto", "Messaggio trasmesso"]
        file_name = (
            f"rapporto_comunicazioni_radio_"
            f"{self.sanitize_filename(operator)}_{n_files}_{login_datetime[:4]}.xlsx"
        )
        wb = self._build_table_xlsx(
            operator, event, login_datetime, n_files, logo_path,
            headers, communication_log
        )
        return self._save_xlsx_multi(wb, directory, file_name)

    # ------------------------------------------------------------------
    # XLSX — chat
    # ------------------------------------------------------------------

    def create_chat_xlsx(self, operator: str, event: str, login_datetime: str,
                         chat_log: list, directory: str,
                         n_files: int, logo_path: str) -> str:
        """
        Genera il report XLSX della chat e lo salva sia nella directory
        indicata sia nel backup locale fisso.
        Ogni voce di chat_log è una tupla (date_time, sender, origin, text).
        Restituisce il percorso del file nella directory indicata.
        """
        headers = ["Data/Ora", "Mittente", "Origine", "Messaggio"]
        rows = [
            (dt, sender, "Operatore (locale)" if origin == "locale" else "Remoto", text)
            for dt, sender, origin, text in chat_log
        ]
        file_name = (
            f"rapporto_chat_"
            f"{self.sanitize_filename(operator)}_{n_files}_{login_datetime[:4]}.xlsx"
        )
        wb = self._build_table_xlsx(
            operator, event, login_datetime, n_files, logo_path,
            headers, rows
        )
        return self._save_xlsx_multi(wb, directory, file_name)

    # ------------------------------------------------------------------
    # XLSX — helpers condivisi
    # ------------------------------------------------------------------

    @staticmethod
    def _build_table_xlsx(operator: str, event: str, login_datetime: str,
                          n_files: int, logo_path: str,
                          headers: list, rows: list) -> Workbook:
        """Costruisce un Workbook tabellare (log o chat) pronto per il salvataggio."""
        IMG_W, IMG_H = 150, 150
        TEXT_SIZE    = 12

        wb = Workbook()
        ws = wb.active

        try:
            img = XLImage(logo_path)
            img.width, img.height = IMG_W, IMG_H
            ws.add_image(img, "A3")
        except Exception as e:
            print(f"Impossibile inserire il logo nel XLSX: {e}")

        ws.append([operator, event, login_datetime, n_files])
        ws.append(headers)

        for col in range(1, len(headers) + 1):
            cell = ws.cell(row=3, column=col)
            cell.font      = Font(bold=True, size=TEXT_SIZE)
            cell.alignment = Alignment(horizontal="center")

        max_lengths = [len(h) for h in headers]
        for entry in rows:
            row_data = list(entry)
            for i, value in enumerate(row_data):
                max_lengths[i] = max(max_lengths[i], len(str(value)))
            ws.append(row_data)

        max_width = 20
        for i, length in enumerate(max_lengths, start=1):
            col_letter = ws.cell(row=1, column=i).column_letter
            if length > max_width:
                ws.column_dimensions[col_letter].width = max_width
                for row in ws.iter_rows(min_col=i, max_col=i):
                    for cell in row:
                        cell.alignment = Alignment(wrap_text=True)
            else:
                ws.column_dimensions[col_letter].width = length + 2

        return wb

    @classmethod
    def _save_xlsx_multi(cls, wb: Workbook, primary_directory: str, file_name: str) -> str:
        """
        Salva il Workbook già costruito in tutte le destinazioni previste
        (directory scelta + backup locale). Restituisce il percorso
        nella directory principale.
        """
        primary_path = os.path.join(primary_directory, file_name)
        for dest_dir in cls._destination_dirs(primary_directory):
            cls.make_directory(dest_dir)
            path = os.path.join(dest_dir, file_name)
            try:
                wb.save(path)
                print(f"XLSX salvato: {path}")
            except Exception as e:
                print(f"Errore salvataggio XLSX in {dest_dir}: {e}")
        return primary_path
