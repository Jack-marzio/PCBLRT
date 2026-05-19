# -*- coding: utf-8 -*-
"""
recovery_manager.py
Gestione del salvataggio e ripristino dei dati di sessione (recovery).
"""

import os
from datetime import datetime

import openpyxl
import pandas as pd
from tkinter import messagebox


class RecoveryManager:
    """
    Salva ogni comunicazione in un foglio Excel di recovery
    e, all'avvio, propone all'utente di ripristinare l'ultima sessione.
    """

    RECOVERY_DIR   = "recovery"
    COLUMNS        = ["DATE AND TIME", "SENDER", "RECEIVER", "MESSAGE SENDER", "MESSAGE RECEIVER"]

    def __init__(self):
        self._rows: list[tuple] = []
        self._filename: str | None = None

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def append(self, date_time: str, sender: str, receiver: str,
               msg_sent: str, msg_received: str) -> None:
        """Aggiunge una riga e sovrascrive il file di recovery."""
        self._rows.append((date_time, sender, receiver, msg_sent, msg_received))
        self._save()

    def load_latest(self) -> list[tuple] | None:
        """
        Cerca il file di recovery più recente nella cartella di lavoro.
        Se è di oggi chiede all'utente se vuole ripristinarlo.
        Restituisce la lista di tuple oppure None.
        """
        recovery_dir = os.path.join(os.getcwd(), self.RECOVERY_DIR)
        if not os.path.exists(recovery_dir):
            return None

        files = [
            os.path.join(recovery_dir, f)
            for f in os.listdir(recovery_dir)
            if f.endswith(".xlsx")
        ]
        if not files:
            return None

        latest = max(files, key=os.path.getmtime)
        file_date = datetime.fromtimestamp(os.path.getmtime(latest)).date()

        if file_date != datetime.today().date():
            return None

        confirm = messagebox.askyesno(
            "Ripristina dati",
            f"Trovato file di recovery:\n{latest}\nVuoi ripristinarlo?"
        )
        if not confirm:
            return None

        return self._read_xlsx(latest)

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    def _save(self) -> None:
        os.makedirs(self.RECOVERY_DIR, exist_ok=True)
        if self._filename is None:
            sanitized = self._rows[0][0].replace(":", "-")
            self._filename = os.path.join(
                self.RECOVERY_DIR, f"{sanitized}_recovery.xlsx"
            )

        data = {col: [r[i] for r in self._rows]
                for i, col in enumerate(self.COLUMNS)}
        pd.DataFrame(data).to_excel(self._filename, index=False, engine="openpyxl")
        print(f"Recovery salvato: {self._filename}")

    @staticmethod
    def _read_xlsx(path: str) -> list[tuple]:
        rows = []
        wb = openpyxl.load_workbook(path)
        ws = wb.active
        for row in ws.iter_rows(min_row=2, values_only=True):
            rows.append(row)
        wb.close()
        return rows
