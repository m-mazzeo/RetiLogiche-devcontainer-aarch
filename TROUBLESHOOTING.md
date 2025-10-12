# Filesystem protetto da SELinux

Se usi SELinux devi abilitare la condivisione dei file temporanei.

1. controlla il contesto: `ls -Z /percorso/della/cartella`

2. assegna il contesto per permettere a docker di accedere ai file 
    `sudo chcon -R -t container_file_t /percorso/della/cartella`

3. Persistenza dei contesti (usa semanage per rendere persistenti i contesti)

    sudo semanage fcontext -a -t httpd_sys_content_t "/percorso/della/cartella(/.*)?"
    sudo restorecon -Rv /percorso/della/cartella

>    ⚠️ Nota: semanage fa parte del pacchetto policycoreutils-python o 
             policycoreutils-python-utils a seconda della distribuzione. 


## Spiegazione output del contesto `ls -lZ`

Perfetto! Quando usi il comando:

```bash
ls -Z /percorso/della/cartella
```

l'output mostra le **etichette di contesto SELinux** dei file o delle cartelle. Queste etichette determinano cosa i processi possono o non possono fare su quei file, secondo le policy SELinux.

---

### 📌 Struttura dell’etichetta SELinux (contesto di sicurezza)

Il contesto di SELinux ha in genere **4 campi**:

```
<utente> : <ruolo> : <tipo> : <livello>
```

Esempio:

```
unconfined_u:object_r:httpd_sys_content_t:s0
```

Vediamo cosa significa ciascun campo:

| Campo       | Significato                                                                |
| ----------- | -------------------------------------------------------------------------- |
| **utente**  | Utente SELinux che "possiede" il file. Esempio: `unconfined_u`             |
| **ruolo**   | Ruolo SELinux, spesso `object_r` per i file normali                        |
| **tipo**    | Il campo più importante: determina l'accesso. Es: `httpd_sys_content_t`    |
| **livello** | Usato per il controllo multilevel (MLS). Spesso `s0`, può essere ignorato. |

---

### 🔍 Esempio reale

Supponiamo tu faccia:

```bash
ls -Z /var/www/html/index.html
```

Output:

```
-rw-r--r--. root root unconfined_u:object_r:httpd_sys_content_t:s0 index.html
```

* `unconfined_u` = utente SELinux
* `object_r` = ruolo (standard per file)
* `httpd_sys_content_t` = tipo (content type per Apache)
* `s0` = livello (standard)

➡️ Questo dice a SELinux: “Questo file può essere letto da processi con tipo `httpd_t` (cioè Apache)”.

---

### ⚠️ Problemi comuni

Se un'applicazione (es. Apache, Nginx, MySQL) **non riesce ad accedere** a un file, anche se i permessi Unix sono corretti (`chmod`, `chown`), **SELinux potrebbe bloccarlo** perché il **tipo** non è compatibile.

---

### 💡 Comandi utili

#### Visualizzare contesti in una directory

```bash
ls -lZ /percorso/della/cartella
```

#### Cambiare contesto temporaneamente

```bash
sudo chcon -t tipo_selinux /percorso/file
```

#### Cambiare contesto in modo persistente

```bash
sudo semanage fcontext -a -t tipo_selinux "/percorso/file"
sudo restorecon -v /percorso/file
```

---

## quali sono i tip i di questo campo

Ottima domanda! Il **campo "tipo" (type)** in un contesto SELinux è **il più importante** perché controlla quali **processi possono accedere a quali file**.
Ogni processo in esecuzione ha un tipo (es. `httpd_t` per Apache), e ogni file ha un tipo (es. `httpd_sys_content_t`). Le policy SELinux dicono **quali tipi possono interagire tra loro**.

---

### 📌 Struttura tipica del tipo

Spesso i **tipi** seguono questa convenzione:

```
<nome_servizio>_<tipo_di_accesso>_t
```

Esempi:

* `httpd_sys_content_t` → contenuti web statici letti da Apache
* `httpd_sys_rw_content_t` → contenuti web leggibili e scrivibili da Apache
* `ssh_home_t` → file usati da SSH all’interno della home
* `mysqld_db_t` → file dei database MySQL
* `var_log_t` → file di log generici

---

### 🔧 Tipi comuni e cosa significano

| Tipo SELinux             | Significato                                                        |
| ------------------------ | ------------------------------------------------------------------ |
| `httpd_sys_content_t`    | File leggibili da Apache/Nginx (ma non scrivibili)                 |
| `httpd_sys_rw_content_t` | File **leggibili e scrivibili** da Apache (es. file upload, cache) |
| `httpd_log_t`            | File di log di Apache                                              |
| `httpd_config_t`         | File di configurazione di Apache                                   |
| `user_home_t`            | File nella home directory di un utente (`/home/utente`)            |
| `ssh_home_t`             | File SSH nella home (chiavi, `.ssh/`)                              |
| `var_log_t`              | File in `/var/log`                                                 |
| `mysqld_db_t`            | File di database MySQL (in `/var/lib/mysql`)                       |
| `mount_tmp_t`            | File temporanei in file system montati dinamicamente               |
| `tmp_t`                  | File in `/tmp`, accessibili da molti processi                      |
| `devpts_t`               | Terminali virtuali (`/dev/pts`)                                    |
| `initrc_t`               | Tipo dei processi che partono all’avvio                            |
| `unlabeled_t`            | File privi di etichetta — possono causare blocchi da SELinux       |

---

### 💡 Come sapere quali tipi usare?

Puoi usare il comando:

```bash
semanage fcontext -l | grep httpd
```

Ti elencherà tutti i **tipi associati al servizio Apache** e le directory consigliate.

Esempio:

```
/var/www(/.*)?              all files        system_u:object_r:httpd_sys_content_t:s0
```

Oppure per MySQL:

```bash
semanage fcontext -l | grep mysql
```

---

### ✅ Esempio pratico: file scrivibili da Apache

Se Apache deve poter scrivere in `/var/www/uploads`, devi:

```bash
sudo semanage fcontext -a -t httpd_sys_rw_content_t "/var/www/uploads(/.*)?"
sudo restorecon -Rv /var/www/uploads
```

---

### Vuoi sapere i tipi SELinux esatti per un altro servizio?

Dimmi il nome (es: nginx, samba, postgres, docker...) e ti do l’elenco dei tipi usati da SELinux per quel servizio.


# DISPLAY socket 

non ci ho capito molto, ma alla fine ha funzionato questa [guida](https://github.com/mviereck/x11docker/wiki/How-to-provide-Wayland-socket-to-docker-container)

ricordati alla fine di eseguire il comando `xhost +local:docker` per il corretto funzionamento
del display-server