# -*- coding: utf-8 -*-
"""
Created on Sat Nov 16 12:30:18 2024

@author: Jacopo
"""




#%% Global parameters:
    
def leggi_config(file_path):
    config = {}

    with open(file_path, 'r', encoding='utf-8') as f:
        for riga in f:
            riga = riga.strip()

            # Salta righe vuote
            if not riga:
                continue

            # Divide chiave e valore
            chiave, valore = riga.split("=", 1)
            chiave = chiave.strip()
            valore = valore.strip()

            # Gestione liste tipo [a, b, c]
            if valore.startswith("[") and valore.endswith("]"):
                valore = valore[1:-1]  # rimuove []
                elementi = [v.strip() for v in valore.split(",")]
                config[chiave] = elementi
            else:
                config[chiave] = valore

    return config
global_parameters_dict = leggi_config('configurator.txt')


