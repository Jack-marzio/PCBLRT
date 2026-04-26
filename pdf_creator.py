# -*- coding: utf-8 -*-
"""
Created on Fri Oct 11 19:42:02 2024

@author: Jacopo
"""

from openpyxl.styles import Font, Alignment
from openpyxl.drawing.image import Image
from openpyxl import Workbook
from datetime import datetime
from fpdf import FPDF
import textwrap
import os
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

def count_xlsx_in_directory(directory): 
    """
    Counts the number of xlsx files in the specified directory.

    Args:
        directory (str): The directory in which to count PDF files.

    Returns:
        int: The number of xlsx files in the directory.
    """
    try:
        # List all files in the directory
        files = os.listdir(directory)
        
        # Filter and count files that end with .xlsx
        xlsx_files_counter = [file for file in files if file.endswith('.xlsx')]
        return len(xlsx_files_counter) + 1
    
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

        def header(self):
            # Logo
            if hasattr(self, "logo_path") and os.path.exists(self.logo_path):
                self.image(self.logo_path, 10, 8, 25)
    
            self.set_font("Arial", "B", 16)
            self.set_xy(0, 15)
            self.cell(0, 10, self.title_report, border=0, ln=True, align="C")
            self.ln(10)
    
            # Info operatore
            self.set_font("Arial", "", 10)
            self.cell(0, 6, f"Operatore: {self.operator}", ln=True)
            self.cell(0, 6, f"Evento: {self.event}", ln=True)
            self.ln(5)
    
            self.draw_table_header()
    
        def footer(self):
            self.set_y(-12)
            self.set_font("Arial", "I", 8)
            self.cell(0, 5, f"Pagina {self.page_no()}", align="C")
    
        def draw_table_header(self):
            self.set_font("Arial", "B", 9)
            self.set_fill_color(230, 230, 230)
    
            headers = ["Data/Time", "Mittente", "Ricevente",
                       "Messaggio ricevuto", "Messaggio trasmesso"]
    
            widths = [35, 30, 30, 90, 90]
    
            for i in range(len(headers)):
                self.cell(widths[i], 8, headers[i], border=1, align='C', fill=True)
            self.ln()

    pdf = PDF(orientation="L")
    pdf.logo_path = logo_path
    pdf.operator = operator
    pdf.event = event
    pdf.title_report = f"Rapporto registrazione comunicazioni radio n° {n_files}/{login_datetime[:4]}"
    
    pdf.add_page()
    pdf.set_font("Arial", "", 9)
    
    col_widths = [35, 30, 30, 90, 90]
    line_height = 5
    
    for entry in communication_log:
    
        row = [str(x) for x in entry]
    
        # Spezza parole troppo lunghe
        for i in range(len(row)):
            row[i] = "\n".join(textwrap.wrap(row[i], 40))
    
        # Calcola altezza massima riga
        max_lines = 0
        for i in range(len(row)):
            lines = row[i].count("\n") + 1
            max_lines = max(max_lines, lines)
    
        row_height = line_height * max_lines
    
        # Page break automatico
        if pdf.get_y() + row_height > pdf.page_break_trigger:
            pdf.add_page()
    
        x_start = pdf.get_x()
        y_start = pdf.get_y()
    
        for i in range(len(row)):
            pdf.set_xy(x_start, y_start)
            align = 'C' if i < 3 else 'L'
            pdf.multi_cell(col_widths[i], line_height, row[i],
                           border=1, align=align)
            x_start += col_widths[i]
    
        pdf.set_y(y_start + row_height)
    
    # Sanitize the file name to remove invalid characters
    operator_clean = sanitize_filename(operator)
    file_name = f"rapporto_comunicazioni_radio_{operator_clean}_{n_files}_{login_datetime[:4]}.pdf"
    file_path = os.path.join(directory, file_name)

    try:
        pdf.output(file_path)
        print(f"Rapporto salvato in: {file_path}")
    except Exception as e:
        print(f"Errore salvataggio PDF: {e}")
        


        
def create_xlsx_report(operator, event, login_datetime, communication_log, directory, n_files, logo_path):
    
    
    IMG_WITH, IMG_HEIGHT = 150, 150
    TEXT_SIZE = 12
    
    table_header = ["Data/Ora", "Mittente", "Ricevente", "Messaggio ricevuto", "Messaggio trasmesso"]
    
    img = Image(logo_path)
    workbook = Workbook()
    sheet = workbook.active
    
    img.width, img.height = IMG_WITH, IMG_HEIGHT
    sheet.add_image(img, "A3")
    
    sup_header = [operator, event, login_datetime, n_files]
    sheet.append(sup_header)
    sheet.append(table_header)
    
    for col in range(1, len(table_header) + 1):
        cell = sheet.cell(row=3, column=col)
        cell.font = Font(bold=True, size=TEXT_SIZE)
        cell.alignment = Alignment(horizontal="center")
    
    max_lengths = [len(header) for header in table_header]
    
    for data_log in communication_log:
        log_datetime, sender, receiver, message_received, message_sent = data_log
        row_data = [log_datetime, sender, receiver, message_received, message_sent]
        
        for i, value in enumerate(row_data):
            max_lengths[i] = max(max_lengths[i], len(str(value)))
        
        sheet.append(row_data)
    
    max_width = 20
    for i, length in enumerate(max_lengths, start=1):
        col_letter = sheet.cell(row=1, column=i).column_letter
        if length > max_width:
            sheet.column_dimensions[col_letter].width = max_width
            for row in sheet.iter_rows(min_col=i, max_col=i):
                for cell in row:
                    cell.alignment = Alignment(wrap_text=True)
        else:
            sheet.column_dimensions[col_letter].width = length + 2
    
    operator_clean = sanitize_filename(operator)
    file_name = f"rapporto_comunicazioni_radio_{operator_clean}_{n_files}_{login_datetime[:4]}.xlsx"
    file_path = os.path.join(directory, file_name)

    try:
        workbook.save(file_path)
        print(f"Rapporto XLSX salvato in: {file_path}")
    except Exception as e:
        print(f"Errore salvataggio XLSX: {e}")

    
    
    