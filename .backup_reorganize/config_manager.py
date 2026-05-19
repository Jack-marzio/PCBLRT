# -*- coding: utf-8 -*-
"""
config_manager.py
Gestione della configurazione dell'applicazione.
"""


class ConfigManager:
    """
    Legge e fornisce i parametri globali dell'applicazione
    dal file di configurazione testuale.
    """

    def __init__(self, file_path: str = "configurator.txt"):
        self._file_path = file_path
        self._config: dict = {}
        self._load()

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    def _load(self) -> None:
        """Legge il file di configurazione e popola il dizionario interno."""
        with open(self._file_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key   = key.strip()
                value = value.strip()
                if value.startswith("[") and value.endswith("]"):
                    value = [v.strip() for v in value[1:-1].split(",")]
                self._config[key] = value

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def get(self, key: str, default=None):
        """Restituisce il valore di un parametro di configurazione."""
        return self._config.get(key, default)

    def __getitem__(self, key: str):
        return self._config[key]