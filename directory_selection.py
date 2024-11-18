# -*- coding: utf-8 -*-
"""
Created on Tue Oct 15 21:14:33 2024

@author: Jacopo
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import os
from PIL import Image, ImageTk
import socket
import time

def check_connection():
    """Verifica la connessione a Internet."""
    try:
        # Prova a connetterti a un server (es. Google)
        socket.create_connection(("8.8.8.8", 53), timeout=2)
        return True
    except OSError:
        return False
    


def select_directory(logo_path, flag_list):
    """
    Mostra una finestra Tkinter per la selezione della directory di salvataggio dei PDF.
    
    Ritorna:
        str: Il percorso della directory selezionata.
    """
    def proceed():
        choice = var_save_option.get()
        if choice == 'external':
            selected_dir = entry_external_dir.get()
            if not selected_dir:
                messagebox.showerror("Errore", "Per favore, seleziona una cartella esterna.")
                return
            directory = selected_dir
        elif choice != 'external' or choice != 'drive':
            # Definisci una directory locale predefinita
            directory = os.path.join(os.getcwd(), 'reports')
            if not os.path.exists(directory):
                try:
                    os.makedirs(directory)
                except Exception as e:
                    messagebox.showerror("Errore", f"Impossibile creare la cartella: {e}")
                    return
        selected_directory[0] = directory
        root.destroy()
    
    def browse():
        dir_selected = filedialog.askdirectory()
        if dir_selected:
            entry_external_dir.delete(0, tk.END)
            entry_external_dir.insert(0, dir_selected)
    
    def toggle_entry():
        if var_save_option.get() == 'external':
            entry_external_dir.config(state='normal')
            btn_browse.config(state='normal')
        else:
            entry_external_dir.config(state='disabled')
            btn_browse.config(state='disabled')
            entry_external_dir.delete(0, tk.END)
    
    # Inizializza la finestra principale
    root = tk.Tk()
    root.title("Seleziona una cartella di Salvataggio")
    root.geometry("1200x800")
    root.resizable(True, True)
    
    # Imposta l'immagine come icona nella barra in alto
    icon_image = ImageTk.PhotoImage(Image.open(logo_path).resize((32, 32), Image.LANCZOS))  # Ridimensiona l'icona
    root.iconphoto(False, icon_image)  # Imposta l'icona nella barra del titolo
   
    
    var_save_option = tk.StringVar(value='local')
    selected_directory = [None]
    
    # Titolo
    label_title = tk.Label(root, text="Seleziona una cartella di Salvataggio", font=("Helvetica", 16))
    label_title.pack(pady=20)
    
    # Frame per LED e stato
    led_frame = tk.Frame(root)
    led_frame.pack(fill="x", pady=5)
  
    # Imposta un LED che verifichi la connessione a internet:
    def update_led():
        if check_connection():
          canvas.itemconfig(led, fill="green")
          lbl_status.config(text="Connesso a Internet", fg="black")
        else:
          canvas.itemconfig(led, fill="red")
          lbl_status.config(text="Non connesso a Internet", fg="black")
      
        root.after(2000, update_led)
  
    # Canvas per il LED
    canvas = tk.Canvas(led_frame, width=50, height=60)
    canvas.pack(side="left", padx=10)
    led = canvas.create_oval(15, 15, 40, 40, fill="red")
  
    # Etichetta per lo stato della connessione
    lbl_status = tk.Label(led_frame, text="Attendo...", font=("Helvetica", 10))
    lbl_status.pack(side="left", padx=10)
  
    update_led()
    # Radiobutton per salvataggio locale
    rb_local = ttk.Radiobutton(root, text="Salva nella cartella Locale", variable=var_save_option, value='local', command=toggle_entry)
    rb_local.pack(anchor='w', padx=20, pady=5)
    
    # Radiobutton per salvataggio esterno
    rb_external = ttk.Radiobutton(root, text="Scegli cartella Esterna", variable=var_save_option, value='external', command=toggle_entry)
    rb_external.pack(anchor='w', padx=20, pady=5)
    
    # Frame per l'input della directory esterna
    frame_external = tk.Frame(root)
    frame_external.pack(anchor='w', padx=40, pady=5)
    
    entry_external_dir = ttk.Entry(frame_external, width=40)
    entry_external_dir.pack(side='left', padx=5)
    btn_browse = ttk.Button(frame_external, text="Sfoglia...", command=browse)
    btn_browse.pack(side='left')
    entry_external_dir.config(state='disabled')
    btn_browse.config(state='disabled')
    
    # Bottone "Avanti"
    btn_proceed = ttk.Button(root, text="Avanti", command=proceed)
    btn_proceed.pack(pady=20)
    
    # Sezione per la selezione della lingua
    language_frame = tk.Frame(root)
    language_frame.pack(pady=10)
    
    def resize_image(image_path, width, height):
        from PIL import Image, ImageTk
        image = Image.open(image_path)
        resized_image = image.resize((width, height), Image.LANCZOS)
        return ImageTk.PhotoImage(resized_image)
    
    # Carica e ridimensiona le immagini delle bandiere
    try:
        flag_en = resize_image( flag_list[1], 50, 30)
        flag_it = resize_image( flag_list[0], 50, 30)
        
        btn_en = tk.Button(language_frame, image=flag_en, command=lambda: change_language('en'))
        btn_it = tk.Button(language_frame, image=flag_it, command=lambda: change_language('it'))
        btn_en.image = flag_en  # Mantenere riferimento all'immagine
        btn_it.image = flag_it
        btn_en.pack(side="left", padx=10)
        btn_it.pack(side="left", padx=10)
    except Exception as e:
        messagebox.showwarning("Avviso", f"Impossibile caricare le immagini delle bandiere: {e}")
    
    def change_language(lang):
        """
        Cambia la lingua dell'interfaccia.
        
        Args:
            lang (str): 'en' per inglese, 'it' per italiano.
        """
        if lang == 'en':
            texts = {
                "title": "Select Save Directory",
                "save_local": "Save to Local Directory",
                "save_external": "Choose External Directory",
                "browse": "Browse...",
                "selected_dir": "No directory selected",
                "proceed": "Proceed",
            }
            root.title("Select Save Directory")
        elif lang == 'it':
            texts = {
                "title": "Seleziona una cartella di Salvataggio",
                "save_local": "Salva nella cartella Locale",
                "save_external": "Scegli cartella Esterna",
                "browse": "Sfoglia...",
                "selected_dir": "Nessuna cartella selezionata",
                "proceed": "Avanti",
            }
            root.title("Seleziona la cartella di Salvataggio")
        else:
            return  # Lingua non supportata
        
        # Aggiorna i testi dei widget
        label_title.config(text=texts["title"])
        rb_local.config(text=texts["save_local"])
        rb_external.config(text=texts["save_external"])
        btn_browse.config(text=texts["browse"])
        btn_proceed.config(text=texts["proceed"])
        if var_save_option.get() != 'external':
            selected_dir_text = texts["selected_dir"]
        else:
            selected_dir_text = entry_external_dir.get() if entry_external_dir.get() else texts["selected_dir"]
        entry_external_dir.delete(0, tk.END)
        entry_external_dir.insert(0, selected_dir_text) if var_save_option.get() == 'external' else None
        if var_save_option.get() != 'external':
            entry_external_dir.config(state='disabled')
            btn_browse.config(state='disabled')
    
    root.mainloop()
    
    return selected_directory[0]




