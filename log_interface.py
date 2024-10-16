import tkinter as tk
import os
from tkinter import ttk, messagebox
from PIL import Image, ImageTk
from datetime import datetime
from pdf_creator import create_pdf_report, count_pdfs_in_directory


def show_splash_screen():
    """
    Mostra una finestra iniziale con un'immagine e del testo.
    """
    # Creazione della finestra di benvenuto
    splash = tk.Tk()
    splash.title("ProcivBesRadioTeamtool")
    splash.geometry("1200x800")  # Imposta le dimensioni della finestra
    splash.resizable(True, True)  # Disabilita il ridimensionamento

    # Carica l'immagine (modifica il percorso in base alla tua immagine)
    try:
        image = Image.open("logoPICCOLOSENZASFONDO.png")  # Sostituisci con il percorso della tua immagine
        image = image.resize((300, 300), Image.LANCZOS)  # Ridimensiona l'immagine
        img = ImageTk.PhotoImage(image)
        
        # Imposta l'immagine come icona nella barra in alto
        icon_image = ImageTk.PhotoImage(Image.open("logoPICCOLOSENZASFONDO.png").resize((32, 32), Image.LANCZOS))  # Ridimensiona l'icona
        splash.iconphoto(False, icon_image)  # Imposta l'icona nella barra del titolo
    except Exception as e:
        img = None
        print(f"Errore nel caricamento dell'immagine: {e}")

    # Mostra l'immagine al centro della finestra
    if img:
        label_img = tk.Label(splash, image=img)
        label_img.pack(pady=10)

    # Mostra il titolo sotto l'immagine
    title_label = tk.Label(splash, text="Pro_Civ_Bes_Radio_Log_Tool", font=("Helvetica", 20, "bold"))
    title_label.pack(pady=10)

    # Mostra i crediti in basso
    credit_label = tk.Label(splash, text="Created by Jacopo Marzio\nproprieties of G.C. Besozzo V1.0", font=("Helvetica", 8))
    credit_label.pack(side="bottom", pady=10)

    # Chiude la finestra dopo 3 secondi
    splash.after(3000, splash.destroy)  # 3000 millisecondi = 3 secondi

    # Mantieni la finestra in esecuzione
    splash.mainloop()

