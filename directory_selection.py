# -*- coding: utf-8 -*-
"""
Created on Tue Oct 15 21:14:33 2024

@author: Jacopo
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import os
from PIL import Image, ImageTk


def select_directory():
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
                messagebox.showerror("Errore", "Per favore, seleziona una directory esterna.")
                return
            directory = selected_dir
        else:
            # Definisci una directory locale predefinita
            directory = os.path.join(os.getcwd(), 'reports')
            if not os.path.exists(directory):
                try:
                    os.makedirs(directory)
                except Exception as e:
                    messagebox.showerror("Errore", f"Impossibile creare la directory: {e}")
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
    root.title("Seleziona la Directory di Salvataggio")
    root.geometry("1200x800")
    root.resizable(True, True)
    
    # Imposta l'immagine come icona nella barra in alto
    icon_image = ImageTk.PhotoImage(Image.open("logoPICCOLOSENZASFONDO.png").resize((32, 32), Image.LANCZOS))  # Ridimensiona l'icona
    root.iconphoto(False, icon_image)  # Imposta l'icona nella barra del titolo
    
    var_save_option = tk.StringVar(value='local')
    selected_directory = [None]
    
    # Titolo
    label_title = tk.Label(root, text="Seleziona la Directory per Salvare i PDF", font=("Helvetica", 16))
    label_title.pack(pady=20)
    
    # Radiobutton per salvataggio locale
    rb_local = ttk.Radiobutton(root, text="Salva nella Directory Locale", variable=var_save_option, value='local', command=toggle_entry)
    rb_local.pack(anchor='w', padx=20, pady=5)
    
    # Radiobutton per salvataggio esterno
    rb_external = ttk.Radiobutton(root, text="Scegli Directory Esterna", variable=var_save_option, value='external', command=toggle_entry)
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
        flag_en = resize_image("uk.png", 50, 30)
        flag_it = resize_image("it.png", 50, 30)
        
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
                "title": "Seleziona la Directory di Salvataggio",
                "save_local": "Salva nella Directory Locale",
                "save_external": "Scegli Directory Esterna",
                "browse": "Sfoglia...",
                "selected_dir": "Nessuna directory selezionata",
                "proceed": "Avanti",
            }
            root.title("Seleziona la Directory di Salvataggio")
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