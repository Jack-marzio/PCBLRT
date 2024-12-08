# -*- coding: utf-8 -*-
"""
Created on Fri Oct 11 19:42:02 2024

@author: Jacopo
"""
import os
from fpdf import FPDF
from datetime import datetime
import re 


year = datetime.now().strftime("%Y")

def make_directory(directory):
    """
    Check and create the directory if it doesn't exist.

    Args:
        directory (str): The directory path to check or create.

    Returns:
        str: The directory path if it was created or already exists.
        None: In case of an error during directory creation.
    """
    # Check and create directory if it doesn't exist
    if not os.path.exists(directory):
        try:
            os.makedirs(directory)
            print(f"Directory created: {directory}")
        except OSError as e:
            print(f"Error creating directory {directory}: {e}")
            return None
    else:
        print(f"Directory already exists: {directory}")
    
    return directory
    

def count_pdfs_in_directory(directory):
    """
    Counts the number of PDF files in the specified directory.

    Args:
        directory (str): The directory in which to count PDF files.

    Returns:
        int: The number of PDF files in the directory.
    """
    try:
        # List all files in the directory
        files = os.listdir(directory)
        
        # Filter and count files that end with .pdf
        pdf_files = [file for file in files if file.endswith('.pdf')]
        return len(pdf_files) + 1
    
    except FileNotFoundError:
        print(f"Directory '{directory}' not found.")
        return 0



def sanitize_filename(filename):
    """
    Rimuove i caratteri non validi dal nome del file per evitare errori di salvataggio.
    
    Args:
        filename (str): Il nome del file da pulire.
    
    Returns:
        str: Il nome del file ripulito dai caratteri non validi.
    """
    return re.sub(r'[<>:"/\\|?*]', '', filename)

def truncate_text(text, max_length):
    """
    Troncatura del testo se supera una certa lunghezza massima.

    Args:
        text (str): Il testo da controllare.
        max_length (int): La lunghezza massima consentita per il testo.

    Returns:
        str: Il testo troncato con '...' alla fine se supera il limite.
    """
    if len(text) > max_length:
        return text[:max_length - 3] + '...'
    return text

def create_pdf_report(operator, event, login_datetime, communication_log, directory, n_files, logo_path):
    """
    Creates a PDF report of radio communications, organizing the data into a table with controlled text length.
    Now includes a header image in the report.

    Args:
        operator (str): The name of the operator who logged in.
        event (str): The name of the event.
        login_datetime (str): The date and time of the login.
        communication_log (list): A list of communications in the format 
                                  (datetime, sender, receiver, message_received, message_sent).
        directory (str): The directory in which to save the PDF file.
        n_files (int): The number of pdf files that are present in the directory.

    Output:
        Saves the PDF file in the specified directory.
    """

    class PDF(FPDF):
        def cell_with_truncation(self, width, height, text, border=0, align='L', max_length=None):
            if max_length:
                text = truncate_text(text, max_length)
            self.cell(width, height, text, border, 0, align)

    # Create PDF object with landscape orientation
    pdf = PDF(orientation='L')  # 'L' stands for landscape
    pdf.add_page()

    # Add header image
    # Assuming the image is in the current directory and is named 'logo.png'
    if os.path.exists(logo_path):
        pdf.image(logo_path, x=10, y=8, w=30)  # Adjust 'x', 'y', and 'w' as needed
    else:
        print(f"Logo image not found at {logo_path}")

    # Move below the image
    pdf.set_xy(50, 15)  # Adjust 'x' and 'y' depending on the image size

    # Report header with title
    pdf.set_font("Arial", "B", 16)
    pdf.cell(200, 10, f"Rapporto registrazione delle comunicazioni radio n° {n_files}/{login_datetime[:4]}", ln=True, align="C")
    pdf.ln(10)

    # Operator info and login datetime
    pdf.set_font("Arial", "B", 9)
    pdf.cell(280, 10, f"Operatore: {operator}", ln=True)
    pdf.cell(280, 10, f"Evento: {event}", ln=True)
    pdf.ln(10)

    # Table headers
    pdf.set_font("Arial", "B", 9)
    pdf.cell(35, 10, "Data/Time", 1, 0, 'C')
    pdf.cell(30, 10, "Mittente", 1, 0, 'C')
    pdf.cell(30, 10, "Ricevente", 1, 0, 'C')
    pdf.cell(90, 10, "Messaggio ricevuto", 1, 0, 'C')
    pdf.cell(90, 10, "Messaggio trasmesso", 1, 1, 'C')  # 1,1 means move to the next line

    # Insert communication log into table with controlled text truncation
    for entry in communication_log:
        log_datetime, sender, receiver, message_received, message_sent = entry
        
        # Truncate text to keep the table clean
        pdf.cell_with_truncation(35, 10, log_datetime, 1, 'C', max_length=25)
        pdf.cell_with_truncation(30, 10, sender, 1, 'C', max_length=20)
        pdf.cell_with_truncation(30, 10, receiver, 1, 'C', max_length=20)
        pdf.cell_with_truncation(90, 10, message_received, 1, 'C', max_length=70)
        pdf.cell_with_truncation(90, 10, message_sent, 1, 'C', max_length=70)
        pdf.ln(10)  # Move to the next line

    # Sanitize the file name to remove invalid characters
    operator_clean = sanitize_filename(operator)
    file_name = f"rapporto_comunicazioni_radio_{operator_clean}_{n_files}_2024.pdf"
    file_path = os.path.join(directory, file_name)

    try:
        pdf.output(file_path)
        print(f"Rapporto salvato in: {file_path}")
    except Exception as e:
        print(f"Errore salvataggio PDF: {e}")