def radio_log_interface(login_datetime, communication_log, directory, n_files, logo_path='logoPICCOLOSENZASFONDO.png', program_title="Radio Communication Log"):
    """
    Crea una GUI per il sistema di log radio.
    """
    # Definizione delle traduzioni
    translations = {
        'en': {
            "operator": "Operator:",
            "event": "Event:",
            "auto_datetime": "Automatic Date/Time",
            "manual_datetime": "Date/Time (Manual):",
            "sender": "Sender:",
            "receiver": "Receiver:",
            "msg_received": "Message Received:",
            "msg_sent": "Message Sent:",
            "add_log": "Add Log",
            "generate_pdf": "Generate PDF",
            "operator_error": "Operator name is required!",
            "event_error": "Event name is required!",
            "fields_error": "All fields must be filled out!",
            "error_title": "Error",
            "warning_title": "Warning",
            "logo_error": "Could not load logo: {}",
            "pdf_success": "PDF report generated at {}",
            "pdf_title": "Radio Communication Log",
            "listbox_header": "Logs",
        },
        'it': {
            "operator": "Operatore:",
            "event": "Evento:",
            "auto_datetime": "Data/Ora Automatica",
            "manual_datetime": "Data/Ora (Manuale):",
            "sender": "Mittente:",
            "receiver": "Destinatario:",
            "msg_received": "Messaggio Ricevuto:",
            "msg_sent": "Messaggio Inviato:",
            "add_log": "Aggiungi Log",
            "generate_pdf": "Genera PDF",
            "operator_error": "Il nome dell'operatore è obbligatorio!",
            "event_error": "Il nome dell'evento è obbligatorio!",
            "fields_error": "Tutti i campi devono essere compilati!",
            "error_title": "Errore",
            "warning_title": "Avviso",
            "logo_error": "Impossibile caricare il logo: {}",
            "pdf_success": "Rapporto PDF generato in {}",
            "pdf_title": "Registro Comunicazioni Radio",
            "listbox_header": "Log",
        }
    }

    current_language = 'en'  # Lingua predefinita

    def change_language(lang):
        nonlocal current_language
        if lang not in translations:
            return
        current_language = lang
        texts = translations[lang]
        # Aggiorna i testi dei label
        labels["operator"].config(text=texts["operator"])
        labels["event"].config(text=texts["event"])
        labels["auto_datetime"].config(text=texts["auto_datetime"])
        labels["manual_datetime"].config(text=texts["manual_datetime"])
        labels["sender"].config(text=texts["sender"])
        labels["receiver"].config(text=texts["receiver"])
        labels["msg_received"].config(text=texts["msg_received"])
        labels["msg_sent"].config(text=texts["msg_sent"])
        btn_add_log.config(text=texts["add_log"])
        btn_generate_pdf.config(text=texts["generate_pdf"])
        title_label.config(text=texts["pdf_title"])
        listbox_label.config(text=texts["listbox_header"])
        root.title(texts["pdf_title"])

    def add_log():
        if var_auto_datetime.get():
            date_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        else:
            date_time = entry_manual_datetime.get()

        sender = entry_sender.get()
        receiver = entry_receiver.get()
        msg_received = entry_msg_received.get()
        msg_sent = entry_msg_sent.get()

        if not (date_time and sender and receiver and msg_received and msg_sent):
            messagebox.showerror(translations[current_language]["error_title"], translations[current_language]["fields_error"])
            return

        # Aggiungi il log alla listbox
        log_entry = f"{date_time} - {sender} -> {receiver} : {msg_received} | {msg_sent}"
        listbox_logs.insert(tk.END, log_entry)

        # Salva il log nella lista interna
        communication_log.append((date_time, sender, receiver, msg_received, msg_sent))

        # Resetta i campi
        if not var_auto_datetime.get():
            entry_manual_datetime.delete(0, tk.END)
        entry_sender.delete(0, tk.END)
        entry_receiver.delete(0, tk.END)
        entry_msg_received.delete(0, tk.END)
        entry_msg_sent.delete(0, tk.END)

    def generate_pdf():
        operator = entry_operator.get()
        event = entry_event.get()
        if not operator:
            messagebox.showerror(translations[current_language]["error_title"], translations[current_language]["operator_error"])
            return
        if not event:
            messagebox.showerror(translations[current_language]["error_title"], translations[current_language]["event_error"])
            return

        if not os.path.exists(directory):
            try:
                os.makedirs(directory)
            except Exception as e:
                messagebox.showerror(translations[current_language]["error_title"], f"Impossibile creare la directory: {e}")
                return

        # Conta i PDF presenti nella directory
        n_files = count_pdfs_in_directory(directory)

        # Crea il report PDF
        try:
            create_pdf_report(operator, event, login_datetime, communication_log, directory, n_files)
            messagebox.showinfo("Success", translations[current_language]["pdf_success"].format(directory))
        except Exception as e:
            messagebox.showerror(translations[current_language]["error_title"], f"Errore nella generazione del PDF: {e}")

    def toggle_manual_datetime():
        if var_auto_datetime.get():
            entry_manual_datetime.config(state='disabled')
        else:
            entry_manual_datetime.config(state='normal')

    def resize_image(image_path, width, height):
        try:
            image = Image.open(image_path)
            resized_image = image.resize((width, height), Image.LANCZOS)
            return ImageTk.PhotoImage(resized_image)
        except Exception as e:
            messagebox.showwarning(translations[current_language]["warning_title"], translations[current_language]["logo_error"].format(e))
            return None

    # Inizializza la finestra Tkinter
    root = tk.Tk()
    root.title(program_title)
    root.geometry("1200x800")
    root.resizable(True, True)

    # Titolo e logo
    top_frame = tk.Frame(root)
    top_frame.pack(pady=10)

    if os.path.exists(logo_path):
        logo_img = resize_image(logo_path, 100, 100)
        if logo_img:
            logo_label = tk.Label(top_frame, image=logo_img)
            logo_label.image = logo_img  # Mantiene il riferimento all'immagine
            logo_label.pack(side='left', padx=10)
            
            # Imposta l'immagine come icona nella barra in alto
            icon_image = ImageTk.PhotoImage(Image.open("logoPICCOLOSENZASFONDO.png").resize((32, 32), Image.LANCZOS))  # Ridimensiona l'icona
            root.iconphoto(False, icon_image)  # Imposta l'icona nella barra del titolo

    title_label = tk.Label(top_frame, text=program_title, font=("Helvetica", 20))
    title_label.pack(side='left')

    # Frame per i campi di input
    input_frame = tk.Frame(root)
    input_frame.pack(pady=10, padx=20, fill="x")

    labels = {}
    entries = {}

    # Operatore
    labels["operator"] = tk.Label(input_frame, text=translations[current_language]["operator"])
    labels["operator"].grid(row=0, column=0, sticky="e", pady=5, padx=5)
    entry_operator = tk.Entry(input_frame)
    entry_operator.grid(row=0, column=1, sticky="ew", pady=5, padx=5)

    # Evento
    labels["event"] = tk.Label(input_frame, text=translations[current_language]["event"])
    labels["event"].grid(row=1, column=0, sticky="e", pady=5, padx=5)
    entry_event = tk.Entry(input_frame)
    entry_event.grid(row=1, column=1, sticky="ew", pady=5, padx=5)

    # Opzione per Data/Ora Automatica
    var_auto_datetime = tk.BooleanVar(value=True)
    labels["auto_datetime"] = ttk.Checkbutton(
        input_frame, 
        text=translations[current_language]["auto_datetime"], 
        variable=var_auto_datetime, 
        command=toggle_manual_datetime
    )
    labels["auto_datetime"].grid(row=2, column=0, columnspan=2, sticky="w", pady=5, padx=5)

    # Data/Ora Manuale
    labels["manual_datetime"] = tk.Label(input_frame, text=translations[current_language]["manual_datetime"])
    labels["manual_datetime"].grid(row=3, column=0, sticky="e", pady=5, padx=5)
    entry_manual_datetime = tk.Entry(input_frame)
    entry_manual_datetime.grid(row=3, column=1, sticky="ew", pady=5, padx=5)
    entry_manual_datetime.config(state='disabled')

    # Mittente
    labels["sender"] = tk.Label(input_frame, text=translations[current_language]["sender"])
    labels["sender"].grid(row=4, column=0, sticky="e", pady=5, padx=5)
    entry_sender = tk.Entry(input_frame)
    entry_sender.grid(row=4, column=1, sticky="ew", pady=5, padx=5)

    # Destinatario
    labels["receiver"] = tk.Label(input_frame, text=translations[current_language]["receiver"])
    labels["receiver"].grid(row=5, column=0, sticky="e", pady=5, padx=5)
    entry_receiver = tk.Entry(input_frame)
    entry_receiver.grid(row=5, column=1, sticky="ew", pady=5, padx=5)

    # Messaggio Ricevuto
    labels["msg_received"] = tk.Label(input_frame, text=translations[current_language]["msg_received"])
    labels["msg_received"].grid(row=6, column=0, sticky="e", pady=5, padx=5)
    entry_msg_received = tk.Entry(input_frame)
    entry_msg_received.grid(row=6, column=1, sticky="ew", pady=5, padx=5)

    # Messaggio Inviato
    labels["msg_sent"] = tk.Label(input_frame, text=translations[current_language]["msg_sent"])
    labels["msg_sent"].grid(row=7, column=0, sticky="e", pady=5, padx=5)
    entry_msg_sent = tk.Entry(input_frame)
    entry_msg_sent.grid(row=7, column=1, sticky="ew", pady=5, padx=5)

    # Configura le colonne per espandersi
    input_frame.grid_columnconfigure(1, weight=1)

    # Listbox per visualizzare i log
    listbox_frame = tk.Frame(root)
    listbox_frame.pack(pady=10, padx=20, fill="both", expand=True)

    listbox_label = tk.Label(listbox_frame, text=translations[current_language]["listbox_header"], font=("Helvetica", 14))
    listbox_label.pack(anchor='w')

    listbox_logs = tk.Listbox(listbox_frame, width=80, height=10)
    listbox_logs.pack(fill="both", expand=True, pady=5)

    # Bottoni per aggiungere log e generare PDF
    button_frame = tk.Frame(root)
    button_frame.pack(pady=10)

    btn_add_log = tk.Button(button_frame, text=translations[current_language]["add_log"], command=add_log)
    btn_add_log.grid(row=0, column=0, padx=10)

    btn_generate_pdf = tk.Button(button_frame, text=translations[current_language]["generate_pdf"], command=generate_pdf)
    btn_generate_pdf.grid(row=0, column=1, padx=10)

    # Sezione per la selezione della lingua
    language_frame = tk.Frame(root)
    language_frame.pack(pady=10)

    def resize_image(image_path, width, height):
        try:
            image = Image.open(image_path)
            resized_image = image.resize((width, height), Image.LANCZOS)
            return ImageTk.PhotoImage(resized_image)
        except Exception as e:
            messagebox.showwarning(translations[current_language]["warning_title"], translations[current_language]["logo_error"].format(e))
            return None

    # Carica e ridimensiona le immagini delle bandiere
    flag_en = resize_image("uk.png", 50, 30)
    flag_it = resize_image("it.png", 50, 30)

    # Bottoni per cambiare lingua
    if flag_en:
        btn_en = tk.Button(language_frame, image=flag_en, command=lambda: change_language('en'))
        btn_en.image = flag_en  # Mantiene un riferimento all'immagine
        btn_en.pack(side='left', padx=10)
    if flag_it:
        btn_it = tk.Button(language_frame, image=flag_it, command=lambda: change_language('it'))
        btn_it.image = flag_it  # Mantiene un riferimento all'immagine
        btn_it.pack(side='left', padx=10)

    # Etichetta del titolo della listbox
    listbox_label.config(text=translations[current_language]["listbox_header"])

    # Avvia la finestra Tkinter
    root.mainloop()