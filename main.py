# -*- coding: utf-8 -*-
"""
Created on Fri Oct 11 19:25:52 2024

@author: Jacopo

FW : 1.1
"""

#%% MANAGE LIBRARIES:
    
from datetime import datetime
from log_interface import radio_log_interface, show_splash_screen
from pdf_creator import count_pdfs_in_directory, make_directory
from directory_selection import select_directory  # Importa la funzione
    
#%% SETUP:
    
# Registriamo la data e l'ora attuali
data_ora_login = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

log_comunicazioni = []
show_splash_screen()

#%% DIRECTORY SELECTION:
    
# Chiama la funzione per selezionare la directory
selected_directory = select_directory()
if not selected_directory:
    print("Directory non selezionata. Uscita dal programma.")
    exit()

#%% LOG BEGIN:
 
# Inizio del log delle comunicazioni radio
n_protocol = count_pdfs_in_directory(selected_directory)
# print("Inizia a registrare le comunicazioni radio (scrivi 'fine' per terminare).")
data_ora_main =  datetime.now().strftime("%Y-%m-%d %H:%M:%S")
radio_log_interface(
    data_ora_main, 
    log_comunicazioni, 
    selected_directory, 
    n_protocol, 
    logo_path='logoPICCOLOSENZASFONDO.png', 
    program_title="Radio Communication Log"
)