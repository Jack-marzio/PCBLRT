# -*- coding: utf-8 -*-
"""
Created on Fri Oct 11 19:25:52 2024

@author: Jacopo

"""

#%% MANAGE LIBRARIES:
    

import sys
from datetime import datetime
from log_interface import radio_log_interface, show_splash_screen
from pdf_creator import count_pdfs_in_directory, make_directory
from directory_selection import select_directory
from sys_param import global_parameters_dict
    
#%% SETUP:
    
FW = global_parameters_dict['Firmware_version']
dirve_path = global_parameters_dict['Drive_path']
data_ora_login = global_parameters_dict['Data_hour_login']
logo_path = global_parameters_dict['Logo_path']
program_title = global_parameters_dict['Program_title']
flag_list = global_parameters_dict['Flags_logo']

log_comunicazioni = []

#%% START UP:

show_splash_screen(FW, logo_path)

#%% DIRECTORY SELECTION:
    
selected_directory = select_directory(logo_path, flag_list)

if not selected_directory:
    print("Directory non selezionata. Uscita dal programma.")
    exit_program = sys.exit()

#%% LOG BEGIN:
 

n_protocol = count_pdfs_in_directory(selected_directory)

radio_log_interface(
    data_ora_login, 
    log_comunicazioni, 
    selected_directory, 
    n_protocol, 
    logo_path, 
    flag_list,
    program_title
)