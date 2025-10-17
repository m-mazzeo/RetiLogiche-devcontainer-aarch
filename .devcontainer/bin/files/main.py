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

documentazione usata: https://sourceware.org/gdb/current/onlinedocs/gdb.html/Python-API.html?utm_source=chatgpt.com
"""
import gdb
import subprocess
import sys
import threading
import time
import os

from pathlib import Path
import string


def get_instruction(addr, n=1):
    if n > 1:
        return  [
            i.strip().split(':')[-1] for i in
            gdb.execute(f"x/{n}i {addr}", to_string=True).strip().splitlines()
        ]
    elif n == 1:
        return gdb.execute(f"x/i {addr}", to_string=True).strip().split(':')[-1]
    else:
        return None

def show_next_instruction(is_step=False):
    try:
        frame = gdb.selected_frame()
        eip = int(frame.read_register("eip"))

        cur, nxt = get_instruction(eip, 2)
        cur = gdb.string_to_argv(cur)

        # Istruzioni di salto: jmp, call, loop, ret
        if "jmp" == cur[0] or "loop" == cur[0] or (is_step and "call" == cur[0]):
            nxt = get_instruction(cur[1])

        if "ret" == cur[0]:
            # 1. Prendi l'indirizzo dallo stack
            esp = int(frame.read_register("esp"))
            addr = int(gdb.execute(f" x/xw {esp}", to_string=True).strip().split(':')[-1].strip(), 16)

            nxt = get_instruction(addr)

        # Istruzioni di salto pazzerelle: jmp_condition, loop_cond
        if (cur[0][0] == "j" and cur[0][1:] != "mp") or (cur[0] != "loop" and cur[0][:4] == "loop"):
            #  1. Evaluate the condition
            f = str(frame.read_register("eflags")) # I flag sono rappresentati tutti in maiuscolo (solo le iniziali)
            condition_flags = {
                # uguaglianza
                "e" : lambda: "ZF" in f,                      # equal / zero
                "ne": lambda: "ZF" not in f,                  # not equal

                # unsigned (CF)
                "a" : lambda: ("CF" not in f) and ("ZF" not in f),  # above (unsigned >)
                "ae": lambda: "CF" not in f,                        # above or equal (>= unsigned)
                "b" : lambda: "CF" in f,                            # below (unsigned <)
                "be": lambda: ("CF" in f) or ("ZF" in f),           # below or equal (<= unsigned)

                # signed (SF, OF)
                "g" : lambda: ("ZF" not in f) and (("SF" in f) == ("OF" in f)),  # greater (signed >)
                "ge": lambda: ("SF" in f) == ("OF" in f),                        # greater or equal (>= signed)
                "l" : lambda: ("SF" in f) != ("OF" in f),                        # less (signed <)
                "le": lambda: ("ZF" in f) or (("SF" in f) != ("OF" in f)),       # less or equal (<= signed)

                # singoli flag
                "z" : lambda: "ZF" in f,
                "nz": lambda: "ZF" not in f,
                "c" : lambda: "CF" in f,
                "nc": lambda: "CF" not in f,
                "o" : lambda: "OF" in f,
                "no": lambda: "OF" not in f,
                "s" : lambda: "SF" in f,
                "ns": lambda: "SF" not in f,
            }


            conditions = cur[0][1:] if cur[0][0] == "j" else cur[0][4:]

            #  2. Send the instruction based on the condition
            if condition_flags[conditions]():

                nxt = get_instruction(cur[1])

        # print(f"📍 Istruzione corrente: {' '.join(cur)}")
        return gdb.string_to_argv(nxt)
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
        self.port = port
        self.process = None
        self.running = False

    # Avvia il compilato sotto qemu-user-static in modalità debug
    def start(self):
        if self.running:
            print("⚠️  Il programma è già in esecuzione.")
            return

        print(f"🚀 Avvio di {self.binary_path} in modalità debug su tcp:{self.port}...")
        cmd = [
            "qemu-i386-static",
            "-g", str(self.port),
            "-one-insn-per-tb",
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
            sys.stdout.write("output << "+line)
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


# ==============================================================
# Classe 2 — Override dei comandi GDB
# ==============================================================

class GDBCommandOverrides:
    def __init__(self, manager: QemuProgramManager):
        self.manager = manager

        self._register_commands()
        self._wrap_commands()

    def before_exec(self, cmd):
        """
        Prima di eseguire una istruzione, questa funzione controlla se si sta
        per richiedere un input da tastiera e, se richiesto, ridireziona l'input
        desiderato direttamente al processo emulato con qemu.

        params:
         - cmd (str): è il comando che viene eseguito subito dopo la before_exec
        """
        asm_line = show_next_instruction("step" == cmd[:-1])

        # TODO: fare i controlli per ogni funzione della utility.s
        # check_utility_call = {
        #     "char" : lambda x: x in string.printable,
        #     "byte" : lambda x: x >=0 and x < 256,
        #     "word" : lambda x: x >=0 and x < 65536,
        #     "long" : lambda x: x >=0 and x < 4294967296,
        # }

        if "call" != asm_line[0] or asm_line[-1][1:3] != "in":
            return

        data = input(f"{asm_line[-1][1:-1]} >> ")
        self.manager.send_input(data)

        # TODO: fare una funzione fixed_ni
        # if cmd in ["next", "nexti", 'n', 'ni']:
        #     print("da implemetnare una si (default di gdb) e ridefinisci la finish")
        #     # A quanto pare il bug è presente anche su gdb-multiarch senza questo setup
        #     return

        return


    def _register_commands(self):
        # Sovrascrive i comandi di GDB con classi Python personalizzate
        runner = MyRunCommand(self.manager)
        MyStartCommand(runner)
        MyQuitCommand(self.manager)
        print("🔧 Comandi GDB personalizzati registrati.")

    def _wrap_commands(self):
        #FIXME: quando uso ni su una funzione di input prosegue con la run del programma senza andare alla prossima istruzione
        for cmd in ["next", "nexti", "step", "stepi"]:
            gdb.execute(f"define hook-{cmd}\npython overrides.before_exec('{cmd}')\nend")
            # gdb.execute(f"define hookpost-{cmd}\npython manager.after_exec()\nend")

        #TODO: va aggiunto un wrap alla funzione continue così da prendere gli input quando viene richiesto
        # --> potrei implementarla scorrendo in automatico con ni fixati, così da riutilizzare il codice di controllo usato nella exec_before
        print("🔧 Hook installati su: next, step, nexti, stepi")

# ---------------------
# Ridefinizioni comandi
# ---------------------
class MyStartCommand(gdb.Command):
    def __init__(self, runner):
        super(MyStartCommand, self).__init__("start", gdb.COMMAND_USER)
        self.runner = runner

    def invoke(self, arg, from_tty):
        self.runner.invoke(arg, from_tty)

# TODO: da implementare la ridirezione degli input da un file
class MyRunCommand(gdb.Command):
    def __init__(self, manager):
        super(MyRunCommand, self).__init__("run", gdb.COMMAND_USER)
        self.manager = manager

    def invoke(self, arg, from_tty):
        self.manager.start()
        gdb.execute(f"target remote :{self.manager.port}")
        gdb.execute("continue")

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

# TODO: sovrascrivere il comando (o fare un wrap) su continue

# ==============================================================
# ESEMPIO DI UTILIZZO AUTOMATICO
# ==============================================================

# In GDB puoi scrivere:
#   (gdb) source debug_manager.py
#   (gdb) python manager = QemuProgramManager("/path/al/tuo/compilato")
#   (gdb) python overrides = GDBCommandOverrides(manager)
#   (gdb) run
# ==============================================================


