"""
Questo file implementa una classe per la gestione del compilato avviata 
in modalità debugging con qemu-user-static.

Requisiti essenziali:
 - Il sistema deve poter avviare e il compilato in modalità 
   debugging sulla porta tcp 1337

 - Il sistema deve ridirezionare l'output del compilato nello standard-out
 - Il sistema deve implementare una funzione per prendere dallo standard-input
   il contenuto da ridirezionare al compilato
  
 - Il sistema deve ridefinire le funzioni run, start e quit di gdb in modo da interagire con il compilato
 - Il sistema deve ridefinire le funzioni di next e step ridirezionando l'output
   e l'input qualora necessario
   
Requisiti utili:
 - Il sistema deve poter fermare il compilato 

fammi due classi, una per la gestione del compilato ed una per ridefinire i comandi su gdb

"""
import gdb
import subprocess
import sys
import threading
import time
import os

from pathlib import Path
import string

def show_next_instruction():
    try:
        frame = gdb.selected_frame()
        pc = int(frame.read_register("eip"))   # program counter
        asm_line = gdb.execute(f"x/2i {pc}", to_string=True)
        # print(f"📍 Istruzione corrente: {asm_line.strip()}")
        return asm_line.strip().splitlines()[-1]
    except Exception as e:
        print(f"⚠️ Errore nel recupero istruzione: {e}")

# ==============================================================
# Classe 1 — Gestione del compilato in esecuzione su QEMU
# ==============================================================

class QemuProgramManager:
    def __init__(self, binary_path=None, port=1337):
        # Se non viene fornito, prova a ottenere il file da GDB
        if binary_path is None:
            try:
                binary_path = gdb.current_progspace().filename
            except gdb.error:
                binary_path = None
        self.binary_path = binary_path
        self._tty_fd = Path(binary_path).parent.resolve() if binary_path else None
        self._tty_fd = str(self._tty_fd) + "/tty"

        self.port = port
        self.process = None
        self.running = False
      
    # Avvia il compilato sotto qemu-user-static in modalità debug
    # TODO: da implementare la ridirezione degli input da un file
    def start(self):
        if self.running:
            print("⚠️  Il programma è già in esecuzione.")
            return

        print(f"🚀 Avvio di {self.binary_path} in modalità debug su tcp:{self.port}...")
        cmd = [
            "qemu-i386-static", 
            "-g", str(self.port),
            self.binary_path
        ]

        # Avvio con pipe per redirezione I/O
        self.process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE, # =open(self._tty_fd, 'w'),
            stderr=subprocess.STDOUT,
            stdin=subprocess.PIPE,
            text=True,
            bufsize=1
        )

        self.running = True
        self.stdout_thread = threading.Thread(target=self._redirect_output, daemon=True)
        self.stdout_thread.start()

        print("✅ QEMU avviato e in ascolto per GDB.")

    # Redireziona l'output del compilato su stdout
    def _redirect_output(self):
        for line in self.process.stdout:
            sys.stdout.write(line)
            sys.stdout.flush()

    # Invia input allo stdin del compilato
    def send_input(self, data: str):
        if not self.running or not self.process:
            print("❌ Il processo non è in esecuzione.")
            return
        self.process.stdin.write(data + "\n")
        self.process.stdin.flush()

    # Ferma il compilato
    def stop(self):
        if self.process and self.running:
            print("🛑 Arresto del compilato...")
            self.process.terminate()
            self.running = False
            self.process.wait(timeout=1)
            print("✅ Compilato terminato.")
        else:
            print("⚠️  Nessun processo QEMU in esecuzione.")
    
    def before_exec(self):
        asm_line = [i.strip() for i in show_next_instruction().split(":")[-1].split(' ') if i.strip() != '']

        inputs_calls = {
            "inchar" : lambda x: x in string.printable,
            "inbyte" : lambda x: x >=0 and x < 256, 
            "inword" : lambda x: x >=0 and x < 65536, 
            "inlong" : lambda x: x >=0 and x < 4294967296,
            "indecimal" : None,
            "inline" : None
        }

        # print("non è una call", "call" != asm_line[0])
        # print("non è presente un input:", asm_line[-1][1:3])

        if "call" != asm_line[0] or asm_line[-1][1:3] != "in":
            return

        data = input(f"{asm_line[-1][1:-1]}: ")
        self.send_input(data)
        return
        
        if "inline" == asm_line[2]:
            data = input()
            self.send_input(data)
        
        if "decimal" not in asm_line[2]:
            ok = False
            while not ok:
                try:
                    data = int(input(), 16)
                    ok = True
                except: pass

        

# ==============================================================
# Classe 2 — Override dei comandi GDB
# ==============================================================

class GDBCommandOverrides:
    def __init__(self, manager: QemuProgramManager):
        self.manager = manager
        self._register_commands()
        self._wrap_commands()

    def _register_commands(self):
        # Sovrascrive i comandi di GDB con classi Python personalizzate
        MyRunCommand(self.manager)
        MyStartCommand(self.manager)
        MyQuitCommand(self.manager)
        print("🔧 Comandi GDB personalizzati registrati.")
    
    def _wrap_commands(self):
        #FIXME: quando uso ni su una funzione di input prosegue con la run del programma senza andare alla prossima istruzione
        for cmd in ["next", "step", "nexti", "stepi"]:
            gdb.execute(f"define hook-{cmd}\npython manager.before_exec()\nend")
            # gdb.execute(f"define hookpost-{cmd}\npython manager.after_exec()\nend")

        #TODO: va aggiunto un wrap alla funzione di continue così da prendere gli input quando viene richiesto
        # --> potrei implementarla scorrendo in automatico con ni fixati, così da riutilizzare il codice di controllo usato nella exec_before
        print("🔧 Hook installati su: next, step, nexti, stepi")

# ---------------------
# Ridefinizioni comandi
# ---------------------

class MyRunCommand(gdb.Command):
    def __init__(self, manager):
        super(MyRunCommand, self).__init__("run", gdb.COMMAND_USER)
        self.manager = manager

    def invoke(self, arg, from_tty):
        print("▶️ Esecuzione personalizzata di 'run'")
        self.manager.start()
        gdb.execute(f"target remote :{self.manager.port}")
        gdb.execute("continue")

class MyStartCommand(gdb.Command):
    def __init__(self, manager):
        super(MyStartCommand, self).__init__("start", gdb.COMMAND_USER)
        self.manager = manager

    def invoke(self, arg, from_tty):
        print("🚀 Start personalizzato: avvio del programma sotto QEMU")
        self.manager.start()
        gdb.execute(f"target remote :{self.manager.port}")

class MyQuitCommand(gdb.Command):
    def __init__(self, manager):
        super(MyQuitCommand, self).__init__("quit", gdb.COMMAND_USER)
        self.manager = manager

    def invoke(self, arg, from_tty):
        print("👋 Chiusura di GDB e del compilato...")
        try:
            self.manager.stop()
        finally:
            try:
                gdb.execute("set confirm off", to_string=True)
                gdb.execute("kill", to_string=True)
            except Exception:
                pass
            os._exit(0)

# ==============================================================
# ESEMPIO DI UTILIZZO AUTOMATICO
# ==============================================================

# In GDB puoi scrivere:
#   (gdb) source debug_manager.py
#   (gdb) python manager = QemuProgramManager("/path/al/tuo/compilato")
#   (gdb) python overrides = GDBCommandOverrides(manager)
#   (gdb) run
# ==============================================================


