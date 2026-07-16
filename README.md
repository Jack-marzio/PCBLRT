# ProcivBes Radio Team Tool

Applicazione desktop (Tkinter) per la tenuta del registro delle comunicazioni
radio durante servizi/esercitazioni di protezione civile, con gestione degli
apparati radio in carico/scarico (TLC Point) e una dashboard web locale in
tempo reale per la condivisione con operatori remoti.

Sviluppato da Jacopo Marzio.

---

## Indice

- [Funzionalità](#funzionalità)
- [Architettura e struttura del progetto](#architettura-e-struttura-del-progetto)
- [Requisiti](#requisiti)
- [Installazione (ambiente di sviluppo)](#installazione-ambiente-di-sviluppo)
- [Configurazione (`configurator.txt`)](#configurazione-configuratortxt)
- [Avvio da sorgente](#avvio-da-sorgente)
- [Build come eseguibile (PyInstaller)](#build-come-eseguibile-pyinstaller)
- [File e formati dati](#file-e-formati-dati)
- [Dashboard Web](#dashboard-web)
- [TLC Point — gestione apparati](#tlc-point--gestione-apparati)
- [Interfaccia adattiva](#interfaccia-adattiva)
- [Note su robustezza I/O (Windows / build windowed)](#note-su-robustezza-io-windows--build-windowed)
- [Problemi noti risolti](#problemi-noti-risolti)
- [Limiti noti / possibili miglioramenti futuri](#limiti-noti--possibili-miglioramenti-futuri)
- [Licenza](#licenza)

---

## Funzionalità

- Registro comunicazioni radio (mittente, destinatario, messaggio ricevuto/trasmesso, data/ora automatica o manuale).
- Generazione report **PDF** e **XLSX** del registro, con numerazione progressiva e doppio salvataggio (directory scelta dall'utente + backup locale fisso).
- Recovery automatico della sessione (in caso di chiusura non prevista dell'app).
- **TLC Point**: anagrafica apparati radio su file Excel, carico/scarico con storico movimenti, generazione QR code ed etichette stampabili, normalizzazione codici (trattini tipografici → ASCII, per compatibilità con lettori USB).
- **Dashboard Web locale** (Flask + Server-Sent Events): pagina consultabile da browser su rete LAN, con vista log, chat bidirezionale e riepilogo assegnazioni apparati in tempo reale — nessun servizio esterno, nessuna chiave API.
- Interfaccia bilingue (IT/EN) commutabile a runtime.
- UI adattiva alla risoluzione dello schermo (vedi [Interfaccia adattiva](#interfaccia-adattiva)).

## Architettura e struttura del progetto

```
app/
├── main.py               # Entry point. Risoluzione path, wiring dei componenti.
├── config_manager.py      # Parsing di configurator.txt (key=value, liste tra [ ]).
├── directory_selector.py  # Finestra Tkinter di scelta cartella di salvataggio.
├── log_interface.py       # SplashScreen + RadioLogInterface (finestra principale).
├── tlc_point.py            # EquipmentManager (I/O Excel) + TLCPointPanel (UI).
├── report_creator.py       # Generazione PDF/XLSX (log, chat, assegnazioni, QR).
├── recovery_manager.py     # Salvataggio/ripristino sessione su Excel.
├── web_dashboard.py        # Server Flask + SSE, HTML/CSS/JS della dashboard.
├── ui_utils.py             # Helper UI adattiva (geometry, scrollbar).
├── __init__.py
└── configurator.txt        # File di configurazione (vedi sotto), non incluso nel repo.
```

### Flusso di avvio (`main.py` → `Application.run()`)

1. Risoluzione della cartella base (`_base_path()`), compatibile sia con
   esecuzione da sorgente sia con eseguibile PyInstaller (`sys._MEIPASS`).
2. Caricamento di `configurator.txt` tramite `ConfigManager`.
3. Risoluzione dei path delle risorse grafiche (`_resolve_asset`), con
   fallback automatico `img/` → `assets/` per retrocompatibilità.
4. `SplashScreen` (finestra di benvenuto, si autochiude).
5. Se `Remote_enabled=true`, avvio di `WebDashboard` in un thread daemon.
6. `DirectorySelector` per la scelta della cartella di salvataggio.
7. Calcolo del numero di protocollo (`ReportCreator.count_files`).
8. Costruzione di `RadioLogInterface` (finestra principale, con tab "Log
   Comunicazioni" e "TLC Point").
9. Wiring del callback bidirezionale chat dashboard → interfaccia
   (`dashboard.set_message_callback(interface.handle_remote_message)`).
10. `interface.run()` → mainloop Tkinter.

### Threading

- Il server Flask della dashboard gira in un **thread daemon separato**
  (`WebDashboard.start()`), `threaded=True`.
- La comunicazione thread Flask → thread Tkinter avviene **esclusivamente**
  tramite una `queue.Queue` thread-safe (`RadioLogInterface._remote_queue`),
  svuotata periodicamente nel thread principale via `root.after(...)`
  (`_poll_remote_queue`, ogni 200ms). Non vengono mai chiamati metodi
  Tkinter da un thread diverso da quello della mainloop.

## Requisiti

- Python 3.10+ (usa sintassi `str | None` e `list[str]`).
- Tkinter (libreria standard; su Linux richiede il pacchetto di sistema
  `python3-tk`).
- Vedi [`requirements.txt`](./requirements.txt) per le dipendenze pip.

## Installazione (ambiente di sviluppo)

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

Su Linux, se `tkinter` non è già presente:

```bash
sudo apt install python3-tk
```

## Configurazione (`configurator.txt`)

File di testo semplice `chiave=valore`, una riga per parametro. Righe vuote e
righe che iniziano con `#` sono ignorate. I valori tra `[ ]` separati da
virgola vengono interpretati come liste.

| Chiave | Obbligatoria | Tipo | Descrizione |
|---|---|---|---|
| `Firmware_version` | sì | stringa | Versione mostrata nello splash screen. |
| `Drive_path` | sì | stringa | Path proposto come opzione "Salva nel Drive". |
| `Program_title` | sì | stringa | Titolo della finestra principale. |
| `Proprieties` | sì | stringa | Nome ente mostrato nello splash screen. |
| `Logo_path` | sì | stringa | Path del logo (risolto rispetto a `BASE`, con fallback `img/`→`assets/`). |
| `Flags_logo` | sì | lista `[it, en]` | Path delle due immagini bandiera (ordine: IT, EN). |
| `Web_dashboard_port` | no (default `8080`) | intero | Porta del server Flask della dashboard. |
| `Remote_enabled` | no (default `false`) | `true`/`false` | Abilita/disabilita l'avvio della dashboard web. |
| `Apparati_db_path` | no (default `apparati.xlsx`) | stringa | Path del database Excel degli apparati TLC Point (creato automaticamente se assente). |

### Variabili d'ambiente

| Variabile | Descrizione |
|---|---|
| `WS_TOKEN` | Se impostata, viene usata come `session_id` fisso della dashboard, così il link non cambia ad ogni riavvio. Se assente, ne viene generato uno casuale (`secrets.token_urlsafe`) ad ogni avvio. |

## Avvio da sorgente

```bash
cd app
python main.py
```

Al primo avvio, se `apparati.xlsx` (o il path indicato in `Apparati_db_path`)
non esiste, viene creato automaticamente con le sole intestazioni.

## Build come eseguibile (PyInstaller)

Il progetto è già predisposto per PyInstaller (`--onefile`, `--windowed`):
`main.py` risolve i path tramite `sys._MEIPASS` quando rilevato come
eseguibile congelato.

Esempio di comando di build (adattare i path delle risorse):

```bash
pyinstaller --onefile --windowed ^
  --name ProcivBesRadioTeamTool ^
  --add-data "configurator.txt;." ^
  --add-data "assets;assets" ^
  main.py
```

> Su macOS/Linux usare `:` al posto di `;` nel separatore di `--add-data`.

**Note importanti per la build `--windowed`:**

- In modalità `--windowed` (nessuna console) `sys.stdout`/`sys.stderr`
  possono essere `None`. `main.py` include già una guardia
  (`_ensure_safe_stdio()`, eseguita all'avvio) che previene crash per questo
  motivo — vedi [Note su robustezza I/O](#note-su-robustezza-io-windows--build-windowed).
- Assicurarsi che `configurator.txt` e la cartella delle risorse grafiche
  vengano copiati accanto all'eseguibile (o inclusi con `--add-data` e
  referenziati tramite path relativi risolti da `_resolve_asset`).
- Testare la build su una macchina Windows "pulita" (senza Python
  installato) per verificare che nessuna dipendenza sia stata dimenticata.

## File e formati dati

### Database apparati (`apparati.xlsx`, gestito da `EquipmentManager`)

Due fogli:

**`Apparati`** — anagrafica e stato corrente:

| Codice | Modello | Numero_seriale | Note | Stato | Assegnato_a | Data_ultimo_movimento | Alias |
|---|---|---|---|---|---|---|---|

`Stato` ∈ `{Disponibile, In carico}`.

**`Movimenti`** — storico di ogni carico/scarico:

| Data_ora | Codice | Modello | Operazione | Persona | Operatore | Alias |
|---|---|---|---|---|---|---|

`_migrate_headers()` aggiunge automaticamente in coda eventuali colonne
nuove (es. `Alias`, introdotta in una versione successiva) ai database Excel
già in uso, senza toccare i dati esistenti.

### File di recovery (`recovery/<data>_recovery.xlsx`)

Un file per sessione, sovrascritto ad ogni `_add_log()`. Colonne: `DATE AND
TIME, SENDER, RECEIVER, MESSAGE SENDER, MESSAGE RECEIVER`. Al successivo
avvio, se il file più recente è datato oggi, l'utente viene interpellato per
il ripristino.

### Report generati (`ReportCreator`)

Salvati sia nella directory scelta dall'utente sia in `report_locale/`
(cartella di backup fissa accanto all'eseguibile). Convenzione di naming:

```
rapporto_comunicazioni_radio_<operatore>_<n>_<anno>.pdf / .xlsx
rapporto_chat_<operatore>_<n>_<anno>.pdf / .xlsx
rapporto_assegnazioni_<operatore>_<n>_<anno>.pdf / .xlsx
rapporto_tlc_point_<operatore>_<n>_<anno>.pdf / .xlsx
foglio_qr_apparati_<timestamp>.pdf
```

## Dashboard Web

`WebDashboard` (in `web_dashboard.py`) espone un server Flask minimale sulla
rete locale (`host="0.0.0.0"` di default), a scopo di sola condivisione LAN —
non pensato per l'esposizione su Internet pubblico.

### Rotte

| Metodo | Percorso | Descrizione |
|---|---|---|
| `GET` | `/?session=...` | Pagina HTML della dashboard (tab Log/Chat/Assegnazioni). |
| `GET` | `/api/logs?session=...` | Log radio accumulato (JSON). |
| `GET` | `/api/chat?session=...` | Cronologia chat (JSON). |
| `GET` | `/api/assignments?session=...` | Riepilogo assegnazioni apparati correnti (JSON). |
| `GET` | `/stream?session=...` | Stream SSE (nuove voci di log/chat/assegnazioni in tempo reale). |
| `POST` | `/api/chat/send?session=...` | Invio messaggio chat dal browser. |
| `GET` | `/health` | Stato del servizio (nessuna autenticazione richiesta). |

### Autenticazione

Autenticazione **semplice basata su token nel query param `session`**
(`_authorized()` confronta `request.args.get("session")` con
`self._session_id`), pensata per un contesto di rete locale fidata (LAN
dell'evento/esercitazione). **Non è un meccanismo di sicurezza robusto**: il
token compare in chiaro nell'URL (potenzialmente loggato da proxy/browser
history) e non c'è rate limiting. Da non esporre su reti non fidate o
Internet pubblico senza ulteriori misure (HTTPS, autenticazione più forte,
reverse proxy, ecc.).

## TLC Point — gestione apparati

- `EquipmentManager` incapsula tutta la logica di business (I/O su Excel,
  regole di carico/scarico, ricerca) ed è completamente indipendente dalla
  UI — testabile/utilizzabile anche da script separati.
- `normalize_code()` sostituisce trattini tipografici Unicode (`– — − ‐` ecc.)
  con un trattino ASCII semplice `-`: i lettori di codici USB (che emulano
  una tastiera) a volte "digitano" male questi caratteri se introdotti
  automaticamente dalla correzione automatica di Excel in fase di
  compilazione manuale dell'anagrafica.
- `find()`/`_find_row_index()` tentano sia la corrispondenza esatta
  (case-insensitive) sia quella normalizzata, per tollerare codici in
  anagrafica non ancora "corretti" con lo strumento apposito.
- `TLCPointPanel` è un `tk.Frame` autonomo pensato per essere inserito come
  tab di un `ttk.Notebook` (vedi utilizzo in `log_interface.py`); riceve un
  callback `push_assignments` per inoltrare il riepilogo alla dashboard web
  dopo ogni operazione.

## Interfaccia adattiva

`ui_utils.py` fornisce:

- **`adaptive_geometry(root, desired_w, desired_h, min_w, min_h, ...)`** —
  calcola geometry/minsize di una finestra Tkinter senza mai superare la
  risoluzione reale dello schermo (con margine per barra del
  titolo/taskbar), centrandola. Usata da `SplashScreen`, `DirectorySelector`
  e `RadioLogInterface` al posto di `geometry()` fissa.
- **`maximize_if_small_screen(root, width_threshold, height_threshold)`** —
  massimizza automaticamente la finestra principale su schermi sotto una
  soglia configurabile (default 1440×850), per evitare che pulsanti/pannelli
  restino fuori dall'area visibile su netbook o monitor secondari a bassa
  risoluzione.
- **`add_vscrollbar(container, widget)`** — aggiunge una scrollbar verticale
  a un `Listbox`/`Treeview` posizionato con `.grid()`. Usata su log
  comunicazioni, chat, elenco apparati e storico movimenti TLC Point.

## Note su robustezza I/O (Windows / build `--windowed`)

`main.py` esegue `_ensure_safe_stdio()` come primissima operazione
all'avvio, per prevenire due classi di crash osservate in produzione:

1. **`UnicodeEncodeError` su console Windows non-UTF-8** (`cp1252`): alcuni
   messaggi di log usano emoji/caratteri speciali (es. `📡` in
   `WebDashboard.start()`). Su una console `cp1252`, un `print()` con questi
   caratteri solleva un'eccezione non gestita e termina il processo.
   `_ensure_safe_stdio()` forza `sys.stdout`/`sys.stderr` a UTF-8 con
   `errors="replace"` tramite `TextIOWrapper.reconfigure()`.
2. **`sys.stdout is None`** in eseguibili PyInstaller `--windowed` (nessuna
   console): qualunque `print()` solleverebbe `AttributeError`.
   `_ensure_safe_stdio()` sostituisce stream `None` con un `io.StringIO()`
   in memoria, così i `print()` sparsi nel codice (usati come log minimale)
   non causano più un crash, anche se il loro output non è visibile
   all'utente in quel caso (per un logging persistente in produzione
   windowed, valutare in futuro `logging` su file al posto di `print`).

## Problemi noti risolti

Changelog delle correzioni applicate durante l'ultimo giro di revisione:

- **Messaggi di errore fuorvianti in `TLCPointPanel`** (`tlc_point.py`):
  `_do_carico()` e `_do_register()` mostravano il messaggio "Inserisci o
  scansiona un codice" quando in realtà mancava il campo Persona/Modello.
  Introdotte le chiavi di traduzione dedicate `person_required` e
  `model_required` (IT/EN).
- **Finestre con `geometry()` fissa più grande dello schermo** su monitor
  piccoli (netbook, risoluzioni sotto 1366×768), con pulsanti/pannelli
  irraggiungibili. Risolto introducendo `ui_utils.adaptive_geometry()` e
  `maximize_if_small_screen()` (vedi sopra).
- **`UnicodeEncodeError` in `WebDashboard.start()`** su console Windows
  `cp1252` (crash immediato all'avvio della dashboard). Risolto con
  `_ensure_safe_stdio()` in `main.py` (vedi sopra), che copre anche il caso
  `sys.stdout is None` nelle build `--windowed`.

## Limiti noti / possibili miglioramenti futuri

- L'autenticazione della dashboard web è volutamente minimale (vedi sopra);
  da rafforzare se in futuro se ne prevede l'uso oltre la LAN locale.
- I `print()` usati come logging applicativo non vengono persistiti su file;
  per diagnosi post-mortem su build `--windowed` conviene migrare a un
  logger su file (`logging.FileHandler`).
- Nessuna suite di test automatizzati inclusa nel repository: la
  validazione funzionale descritta in questo cambio è stata eseguita
  manualmente (avvio end-to-end headless, test diretti su
  `EquipmentManager`, `ReportCreator`, `RecoveryManager`, endpoint della
  dashboard).
- `_add_log()` non valida il formato della data/ora inserita manualmente
  quando "Data/Ora Automatica" è disattivato: viene salvata come stringa
  libera.

## Licenza

_Da definire dal proprietario del progetto._