# -*- coding: utf-8 -*-
"""
Created on Sun Oct 20 11:32:41 2024

@author: Jacopo
"""

import pandas as pd
import os


data_ = [[],[], [], [], []]

def recovery_sheet(d_t, s, r, m_s, m_r): 
    data_[0].append(d_t), 
    data_[1].append(s), 
    data_[2].append(r), 
    data_[3].append(m_s),
    data_[4].append(m_r)
    
    data = {
        
        'DATE AND TIME': data_[0],
        'SENDER':data_[1],
        'RECIVER':data_[2],
        'MESSAGE SENDER':data_[3],
        'MESSAGE RECIVER':data_[4]
        }
    
    RECOVERY = pd.DataFrame(data)
    
    # Specificare la directory dove salvare il file
    directory = 'recovery'
    
    # Creare la directory se non esiste
    if not os.path.exists(directory):
        os.makedirs(directory)
    
    # Modificare la data e ora per renderla compatibile con i nomi di file su Windows
    sanitized_d_t = data_[0][0].replace(':', '-')
   
    # Creare il percorso completo del file
    filename = os.path.join(directory, f"{sanitized_d_t}_recovery.xlsx")
   
    # Salvare il DataFrame in un file Excel nella directory specificata
    RECOVERY.to_excel(filename, index=True, engine='openpyxl')
   
    print(f"File salvato come: {filename}")


