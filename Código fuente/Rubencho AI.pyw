#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Rubencho AI
Asistente de voz con IA local (Ollama) + Ejecución de comandos CMD

Se puede ejecutar como script (pythonw "Rubencho AI.pyw") o como aplicación de
escritorio compilada con PyInstaller (Rubencho AI.exe, ver compilar.bat).

Novedades 1.3.0
  • Control del PC: la IA puede mover el ratón, hacer clic, escribir, pulsar
    teclas, arrastrar y usar la rueda (<PC_VER/>, <PC_CLIC/>, <PC_ESCRIBIR>…).
    Localiza las cosas por los elementos de las ventanas (botones, campos,
    menús…) y por una cuadrícula para lo que no los tiene (juegos, imágenes…).
  • Precauciones, cada una se puede activar o desactivar: confirmación antes de
    acciones peligrosas, freno de emergencia (tecla o ratón a una esquina),
    límite de pasos, no actuar en juegos a pantalla completa y aviso en pantalla.
  • El control del PC se activa/desactiva en Configuración y desde la bandeja.

Novedades 1.2.0
  • Visión: la IA puede hacer capturas de pantalla y fotos con la cámara
    (<CAPTURA/>, <CAMARA/>) sin pedir confirmación, y recibe la imagen.
  • Fecha y hora en cada mensaje (se activa/desactiva en Configuración → General).
  • Precarga del modelo de transcripción (Whisper/Vosk) y del modelo de Ollama al iniciar.
  • «Escribir mensaje» desde el icono de la bandeja (clic izquierdo o menú).
  • Orbe rediseñado: colores por modo con transiciones suaves y sin parpadeos.
  • Memoria persistente que la IA puede ampliar, modificar y borrar.
  • Recordatorios con sonido y notificación a la hora indicada.
  • Muchos arreglos (ver el resumen de cambios entregado con esta versión).
"""

APP_VERSION = "1.3.6"      # interna: no se muestra al usuario (ver version_info.txt)

import tkinter as tk
from tkinter import ttk, messagebox, colorchooser, filedialog, simpledialog
import threading
import queue
import collections
import json
import os
import sys
import re
import io
import base64
import html as _html
import platform
import math
import time
import wave
import struct
import calendar
import unicodedata
import subprocess
import urllib.request
import urllib.parse
import concurrent.futures
from datetime import datetime, timedelta
from html.parser import HTMLParser
from pathlib import Path
from typing import Tuple, Optional

IS_WINDOWS = platform.system() == "Windows"
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")   # sin el saludo de pygame en el log

APP_NAME  = "Rubencho AI"
APP_ID    = "RubenchoAI.Asistente"        # AppUserModelID: agrupa y fija el icono en la barra de tareas
IS_FROZEN = bool(getattr(sys, "frozen", False))      # ¿es la aplicación compilada (.exe)?
# Carpeta de la aplicación (donde está el .exe o el script) y de sus recursos
APP_HOME  = Path(sys.executable).resolve().parent if IS_FROZEN else Path(__file__).resolve().parent
RES_DIR   = Path(getattr(sys, "_MEIPASS", APP_HOME)) / "recursos"
ICON_ICO  = RES_DIR / "rubencho.ico"
ICON_TRAY = RES_DIR / "rubencho_bandeja.png"


def _data_dir() -> Path:
    """Carpeta de datos: %APPDATA%\\Rubencho AI (se puede cambiar con RUBENCHO_DATA_DIR)."""
    custom = os.environ.get("RUBENCHO_DATA_DIR", "").strip()
    if custom:
        return Path(custom)
    base = os.environ.get("APPDATA") if IS_WINDOWS else None
    return Path(base) / APP_NAME if base else Path.home() / f".{APP_NAME.lower().replace(' ', '')}"


# Carpeta de datos de la app (config, memoria, recordatorios, capturas, logs)
APP_DIR    = _data_dir()
LEGACY_DIR = Path.home() / ".voiceai"           # carpeta de las versiones anteriores


def _migrate_legacy_data():
    """
    La primera vez, copia los datos de las versiones anteriores (~/.voiceai) a la
    carpeta nueva. Se copian (no se mueven) para que las versiones antiguas sigan
    funcionando si se vuelven a abrir.
    """
    if APP_DIR.exists() or not LEGACY_DIR.is_dir() or os.environ.get("RUBENCHO_DATA_DIR"):
        return
    import shutil
    try:
        shutil.copytree(LEGACY_DIR, APP_DIR,
                        ignore=shutil.ignore_patterns("rubencho_consola.log", "*.tmp", "SingletonLock"))
        note = ["Datos copiados de la carpeta anterior (.voiceai)."]
        # El historial de conversaciones solía estar junto al programa: se copia aquí
        cfg_path = APP_DIR / "config.json"
        try:
            cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        except Exception:
            cfg = None
        if isinstance(cfg, dict):
            old_log = str(cfg.get("log_file_path") or "").strip()
            if old_log and Path(old_log).is_file():
                new_log = APP_DIR / "historial_conversaciones.txt"
                shutil.copy2(old_log, new_log)
                cfg["log_file_path"] = str(new_log)
                note.append(f"Historial copiado desde {old_log}.")
            vosk = str(cfg.get("vosk_model_path") or "").strip()
            if vosk and not Path(vosk).is_dir():
                cfg["vosk_model_path"] = ""
            tmp = cfg_path.with_suffix(".tmp")
            tmp.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(tmp, cfg_path)
        (APP_DIR / "migracion.txt").write_text(
            f"{datetime.now():%Y-%m-%d %H:%M}\n" + "\n".join(note) + "\n", encoding="utf-8")
    except Exception as e:
        try:
            APP_DIR.mkdir(parents=True, exist_ok=True)
            (APP_DIR / "migracion.txt").write_text(f"No se pudieron copiar los datos: {e}\n",
                                                   encoding="utf-8")
        except Exception:
            pass


_migrate_legacy_data()


def _set_app_user_model_id():
    """Nombre e icono propios en la barra de tareas (y poder fijar la app) en vez de «Python»."""
    if IS_WINDOWS:
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
        except Exception:
            pass


_set_app_user_model_id()


# ── Consola ───────────────────────────────────────────────────────────────────
# Con pythonw.exe no existen sys.stdout / sys.stderr: los print() se pierden y
# algunas librerías (barras de progreso, avisos) fallan al escribir en stderr.
# Se redirigen a %APPDATA%\\Rubencho AI\\rubencho_consola.log para poder diagnosticar.
def _setup_console_log():
    if sys.stdout is not None and sys.stderr is not None:
        return
    try:
        APP_DIR.mkdir(parents=True, exist_ok=True)
        log_path = APP_DIR / "rubencho_consola.log"
        try:
            if log_path.exists() and log_path.stat().st_size > 2_000_000:
                log_path.write_bytes(log_path.read_bytes()[-400_000:])
        except Exception:
            pass
        f = open(log_path, "a", encoding="utf-8", errors="replace", buffering=1)
        f.write(f"\n===== Rubencho AI · "
                f"{datetime.now():%Y-%m-%d %H:%M:%S} =====\n")
        if sys.stdout is None:
            sys.stdout = f
        if sys.stderr is None:
            sys.stderr = f
    except Exception:
        pass


_setup_console_log()

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

try:
    import speech_recognition as sr
    HAS_SR = True
except ImportError:
    HAS_SR = False

try:
    from PIL import Image, ImageDraw
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

try:
    import pystray
    HAS_TRAY = HAS_PIL
except ImportError:
    HAS_TRAY = False

try:
    from pynput import keyboard as _pynput_kb
    import pyaudio as _pyaudio
    HAS_PYNPUT = True
except ImportError:
    HAS_PYNPUT = False

try:
    import winsound
    HAS_WINSOUND = True
except ImportError:
    HAS_WINSOUND = False

# ── Global TTS mute flag ──────────────────────────────────────────────────────
_TTS_MUTED: bool = False


# ══════════════════════════════════════════════════════════════════════════════
#  UTILIDADES: fechas en español, texto, JSON
# ══════════════════════════════════════════════════════════════════════════════

# strftime("%A %B") devuelve los nombres en inglés en Windows (locale "C"),
# así que los nombres se generan a mano.
_DIAS_ES  = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
_MESES_ES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
             "agosto", "septiembre", "octubre", "noviembre", "diciembre"]


def fecha_larga(dt: datetime = None, hora: bool = True) -> str:
    """'martes 6 de octubre de 2026, 18:45'"""
    dt = dt or datetime.now()
    s = f"{_DIAS_ES[dt.weekday()]} {dt.day} de {_MESES_ES[dt.month - 1]} de {dt.year}"
    return f"{s}, {dt:%H:%M}" if hora else s


def fecha_corta(dt: datetime, now: datetime = None) -> str:
    """Formato compacto: 'hoy 18:30', 'mañana 9:00', 'viernes 9 10:00', 'lun 12 oct 10:00'."""
    now = now or datetime.now()
    d = (dt.date() - now.date()).days
    hhmm = f"{dt:%H:%M}"
    if d == 0:
        return f"hoy {hhmm}"
    if d == 1:
        return f"mañana {hhmm}"
    if d == -1:
        return f"ayer {hhmm}"
    if 1 < d < 7:
        return f"{_DIAS_ES[dt.weekday()]} {dt.day} {hhmm}"
    s = f"{_DIAS_ES[dt.weekday()][:3]} {dt.day} {_MESES_ES[dt.month - 1][:3]}"
    if dt.year != now.year:
        s += f" {dt.year}"
    return f"{s} {hhmm}"


def duracion_humana(delta: timedelta) -> str:
    secs = int(delta.total_seconds())
    if secs <= 0:
        return "ya"
    if secs < 60:
        return f"{secs} s"
    mins = secs // 60
    if mins < 60:
        return f"{mins} min"
    h, m = divmod(mins, 60)
    if h < 24:
        return f"{h} h {m} min" if m else f"{h} h"
    d, h = divmod(h, 24)
    return f"{d} d {h} h" if h else f"{d} d"


def _norm_text(s: str) -> str:
    """Minúsculas, sin tildes y con espacios simples (para comparar textos)."""
    s = unicodedata.normalize("NFKD", str(s or ""))
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", s.lower()).strip()


def _one_line(s: str) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip()


def _read_json(path: Path, default):
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[JSON] No se pudo leer {path.name}: {e}")
        try:   # conservar el fichero dañado para no perder datos
            path.replace(path.with_name(f"{path.stem}.danado_{int(time.time())}{path.suffix}"))
        except Exception:
            pass
    return default


def _atomic_write_json(path: Path, data):
    """Escribe JSON de forma atómica (evita ficheros a medias si se corta la luz)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def _open_path(path):
    """Abre un fichero o carpeta con la aplicación predeterminada del sistema."""
    try:
        if IS_WINDOWS:
            os.startfile(str(path))
        elif platform.system() == "Darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])
    except Exception as e:
        print(f"[Abrir] {e}")


# ══════════════════════════════════════════════════════════════════════════════
#  MÓDULO CMD – Ejecución de comandos del sistema
# ══════════════════════════════════════════════════════════════════════════════

# Tiempo máximo (segundos) que puede tardar un comando antes de cancelarse
CMD_TIMEOUT: int = 15

# Máximo de caracteres de salida que se devuelven a la IA
CMD_MAX_OUTPUT: int = 3000

# Si True, guarda cada comando ejecutado en cmd_log.txt (carpeta de datos)
CMD_LOG_ENABLED: bool = True

# Lista negra: estos comandos NUNCA se ejecutarán, independientemente de la config
CMD_BLOCKED: list = [
    "rm", "rmdir", "del", "rd", "format",
    "shutdown", "reboot", "halt", "poweroff",
    "sudo", "su", "runas",
    "reg",
]

# Patrón que detecta bloques <CMD>...</CMD> en la respuesta de la IA
_CMD_PATTERN = re.compile(r"<CMD>(.*?)</CMD>", re.DOTALL | re.IGNORECASE)

# Instrucciones que se añaden al system prompt cuando CMD está activado
_CMD_SYSTEM_ADDON = """
─── CAPACIDAD DE EJECUCIÓN DE COMANDOS (MODO AGENTE) ────────────────────────
Puedes ejecutar comandos reales en el sistema operativo del usuario.
Para hacerlo, incluye el comando en una etiqueta especial:

    <CMD>comando aquí</CMD>

FLUJO AGENTE — PUEDES ENCADENAR PASOS:
Tras recibir los resultados entre <RESULTADO>...</RESULTADO>, puedes:
  a) Emitir OTRO bloque <CMD> si necesitas más información o ejecutar el siguiente paso.
  b) Responder al usuario en lenguaje natural cuando hayas terminado completamente.

REGLAS:
1. Usa <CMD>...</CMD> SOLO cuando sea necesario para obtener información
   real del sistema o realizar una tarea concreta pedida por el usuario.
2. UN SOLO bloque <CMD> por turno. Usa && para pasos atómicos dentro del mismo comando.
3. Sé eficiente: no repitas comandos que ya ejecutaste en la misma sesión.
4. Nunca inventes resultados. Si el comando falla, diagnostica y prueba otra forma.
5. Antes del primer <CMD>, indica brevemente el plan de acción.
6. NUNCA ejecutes comandos destructivos (borrar masivamente, formatear).
7. Los comandos se ejecutan en cmd.exe de Windows (timeout de 15 s). Para abrir
   programas o webs usa "start" (vuelve al instante, no bloquea).
8. Para cálculos no triviales NO calcules de cabeza: usa PowerShell y da el
   resultado exacto.

Ejemplos:
- "Abre YouTube" / "Abre esta web"
  → <CMD>start "" "https://www.youtube.com"</CMD>

- "Abre el bloc de notas" / "Abre la calculadora"
  → <CMD>start "" notepad</CMD>     |     <CMD>start "" calc</CMD>

- "¿Cuánto es 3.312 entre 0,9?"
  → <CMD>powershell -NoProfile -Command "3312/0.9"</CMD>

- "¿Cuánta RAM libre tengo?"
  → "Voy a consultar la memoria del sistema."
    <CMD>systeminfo | findstr /C:"Memoria física disponible"</CMD>

- "¿Cuál es mi IP local?"
  → "Consulto la configuración de red."
    <CMD>ipconfig</CMD>

- "¿Qué procesos consumen más CPU?"
  → "Reviso los procesos activos."
    <CMD>tasklist /fo list | findstr /i "nombre imagen uso mem"</CMD>

- "¿Qué archivos hay en el escritorio?"
  → "Listo el escritorio."
    <CMD>dir "%USERPROFILE%\\Desktop"</CMD>

- "Crea la carpeta Pruebas en el escritorio"
  → "Creo la carpeta."
    <CMD>mkdir "%USERPROFILE%\\Desktop\\Pruebas"</CMD>
─────────────────────────────────────────────────────────────────────────────
"""


def _cmd_log(cmd: str, output: str):
    """Registra el comando ejecutado en el log CMD."""
    if not CMD_LOG_ENABLED:
        return
    try:
        APP_DIR.mkdir(exist_ok=True)
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        with open(APP_DIR / "cmd_log.txt", "a", encoding="utf-8") as f:
            f.write(f"[{ts}] CMD: {cmd}\nOUT:\n{output}\n{'─'*50}\n")
    except Exception:
        pass


# Separadores de comandos encadenados (cmd.exe / PowerShell)
_CMD_SPLIT_RE = re.compile(r"&&|\|\||[&|;\n]")
# Cmdlets de PowerShell destructivos (equivalentes a los comandos bloqueados)
_PS_BLOCKED_RE = re.compile(
    r"\b(remove-item|format-volume|clear-disk|initialize-disk|stop-computer|"
    r"restart-computer|remove-itemproperty)\b", re.IGNORECASE)
# Prefijos que solo lanzan otro programa: se mira el programa lanzado
_CMD_LAUNCHERS = {"start", "call", "cmd", "powershell", "pwsh"}


def _cmd_segment_root(seg: str) -> str:
    """Devuelve el programa real que ejecuta un segmento ('start "" shutdown /s' → 'shutdown')."""
    tokens = seg.strip().split()
    i = 0
    while i < len(tokens):
        tok = tokens[i].strip().strip('"').lstrip("@").lower()
        if not tok or tok.startswith("/") or tok.startswith("-"):
            i += 1               # título vacío "" o modificadores (/c, /min, -Command…)
            continue
        tok = os.path.basename(tok.replace("\\", "/"))
        if tok.endswith(".exe"):
            tok = tok[:-4]
        if tok in _CMD_LAUNCHERS:
            i += 1
            continue
        return tok
    return ""


def _cmd_is_allowed(cmd: str) -> Tuple[bool, str]:
    """Comprueba si el comando (y cada parte encadenada) está permitido. Devuelve (ok, motivo)."""
    if not cmd.strip():
        return False, "Comando vacío."
    blocked = {b.lower() for b in CMD_BLOCKED}
    for seg in _CMD_SPLIT_RE.split(cmd):
        root = _cmd_segment_root(seg)
        if root in blocked:
            return False, f"Comando '{root}' bloqueado por seguridad."
    m = _PS_BLOCKED_RE.search(cmd)
    if m:
        return False, f"Cmdlet '{m.group(1)}' bloqueado por seguridad."
    return True, ""


def _console_encoding() -> str:
    """Página de códigos de la consola (cp850 en Windows en español)."""
    if IS_WINDOWS:
        try:
            import ctypes
            import codecs
            enc = f"cp{ctypes.windll.kernel32.GetOEMCP()}"
            codecs.lookup(enc)
            return enc
        except Exception:
            return "cp850"
    return "utf-8"


_CONSOLE_ENCODING = _console_encoding()


def execute_command(cmd: str) -> str:
    """
    Ejecuta un comando de shell y devuelve su salida como string.
    Aplica lista negra, timeout y límite de caracteres.
    """
    cmd = cmd.strip()
    if not cmd:
        return "⚠️ Comando vacío."

    ok, reason = _cmd_is_allowed(cmd)
    if not ok:
        return f"🚫 Ejecución denegada: {reason}"

    try:
        if IS_WINDOWS:
            proc = subprocess.run(
                cmd, shell=True, capture_output=True,
                text=True, encoding=_CONSOLE_ENCODING, errors="replace",
                timeout=CMD_TIMEOUT, stdin=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        else:
            proc = subprocess.run(
                cmd, shell=True, capture_output=True,
                text=True, encoding="utf-8", errors="replace",
                timeout=CMD_TIMEOUT,
            )

        out = ""
        if proc.stdout:
            out += proc.stdout
        if proc.stderr:
            out += ("\n[STDERR]\n" if proc.stdout else "") + proc.stderr
        out = out.strip() or "(Sin salida — comando ejecutado sin errores)"

        if len(out) > CMD_MAX_OUTPUT:
            out = out[:CMD_MAX_OUTPUT] + f"\n… [truncado a {CMD_MAX_OUTPUT} chars]"

        _cmd_log(cmd, out)
        return out

    except subprocess.TimeoutExpired:
        msg = f"⏱️ Timeout: el comando superó {CMD_TIMEOUT}s y fue cancelado."
        _cmd_log(cmd, msg)
        return msg
    except FileNotFoundError:
        msg = f"❌ Comando no encontrado: '{cmd.split()[0]}'"
        _cmd_log(cmd, msg)
        return msg
    except Exception as e:
        msg = f"❌ Error al ejecutar: {e}"
        _cmd_log(cmd, msg)
        return msg


# ── Patrones de etiquetas especiales ─────────────────────────────────────────
_SEARCH_PATTERN = re.compile(r"<SEARCH>(.*?)</SEARCH>", re.DOTALL | re.IGNORECASE)
_FETCH_PATTERN  = re.compile(r"<FETCH>(.*?)</FETCH>",  re.DOTALL | re.IGNORECASE)

# ── Instrucciones adicionales para SEARCH/FETCH (se inyectan al addon CMD) ───
_WEB_SYSTEM_ADDON = """
─── BÚSQUEDA EN INTERNET — MODO AGENTE ──────────────────────────────────────
También puedes buscar en internet y leer páginas web usando estas etiquetas:

    <SEARCH>tu consulta aquí</SEARCH>    → Busca en DuckDuckGo y devuelve resultados
    <FETCH>https://url.com</FETCH>       → Descarga y lee el contenido de esa URL

FLUJO AGENTE — PUEDES ENCADENAR PASOS:
Tras recibir <RESULTADO_WEB>...</RESULTADO_WEB>, puedes:
  a) Emitir otra etiqueta <SEARCH>, <FETCH> o <CMD> si necesitas más datos.
  b) Responder al usuario cuando tengas suficiente información.

CUÁNDO USARLAS:
• Usa <SEARCH> cuando el usuario pregunte algo que requiera información actual,
  noticias, precios, datos recientes o que no tengas en tu contexto.
• Usa <FETCH> para leer el contenido completo de una URL concreta.
• NUNCA hagas SEARCH o FETCH si ya tienes la información suficiente en contexto.
• Cuando termines de recopilar datos, sintetiza y responde al usuario.

Ejemplos:
- "¿Cuál es el precio del Bitcoin hoy?"
  → <SEARCH>precio Bitcoin hoy EUR</SEARCH>

- "¿Qué ha pasado hoy en las noticias?"
  → <SEARCH>noticias hoy España</SEARCH>

- "Investiga las características del iPhone 16"
  → <SEARCH>iPhone 16 características especificaciones</SEARCH>

- "¿Qué dice esta página?" + URL
  → <FETCH>https://esa-url.com</FETCH>
─────────────────────────────────────────────────────────────────────────────
"""


def _ddg_real_url(href: str) -> str:
    """Convierte los enlaces de redirección de DuckDuckGo (/l/?uddg=...) en la URL real."""
    href = (href or "").strip()
    if href.startswith("//"):
        href = "https:" + href
    try:
        q = urllib.parse.urlparse(href)
        if "duckduckgo.com" in q.netloc and q.path.startswith("/l/"):
            target = urllib.parse.parse_qs(q.query).get("uddg", [""])[0]
            if target:
                return target
    except Exception:
        pass
    return href


class _DDGParser(HTMLParser):
    """
    Extrae resultados de DuckDuckGo (versión html y lite).
    Cada resultado empieza en el enlace del título (result__a / result-link) y
    el fragmento puede venir en <a>, <div> o <td> con clase result__snippet / result-snippet.
    """
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.results: list = []
        self._cur        = None
        self._field      = None     # "title" | "snippet"
        self._field_tag  = None

    def _flush(self):
        if self._cur and self._cur.get("title", "").strip():
            self._cur = {k: _one_line(v) for k, v in self._cur.items()}
            self.results.append(self._cur)
        self._cur = None

    def handle_starttag(self, tag, attrs):
        a   = dict(attrs)
        cls = a.get("class") or ""
        if tag == "a" and ("result__a" in cls or "result-link" in cls):
            self._flush()
            self._cur = {"title": "", "url": _ddg_real_url(a.get("href", "")), "snippet": ""}
            self._field, self._field_tag = "title", "a"
        elif (self._cur is not None and tag in ("a", "div", "td", "span")
              and ("result__snippet" in cls or "result-snippet" in cls)):
            self._field, self._field_tag = "snippet", tag

    def handle_endtag(self, tag):
        if self._field and tag == self._field_tag:
            self._field = self._field_tag = None

    def handle_data(self, data):
        if self._cur is not None and self._field:
            self._cur[self._field] += data

    def close(self):
        super().close()
        self._flush()


_WEB_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
           "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36")


def web_search(query: str, max_results: int = 5) -> str:
    """
    Busca en DuckDuckGo (sin API, sin clave) y devuelve los resultados
    como texto para que la IA los analice.
    """
    query = query.strip()
    if not query:
        return "⚠️ Consulta vacía."
    items, last_err = [], None
    for base in ("https://html.duckduckgo.com/html/?q=",
                 "https://lite.duckduckgo.com/lite/?q="):
        try:
            req = urllib.request.Request(base + urllib.parse.quote(query), headers={
                "User-Agent":      _WEB_UA,
                "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
            })
            with urllib.request.urlopen(req, timeout=10) as resp:
                page = resp.read().decode("utf-8", errors="replace")
            parser = _DDGParser()
            parser.feed(page)
            parser.close()
            items = [r for r in parser.results
                     if r.get("url") and "duckduckgo.com/y.js" not in r["url"]][:max_results]
            if items:
                break
        except Exception as e:
            last_err = e

    if not items:
        if last_err:
            return f"❌ Error al buscar: {last_err}"
        return f"No se encontraron resultados para: {query}"

    lines = [f"🔍 Resultados de búsqueda para: «{query}»\n"]
    for n, r in enumerate(items, 1):
        lines.append(f"{n}. {r.get('title') or 'Sin título'}")
        if r.get("url"):
            lines.append(f"   🔗 {r['url']}")
        if r.get("snippet"):
            lines.append(f"   {r['snippet']}")
        lines.append("")
    return "\n".join(lines).strip()


def web_fetch(url: str, max_chars: int = 4000) -> str:
    """
    Descarga una URL y extrae su texto plano (elimina HTML/JS/CSS).
    Devuelve los primeros max_chars caracteres.
    """
    url = url.strip().strip("<>\"'")
    if not url.startswith("http"):
        url = "https://" + url
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent":      _WEB_UA,
            "Accept":          "text/html,application/xhtml+xml,*/*;q=0.8",
            "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
        })
        with urllib.request.urlopen(req, timeout=12) as resp:
            raw   = resp.read(3_000_000)
            enc   = resp.headers.get_content_charset() or "utf-8"
            ctype = (resp.headers.get_content_type() or "").lower()
            try:
                page = raw.decode(enc, errors="replace")
            except LookupError:
                page = raw.decode("utf-8", errors="replace")

        if ctype and not any(t in ctype for t in ("html", "xml", "text", "json")):
            return f"⚠️ La URL no es una página de texto ({ctype}); no se puede leer."

        # Eliminar scripts, estilos y comentarios
        page = re.sub(r"<script[^>]*>.*?</script>", " ", page, flags=re.DOTALL|re.IGNORECASE)
        page = re.sub(r"<style[^>]*>.*?</style>",   " ", page, flags=re.DOTALL|re.IGNORECASE)
        page = re.sub(r"<noscript[^>]*>.*?</noscript>", " ", page, flags=re.DOTALL|re.IGNORECASE)
        page = re.sub(r"<!--.*?-->",                 " ", page, flags=re.DOTALL)
        # Convertir algunos tags a saltos de línea
        page = re.sub(r"<br\s*/?>|<p[^>]*>|</p>|<div[^>]*>|</div>|<li[^>]*>|<tr[^>]*>",
                      "\n", page, flags=re.IGNORECASE)
        page = re.sub(r"<h[1-6][^>]*>", "\n## ", page, flags=re.IGNORECASE)
        page = re.sub(r"</h[1-6]>",     "\n",    page, flags=re.IGNORECASE)
        # Quitar todos los demás tags y decodificar TODAS las entidades HTML
        text = _html.unescape(re.sub(r"<[^>]+>", "", page)).replace("\xa0", " ")
        # Comprimir espacios
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = text.strip()

        if not text:
            return "⚠️ No se pudo extraer texto de la página."
        if len(text) > max_chars:
            text = text[:max_chars] + f"\n… [contenido truncado a {max_chars} chars]"
        return f"📄 Contenido de {url}:\n\n{text}"

    except Exception as e:
        return f"❌ Error al obtener la página: {e}"


# ══════════════════════════════════════════════════════════════════════════════
#  MÓDULO BROWSER AGENT – Control de navegador web con Playwright
# ══════════════════════════════════════════════════════════════════════════════

try:
    from playwright.sync_api import sync_playwright as _sync_playwright
    _PLAYWRIGHT_AVAILABLE = True
except ImportError:
    _PLAYWRIGHT_AVAILABLE = False

# ── Patrones de etiquetas WEB_* ───────────────────────────────────────────────
_WEB_GOTO_PAT   = re.compile(r"<WEB_GOTO>(.*?)</WEB_GOTO>",     re.DOTALL | re.IGNORECASE)
_WEB_CLICK_PAT  = re.compile(r"<WEB_CLICK>(.*?)</WEB_CLICK>",   re.DOTALL | re.IGNORECASE)
_WEB_TYPE_PAT   = re.compile(r"<WEB_TYPE>(.*?)</WEB_TYPE>",     re.DOTALL | re.IGNORECASE)
_WEB_SELECT_PAT = re.compile(r"<WEB_SELECT>(.*?)</WEB_SELECT>", re.DOTALL | re.IGNORECASE)
_WEB_CHECK_PAT  = re.compile(r"<WEB_CHECK>(.*?)</WEB_CHECK>",   re.DOTALL | re.IGNORECASE)
_WEB_SCROLL_PAT = re.compile(r"<WEB_SCROLL>(.*?)</WEB_SCROLL>", re.DOTALL | re.IGNORECASE)
_WEB_BACK_PAT   = re.compile(r"<WEB_BACK\s*/?>",                re.DOTALL | re.IGNORECASE)
_WEB_READ_PAT   = re.compile(r"<WEB_READ\s*/?>",                re.DOTALL | re.IGNORECASE)
_WEB_KEY_PAT    = re.compile(r"<WEB_KEY>(.*?)</WEB_KEY>",       re.DOTALL | re.IGNORECASE)

_ALL_WEB_PATS = [
    _WEB_GOTO_PAT, _WEB_CLICK_PAT, _WEB_TYPE_PAT, _WEB_SELECT_PAT,
    _WEB_CHECK_PAT, _WEB_SCROLL_PAT, _WEB_BACK_PAT, _WEB_READ_PAT,
    _WEB_KEY_PAT,
]

def _has_web_action(text: str) -> bool:
    return any(p.search(text) for p in _ALL_WEB_PATS)


# ── System prompt addon para el navegador ────────────────────────────────────
_BROWSER_SYSTEM_ADDON = """
─── CONTROL DE NAVEGADOR WEB (MODO AGENTE) ──────────────────────────────────
Puedes controlar un navegador web real (Chromium visible). Tienes estas acciones:

  <WEB_GOTO>https://url.com</WEB_GOTO>
      Navega a una URL. Recibirás el contenido completo de la página y TODOS
      los elementos interactivos numerados como [N].

  <WEB_CLICK>[N]</WEB_CLICK>
      Haz clic en el elemento número N (enlace, botón, etc.).
      Ejemplo:  <WEB_CLICK>[7]</WEB_CLICK>

  <WEB_TYPE>[N] | texto a escribir</WEB_TYPE>
      Escribe texto en el campo de entrada número N.
      USA SIEMPRE el separador | entre el número y el texto.
      Ejemplo:  <WEB_TYPE>[3] | usuario@email.com</WEB_TYPE>
      Ejemplo:  <WEB_TYPE>[4] | Mi contraseña segura</WEB_TYPE>

  <WEB_SELECT>[N] | opción visible</WEB_SELECT>
      Selecciona una opción en el desplegable número N.
      Escribe el texto de la opción tal como aparece en el snapshot.
      Ejemplo:  <WEB_SELECT>[5] | España</WEB_SELECT>

  <WEB_CHECK>[N]</WEB_CHECK>
      Marca o desmarca la casilla/radio número N.
      Ejemplo:  <WEB_CHECK>[9]</WEB_CHECK>

  <WEB_KEY>[N] | tecla</WEB_KEY>
      Pulsa una tecla especial en el elemento N.
      Teclas válidas: Enter, Tab, Escape, ArrowDown, ArrowUp, Backspace, Delete
      Ejemplo:  <WEB_KEY>[3] | Enter</WEB_KEY>

  <WEB_SCROLL>down|600</WEB_SCROLL>
      Scroll por la página. Dirección: down/up/abajo/arriba. Píxeles opcional (defecto 600).
      Ejemplo:  <WEB_SCROLL>down|800</WEB_SCROLL>

  <WEB_BACK/>
      Vuelve a la página anterior del historial del navegador.

  <WEB_READ/>
      Re-lee la página actual. Útil cuando la página cambia dinámicamente
      (pop-ups, validaciones, carga AJAX) sin haber navegado.

═══ CÓMO LEER EL SNAPSHOT DE PÁGINA ═══════════════════════════════════════
Cada vez que navegues o interactúes, recibirás un bloque como éste:

  ╔══ URL: https://... / TÍTULO: ...
  ║ CONTENIDO DE LA PÁGINA
  ║ [texto visible, puede estar truncado a 3000 chars]
  ║ ELEMENTOS INTERACTIVOS
  ║   [1]  🔗 ENLACE      "Inicio" → https://...
  ║   [2]  🔘 BOTÓN       "Buscar"
  ║   [3]  ✏️  CAMPO TEXT  "Nombre" (placeholder: "Tu nombre completo")
  ║   [4]  ✏️  CAMPO EMAIL "Email"  [valor actual: "ya@puesto.com"]
  ║   [5]  🔽 DESPLEGABLE "País" [seleccionado: "España"]
  ║            Opciones: España | Francia | Alemania | Italia...
  ║   [6]  ☑  CASILLA     "Acepto los términos y condiciones"
  ║   [7]  ○  RADIO       "Pago con tarjeta"
  ║   [8]  📝 ÁREA TEXTO  "Mensaje" [contiene texto]
  ║   [9]  🔘 BOTÓN       "Enviar" ⛔DESACTIVADO

ICONOS:  🔗=enlace  🔘=botón  ✏️=campo  🔽=desplegable  ☑/☐=casilla  ●/○=radio  📝=área
⛔DESACTIVADO = no puedes interactuar con ese elemento todavía.

═══ REGLAS DE USO ══════════════════════════════════════════════════════════
1.  UNA SOLA ACCIÓN POR TURNO. Espera el resultado antes de la siguiente.
2.  Usa SIEMPRE el número [N] del snapshot más reciente.
3.  Si un elemento no aparece, prueba <WEB_SCROLL>down|600</WEB_SCROLL> para desplazarte.
4.  Para formularios: rellena TODOS los campos obligatorios y luego haz clic en el botón.
5.  Si la página cambia sin navegar (validación, AJAX), usa <WEB_READ/> para actualizarla.
6.  Después de un WEB_CLICK en un botón de envío, espera el resultado para confirmar.
7.  Informa al usuario de cada acción: "Hago clic en Registrarse…", "Relleno el email…".
8.  Si algo falla (elemento no encontrado, error), analiza el snapshot y ajusta el plan.

═══ EJEMPLO DE FLUJO ═══════════════════════════════════════════════════════
  Usuario: "Busca 'monitor 4k' en Amazon"
  1. <WEB_GOTO>https://www.amazon.es</WEB_GOTO>
  2. [snapshot] → ve el campo de búsqueda en [3]
     <WEB_TYPE>[3] | monitor 4k</WEB_TYPE>
  3. [snapshot] → ve botón "Ir" en [4]
     <WEB_CLICK>[4]</WEB_CLICK>
  4. [snapshot con resultados] → resume los mejores resultados al usuario
─────────────────────────────────────────────────────────────────────────────
"""


class BrowserAgent:
    """
    Controlador de navegador web usando Playwright (Chromium).
    Gestiona una sola ventana visible. Singleton por proceso.

    Genera snapshots textuales con elementos numerados [N] para que la IA
    pueda referirse a ellos por índice al hacer clic, escribir, etc.
    """

    # ── JavaScript inyectado en la página ─────────────────────────────────

    # Asigna data-ai-idx a todos los elementos interactivos visibles
    _JS_INJECT = r"""
    (function() {
        const SEL = [
            'a[href]',
            'button:not([disabled])',
            'button[disabled]',
            'input:not([type=hidden])',
            'select',
            'textarea',
            '[role="button"]',
            '[role="link"]',
            '[role="checkbox"]',
            '[role="radio"]',
            '[role="menuitem"]',
            '[role="option"]',
            '[role="tab"]',
            '[role="combobox"]',
            '[contenteditable="true"]',
        ].join(',');
        let idx = 1;
        document.querySelectorAll('[data-ai-idx]').forEach(
            el => el.removeAttribute('data-ai-idx'));
        document.querySelectorAll(SEL).forEach(el => {
            const r = el.getBoundingClientRect();
            if (r.width > 0 && r.height > 0 &&
                r.top < window.innerHeight + 800 &&
                r.bottom > -800) {
                el.setAttribute('data-ai-idx', String(idx++));
            }
        });
        return idx - 1;
    })();
    """

    # Extrae datos de todos los elementos con data-ai-idx
    _JS_ELEMENTS = r"""
    (function() {
        const items = [];
        document.querySelectorAll('[data-ai-idx]').forEach(el => {
            const tag  = el.tagName.toLowerCase();
            const role = (el.getAttribute('role') || '').toLowerCase();
            const typ  = (el.type || '').toLowerCase();
            const r    = el.getBoundingClientRect();
            if (r.width === 0 || r.height === 0) return;

            const label = (
                el.getAttribute('aria-label') ||
                el.getAttribute('title')       ||
                el.getAttribute('placeholder') ||
                (el.innerText || '').trim()    ||
                el.value                       ||
                el.name                        ||
                el.id                          || ''
            ).replace(/\s+/g,' ').trim().slice(0, 120);

            items.push({
                idx:      el.getAttribute('data-ai-idx'),
                tag,      role,      typ,       label,
                href:     (el.href || '').slice(0, 140),
                value:    (el.value || '').slice(0, 80),
                checked:  !!el.checked,
                disabled: !!el.disabled,
                options:  tag === 'select'
                    ? Array.from(el.options).map(o => o.text.trim()).slice(0, 20)
                    : [],
                placeholder: (el.placeholder || '').slice(0, 60),
            });
        });
        return items;
    })();
    """

    # Extrae texto limpio del body
    _JS_TEXT = r"""
    (function() {
        const clone = document.body.cloneNode(true);
        clone.querySelectorAll(
            'script,style,noscript,svg,canvas,iframe,nav,footer,header,' +
            '[aria-hidden="true"],[role="navigation"],[role="banner"]'
        ).forEach(e => e.remove());
        return clone.innerText
            .replace(/[ \t]+/g,' ')
            .replace(/\n{3,}/g,'\n\n')
            .trim();
    })();
    """

    def __init__(self):
        self._pw      = None
        self._browser = None
        self._ctx     = None
        self._page    = None
        self._lock    = threading.Lock()
        self._ready   = False
        # La API síncrona de Playwright solo funciona en el hilo que la creó.
        # Cada petición a la IA corre en un hilo distinto, así que todas las
        # operaciones del navegador se ejecutan en este único hilo dedicado.
        self._executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="browser")

    def _run(self, fn, *args) -> str:
        try:
            return self._executor.submit(fn, *args).result(timeout=150)
        except concurrent.futures.TimeoutError:
            return "❌ El navegador no respondió a tiempo (150 s)."
        except Exception as e:
            return f"❌ Error del navegador: {e}"

    # API pública (segura desde cualquier hilo)
    def goto(self, url: str) -> str:          return self._run(self._goto, url)
    def click(self, ref: str) -> str:         return self._run(self._click, ref)
    def type_text(self, raw: str) -> str:     return self._run(self._type_text, raw)
    def select_option(self, raw: str) -> str: return self._run(self._select_option, raw)
    def check_toggle(self, ref: str) -> str:  return self._run(self._check_toggle, ref)
    def press_key(self, raw: str) -> str:     return self._run(self._press_key, raw)
    def scroll(self, raw: str) -> str:        return self._run(self._scroll, raw)
    def back(self) -> str:                    return self._run(self._back)
    def read(self) -> str:                    return self._run(self._read)

    # ── Ciclo de vida ─────────────────────────────────────────────────────

    def _ensure_ready(self):
        if self._ready:
            # Si el usuario cerró la ventana del navegador, se vuelve a abrir
            try:
                if (self._page is not None and not self._page.is_closed()
                        and self._browser is not None and self._browser.is_connected()):
                    return
            except Exception:
                pass
            self._close()
        if not _PLAYWRIGHT_AVAILABLE:
            raise RuntimeError(
                "El control del navegador no está disponible (falta Playwright).\n"
                "Instálalo con:\n"
                "  pip install playwright\n"
                "  playwright install chromium"
            )
        try:
            return self._launch_browser()
        except Exception as e:
            if "Executable doesn't exist" not in str(e) and "playwright install" not in str(e):
                raise
            # Falta el navegador Chromium: se descarga una vez (≈150 MB) y se reintenta
            print("[Web] Falta Chromium: descargándolo…")
            ok, msg = install_playwright_chromium()
            if not ok:
                raise RuntimeError(f"No se pudo descargar el navegador: {msg}")
            self._close()
            return self._launch_browser()

    def _launch_browser(self):
        self._pw      = _sync_playwright().start()
        self._browser = self._pw.chromium.launch(
            headless=False,
            args=["--start-maximized", "--disable-infobars"],
        )
        self._ctx  = self._browser.new_context(
            viewport={"width": 1280, "height": 800},
            locale="es-ES",
            timezone_id="Europe/Madrid",
        )
        # Interceptar diálogos automáticamente (alert/confirm/prompt)
        self._page = self._ctx.new_page()
        self._page.on("dialog", lambda d: d.dismiss())
        self._ready = True

    def close(self):
        """Cierra el navegador y libera recursos (desde cualquier hilo)."""
        if self._ready:
            self._run(self._close)

    def _close(self):
        try:
            if self._browser: self._browser.close()
        except Exception:
            pass
        try:
            if self._pw: self._pw.stop()
        except Exception:
            pass
        self._ready   = False
        self._browser = None
        self._ctx     = None
        self._page    = None
        self._pw      = None
        return "✅ Navegador cerrado."

    # ── Snapshot ──────────────────────────────────────────────────────────

    def _wait_stable(self, timeout: int = 5_000):
        """Espera a que la red esté inactiva (con tolerancia a timeouts)."""
        try:
            self._page.wait_for_load_state("domcontentloaded", timeout=timeout)
        except Exception:
            pass
        try:
            self._page.wait_for_load_state("networkidle", timeout=3_000)
        except Exception:
            pass

    def _snapshot(self, max_text: int = 3000) -> str:
        """
        Genera el snapshot completo de la página:
        URL + título + texto visible + lista de elementos [N].
        """
        p = self._page
        url   = p.url
        title = p.title() or "(sin título)"

        # 1. Inyectar índices en el DOM
        try:
            total = p.evaluate(self._JS_INJECT)
        except Exception:
            total = 0

        # 2. Extraer texto limpio
        try:
            body_text = p.evaluate(self._JS_TEXT) or ""
        except Exception:
            body_text = ""
        if len(body_text) > max_text:
            body_text = (body_text[:max_text]
                         + f"\n… [texto truncado — {len(body_text)-max_text} chars adicionales]")

        # 3. Extraer datos de elementos
        try:
            elems = p.evaluate(self._JS_ELEMENTS) or []
        except Exception:
            elems = []

        # 4. Formatear
        out = [
            "╔══════════════════════════════════════════════════════════════",
            f"║  URL    : {url}",
            f"║  TÍTULO : {title}",
            "╠══════════════════════════════════════════════════════════════",
            "║  CONTENIDO VISIBLE DE LA PÁGINA",
            "╟──────────────────────────────────────────────────────────────",
            body_text or "(página sin contenido textual)",
            "╠══════════════════════════════════════════════════════════════",
            f"║  ELEMENTOS INTERACTIVOS  [{total} indexados]",
            "║  (Referencia por número: [N]  •  Usa ese número en WEB_CLICK, WEB_TYPE, etc.)",
            "╟──────────────────────────────────────────────────────────────",
        ]

        for el in elems:
            n        = el["idx"]
            tag      = el["tag"]
            role     = el["role"]
            typ      = el["typ"]
            label    = el["label"] or el["placeholder"] or el["value"] or "(sin etiqueta)"
            disabled = "  ⛔DESACTIVADO" if el["disabled"] else ""

            # Tipo efectivo
            eff = typ or role or tag

            if tag == "a":
                href = el["href"]
                out.append(f"  [{n:>3}]  🔗 ENLACE       \"{label}\"  → {href}{disabled}")

            elif tag in ("button",) or eff in ("button", "submit", "reset", "menuitem"):
                out.append(f"  [{n:>3}]  🔘 BOTÓN        \"{label}\"{disabled}")

            elif tag == "input":
                if typ == "checkbox":
                    mark = "☑" if el["checked"] else "☐"
                    out.append(f"  [{n:>3}]  {mark}  CASILLA      \"{label}\"{disabled}")
                elif typ == "radio":
                    mark = "●" if el["checked"] else "○"
                    out.append(f"  [{n:>3}]  {mark}  RADIO        \"{label}\"{disabled}")
                elif typ in ("submit", "button", "image", "reset"):
                    out.append(f"  [{n:>3}]  🔘 BOTÓN        \"{label}\"{disabled}")
                elif typ == "file":
                    out.append(f"  [{n:>3}]  📎 ARCHIVO      \"{label}\"{disabled}")
                else:
                    ph = f"  (escribe aquí: \"{el['placeholder']}\")" if el["placeholder"] else ""
                    cv = f"  [valor: \"{el['value']}\"]" if el["value"] else ""
                    t_label = typ.upper() if typ else "TEXT"
                    out.append(f"  [{n:>3}]  ✏️  CAMPO {t_label:<7} \"{label}\"{ph}{cv}{disabled}")

            elif tag == "select":
                cur  = f"  [seleccionado: \"{el['value']}\"]" if el["value"] else ""
                opts = el["options"]
                opts_str = "  |  ".join(opts[:8])
                extra    = f"  (+{len(opts)-8} más)" if len(opts) > 8 else ""
                out.append(f"  [{n:>3}]  🔽 DESPLEGABLE  \"{label}\"{cur}{disabled}")
                if opts:
                    out.append(f"           Opciones:  {opts_str}{extra}")

            elif tag == "textarea":
                cv = "  [contiene texto]" if el["value"] else ""
                out.append(f"  [{n:>3}]  📝 ÁREA TEXTO   \"{label}\"{cv}{disabled}")

            elif tag == "[contenteditable]" or role == "textbox":
                out.append(f"  [{n:>3}]  ✏️  EDITABLE      \"{label}\"{disabled}")

            else:
                out.append(f"  [{n:>3}]  ◻️  {tag.upper():<12} \"{label}\"{disabled}")

        if not elems:
            out.append("  (No se encontraron elementos interactivos visibles en esta zona)")
        out.append("╚══════════════════════════════════════════════════════════════")
        return "\n".join(out)

    # ── Acciones públicas ─────────────────────────────────────────────────

    def _goto(self, url: str) -> str:
        with self._lock:
            self._ensure_ready()
            if not url.startswith(("http://", "https://")):
                url = "https://" + url
            try:
                self._page.goto(url, wait_until="domcontentloaded", timeout=20_000)
            except Exception as e:
                if "timeout" not in str(e).lower():
                    return f"❌ Error navegando a {url}:\n{e}"
            self._wait_stable()
            return self._snapshot()

    def _click(self, ref: str) -> str:
        with self._lock:
            self._ensure_ready()
            m = re.search(r"\d+", ref.strip())
            if not m:
                return f"❌ Referencia inválida: '{ref}'. Usa el número entre corchetes, p.ej. [3]."
            n = m.group(0)
            try:
                self._page.evaluate(f"""
                    (() => {{
                        const el = document.querySelector('[data-ai-idx="{n}"]');
                        if (!el) throw new Error('Elemento [{n}] no encontrado');
                        el.scrollIntoView({{block:'center'}});
                        el.click();
                    }})();
                """)
                self._wait_stable()
                snap = self._snapshot()
                return f"✅ Clic en [{n}]\n\n{snap}"
            except Exception as e:
                return (f"❌ No pude hacer clic en [{n}]: {e}\n"
                        f"Prueba <WEB_SCROLL>down|400</WEB_SCROLL> y vuelve a intentarlo.")

    def _type_text(self, raw: str) -> str:
        """Formato esperado: '[N] | texto'  o  '[N] texto'"""
        with self._lock:
            self._ensure_ready()
            m = re.match(r"\[?(\d+)\]?\s*[|:]\s*(.*)", raw, re.DOTALL)
            if not m:
                m = re.match(r"(\d+)\s+(.*)", raw, re.DOTALL)
            if not m:
                return ("❌ Formato incorrecto.\n"
                        "Usa: <WEB_TYPE>[N] | texto</WEB_TYPE>\n"
                        "Ejemplo: <WEB_TYPE>[3] | usuario@email.com</WEB_TYPE>")
            n, text = m.group(1), m.group(2).strip()
            try:
                handle = self._page.query_selector(f'[data-ai-idx="{n}"]')
                if not handle:
                    return f"❌ Elemento [{n}] no encontrado en la página actual."
                handle.scroll_into_view_if_needed()
                handle.click()
                handle.fill(text)
                snap = self._snapshot()
                return f"✅ Texto introducido en [{n}]: \"{text[:60]}{'…' if len(text)>60 else ''}\"\n\n{snap}"
            except Exception as e:
                return f"❌ Error al escribir en [{n}]: {e}"

    def _select_option(self, raw: str) -> str:
        """Formato: '[N] | opción visible'"""
        with self._lock:
            self._ensure_ready()
            m = re.match(r"\[?(\d+)\]?\s*[|:]\s*(.*)", raw, re.DOTALL)
            if not m:
                return "❌ Usa: <WEB_SELECT>[N] | opción</WEB_SELECT>"
            n, value = m.group(1), m.group(2).strip()
            try:
                sel = f'[data-ai-idx="{n}"]'
                # Intentar por label, luego por value
                try:
                    self._page.select_option(sel, label=value)
                except Exception:
                    self._page.select_option(sel, value=value)
                snap = self._snapshot()
                return f"✅ Seleccionado '{value}' en [{n}]\n\n{snap}"
            except Exception as e:
                return f"❌ Error al seleccionar en [{n}]: {e}"

    def _check_toggle(self, ref: str) -> str:
        with self._lock:
            self._ensure_ready()
            m = re.search(r"\d+", ref.strip())
            if not m:
                return f"❌ Referencia inválida: '{ref}'"
            n = m.group(0)
            try:
                self._page.evaluate(f"""
                    (() => {{
                        const el = document.querySelector('[data-ai-idx="{n}"]');
                        if (!el) throw new Error('no encontrado');
                        el.scrollIntoView({{block:'center'}});
                        el.click();
                    }})();
                """)
                snap = self._snapshot()
                return f"✅ Casilla [{n}] activada/desactivada\n\n{snap}"
            except Exception as e:
                return f"❌ Error en [{n}]: {e}"

    def _press_key(self, raw: str) -> str:
        """Formato: '[N] | Enter'  o  '[N] | ArrowDown'"""
        with self._lock:
            self._ensure_ready()
            m = re.match(r"\[?(\d+)\]?\s*[|:]\s*(.*)", raw.strip(), re.DOTALL)
            if not m:
                return "❌ Usa: <WEB_KEY>[N] | tecla</WEB_KEY>"
            n, key = m.group(1), m.group(2).strip()
            try:
                handle = self._page.query_selector(f'[data-ai-idx="{n}"]')
                if handle:
                    handle.press(key)
                else:
                    self._page.keyboard.press(key)
                self._wait_stable()
                snap = self._snapshot()
                return f"✅ Tecla '{key}' pulsada en [{n}]\n\n{snap}"
            except Exception as e:
                return f"❌ Error al pulsar '{key}' en [{n}]: {e}"

    def _scroll(self, raw: str) -> str:
        with self._lock:
            self._ensure_ready()
            parts = re.split(r"[|,\s]+", raw.strip().lower())
            direction = parts[0] if parts else "down"
            try:
                amount = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 600
            except (ValueError, IndexError):
                amount = 600
            dy = amount if direction in ("down", "abajo") else -amount
            self._page.evaluate(f"window.scrollBy(0, {dy})")
            time.sleep(0.3)
            snap = self._snapshot()
            return f"✅ Scroll {'↓' if dy > 0 else '↑'} {abs(dy)}px\n\n{snap}"

    def _back(self) -> str:
        with self._lock:
            self._ensure_ready()
            try:
                self._page.go_back(wait_until="domcontentloaded", timeout=8_000)
                self._wait_stable()
                return "✅ Navegado atrás\n\n" + self._snapshot()
            except Exception as e:
                return f"❌ No se pudo volver atrás: {e}"

    def _read(self) -> str:
        with self._lock:
            self._ensure_ready()
            self._wait_stable(timeout=2_000)
            return self._snapshot()


# Singleton global del agente de navegador
_browser_agent: "BrowserAgent | None" = None

def get_browser_agent() -> BrowserAgent:
    global _browser_agent
    if _browser_agent is None:
        _browser_agent = BrowserAgent()
    return _browser_agent


def _execute_web_actions(response: str, ui_q: "queue.Queue") -> str:
    """
    Detecta y ejecuta TODAS las acciones WEB_* presentes en `response`.
    Devuelve un bloque de resultados para re-inyectar a la IA.
    """
    agent   = get_browser_agent()
    results = []

    def _add(action: str, result: str):
        results.append(f"<ACCION_WEB>{action}</ACCION_WEB>\n"
                       f"<RESULTADO_WEB>\n{result}\n</RESULTADO_WEB>")
        ui_q.put(("popup_chunk", f"\n{result[:200]}{'…' if len(result)>200 else ''}\n"))

    for m in _WEB_GOTO_PAT.finditer(response):
        url = m.group(1).strip()
        ui_q.put(("popup_chunk", f"\n🌐  Navegando a: {url}\n"))
        _add(f"WEB_GOTO {url}", agent.goto(url))

    for m in _WEB_CLICK_PAT.finditer(response):
        ref = m.group(1).strip()
        ui_q.put(("popup_chunk", f"\n🖱️   Clic en: [{ref}]\n"))
        _add(f"WEB_CLICK [{ref}]", agent.click(ref))

    for m in _WEB_TYPE_PAT.finditer(response):
        raw = m.group(1)
        ui_q.put(("popup_chunk", "\n⌨️   Escribiendo en campo…\n"))
        _add(f"WEB_TYPE {raw[:60]}", agent.type_text(raw))

    for m in _WEB_SELECT_PAT.finditer(response):
        raw = m.group(1)
        ui_q.put(("popup_chunk", "\n🔽   Seleccionando opción…\n"))
        _add(f"WEB_SELECT {raw[:60]}", agent.select_option(raw))

    for m in _WEB_CHECK_PAT.finditer(response):
        ref = m.group(1).strip()
        ui_q.put(("popup_chunk", f"\n☑️   Toggle casilla [{ref}]\n"))
        _add(f"WEB_CHECK [{ref}]", agent.check_toggle(ref))

    for m in _WEB_KEY_PAT.finditer(response):
        raw = m.group(1)
        ui_q.put(("popup_chunk", "\n⌨️   Tecla especial…\n"))
        _add(f"WEB_KEY {raw[:40]}", agent.press_key(raw))

    for m in _WEB_SCROLL_PAT.finditer(response):
        raw = m.group(1).strip()
        ui_q.put(("popup_chunk", f"\n📜   Scroll {raw}…\n"))
        _add(f"WEB_SCROLL {raw}", agent.scroll(raw))

    if _WEB_BACK_PAT.search(response):
        ui_q.put(("popup_chunk", "\n⬅️   Volver atrás…\n"))
        _add("WEB_BACK", agent.back())

    if _WEB_READ_PAT.search(response):
        ui_q.put(("popup_chunk", "\n🔄   Re-leyendo página…\n"))
        _add("WEB_READ", agent.read())

    return "\n\n".join(results)


# ══════════════════════════════════════════════════════════════════════════════
#  MÓDULO WHATSAPP – Comunicación con el bridge Baileys
# ══════════════════════════════════════════════════════════════════════════════

import urllib.request as _urlreq
import json as _json_wa

# Puerto del bridge (puede ser sobreescrito por la config)
_WA_PORT: int = 3847

# Patrón para detectar bloques <WA to="...">...</WA> en respuestas de la IA
_WA_PATTERN = re.compile(
    r'<WA\s+(?:to|para|contacto|a)\s*=\s*[\'"]([^\'"]+)[\'"]\s*>(.*?)</WA\s*>',
    re.DOTALL | re.IGNORECASE
)

# Lista de contactos (solo nombres) y lectura de mensajes de un chat
_WA_CONTACTS_PAT = re.compile(r"<WA_CONTACTOS\b(?P<attrs>[^>]*?)/?>(?:\s*</WA_CONTACTOS\s*>)?",
                              re.IGNORECASE)
_WA_READ_PAT = re.compile(r"<WA_LEER\b(?P<attrs>[^>]*?)(?:/>|>(?P<body>[^<]*)</WA_LEER\s*>|>)",
                          re.IGNORECASE | re.DOTALL)

# Patrón para mensajes a uno mismo: <WA_SELF>mensaje</WA_SELF>
_WA_SELF_PATTERN = re.compile(
    r"<WA_SELF>(.*?)</WA_SELF>",
    re.DOTALL | re.IGNORECASE
)

def _wa_system_addon(cfg: dict) -> str:
    """Instrucciones de WhatsApp según las opciones (leer, fotos, audios, máximo…)."""
    g = lambda k: cfg.get(k, DEFAULT_CONFIG.get(k))
    read = bool(g("whatsapp_read_enabled"))
    try:
        mx = max(1, int(float(g("whatsapp_read_max") or 20)))
    except (TypeError, ValueError):
        mx = 20
    lines = [
        "─── WHATSAPP ────────────────────────────────────────────────────────────────",
        "Puedes enviar WhatsApps a los contactos del usuario" +
        (" y leer sus chats" if read else "") + " cuando él te lo pida.",
        "",
        "    <WA_CONTACTOS/>                        → lista con los NOMBRES de sus contactos",
        "    <WA_CONTACTOS buscar=\"ana\"/>          → solo los que contienen «ana»",
    ]
    if read:
        extras = []
        if g("whatsapp_read_images"):
            extras.append("las fotos te llegan como imágenes")
        if g("whatsapp_read_audio"):
            extras.append("los audios te llegan transcritos")
        lines += [
            f"    <WA_LEER contacto=\"Mamá\" cantidad=\"5\"/>  → los últimos N mensajes del chat con esa",
            f"        persona, suyos y del usuario (máximo {mx})" +
            (f"; {' y '.join(extras)}" if extras else ""),
        ]
    lines += [
        "    <WA to=\"Mamá\">texto</WA>                → enviar un mensaje a un contacto",
        "    <WA_SELF>texto</WA_SELF>                 → enviarle una nota al propio usuario",
        "",
        "REGLAS:",
        "1. Usa el nombre del contacto tal y como sale en la lista. Si no sabes cómo lo tiene",
        "   guardado (\"mi madre\", \"el de clase\"…) o hay varios parecidos, mira antes",
        "   <WA_CONTACTOS/> y, si sigue habiendo dudas, pregunta al usuario.",
    ]
    if read:
        lines += [
            "2. Lee mensajes SOLO cuando el usuario lo pida (\"¿qué me ha dicho Mamá?\", \"léeme lo",
            "   último de Juan\", \"resúmeme el audio de Ana\") o cuando te pida contestar a alguien",
            "   y necesites saber de qué iba la conversación. TÚ decides cuántos leer: pocos (3-5)",
            "   si basta con lo último; más si pide un resumen de la conversación.",
            "3. Al contar lo recibido, resume con naturalidad: quién, qué y cuándo. Describe las",
            "   fotos y resume los audios; no leas todo literal salvo que te lo pida.",
            "4. Si te vuelve a preguntar por los mensajes de alguien («¿y ahora qué dice?», «¿te ha",
            "   contestado?», «¿qué me ha dicho?» otra vez), VUELVE A LEERLOS con <WA_LEER>: puede",
            "   haber mensajes nuevos y lo que leíste antes ya no vale. Nunca cuentes lo que pone un",
            "   mensaje sin haberlo leído en esta misma respuesta.",
        ]
    lines += [
        f"{5 if read else 2}. Lo que va dentro de <WA> se envía tal cual: escríbelo como si lo escribiera",
        "   el usuario (en primera persona, sin firmar como IA) y solo cuando te lo pida.",
        f"{6 if read else 3}. Nunca envíes a grupos ni inventes mensajes recibidos: espera al resultado.",
        f"{7 if read else 4}. No conoces ni des números de teléfono. Si el resultado dice que no tienes",
        "   permiso para escribir a alguien, díselo al usuario (se cambia en Configuración → WhatsApp).",
        "",
        "Ejemplos:",
        "  \"Dile a Mamá que llego tarde\" → \"Se lo digo. <WA to=\"Mamá\">Llegaré un poco tarde 👍</WA>\"",
    ]
    if read:
        lines += [
            "  \"¿Qué me ha mandado Juan?\" → \"<WA_LEER contacto=\"Juan\" cantidad=\"5\"/>\"",
            "     (recibes los mensajes) → \"Juan te ha mandado una foto de su perro y un audio",
            "     diciendo que mañana no puede quedar.\"",
            "  \"Contéstale a Ana que sí\" → primero <WA_LEER contacto=\"Ana\" cantidad=\"3\"/> para ver",
            "     qué te preguntó y luego <WA to=\"Ana\">…</WA> con la respuesta adecuada.",
        ]
    return "\n".join(lines)


# Instrucciones que se añaden al system prompt cuando WA está activado
_WA_SYSTEM_ADDON = """
─── INTEGRACIÓN WHATSAPP ────────────────────────────────────────────────────
Puedes enviar mensajes de WhatsApp al usuario y a sus contactos usando estas
etiquetas especiales:

Para enviarte un recordatorio/nota a ti mismo:
    <WA_SELF>texto del mensaje</WA_SELF>

Para enviar a un contacto (por nombre o número INDIVIDUAL, NUNCA un grupo):
    <WA to="Mamá">Hola, ¿qué tal?</WA>
    <WA to="+34612345678">Mensaje de texto aquí</WA>

REGLAS ESTRICTAS:
1. Úsalo SOLO cuando el usuario pida explícitamente enviar un mensaje WA.
2. Un solo bloque WA o WA_SELF por respuesta.
3. El texto dentro de las etiquetas ES el mensaje que se enviará tal cual.
4. Antes del bloque, confirma brevemente qué vas a hacer.
5. Cuando recibas <RESULTADO_WA>...</RESULTADO_WA>, informa al usuario.
6. NUNCA envíes mensajes sin que el usuario lo haya pedido claramente.
7. NUNCA envíes mensajes a grupos. Solo a contactos individuales o a ti mismo.
8. Si el usuario pide enviar a un grupo, explícale que esa función no está disponible.

Ejemplos:
- "Mándate una nota para mañana"
  → "Te mando una nota a tu chat."
    <WA_SELF>📌 Nota: recordar revisar el proyecto mañana</WA_SELF>

- "Dile a Mamá que llegaré tarde"
  → "Le escribo a Mamá."
    <WA to="Mamá">Llegaré tarde hoy, no te preocupes 👍</WA>

- "Envía al grupo de clase que no hay reunión"
  → "Lo siento, solo puedo enviar mensajes a contactos individuales, no a grupos."
─────────────────────────────────────────────────────────────────────────────
"""


def _wa_request(endpoint: str, method: str = "GET",
                body: dict = None, port: int = None, timeout: float = 10) -> dict:
    """Hace una petición HTTP al bridge de WhatsApp."""
    p   = port or _WA_PORT
    url = f"http://127.0.0.1:{p}/{endpoint.lstrip('/')}"
    try:
        data    = _json_wa.dumps(body).encode() if body else None
        headers = {"Content-Type": "application/json"} if data else {}
        req     = _urlreq.Request(url, data=data, headers=headers, method=method)
        with _urlreq.urlopen(req, timeout=timeout) as resp:
            return _json_wa.loads(resp.read().decode())
    except _urlreq.HTTPError as e:                  # el puente responde {ok:false, error}
        try:
            return _json_wa.loads(e.read().decode())
        except Exception:
            return {"ok": False, "error": str(e)}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def wa_status(port: int = None) -> dict:
    """Devuelve el estado del bridge: {connected, has_qr, self}"""
    return _wa_request("status", port=port)


def wa_send(to: str, message: str, port: int = None) -> str:
    """Envía un mensaje de WhatsApp al contacto/número indicado."""
    result = _wa_request("send", method="POST",
                         body={"to": to, "message": message}, port=port)
    if result.get("ok"):
        return f"✅ {result.get('message', 'Mensaje enviado.')}"
    return f"❌ Error WA: {result.get('error', 'desconocido')}"


def wa_send_self(message: str, port: int = None) -> str:
    """Envía un mensaje a tu propio chat de WhatsApp."""
    result = _wa_request("send_self", method="POST",
                         body={"message": message}, port=port)
    if result.get("ok"):
        return f"✅ {result.get('message', 'Mensaje enviado a ti mismo.')}"
    return f"❌ Error WA: {result.get('error', 'desconocido')}"


def wa_contacts(port: int = None) -> list:
    """Devuelve la lista de contactos de WhatsApp."""
    result = _wa_request("contacts", port=port)
    if result.get("ok"):
        return result.get("contacts", [])
    return []


def wa_start_bridge(port: int = 3847, bridge_js_path: str = None):
    """
    Arranca el bridge Node.js en segundo plano.
    Devuelve el proceso Popen o None si falla.
    """
    if bridge_js_path is None:
        for cand in (APP_HOME / "whatsapp" / "whatsapp_bridge.js", APP_HOME / "whatsapp_bridge.js"):
            if cand.exists():
                bridge_js_path = str(cand)
                break
        else:
            bridge_js_path = str(APP_HOME / "whatsapp" / "whatsapp_bridge.js")

    if not os.path.exists(bridge_js_path):
        print(f"[WA] No se encuentra el bridge: {bridge_js_path}")
        return None

    env = os.environ.copy()
    env["WHATSAPP_BRIDGE_PORT"] = str(port)
    env["RUBENCHO_WA_SESSION"] = str(APP_DIR / "whatsapp_session")
    env["RUBENCHO_WA_STORE"]   = str(APP_DIR / "whatsapp_store")

    try:
        if platform.system() == "Windows":
            proc = subprocess.Popen(
                ["node", bridge_js_path],
                env=env,
                cwd=str(Path(bridge_js_path).parent),
                creationflags=subprocess.CREATE_NO_WINDOW,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        else:
            proc = subprocess.Popen(
                ["node", bridge_js_path],
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        print(f"[WA] Bridge arrancado (PID {proc.pid}) en puerto {port}")
        return proc
    except FileNotFoundError:
        print("[WA] ❌ Node.js no encontrado. Instálalo desde https://nodejs.org")
        return None
    except Exception as e:
        print(f"[WA] Error arrancando bridge: {e}")
        return None


def wa_stop_bridge(proc, port: int = 3847):
    """Para el bridge enviando POST /stop y luego terminando el proceso."""
    try:
        _wa_request("stop", method="POST", port=port)
        time.sleep(0.8)
    except Exception:
        pass
    if proc and proc.poll() is None:
        try:
            proc.terminate()
        except Exception:
            pass


def wa_self_trigger_ok(text: str, cfg: dict) -> bool:
    """
    ¿Hay que contestar a este mensaje del chat propio? Si está activada la opción,
    solo cuando le llamas por una de tus palabras («asistente», «rubencho»…).
    """
    if not cfg.get("whatsapp_self_trigger", False):
        return True
    words = [w for w in (_norm_text(x) for x in
                         re.split(r"[,;\n]", str(cfg.get("whatsapp_self_trigger_words", "") or ""))) if w]
    if not words:
        return True
    t = _norm_text(text)
    return any(re.search(r"(?<!\w)" + re.escape(w) + r"(?!\w)", t) for w in words)


class _NoPopupQueue:
    """
    Cola de la interfaz que descarta el panel de respuesta (lo demás pasa igual).
    Se usa con lo que llega por tu chat propio de WhatsApp: la respuesta va allí.
    """
    DROP = {"open_popup_stream", "popup_chunk", "popup_image", "popup_stream_done", "close_popup"}

    def __init__(self, q):
        self._q = q

    def put(self, item, *a, **k):
        if isinstance(item, tuple) and item and item[0] in self.DROP:
            return
        self._q.put(item, *a, **k)

    def __getattr__(self, name):
        return getattr(self._q, name)


def wa_poll_messages(port: int = 3847) -> list:
    """
    Consulta GET /messages al bridge y devuelve los mensajes nuevos
    del chat propio. Vacía la cola en el bridge al consumirlos.
    """
    result = _wa_request("messages", port=port)
    if result.get("ok"):
        return result.get("messages", [])
    return []


def wa_refresh_contacts(port: int = None) -> dict:
    """Vuelve a descargar la agenda de WhatsApp (sin volver a escanear el QR)."""
    return _wa_request("contacts/refresh", method="POST", body={}, port=port, timeout=60)


def wa_relink(port: int = None) -> dict:
    """Desvincula el dispositivo y genera un QR nuevo (para recibir la agenda y el historial)."""
    return _wa_request("relink", method="POST", body={}, port=port, timeout=20)


def wa_history(jid: str, count: int, port: int = None) -> dict:
    """Últimos mensajes guardados de un chat individual: {ok, messages, total, requested}."""
    q = urllib.parse.urlencode({"jid": jid, "count": int(count)})
    return _wa_request(f"history?{q}", port=port, timeout=30)


def wa_media(jid: str, msg_id: str, port: int = None) -> dict:
    """Descarga la foto/audio/vídeo de un mensaje guardado: {ok, mimetype, base64, kind}."""
    q = urllib.parse.urlencode({"jid": jid, "id": msg_id})
    return _wa_request(f"media?{q}", port=port, timeout=90)


def wa_match_contact(query: str, contacts: list) -> Tuple[Optional[dict], list]:
    """
    Busca un contacto por su nombre. → (contacto, [])  si hay uno claro
                                     → (None, [candidatos]) si es ambiguo
                                     → (None, [])  si no hay ninguno
    """
    q = _norm_text(query).strip(" \"'.,:;!?¿¡")
    if not q:
        return None, []
    named = [c for c in contacts if c.get("name")]
    word = re.compile(rf"(^|[\s(\-]){re.escape(q)}($|[\s)\-.,])")
    tiers = [
        [c for c in named if _norm_text(c["name"]) == q],
        [c for c in named if word.search(_norm_text(c["name"]))],
        [c for c in named if _norm_text(c["name"]).startswith(q)],
        [c for c in named if q in _norm_text(c["name"])],
    ]
    for tier in tiers:
        if len(tier) == 1:
            return tier[0], []
        if len(tier) > 1:
            return None, tier
    return None, []


# ══════════════════════════════════════════════════════════════════════════════
#  INSTRUCCIONES PARA LA IA: cabecera, fecha/hora, visión, memoria, recordatorios
# ══════════════════════════════════════════════════════════════════════════════

_TOOLS_HEADER = """
═══ CÓMO USAR TUS HERRAMIENTAS ═════════════════════════════════════════════
Tienes herramientas reales que se activan escribiendo etiquetas especiales en tu
respuesta. El sistema detecta las etiquetas, las ejecuta y NO se las muestra ni
se las lee en voz alta al usuario (él solo ve/oye el resto del texto).
• Escribe las etiquetas EXACTAMENTE como se indica (mayúsculas, comillas y cierre).
• Una herramienta solo funciona si escribes su etiqueta: nunca digas que has hecho
  algo (guardar, recordar, mirar la pantalla…) sin haber escrito la etiqueta.
• Nunca inventes el resultado de una herramienta: espera a recibirlo.
• Si el resultado llega en un mensaje del sistema (<RESULTADO…>), úsalo para
  responder al usuario de forma natural.
"""

_DATETIME_ADDON = """
─── FECHA Y HORA ────────────────────────────────────────────────────────────
Fecha y hora actuales: {ahora}.
Cada mensaje del usuario empieza con una marca entre corchetes con el día y la
hora exactos en que lo envió, p.ej. [martes 6 de octubre de 2026, 18:45].
• Úsala para saber qué día y hora es y cuánto tiempo ha pasado entre mensajes
  (puede ser segundos, horas o días).
• Úsala para resolver "hoy", "mañana", "esta tarde", "el viernes"…
• NO escribas nunca esa marca en tus respuestas ni la menciones, salvo que el
  usuario pregunte la fecha o la hora.
"""

_NO_DATETIME_ADDON = """
─── FECHA Y HORA ────────────────────────────────────────────────────────────
No conoces la fecha ni la hora actuales. {como}
"""

_VISION_SYSTEM_ADDON = """
─── VISIÓN: CAPTURA DE PANTALLA Y CÁMARA ────────────────────────────────────
Puedes VER la pantalla del PC del usuario y lo que capta su cámara web.
El usuario te ha autorizado: NO pidas permiso ni confirmación, simplemente hazlo.

    <CAPTURA/>                   → captura de la pantalla donde está el ratón
    <CAPTURA pantalla="todas"/>  → captura de todos los monitores juntos
    <CAMARA/>                    → foto con la cámara web

Tras escribir la etiqueta recibirás la imagen en el siguiente mensaje
(<RESULTADO_CAPTURA>) y podrás analizarla para responder.

CUÁNDO USARLAS:
• "¿Qué ves en mi pantalla?", "mira esto", "¿qué pone aquí?", "ayúdame con este
  error", "¿qué opinas de lo que tengo abierto?", "resume lo que estoy leyendo"
  → <CAPTURA/>
• "¿Qué ves?", "mírame", "hazme una foto", "¿cómo voy vestido?",
  "¿qué tengo en la mano?", "¿hay alguien detrás de mí?"  → <CAMARA/>
• Si el usuario dice "esto", "aquí" o "lo que tengo delante" refiriéndose a algo
  que tú no puedes ver, haz la captura adecuada.

REGLAS:
1. Una sola captura por turno. Antes de la etiqueta di algo breve ("Echo un vistazo.").
2. Úsalas solo cuando haga falta ver algo; no en cada mensaje.
3. Al recibir la imagen céntrate en lo que pidió el usuario; no describas todo.
4. Si la imagen sale negra o vacía, díselo (puede que la cámara esté tapada).

Ejemplo:
  Usuario: "¿Qué tengo abierto en la pantalla?"
  Tú:      "A ver. <CAPTURA/>"
  (recibes la imagen) → "Tienes abierto Visual Studio Code con un archivo de Python…"
"""

_MEMORY_SYSTEM_ADDON = """
─── MEMORIA PERSISTENTE ─────────────────────────────────────────────────────
Tienes una memoria a largo plazo que se conserva entre conversaciones y aunque se
reinicie el PC. Más abajo tienes su contenido actual, con un número para cada dato.
Úsala SIEMPRE para personalizar tus respuestas y actuar como el usuario prefiere.

Para gestionarla (puedes hacerlo cuando quieras, sin pedir permiso):
    <MEMORIA_GUARDAR>dato a recordar</MEMORIA_GUARDAR>
    <MEMORIA_EDITAR id="N">texto nuevo completo del dato N</MEMORIA_EDITAR>
    <MEMORIA_BORRAR id="N"/>

GUARDA SOLO LO QUE DE VERDAD MERECE LA PENA RECORDAR (si dudas, no guardes):
✔ Lo que el usuario te pida expresamente recordar ("acuérdate de que…", "apúntate…").
✔ Datos personales estables: nombre, familia, mascotas, trabajo/estudios, ciudad,
  cumpleaños, gustos, alergias, equipo, coche, aficiones…
✔ Preferencias sobre cómo quiere que respondas o actúes
  (p.ej. "verifica siempre el tiempo en internet antes de responder").
✔ Proyectos o situaciones en curso que serán útiles en próximas conversaciones.
✘ NO guardes: charla trivial, preguntas puntuales, resultados de comandos o
  búsquedas, cosas que caducan enseguida, ni datos que ya estén en la memoria.
✘ Para avisos con fecha y hora usa un RECORDATORIO, no la memoria.

CÓMO:
• Una sola idea por dato, breve y en tercera persona ("Rubén tiene un perro llamado Toby").
• Si un dato cambia o se queda viejo, EDÍTALO (no crees uno nuevo duplicado).
• Si el usuario pide olvidar algo, o un dato es falso, BÓRRALO.
• No anuncies que guardas algo salvo que te lo hayan pedido; en ese caso basta con
  una confirmación breve ("Apuntado.").

Ejemplo:
  Usuario: "Acuérdate de que los martes tengo clase de inglés."
  Tú:      "Apuntado. <MEMORIA_GUARDAR>Rubén tiene clase de inglés los martes.</MEMORIA_GUARDAR>"
  Usuario: "Ya no voy a inglés, ahora es alemán."
  Tú:      "Vale, lo cambio. <MEMORIA_EDITAR id="3">Rubén tiene clase de alemán los martes.</MEMORIA_EDITAR>"

═══ CONTENIDO ACTUAL DE TU MEMORIA ═══
{memoria}
"""

_REMINDERS_SYSTEM_ADDON = """
─── RECORDATORIOS Y ALARMAS ─────────────────────────────────────────────────
Puedes programar recordatorios: a la hora indicada sonará un aviso en el PC del
usuario y aparecerá una notificación con el texto (también se lee en voz alta).

    <RECORDATORIO cuando="CUÁNDO">texto del aviso</RECORDATORIO>
    <RECORDATORIO cuando="CUÁNDO" repetir="diario">texto</RECORDATORIO>
    <RECORDATORIO_BORRAR id="N"/>

Valores de "cuando" (el sistema calcula la fecha exacta, no la calcules tú):
  • Dentro de un tiempo:  "+10m"  "+45m"  "+2h"  "+1h30m"  "+3d"
                          (m = minutos, h = horas, d = días)  ← úsalo para "en X minutos/horas"
  • Hoy / mañana:         "hoy 18:30"  "mañana 9:00"  "pasado mañana 10:00"
  • Día de la semana:     "viernes 17:00"  (el próximo viernes)
  • Fecha concreta:       "2026-12-24 20:00"  (AAAA-MM-DD HH:MM)  o  "24/12 20:00"
Valores de "repetir" (opcional): diario | laborables | semanal | mensual | anual

REGLAS:
1. Cuando el usuario pida que le recuerdes/avises/despiertes algo a una hora o
   dentro de un tiempo, escribe SIEMPRE la etiqueta <RECORDATORIO>. Decir "te
   avisaré" sin la etiqueta no programa nada.
2. Las horas en formato 24 h ("las 5 de la tarde" → 17:00).
3. Si dice un día sin hora ("mañana"), usa las 9:00. Si no dice ni día ni hora,
   pregúntale cuándo.
4. El texto debe ser el aviso tal y como debe leerse cuando suene, breve y claro
   ("Sacar la pizza del horno", "Llamar al dentista").
5. Confirma en pocas palabras ("Hecho, te aviso a las 18:30."). El sistema mostrará
   la fecha exacta calculada.
6. Para borrar o consultar recordatorios usa la lista de abajo (con sus números).
   Para cambiar uno: bórralo y crea otro.

Ejemplos:
  "Recuérdame en 20 minutos que saque la ropa"
    → "Vale. <RECORDATORIO cuando="+20m">Sacar la ropa de la lavadora</RECORDATORIO>"
  "Despiértame mañana a las 7 y media"
    → "Hecho. <RECORDATORIO cuando="mañana 7:30">¡Buenos días! Hora de levantarse</RECORDATORIO>"
  "Todos los días a las 10 de la noche recuérdame tomarme la pastilla"
    → "Hecho. <RECORDATORIO cuando="22:00" repetir="diario">Tomar la pastilla</RECORDATORIO>"
  "Quita el recordatorio de la ropa" (es el número 4)
    → "Quitado. <RECORDATORIO_BORRAR id="4"/>"

═══ RECORDATORIOS PENDIENTES ═══
{recordatorios}
"""

_THINK_SYSTEM_ADDON = """
─── PENSAR ANTES DE ACTUAR ──────────────────────────────────────────────────
Normalmente respondes directamente, sin razonar por dentro (es más rápido).
Si de verdad lo necesitas, puedes pensar con calma antes de responder: escribe
SOLO esta etiqueta, sin nada más, y se te volverá a hacer la misma petición con
tu modo de razonamiento activado (tarda unos segundos más):

    <PENSAR/>

Úsala SOLO cuando:
  • Sea realmente complicado: un problema de lógica o de varios pasos, un cálculo
    o razonamiento difícil, planificar algo largo o con muchas condiciones,
    programar, o una tarea larga de control del PC o del navegador.
  • Ya lo intentaste y salió mal (una herramienta falló, el resultado no es el
    esperado o el usuario te dice que te has equivocado) y ves que no es trivial.
NO la uses para lo normal: saludos, charlar, preguntas sencillas, datos que ya
sabes, abrir un programa, buscar en internet, enviar o leer un WhatsApp, poner un
recordatorio o guardar algo en la memoria. Eso hazlo directamente.

Antes de responder, pregúntate: «¿podría equivocarme si contesto sin pensarlo?».
Si la respuesta es sí, tu respuesta entera es <PENSAR/>. Las respuestas rápidas a
problemas difíciles suelen tener errores.

Ejemplos:
  "Tengo tres cajas con las etiquetas mal puestas… ¿cómo las reetiqueto?" → "<PENSAR/>"
  "Hazme un plan de estudio para mis tres exámenes, con estas condiciones…" → "<PENSAR/>"
  "Escríbeme un programa que lea un archivo y calcule…"                     → "<PENSAR/>"
  "Dos trenes salen a distintas horas… ¿dónde se cruzan?"                   → "<PENSAR/>"
  "Está mal, repásalo" (y no era algo trivial)                              → "<PENSAR/>"
  "¿Cuál es la capital de Francia?"   → "París." (directo)
  "Dile a Mamá que llego tarde"       → "Se lo digo. <WA to="Mamá">Llego tarde</WA>" (directo)
  "Recuérdame en 10 minutos la ropa"  → "Hecho. <RECORDATORIO cuando="+10m">…</RECORDATORIO>" (directo){memoria}
"""

_THINK_MEMORY_HINT = """
Si algo te salió mal por ser difícil, guárdalo en la memoria («Para X conviene
pensar antes») y, la próxima vez que te pidan algo parecido, piensa desde el
principio."""

_THINK_ON_NOTE = ("\n\n[MODO RAZONAMIENTO ACTIVADO: piensa con calma antes de responder o "
                  "actuar. No escribas <PENSAR/>.]")


def think_mode(cfg: dict) -> str:
    """«never», «always» o «auto» (la IA decide). Antes solo existía ollama_no_think."""
    m = str(cfg.get("ollama_think_mode") or "").strip().lower()
    if m in ("never", "always", "auto"):
        return m
    return "never" if cfg.get("ollama_no_think", True) else "always"


_AI_TASKS_SYSTEM_ADDON = """
─── TAREAS PARA TI MISMO ────────────────────────────────────────────────────
Además de los recordatorios para el usuario, puedes programarte TAREAS a ti
mismo. Cuando llegue la hora, el sistema te enviará un mensaje con lo que
escribiste y entonces la harás tú con tus herramientas (enviar un WhatsApp,
buscar en internet, mirar algo…), aunque el usuario no esté delante.

    <TAREA cuando="CUÁNDO">qué tienes que hacer, con todos los detalles</TAREA>
    <TAREA cuando="CUÁNDO" repetir="diario">…</TAREA>
    <TAREA_BORRAR id="N"/>

"cuando" y "repetir" se escriben igual que en los recordatorios.

¿RECORDATORIO o TAREA?
  • RECORDATORIO → el usuario quiere que le AVISES a él ("recuérdame llamar a mi padre").
  • TAREA        → quiere que TÚ HAGAS algo más tarde ("mañana a las 8 mándale a mi
                   padre que…", "a las 10 de la noche mira el tiempo de mañana y dímelo").

REGLAS:
1. Escribe la tarea como una orden completa para ti, con todo lo necesario para
   hacerla sin más contexto: qué hacer, a quién, por qué medio y el texto exacto
   si hay que enviar algo. Mal: "lo de mi padre". Bien: "Enviar un WhatsApp a
   Papá: «Llego a las 3, guárdame comida»".
2. Si te falta algo para poder hacerla (qué mensaje, a quién…), pregúntalo ANTES
   de programarla.
3. Confirma en pocas palabras ("Hecho, mañana a las 8 se lo mando.").
4. Para borrar o consultar tus tareas usa la lista de abajo (con sus números).

Ejemplo:
  "Mañana a las 8 mándale un WhatsApp a mi padre diciéndole que llego a las 3"
    → "Hecho, mañana a las 8 se lo mando. <TAREA cuando="mañana 8:00">Enviar un
       WhatsApp a mi padre: «Llego a las 3»</TAREA>"

═══ TUS TAREAS PENDIENTES ═══
{tareas}
"""


def _pc_system_addon(cfg: dict, cmd_enabled: bool = False, browser_enabled: bool = False) -> str:
    """Instrucciones del control del PC según las opciones activadas."""
    g = lambda k: cfg.get(k, DEFAULT_CONFIG.get(k))
    use_el, use_grid = bool(g("pc_use_elements")), bool(g("pc_use_grid"))
    verify, confirm = bool(g("pc_verify")), bool(g("pc_confirm_dangerous"))
    marks = []
    if use_el:
        marks.append("los elementos de las ventanas (botones, campos, menús…) en recuadros numerados")
    if use_grid:
        marks.append("una cuadrícula de casillas (columnas A, B, C… y filas 1, 2, 3…)")
    where = []
    if use_el:
        where.append('    id="12"            → el elemento nº 12 de la ÚLTIMA lista (lo más preciso)')
    if use_grid:
        where.append('    celda="D3"         → el centro de la casilla D3')
        where.append('    celda="D3.15"      → la subcasilla 15 de la zona de D3 (las ves con <PC_ZOOM celda="D3"/>)')
    where.append('    x="640" y="360"    → un punto exacto de la imagen, en píxeles de la captura'
                 + ("" if not (use_el or use_grid) else " (solo si no hay otra forma)"))
    ex_t = 'id="7"' if use_el else ('celda="D3"' if use_grid else 'x="640" y="360"')
    lines = [
        "─── CONTROL DEL ORDENADOR: RATÓN Y TECLADO ──────────────────────────────────",
        "Puedes manejar el PC del usuario como lo haría una persona: mirar la pantalla,",
        "hacer clic, escribir, pulsar teclas, arrastrar y usar la rueda del ratón.",
        "El usuario te ha autorizado: no pidas permiso para las acciones normales.",
        "",
        "1) MIRAR:  <PC_VER/>",
        "   Recibes una captura de la pantalla" + (" con " + " y ".join(marks) if marks else "") +
        ", la ventana activa, las ventanas abiertas" + (" y la lista de elementos." if use_el else "."),
        "   Haz SIEMPRE <PC_VER/> antes de tu primera acción: no adivines lo que hay en pantalla.",
        "",
        "2) ACTUAR. Para decir DÓNDE usa uno de estos atributos:",
        *where,
        "",
        f"    <PC_CLIC {ex_t}/>                     clic izquierdo",
        f"    <PC_CLIC {ex_t} boton=\"derecho\"/>     clic derecho",
        f"    <PC_CLIC {ex_t} doble=\"si\"/>          doble clic",
        f"    <PC_ESCRIBIR {ex_t}>texto</PC_ESCRIBIR>  clic en ese campo y escribe",
        "    <PC_ESCRIBIR>texto</PC_ESCRIBIR>         escribe donde esté el cursor",
        "        (añade enter=\"si\" para pulsar Intro al final y borrar=\"si\" para vaciar antes el campo)",
        "    <PC_TECLA>ctrl+c</PC_TECLA>              teclas y atajos: enter, esc, tab, espacio,",
        "        retroceso, supr, arriba, abajo, izquierda, derecha, inicio, fin, repag, avpag,",
        "        f1…f12, win, ctrl+s, alt+tab, win+d, ctrl+shift+t…  (veces=\"3\" para repetir;",
        "        varias seguidas separadas por comas: <PC_TECLA>tab, tab, enter</PC_TECLA>)",
        "    <PC_ARRASTRAR desde=\"…\" hasta=\"…\"/>       arrastrar (valores: nº de elemento, casilla o \"x,y\")",
        "    <PC_RUEDA direccion=\"abajo\" cantidad=\"5\"/> desplazar (arriba/abajo/izquierda/derecha;",
        f"        añade {ex_t} para desplazar sobre un sitio concreto)",
        f"    <PC_MOVER {ex_t}/>                     poner el ratón encima sin hacer clic",
        "    <PC_VENTANA>parte del título</PC_VENTANA>  traer al frente una ventana abierta",
        "    <PC_ESPERAR segundos=\"2\"/>               esperar a que algo cargue",
    ]
    if use_grid:
        lines.append("    <PC_ZOOM celda=\"D3\"/>                    ver ampliada una casilla para afinar")
    lines += [
        "",
        "3) COMPROBAR: " + ("después de tus acciones recibirás automáticamente una captura nueva."
                           if verify else "usa <PC_VER/> para ver el resultado de tus acciones.")
        + " Mírala con atención:",
        "   ¿ha cambiado la pantalla como esperabas? Si no ha cambiado, la acción NO ha funcionado",
        "   (aunque ponga ✅, eso solo significa que el clic o la tecla se enviaron): corrígelo.",
        "   No digas que has terminado hasta VER en la captura que está hecho.",
        "",
        "PRECISIÓN: " + ("los elementos numerados son exactos; " if use_el else "")
        + ("una casilla entera es grande (el clic va a su centro): para cosas pequeñas o para "
           "arrastrar objetos sin número, haz antes <PC_ZOOM celda=\"…\"/> y usa la subcasilla "
           "(celda=\"D3.15\"). Si un objeto queda entre dos casillas, haz zoom." if use_grid else
           "para cosas sin número usa x,y con cuidado, mirando la escala de la imagen."),
        "",
        "REGLAS:",
        "1. Encadena varias acciones solo si la pantalla no cambia entre ellas (p. ej. clic en un",
        "   campo y escribir). Tras algo que abre o cambia la pantalla (menú, ventana, página),",
        "   PARA y espera a la captura nueva.",
        "2. Los números de los elementos cambian en cada captura: usa siempre los de la última.",
        "3. Para abrir un programa: <PC_TECLA>win</PC_TECLA><PC_ESPERAR segundos=\"1\"/>"
        "<PC_ESCRIBIR enter=\"si\">nombre del programa</PC_ESCRIBIR>"
        + (" (o <CMD>start …</CMD>)." if cmd_enabled else "."),
        "4. Marca con peligroso=\"si\" toda acción que borre, envíe, publique, compre, pague, cierre",
        "   sin guardar o no se pueda deshacer, p. ej. <PC_CLIC id=\"5\" peligroso=\"si\"/>."
        + (" El usuario tendrá que confirmarla." if confirm else ""),
        "   Nunca repitas una acción así (enviar, borrar, comprar…) aunque parezca que no ha",
        "   funcionado: pregunta antes al usuario.",
        "5. Haz solo lo que el usuario ha pedido. Si aparece una contraseña, datos bancarios, un",
        "   pago o un captcha, para y pide al usuario que lo haga él.",
        "6. Si una acción falla dos o tres veces, prueba de otra forma (un atajo de teclado, otro",
        "   elemento" + (", la cuadrícula o el zoom" if use_grid else "") + ") o explica el problema.",
        "7. Si el sistema te dice que el usuario ha detenido el control, no sigas: díselo.",
        "8. Al terminar, responde en una o dos frases qué has hecho (sin etiquetas).",
    ]
    if browser_enabled:
        lines.append("9. Para tareas solo de páginas web prefiere tus herramientas WEB_* (navegador propio);"
                     " usa el control del PC para programas de Windows o el navegador del usuario.")
    lines += [
        "",
        "Ejemplo:",
        "  Usuario: \"Abre el bloc de notas y escribe hola\"",
        "  Tú:      \"Voy. <PC_TECLA>win</PC_TECLA><PC_ESPERAR segundos=\"1\"/>"
        "<PC_ESCRIBIR enter=\"si\">bloc de notas</PC_ESCRIBIR><PC_ESPERAR segundos=\"2\"/>\"",
        "  (recibes la captura: el Bloc de notas está abierto) → \"<PC_ESCRIBIR>hola</PC_ESCRIBIR>\"",
        "  (recibes la captura: pone «hola») → \"Listo: he abierto el Bloc de notas y he escrito hola.\"",
    ]
    return "\n".join(lines)


def _build_system_prompt(base: str, cmd_enabled: bool,
                         wa_enabled: bool = False,
                         browser_enabled: bool = False,
                         web_enabled: bool = True,
                         datetime_enabled: bool = True,
                         vision_enabled: bool = False,
                         memory_enabled: bool = False,
                         reminders_enabled: bool = False,
                         ai_tasks_enabled: bool = False,
                         think_auto: bool = False,
                         memory_block: str = "",
                         reminders_block: str = "",
                         ai_tasks_block: str = "",
                         pc_block: str = "",
                         wa_block: str = "") -> str:
    """
    Construye las instrucciones completas para la IA:
    personalidad del usuario + fecha/hora + herramientas activas + memoria + recordatorios.
    """
    parts = [(base or "").strip() or
             "Eres un asistente de voz útil, conciso y amable. "
             "Responde siempre en el mismo idioma que el usuario."]
    if datetime_enabled:
        parts.append(_DATETIME_ADDON.format(ahora=fecha_larga()))
    else:
        parts.append(_NO_DATETIME_ADDON.format(como=(
            "Si el usuario las pregunta, consúltalas con <CMD>echo %date% %time%</CMD>."
            if cmd_enabled else "Si el usuario las pregunta, dile que no las sabes.")))

    tools = []
    if cmd_enabled:
        tools.append(_CMD_SYSTEM_ADDON)
    if web_enabled:
        tools.append(_WEB_SYSTEM_ADDON)
    if browser_enabled:
        tools.append(_BROWSER_SYSTEM_ADDON)
    if wa_enabled:
        tools.append(wa_block or _WA_SYSTEM_ADDON)
    if vision_enabled:
        tools.append(_VISION_SYSTEM_ADDON)
    if pc_block:
        tools.append(pc_block)
    if reminders_enabled:
        tools.append(_REMINDERS_SYSTEM_ADDON.format(
            recordatorios=reminders_block or "(No hay recordatorios pendientes.)"))
    if ai_tasks_enabled:
        tools.append(_AI_TASKS_SYSTEM_ADDON.format(
            tareas=ai_tasks_block or "(No tienes tareas pendientes.)"))
    if memory_enabled:
        tools.append(_MEMORY_SYSTEM_ADDON.format(
            memoria=memory_block or "(La memoria está vacía.)"))
    if think_auto:
        tools.append(_THINK_SYSTEM_ADDON.format(memoria=_THINK_MEMORY_HINT if memory_enabled else ""))
    if tools:
        parts.append(_TOOLS_HEADER)
        parts.extend(tools)
    return "\n\n".join(p.strip("\n") for p in parts)


# ══════════════════════════════════════════════════════════════════════════════
#  ETIQUETAS DE ACCIÓN: patrones, filtrado en streaming y limpieza
# ══════════════════════════════════════════════════════════════════════════════

_CAPTURA_PAT = re.compile(r"<CAPTURA\b(?P<attrs>[^>]*?)/?>(?:\s*</CAPTURA>)?", re.IGNORECASE)
_CAMARA_PAT  = re.compile(r"<C[AÁ]MARA\b(?P<attrs>[^>]*?)/?>(?:\s*</C[AÁ]MARA>)?", re.IGNORECASE)

_MEM_SAVE_PAT = re.compile(r"<MEMORIA_GUARDAR\b[^>]*>(?P<body>.*?)</MEMORIA_GUARDAR\s*>",
                           re.IGNORECASE | re.DOTALL)
_MEM_EDIT_PAT = re.compile(r"<MEMORIA_EDITAR\b(?P<attrs>[^>]*)>(?P<body>.*?)</MEMORIA_EDITAR\s*>",
                           re.IGNORECASE | re.DOTALL)
_MEM_DEL_PAT  = re.compile(r"<MEMORIA_BORRAR\b(?P<attrs>[^>]*?)(?:/>|>(?P<body>.*?)</MEMORIA_BORRAR\s*>)",
                           re.IGNORECASE | re.DOTALL)
_REM_ADD_PAT  = re.compile(r"<RECORDATORIO(?P<attrs>(?:\s[^>]*)?)>(?P<body>.*?)</RECORDATORIO\s*>",
                           re.IGNORECASE | re.DOTALL)
_REM_DEL_PAT  = re.compile(r"<RECORDATORIO_BORRAR\b(?P<attrs>[^>]*?)(?:/>|>(?P<body>.*?)</RECORDATORIO_BORRAR\s*>)",
                           re.IGNORECASE | re.DOTALL)
_THINK_PAT    = re.compile(r"<PENSAR\b[^>]*>", re.IGNORECASE)
_TASK_ADD_PAT = re.compile(r"<TAREA(?P<attrs>(?:\s[^>]*)?)>(?P<body>.*?)</TAREA\s*>",
                           re.IGNORECASE | re.DOTALL)
_TASK_DEL_PAT = re.compile(r"<TAREA_BORRAR\b(?P<attrs>[^>]*?)(?:/>|>(?P<body>.*?)</TAREA_BORRAR\s*>)",
                           re.IGNORECASE | re.DOTALL)

_ATTR_PAT = re.compile(r"""([\wáéíóúñ]+)\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s"'>/]+))""", re.IGNORECASE)


def _parse_attrs(s: str) -> dict:
    out = {}
    for m in _ATTR_PAT.finditer(s or ""):
        val = next((g for g in m.groups()[1:] if g is not None), "")
        out[_norm_text(m.group(1))] = val.strip()
    return out


def _tag_id(attrs: str, body: str = "") -> Optional[int]:
    """Extrae el número de id="N", de un número suelto en el cuerpo o '#N'."""
    a = _parse_attrs(attrs)
    for src in (a.get("id", ""), a.get("numero", ""), attrs or "", body or ""):
        m = re.search(r"\d+", str(src))
        if m:
            return int(m.group(0))
    return None


# Nombres de todas las etiquetas que el usuario nunca debe ver ni oír
_ACTION_TAG_NAMES = [
    "CMD", "SEARCH", "FETCH",
    "WEB_GOTO", "WEB_CLICK", "WEB_TYPE", "WEB_SELECT", "WEB_CHECK",
    "WEB_SCROLL", "WEB_BACK", "WEB_READ", "WEB_KEY",
    "WA", "WA_SELF", "WA_CONTACTOS", "WA_LEER",
    "CAPTURA", "CAMARA", "CÁMARA",
    "MEMORIA_GUARDAR", "MEMORIA_EDITAR", "MEMORIA_BORRAR",
    "RECORDATORIO", "RECORDATORIO_BORRAR", "TAREA", "TAREA_BORRAR", "PENSAR",
    "PC_VER", "PC_CLIC", "PC_DOBLE_CLIC", "PC_ESCRIBIR", "PC_TECLA", "PC_ARRASTRAR",
    "PC_RUEDA", "PC_MOVER", "PC_ZOOM", "PC_VENTANA", "PC_ESPERAR",
]
_SELF_CLOSING_TAGS = {"WEB_BACK", "WEB_READ", "CAPTURA", "CAMARA", "CÁMARA", "PENSAR",
                      "WA_CONTACTOS", "WA_LEER",
                      "PC_VER", "PC_CLIC", "PC_DOBLE_CLIC", "PC_ARRASTRAR", "PC_RUEDA",
                      "PC_MOVER", "PC_ZOOM", "PC_ESPERAR"}
_TAG_NAMES_ALT = "|".join(sorted((re.escape(n) for n in _ACTION_TAG_NAMES), key=len, reverse=True))
_PAIRED_TAG_RE = re.compile(rf"<({_TAG_NAMES_ALT})\b[^>]*>.*?</\1\s*>", re.IGNORECASE | re.DOTALL)
_SINGLE_TAG_RE = re.compile(rf"</?({_TAG_NAMES_ALT})\b[^>]*?/?>", re.IGNORECASE)
_LEADING_STAMP_RE = re.compile(
    r"^\s*\[(?:🕐\s*)?(?:lunes|martes|miércoles|miercoles|jueves|viernes|sábado|sabado|domingo)"
    r"[^\]]{0,60}\]\s*", re.IGNORECASE)


def action_tags(text: str) -> list:
    """Las etiquetas de acción de una respuesta, en orden y tal y como las escribió la IA."""
    if not text:
        return []
    found = [(m.start(), m.group(0)) for m in _PAIRED_TAG_RE.finditer(text)]
    rest = _PAIRED_TAG_RE.sub(lambda m: " " * len(m.group(0)), text)
    found += [(m.start(), m.group(0)) for m in _SINGLE_TAG_RE.finditer(rest)
              if not m.group(0).startswith("</")]
    return [t for _, t in sorted(found)]


def tools_trace(tags: list) -> str:
    """
    Resumen de las herramientas usadas en una respuesta, para el historial. Sin los
    resultados (ocuparían mucho y caducan); el control del PC, solo contado, para que
    nunca repita clics con coordenadas antiguas.
    """
    out, pc = [], 0
    for t in tags:
        name = re.match(r"<\s*([\wÁÉÍÓÚáéíóú]+)", t)
        name = name.group(1).upper() if name else ""
        if name.startswith("PC_") and name != "PC_VER":
            pc += 1
            continue
        if len(t) > 300:                               # mensajes o comandos muy largos
            m = re.match(r"(<[^>]*>)(.*)(</[^>]+>)\s*$", t, re.DOTALL)
            t = (m.group(1) + m.group(2)[:200] + "…" + m.group(3)) if m else t[:300] + "…"
        if not out or out[-1] != t:
            out.append(t)
    if len(out) > 6:
        out = out[:3] + [f"(… {len(out) - 5} herramientas más …)"] + out[-2:]
    if pc:
        out.append(f"({pc} acciones de ratón y teclado en el PC)")
    return "\n".join(out)


def strip_action_tags(text: str) -> str:
    """Quita del texto todas las etiquetas de acción (para mostrar, leer en voz alta o loguear)."""
    if not text:
        return ""
    out = _PAIRED_TAG_RE.sub("", text)
    out = _SINGLE_TAG_RE.sub("", out)
    out = _LEADING_STAMP_RE.sub("", out)           # la IA a veces imita la marca de fecha
    out = re.sub(r"[ \t]+\n", "\n", out)
    out = re.sub(r"\n{3,}", "\n\n", out)
    return out.strip()


class TagStreamFilter:
    """
    Filtra etiquetas de acción de un texto que llega a trozos (streaming).
    Retiene el texto que podría ser el principio de una etiqueta hasta saber si lo es;
    las etiquetas completas desaparecen y el resto pasa tal cual.
    """
    _NAME_START = re.compile(r"<(/?)([A-Za-zÁÉÍÓÚáéíóú_]*)")

    def __init__(self):
        self._buf = ""
        self._names = [n.upper() for n in _ACTION_TAG_NAMES]

    def feed(self, chunk: str) -> str:
        self._buf += chunk or ""
        out = []
        while self._buf:
            i = self._buf.find("<")
            if i < 0:
                out.append(self._buf)
                self._buf = ""
                break
            if i:
                out.append(self._buf[:i])
                self._buf = self._buf[i:]
            m = self._NAME_START.match(self._buf)
            name = m.group(2).upper() if m else ""
            if m.end() >= len(self._buf):
                # Solo se ha visto "<" + parte del nombre: ¿puede ser una etiqueta?
                if any(n.startswith(name) for n in self._names):
                    break                                   # esperar más texto
                out.append(self._buf)
                self._buf = ""
                break
            if name not in self._names:
                out.append("<")                             # no es una etiqueta nuestra
                self._buf = self._buf[1:]
                continue
            j = self._buf.find(">")
            if j < 0:
                break                                       # etiqueta aún sin cerrar
            tag = self._buf[:j + 1]
            if m.group(1) == "/" or tag.endswith("/>") or name in _SELF_CLOSING_TAGS:
                self._buf = self._buf[j + 1:]               # etiqueta suelta: fuera
                continue
            close = re.compile(rf"</{re.escape(name)}\s*>", re.IGNORECASE).search(self._buf, j + 1)
            if not close:
                break                                       # esperar al cierre
            self._buf = self._buf[close.end():]
        return "".join(out)

    def flush(self) -> str:
        rest, self._buf = self._buf, ""
        return rest


# ══════════════════════════════════════════════════════════════════════════════
#  MEMORIA PERSISTENTE
# ══════════════════════════════════════════════════════════════════════════════

MEMORY_FILE    = APP_DIR / "memoria.json"
REMINDERS_FILE = APP_DIR / "recordatorios.json"
AI_TASKS_FILE  = APP_DIR / "tareas_ia.json"
CAPTURES_DIR   = APP_DIR / "capturas"
SOUNDS_DIR     = APP_DIR / "sonidos"


class MemoryStore:
    """Datos que la IA recuerda entre sesiones (memoria.json en la carpeta de datos)."""
    MAX_PROMPT_CHARS = 6000
    MAX_ENTRY_CHARS  = 400

    def __init__(self, path: Path = MEMORY_FILE):
        self._path = path
        self._lock = threading.RLock()
        data = _read_json(path, {})
        if isinstance(data, list):
            data = {"entradas": data}
        self._entries = []
        for e in data.get("entradas", []):
            if isinstance(e, dict) and _one_line(e.get("texto")):
                try:
                    e["id"] = int(e.get("id"))
                except (TypeError, ValueError):
                    continue
                self._entries.append(e)
        ids = [e["id"] for e in self._entries]
        self._next_id = max(ids + [int(data.get("siguiente_id", 1) or 1) - 1, 0]) + 1

    def _save(self):
        _atomic_write_json(self._path, {"siguiente_id": self._next_id,
                                        "entradas": self._entries})

    def all(self) -> list:
        with self._lock:
            return [dict(e) for e in self._entries]

    def _find(self, mid: int):
        return next((e for e in self._entries if e["id"] == mid), None)

    def add(self, texto: str) -> Tuple[bool, str, Optional[int]]:
        texto = _one_line(texto)[:self.MAX_ENTRY_CHARS]
        if not texto:
            return False, "el dato está vacío", None
        with self._lock:
            norm = _norm_text(texto)
            for e in self._entries:
                if _norm_text(e["texto"]) == norm:
                    return True, "ya estaba guardado", e["id"]
            now = datetime.now().isoformat(timespec="seconds")
            e = {"id": self._next_id, "texto": texto, "creado": now, "actualizado": now}
            self._next_id += 1
            self._entries.append(e)
            self._save()
            return True, "guardado", e["id"]

    def edit(self, mid: int, texto: str) -> Tuple[bool, str]:
        texto = _one_line(texto)[:self.MAX_ENTRY_CHARS]
        if not texto:
            return False, "el texto nuevo está vacío"
        with self._lock:
            e = self._find(mid)
            if not e:
                return False, f"no existe el dato #{mid}"
            e["texto"] = texto
            e["actualizado"] = datetime.now().isoformat(timespec="seconds")
            self._save()
            return True, "modificado"

    def delete(self, mid: int) -> Tuple[bool, str]:
        with self._lock:
            e = self._find(mid)
            if not e:
                return False, f"no existe el dato #{mid}"
            self._entries.remove(e)
            self._save()
            return True, f"borrado: {e['texto']}"

    def clear(self):
        with self._lock:
            self._entries = []
            self._save()

    def prompt_block(self) -> str:
        entries = self.all()
        if not entries:
            return "(La memoria está vacía.)"
        lines, total = [], 0
        for e in reversed(entries):                 # prioriza lo más reciente
            line = f"[{e['id']}] {e['texto']}"
            if total + len(line) > self.MAX_PROMPT_CHARS:
                break
            lines.append(line)
            total += len(line) + 1
        lines.reverse()
        omitted = len(entries) - len(lines)
        if omitted:
            lines.insert(0, f"(… {omitted} datos antiguos no caben aquí)")
        return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════════════
#  RECORDATORIOS: interpretación de "cuando", almacén y planificador
# ══════════════════════════════════════════════════════════════════════════════

_DIAS_NORM = ["lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo"]
_MESES_NORM = {m: i + 1 for i, m in enumerate(
    ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
     "septiembre", "octubre", "noviembre", "diciembre"])}
_MESES_NORM["setiembre"] = 9

_NUM_WORDS = {
    "un": 1, "una": 1, "uno": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5,
    "seis": 6, "siete": 7, "ocho": 8, "nueve": 9, "diez": 10, "once": 11,
    "doce": 12, "quince": 15, "veinte": 20, "treinta": 30, "cuarenta": 40,
    "cincuenta": 50, "sesenta": 60,
}
_REL_NUM  = (r"((?<![0-9.,])\d+(?:[.,]\d+)?|\b(?:"
             + "|".join(sorted(_NUM_WORDS, key=len, reverse=True)) + r")\b)")
_REL_UNIT = r"(segundos?|segs?|s|minutos?|mins?|m|horas?|hrs?|h|dias?|d|semanas?|sem)(?![a-z])"
_REL_ITEM_RE = re.compile(_REL_NUM + r"\s*" + _REL_UNIT)

_REPEAT_ALIASES = {
    "": "", "no": "", "ninguno": "", "ninguna": "", "nunca": "", "una vez": "",
    "diario": "diario", "diaria": "diario", "diariamente": "diario", "cada dia": "diario",
    "todos los dias": "diario", "daily": "diario",
    "laborables": "laborables", "laborable": "laborables", "entre semana": "laborables",
    "de lunes a viernes": "laborables", "lunes a viernes": "laborables",
    "semanal": "semanal", "semanalmente": "semanal", "cada semana": "semanal", "weekly": "semanal",
    "mensual": "mensual", "mensualmente": "mensual", "cada mes": "mensual", "monthly": "mensual",
    "anual": "anual", "anualmente": "anual", "cada ano": "anual", "yearly": "anual",
}
REPEAT_LABELS = {"": "una vez", "diario": "cada día", "laborables": "de lunes a viernes",
                 "semanal": "cada semana", "mensual": "cada mes", "anual": "cada año"}


def normalize_repeat(value: str) -> str:
    key = _norm_text(value)
    if key in _REPEAT_ALIASES:
        return _REPEAT_ALIASES[key]
    raise ValueError(f"repetición no válida: '{value}' (usa diario, laborables, semanal, mensual o anual)")


def _num_value(tok: str) -> float:
    tok = tok.replace(",", ".")
    try:
        return float(tok)
    except ValueError:
        return float(_NUM_WORDS.get(tok, 0))


def _unit_seconds(unit: str) -> int:
    if unit.startswith("seg") or unit == "s":
        return 1
    if unit.startswith("min") or unit == "m":
        return 60
    if unit.startswith("h"):
        return 3600
    if unit.startswith("sem"):
        return 604800
    return 86400                                     # d / dia(s)


def _parse_relative(s: str) -> Optional[timedelta]:
    """'+10m', 'en 2 horas', 'dentro de media hora', '1h30m' → timedelta (o None si no es relativo)."""
    t = s.strip()
    had_prefix = False
    m = re.match(r"^(\+\s*|en\s+|dentro\s+de\s+|de\s+aqui\s+a\s+|tras\s+)", t)
    if m:
        had_prefix = True
        t = t[m.end():].strip()
    if not t:
        return None
    if had_prefix and re.fullmatch(r"\d+", t):
        return timedelta(minutes=int(t))             # "+10" → 10 minutos
    t = re.sub(r"\b(?:una?\s+)?hora\s+y\s+media\b", "90 minutos", t)
    t = re.sub(r"\bmedia\s+hora\b", "30 minutos", t)
    t = re.sub(r"\btres\s+cuartos\s+de\s+hora\b", "45 minutos", t)
    t = re.sub(r"\b(?:un\s+)?cuarto\s+de\s+hora\b", "15 minutos", t)
    t = re.sub(_REL_NUM + r"\s*(horas?|h)\s+y\s+media\b", r"\1 \2 30 minutos", t)
    t = re.sub(r"(\d+)\s*h\s*(\d{1,2})(?!\d)(?!\s*(?:m|min|s|seg))", r"\1h \2m", t)   # 1h30 → 1h 30m
    total, found = 0.0, False

    def _acc(mm):
        nonlocal total, found
        total += _num_value(mm.group(1)) * _unit_seconds(mm.group(2))
        found = True
        return " "

    rest = _REL_ITEM_RE.sub(_acc, t)
    rest = re.sub(r"\b(y|aprox|aproximadamente|exactos|justos|mas o menos)\b|[,+.]", " ", rest).strip()
    if not found or rest:
        return None
    return timedelta(seconds=round(total))


def _add_months(dt: datetime, months: int, day: int = None) -> datetime:
    y, mth = divmod(dt.month - 1 + months, 12)
    y += dt.year
    mth += 1
    d = min(day or dt.day, calendar.monthrange(y, mth)[1])
    return dt.replace(year=y, month=mth, day=d)


def parse_when(texto: str, now: datetime = None) -> datetime:
    """
    Interpreta cuándo debe sonar un recordatorio. Acepta, entre otros:
      relativos  "+10m", "+1h30m", "en 20 minutos", "dentro de 2 horas", "en media hora"
      hoy/mañana "hoy 18:30", "mañana 9:00", "pasado mañana a las 10", "en 3 días a las 8"
      semana     "viernes 17:00", "el próximo lunes a las 8"
      fechas     "2026-12-24 20:00", "24/12 20:00", "24 de diciembre a las 8 de la tarde"
      solo hora  "18:30", "a las 5 de la tarde", "10 pm", "mediodía", "medianoche"
    Devuelve un datetime futuro o lanza ValueError con una explicación.
    """
    now = (now or datetime.now()).replace(microsecond=0)
    raw = str(texto or "").strip()
    if not raw:
        raise ValueError("no se indicó cuándo")
    s = _norm_text(raw).replace("p.m.", "pm").replace("a.m.", "am").replace("’", "'")
    s = re.sub(r"\s+", " ", s)

    rel = _parse_relative(s)
    if rel is not None:
        if rel.total_seconds() < 5:
            raise ValueError("el tiempo indicado es demasiado corto")
        return now + rel

    t = f" {s} "
    date = None             # fecha (datetime.date)
    explicit = False        # fecha con año explícito: si ya pasó es un error
    say_today = False       # "hoy", "esta tarde"…: no se mueve a otro día
    weekday_today = False   # "viernes" dicho un viernes: hoy, o +7 días si ya pasó la hora
    period = None           # manana | tarde | noche | madrugada | mediodia
    default_time = (9, 0)
    midnight = False

    def cut(m):
        nonlocal t
        t = t[:m.start()] + " " + t[m.end():]

    # ── Franjas del día ──────────────────────────────────────────────────────
    for pat, per, hhmm in ((r"\b(?:de|por)\s+la\s+manana\b|\besta\s+manana\b", "manana", (9, 0)),
                           (r"\b(?:de|por)\s+la\s+tarde\b|\besta\s+tarde\b", "tarde", (17, 0)),
                           (r"\b(?:de|por)\s+la\s+noche\b|\besta\s+noche\b", "noche", (21, 0)),
                           (r"\b(?:de|por)\s+la\s+madrugada\b|\besta\s+madrugada\b", "madrugada", (3, 0)),
                           (r"\b(?:al|a|del|de)?\s*mediodia\b", "mediodia", (12, 0))):
        m = re.search(pat, t)
        if m:
            period, default_time = per, hhmm
            if m.group(0).strip().startswith("esta "):
                say_today = True
            cut(m)
            break
    m = re.search(r"\b(?:a\s+)?(?:la\s+)?medianoche\b", t)
    if m:
        midnight, default_time = True, (0, 0)
        cut(m)

    # ── Fechas explícitas ────────────────────────────────────────────────────
    try:
        m = re.search(r"\b(\d{4})[-/](\d{1,2})[-/](\d{1,2})(?=[t\s]|$)", t)
        if m:
            y, mo, d = map(int, m.groups())
            date, explicit = datetime(y, mo, d).date(), True
            cut(m)
        if date is None:
            m = re.search(r"\b(\d{1,2})[/.-](\d{1,2})(?:[/.-](\d{2,4}))?\b", t)
            if m:
                d, mo = int(m.group(1)), int(m.group(2))
                y = int(m.group(3)) if m.group(3) else now.year
                y += 2000 if y < 100 else 0
                date, explicit = datetime(y, mo, d).date(), bool(m.group(3))
                if not explicit and date < now.date():
                    date = date.replace(year=now.year + 1)
                cut(m)
        if date is None:
            m = re.search(r"\b(\d{1,2})\s+(?:de\s+)?(" + "|".join(_MESES_NORM) + r")\b"
                          r"(?:\s+(?:de|del)?\s*(\d{4}))?", t)
            if m:
                d, mo = int(m.group(1)), _MESES_NORM[m.group(2)]
                y = int(m.group(3)) if m.group(3) else now.year
                date, explicit = datetime(y, mo, d).date(), bool(m.group(3))
                if not explicit and date < now.date():
                    date = date.replace(year=now.year + 1)
                cut(m)
    except ValueError:
        raise ValueError(f"la fecha de '{raw}' no existe")

    # ── Palabras: pasado mañana, mañana, hoy, en N días, días de la semana ──
    if date is None:
        m = re.search(r"\bpasado\s+manana\b", t)
        if m:
            date = (now + timedelta(days=2)).date()
            cut(m)
    if date is None:
        m = re.search(r"\bmanana\b", t)
        if m:
            date = (now + timedelta(days=1)).date()
            cut(m)
    if date is None:
        m = re.search(r"\bhoy\b", t)
        if m:
            date, say_today = now.date(), True
            cut(m)
    if date is None:
        m = re.search(r"\b(?:en|dentro\s+de)\s+" + _REL_NUM + r"\s+(dias?|semanas?)\b", t)
        if m:
            n = _num_value(m.group(1)) * (7 if m.group(2).startswith("semana") else 1)
            date = (now + timedelta(days=int(n))).date()
            cut(m)
    if date is None:
        m = re.search(r"\b(proximo\s+|este\s+)?(" + "|".join(_DIAS_NORM) + r")\b", t)
        if m:
            wd = _DIAS_NORM.index(m.group(2))
            ahead = (wd - now.weekday()) % 7
            if ahead == 0 and (m.group(1) or "").strip() == "proximo":
                ahead = 7
            date = (now + timedelta(days=ahead)).date()
            weekday_today = ahead == 0
            cut(m)
    if date is None:
        m = re.search(r"\bdia\s+(\d{1,2})\b", t)
        if m:
            d = int(m.group(1))
            first = now.replace(day=1, hour=0, minute=0, second=0)
            for k in range(13):
                c = _add_months(first, k, 1)
                if d <= calendar.monthrange(c.year, c.month)[1] and c.replace(day=d).date() >= now.date():
                    date = c.replace(day=d).date()
                    break
            cut(m)
    t = re.sub(r"\b(hoy|manana|pasado)\b", " ", t)
    if date is None and say_today:
        date = now.date()

    # ── Hora ─────────────────────────────────────────────────────────────────
    hour = minute = None
    suffix = ""
    m = re.search(r"(?<![\d/.:-])(\d{1,2})\s*(?::|\.|h)\s*(\d{2})(?![\d/.:-])\s*(am|pm|hrs|horas|h)?(?![a-z])", t)
    if m:
        hour, minute, suffix = int(m.group(1)), int(m.group(2)), (m.group(3) or "")
    if hour is None:
        m = re.search(r"(?<![\d/.:-])(\d{1,2})\s*(am|pm|hrs|horas|h)(?![a-z])", t)
        if m:
            hour, minute, suffix = int(m.group(1)), 0, m.group(2)
    if hour is None:
        m = re.search(r"\b(?:a\s+)?las?\s+(\d{1,2})(?![\d/.:-])", t)
        if not m and (date is not None or period):
            m = re.search(r"(?<![\d/.:-])\b(\d{1,2})\b(?![\d/.:-])", t)
        if m:
            hour, minute = int(m.group(1)), 0
    if hour is not None:
        rest = t[m.end():]
        if minute == 0:
            if re.match(r"\s*y\s+media\b", rest):
                minute = 30
            elif re.match(r"\s*y\s+cuarto\b", rest):
                minute = 15
            elif re.match(r"\s*menos\s+cuarto\b", rest):
                hour, minute = (hour - 1) % 24, 45
        if suffix == "pm" and hour < 12:
            hour += 12
        elif suffix == "am" and hour == 12:
            hour = 0
        elif suffix != "am":
            if period == "tarde" and hour < 12:
                hour += 12
            elif period == "noche" and 6 <= hour < 12:
                hour += 12
            elif period == "noche" and hour == 12:
                hour = 0
            elif period == "mediodia" and hour < 6:
                hour += 12
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise ValueError(f"la hora de '{raw}' no es válida")

    if date is None and hour is None and not period and not midnight:
        raise ValueError(f"no entiendo '{raw}'. Usa por ejemplo \"+10m\", \"mañana 9:00\", "
                         f"\"viernes 17:00\" o \"2026-12-24 20:00\"")
    if hour is None:
        hour, minute = default_time

    if midnight and hour == 0 and minute == 0:          # medianoche = fin del día indicado
        base = date or now.date()
        dt = datetime(base.year, base.month, base.day) + timedelta(days=1)
        if dt <= now:
            dt += timedelta(days=1)
        return dt

    if date is None:                                    # solo hora (o franja) → hoy o mañana
        dt = now.replace(hour=hour, minute=minute, second=0)
        if dt <= now:
            dt += timedelta(days=1)
        return dt

    dt = datetime(date.year, date.month, date.day, hour, minute)
    if dt <= now - timedelta(seconds=30):
        if weekday_today:
            dt += timedelta(days=7)        # "viernes 10:00" dicho un viernes a las 12 → el próximo
        else:
            raise ValueError(f"esa fecha y hora ya han pasado ({fecha_corta(dt, now)})")
    return dt


def _next_occurrence(dt: datetime, repetir: str, now: datetime, anchor_day: int = None) -> Optional[datetime]:
    """Siguiente vez que debe sonar un recordatorio periódico (posterior a 'now')."""
    if not repetir:
        return None
    nxt = dt
    for _ in range(3700):
        if repetir == "diario":
            nxt += timedelta(days=1)
        elif repetir == "semanal":
            nxt += timedelta(days=7)
        elif repetir == "laborables":
            nxt += timedelta(days=1)
            while nxt.weekday() >= 5:
                nxt += timedelta(days=1)
        elif repetir == "mensual":
            nxt = _add_months(nxt, 1, anchor_day)
        elif repetir == "anual":
            nxt = _add_months(nxt, 12, anchor_day)
        else:
            return None
        if nxt > now:
            return nxt
    return None


class ReminderStore:
    """Recordatorios guardados en recordatorios.json (carpeta de datos)"""
    NOUN, DEFAULT_TEXT, MAX_TEXT = "el recordatorio", "Recordatorio", 300
    EMPTY = "(No hay recordatorios pendientes.)"

    def __init__(self, path: Path = REMINDERS_FILE):
        self._path = path
        self._lock = threading.RLock()
        self.changed = threading.Event()       # despierta al planificador
        data = _read_json(path, {})
        self._items = []
        for r in data.get("recordatorios", []):
            try:
                r["id"] = int(r["id"])
                datetime.fromisoformat(r["cuando"])
                r.setdefault("repetir", "")
                r.setdefault("hecho", False)
                self._items.append(r)
            except Exception:
                continue
        ids = [r["id"] for r in self._items]
        self._next_id = max(ids + [int(data.get("siguiente_id", 1) or 1) - 1, 0]) + 1
        self._purge()

    def _save(self):
        _atomic_write_json(self._path, {"siguiente_id": self._next_id,
                                        "recordatorios": self._items})
        self.changed.set()

    def _purge(self):
        """Elimina los recordatorios ya avisados hace más de 7 días."""
        limit = datetime.now() - timedelta(days=7)
        before = len(self._items)
        self._items = [r for r in self._items if not (
            r.get("hecho") and datetime.fromisoformat(r.get("disparado") or r["cuando"]) < limit)]
        if len(self._items) != before:
            self._save()

    def add(self, texto: str, when: datetime, repetir: str = "", extra: dict = None) -> dict:
        texto = _one_line(texto)[:self.MAX_TEXT] or self.DEFAULT_TEXT
        repetir = normalize_repeat(repetir)
        if repetir == "laborables":
            while when.weekday() >= 5:
                when += timedelta(days=1)
        with self._lock:
            r = {"id": self._next_id, "texto": texto,
                 "cuando": when.isoformat(timespec="seconds"),
                 "repetir": repetir, "dia_ancla": when.day,
                 "creado": datetime.now().isoformat(timespec="seconds"),
                 "hecho": False, "disparado": None, "veces": 0, **(extra or {})}
            self._next_id += 1
            self._items.append(r)
            self._save()
            return dict(r)

    def get(self, rid: int) -> Optional[dict]:
        with self._lock:
            r = next((x for x in self._items if x["id"] == rid), None)
            return dict(r) if r else None

    def delete(self, rid: int) -> Tuple[bool, str]:
        with self._lock:
            r = next((x for x in self._items if x["id"] == rid and not x.get("hecho")), None)
            if not r:
                return False, f"no existe {self.NOUN} pendiente #{rid}"
            self._items.remove(r)
            self._save()
            return True, f"borrado: {r['texto']}"

    def pending(self) -> list:
        with self._lock:
            items = [dict(r) for r in self._items if not r.get("hecho")]
        return sorted(items, key=lambda r: r["cuando"])

    def next_due(self) -> Optional[datetime]:
        p = self.pending()
        return datetime.fromisoformat(p[0]["cuando"]) if p else None

    def due(self, now: datetime) -> list:
        return [r for r in self.pending() if datetime.fromisoformat(r["cuando"]) <= now]

    def mark_fired(self, rid: int, now: datetime):
        with self._lock:
            r = next((x for x in self._items if x["id"] == rid), None)
            if not r:
                return
            r["disparado"] = now.isoformat(timespec="seconds")
            r["veces"] = int(r.get("veces", 0)) + 1
            nxt = _next_occurrence(datetime.fromisoformat(r["cuando"]), r.get("repetir", ""),
                                   now, r.get("dia_ancla"))
            if nxt:
                r["cuando"] = nxt.isoformat(timespec="seconds")
            else:
                r["hecho"] = True
            self._save()

    def describe(self, r: dict, now: datetime = None) -> str:
        now = now or datetime.now()
        when = datetime.fromisoformat(r["cuando"])
        rep = f", {REPEAT_LABELS.get(r.get('repetir', ''), '')}" if r.get("repetir") else ""
        return f"{fecha_corta(when, now)}{rep}"

    def prompt_block(self) -> str:
        now = datetime.now()
        p = self.pending()
        if not p:
            return self.EMPTY
        lines = [f"[#{r['id']}] {self.describe(r, now)} — {r['texto']}" for r in p[:30]]
        if len(p) > 30:
            lines.append(f"(… y {len(p) - 30} más)")
        return "\n".join(lines)


class AITaskStore(ReminderStore):
    """Tareas que la IA se programa a sí misma (tareas_ia.json): al llegar la hora,
    se le manda lo que tenía que hacer y lo hace ella."""
    NOUN, DEFAULT_TEXT, MAX_TEXT = "la tarea", "", 1000
    EMPTY = "(No tienes tareas pendientes.)"

    def __init__(self, path: Path = AI_TASKS_FILE):
        super().__init__(path)


class ReminderScheduler(threading.Thread):
    """Hilo que vigila los recordatorios y avisa (on_fire) cuando llega su hora."""

    def __init__(self, store: ReminderStore, on_fire):
        super().__init__(daemon=True, name="recordatorios")
        self._store = store
        self._on_fire = on_fire
        self._stop_evt = threading.Event()

    def stop(self):
        self._stop_evt.set()
        self._store.changed.set()

    def run(self):
        while not self._stop_evt.is_set():
            now = datetime.now()
            try:
                for r in self._store.due(now):
                    due = datetime.fromisoformat(r["cuando"])
                    late = (now - due).total_seconds() > 120
                    self._store.mark_fired(r["id"], now)
                    try:
                        self._on_fire(r, late)
                    except Exception as e:
                        print(f"[Recordatorios] Error al avisar: {e}")
            except Exception as e:
                print(f"[Recordatorios] {e}")
            nxt = self._store.next_due()
            wait = 30.0 if nxt is None else max(0.5, min(30.0, (nxt - datetime.now()).total_seconds()))
            self._store.changed.wait(wait)
            self._store.changed.clear()


# ══════════════════════════════════════════════════════════════════════════════
#  SONIDOS (avisos generados al vuelo, sin ficheros externos)
# ══════════════════════════════════════════════════════════════════════════════

def _make_tone_wav(path: Path, notes, rate: int = 22050, volume: float = 0.55):
    """Genera un WAV con una secuencia de notas [(frecuencia_Hz, duración_s), …]."""
    frames = bytearray()
    for freq, dur in notes:
        n = int(rate * dur)
        rel = max(1, int(rate * 0.012))
        for i in range(n):
            tt = i / rate
            env = min(1.0, i / (rate * 0.008)) * math.exp(-2.6 * tt / max(dur, 0.01))
            if i > n - rel:
                env *= (n - i) / rel
            s = (math.sin(2 * math.pi * freq * tt) + 0.3 * math.sin(4 * math.pi * freq * tt)) / 1.3
            frames += struct.pack("<h", int(max(-1.0, min(1.0, s * env * volume)) * 32767))
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(bytes(frames))


def _sound_file(name: str) -> Optional[Path]:
    """Ruta del sonido integrado (lo genera la primera vez)."""
    specs = {
        "activacion":   [(880.0, 0.07), (1318.5, 0.11)],
        "recordatorio": [(1046.5, 0.16), (783.99, 0.16), (1046.5, 0.16), (1318.5, 0.42)],
        "confirmar":    [(659.25, 0.09), (0.0, 0.05), (659.25, 0.09), (880.0, 0.14)],
        "parada":       [(523.25, 0.12), (392.0, 0.22)],
    }
    path = SOUNDS_DIR / f"{name}.wav"
    try:
        if not path.exists():
            _make_tone_wav(path, specs[name])
        return path
    except Exception as e:
        print(f"[Sonido] No se pudo generar {name}: {e}")
        return None


def play_sound(name_or_path: str, wait: bool = False):
    """Reproduce un sonido integrado ('activacion', 'recordatorio') o un fichero .wav/.mp3."""
    p = Path(name_or_path) if os.path.sep in str(name_or_path) or "/" in str(name_or_path) \
        else _sound_file(name_or_path)
    if not p or not Path(p).exists():
        p = _sound_file("recordatorio")
    if not p:
        return
    try:
        if str(p).lower().endswith(".wav") and HAS_WINSOUND:
            flags = winsound.SND_FILENAME | winsound.SND_NODEFAULT
            if not wait:
                flags |= winsound.SND_ASYNC
            winsound.PlaySound(str(p), flags)
            return
        os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
        import pygame
        if not pygame.mixer.get_init():
            pygame.mixer.init()
        snd = pygame.mixer.Sound(str(p))
        ch = snd.play()
        if wait:
            while ch.get_busy():
                time.sleep(0.05)
    except Exception as e:
        print(f"[Sonido] {e}")
        if HAS_WINSOUND:
            try:
                winsound.MessageBeep(winsound.MB_ICONASTERISK)
            except Exception:
                pass


# ══════════════════════════════════════════════════════════════════════════════
#  VISIÓN: captura de pantalla y foto con la cámara
# ══════════════════════════════════════════════════════════════════════════════

def _cursor_monitor_rect():
    """((izq, arriba, der, abajo), es_principal) del monitor donde está el ratón (píxeles físicos)."""
    if not IS_WINDOWS:
        return None
    try:
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.windll.user32
        old_ctx = None
        try:   # mismo contexto DPI que usa Pillow al capturar (per-monitor aware)
            user32.SetThreadDpiAwarenessContext.restype = ctypes.c_void_p
            user32.SetThreadDpiAwarenessContext.argtypes = [ctypes.c_void_p]
            old_ctx = user32.SetThreadDpiAwarenessContext(ctypes.c_void_p(-3))
        except Exception:
            old_ctx = None
        try:
            class MONITORINFO(ctypes.Structure):
                _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
                            ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]
            pt = wintypes.POINT()
            user32.GetCursorPos(ctypes.byref(pt))
            user32.MonitorFromPoint.restype = ctypes.c_void_p
            user32.MonitorFromPoint.argtypes = [wintypes.POINT, wintypes.DWORD]
            hmon = user32.MonitorFromPoint(pt, 2)          # MONITOR_DEFAULTTONEAREST
            mi = MONITORINFO()
            mi.cbSize = ctypes.sizeof(MONITORINFO)
            user32.GetMonitorInfoW.argtypes = [ctypes.c_void_p, ctypes.POINTER(MONITORINFO)]
            if not user32.GetMonitorInfoW(hmon, ctypes.byref(mi)):
                return None
            r = mi.rcMonitor
            return (r.left, r.top, r.right, r.bottom), bool(mi.dwFlags & 1)
        finally:
            if old_ctx:
                user32.SetThreadDpiAwarenessContext(ctypes.c_void_p(old_ctx))
    except Exception as e:
        print(f"[Captura] No se pudo localizar el monitor: {e}")
        return None


def capture_screen(all_screens: bool = False):
    """Devuelve (imagen PIL, descripción)."""
    from PIL import ImageGrab
    if all_screens:
        return ImageGrab.grab(all_screens=True).convert("RGB"), "todas las pantallas"
    info = _cursor_monitor_rect()
    if info:
        rect, primary = info
        img = ImageGrab.grab(bbox=rect, all_screens=True)
        desc = "pantalla principal" if primary else "pantalla secundaria (donde está el ratón)"
    else:
        img, desc = ImageGrab.grab(), "pantalla principal"
    return img.convert("RGB"), desc


def capture_camera(index: int = 0, warmup_s: float = 0.9):
    """Hace una foto con la webcam. Devuelve (imagen PIL, descripción)."""
    try:
        import cv2
    except ImportError:
        raise RuntimeError("OpenCV no está instalado (pip install opencv-python)")
    backends = [cv2.CAP_DSHOW, cv2.CAP_MSMF, cv2.CAP_ANY] if IS_WINDOWS else [cv2.CAP_ANY]
    cap = None
    for be in backends:
        try:
            cap = cv2.VideoCapture(int(index), be)
            if cap is not None and cap.isOpened():
                break
        except Exception:
            pass
        if cap is not None:
            cap.release()
        cap = None
    if cap is None:
        raise RuntimeError(f"no se pudo abrir la cámara nº {index} (¿la está usando otra app?)")
    try:
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
        frame, n = None, 0
        t_end = time.time() + 6.0
        t_min = time.time() + warmup_s           # dar tiempo a la exposición automática
        while time.time() < t_end:
            ok, f = cap.read()
            if ok and f is not None:
                frame, n = f, n + 1
                if n >= 5 and time.time() >= t_min:
                    break
            else:
                time.sleep(0.05)
        if frame is None:
            raise RuntimeError("la cámara no devolvió ninguna imagen")
        img = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        desc = f"cámara nº {index}"
        if float(frame.mean()) < 8:
            desc += " — la imagen está casi negra (¿cámara tapada o apagada?)"
        return img, desc
    finally:
        cap.release()


def _image_to_b64_jpeg(img, max_side: int = 1600, quality: int = 85) -> str:
    im = img
    if max(im.size) > max_side:
        im = im.copy()
        im.thumbnail((max_side, max_side), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=quality, optimize=True)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def save_capture(img, kind: str, keep: int = 30) -> Optional[Path]:
    """Guarda la imagen en la carpeta capturas y borra las más antiguas (conserva 'keep')."""
    try:
        CAPTURES_DIR.mkdir(parents=True, exist_ok=True)
        path = CAPTURES_DIR / f"{kind}_{datetime.now():%Y%m%d_%H%M%S}.jpg"
        img.save(path, "JPEG", quality=92)
        files = sorted(CAPTURES_DIR.glob("*.jpg"), key=lambda p: p.stat().st_mtime, reverse=True)
        for old in files[max(1, int(keep)):]:
            try:
                old.unlink()
            except Exception:
                pass
        return path
    except Exception as e:
        print(f"[Captura] No se pudo guardar: {e}")
        return None


# ══════════════════════════════════════════════════════════════════════════════
#  CONTROL DEL PC: ratón, teclado y elementos de las ventanas
# ══════════════════════════════════════════════════════════════════════════════
# La IA no tiene que adivinar coordenadas: recibe una captura con los elementos
# de las ventanas numerados (los que Windows ofrece a los lectores de pantalla)
# y, si se quiere, una cuadrícula. Dice «clic en el 12» o «clic en la casilla
# D3» y aquí se calcula el punto exacto en la pantalla.

try:
    from pynput import mouse as _pynput_mouse, keyboard as _pynput_keyboard
    HAS_PC_INPUT = IS_WINDOWS
except ImportError:
    HAS_PC_INPUT = False

if IS_WINDOWS:
    import ctypes
    from ctypes import wintypes

_PC_TAGS = ["PC_VER", "PC_CLIC", "PC_DOBLE_CLIC", "PC_ESCRIBIR", "PC_TECLA", "PC_ARRASTRAR",
            "PC_RUEDA", "PC_MOVER", "PC_ZOOM", "PC_VENTANA", "PC_ESPERAR"]
_PC_BODY_TAGS = {"PC_ESCRIBIR", "PC_TECLA", "PC_VENTANA"}
_PC_OPEN_RE   = re.compile(r"<(PC_[A-Za-z_]+)\b([^>]*?)(/?)>", re.IGNORECASE)
_PC_ANY_RE    = re.compile(r"<(?:%s)\b" % "|".join(_PC_TAGS), re.IGNORECASE)
_PC_CELL_RE   = re.compile(r"^\s*([A-Za-z])\s*(\d{1,2})(?:\s*[.\-_]\s*(\d{1,2}))?\s*$")
_PC_XY_RE     = re.compile(r"^\s*\(?\s*(?:x\s*[=:]\s*)?(\d+(?:\.\d+)?)\s*[,;\s]\s*"
                           r"(?:y\s*[=:]\s*)?(\d+(?:\.\d+)?)\s*\)?\s*$", re.IGNORECASE)
_PC_YES       = {"si", "sí", "true", "1", "yes", "y", "s"}

# Nombres de botones que indican una acción difícil de deshacer
_PC_DANGER_RE = re.compile(
    r"\b(eliminar|elimina|borrar|borra|suprimir|delete|remove|desinstalar|uninstall|"
    r"formatear|format|vaciar|empty|enviar|envia|send|publicar|publica|post|tweet|"
    r"twittear|comprar|compra|buy|purchase|pagar|paga|pay|checkout|tramitar|"
    r"realizar pedido|place order|confirmar (?:compra|pago|pedido)|transferir|transfer|"
    r"no guardar|don'?t save|descartar|discard|restablecer|reset|cerrar sesion|"
    r"sign out|log ?out|apagar|shut ?down|reiniciar|restart|suscribir|subscribe)\b")
_PC_CHAT_RE   = re.compile(r"mensaje|message|chat|coment|comment|respuesta|reply|tweet|post|publica")
_PC_DANGER_KEYS = {"alt+f4", "shift+delete", "ctrl+shift+delete", "ctrl+alt+delete"}

_PC_KEY_ALIASES = {
    "enter": "enter", "intro": "enter", "return": "enter", "entrar": "enter",
    "esc": "esc", "escape": "esc", "tab": "tab", "tabulador": "tab",
    "espacio": "space", "space": "space", "barra espaciadora": "space",
    "retroceso": "backspace", "backspace": "backspace", "borrar": "backspace",
    "supr": "delete", "suprimir": "delete", "delete": "delete", "del": "delete",
    "arriba": "up", "abajo": "down", "izquierda": "left", "derecha": "right",
    "flecha arriba": "up", "flecha abajo": "down", "flecha izquierda": "left",
    "flecha derecha": "right", "up": "up", "down": "down", "left": "left", "right": "right",
    "inicio": "home", "home": "home", "fin": "end", "end": "end",
    "repag": "page_up", "re pag": "page_up", "pageup": "page_up", "page_up": "page_up",
    "pgup": "page_up", "avpag": "page_down", "av pag": "page_down", "pagedown": "page_down",
    "page_down": "page_down", "pgdn": "page_down",
    "ctrl": "ctrl", "control": "ctrl", "shift": "shift", "mayus": "shift",
    "mayusculas": "shift", "alt": "alt", "altgr": "alt_gr", "alt gr": "alt_gr",
    "win": "cmd", "windows": "cmd", "tecla windows": "cmd", "super": "cmd", "cmd": "cmd",
    "meta": "cmd", "inicio windows": "cmd",
    "insert": "insert", "insertar": "insert", "ins": "insert",
    "imprpant": "print_screen", "impr pant": "print_screen", "printscreen": "print_screen",
    "print_screen": "print_screen", "menu": "menu", "bloqmayus": "caps_lock",
    "capslock": "caps_lock", "caps_lock": "caps_lock",
    "subir volumen": "media_volume_up", "volumen+": "media_volume_up",
    "volume_up": "media_volume_up", "bajar volumen": "media_volume_down",
    "volumen-": "media_volume_down", "volume_down": "media_volume_down",
    "silenciar": "media_volume_mute", "mute": "media_volume_mute",
    "play": "media_play_pause", "pausa": "media_play_pause", "reproducir": "media_play_pause",
    "play_pause": "media_play_pause", "siguiente": "media_next", "next": "media_next",
    "anterior": "media_previous", "previous": "media_previous",
}
_PC_MODIFIERS = {"ctrl", "shift", "alt", "alt_gr", "cmd"}

_UIA_TYPE_NAMES = {
    50000: "botón", 50001: "calendario", 50002: "casilla", 50003: "desplegable",
    50004: "campo de texto", 50005: "enlace", 50006: "imagen", 50007: "elemento de lista",
    50011: "opción de menú", 50013: "opción", 50015: "deslizador", 50016: "selector",
    50019: "pestaña", 50020: "texto", 50024: "elemento de árbol", 50025: "control",
    50026: "grupo", 50029: "elemento", 50030: "documento", 50031: "botón desplegable",
    50035: "encabezado",
}
_UIA_ALWAYS = {50000, 50002, 50003, 50004, 50005, 50007, 50011, 50013, 50015, 50016,
               50019, 50024, 50029, 50031, 50035}
_UIA_IF_NAMED = {50001, 50006, 50025, 50026}       # solo si tienen nombre y aceptan foco

_PC_PALETTE = [(255, 214, 0), (0, 230, 118), (41, 182, 255), (255, 64, 129),
               (255, 145, 0), (179, 136, 255), (29, 233, 182), (255, 82, 82)]


class PcError(Exception):
    pass


def parse_pc_actions(text: str) -> list:
    """Acciones de control del PC en el orden en que aparecen: [{tag, attrs, body}]."""
    out, pos, text = [], 0, text or ""
    while True:
        m = _PC_OPEN_RE.search(text, pos)
        if not m:
            break
        name, pos = m.group(1).upper(), m.end()
        if name not in _PC_TAGS:
            continue
        body = ""
        if not m.group(3):
            close = re.compile(rf"\s*</{name}\s*>" if name not in _PC_BODY_TAGS
                               else rf"</{name}\s*>", re.IGNORECASE)
            if name in _PC_BODY_TAGS:
                c = close.search(text, pos)
                nxt = _PC_OPEN_RE.search(text, pos)
                if c and (nxt is None or nxt.start() >= c.start()):
                    body, pos = text[pos:c.start()], c.end()
            else:
                c = close.match(text, pos)
                if c:
                    pos = c.end()
        out.append({"tag": name, "attrs": _parse_attrs(m.group(2)),
                    "body": _html.unescape(body.strip("\r\n"))})
    return out


def _pc_attr(attrs: dict, *names, default=""):
    for n in names:
        v = attrs.get(_norm_text(n))
        if v not in (None, ""):
            return v
    return default


def _pc_yes(v) -> bool:
    return _norm_text(v) in _PC_YES


def _pc_col_label(i: int) -> str:
    return chr(ord("A") + i)


class _PcDpi:
    """El hilo trabaja en píxeles físicos (sin el escalado de Windows) mientras dura el bloque."""
    def __enter__(self):
        self._old = None
        try:
            u = ctypes.windll.user32
            u.SetThreadDpiAwarenessContext.restype = ctypes.c_void_p
            u.SetThreadDpiAwarenessContext.argtypes = [ctypes.c_void_p]
            self._old = u.SetThreadDpiAwarenessContext(ctypes.c_void_p(-4))   # per-monitor v2
        except Exception:
            self._old = None
        return self

    def __exit__(self, *exc):
        if self._old:
            try:
                ctypes.windll.user32.SetThreadDpiAwarenessContext(ctypes.c_void_p(self._old))
            except Exception:
                pass
        return False


# ── Ventanas de Windows ──────────────────────────────────────────────────────
def _win_title(hwnd) -> str:
    u = ctypes.windll.user32
    n = u.GetWindowTextLengthW(hwnd)
    if n <= 0:
        return ""
    buf = ctypes.create_unicode_buffer(n + 1)
    u.GetWindowTextW(hwnd, buf, n + 1)
    return buf.value


def _win_class(hwnd) -> str:
    buf = ctypes.create_unicode_buffer(256)
    ctypes.windll.user32.GetClassNameW(hwnd, buf, 256)
    return buf.value


def _win_pid(hwnd) -> int:
    pid = wintypes.DWORD()
    ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value


def _win_rect(hwnd):
    r = wintypes.RECT()
    if not ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(r)):
        return None
    return (r.left, r.top, r.right, r.bottom)


def _win_cloaked(hwnd) -> bool:
    try:
        val = ctypes.c_int(0)
        ctypes.windll.dwmapi.DwmGetWindowAttribute(hwnd, 14, ctypes.byref(val), ctypes.sizeof(val))
        return bool(val.value)
    except Exception:
        return False


def _top_windows() -> list:
    """Ventanas visibles de primer nivel, de la de arriba a la de abajo (orden Z)."""
    u = ctypes.windll.user32
    res = []
    proto = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def cb(hwnd, _lp):
        try:
            if u.IsWindowVisible(hwnd) and not _win_cloaked(hwnd):
                res.append(hwnd)
        except Exception:
            pass
        return True
    u.EnumWindows(proto(cb), 0)
    return res


def _is_app_window(hwnd) -> bool:
    """¿Es una ventana normal de aplicación (con título, no una herramienta ni el escritorio)?"""
    u = ctypes.windll.user32
    u.GetWindowLongW.restype = ctypes.c_long
    ex = u.GetWindowLongW(hwnd, -20)
    if ex & 0x80 and not ex & 0x40000:          # WS_EX_TOOLWINDOW sin WS_EX_APPWINDOW
        return False
    if u.GetWindow(hwnd, 4) and not ex & 0x40000:   # tiene propietario (diálogo flotante)
        return bool(_win_title(hwnd))
    cls = _win_class(hwnd)
    if cls in ("Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd"):
        return False
    return bool(_win_title(hwnd).strip())


def _monitor_rect_of_point(x: int, y: int):
    u = ctypes.windll.user32

    class MONITORINFO(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
                    ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]
    u.MonitorFromPoint.restype = ctypes.c_void_p
    u.MonitorFromPoint.argtypes = [wintypes.POINT, wintypes.DWORD]
    hmon = u.MonitorFromPoint(wintypes.POINT(int(x), int(y)), 2)
    mi = MONITORINFO()
    mi.cbSize = ctypes.sizeof(MONITORINFO)
    u.GetMonitorInfoW.argtypes = [ctypes.c_void_p, ctypes.POINTER(MONITORINFO)]
    if not u.GetMonitorInfoW(hmon, ctypes.byref(mi)):
        return None
    r = mi.rcMonitor
    return (r.left, r.top, r.right, r.bottom)


def _cursor_pos():
    pt = wintypes.POINT()
    ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y


def pc_fullscreen_app() -> Optional[str]:
    """Título de la app a pantalla completa en primer plano (juego, vídeo…) o None."""
    if not IS_WINDOWS:
        return None
    with _PcDpi():
        u = ctypes.windll.user32
        hwnd = u.GetForegroundWindow()
        if not hwnd or _win_pid(hwnd) == os.getpid():
            return None
        if _win_class(hwnd) in ("Progman", "WorkerW", "Shell_TrayWnd"):
            return None
        u.GetWindowLongW.restype = ctypes.c_long
        style = u.GetWindowLongW(hwnd, -16)
        if u.IsZoomed(hwnd) and style & 0x00C00000:      # maximizada con barra de título
            return None
        r = _win_rect(hwnd)
        if not r:
            return None
        mon = _monitor_rect_of_point((r[0] + r[2]) // 2, (r[1] + r[3]) // 2)
        if mon and r[0] <= mon[0] and r[1] <= mon[1] and r[2] >= mon[2] and r[3] >= mon[3]:
            return _win_title(hwnd) or _win_class(hwnd)
    return None


def pc_activate_window(hwnd) -> bool:
    u = ctypes.windll.user32
    try:
        if u.IsIconic(hwnd):
            u.ShowWindow(hwnd, 9)                        # SW_RESTORE
        u.SetForegroundWindow(hwnd)
        time.sleep(0.12)
        if u.GetForegroundWindow() != hwnd:
            u.SwitchToThisWindow(hwnd, True)
            time.sleep(0.15)
        return u.GetForegroundWindow() == hwnd
    except Exception:
        return False


# ── UI Automation (elementos de las ventanas) ────────────────────────────────
_UIA_LOCAL = threading.local()


def _uia():
    """Objeto IUIAutomation de este hilo (COM es por hilo). → (uia, módulo, petición de caché)"""
    st = getattr(_UIA_LOCAL, "st", None)
    if st is None:
        import comtypes
        import comtypes.client
        try:
            comtypes.CoInitialize()
        except OSError:
            pass
        comtypes.client.GetModule("UIAutomationCore.dll")
        from comtypes.gen import UIAutomationClient as U
        uia = comtypes.client.CreateObject(U.CUIAutomation, interface=U.IUIAutomation)
        cr = uia.CreateCacheRequest()
        for pid in (U.UIA_NamePropertyId, U.UIA_ControlTypePropertyId,
                    U.UIA_BoundingRectanglePropertyId, U.UIA_IsEnabledPropertyId,
                    U.UIA_IsKeyboardFocusablePropertyId):
            cr.AddProperty(pid)
        cond = uia.CreateAndCondition(
            uia.ControlViewCondition,
            uia.CreatePropertyCondition(U.UIA_IsOffscreenPropertyId, False))
        st = (uia, U, cr, cond)
        _UIA_LOCAL.st = st
    return st


def uia_available() -> bool:
    if not IS_WINDOWS:
        return False
    try:
        import comtypes  # noqa: F401
        return True
    except ImportError:
        return False


def uia_element_at(x: int, y: int) -> Tuple[str, str]:
    """(tipo, nombre) del elemento que hay en un punto de la pantalla (píxeles físicos)."""
    try:
        with _PcDpi():
            uia, U, _cr, _c = _uia()
            e = uia.ElementFromPoint(wintypes.POINT(int(x), int(y)))
            return _UIA_TYPE_NAMES.get(e.CurrentControlType, "elemento"), _one_line(e.CurrentName)[:80]
    except Exception:
        return "", ""


def uia_focused() -> Tuple[str, str]:
    try:
        with _PcDpi():
            uia, U, _cr, _c = _uia()
            e = uia.GetFocusedElement()
            return _UIA_TYPE_NAMES.get(e.CurrentControlType, "elemento"), _one_line(e.CurrentName)[:80]
    except Exception:
        return "", ""


def uia_collect(hwnds: list, clip, max_items: int = 160) -> list:
    """
    Elementos con los que se puede interactuar en esas ventanas (de arriba abajo en
    orden Z). Los que quedan tapados por una ventana de encima se descartan.
    → [{"name", "type", "rect": (l, t, r, b)}]   (píxeles físicos)
    """
    with _PcDpi():
        uia, U, cr, cond = _uia()
        items, seen, above = [], set(), []
        cl, ct, cr_, cb = clip
        for hwnd in hwnds:
            wr = _win_rect(hwnd)
            if not wr:
                continue
            try:
                arr = uia.ElementFromHandle(hwnd).FindAllBuildCache(U.TreeScope_Descendants, cond, cr)
            except Exception as e:
                print(f"[PC] UIA no pudo leer «{_win_title(hwnd)}»: {e}")
                above.append(wr)
                continue
            for i in range(arr.Length):
                try:
                    e = arr.GetElement(i)
                    ctype = e.CachedControlType
                    name = _one_line(e.CachedName)
                    is_text = False
                    if ctype not in _UIA_ALWAYS:
                        if ctype == 50020 and name and len(name) <= 60:
                            is_text = True      # texto con nombre (etiquetas, objetos…)
                        elif ctype not in _UIA_IF_NAMED or not name or not e.CachedIsKeyboardFocusable:
                            continue
                    if not e.CachedIsEnabled:
                        continue
                    r = e.CachedBoundingRectangle
                    l, t, rr, b = max(r.left, cl, wr[0]), max(r.top, ct, wr[1]), \
                        min(r.right, cr_, wr[2]), min(r.bottom, cb, wr[3])
                    if rr - l < 4 or b - t < 4:
                        continue
                    if (rr - l) * (b - t) > 0.6 * (wr[2] - wr[0]) * (wr[3] - wr[1]):
                        continue                    # ocupa casi toda la ventana: no ayuda
                    cx, cy = (l + rr) // 2, (t + b) // 2
                    if any(a[0] <= cx < a[2] and a[1] <= cy < a[3] for a in above):
                        continue                    # tapado por una ventana de encima
                    key = (round(l / 6), round(t / 6), round(rr / 6), round(b / 6), name)
                    if key in seen:
                        continue
                    seen.add(key)
                    if ctype == 50004 and not name:
                        name = "(sin nombre)"
                    items.append({"name": name[:70], "type": _UIA_TYPE_NAMES.get(ctype, "elemento"),
                                  "rect": (l, t, rr, b), "ctype": ctype, "text": is_text})
                except Exception:
                    continue
            above.append(wr)
        # Si hay demasiados, los textos son los primeros en quedarse fuera
        if len(items) > max_items:
            ctrls = [it for it in items if not it["text"]]
            items = ctrls[:max_items] + [it for it in items if it["text"]][:max(0, max_items - len(ctrls))]
        # Orden de lectura: por filas de arriba abajo y de izquierda a derecha
        items.sort(key=lambda it: (round(((it["rect"][1] + it["rect"][3]) / 2) / 18),
                                   it["rect"][0]))
        return items


def _pc_font(size: int):
    try:
        from PIL import ImageFont
        for name in ("segoeuib.ttf", "arialbd.ttf", "arial.ttf"):
            try:
                return ImageFont.truetype(name, size)
            except Exception:
                continue
        return ImageFont.load_default()
    except Exception:
        return None


# ── Controlador ──────────────────────────────────────────────────────────────
class PcController:
    """
    Una sesión de control del PC (dura lo que tarda la IA en completar una orden).
    hooks (llamadas a la interfaz, se ejecutan en el hilo de Tk):
        protect(on)        → oculta de las capturas el orbe, el popup y el aviso
        banner(texto|None) → muestra/actualiza/quita el aviso «Rubencho controla el PC»
        confirm(acción, motivo) → "si" | "no" | "todo"
        post(texto)        → añade una línea al popup
    """
    GRID_COLS = 16
    SUB = 6                              # subcasillas por lado al hacer zoom (6×6 = 36)

    def __init__(self, cfg: dict, hooks: dict = None):
        self.cfg = cfg
        self.hooks = hooks or {}
        self.stop_event = threading.Event()
        self.stop_reason = ""
        self.allow_all = False
        self.monitor = None              # (izq, arriba, der, abajo) en píxeles físicos
        self.obs = None                  # última observación
        self.actions_done = 0
        self.observations = 0
        self._mouse = self._kb = None
        self._listener = None
        self._watch = None
        self._active = False
        self._last_pos = None
        self._inject_t = 0.0
        self.last_image = None
        self._danger_done = False

    # ── opciones ─────────────────────────────────────────────────────────────
    def _opt(self, key, default=None):
        return self.cfg.get(key, DEFAULT_CONFIG.get(key, default))

    def _hook(self, name, *args, default=None):
        fn = self.hooks.get(name)
        if fn is None:
            return default
        try:
            return fn(*args)
        except Exception as e:
            print(f"[PC] hook {name}: {e}")
            return default

    def _post(self, s: str):
        self._hook("post", s)

    # ── sesión ───────────────────────────────────────────────────────────────
    def start(self, banner: bool = True) -> Tuple[bool, str]:
        if not IS_WINDOWS:
            return False, "el control del PC solo funciona en Windows"
        if not HAS_PC_INPUT:
            return False, "falta la librería pynput (pip install pynput)"
        with _PcDpi():
            info = _cursor_monitor_rect()
            if info:
                self.monitor = info[0]
            else:
                u = ctypes.windll.user32
                self.monitor = (0, 0, u.GetSystemMetrics(0), u.GetSystemMetrics(1))
            self._last_pos = _cursor_pos()
        self._mouse = _pynput_mouse.Controller()
        self._kb = _pynput_keyboard.Controller()
        self._active = True
        self._hook("protect", True)
        if banner and self._opt("pc_show_banner", True):
            self._hook("banner", "Preparando…")
        self._start_stop_watchers()
        self._release_own_foreground()
        return True, ""

    def stop(self):
        if not self._active:
            return
        self._active = False
        try:
            if self._listener is not None:
                self._listener.stop()
        except Exception:
            pass
        self._listener = None
        self._hook("banner", None)
        self._hook("protect", False)

    def request_stop(self, reason: str):
        if not self.stop_event.is_set():
            self.stop_reason = reason
            self.stop_event.set()
            print(f"⛔  Control del PC detenido: {reason}")
            play_sound("parada")
            self._hook("banner", f"⛔ Detenido: {reason}")

    def _check_stop(self):
        if self.stop_event.is_set():
            raise PcError("__stop__")

    def _start_stop_watchers(self):
        hk = str(self._opt("pc_stop_hotkey", "esc") or "").strip().lower()
        if self._opt("pc_stop_hotkey_enabled", True) and hk:
            target = _PC_KEY_ALIASES.get(_norm_text(hk), _norm_text(hk))

            def on_press(key, injected=False):
                if injected or time.time() < self._inject_t:
                    return
                name = getattr(key, "name", None) or getattr(key, "char", None) or ""
                if str(name).lower() == target:
                    self.request_stop(f"has pulsado {hk.upper()}")
            try:
                self._listener = _pynput_keyboard.Listener(on_press=on_press)
                self._listener.daemon = True
                self._listener.start()
            except Exception as e:
                print(f"[PC] No se pudo vigilar la tecla de parada: {e}")
        if self._opt("pc_stop_corner", True) or self._opt("pc_stop_on_user_mouse", False):
            self._watch = threading.Thread(target=self._watch_mouse, daemon=True, name="pc-freno")
            self._watch.start()

    def _watch_mouse(self):
        with _PcDpi():
            u = ctypes.windll.user32
            vx, vy = u.GetSystemMetrics(76), u.GetSystemMetrics(77)
            vw, vh = u.GetSystemMetrics(78), u.GetSystemMetrics(79)
            corners_rects = [(vx, vy, vx + vw, vy + vh)]
            if self.monitor:
                corners_rects.append(self.monitor)
            while self._active and not self.stop_event.is_set():
                time.sleep(0.08)
                if time.time() < self._inject_t:
                    continue
                x, y = _cursor_pos()
                lx, ly = self._last_pos or (x, y)
                ours = abs(x - lx) <= 2 and abs(y - ly) <= 2
                if ours:
                    continue
                if self._opt("pc_stop_corner", True):
                    for (l, t, r, b) in corners_rects:
                        if (x <= l + 3 or x >= r - 4) and (y <= t + 3 or y >= b - 4):
                            self.request_stop("has llevado el ratón a una esquina")
                            return
                if self._opt("pc_stop_on_user_mouse", False) and \
                        math.hypot(x - lx, y - ly) > 40:
                    self.request_stop("has movido el ratón")
                    return

    def _release_own_foreground(self):
        """Si el foco lo tiene una ventana de Rubencho, se pasa a la ventana de debajo."""
        try:
            u = ctypes.windll.user32
            fg = u.GetForegroundWindow()
            if fg and _win_pid(fg) != os.getpid():
                return
            for hwnd in _top_windows():
                if _win_pid(hwnd) != os.getpid() and _is_app_window(hwnd) and not u.IsIconic(hwnd):
                    pc_activate_window(hwnd)
                    return
        except Exception as e:
            print(f"[PC] {e}")

    # ── coordenadas ──────────────────────────────────────────────────────────
    def _img_size(self):
        l, t, r, b = self.monitor
        mw, mh = r - l, b - t
        w = int(float(self._opt("pc_image_width", 1280) or 1280))
        w = max(640, min(w, mw))
        return w, max(1, round(mh * w / mw))

    def _grid(self, iw, ih):
        cols = self.GRID_COLS
        rows = max(4, min(20, round(cols * ih / iw)))
        return cols, rows

    def _to_phys(self, x: float, y: float):
        """Punto de la imagen enviada → píxel físico de la pantalla."""
        l, t, r, b = self.monitor
        iw, ih = self.obs["img_size"] if self.obs else self._img_size()
        px = l + x * (r - l) / iw
        py = t + y * (b - t) / ih
        return int(min(max(px, l), r - 1)), int(min(max(py, t), b - 1))

    def _to_img(self, px: float, py: float):
        l, t, r, b = self.monitor
        iw, ih = self.obs["img_size"] if self.obs else self._img_size()
        return (px - l) * iw / (r - l), (py - t) * ih / (b - t)

    def _cell_rect_img(self, col: int, row: int):
        iw, ih = self.obs["img_size"] if self.obs else self._img_size()
        cols, rows = self._grid(iw, ih)
        cw, ch = iw / cols, ih / rows
        return col * cw, row * ch, (col + 1) * cw, (row + 1) * ch

    def _zoom_region(self, col: int, row: int):
        """Zona del zoom de una casilla: la casilla y media casilla alrededor (en la imagen)."""
        iw, ih = self.obs["img_size"] if self.obs else self._img_size()
        x0, y0, x1, y1 = self._cell_rect_img(col, row)
        cw, ch = x1 - x0, y1 - y0
        return max(0, x0 - cw / 2), max(0, y0 - ch / 2), min(iw, x1 + cw / 2), min(ih, y1 + ch / 2)

    def _cell_of_img(self, x, y) -> str:
        iw, ih = self.obs["img_size"] if self.obs else self._img_size()
        cols, rows = self._grid(iw, ih)
        c = int(min(cols - 1, max(0, x * cols / iw)))
        r = int(min(rows - 1, max(0, y * rows / ih)))
        return f"{_pc_col_label(c)}{r + 1}"

    def _resolve(self, value: str, kind: str = "") -> Tuple[int, int, str, Optional[dict]]:
        """
        Traduce «12», «D3», «D3.7» o «640,360» (o id=/celda=/x,y) a un punto físico.
        → (x, y, descripción, elemento | None)
        """
        v = str(value or "").strip().strip('"\'')
        low = _norm_text(v)
        for pre in ("id:", "id ", "elemento:", "elemento ", "#"):
            if low.startswith(pre):
                v, kind = v[len(pre):].strip(), "id"
                break
        for pre in ("celda:", "celda ", "casilla:", "casilla "):
            if low.startswith(pre):
                v, kind = v[len(pre):].strip(), "celda"
                break
        if kind in ("", "id") and re.fullmatch(r"\d+", v):
            if not self.obs or not self.obs.get("elements"):
                raise PcError(f"no hay lista de elementos: haz antes <PC_VER/>")
            idx = int(v)
            els = self.obs["elements"]
            if not 1 <= idx <= len(els):
                raise PcError(f"no existe el elemento {idx} (la última lista va del 1 al {len(els)})")
            el = els[idx - 1]
            l, t, r, b = el["rect"]
            return (l + r) // 2, (t + b) // 2, f"{el['type']} «{el['name']}» (nº {idx})", el
        m = _PC_CELL_RE.match(v)
        if m and kind in ("", "celda"):
            iw, ih = self.obs["img_size"] if self.obs else self._img_size()
            cols, rows = self._grid(iw, ih)
            col = ord(m.group(1).upper()) - ord("A")
            row = int(m.group(2)) - 1
            if not (0 <= col < cols and 0 <= row < rows):
                raise PcError(f"la casilla {v} no existe (columnas A–{_pc_col_label(cols - 1)}, "
                              f"filas 1–{rows})")
            x0, y0, x1, y1 = self._cell_rect_img(col, row)
            label = f"{m.group(1).upper()}{row + 1}"
            if m.group(3):
                n = int(m.group(3))
                if not 1 <= n <= self.SUB * self.SUB:
                    raise PcError(f"la subcasilla debe ir del 1 al {self.SUB * self.SUB}")
                sr, sc = (n - 1) // self.SUB, (n - 1) % self.SUB
                zx0, zy0, zx1, zy1 = self._zoom_region(col, row)
                sw, sh = (zx1 - zx0) / self.SUB, (zy1 - zy0) / self.SUB
                x, y = zx0 + (sc + 0.5) * sw, zy0 + (sr + 0.5) * sh
                label += f".{n}"
            else:
                x, y = (x0 + x1) / 2, (y0 + y1) / 2
            px, py = self._to_phys(x, y)
            return px, py, f"casilla {label}", None
        m = _PC_XY_RE.match(v)
        if m:
            x, y = float(m.group(1)), float(m.group(2))
            iw, ih = self.obs["img_size"] if self.obs else self._img_size()
            if not (0 <= x <= iw and 0 <= y <= ih):
                raise PcError(f"el punto ({v}) está fuera de la imagen ({iw}×{ih})")
            px, py = self._to_phys(x, y)
            return px, py, f"punto ({int(x)}, {int(y)})", None
        raise PcError(f"no entiendo «{value}»: usa un número de elemento, una casilla (D3) o x,y")

    def _target(self, attrs: dict, required: bool = True, prefix: str = ""):
        """Destino de una acción a partir de sus atributos."""
        if not prefix:
            x, y = _pc_attr(attrs, "x"), _pc_attr(attrs, "y")
            if x and y:
                return self._resolve(f"{x},{y}")
            v = _pc_attr(attrs, "id", "elemento", "numero")
            if v:
                return self._resolve(v, "id")
            v = _pc_attr(attrs, "celda", "casilla")
            if v:
                return self._resolve(v, "celda")
            v = _pc_attr(attrs, "en", "donde", "sobre", "punto")
            if v:
                return self._resolve(v)
        else:
            v = _pc_attr(attrs, prefix)
            if v:
                return self._resolve(v)
        if required:
            raise PcError("falta dónde: usa id=\"N\", celda=\"D3\" o x=\"…\" y=\"…\"")
        return None

    # ── entrada (ratón y teclado) ────────────────────────────────────────────
    def _mark_inject(self, secs: float = 0.35):
        self._inject_t = time.time() + secs

    def _move(self, x: int, y: int):
        self._check_stop()
        with _PcDpi():
            self._mark_inject()
            self._mouse.position = (int(x), int(y))
            self._last_pos = (int(x), int(y))

    def _click(self, x, y, button: str = "left", count: int = 1):
        self._move(x, y)
        time.sleep(0.06)
        btn = getattr(_pynput_mouse.Button, button, _pynput_mouse.Button.left)
        with _PcDpi():
            self._mark_inject()
            self._mouse.click(btn, count)

    def _drag(self, a, b):
        self._move(*a)
        time.sleep(0.08)
        with _PcDpi():
            self._mark_inject(2.0)
            self._mouse.press(_pynput_mouse.Button.left)
            try:
                steps = 18
                for i in range(1, steps + 1):
                    if self.stop_event.is_set():
                        break
                    x = a[0] + (b[0] - a[0]) * i / steps
                    y = a[1] + (b[1] - a[1]) * i / steps
                    self._mouse.position = (int(x), int(y))
                    self._last_pos = (int(x), int(y))
                    time.sleep(0.018)
                time.sleep(0.08)
            finally:
                self._mouse.release(_pynput_mouse.Button.left)
                self._mark_inject()

    def _key_obj(self, name: str):
        K = _pynput_keyboard.Key
        n = _norm_text(name)
        alias = _PC_KEY_ALIASES.get(n, n)
        if re.fullmatch(r"f([1-9]|1\d|2[0-4])", alias):
            return getattr(K, alias)
        if hasattr(K, alias) and len(alias) > 1:
            return getattr(K, alias)
        if len(name.strip()) == 1:
            ch = name.strip()
            vk = ctypes.windll.user32.VkKeyScanW(ctypes.c_wchar(ch)) & 0xFF if IS_WINDOWS else 0xFF
            if vk != 0xFF:
                return _pynput_keyboard.KeyCode.from_vk(vk)
            return _pynput_keyboard.KeyCode.from_char(ch)
        raise PcError(f"no conozco la tecla «{name}»")

    def _parse_combo(self, spec: str) -> list:
        """«ctrl+shift+t» → [Key.ctrl, Key.shift, KeyCode('t')]"""
        spec = re.sub(r"\s*\+\s*", "+", spec.strip())
        parts = [p for p in spec.split("+") if p] or ["+"]
        return [self._key_obj(p) for p in parts]

    def _press_combo(self, keys: list):
        self._check_stop()
        with _PcDpi():
            self._mark_inject(1.0)
            mods, main = keys[:-1], keys[-1]
            for k in mods:
                self._kb.press(k)
            try:
                self._kb.press(main)
                time.sleep(0.03)
                self._kb.release(main)
            finally:
                for k in reversed(mods):
                    self._kb.release(k)
            self._mark_inject()

    def _type(self, text: str):
        self._check_stop()
        with _PcDpi():
            # Se escribe en trozos para poder parar a mitad si el usuario lo pide
            for i in range(0, len(text), 24):
                self._check_stop()
                self._mark_inject(1.0)
                self._kb.type(text[i:i + 24])
            self._mark_inject()

    # ── precauciones ─────────────────────────────────────────────────────────
    def _danger_reason(self, act: dict, el: Optional[dict], point=None, combo: str = "") -> str:
        """Por qué una acción puede ser peligrosa ("" si no lo parece)."""
        attrs = act["attrs"]
        if _pc_yes(_pc_attr(attrs, "peligroso", "peligrosa", "confirmar")):
            return "la IA la ha marcado como peligrosa"
        if combo and _norm_text(combo).replace(" ", "") in _PC_DANGER_KEYS:
            return f"el atajo {combo} puede cerrar o borrar cosas"
        name = el["name"] if el else ""
        if not name and point is not None and act["tag"] in ("PC_CLIC", "PC_DOBLE_CLIC"):
            _t, name = uia_element_at(*point)
        if name and act["tag"] in ("PC_CLIC", "PC_DOBLE_CLIC") and _PC_DANGER_RE.search(_norm_text(name)):
            return f"el botón se llama «{name}»"
        if act["tag"] == "PC_ESCRIBIR" and _pc_yes(_pc_attr(attrs, "enter", "intro")):
            fname = name or uia_focused()[1]
            if fname and _PC_CHAT_RE.search(_norm_text(fname)):
                return f"al pulsar Intro en «{fname}» puede enviarse un mensaje"
        return ""

    def _approved(self, desc: str, reason: str) -> bool:
        """¿Se puede hacer la acción? Pide confirmación si es peligrosa y está activada la opción."""
        if not reason:
            return True
        self._danger_done = True           # aunque no haga falta confirmar, no se debe repetir
        if not self._opt("pc_confirm_dangerous", True) or self.allow_all:
            return True
        return self._confirm(desc, reason)

    def _confirm(self, desc: str, reason: str) -> bool:
        play_sound("confirmar")
        self._hook("banner", f"✋ Esperando tu confirmación: {desc}")
        prev = None
        try:
            prev = ctypes.windll.user32.GetForegroundWindow()
        except Exception:
            pass
        ans = self._hook("confirm", desc, reason, default="no") or "no"
        if prev:
            pc_activate_window(prev)          # el foco vuelve a donde estaba
        if ans == "todo":
            self.allow_all = True
        return ans in ("si", "todo")

    def _check_fullscreen(self):
        if self._opt("pc_block_fullscreen", True):
            app = pc_fullscreen_app()
            if app:
                raise PcError(f"__fullscreen__{app}")

    # ── observar ─────────────────────────────────────────────────────────────
    def _scan_windows(self):
        """→ (ventanas a analizar en orden Z, ventana activa, otras ventanas abiertas)"""
        u = ctypes.windll.user32
        own = os.getpid()
        mon = self.monitor
        fg = u.GetForegroundWindow()
        if fg and _win_pid(fg) == own:
            fg = None
        tops = [h for h in _top_windows() if _win_pid(h) != own]
        if fg is None:
            fg = next((h for h in tops if _is_app_window(h) and not u.IsIconic(h)), None)
        fg_pid = _win_pid(fg) if fg else -1
        scan = []
        for h in tops:
            if h == fg:
                scan.append(h)
                break
            r = _win_rect(h)
            if not r or r[2] <= mon[0] or r[0] >= mon[2] or r[3] <= mon[1] or r[1] >= mon[3]:
                continue
            cls = _win_class(h)
            if cls == "#32768" or _win_pid(h) == fg_pid or cls.startswith("Xaml_WindowedPopup"):
                scan.append(h)                 # menús y ventanas flotantes encima de la activa
        for h in tops:
            if _win_class(h) in ("Shell_TrayWnd", "Shell_SecondaryTrayWnd"):
                r = _win_rect(h)
                if r and r[0] < mon[2] and r[2] > mon[0] and r[1] < mon[3] and r[3] > mon[1]:
                    scan.append(h)            # barra de tareas de esta pantalla
        others = []
        for h in tops:
            if h != fg and _is_app_window(h):
                t = _one_line(_win_title(h))[:60]
                if t and t not in others:
                    others.append(t + (" (minimizada)" if u.IsIconic(h) else ""))
        return scan, fg, others[:14]

    def observe(self, for_ai: bool = True) -> Tuple[str, Optional[str], object]:
        """Captura + elementos. → (texto para la IA, imagen b64 | None, imagen PIL anotada)"""
        from PIL import ImageGrab
        self._check_stop()
        self._hook("protect", True)
        time.sleep(0.05)
        use_el = bool(self._opt("pc_use_elements", True)) and uia_available()
        use_grid = bool(self._opt("pc_use_grid", True))
        with _PcDpi():
            shot = ImageGrab.grab(bbox=self.monitor, all_screens=True).convert("RGB")
            scan, fg, others = self._scan_windows()
            elements = []
            if use_el and scan:
                try:
                    elements = uia_collect(scan, self.monitor,
                                           int(float(self._opt("pc_max_elements", 160) or 160)))
                except Exception as e:
                    print(f"[PC] No se pudieron leer los elementos: {e}")
            fg_title = _one_line(_win_title(fg))[:80] if fg else ""
        ftype, fname = uia_focused() if use_el else ("", "")
        iw, ih = self._img_size()
        img = shot.resize((iw, ih), Image.LANCZOS) if shot.size != (iw, ih) else shot
        self.obs = {"img_size": (iw, ih), "elements": elements, "time": time.time()}
        # ¿Cuánto ha cambiado la pantalla desde la captura anterior? (señal objetiva para la IA)
        try:
            small = shot.convert("L").resize((192, 108))
            prev, self._prev_small = getattr(self, "_prev_small", None), small
            if prev is not None:
                diff = [abs(a - b) > 22 for a, b in zip(small.getdata(), prev.getdata())]
                self.last_change = sum(diff) / len(diff)
            else:
                self.last_change = None
        except Exception:
            self.last_change = None
        img = self._annotate(img, elements, use_grid)
        self.observations += 1
        self.last_image = img

        l, t, r, b = self.monitor
        lines = [f"Pantalla de {r - l}×{b - t} px; la imagen adjunta mide {iw}×{ih} px "
                 f"(x = 0…{iw}, y = 0…{ih})."]
        if use_grid:
            cols, rows = self._grid(iw, ih)
            lines.append(f"Cuadrícula: columnas A–{_pc_col_label(cols - 1)} (de izquierda a derecha), "
                         f"filas 1–{rows} (de arriba abajo).")
        lines.append(f"Ventana activa: «{fg_title or 'escritorio'}»")
        if fname or ftype:
            lines.append(f"Foco del teclado: {ftype} «{fname}»")
        if others:
            lines.append("Otras ventanas abiertas: " + " · ".join(f"«{o}»" for o in others))
        if use_el:
            if elements:
                el_lines = []
                for i, el in enumerate(elements, 1):
                    cx, cy = self._to_img((el["rect"][0] + el["rect"][2]) / 2,
                                          (el["rect"][1] + el["rect"][3]) / 2)
                    where = f" · {self._cell_of_img(cx, cy)}" if use_grid else ""
                    nm = f" «{el['name']}»" if el["name"] else ""
                    el_lines.append(f"[{i}] {el['type']}{nm}{where}")
                lines.append("<ELEMENTOS> (números = recuadros de la imagen)\n" +
                             "\n".join(el_lines) + "\n</ELEMENTOS>")
            else:
                lines.append("Esta ventana no ofrece elementos" +
                             (": usa la cuadrícula." if use_grid else ": usa coordenadas x,y."))
        b64 = _image_to_b64_jpeg(img, max_side=max(iw, ih), quality=82) if for_ai else None
        return "\n".join(lines), b64, img

    def _annotate(self, img, elements: list, grid: bool):
        from PIL import ImageDraw
        base = img.convert("RGBA")
        over = Image.new("RGBA", base.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(over)
        iw, ih = base.size
        if grid:
            cols, rows = self._grid(iw, ih)
            f = _pc_font(9)
            for c in range(1, cols):
                x = round(c * iw / cols)
                d.line([(x, 0), (x, ih)], fill=(0, 229, 255, 70), width=1)
            for r in range(1, rows):
                y = round(r * ih / rows)
                d.line([(0, y), (iw, y)], fill=(0, 229, 255, 70), width=1)
            for c in range(cols):
                for r in range(rows):
                    x0, y0 = c * iw / cols, r * ih / rows
                    lab = f"{_pc_col_label(c)}{r + 1}"
                    d.rectangle([x0 + 1, y0 + 1, x0 + 6 * len(lab) + 4, y0 + 12], fill=(0, 0, 0, 100))
                    d.text((x0 + 2, y0 + 1), lab, fill=(0, 229, 255, 190), font=f)
        if elements:
            # Etiquetas pequeñas (≈11 px) pegadas a la esquina del recuadro, para no tapar
            # el texto de los elementos; los números siguen siendo legibles para la IA.
            f = _pc_font(9)
            for i, el in enumerate(elements, 1):
                col = _PC_PALETTE[i % len(_PC_PALETTE)]
                x0, y0 = self._to_img(el["rect"][0], el["rect"][1])
                x1, y1 = self._to_img(el["rect"][2], el["rect"][3])
                d.rectangle([x0, y0, x1, y1], outline=col + (200,), width=1)
                lab = str(i)
                try:
                    tw = d.textbbox((0, 0), lab, font=f)[2] + 4
                except Exception:
                    tw = 6 * len(lab) + 4
                lh = 11
                ly = y0 - lh if y0 >= lh else y0
                d.rectangle([x0, ly, x0 + tw, ly + lh], fill=col + (215,))
                d.text((x0 + 2, ly - 1), lab, fill=(0, 0, 0, 255), font=f)
        return Image.alpha_composite(base, over).convert("RGB")

    def zoom(self, attrs: dict) -> Tuple[str, Optional[str], object]:
        """Imagen ampliada de una casilla con subcasillas numeradas para afinar."""
        from PIL import ImageGrab, ImageDraw
        self._check_stop()
        if not self.obs:
            raise PcError("haz antes <PC_VER/>")
        cell = _pc_attr(attrs, "celda", "casilla", "en", "id")
        x, y = _pc_attr(attrs, "x"), _pc_attr(attrs, "y")
        if x and y:
            ix, iy = self._to_img(*self._resolve(f"{x},{y}")[:2])
            cell = self._cell_of_img(ix, iy)
        elif cell and not _PC_CELL_RE.match(cell):
            ix, iy = self._to_img(*self._resolve(cell)[:2])
            cell = self._cell_of_img(ix, iy)
        m = _PC_CELL_RE.match(cell or "")
        if not m:
            raise PcError('indica la casilla: <PC_ZOOM celda="D3"/>')
        col, row = ord(m.group(1).upper()) - ord("A"), int(m.group(2)) - 1
        iw, ih = self.obs["img_size"]
        cols, rows = self._grid(iw, ih)
        if not (0 <= col < cols and 0 <= row < rows):
            raise PcError(f"la casilla {cell} no existe")
        x0, y0, x1, y1 = self._cell_rect_img(col, row)
        zx0, zy0, zx1, zy1 = self._zoom_region(col, row)
        p0, p1 = self._to_phys(zx0, zy0), self._to_phys(zx1, zy1)
        self._hook("protect", True)
        with _PcDpi():
            shot = ImageGrab.grab(bbox=(p0[0], p0[1], p1[0] + 1, p1[1] + 1), all_screens=True).convert("RGB")
        scale = 720 / max(1, shot.size[0])
        big = shot.resize((720, max(1, round(shot.size[1] * scale))), Image.LANCZOS).convert("RGBA")
        over = Image.new("RGBA", big.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(over)
        bx = lambda v: (v - zx0) * big.size[0] / (zx1 - zx0)
        by = lambda v: (v - zy0) * big.size[1] / (zy1 - zy0)
        W, H = big.size
        d.rectangle([bx(x0), by(y0), bx(x1), by(y1)], outline=(255, 214, 0, 120), width=2)
        f = _pc_font(14)
        sw, sh = W / self.SUB, H / self.SUB
        for i in range(1, self.SUB):
            d.line([(i * sw, 0), (i * sw, H)], fill=(0, 229, 255, 170), width=1)
            d.line([(0, i * sh), (W, i * sh)], fill=(0, 229, 255, 170), width=1)
        for n in range(self.SUB * self.SUB):
            r_, c_ = divmod(n, self.SUB)
            tx, ty = c_ * sw + 3, r_ * sh + 2
            d.rectangle([tx - 1, ty, tx + 8 * len(str(n + 1)) + 3, ty + 16], fill=(0, 0, 0, 150))
            d.text((tx + 1, ty), str(n + 1), fill=(0, 229, 255, 255), font=f)
        img = Image.alpha_composite(big, over).convert("RGB")
        label = f"{m.group(1).upper()}{row + 1}"
        text = (f"Zoom de la zona de la casilla {label}: la casilla (recuadro amarillo) y media "
                f"casilla alrededor. La imagen está dividida en {self.SUB * self.SUB} subcasillas "
                f"(cuadrícula azul) numeradas de izquierda a derecha y de arriba abajo, de 1 a "
                f"{self.SUB * self.SUB}. Para actuar en una usa celda=\"{label}.N\", p. ej. "
                f"<PC_CLIC celda=\"{label}.15\"/> o, al arrastrar, desde=\"{label}.15\". Elige la "
                f"subcasilla que caiga en el CENTRO del objeto.")
        return text, _image_to_b64_jpeg(img, max_side=720, quality=85), img

    # ── ejecutar acciones ────────────────────────────────────────────────────
    def run(self, actions: list, can_see: bool = True) -> Tuple[str, Optional[str]]:
        """
        Ejecuta las acciones en orden. Se para en la primera que falle, al pedir una
        captura/zoom o si el usuario detiene el control. → (texto para la IA, imagen b64)
        """
        lines, image, did_input = [], None, False
        self._danger_done = False
        delay = max(0.05, float(self._opt("pc_action_delay", 0.6) or 0.6))
        skipped = 0
        for n, act in enumerate(actions):
            tag, attrs, body = act["tag"], act["attrs"], act["body"]
            try:
                self._check_stop()
                if tag == "PC_VER":
                    text, image, _img = self.observe()
                    lines.append("📸 Captura nueva:\n" + text)
                    skipped = len(actions) - n - 1
                    break
                if tag == "PC_ZOOM":
                    text, image, _img = self.zoom(attrs)
                    lines.append("🔍 " + text)
                    skipped = len(actions) - n - 1
                    break
                if tag == "PC_ESPERAR":
                    secs = min(15.0, max(0.1, float(_pc_attr(attrs, "segundos", "s", default="1")
                                                   .replace(",", "."))))
                    self._banner(f"Esperando {secs:g} s")
                    t_end = time.time() + secs
                    while time.time() < t_end:
                        self._check_stop()
                        time.sleep(0.05)
                    lines.append(f"✅ Esperado {secs:g} s")
                    continue
                if tag == "PC_VENTANA":
                    q = _norm_text(body or _pc_attr(attrs, "titulo", "nombre"))
                    if not q:
                        raise PcError("falta el título de la ventana")
                    with _PcDpi():
                        cands = [(h, _win_title(h)) for h in _top_windows()
                                 if _win_pid(h) != os.getpid() and _is_app_window(h)]
                        cands += [(h, _win_title(h)) for h in self._minimized_windows()]
                        match = [(h, t) for h, t in cands if q in _norm_text(t)]
                    if not match:
                        raise PcError(f"no hay ninguna ventana abierta con «{body}» en el título")
                    h, title = min(match, key=lambda ht: len(ht[1]))
                    self._check_fullscreen()
                    self._banner(f"Activando «{title[:40]}»")
                    ok = pc_activate_window(h)
                    lines.append(f"✅ Ventana al frente: «{title}»" if ok else
                                 f"⚠️ Intenté traer «{title}» al frente, pero Windows no lo permitió")
                    did_input = True
                    time.sleep(delay)
                    continue

                # Acciones con ratón o teclado
                self._check_fullscreen()
                if tag in ("PC_CLIC", "PC_DOBLE_CLIC"):
                    x, y, desc, el = self._target(attrs)
                    btn_raw = _norm_text(_pc_attr(attrs, "boton", "button", default="izquierdo"))
                    button = ("right" if btn_raw.startswith(("der", "right")) else
                              "middle" if btn_raw.startswith(("med", "cen", "mid")) else "left")
                    count = 2 if (tag == "PC_DOBLE_CLIC" or _pc_yes(_pc_attr(attrs, "doble"))) else 1
                    what = ("Doble clic" if count == 2 else
                            "Clic derecho" if button == "right" else
                            "Clic central" if button == "middle" else "Clic")
                    full = f"{what} en {desc}"
                    reason = self._danger_reason(act, el, (x, y))
                    if not self._approved(full, reason):
                        lines.append(f"🚫 El usuario NO ha permitido: {full}. No la repitas; "
                                     "pregúntale qué quiere hacer.")
                        skipped = len(actions) - n - 1
                        break
                    self._banner(full)
                    self._post(f"🖱  {full}\n")
                    self._click(x, y, button, count)
                    lines.append(f"✅ {full}")
                elif tag == "PC_MOVER":
                    x, y, desc, _el = self._target(attrs)
                    self._banner(f"Ratón sobre {desc}")
                    self._move(x, y)
                    lines.append(f"✅ Ratón sobre {desc}")
                elif tag == "PC_ESCRIBIR":
                    text = body if body else _pc_attr(attrs, "texto")
                    tgt = self._target(attrs, required=False)
                    el = tgt[3] if tgt else None
                    enter = _pc_yes(_pc_attr(attrs, "enter", "intro"))
                    short = text if len(text) <= 40 else text[:37] + "…"
                    full = f"Escribir «{short}»" + (f" en {tgt[2]}" if tgt else "") + \
                           (" y pulsar Intro" if enter else "")
                    reason = self._danger_reason(act, el)
                    if not self._approved(full, reason):
                        lines.append(f"🚫 El usuario NO ha permitido: {full}. No la repitas.")
                        skipped = len(actions) - n - 1
                        break
                    self._banner(full)
                    self._post(f"⌨️  {full}\n")
                    if tgt:
                        self._click(tgt[0], tgt[1])
                        time.sleep(0.15)
                    if _pc_yes(_pc_attr(attrs, "borrar", "reemplazar", "limpiar")):
                        # Ctrl+A no funciona en algunos campos antiguos: también Fin + Mayús+Inicio
                        for combo in ("ctrl+a", "delete", "end", "shift+home", "delete"):
                            self._press_combo(self._parse_combo(combo))
                            time.sleep(0.03)
                    if text:
                        self._type(text)
                    if enter:
                        time.sleep(0.05)
                        self._press_combo(self._parse_combo("enter"))
                    lines.append(f"✅ {full}")
                elif tag == "PC_TECLA":
                    spec = (body or _pc_attr(attrs, "tecla", "teclas")).strip()
                    if not spec:
                        raise PcError("falta la tecla")
                    times = max(1, min(30, int(float(_pc_attr(attrs, "veces", default="1") or 1))))
                    combos = [c for c in re.split(r"\s*[,;]\s*|\s{2,}", spec) if c] \
                        if re.search(r"[,;]", spec) else [spec]
                    parsed = [(c, self._parse_combo(c)) for c in combos]
                    label = ", ".join(c for c, _ in parsed) + (f" ×{times}" if times > 1 else "")
                    reason = ""
                    for c, _k in parsed:
                        reason = reason or self._danger_reason(act, None, combo=c)
                    if not self._approved(f"Pulsar {label}", reason):
                        lines.append(f"🚫 El usuario NO ha permitido pulsar {label}. No lo repitas.")
                        skipped = len(actions) - n - 1
                        break
                    self._banner(f"Pulsando {label}")
                    self._post(f"⌨️  Tecla: {label}\n")
                    for _ in range(times):
                        for _c, keys in parsed:
                            self._press_combo(keys)
                            time.sleep(0.06)
                    lines.append(f"✅ Pulsado {label}")
                elif tag == "PC_ARRASTRAR":
                    a = self._target(attrs, prefix="desde") if _pc_attr(attrs, "desde") else None
                    b = self._target(attrs, prefix="hasta") if _pc_attr(attrs, "hasta") else None
                    if not a or not b:
                        raise PcError('usa desde="…" y hasta="…" (número de elemento, casilla o x,y)')
                    full = f"Arrastrar desde {a[2]} hasta {b[2]}"
                    reason = self._danger_reason(act, None)
                    if not self._approved(full, reason):
                        lines.append(f"🚫 El usuario NO ha permitido: {full}.")
                        skipped = len(actions) - n - 1
                        break
                    self._banner(full)
                    self._post(f"🖱  {full}\n")
                    self._drag(a[:2], b[:2])
                    lines.append(f"✅ {full}")
                elif tag == "PC_RUEDA":
                    dir_ = _norm_text(_pc_attr(attrs, "direccion", "hacia", default="abajo"))
                    amount = max(1, min(40, int(float(_pc_attr(attrs, "cantidad", "veces",
                                                                default="5") or 5))))
                    tgt = self._target(attrs, required=False)
                    if tgt:
                        self._move(tgt[0], tgt[1])
                        time.sleep(0.05)
                    dx, dy = {"arriba": (0, 1), "up": (0, 1), "izquierda": (-1, 0), "left": (-1, 0),
                              "derecha": (1, 0), "right": (1, 0)}.get(dir_, (0, -1))
                    full = f"Rueda del ratón hacia {dir_ or 'abajo'} ×{amount}" + \
                           (f" sobre {tgt[2]}" if tgt else "")
                    self._banner(full)
                    self._post(f"🖱  {full}\n")
                    with _PcDpi():
                        self._mark_inject()
                        self._mouse.scroll(dx * amount, dy * amount)
                    lines.append(f"✅ {full}")
                else:
                    continue
                self.actions_done += 1
                did_input = True
                time.sleep(delay)
            except PcError as e:
                msg = str(e)
                if msg == "__stop__":
                    lines.append(f"⛔ EL USUARIO HA DETENIDO EL CONTROL DEL PC ({self.stop_reason}). "
                                 "No hagas más acciones de control: dile brevemente lo que llegaste "
                                 "a hacer.")
                    return "\n".join(lines), None
                if msg.startswith("__fullscreen__"):
                    lines.append(f"🎮 No actúo: «{msg[14:]}» está a pantalla completa (puede ser un "
                                 "juego o un vídeo). Dile al usuario que salga de la pantalla "
                                 "completa si quiere que controles el PC.")
                    return "\n".join(lines), None
                lines.append(f"❌ {tag}: {msg}")
                skipped = len(actions) - n - 1
                break
            except Exception as e:
                lines.append(f"❌ {tag}: error inesperado: {e}")
                skipped = len(actions) - n - 1
                break
        if skipped:
            lines.append(f"(Las {skipped} acciones siguientes NO se han hecho: revisa el resultado "
                         "y vuelve a pedirlas si siguen haciendo falta.)")
        if did_input and image is None:
            if self._opt("pc_verify", True) and not self.stop_event.is_set():
                try:
                    time.sleep(0.25)
                    text, image, _img = self.observe()
                    lines.append("📸 Captura DESPUÉS de las acciones. Compárala con lo que querías "
                                 "conseguir: si no ha cambiado lo esperado, no ha funcionado y "
                                 "debes intentarlo de otra forma antes de responder.\n" + text)
                    ch = getattr(self, "last_change", None)
                    if self._danger_done:
                        lines.append("⚠️ Has hecho una acción importante (enviar, borrar, comprar…). "
                                     "NO la repitas aunque parezca que no ha cambiado nada: podría "
                                     "hacerse dos veces. Si dudas de si ha funcionado, díselo al "
                                     "usuario y pregúntale.")
                    elif ch is not None and ch < 0.002:
                        lines.append("⚠️ ATENCIÓN: la pantalla prácticamente NO ha cambiado con tus "
                                     "acciones. Si esperabas un cambio visible (algo movido, abierto, "
                                     "escrito…), la acción ha fallado: probablemente no apuntaste "
                                     "al sitio correcto. Mira bien la captura, afina (zoom o x,y) "
                                     "y repítela.")
                    elif ch is not None:
                        lines.append(f"(Ha cambiado aprox. el {ch * 100:.1f}% de la pantalla.)")
                except PcError:
                    pass
            else:
                lines.append("(No se ha hecho captura: usa <PC_VER/> si necesitas ver el resultado.)")
        if image is not None and not can_see:
            lines.append("⚠️ Tu modelo no puede ver imágenes: guíate solo por la lista de elementos.")
            image = None
        self._banner("Pensando…")
        return "\n".join(lines), image

    def _banner(self, text: str):
        if self._opt("pc_show_banner", True):
            self._hook("banner", text)

    def _minimized_windows(self) -> list:
        u = ctypes.windll.user32
        return [h for h in _top_windows() if u.IsIconic(h) and _win_pid(h) != os.getpid()
                and _is_app_window(h)]


def pc_preview(cfg: dict) -> Tuple[Optional[Path], str]:
    """Hace una observación de prueba (botón de Configuración). → (ruta de la imagen, resumen)"""
    c = PcController(cfg)
    if not IS_WINDOWS:
        return None, "Solo funciona en Windows"
    with _PcDpi():
        info = _cursor_monitor_rect()
        c.monitor = info[0] if info else (0, 0, ctypes.windll.user32.GetSystemMetrics(0),
                                          ctypes.windll.user32.GetSystemMetrics(1))
    t0 = time.time()
    text, _b64, img = c.observe(for_ai=False)
    n = len(c.obs["elements"]) if c.obs else 0
    path = save_capture(img, "control", int(cfg.get("captures_keep", 30)))
    return path, f"{n} elementos en {time.time() - t0:.1f} s"


# ══════════════════════════════════════════════════════════════════════════════
#  OLLAMA: capacidades de los modelos
# ══════════════════════════════════════════════════════════════════════════════

_MODEL_CAPS: dict = {}


class OllamaError(Exception):
    pass


def ollama_capabilities(host: str, model: str) -> Optional[set]:
    """Capacidades del modelo ('vision', 'thinking', 'tools'…) o None si no se pueden saber."""
    key = (host.rstrip("/"), model)
    if key in _MODEL_CAPS:
        return _MODEL_CAPS[key]
    if not HAS_REQUESTS or not model:
        return None
    try:
        r = requests.post(f"{host}/api/show", json={"model": model}, timeout=8)
        if r.status_code == 200:
            caps = r.json().get("capabilities")
            caps = {str(c).lower() for c in caps} if isinstance(caps, list) else None
            _MODEL_CAPS[key] = caps
            return caps
        if r.status_code == 404:
            _MODEL_CAPS[key] = None
    except Exception:
        pass
    return None


def is_cloud_model(model: str) -> bool:
    m = (model or "").lower()
    return m.endswith(":cloud") or m.endswith("-cloud") or "-cloud:" in m


def _ollama_error_message(resp, model: str) -> str:
    err = ""
    try:
        err = str(resp.json().get("error", ""))
    except Exception:
        err = (resp.text or "")[:300]
    low = err.lower()
    if resp.status_code == 404 or "not found" in low:
        return (f"El modelo '{model}' no está instalado en Ollama.\n"
                f"Instálalo con:  ollama pull {model}")
    if "unauthorized" in low or resp.status_code == 401:
        return ("Ollama rechazó la petición (no autorizado). Si usas un modelo cloud, "
                "inicia sesión con:  ollama signin")
    return f"Ollama devolvió un error ({resp.status_code}): {err or 'sin detalles'}"


# ══════════════════════════════════════════════════════════════════════════════
#  WHISPER: aceleración por GPU y filtro de alucinaciones
# ══════════════════════════════════════════════════════════════════════════════

def _register_cuda_dll_dirs():
    """
    Si están instalados los paquetes pip de NVIDIA (nvidia-cublas-cu12 y
    nvidia-cudnn-cu12), registra sus DLL para que faster-whisper pueda usar la GPU.
    """
    if not IS_WINDOWS or globals().get("_CUDA_DIRS_DONE"):
        return
    globals()["_CUDA_DIRS_DONE"] = True
    for bin_dir in _cuda_dll_dirs():
        try:
            os.add_dll_directory(str(bin_dir))
            os.environ["PATH"] = str(bin_dir) + os.pathsep + os.environ.get("PATH", "")
            print(f"[GPU] Librerías de NVIDIA: {bin_dir}")
        except Exception:
            pass


def _cuda_dll_dirs() -> list:
    """
    Carpetas con cuBLAS 12 y cuDNN 9: junto a la aplicación (carpeta «gpu»), en el
    Python actual o, en la aplicación compilada, en cualquier Python del usuario que
    tenga instalados nvidia-cublas-cu12 y nvidia-cudnn-cu12, o en el CUDA Toolkit.
    """
    import glob
    found, seen = [], set()

    def add(d):
        d = Path(d)
        key = str(d).lower()
        if d.is_dir() and key not in seen:
            seen.add(key)
            found.append(d)

    add(APP_HOME / "gpu")
    roots = []
    try:
        import site
        roots += list(site.getsitepackages()) + [site.getusersitepackages()]
    except Exception:
        pass
    la, ap = os.environ.get("LOCALAPPDATA", ""), os.environ.get("APPDATA", "")
    pats = [
        rf"{la}\Packages\PythonSoftwareFoundation.Python.3.*\LocalCache\local-packages\Python3*\site-packages",
        rf"{la}\Programs\Python\Python3*\Lib\site-packages",
        rf"{ap}\Python\Python3*\site-packages",
        r"C:\Program Files\Python3*\Lib\site-packages",
    ]
    for pat in pats:
        roots += sorted(glob.glob(pat), reverse=True)        # primero las versiones más nuevas
    for want in ("cublas", "cudnn"):
        for root in roots:
            d = Path(root) / "nvidia" / want / "bin"
            if d.is_dir():
                add(d)
                break
    cuda = os.environ.get("CUDA_PATH", "")
    if cuda:
        add(Path(cuda) / "bin")
    return found


def cuda_whisper_available() -> Tuple[bool, str]:
    """¿Puede faster-whisper usar la GPU? Comprueba GPU + cuBLAS 12 + cuDNN 9 sin colgarse."""
    try:
        import ctranslate2
        if ctranslate2.get_cuda_device_count() <= 0:
            return False, "no hay GPU NVIDIA compatible"
    except Exception as e:
        return False, f"ctranslate2 no disponible ({e})"
    if IS_WINDOWS:
        import ctypes
        _register_cuda_dll_dirs()
        for dll in ("cublas64_12.dll", "cudnn64_9.dll"):
            try:
                ctypes.WinDLL(dll)
            except OSError:
                return False, (f"falta {dll} (librerías de NVIDIA para la GPU: "
                               f"pip install nvidia-cublas-cu12 nvidia-cudnn-cu12)")
    return True, "ok"


# Frases que Whisper "se inventa" con ruido o silencio (finales de vídeos de YouTube…)
_WHISPER_HALLUCINATIONS = {
    "gracias por ver el video", "gracias por ver", "muchas gracias por ver el video",
    "gracias por ver el video y hasta la proxima", "gracias por vernos",
    "subtitulos realizados por la comunidad de amara.org",
    "subtitulos por la comunidad de amara.org", "subtitulado por la comunidad de amara.org",
    "transcripcion realizada por la comunidad de amara.org",
    "suscribete", "suscribete al canal", "no olvides suscribirte", "suscribete y dale like",
    "dale like y suscribete", "musica", "gracias por su atencion", "nos vemos en el proximo video",
    "y hasta aqui el video de hoy", "gracias a todos por ver el video",
    "thank you for watching", "thanks for watching",
}


def is_whisper_hallucination(text: str) -> bool:
    n = _norm_text(text).strip(" .!¡?¿,;:-—[]()♪*")
    if not n:
        return True
    return n in _WHISPER_HALLUCINATIONS or "amara.org" in n


# ── Markdown → tk.Text tags ──────────────────────────────────────────────────
def render_markdown(widget, text: str, colors: dict, images: list = None):
    """
    Inserta texto con formato markdown en un tk.Text widget.
    Soporta: **negrita**, *cursiva*, `código`, ```bloques```, # Cabeceras,
    - listas, > notas, ---  y, al final, miniaturas de imágenes [(PhotoImage, ruta)].
    """
    widget.config(state='normal')
    widget.delete('1.0', 'end')

    bg      = colors.get("bg",     "#0d1117")
    fg      = colors.get("fg",     "#e2e8f0")
    acc     = colors.get("accent", "#4f8ef7")
    code_bg = colors.get("code_bg","#1e2530")

    widget.tag_configure("bold",    font=("Segoe UI", 10, "bold"), foreground=fg)
    widget.tag_configure("italic",  font=("Segoe UI", 10, "italic"), foreground=fg)
    widget.tag_configure("code",    font=("Consolas", 9), background=code_bg,
                         foreground="#7dd3fc")
    widget.tag_configure("h1",      font=("Segoe UI", 13, "bold"), foreground=acc)
    widget.tag_configure("h2",      font=("Segoe UI", 12, "bold"), foreground=acc)
    widget.tag_configure("h3",      font=("Segoe UI", 11, "bold"), foreground=acc)
    widget.tag_configure("bullet",  lmargin1=16, lmargin2=28, foreground=fg)
    widget.tag_configure("hr",      foreground=colors.get("muted","#333"))
    widget.tag_configure("normal",  foreground=fg)
    widget.tag_configure("muted",   foreground=colors.get("muted","#7d8590"))
    widget.tag_configure("codeblock", font=("Consolas", 9), background=code_bg,
                         foreground="#7dd3fc", lmargin1=8, lmargin2=8)
    widget.tag_configure("note", font=("Segoe UI", 9, "italic"),
                         foreground=colors.get("muted", "#7d8590"), lmargin1=4, lmargin2=18)

    lines = text.split("\n")
    in_code = False
    for line in lines:
        if line.strip().startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            widget.insert("end", line + "\n", "codeblock")
            continue
        qm = re.match(r"^>\s?(.*)", line)
        if qm:
            widget.insert("end", qm.group(1) + "\n", "note")
            continue
        hm = re.match(r"^(#{1,3})\s+(.*)", line)
        if hm:
            level = len(hm.group(1))
            widget.insert("end", hm.group(2) + "\n", f"h{level}")
            continue
        if re.match(r"^-{3,}\s*$", line):
            widget.insert("end", "─" * 40 + "\n", "muted")
            continue
        bm = re.match(r"^\s*[\-\*•]\s+(.*)", line)
        if bm:
            _insert_inline(widget, "• " + bm.group(1) + "\n", "bullet", colors)
            continue
        _insert_inline(widget, line + "\n", "normal", colors)

    for n, (photo, path) in enumerate(images or []):
        _insert_image(widget, photo, path, n)

    widget.config(state='disabled')


def _insert_image(widget, photo, path, n: int = 0):
    """Inserta una miniatura clicable (abre la imagen completa) en un tk.Text."""
    try:
        tag = f"img{n}_{id(photo)}"
        widget.insert("end", "\n")
        idx = widget.index("end-1c")
        widget.image_create("end", image=photo, padx=2, pady=4)
        widget.tag_add(tag, idx)
        widget.tag_bind(tag, "<Button-1>", lambda _e, p=path: _open_path(p))
        widget.tag_bind(tag, "<Enter>", lambda _e: widget.config(cursor="hand2"))
        widget.tag_bind(tag, "<Leave>", lambda _e: widget.config(cursor="arrow"))
        widget.insert("end", "\n")
    except Exception as e:
        print(f"[Popup] Miniatura: {e}")


def _insert_inline(widget, line: str, base_tag: str, colors: dict):
    """Procesa **bold**, *italic* y `code` dentro de una línea."""
    pattern = re.compile(r"(\*\*(.+?)\*\*|\*(.+?)\*|`(.+?)`)")
    pos = 0
    for m in pattern.finditer(line):
        if m.start() > pos:
            widget.insert("end", line[pos:m.start()], base_tag)
        if m.group(2) is not None:
            widget.insert("end", m.group(2), "bold")
        elif m.group(3) is not None:
            widget.insert("end", m.group(3), "italic")
        elif m.group(4) is not None:
            widget.insert("end", m.group(4), "code")
        pos = m.end()
    if pos < len(line):
        widget.insert("end", line[pos:], base_tag)


# ── Config ────────────────────────────────────────────────────────────────────
CONFIG_FILE = APP_DIR / "config.json"

DEFAULT_CONFIG = {
    "autostart":            False,
    "minimize_to_tray":     True,
    "always_on_top_popup":  True,
    "sound_feedback":       False,
    "language":             "es-ES",
    "wake_word":            "asistente",
    "custom_wake_word":     "",
    "use_custom_wake_word": False,
    "wake_words_presets": [
        "jarvis","nova","nexus","atlas","echo",
        "computer","asistente","despierta","oye","hola"
    ],
    "speech_engine":        "vosk",       # palabra clave: "vosk" (local, al instante) o "google"
    "command_engine":       "whisper",
    "whisper_model":        "small",
    "whisper_device":       "auto",
    "whisper_language":     "es",
    "vosk_model_path":      "",
    "silence_timeout":      2.5,
    "phrase_time_limit":    15.0,
    "wake_phrase_limit":    3.0,
    "pause_threshold":          1.8,
    "phrase_threshold":         0.1,
    "non_speaking_duration":    0.4,
    "dynamic_energy_threshold": True,
    "energy_threshold":         300,
    "dynamic_energy_ratio":     1.5,
    "whisper_beam_size":    5,
    "whisper_preload":      True,
    "ollama_host":          "http://localhost:11434",
    "ollama_model":         "gemma3:4b",
    "ollama_no_think":      True,
    "ollama_think_mode":    "",       # "never", "auto" (decide la IA) o "always"; vacío = según la anterior
    "ollama_keep_alive":    "30m",
    "ollama_num_ctx":       0,
    "ollama_preload":       True,
    "conversation_memory":  True,
    "max_history_turns":    10,       # mensajes anteriores que se le envían (cada uno con su respuesta)
    "history_max_hours":    0,        # olvidar los de hace más de N horas (0 = no)
    # Fecha y hora en cada mensaje
    "datetime_in_messages": True,
    # CMD / web / navegador
    "cmd_enabled":          True,
    "web_enabled":          True,
    "browser_enabled":      False,
    # Visión (captura de pantalla y cámara)
    "vision_enabled":       True,
    "vision_model":         "",
    "vision_hide_windows":  True,
    "vision_max_side":      1600,
    "camera_index":         0,
    "captures_keep":        30,
    # Control del PC (ratón y teclado)
    "pc_control_enabled":     False,
    "pc_use_elements":        True,
    "pc_use_grid":            True,
    "pc_verify":              True,
    "pc_confirm_dangerous":   True,
    "pc_stop_hotkey_enabled": True,
    "pc_stop_hotkey":         "esc",
    "pc_stop_corner":         True,
    "pc_stop_on_user_mouse":  False,
    "pc_block_fullscreen":    True,
    "pc_show_banner":         True,
    "pc_max_steps":           25,
    "pc_action_delay":        0.6,
    "pc_image_width":         1280,
    "pc_max_elements":        160,
    # Memoria persistente
    "memory_enabled":       True,
    # Recordatorios
    "reminders_enabled":       True,
    # Tareas que la IA se programa a sí misma
    "ai_tasks_enabled":        True,
    "ai_tasks_whatsapp":       False,    # mandarte por WhatsApp lo que ha hecho
    "ai_tasks_confirm":        False,    # pedir confirmación antes de enviar WhatsApps
    "reminder_sound":          True,
    "reminder_sound_file":     "",
    "reminder_sound_repeats":  3,
    "reminder_tts":            True,
    "reminder_whatsapp":       False,
    "reminder_snooze_minutes": 10,
    # Orbe
    "orb_size":             54,
    "orb_opacity":          0.88,
    "orb_opacity_min":      0.45,
    "orb_x":                -1,
    "orb_y":                -1,
    "orb_visible":          True,
    "orb_idle_visible":     False,
    "orb_show_loading":     True,
    "orb_color_idle":       "#2979ff",
    "orb_color_listening":  "#2979ff",
    "orb_color_thinking":   "#ff9800",
    "orb_color_speaking":   "#9c27b0",
    "orb_color_continuous": "#00c853",
    "orb_color_loading":    "#607d8b",
    # Popup
    "popup_bg":             "#0d1117",
    "popup_opacity":        0.94,
    "popup_text_color":     "#e2e8f0",
    "popup_accent":         "#4f8ef7",
    "popup_width":          480,
    "popup_height":         340,
    "popup_position":       "bottom-right",
    "popup_custom_x":       100,
    "popup_custom_y":       100,
    "popup_auto_close":     30,
    "show_transcript":      True,
    "system_prompt":        "Eres un asistente de voz útil, conciso y amable. Responde siempre en el mismo idioma que el usuario.",
    "log_enabled":          False,
    "log_file_path":        "",
    "log_load_as_memory":   False,
    "log_max_entries":      0,        # conversaciones que se guardan en el log (0 = todas)
    "tts_enabled":          False,
    "tts_engine":           "pyttsx3",
    "tts_rate":             180,
    "tts_volume":           1.0,
    "tts_voice_id":         "",
    "text_input_tts":       True,
    "continuous_conv":              True,
    "continuous_timeout":           8.0,
    "continuous_stop_word":         "para",
    # Cerrar popup automáticamente tras TTS
    "popup_close_on_tts_end":       False,
    "popup_close_on_tts_end_delay": 2,
    # WhatsApp
    "whatsapp_enabled":             False,
    "whatsapp_bridge_port":         3847,
    "whatsapp_bridge_autostart":    True,
    "whatsapp_notify_self":         True,
    "whatsapp_self_reply":          True,     # contestar a lo que te escribes en tu chat propio
    "whatsapp_self_trigger":        False,    # …solo si le llamas por una de estas palabras
    "whatsapp_self_trigger_words":  "asistente, rubencho",
    "whatsapp_self_popup":          False,    # mostrar en el PC el panel con lo que contesta ahí
    "whatsapp_read_enabled":        True,     # leer chats cuando el usuario lo pide
    "whatsapp_read_max":            20,       # máximo de mensajes hacia atrás
    "whatsapp_read_images":         True,     # ver las fotos recibidas
    "whatsapp_read_audio":          True,     # transcribir los audios con Whisper
    "whatsapp_confirm_send":        True,     # pedir confirmación antes de enviar
    "whatsapp_send_all":            False,    # escribir a todos o solo a los permitidos
    "whatsapp_allowed_contacts":    [],       # contactos a los que puede escribir
    # PTT – Push to Talk
    "ptt_enabled":                  False,
    "ptt_hotkey":                   "f9",
    "ptt_no_continuous":            True,
}


def load_config() -> dict:
    APP_DIR.mkdir(parents=True, exist_ok=True)
    cfg = DEFAULT_CONFIG.copy()
    data = _read_json(CONFIG_FILE, {})        # si está dañado se guarda una copia
    if isinstance(data, dict):
        cfg.update(data)
    return cfg


def save_config(cfg: dict):
    try:
        _atomic_write_json(CONFIG_FILE, cfg)
    except Exception as e:
        print(f"[Config] No se pudo guardar: {e}")


def lerp_color(c1: str, c2: str, t: float) -> str:
    def h(c): return int(c[1:3],16), int(c[3:5],16), int(c[5:7],16)
    r1,g1,b1 = h(c1); r2,g2,b2 = h(c2)
    return f"#{int(r1+(r2-r1)*t):02x}{int(g1+(g2-g1)*t):02x}{int(b1+(b2-b1)*t):02x}"


# ── Orb Window ────────────────────────────────────────────────────────────────
class OrbWindow(tk.Toplevel):
    """
    Orbe flotante que indica el estado del asistente:
      loading     gris azulado, arco girando    → cargando modelos al iniciar
      idle        azul, quieto                  → en reposo (oculto salvo «visible en reposo»)
      listening   azul, latido + onda           → grabando tu orden
      thinking    naranja, pulso + puntos       → la IA piensa o ejecuta herramientas
      speaking    morado, vibración de voz      → la IA está hablando (TTS)
      continuous  verde, respiración lenta      → esperando tu siguiente frase
    Color, tamaño y opacidad se interpolan en cada fotograma, así que los cambios
    de modo son suaves. La ventana no se oculta/muestra (withdraw/deiconify) en
    cada cambio: se desvanece con la opacidad, lo que evita parpadeos y robos de foco.
    """
    STATES = ("loading", "idle", "listening", "thinking", "speaking", "continuous")
    DEFAULT_COLORS = {
        "loading":    "#607d8b",
        "idle":       "#2979ff",
        "listening":  "#2979ff",
        "thinking":   "#ff9800",
        "speaking":   "#9c27b0",
        "continuous": "#00c853",
    }
    FRAME_MS = 33

    def __init__(self, root, config: dict, on_open_settings, on_listen_now,
                 on_stop_listening=None, on_write=None, is_speaking=None):
        super().__init__(root)
        self._cfg         = config
        self._on_settings = on_open_settings
        self._on_listen   = on_listen_now
        self._on_stop     = on_stop_listening
        self._on_write    = on_write
        self._is_speaking = is_speaking
        self._state       = "idle"
        self._alive       = True
        self._shown       = False       # ¿se está dibujando?
        self._suspended   = False       # oculto temporalmente (capturas de pantalla)
        self._dragging    = False
        self._peek_until  = 0.0
        self._preview     = []          # [(estado, hasta)] para «Probar colores»
        self._preview_colors = {}
        self._alpha       = 0.0
        self._applied_alpha = -1.0
        self._t0 = self._last_t = time.time()
        self._drag_offset = (0, 0)
        self._rgb         = self._hex_to_rgb(self._color_for("idle"))
        self._radius      = None
        self._after_id    = None
        self._sz          = 54

        self.overrideredirect(True)
        self.wm_attributes("-topmost", True)
        self.configure(bg="black")
        try:    self.wm_attributes("-transparentcolor", "black")
        except Exception: pass
        self._set_alpha(0.0)

        self._cv = tk.Canvas(self, bg="black", highlightthickness=0, bd=0)
        self._cv.pack()
        self.apply_config()

        self._cv.bind("<ButtonPress-1>",   self._drag_start)
        self._cv.bind("<B1-Motion>",       self._drag_move)
        self._cv.bind("<ButtonRelease-1>", self._drag_end)
        self._cv.bind("<Double-Button-1>", lambda _e: self._on_write and self._on_write())
        self._cv.bind("<Button-3>",        self._show_menu)

        self._after_id = self.after(self.FRAME_MS, self._animate)

    # ── Configuración y posición ──────────────────────────────────────────
    def apply_config(self):
        """Aplica tamaño, posición y opacidad (también tras guardar la configuración)."""
        try:
            self._sz = max(24, int(float(self._cfg.get("orb_size", 54))))
        except (TypeError, ValueError):
            self._sz = 54
        self._cv.config(width=self._sz, height=self._sz)
        self._radius = None
        self._applied_alpha = -1.0
        self._position_orb()

    def _virtual_screen(self):
        """(x, y, ancho, alto) del escritorio virtual (todos los monitores)."""
        if IS_WINDOWS:
            try:
                import ctypes
                gm = ctypes.windll.user32.GetSystemMetrics
                w, h = gm(78), gm(79)
                if w > 0 and h > 0:
                    return gm(76), gm(77), w, h
            except Exception:
                pass
        return 0, 0, self.winfo_screenwidth(), self.winfo_screenheight()

    def _position_orb(self):
        sz = self._sz
        try:
            ox = int(float(self._cfg.get("orb_x", -1)))
            oy = int(float(self._cfg.get("orb_y", -1)))
        except (TypeError, ValueError):
            ox = oy = -1
        if ox == -1 and oy == -1:
            ox = self.winfo_screenwidth() - sz - 28
            oy = self.winfo_screenheight() - sz - 64
        else:
            # Las coordenadas negativas son válidas con varios monitores; solo se
            # corrige si el orbe quedaría fuera de todas las pantallas.
            vx, vy, vw, vh = self._virtual_screen()
            ox = max(vx, min(ox, vx + vw - sz))
            oy = max(vy, min(oy, vy + vh - sz))
        self.geometry(f"{sz}x{sz}+{ox}+{oy}")

    # ── Colores ───────────────────────────────────────────────────────────
    def _color_for(self, state: str) -> str:
        val = ""
        if self._preview:
            val = str(self._preview_colors.get(state, "") or "")
        if not val:
            val = str(self._cfg.get(f"orb_color_{state}", "") or "")
        return val if re.fullmatch(r"#[0-9a-fA-F]{6}", val) else self.DEFAULT_COLORS[state]

    @staticmethod
    def _hex_to_rgb(h: str):
        try:
            return (int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16))
        except Exception:
            return (41, 121, 255)

    @staticmethod
    def _rgb_to_hex(rgb) -> str:
        r, g, b = (max(0, min(255, int(round(v)))) for v in rgb)
        if (r, g, b) == (0, 0, 0):          # el negro puro es el color transparente
            r = g = b = 1
        return f"#{r:02x}{g:02x}{b:02x}"

    @staticmethod
    def _mix(rgb, other, t: float):
        return tuple(a + (b - a) * t for a, b in zip(rgb, other))

    # ── Estado ────────────────────────────────────────────────────────────
    def set_state(self, state: str):
        if state in self.STATES:
            self._state = state

    @property
    def state(self) -> str:
        return self._state

    def _effective_state(self, now: float) -> str:
        while self._preview and now >= self._preview[0][1]:
            self._preview.pop(0)
        if self._preview:
            return self._preview[0][0]
        st = self._state
        if st in ("idle", "thinking", "continuous") and self._is_speaking:
            try:
                if self._is_speaking():
                    return "speaking"
            except Exception:
                pass
        return st

    def _want_visible(self, eff: str, now: float) -> bool:
        if self._suspended:
            return False
        if self._dragging or self._preview or now < self._peek_until:
            return True
        if not self._cfg.get("orb_visible", True):
            return False
        if eff == "loading":
            return bool(self._cfg.get("orb_show_loading", True))
        if eff == "idle":
            return bool(self._cfg.get("orb_idle_visible", False))
        return True

    # ── Animación ─────────────────────────────────────────────────────────
    def _raise_noactivate(self):
        """Pone el orbe encima de todo SIN activarlo (no roba el foco del teclado)."""
        if not IS_WINDOWS:
            return
        try:
            import ctypes
            user32 = ctypes.windll.user32
            user32.SetWindowPos.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int,
                                            ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_uint]
            hwnd = int(self.wm_frame(), 16)
            # HWND_TOPMOST = -1 · SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE
            user32.SetWindowPos(hwnd, ctypes.c_void_p(-1), 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0010)
        except Exception:
            pass

    def _set_alpha(self, a: float):
        if abs(a - self._applied_alpha) < 0.004:
            return
        try:
            self.wm_attributes("-alpha", max(0.0, min(1.0, a)))
            self._applied_alpha = a
        except Exception:
            pass

    def _animate(self):
        if not self._alive:
            return
        now = time.time()
        dt  = max(0.0, min(0.1, now - self._last_t))
        self._last_t = now
        try:
            eff     = self._effective_state(now)
            visible = self._want_visible(eff, now)
            try:
                hi = float(self._cfg.get("orb_opacity", 0.88))
                lo = float(self._cfg.get("orb_opacity_min", 0.45))
            except (TypeError, ValueError):
                hi, lo = 0.88, 0.45
            if not visible:
                target = 0.0
            elif eff == "idle" and not (self._preview or self._dragging or now < self._peek_until):
                target = lo
            else:
                target = hi

            if visible and not self._shown:
                self._shown = True
                self._raise_noactivate()
            self._alpha += (target - self._alpha) * (1.0 - math.exp(-dt * 11.0))
            if abs(target - self._alpha) < 0.01:
                self._alpha = target

            if self._shown:
                if not visible and self._alpha <= 0.02:
                    self._shown = False
                    self._cv.delete("all")       # todo transparente y sin capturar clics
                    self._set_alpha(0.0)
                else:
                    self._set_alpha(self._alpha)
                    self._draw(eff, now, dt)
        except Exception as e:
            print(f"[Orbe] {e}")
        self._after_id = self.after(self.FRAME_MS if self._shown else 120, self._animate)

    def _draw(self, eff: str, now: float, dt: float):
        c  = self._cv
        c.delete("all")
        sz = self._sz
        cx = cy = sz / 2.0
        R  = sz / 2.0 - 3
        t  = now - self._t0
        tau = 2 * math.pi

        target_rgb = self._hex_to_rgb(self._color_for(eff))
        k = 1.0 - math.exp(-dt * 9.0)
        self._rgb = self._mix(self._rgb, target_rgb, k)
        col   = self._rgb_to_hex(self._rgb)
        light = self._rgb_to_hex(self._mix(self._rgb, (255, 255, 255), 0.38))
        dark  = self._rgb_to_hex(self._mix(self._rgb, (0, 0, 0), 0.30))

        if eff == "listening":
            f = 0.80 + 0.07 * math.sin(t * tau * 1.4)
        elif eff == "thinking":
            f = 0.72 + 0.07 * math.sin(t * tau * 1.8)
        elif eff == "speaking":
            f = 0.80 + 0.07 * math.sin(t * tau * 2.3) + 0.05 * math.sin(t * tau * 5.3 + 1.3)
        elif eff == "continuous":
            f = 0.82 + 0.06 * math.sin(t * tau * 0.7)
        elif eff == "loading":
            f = 0.60
        else:
            f = 0.86
        target_r = R * f
        if self._radius is None:
            self._radius = target_r
        self._radius += (target_r - self._radius) * (1.0 - math.exp(-dt * 16.0))
        r = self._radius

        if eff == "listening":                       # onda que se expande
            ph = (t * 0.9) % 1.0
            rr = r + (R - r) * ph + 1
            c.create_oval(cx - rr, cy - rr, cx + rr, cy + rr,
                          outline=light, width=max(1, int(round(3 * (1 - ph)))))
        elif eff == "continuous":                    # anillo fijo
            c.create_oval(cx - R + 1, cy - R + 1, cx + R - 1, cy + R - 1, outline=col, width=2)
        elif eff == "loading":                       # arco girando
            c.create_arc(cx - R + 2, cy - R + 2, cx + R - 2, cy + R - 2,
                         start=(t * 320) % 360, extent=110, style="arc", outline=light, width=3)
        elif eff == "speaking":                      # anillo que vibra con la voz
            rr = min(R, r + 3 + 2 * abs(math.sin(t * tau * 3.1)))
            c.create_oval(cx - rr, cy - rr, cx + rr, cy + rr, outline=light, width=1)

        c.create_oval(cx - r, cy - r, cx + r, cy + r, fill=col, outline=dark, width=1)
        hr, hx, hy = r * 0.40, cx - r * 0.28, cy - r * 0.30
        c.create_oval(hx - hr, hy - hr * 0.8, hx + hr, hy + hr * 0.8, fill=light, outline="")

        if eff == "thinking":                        # tres puntos orbitando
            dot = max(1.5, sz * 0.045)
            dist = R - dot - 0.5
            for i in range(3):
                a = t * 3.6 + i * tau / 3
                px, py = cx + math.cos(a) * dist, cy + math.sin(a) * dist
                c.create_oval(px - dot, py - dot, px + dot, py + dot, fill=light, outline="")

    # ── Visibilidad ───────────────────────────────────────────────────────
    def peek(self, seconds: float = 2.5):
        """Muestra el orbe unos segundos aunque esté en reposo."""
        self._peek_until = time.time() + seconds

    def suspend(self, on: bool):
        """Oculta el orbe al instante (p.ej. para que no salga en una captura)."""
        self._suspended = bool(on)
        if on:
            self._shown = False
            self._alpha = 0.0
            try:
                self._cv.delete("all")
                self._set_alpha(0.0)
                self.update_idletasks()
            except Exception:
                pass

    def preview_states(self, colors: dict = None):
        """Recorre todos los modos para ver los colores (botón de Configuración)."""
        self._preview_colors = dict(colors or {})
        now = time.time()
        seq, t = [], now
        for st in ("listening", "thinking", "speaking", "continuous", "loading", "idle"):
            t += 1.8
            seq.append((st, t))
        self._preview = seq

    def hide_orb(self):
        self._cfg["orb_visible"] = False
        save_config(self._cfg)

    def show_orb(self):
        self._cfg["orb_visible"] = True
        save_config(self._cfg)
        self.peek(3.0)

    # ── Ratón ─────────────────────────────────────────────────────────────
    def _drag_start(self, e):
        self._dragging = True
        self._drag_offset = (e.x_root - self.winfo_x(), e.y_root - self.winfo_y())

    def _drag_move(self, e):
        ox, oy = self._drag_offset
        nx, ny = e.x_root - ox, e.y_root - oy
        self.geometry(f"+{nx}+{ny}")
        self._cfg["orb_x"] = nx
        self._cfg["orb_y"] = ny

    def _drag_end(self, _e):
        self._dragging = False
        self.peek(1.0)
        save_config(self._cfg)

    def _show_menu(self, e):
        m = tk.Menu(self, tearoff=0,
                    bg="#1a1a2e", fg="#c8e6ff",
                    activebackground="#0f3460", activeforeground="white",
                    font=("Segoe UI", 10), relief='flat', bd=0)
        if self._on_write:
            m.add_command(label="✍️  Escribir mensaje", command=self._on_write)
        m.add_command(label="🎙  Escuchar ahora",  command=self._on_listen)
        if self._on_stop:
            m.add_command(label="🛑  Terminar",    command=self._on_stop)
        m.add_separator()
        m.add_command(label="👁  Ocultar orbe",    command=self.hide_orb)
        m.add_command(label="⚙️  Configuración",   command=self._on_settings)
        m.add_separator()
        m.add_command(label="✕  Salir",
                      command=lambda: self.event_generate("<<Quit>>"))
        try:   m.tk_popup(e.x_root, e.y_root)
        finally: m.grab_release()

    def safe_close(self):
        self._alive = False
        try:
            if self._after_id:
                self.after_cancel(self._after_id)
        except Exception:
            pass
        try: self.destroy()
        except Exception: pass


# ── Response Popup ────────────────────────────────────────────────────────────
class ResponsePopup(tk.Toplevel):
    RADIUS = 16

    def __init__(self, root, config: dict, transcript: str, response: str,
                 streaming: bool = False, on_send=None, on_mute=None):
        super().__init__(root)
        cfg            = config
        self._cfg      = cfg
        # El negro puro es el color transparente de la ventana: se evita
        self._bg       = self._safe_color(cfg.get("popup_bg",        "#0d1117"), "#0d1117")
        self._text     = self._safe_color(cfg.get("popup_text_color", "#e2e8f0"), "#e2e8f0")
        self._accent   = self._safe_color(cfg.get("popup_accent",     "#4f8ef7"), "#4f8ef7")
        w              = int(cfg.get("popup_width",  480))
        h              = int(cfg.get("popup_height", 340))
        opacity        = float(cfg.get("popup_opacity", 0.94))
        self._auto     = int(float(cfg.get("popup_auto_close", 30)))
        self._paused   = False
        # Sin cierre automático si el contador es ≤ 0 o si se cierra al acabar
        # de hablar (solo cuando el TTS está realmente activo).
        tts_close = (bool(cfg.get("popup_close_on_tts_end", False))
                     and bool(cfg.get("tts_enabled", False)) and not _TTS_MUTED)
        self._no_autoclose = self._auto <= 0 or tts_close
        self._cd       = max(1, self._auto)
        self._streaming= streaming
        self._rtxt     = None
        self._md_colors= {}
        self._full_buf = ""
        self._images   = []           # [(PhotoImage, ruta)] miniaturas de capturas
        self._on_send  = on_send
        self._on_mute  = on_mute
        self._muted    = _TTS_MUTED   # estado inicial del icono
        self._full_response = response  # para copiar

        self.overrideredirect(True)
        self.wm_attributes("-topmost", bool(cfg.get("always_on_top_popup", True)))
        self.configure(bg="black")
        try:    self.wm_attributes("-transparentcolor", "black")
        except Exception: pass
        try:    self.wm_attributes("-alpha", opacity)
        except Exception: pass

        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        pos    = cfg.get("popup_position", "bottom-right")
        pad    = 24
        if   pos == "center":       x, y = (sw-w)//2,    (sh-h)//2
        elif pos == "top-right":    x, y = sw-w-pad,      pad
        elif pos == "top-left":     x, y = pad,           pad
        elif pos == "bottom-right": x, y = sw-w-pad,      sh-h-72
        elif pos == "bottom-left":  x, y = pad,           sh-h-72
        else:
            x = int(cfg.get("popup_custom_x", 100))
            y = int(cfg.get("popup_custom_y", 100))
        self.geometry(f"{w}x{h}+{x}+{y}")
        self._pw, self._ph = w, h
        self._drag         = (0, 0)

        self._canvas = tk.Canvas(self, width=w, height=h,
                                  bg="black", highlightthickness=0)
        self._canvas.pack()

        self._draw_rounded_bg()
        self._build_content(transcript, response)

        self.bind("<Enter>", lambda _: setattr(self, "_paused", True))
        self.bind("<Leave>", lambda _: setattr(self, "_paused", False))
        self._canvas.bind("<ButtonPress-1>", self._ds)
        self._canvas.bind("<B1-Motion>",     self._dm)

        self._tick()

    @staticmethod
    def _safe_color(value, default: str) -> str:
        v = str(value or "").strip()
        if not re.fullmatch(r"#[0-9a-fA-F]{6}", v):
            return default
        return "#010101" if v.lower() == "#000000" else v

    def _draw_rounded_bg(self):
        c  = self._canvas
        w, h, r = self._pw, self._ph, self.RADIUS
        bg = self._bg

        c.create_arc(  0,     0,   r*2,   r*2, start=90,  extent=90, fill=bg, outline=bg)
        c.create_arc(w-r*2,   0,   w,     r*2, start=0,   extent=90, fill=bg, outline=bg)
        c.create_arc(  0,   h-r*2, r*2,   h,   start=180, extent=90, fill=bg, outline=bg)
        c.create_arc(w-r*2, h-r*2, w,     h,   start=270, extent=90, fill=bg, outline=bg)
        c.create_rectangle(r,   0,  w-r,  h,   fill=bg, outline=bg)
        c.create_rectangle(0,   r,  w,  h-r,   fill=bg, outline=bg)

        # Borde superior de acento de 3 px que sigue la curva de las esquinas
        accent = self._accent
        c.create_arc(1.5, 1.5, r*2, r*2, start=90, extent=90,
                     style="arc", outline=accent, width=3)
        c.create_arc(w-r*2, 1.5, w-1.5, r*2, start=0, extent=90,
                     style="arc", outline=accent, width=3)
        c.create_rectangle(r, 0, w-r, 3, fill=accent, outline=accent)

    def _build_content(self, transcript: str, response: str):
        c    = self._canvas
        w    = int(self._pw)
        h    = int(self._ph)
        bg   = self._bg
        acc  = self._accent
        txt  = self._text
        sub  = lerp_color(self._bg, self._text, 0.4)
        panel= lerp_color(bg, "#ffffff", 0.06)   # fondo del input
        PAD  = 18

        # ── Botón cerrar ──────────────────────────────────────────────────────
        close = tk.Label(c, text="×", bg=bg, fg=sub,
                          font=("Segoe UI", 14), cursor="hand2")
        close.place(x=w - PAD - 8, y=6)
        close.bind("<Button-1>", lambda _: self.destroy())
        close.bind("<Enter>",    lambda _: close.config(fg=txt))
        close.bind("<Leave>",    lambda _: close.config(fg=sub))

        # ── Botón silenciar ───────────────────────────────────────────────────
        mute_icon  = "🔇" if self._muted else "🔊"
        mute_color = "#ff5566" if self._muted else sub
        self._mute_lbl = tk.Label(c, text=mute_icon, bg=bg, fg=mute_color,
                                   font=("Segoe UI", 11), cursor="hand2")
        self._mute_lbl.place(x=w - PAD - 34, y=6)

        def toggle_mute(_e=None):
            if self._on_mute:
                self._muted = self._on_mute()
            else:
                global _TTS_MUTED
                _TTS_MUTED = not _TTS_MUTED
                self._muted = _TTS_MUTED
            icon  = "🔇" if self._muted else "🔊"
            color = "#ff5566" if self._muted else sub
            try: self._mute_lbl.config(text=icon, fg=color)
            except Exception: pass

        self._mute_lbl.bind("<Button-1>", toggle_mute)

        y = int(PAD) + 2

        # ── Badge ─────────────────────────────────────────────────────────────
        badge = tk.Label(c, text=" 🐢  Rubencho AI ", bg=acc, fg="white",
                          font=("Segoe UI", 8, "bold"), padx=6, pady=2)
        badge.place(x=PAD, y=y)
        y += 26

        # ── Transcripción ─────────────────────────────────────────────────────
        if transcript and self._cfg.get("show_transcript", True):
            wrap = w - PAD * 2 - 20
            max_chars = max(40, int(wrap / 6.2) * 2)          # ~2 líneas como máximo
            shown = transcript if len(transcript) <= max_chars else transcript[:max_chars - 1] + "…"
            tl = tk.Label(c, text=f"\u201c{shown}\u201d",
                           bg=bg, fg=sub,
                           font=("Segoe UI", 9, "italic"),
                           wraplength=wrap,
                           justify='left', anchor='w')
            tl.place(x=PAD, y=y, width=wrap)
            tl.update_idletasks()
            y += max(20, tl.winfo_reqheight()) + 6

        sep_color = lerp_color(bg, acc, 0.2)
        tk.Frame(c, bg=sep_color, height=1).place(x=PAD, y=y, width=w - PAD * 2)
        y += 10

        # ── Área de respuesta ─────────────────────────────────────────────────
        # Reservamos espacio: 24px (footer) + 36px (input) + 4px (gap) = 64px
        FOOTER_H = 64
        avail_h  = max(60, int(h) - int(y) - FOOTER_H)

        vsb = tk.Scrollbar(c, orient='vertical',
                           bg=lerp_color(bg, "#ffffff", 0.07),
                           troughcolor=bg, relief='flat', bd=0, width=5)
        rtxt = tk.Text(c, bg=bg, fg=txt,
                        font=("Segoe UI", 10), wrap='word',
                        relief='flat', bd=0, padx=0, pady=2,
                        yscrollcommand=vsb.set,
                        cursor="arrow",
                        selectbackground=lerp_color(bg, acc, 0.35),
                        highlightthickness=0)
        vsb.config(command=rtxt.yview)
        vsb.place(x=w - PAD - 3, y=y, height=avail_h)
        rtxt.place(x=PAD, y=y, width=w - PAD * 2 - 10, height=avail_h)

        md_colors = {
            "bg":      bg,
            "fg":      txt,
            "accent":  acc,
            "code_bg": lerp_color(bg, "#2979ff", 0.12),
            "muted":   lerp_color(bg, txt, 0.35),
        }
        self._rtxt     = rtxt
        self._md_colors= md_colors

        if self._streaming:
            rtxt.config(state="normal")
        else:
            render_markdown(rtxt, str(response), md_colors)

        # ── Footer: contador + copiar ─────────────────────────────────────────
        footer_y = h - FOOTER_H

        self._cd_lbl = tk.Label(c, text=self._countdown_text(),
                                 bg=bg, fg=sub, font=("Segoe UI", 8))
        self._cd_lbl.place(x=PAD, y=footer_y + 4)

        full_resp_ref = [response]   # lista mutable para captura en closure

        def copy_it(_e=None):
            try:
                self.clipboard_clear()
                self.clipboard_append(self._full_response or full_resp_ref[0])
                cb.config(text="✓")
                self.after(1500, lambda: cb.config(text="⎘"))
            except Exception: pass

        cb = tk.Label(c, text="⎘", bg=bg, fg=sub,
                       font=("Segoe UI", 10), cursor="hand2")
        cb.place(x=w - PAD - 16, y=footer_y + 2)
        cb.bind("<Button-1>", copy_it)
        cb.bind("<Enter>",    lambda _: cb.config(fg=acc))
        cb.bind("<Leave>",    lambda _: cb.config(fg=sub))

        # ── Input de texto ────────────────────────────────────────────────────
        input_y = footer_y + 26
        input_h = 28
        btn_w   = 32

        input_bg = lerp_color(bg, "#ffffff", 0.09)
        input_frame = tk.Frame(c, bg=input_bg,
                                highlightbackground=lerp_color(bg, acc, 0.3),
                                highlightthickness=1, bd=0)
        input_frame.place(x=PAD, y=input_y,
                          width=w - PAD * 2 - btn_w - 4, height=input_h)

        entry_var = tk.StringVar()
        entry = tk.Entry(input_frame, textvariable=entry_var,
                         bg=input_bg, fg=txt,
                         font=("Segoe UI", 9), relief='flat', bd=4,
                         insertbackground=acc,
                         highlightthickness=0)
        entry.pack(fill='both', expand=True)
        entry.insert(0, "Escribe un mensaje…")
        entry.config(fg=sub)

        def _on_focus_in(_e):
            if entry_var.get() == "Escribe un mensaje…":
                entry.delete(0, 'end')
                entry.config(fg=txt)
        def _on_focus_out(_e):
            if not entry_var.get():
                entry.insert(0, "Escribe un mensaje…")
                entry.config(fg=sub)

        entry.bind("<FocusIn>",  _on_focus_in)
        entry.bind("<FocusOut>", _on_focus_out)

        def _send(_e=None):
            text = entry_var.get().strip()
            if not text or text == "Escribe un mensaje…":
                return
            entry.delete(0, 'end')
            entry.config(fg=sub)
            entry.insert(0, "Escribe un mensaje…")
            if self._on_send:
                self._on_send(text)

        entry.bind("<Return>", _send)
        # Evitar que el clic en entry pause el contador accidentalmente
        entry.bind("<Button-1>", lambda e: (entry.focus_set(), "break"))

        send_btn = tk.Label(c, text="➤", bg=acc, fg="white",
                             font=("Segoe UI", 11, "bold"), cursor="hand2",
                             width=2)
        send_btn.place(x=w - PAD - btn_w + 2, y=input_y, height=input_h)
        send_btn.bind("<Button-1>", _send)
        send_btn.bind("<Enter>",    lambda _: send_btn.config(bg=lerp_color(acc,"#ffffff",0.15)))
        send_btn.bind("<Leave>",    lambda _: send_btn.config(bg=acc))

        # Pausar el countdown cuando el usuario escribe en el entry
        entry.bind("<FocusIn>",  lambda e: (setattr(self, "_paused", True),  _on_focus_in(e)))
        entry.bind("<FocusOut>", lambda e: (setattr(self, "_paused", False), _on_focus_out(e)))

    def append_chunk(self, chunk: str):
        if self._rtxt is None:
            return
        try:
            self._full_buf += chunk
            self._full_response = self._full_buf
            self._rtxt.config(state="normal")
            self._rtxt.insert("end", chunk, "normal")
            self._rtxt.see("end")
        except Exception:
            pass

    def finalize(self, full_response: str):
        if self._rtxt is None:
            return
        try:
            self._full_response = full_response
            render_markdown(self._rtxt, full_response, self._md_colors, images=self._images)
            self._rtxt.see("1.0")
        except Exception as e:
            print(f"[Popup] {e}")
        # El contador empieza a contar cuando la respuesta está completa
        self._streaming = False
        self._cd = max(1, self._auto)
        try:   self._cd_lbl.config(text=self._countdown_text())
        except Exception: pass

    def add_image(self, pil_img, path):
        """Añade la miniatura de una captura (pil_img ya reducida) al popup."""
        if self._rtxt is None:
            return
        try:
            from PIL import ImageTk
            photo = ImageTk.PhotoImage(pil_img, master=self)
        except Exception as e:
            print(f"[Popup] Miniatura: {e}")
            return
        self._images.append((photo, path))
        try:
            self._rtxt.config(state="normal")
            _insert_image(self._rtxt, photo, path, len(self._images))
            self._rtxt.see("end")
            if not self._streaming:
                self._rtxt.config(state="disabled")
        except Exception:
            pass

    def _countdown_text(self) -> str:
        if self._no_autoclose:
            return ""
        return "…" if self._streaming else f"{self._cd}s"

    def _ds(self, e):
        self._drag = (e.x_root - self.winfo_x(), e.y_root - self.winfo_y())

    def _dm(self, e):
        ox, oy = self._drag
        self.geometry(f"+{e.x_root-ox}+{e.y_root-oy}")

    def _tick(self):
        # Mientras se genera la respuesta, con el ratón encima o escribiendo,
        # el contador se detiene; con «sin cierre automático» no corre nunca.
        if not (self._paused or self._streaming or self._no_autoclose):
            self._cd -= 1
            if self._cd <= 0:
                try:   self.destroy()
                except Exception: pass
                return
        try:   self._cd_lbl.config(text=self._countdown_text())
        except Exception: pass
        try:   self.after(1000, self._tick)
        except Exception: pass


def _force_foreground(win):
    """Intenta traer una ventana al frente con el foco del teclado (Windows)."""
    try:
        win.deiconify()
        win.lift()
        win.focus_force()
    except Exception:
        pass
    if IS_WINDOWS:
        try:
            import ctypes
            hwnd = int(win.wm_frame(), 16)
            ctypes.windll.user32.SetForegroundWindow(hwnd)
        except Exception:
            pass


# ── Ventana «Escribir mensaje» ───────────────────────────────────────────────
class QuickInputWindow(tk.Toplevel):
    """Cuadro flotante para escribir un mensaje a la IA (bandeja / orbe)."""
    PLACEHOLDER = "Escribe tu mensaje…"

    def __init__(self, root, config: dict, on_send, on_close=None):
        super().__init__(root)
        self._on_send  = on_send
        self._on_close = on_close
        self._closed   = False
        bg   = ResponsePopup._safe_color(config.get("popup_bg", "#0d1117"), "#0d1117")
        txt  = ResponsePopup._safe_color(config.get("popup_text_color", "#e2e8f0"), "#e2e8f0")
        acc  = ResponsePopup._safe_color(config.get("popup_accent", "#4f8ef7"), "#4f8ef7")
        if acc.lower() == bg.lower():               # acento invisible → uno visible
            acc = "#4f8ef7"
        self._txt_color = txt
        self._sub = sub = lerp_color(bg, txt, 0.45)
        panel = lerp_color(bg, "#ffffff", 0.08)

        self.title("Escribir a Rubencho AI")
        self.overrideredirect(True)
        self.wm_attributes("-topmost", True)
        self.configure(bg=acc)                       # 1 px de borde con el color de acento

        w, h = 540, 168
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry(f"{w}x{h}+{(sw - w) // 2}+{int(sh * 0.30)}")

        body = tk.Frame(self, bg=bg)
        body.pack(fill="both", expand=True, padx=1, pady=1)

        top = tk.Frame(body, bg=bg)
        top.pack(fill="x", padx=14, pady=(10, 4))
        title = tk.Label(top, text="✍️  Escribe a Rubencho AI", bg=bg, fg=acc if acc != bg else txt,
                         font=("Segoe UI", 10, "bold"))
        title.pack(side="left")
        close = tk.Label(top, text="×", bg=bg, fg=sub, font=("Segoe UI", 14), cursor="hand2")
        close.pack(side="right")
        close.bind("<Button-1>", lambda _e: self.close())
        for wdg in (top, title):                     # arrastrar desde la cabecera
            wdg.bind("<ButtonPress-1>", self._ds)
            wdg.bind("<B1-Motion>", self._dm)

        row = tk.Frame(body, bg=bg)
        row.pack(fill="both", expand=True, padx=14)
        box = tk.Frame(row, bg=panel, highlightthickness=1,
                       highlightbackground=lerp_color(bg, acc, 0.5), highlightcolor=acc)
        box.pack(side="left", fill="both", expand=True)
        self._text = tk.Text(box, height=3, wrap="word", bg=panel, fg=sub,
                             insertbackground=acc, relief="flat", bd=6,
                             font=("Segoe UI", 11), highlightthickness=0, undo=True)
        self._text.pack(fill="both", expand=True)
        self._text.insert("1.0", self.PLACEHOLDER)
        self._placeholder = True
        send = tk.Label(row, text="➤", bg=acc, fg="white", font=("Segoe UI", 14, "bold"),
                        cursor="hand2", width=3)
        send.pack(side="left", fill="y", padx=(6, 0))
        send.bind("<Button-1>", lambda _e: self._send())

        tk.Label(body, text="Enter: enviar   ·   Shift+Enter: nueva línea   ·   Esc: cerrar",
                 bg=bg, fg=sub, font=("Segoe UI", 8)).pack(anchor="w", padx=14, pady=(4, 8))

        self._text.bind("<Return>", self._on_return)
        self._text.bind("<KP_Enter>", self._on_return)
        self._text.bind("<Escape>", lambda _e: self.close())
        self._text.bind("<FocusIn>", self._clear_placeholder)
        self._text.bind("<Key>", self._clear_placeholder, add="+")
        self.bind("<Escape>", lambda _e: self.close())
        self._drag = (0, 0)
        self.after(60, self.focus_input)

    def focus_input(self):
        _force_foreground(self)
        try:
            self._text.focus_set()
        except Exception:
            pass

    def _clear_placeholder(self, _e=None):
        if self._placeholder:
            self._placeholder = False
            self._text.delete("1.0", "end")
            self._text.config(fg=self._txt_color)

    def _on_return(self, e):
        if e.state & 0x0001:                         # Shift+Enter → salto de línea
            return None
        self._send()
        return "break"

    def _send(self):
        if self._placeholder:
            return
        text = self._text.get("1.0", "end").strip()
        if not text:
            return
        self.close()
        self._on_send(text)

    def _ds(self, e):
        self._drag = (e.x_root - self.winfo_x(), e.y_root - self.winfo_y())

    def _dm(self, e):
        ox, oy = self._drag
        self.geometry(f"+{e.x_root - ox}+{e.y_root - oy}")

    def close(self):
        if self._closed:
            return
        self._closed = True
        try:
            self.destroy()
        except Exception:
            pass
        if self._on_close:
            self._on_close()


# ── Notificación de recordatorio ─────────────────────────────────────────────
class ReminderNotification(tk.Toplevel):
    """Aviso visible (siempre encima) cuando salta un recordatorio."""
    W, H = 400, 158
    ACCENT = "#ff9800"

    def __init__(self, root, config: dict, reminder: dict, late: bool, slot: int,
                 on_snooze, on_done, on_close=None):
        super().__init__(root)
        self._on_snooze = on_snooze
        self._on_done   = on_done
        self._on_close  = on_close
        self._closed    = False
        self._flash_n   = 0
        bg   = ResponsePopup._safe_color(config.get("popup_bg", "#0d1117"), "#0d1117")
        txt  = ResponsePopup._safe_color(config.get("popup_text_color", "#e2e8f0"), "#e2e8f0")
        self._bg = bg
        sub  = lerp_color(bg, txt, 0.5)
        btn_bg = lerp_color(bg, "#ffffff", 0.10)

        self.title("Recordatorio")
        self.overrideredirect(True)
        self.wm_attributes("-topmost", True)
        self.configure(bg=self.ACCENT)

        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        x = sw - self.W - 24
        y = sh - 72 - (self.H + 12) * (slot + 1)
        if y < 10:
            y = 10 + (slot % 4) * 24
        self.geometry(f"{self.W}x{self.H}+{x}+{y}")

        self._body = body = tk.Frame(self, bg=bg)
        body.pack(fill="both", expand=True, padx=(5, 1), pady=1)

        top = tk.Frame(body, bg=bg)
        top.pack(fill="x", padx=14, pady=(10, 2))
        tk.Label(top, text="⏰  Recordatorio", bg=bg, fg=self.ACCENT,
                 font=("Segoe UI", 11, "bold")).pack(side="left")
        try:
            when = datetime.fromisoformat(reminder.get("cuando", ""))
        except Exception:
            when = datetime.now()
        hora = f"{when:%H:%M}"
        info = f"{hora}  (atrasado)" if late else hora
        tk.Label(top, text=info, bg=bg, fg=sub, font=("Segoe UI", 9)).pack(side="left", padx=8)
        close = tk.Label(top, text="×", bg=bg, fg=sub, font=("Segoe UI", 14), cursor="hand2")
        close.pack(side="right")
        close.bind("<Button-1>", lambda _e: self._done())

        tk.Label(body, text=reminder.get("texto", ""), bg=bg, fg=txt,
                 font=("Segoe UI", 12, "bold"), wraplength=self.W - 40,
                 justify="left", anchor="w").pack(fill="x", padx=14, pady=(2, 6))
        if reminder.get("repetir"):
            tk.Label(body, text=f"Se repite {REPEAT_LABELS.get(reminder['repetir'], '')}",
                     bg=bg, fg=sub, font=("Segoe UI", 8)).pack(anchor="w", padx=14)

        bar = tk.Frame(body, bg=bg)
        bar.pack(side="bottom", fill="x", padx=12, pady=(4, 10))
        try:
            snooze = max(1, int(float(config.get("reminder_snooze_minutes", 10))))
        except (TypeError, ValueError):
            snooze = 10
        for label, mins in ((f"Posponer {snooze} min", snooze), ("1 hora", 60)):
            b = tk.Label(bar, text=label, bg=btn_bg, fg=txt, font=("Segoe UI", 9),
                         padx=10, pady=4, cursor="hand2")
            b.pack(side="left", padx=(0, 6))
            b.bind("<Button-1>", lambda _e, m=mins: self._snooze(m))
        ok = tk.Label(bar, text="✓  Hecho", bg=self.ACCENT, fg="white",
                      font=("Segoe UI", 9, "bold"), padx=14, pady=4, cursor="hand2")
        ok.pack(side="right")
        ok.bind("<Button-1>", lambda _e: self._done())
        self.after(400, self._flash)

    def _flash(self):
        """Parpadeo del borde unas cuantas veces para llamar la atención."""
        if self._closed:
            return
        self._flash_n += 1
        try:
            self.configure(bg=self.ACCENT if self._flash_n % 2 else "#ffd180")
        except Exception:
            return
        if self._flash_n < 12:
            self.after(350, self._flash)
        else:
            self.configure(bg=self.ACCENT)

    def _snooze(self, minutes: int):
        self._close()
        self._on_snooze(minutes)

    def _done(self):
        self._close()
        self._on_done()

    def _close(self):
        if self._closed:
            return
        self._closed = True
        try:
            self.destroy()
        except Exception:
            pass
        if self._on_close:
            self._on_close(self)


# ── Settings Window ───────────────────────────────────────────────────────────
# ── Control del PC: utilidades de ventanas Tk ────────────────────────────────
def _tk_hwnd(win) -> int:
    """HWND de primer nivel de una ventana Tk."""
    h = win.winfo_id()
    try:
        p = ctypes.windll.user32.GetParent(h)
        return p or h
    except Exception:
        return h


def _tk_exclude_from_capture(win, on: bool = True):
    """La ventana sigue viéndose, pero no sale en las capturas de pantalla (Windows 10 2004+)."""
    if not IS_WINDOWS:
        return
    try:
        ctypes.windll.user32.SetWindowDisplayAffinity(_tk_hwnd(win), 0x11 if on else 0)
    except Exception:
        pass


def _tk_click_through(win, on: bool = True, no_activate: bool = False):
    """Los clics atraviesan la ventana (para que no estorbe a los clics de la IA)."""
    if not IS_WINDOWS:
        return
    try:
        u = ctypes.windll.user32
        h = _tk_hwnd(win)
        u.GetWindowLongW.restype = ctypes.c_long
        ex = u.GetWindowLongW(h, -20)
        if on:
            ex |= 0x20 | 0x80000 | (0x08000000 if no_activate else 0)   # TRANSPARENT|LAYERED
        else:
            ex &= ~0x20
        u.SetWindowLongW(h, -20, ex)
    except Exception:
        pass


def _tk_scale_monitor(root, monitor):
    """Rectángulo físico de un monitor → coordenadas de Tk (que no conoce el escalado)."""
    try:
        with _PcDpi():
            phys_w = ctypes.windll.user32.GetSystemMetrics(0)
        k = root.winfo_screenwidth() / max(1, phys_w)
    except Exception:
        k = 1.0
    l, t, r, b = monitor
    return int(l * k), int(t * k), int(r * k), int(b * k)


class PcBanner(tk.Toplevel):
    """Aviso en la parte de arriba de la pantalla mientras la IA controla el PC."""
    W, H = 560, 54

    def __init__(self, root, config: dict, monitor=None):
        super().__init__(root)
        self.overrideredirect(True)
        self.wm_attributes("-topmost", True)
        self.wm_attributes("-alpha", 0.93)
        self.configure(bg="#ff9800")
        inner = tk.Frame(self, bg="#161b22")
        inner.pack(fill='both', expand=True, padx=2, pady=2)
        hints = []
        if config.get("pc_stop_hotkey_enabled", True) and str(config.get("pc_stop_hotkey", "")).strip():
            hints.append(str(config.get("pc_stop_hotkey")).strip().upper())
        if config.get("pc_stop_corner", True):
            hints.append("ratón a una esquina")
        stop = ("  ·  Para detener: " + " o ".join(hints)) if hints else ""
        tk.Label(inner, text=f"🖱  Rubencho está controlando el PC{stop}", bg="#161b22",
                 fg="#ffb74d", font=("Segoe UI", 10, "bold")).pack(anchor='w', padx=12, pady=(5, 0))
        self._lbl = tk.Label(inner, text="", bg="#161b22", fg="#c9d1d9",
                             font=("Segoe UI", 9), anchor='w')
        self._lbl.pack(fill='x', padx=12)
        if monitor:
            l, t, r, _b = _tk_scale_monitor(root, monitor)
        else:
            l, t, r = 0, 0, self.winfo_screenwidth()
        self.geometry(f"{self.W}x{self.H}+{l + (r - l - self.W) // 2}+{t + 6}")
        self.update_idletasks()
        _tk_click_through(self, True, no_activate=True)
        _tk_exclude_from_capture(self, True)

    def set_text(self, text: str):
        t = _one_line(text)
        self._lbl.config(text=t if len(t) <= 80 else t[:77] + "…")


class PcConfirmDialog(tk.Toplevel):
    """Pregunta al usuario si permite una acción peligrosa de la IA."""
    TIMEOUT = 60

    def __init__(self, root, action: str, reason: str, on_result):
        super().__init__(root)
        self._on_result = on_result
        self._done = False
        self._left = self.TIMEOUT
        self.overrideredirect(True)
        self.wm_attributes("-topmost", True)
        self.configure(bg="#ff9800")
        bg, fg, muted = "#0d1117", "#e2e8f0", "#8b949e"
        box = tk.Frame(self, bg=bg, padx=18, pady=14)
        box.pack(fill='both', expand=True, padx=2, pady=2)
        tk.Label(box, text="✋  Rubencho quiere hacer algo que puede no tener vuelta atrás",
                 bg=bg, fg="#ffb74d", font=("Segoe UI", 11, "bold")).pack(anchor='w')
        tk.Label(box, text=action, bg=bg, fg=fg, font=("Segoe UI", 11), wraplength=470,
                 justify='left').pack(anchor='w', pady=(10, 2))
        tk.Label(box, text=f"Motivo del aviso: {reason}", bg=bg, fg=muted,
                 font=("Segoe UI", 9), wraplength=470, justify='left').pack(anchor='w')
        self._count = tk.Label(box, text="", bg=bg, fg=muted, font=("Segoe UI", 8))
        self._count.pack(anchor='w', pady=(6, 8))
        row = tk.Frame(box, bg=bg)
        row.pack(fill='x')
        for txt, ans, col in (("✅  Permitir", "si", "#2ea043"),
                              ("✅  Permitir todo en esta tarea", "todo", "#1f6feb"),
                              ("⛔  Cancelar", "no", "#da3633")):
            tk.Button(row, text=txt, bg=col, fg="white", activebackground=col, relief='flat',
                      font=("Segoe UI", 10, "bold"), padx=12, pady=6, cursor="hand2",
                      command=lambda a=ans: self._finish(a)).pack(side='left', padx=(0, 8))
        self.bind("<Escape>", lambda _e: self._finish("no"))
        self.update_idletasks()
        w, h = max(520, self.winfo_reqwidth()), self.winfo_reqheight()
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry(f"{w}x{h}+{(sw - w) // 2}+{(sh - h) // 3}")
        _tk_exclude_from_capture(self, True)
        self._tick()
        self.after(60, lambda: _force_foreground(self))

    def _tick(self):
        if self._done:
            return
        if self._left <= 0:
            self._finish("no")
            return
        self._count.config(text=f"Si no respondes, se cancelará en {self._left} s.")
        self._left -= 1
        self.after(1000, self._tick)

    def _finish(self, ans: str):
        if self._done:
            return
        self._done = True
        try:
            self.destroy()
        except Exception:
            pass
        self._on_result(ans)


class SettingsWindow(tk.Toplevel):
    C = {
        "bg":     "#0d1117",
        "panel":  "#161b22",
        "deep":   "#21262d",
        "accent": "#4f8ef7",
        "text":   "#e2e8f0",
        "muted":  "#7d8590",
    }
    LANGS = [
        ("es-ES","Español (España)"), ("es-MX","Español (México)"),
        ("es-AR","Español (Argentina)"), ("es-CO","Español (Colombia)"),
        ("en-US","English (US)"), ("en-GB","English (UK)"),
        ("fr-FR","Français"), ("de-DE","Deutsch"),
        ("it-IT","Italiano"), ("pt-BR","Português (Brasil)"),
        ("ca-ES","Català"), ("gl-ES","Galego"),
        ("ja-JP","日本語"), ("zh-CN","中文 (简体)"),
    ]
    # Secciones de la barra lateral: (clave, título, método que la construye)
    SECTIONS = [
        ("general",   "🏠  General",         "_tab_general"),
        ("wakeword",  "🗣  Palabra clave",    "_tab_wakeword"),
        ("voice",     "🎤  Reconocimiento",   "_tab_voice"),
        ("ai",        "🤖  IA / Ollama",      "_tab_ai"),
        ("vision",    "📸  Visión",           "_tab_vision"),
        ("pc",        "🖱  Control del PC",   "_tab_pc"),
        ("memory",    "🧠  Memoria",          "_tab_memory"),
        ("reminders", "⏰  Recordatorios",    "_tab_reminders"),
        ("aitasks",   "🤖  Tareas de la IA",   "_tab_ai_tasks"),
        ("orb",       "🔵  Orbe",             "_tab_orb"),
        ("popup",     "💬  Popup",            "_tab_popup"),
        ("tts",       "🔊  Voz IA",           "_tab_tts"),
        ("log",       "💬  Conversación",     "_tab_log"),
        ("whatsapp",  "📱  WhatsApp",         "_tab_whatsapp"),
        ("ptt",       "⌨️  Push-to-Talk",     "_tab_ptt"),
    ]

    def __init__(self, root, config: dict, on_save, app=None, section: str = None):
        super().__init__(root)
        self._cfg     = config.copy()
        self._on_save = on_save
        self._app     = app            # acceso a memoria, recordatorios y pruebas
        self._vars: dict = {}
        # Los hilos de fondo no tocan widgets: encolan la actualización aquí
        self._ui_calls: queue.Queue = queue.Queue()
        self.after(80, self._poll_ui_calls)
        self.title("⚙️  Rubencho AI – Configuración")
        self.resizable(True, True)
        self.configure(bg=self.C["bg"])
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        W, H = 940, min(720, sh - 80)
        self.geometry(f"{W}x{H}+{(sw - W) // 2}+{max(10, (sh - H) // 2 - 20)}")
        self.minsize(780, 500)
        self._init_styles()
        self._build(section or "general")
        self.after(80, lambda: _force_foreground(self))

    def _init_styles(self):
        s = ttk.Style()
        s.theme_use('clam')
        bg, panel, deep, accent, text, muted = (
            self.C["bg"], self.C["panel"], self.C["deep"],
            self.C["accent"], self.C["text"], self.C["muted"])
        s.configure("TNotebook",     background=bg, borderwidth=0)
        s.configure("TNotebook.Tab", background=panel, foreground=muted,
                    padding=[14,7], font=("Segoe UI",10))
        s.map("TNotebook.Tab",
              background=[("selected", deep)],
              foreground=[("selected", accent)])
        for cls in ("TFrame","TLabelframe"):
            s.configure(cls, background=bg)
        s.configure("TLabelframe.Label", background=bg,
                    foreground=accent, font=("Segoe UI",10,"bold"))
        s.configure("TLabel",       background=bg, foreground=text, font=("Segoe UI",10))
        s.configure("TCheckbutton", background=bg, foreground=text, font=("Segoe UI",10))
        s.map("TCheckbutton", background=[("active", bg)])
        s.configure("TCombobox",    fieldbackground=panel, background=panel,
                    foreground=text, selectbackground=deep, font=("Segoe UI",10))
        s.configure("Treeview", background=panel, fieldbackground=panel, foreground=text,
                    rowheight=26, borderwidth=0, font=("Segoe UI", 10))
        s.configure("Treeview.Heading", background=deep, foreground=accent, relief="flat",
                    font=("Segoe UI", 9, "bold"))
        s.map("Treeview", background=[("selected", accent)], foreground=[("selected", "white")])
        s.map("Treeview.Heading", background=[("active", deep)])

    def _build(self, initial: str = "general"):
        bg, panel, deep, accent = self.C["bg"], self.C["panel"], self.C["deep"], self.C["accent"]
        text, muted = self.C["text"], self.C["muted"]
        hdr = tk.Frame(self, bg=deep, height=54)
        hdr.pack(fill='x')
        hdr.pack_propagate(False)
        tk.Label(hdr, text="⚙️   Configuración de Rubencho AI",
                 bg=deep, fg=accent,
                 font=("Segoe UI",14,"bold")).pack(side='left', padx=20)

        foot = tk.Frame(self, bg=deep, height=54)
        foot.pack(fill='x', side='bottom')
        foot.pack_propagate(False)
        tk.Button(foot, text="💾  Guardar",
                  bg=accent, fg="white",
                  font=("Segoe UI",11,"bold"),
                  relief='flat', padx=24, pady=10, cursor="hand2",
                  activebackground="#2563eb",
                  command=self._save).pack(side='right', padx=10, pady=8)
        tk.Button(foot, text="✕  Cancelar",
                  bg=self.C["panel"], fg=self.C["muted"],
                  font=("Segoe UI",10),
                  relief='flat', padx=16, pady=10, cursor="hand2",
                  activebackground=self.C["deep"],
                  command=self.destroy).pack(side='right', padx=4, pady=8)
        tk.Label(foot, text="La memoria y los recordatorios se guardan al momento; "
                            "el resto, al pulsar Guardar.",
                 bg=deep, fg=muted, font=("Segoe UI", 8)).pack(side='left', padx=16)

        body = tk.Frame(self, bg=bg)
        body.pack(fill='both', expand=True)
        side = tk.Frame(body, bg=panel, width=200)
        side.pack(side='left', fill='y')
        side.pack_propagate(False)
        tk.Frame(body, bg=deep, width=1).pack(side='left', fill='y')
        self._content = tk.Frame(body, bg=bg)
        self._content.pack(side='left', fill='both', expand=True)

        self._sections: dict = {}
        self._current = None
        tk.Frame(side, bg=panel, height=8).pack(fill='x')
        for key, title, builder in self.SECTIONS:
            btn = tk.Label(side, text=title, anchor='w', bg=panel, fg=text,
                           font=("Segoe UI", 10), padx=16, pady=7, cursor="hand2")
            btn.pack(fill='x')
            btn.bind("<Button-1>", lambda _e, k=key: self._show_section(k))
            btn.bind("<Enter>", lambda _e, b=btn, k=key:
                     b.config(bg=deep) if k != self._current else None)
            btn.bind("<Leave>", lambda _e, b=btn, k=key:
                     b.config(bg=panel) if k != self._current else None)
            self._sections[key] = {"btn": btn, "builder": getattr(self, builder),
                                   "outer": None, "canvas": None}
        tk.Label(side, text=APP_NAME, bg=panel, fg=muted,
                 font=("Segoe UI", 8)).pack(side='bottom', pady=10)

        # Una sola gestión de la rueda del ratón para toda la ventana (antes cada
        # pestaña hacía bind_all y solo funcionaba la última).
        self.bind("<MouseWheel>", self._on_wheel)
        self.bind("<Button-4>",   self._on_wheel)
        self.bind("<Button-5>",   self._on_wheel)
        self._show_section(initial)

    def _show_section(self, key: str):
        if key not in self._sections:
            key = "general"
        bg, panel, deep, accent = self.C["bg"], self.C["panel"], self.C["deep"], self.C["accent"]
        sec = self._sections[key]
        if sec["outer"] is None:                  # se construye la primera vez que se abre
            outer, canvas, inner = self._scrollable_section(self._content)
            sec["outer"], sec["canvas"] = outer, canvas
            try:
                sec["builder"](inner)
            except Exception as e:
                import traceback
                traceback.print_exc()
                tk.Label(inner, text=f"❌ Error construyendo la sección: {e}",
                         bg=bg, fg="#ff5566", font=("Segoe UI", 10)).pack(anchor='w')
        if self._current and self._current != key:
            prev = self._sections[self._current]
            prev["outer"].pack_forget()
            prev["btn"].config(bg=panel, fg=self.C["text"], font=("Segoe UI", 10))
        sec["outer"].pack(fill='both', expand=True)
        sec["btn"].config(bg=deep, fg=accent, font=("Segoe UI", 10, "bold"))
        self._current = key

    def _scrollable_section(self, parent):
        bg = self.C["bg"]
        outer = tk.Frame(parent, bg=bg)
        canvas = tk.Canvas(outer, bg=bg, highlightthickness=0, bd=0)
        vsb    = tk.Scrollbar(outer, orient="vertical",
                              command=canvas.yview,
                              bg=self.C["panel"],
                              troughcolor=self.C["bg"],
                              relief='flat', bd=0, width=8)
        canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side='right', fill='y')
        canvas.pack(side='left', fill='both', expand=True)
        inner = tk.Frame(canvas, bg=bg, padx=16, pady=10)
        win_id = canvas.create_window((0, 0), window=inner, anchor='nw')

        inner.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(win_id, width=e.width))
        return outer, canvas, inner

    def _on_wheel(self, event):
        sec = self._sections.get(self._current) if self._current else None
        if not sec or sec["canvas"] is None:
            return
        try:
            cls = event.widget.winfo_class()
        except Exception:
            cls = ""
        if cls in ("Text", "Treeview", "Listbox", "TCombobox"):
            return                                 # esos widgets se desplazan solos
        canvas = sec["canvas"]
        if getattr(event, "num", None) == 4:
            step = -1
        elif getattr(event, "num", None) == 5:
            step = 1
        else:
            step = -1 if event.delta > 0 else 1
            step *= max(1, abs(int(event.delta / 120)))
        try:
            canvas.yview_scroll(step * 2, "units")
        except Exception:
            pass

    # ── Helpers ───────────────────────────────────────────────────────────────
    def _ui(self, fn):
        """Ejecuta fn en el hilo de la interfaz (se puede llamar desde cualquier hilo)."""
        self._ui_calls.put(fn)

    def _poll_ui_calls(self):
        try:
            while True:
                fn = self._ui_calls.get_nowait()
                try:
                    fn()
                except Exception as e:
                    print(f"[Ajustes] {e}")
        except queue.Empty:
            pass
        try:
            if self.winfo_exists():
                self.after(80, self._poll_ui_calls)
        except Exception:
            pass

    def _var_value(self, key: str, default=""):
        """Valor actual de una opción (de la interfaz si existe; si no, de la config)."""
        var = self._vars.get(key)
        if var is not None:
            try:
                return var.get()
            except Exception:
                pass
        return self._cfg.get(key, DEFAULT_CONFIG.get(key, default))

    def _v(self, key, typ='str'):
        val = self._cfg.get(key, DEFAULT_CONFIG.get(key,""))
        if   typ=='bool':   v = tk.BooleanVar(value=bool(val))
        elif typ=='int':    v = tk.IntVar(value=int(float(val)))
        elif typ=='double': v = tk.DoubleVar(value=float(val))
        else:               v = tk.StringVar(value=str(val))
        self._vars[key] = v
        return v

    def _entry(self, p, key, row, col=1, w=28):
        var = self._v(key)
        tk.Entry(p, textvariable=var,
                 bg=self.C["panel"], fg=self.C["text"],
                 font=("Segoe UI",10), relief='flat', width=w,
                 insertbackground=self.C["accent"]
                 ).grid(row=row, column=col, sticky='ew', padx=8, pady=5)
        return var

    def _check(self, p, key, text, row, col=0):
        v = self._v(key,'bool')
        ttk.Checkbutton(p, text=text, variable=v).grid(
            row=row, column=col, columnspan=2, sticky='w', padx=8, pady=5)
        return v

    def _scale(self, p, key, row, frm=0.0, to=1.0, res=0.01, col=1):
        v  = self._v(key,'double')
        fr = tk.Frame(p, bg=self.C["bg"])
        fr.grid(row=row, column=col, sticky='ew', padx=8, pady=5)
        tk.Scale(fr, variable=v, from_=frm, to=to, resolution=res,
                 orient='horizontal', bg=self.C["bg"], fg=self.C["text"],
                 troughcolor=self.C["panel"], highlightthickness=0,
                 length=200, showvalue=False).pack(side='left')

        def fmt(*_):
            try:
                x = float(v.get())
                return f"{int(round(x))}" if res >= 1 else f"{x:g}"
            except Exception:
                return ""
        val_lbl = tk.Label(fr, text=fmt(), bg=self.C["bg"], fg=self.C["accent"],
                           font=("Segoe UI",9,"bold"), width=6)
        val_lbl.pack(side='left', padx=4)
        v.trace_add('write', lambda *_: val_lbl.config(text=fmt()))
        return v

    def _color_btn(self, p, key, row, col=1):
        v    = tk.StringVar(value=self._cfg.get(key,"#4f8ef7"))
        self._vars[key] = v
        fr   = tk.Frame(p, bg=self.C["bg"])
        fr.grid(row=row, column=col, sticky='w', padx=8, pady=5)
        prev = tk.Label(fr, bg=v.get(), width=3, height=1, relief='groove', bd=2)
        prev.pack(side='left', padx=(0,6))
        tk.Entry(fr, textvariable=v, bg=self.C["panel"], fg=self.C["text"],
                 font=("Segoe UI",10), relief='flat', width=9,
                 insertbackground=self.C["accent"]).pack(side='left')
        def pick():
            res = colorchooser.askcolor(color=v.get(), parent=self)
            if res[1]: v.set(res[1]); prev.config(bg=res[1])
        def sync(*_):
            try: prev.config(bg=v.get())
            except Exception: pass
        v.trace_add('write', sync)
        tk.Button(fr, text="🎨", bg=self.C["deep"], fg="white",
                  relief='flat', cursor="hand2", command=pick, padx=4
                  ).pack(side='left', padx=4)
        return v

    def _lbl(self, p, text, row, col=0):
        ttk.Label(p, text=text).grid(row=row, column=col, sticky='w', padx=8, pady=5)

    def _info(self, p, lines):
        box = tk.Frame(p, bg=self.C["deep"], padx=12, pady=10)
        box.pack(fill='x', pady=8)
        for ln in lines:
            tk.Label(box, text=ln, bg=self.C["deep"], fg=self.C["muted"],
                     font=("Segoe UI",9), anchor='w').pack(fill='x', pady=1)

    # ── Tabs ──────────────────────────────────────────────────────────────────
    def _tab_general(self, p):
        p.columnconfigure(1, weight=1)
        sf = ttk.LabelFrame(p, text="Sistema", padding=10)
        sf.pack(fill='x', pady=8)
        self._check(sf, "autostart",           "🚀  Iniciar con el sistema operativo", 0)
        self._check(sf, "always_on_top_popup",  "🔝  Popup siempre encima",             1)
        self._check(sf, "sound_feedback",       "🔔  Pitido al detectar la palabra clave", 2)

        df = ttk.LabelFrame(p, text="🕐  Fecha y hora", padding=10)
        df.pack(fill='x', pady=8)
        self._check(df, "datetime_in_messages",
                    "🕐  Decir a la IA el día y la hora actuales en cada mensaje", 0)
        tk.Label(df,
                 text=("Cada mensaje se envía con una marca como «[martes 6 de octubre de 2026, 18:45]»,\n"
                       "así la IA sabe qué hora es y cuánto tiempo ha pasado entre mensajes.\n"
                       "Los recordatorios funcionan igualmente aunque lo desactives."),
                 bg=self.C["bg"], fg=self.C["muted"], font=("Segoe UI", 8), justify='left'
                 ).grid(row=1, column=0, columnspan=2, sticky='w', padx=8, pady=(0, 4))
        cf = ttk.LabelFrame(p, text="💬  Conversación continua", padding=10)
        cf.pack(fill='x', pady=8)
        cf.columnconfigure(1, weight=1)
        self._check(cf, "continuous_conv",
                    "🔁  Seguir escuchando tras responder (sin repetir la palabra clave)", 0)
        self._lbl(cf, "Silencio para parar (s):", 1)
        self._scale(cf, "continuous_timeout", 1, frm=2.0, to=30.0, res=0.5)
        self._lbl(cf, "Palabra de parada:", 2)
        self._entry(cf, "continuous_stop_word", 2, w=14)
        tk.Label(cf,
                 text="Di la palabra de parada para volver al modo wake word.\nEl orbe se vuelve verde mientras estás en modo continuo.",
                 bg=self.C["bg"], fg=self.C["muted"],
                 font=("Segoe UI", 8), justify='left'
                 ).grid(row=3, column=0, columnspan=2, sticky='w', padx=8, pady=4)

        dd = ttk.LabelFrame(p, text="📂  Tus datos", padding=10)
        dd.pack(fill='x', pady=8)
        tk.Label(dd, text=f"Configuración, memoria, recordatorios, capturas e historial:\n{APP_DIR}",
                 bg=self.C["bg"], fg=self.C["muted"], font=("Segoe UI", 9), justify='left'
                 ).pack(anchor='w', padx=8, pady=(0, 6))
        tk.Button(dd, text="📂  Abrir la carpeta de datos", bg=self.C["deep"], fg=self.C["text"],
                  relief='flat', cursor="hand2", font=("Segoe UI", 9), padx=10, pady=5,
                  command=lambda: (APP_DIR.mkdir(parents=True, exist_ok=True), _open_path(APP_DIR))
                  ).pack(anchor='w', padx=8)

        lf = ttk.LabelFrame(p, text="Idioma de reconocimiento de voz", padding=10)
        lf.pack(fill='x', pady=8)
        lf.columnconfigure(1, weight=1)
        names = [f"{c}  –  {n}" for c,n in self.LANGS]
        codes = [c for c,_ in self.LANGS]
        cur   = self._cfg.get("language","es-ES")
        cur_n = next((f"{c}  –  {n}" for c,n in self.LANGS if c==cur), names[0])
        lv    = tk.StringVar(value=cur_n)
        self._vars["_lang_display"] = lv
        self._lang_codes = codes
        self._lang_names = names
        ttk.Label(lf, text="Idioma:").grid(row=0, column=0, sticky='w', padx=8, pady=5)
        ttk.Combobox(lf, textvariable=lv, values=names, state='readonly', width=38
                     ).grid(row=0, column=1, sticky='ew', padx=8, pady=5)

    def _tab_wakeword(self, p):
        p.columnconfigure(1, weight=1)
        pf = ttk.LabelFrame(p, text="Palabra de activación", padding=12)
        pf.pack(fill='x', pady=8)
        ttk.Label(pf, text="Pronuncia esta palabra para activar Rubencho AI:"
                  ).pack(anchor='w', pady=(0,10))
        cur     = self._cfg.get("wake_word","asistente")
        wv      = tk.StringVar(value=cur)
        self._vars["wake_word"] = wv
        presets = self._cfg.get("wake_words_presets", DEFAULT_CONFIG["wake_words_presets"])
        grid    = tk.Frame(pf, bg=self.C["bg"])
        grid.pack(fill='x')
        cols = 4
        for i, word in enumerate(presets):
            tk.Radiobutton(grid, text=f"  {word.capitalize()}  ",
                           variable=wv, value=word,
                           bg=self.C["bg"], fg=self.C["text"],
                           selectcolor=self.C["deep"],
                           activebackground=self.C["bg"],
                           font=("Segoe UI",10), indicatoron=0,
                           relief='groove', padx=8, pady=5, cursor="hand2"
                           ).grid(row=i//cols, column=i%cols, padx=4, pady=4, sticky='ew')
        cf = ttk.LabelFrame(p, text="Palabra personalizada", padding=10)
        cf.pack(fill='x', pady=8)
        cf.columnconfigure(1, weight=1)
        ttk.Label(cf, text="Palabra:").grid(row=0, column=0, sticky='w', padx=8)
        self._entry(cf, "custom_wake_word", 0, w=22)
        self._check(cf, "use_custom_wake_word",
                    "Usar esta palabra en vez de la lista", 1)
        self._info(p, [
            "💡  Palabras de 2-3 sílabas con consonantes fuertes funcionan mejor",
            "⚡  En modo local (Reconocimiento) usa una palabra que exista en español: asistente,",
            "      oye, despierta, Alcantarilla… Las inventadas o en inglés (Jarvis, Rubencho, Nova)",
            "      no las conoce: con esas elige Google.",
        ])

    def _tab_voice(self, p):
        p.columnconfigure(1, weight=1)
        ef = ttk.LabelFrame(p, text="Motor de la palabra clave", padding=12)
        ef.pack(fill='x', pady=8)
        ev = self._v("speech_engine")
        for val, txt in [
            ("vosk",  "⚡  Local al instante  (Vosk, sin internet, recomendado)"),
            ("google","🌐  Google Speech  (por internet; espera a que acabes la frase)"),
        ]:
            tk.Radiobutton(ef, text=txt, variable=ev, value=val,
                           bg=self.C["bg"], fg=self.C["text"],
                           selectcolor=self.C["deep"], activebackground=self.C["bg"],
                           font=("Segoe UI",10)).pack(anchor='w', pady=4)
        vf = ttk.LabelFrame(p, text="Modelo Vosk  (vacío = el que viene con Rubencho)", padding=10)
        vf.pack(fill='x', pady=8)
        vf.columnconfigure(1, weight=1)
        ttk.Label(vf, text="Carpeta:").grid(row=0, column=0, sticky='w', padx=8)
        vp = self._entry(vf, "vosk_model_path", 0, w=26)
        def browse():
            d = filedialog.askdirectory(parent=self)
            if d: vp.set(d)
        tk.Button(vf, text="📁", bg=self.C["deep"], fg="white",
                  relief='flat', cursor="hand2", command=browse
                  ).grid(row=0, column=2, padx=4)
        tk.Label(vf, text="Descarga: https://alphacephei.com/vosk/models  →  vosk-model-es-0.42",
                 bg=self.C["bg"], fg=self.C["muted"], font=("Segoe UI",9)
                 ).grid(row=1, column=0, columnspan=3, sticky='w', padx=8, pady=4)
        tf = ttk.LabelFrame(p, text="⏱  Tiempos de grabación", padding=10)
        tf.pack(fill='x', pady=6)
        tf.columnconfigure(1, weight=1)
        for i,(key,lbl,frm,to,res) in enumerate([
            ("phrase_time_limit", "Tiempo máx. escucha (s):",    5.0, 30.0, 1.0),
            ("wake_phrase_limit", "Frase activación, Google (s):", 2.0,  6.0, 0.5),
            ("silence_timeout",   "Timeout si no hay voz (s):",   0.5,  8.0, 0.5),
        ]):
            self._lbl(tf, lbl, i)
            self._scale(tf, key, i, frm=frm, to=to, res=res)
        self._check(tf, "show_transcript", "Mostrar lo que dijiste en el popup", 3)

        vf2 = ttk.LabelFrame(p, text="🎤  Detección de fin de frase (VAD)", padding=10)
        vf2.pack(fill='x', pady=6)
        vf2.columnconfigure(1, weight=1)
        for i,(key,lbl,frm,to,res) in enumerate([
            ("pause_threshold",       "⭐ Pausa para terminar frase (s):", 0.5, 5.0, 0.1),
            ("phrase_threshold",      "Voz mínima para empezar (s):",      0.05, 1.0, 0.05),
            ("non_speaking_duration", "Silencio a mantener al final (s):",  0.05, 1.5, 0.05),
            ("dynamic_energy_ratio",  "Ratio voz/ambiente:",                1.0,  4.0, 0.1),
        ]):
            self._lbl(vf2, lbl, i)
            self._scale(vf2, key, i, frm=frm, to=to, res=res)

        ef2 = ttk.LabelFrame(p, text="🔊  Umbral de energía", padding=10)
        ef2.pack(fill='x', pady=6)
        ef2.columnconfigure(1, weight=1)
        self._check(ef2, "dynamic_energy_threshold",
                    "Ajustar umbral automáticamente (recomendado)", 0)
        self._lbl(ef2, "Umbral manual:", 1)
        self._scale(ef2, "energy_threshold", 1, frm=50, to=4000, res=50)

        cf = ttk.LabelFrame(p, text="🤖  Motor de transcripción del comando", padding=12)
        cf.pack(fill='x', pady=6)
        cf.columnconfigure(1, weight=1)
        cv = self._v("command_engine")
        for val, txt2 in [
            ("whisper","⭐  faster-whisper  (muy preciso, offline, recomendado)"),
            ("google", "🌐  Google Speech  (online, ligero, sin descarga)"),
            ("vosk",   "💻  Vosk           (offline, modelo pequeño)"),
        ]:
            tk.Radiobutton(cf, text=txt2, variable=cv, value=val,
                           bg=self.C["bg"], fg=self.C["text"],
                           selectcolor=self.C["deep"], activebackground=self.C["bg"],
                           font=("Segoe UI",10)).pack(anchor='w', pady=2)

        wf = ttk.LabelFrame(p, text="⚙️  Opciones de faster-whisper", padding=10)
        wf.pack(fill='x', pady=6)
        wf.columnconfigure(1, weight=1)

        self._lbl(wf, "Modelo:", 0)
        wm = self._v("whisper_model")
        ttk.Combobox(wf, textvariable=wm,
                     values=["tiny","base","small","medium","large-v2","large-v3"],
                     state='readonly', width=14
                     ).grid(row=0, column=1, sticky='w', padx=8, pady=4)

        self._lbl(wf, "Dispositivo:", 1)
        wd = self._v("whisper_device")
        ttk.Combobox(wf, textvariable=wd,
                     values=["auto", "cpu", "cuda"],
                     state='readonly', width=8
                     ).grid(row=1, column=1, sticky='w', padx=8, pady=4)

        self._lbl(wf, "Idioma:", 2)
        wl = self._v("whisper_language")
        ttk.Combobox(wf, textvariable=wl,
                     values=["es","en","fr","de","it","pt","ca","gl","ja","zh"],
                     width=8).grid(row=2, column=1, sticky='w', padx=8, pady=4)

        self._lbl(wf, "Precisión (beam):", 3)
        self._scale(wf, "whisper_beam_size", 3, frm=1, to=5, res=1)
        self._check(wf, "whisper_preload",
                    "⚡  Cargar el modelo al iniciar el asistente (la 1ª orden no espera)", 4)

        gpu_lbl = tk.Label(wf, text="🔎  Comprobando GPU…", bg=self.C["bg"], fg=self.C["muted"],
                           font=("Segoe UI", 8), justify='left')
        gpu_lbl.grid(row=5, column=0, columnspan=2, sticky='w', padx=8, pady=(4, 0))

        def _check_gpu():
            ok, why = cuda_whisper_available()
            msg = ("✅  GPU NVIDIA lista: con «auto» o «cuda» transcribe ~15 veces más rápido,\n"
                   "     pero ocupa ~1 GB de memoria de vídeo mientras Rubencho está abierto\n"
                   "     (con «medium»; «small» ≈ 0,5 GB). Elige «cpu» para dejarla libre."
                   if ok else f"ℹ️  GPU no disponible para Whisper: {why}")
            self._ui(lambda: gpu_lbl.config(text=msg, fg="#44ff88" if ok else self.C["muted"]))
        threading.Thread(target=_check_gpu, daemon=True).start()

        tk.Label(wf,
                 text=("Instalar:  pip install faster-whisper\n"
                       "tiny≈39MB · base≈74MB · small≈244MB · medium≈769MB · large≈1.5GB\n"
                       "El modelo se descarga automáticamente la primera vez que se usa.\n"
                       "«auto» usa la GPU si está disponible y, si falla, la CPU.\n"
                       "Beam 5 = más preciso · Beam 1 = algo más rápido."),
                 bg=self.C["bg"], fg=self.C["muted"], font=("Segoe UI",8), justify='left'
                 ).grid(row=6, column=0, columnspan=2, sticky='w', padx=8, pady=4)

        self._info(p, [
            "⭐  'Pausa para terminar frase' sigue siendo el ajuste más importante para el VAD",
            "⭐  faster-whisper small: mejor relación velocidad/precisión en español",
            "⚡  En modo local te escucha en cuanto dices la palabra, y vale decirlo todo seguido:",
            "      «asistente, ¿qué hora es?». Luego espera la «Pausa para terminar frase» y transcribe.",
            "💡  La palabra clave usa el motor de arriba; la orden, el de abajo",
            "💡  Whisper ignora frases que se inventa con ruido («¡Gracias por ver el vídeo!»…)",
        ])

    def _tab_ai(self, p):
        p.columnconfigure(1, weight=1)

        # ── Ollama conexión ──────────────────────────────────────────────────
        of = ttk.LabelFrame(p, text="Ollama", padding=12)
        of.pack(fill='x', pady=6)
        of.columnconfigure(1, weight=1)
        self._lbl(of, "Host:", 0)
        self._entry(of, "ollama_host", 0)
        self._lbl(of, "Modelo:", 1)
        mv  = self._v("ollama_model")
        mcb = ttk.Combobox(of, textvariable=mv, width=30, font=("Segoe UI",10))
        mcb.grid(row=1, column=1, sticky='ew', padx=8, pady=5)
        sl  = tk.Label(of, text="", bg=self.C["bg"], fg=self.C["muted"], font=("Segoe UI",9))
        sl.grid(row=3, column=0, columnspan=2, sticky='w', padx=8, pady=4)
        def refresh(host: str):
            # (hilo secundario: los widgets se actualizan con self.after)
            try:
                r = requests.get(f"{host}/api/tags", timeout=5)
                models = [m["name"] for m in r.json().get("models",[])]
                if models:
                    self._ui(lambda: (mcb.configure(values=models),
                                           sl.config(text=f"✅  {len(models)} modelo(s)", fg="#44ff88")))
                else:
                    self._ui(lambda: sl.config(text="⚠️  Sin modelos", fg="#ffaa44"))
            except Exception as e:
                err = f"❌  {e}"
                self._ui(lambda: sl.config(text=err, fg="#ff5566"))
        def start_refresh():
            sl.config(text="⏳  Conectando...", fg=self.C["muted"])
            threading.Thread(target=refresh, args=(self._var_value("ollama_host"),),
                             daemon=True).start()
        tk.Button(of, text="🔄  Detectar modelos",
                  bg=self.C["deep"], fg="white", relief='flat', cursor="hand2",
                  font=("Segoe UI",9), padx=10, pady=6,
                  command=start_refresh
                  ).grid(row=2, column=0, columnspan=2, sticky='w', padx=8, pady=4)
        self._lbl(of, "Mantener cargado:", 4)
        self._entry(of, "ollama_keep_alive", 4, w=10)
        self._lbl(of, "Contexto (num_ctx):", 5)
        self._entry(of, "ollama_num_ctx", 5, w=10)
        self._check(of, "ollama_preload",
                    "⚡  Precargar el modelo al iniciar (solo modelos locales)", 6)
        tk.Label(of, text=("«Mantener cargado»: tiempo que Ollama conserva el modelo en memoria "
                           "(p.ej. 30m, 2h, -1 = siempre).\n«Contexto»: 0 = el de Ollama. Con modelos "
                           "locales y mucha memoria/herramientas, 8192 o 16384 evita que olvide instrucciones."),
                 bg=self.C["bg"], fg=self.C["muted"], font=("Segoe UI", 8), justify='left'
                 ).grid(row=7, column=0, columnspan=2, sticky='w', padx=8, pady=(2, 4))

        # ── Opciones IA ──────────────────────────────────────────────────────
        opt = ttk.LabelFrame(p, text="Comportamiento", padding=12)
        opt.pack(fill='x', pady=6)
        opt.columnconfigure(1, weight=1)
        tk.Label(opt, text="🧠  Razonamiento interno (pensar antes de responder):",
                 bg=self.C["bg"], fg=self.C["text"], font=("Segoe UI", 10)
                 ).grid(row=0, column=0, columnspan=2, sticky='w', padx=8, pady=(0, 2))
        tv = tk.StringVar(value=think_mode(self._cfg))
        self._vars["ollama_think_mode"] = tv
        for i, (val, txt) in enumerate((
                ("never",  "⚡  Nunca  (respuestas más rápidas)"),
                ("auto",   "🤔  Que decida la IA: solo si es complicado o si se ha equivocado"),
                ("always", "🧠  Siempre  (más lento: unos segundos más por respuesta)"))):
            tk.Radiobutton(opt, text=txt, variable=tv, value=val,
                           bg=self.C["bg"], fg=self.C["text"], selectcolor=self.C["deep"],
                           activebackground=self.C["bg"], font=("Segoe UI", 10)
                           ).grid(row=1 + i, column=0, columnspan=2, sticky='w', padx=16, pady=1)
        tk.Label(opt, text=("Con «Que decida la IA», cuando piensa lo verás en el panel («Lo pienso con "
                            "calma…»).\nSolo funciona con modelos que razonan (como Gemma 4)."),
                 bg=self.C["bg"], fg=self.C["muted"], font=("Segoe UI", 8), justify='left'
                 ).grid(row=4, column=0, columnspan=2, sticky='w', padx=8, pady=(2, 4))
        tk.Label(opt, text="💬  Los mensajes anteriores que recuerda se ajustan en «Conversación».",
                 bg=self.C["bg"], fg=self.C["muted"], font=("Segoe UI", 8)
                 ).grid(row=5, column=0, columnspan=2, sticky='w', padx=8, pady=2)

        # ── Herramientas ─────────────────────────────────────────────────────
        cmd_f = ttk.LabelFrame(p, text="🛠  Herramientas de la IA", padding=12)
        cmd_f.pack(fill='x', pady=6)
        cmd_f.columnconfigure(1, weight=1)
        self._check(cmd_f, "cmd_enabled",
                    "🖥️  Permitir que la IA ejecute comandos del sistema (CMD)", 0)
        self._check(cmd_f, "web_enabled",
                    "🔍  Permitir búsquedas en internet y leer páginas web", 1)
        self._check(cmd_f, "browser_enabled",
                    "🌐  Permitir que controle un navegador (Playwright)" +
                    ("" if _PLAYWRIGHT_AVAILABLE else "  — no instalado"), 2)
        tk.Label(cmd_f,
                 text=(
                     "Con CMD activado, la IA puede ejecutar comandos reales en tu consola para\n"
                     "obtener información (IP, RAM, archivos, procesos…), abrir programas o webs\n"
                     "y hacer cálculos exactos. Los comandos destructivos están bloqueados.\n"
                     "La visión, la memoria y los recordatorios tienen su propia sección.\n\n"
                     f"⏱  Timeout por comando: {CMD_TIMEOUT}s     "
                     f"📄  Log: {APP_DIR / 'cmd_log.txt'}"
                 ),
                 bg=self.C["bg"], fg=self.C["muted"],
                 font=("Segoe UI", 8), justify='left'
                 ).grid(row=3, column=0, columnspan=2, sticky='w', padx=8, pady=(4,2))
        def open_cmd_log():
            log_path = APP_DIR / "cmd_log.txt"
            if log_path.exists():
                _open_path(log_path)
            else:
                messagebox.showinfo("Log CMD",
                    "Todavía no se ha ejecutado ningún comando.", parent=self)
        tk.Button(cmd_f, text="📋  Ver log de comandos",
                  bg=self.C["deep"], fg=self.C["text"],
                  font=("Segoe UI",9), relief='flat', cursor="hand2",
                  padx=10, pady=5,
                  command=open_cmd_log
                  ).grid(row=4, column=0, sticky='w', padx=8, pady=6)

        # ── Prompt de sistema ────────────────────────────────────────────────
        sf = ttk.LabelFrame(p, text="📝  Prompt de sistema  (instrucciones iniciales a la IA)", padding=12)
        sf.pack(fill='x', pady=6)
        sf.columnconfigure(0, weight=1)
        tk.Label(sf, text=("Tu personalidad e indicaciones para la IA. Las instrucciones de las "
                           "herramientas (comandos, visión,\nmemoria, recordatorios…) se añaden "
                           "automáticamente según lo que tengas activado."),
                 bg=self.C["bg"], fg=self.C["muted"], font=("Segoe UI",9), justify='left'
                 ).grid(row=0, column=0, sticky='w', pady=(0,4))
        sp_var = tk.StringVar(value=self._cfg.get("system_prompt",""))
        self._vars["system_prompt"] = sp_var
        sp_txt = tk.Text(sf, height=7, bg=self.C["panel"], fg=self.C["text"],
                         font=("Segoe UI",10), relief='flat',
                         insertbackground=self.C["accent"], wrap='word', undo=True)
        sp_txt.insert("1.0", sp_var.get())
        sp_txt.grid(row=1, column=0, sticky='ew', pady=2)
        self._sp_text_widget = sp_txt
        tk.Button(sf, text="👁  Ver las instrucciones completas que recibe la IA",
                  bg=self.C["deep"], fg=self.C["text"], font=("Segoe UI", 9),
                  relief='flat', cursor="hand2", padx=10, pady=5,
                  command=self._show_full_prompt
                  ).grid(row=2, column=0, sticky='w', pady=(6, 0))

    def _pending_cfg(self) -> dict:
        """Configuración con los cambios aún no guardados de esta ventana."""
        cfg = dict(self._app.config if self._app else self._cfg)
        for key, var in self._vars.items():
            if not key.startswith("_"):
                try:
                    cfg[key] = var.get()
                except Exception:
                    pass
        if hasattr(self, "_sp_text_widget"):
            cfg["system_prompt"] = self._sp_text_widget.get("1.0", "end-1c").strip()
        return cfg

    def _show_full_prompt(self):
        if not self._app:
            return
        try:
            text = self._app._system_prompt(self._pending_cfg())
        except Exception as e:
            text = f"Error construyendo las instrucciones: {e}"
        win = tk.Toplevel(self)
        win.title("Instrucciones completas que recibe la IA")
        win.configure(bg=self.C["bg"])
        win.geometry("820x640")
        bar = tk.Frame(win, bg=self.C["deep"])
        bar.pack(fill='x')
        tk.Label(bar, text=f"📝  {len(text):,} caracteres  ·  se regeneran en cada mensaje (fecha, memoria, recordatorios)".replace(",", "."),
                 bg=self.C["deep"], fg=self.C["muted"], font=("Segoe UI", 9)).pack(side='left', padx=12, pady=8)
        def copy():
            win.clipboard_clear()
            win.clipboard_append(text)
        tk.Button(bar, text="⎘  Copiar", bg=self.C["accent"], fg="white", relief='flat',
                  cursor="hand2", command=copy).pack(side='right', padx=10, pady=6)
        fr = tk.Frame(win, bg=self.C["bg"])
        fr.pack(fill='both', expand=True)
        sb = tk.Scrollbar(fr)
        sb.pack(side='right', fill='y')
        t = tk.Text(fr, bg=self.C["panel"], fg=self.C["text"], font=("Consolas", 10),
                    wrap='word', relief='flat', padx=12, pady=10, yscrollcommand=sb.set)
        t.pack(fill='both', expand=True)
        sb.config(command=t.yview)
        t.insert("1.0", text)
        t.config(state='disabled')

    def _tab_orb(self, p):
        p.columnconfigure(1, weight=1)
        bf = ttk.LabelFrame(p, text="Orbe flotante", padding=12)
        bf.pack(fill='x', pady=8)
        bf.columnconfigure(1, weight=1)
        self._check(bf, "orb_visible",
                    "👁  Mostrar el orbe (mientras escucha, piensa o habla)", 0)
        self._check(bf, "orb_idle_visible",
                    "📌  Mantenerlo visible también en reposo (con la opacidad mínima)", 1)
        self._check(bf, "orb_show_loading",
                    "⏳  Mostrarlo mientras se cargan los modelos al iniciar", 2)
        self._lbl(bf, "Opacidad máxima:", 3)
        self._scale(bf, "orb_opacity",    3, frm=0.3, to=1.0,  res=0.05)
        self._lbl(bf, "Opacidad en reposo:", 4)
        self._scale(bf, "orb_opacity_min",4, frm=0.05, to=0.8, res=0.05)
        self._lbl(bf, "Tamaño (px):",     5)
        self._scale(bf, "orb_size",       5, frm=24, to=120,   res=4)

        cf = ttk.LabelFrame(p, text="🎨  Color de cada modo", padding=12)
        cf.pack(fill='x', pady=8)
        cf.columnconfigure(1, weight=1)
        modes = [("Escuchando (tu orden):",  "orb_color_listening"),
                 ("Pensando / herramientas:", "orb_color_thinking"),
                 ("Hablando (voz IA):",      "orb_color_speaking"),
                 ("Conversación continua:",   "orb_color_continuous"),
                 ("Cargando al iniciar:",     "orb_color_loading"),
                 ("En reposo:",               "orb_color_idle")]
        for i, (lbl, key) in enumerate(modes):
            self._lbl(cf, lbl, i)
            self._color_btn(cf, key, i)

        def preview():
            if self._app and self._app._orb:
                colors = {}
                for _lbl, key in modes:
                    try:
                        colors[key.replace("orb_color_", "")] = self._vars[key].get()
                    except Exception:
                        pass
                self._app._orb.preview_states(colors)
        def reset_colors():
            for _lbl, key in modes:
                if key in self._vars:
                    self._vars[key].set(DEFAULT_CONFIG[key])
        brow = tk.Frame(cf, bg=self.C["bg"])
        brow.grid(row=len(modes), column=0, columnspan=2, sticky='w', padx=8, pady=(8, 0))
        tk.Button(brow, text="▶  Probar colores en el orbe", bg=self.C["accent"], fg="white",
                  relief='flat', cursor="hand2", font=("Segoe UI", 9, "bold"), padx=10, pady=5,
                  command=preview).pack(side='left', padx=(0, 6))
        tk.Button(brow, text="↺  Colores por defecto", bg=self.C["deep"], fg=self.C["text"],
                  relief='flat', cursor="hand2", font=("Segoe UI", 9), padx=10, pady=5,
                  command=reset_colors).pack(side='left')

        pf = ttk.LabelFrame(p, text="Posición  (-1 y -1 = esquina inferior derecha)", padding=12)
        pf.pack(fill='x', pady=8)
        pf.columnconfigure(1, weight=1)
        self._lbl(pf, "X:", 0); self._entry(pf, "orb_x", 0, w=8)
        self._lbl(pf, "Y:", 1); self._entry(pf, "orb_y", 1, w=8)
        self._info(p, [
            "💡  Arrastra el orbe con el ratón — la posición se guarda automáticamente",
            "💡  Doble clic → escribir un mensaje · Clic derecho → menú rápido",
            "💡  Si lo ocultas, recupéralo desde la bandeja del sistema («Mostrar orbe»)",
            "💡  Los cambios de color, tamaño y posición se aplican al guardar, sin reiniciar",
        ])

    # ── Visión ────────────────────────────────────────────────────────────────
    def _tab_vision(self, p):
        p.columnconfigure(1, weight=1)
        C = self.C
        vf = ttk.LabelFrame(p, text="📸  Capturas de pantalla y cámara", padding=12)
        vf.pack(fill='x', pady=6)
        vf.columnconfigure(1, weight=1)
        self._check(vf, "vision_enabled",
                    "📸  Permitir que la IA vea tu pantalla y use la cámara (sin pedir confirmación)", 0)
        self._check(vf, "vision_hide_windows",
                    "🙈  Ocultar el orbe y el popup mientras se hace la captura de pantalla", 1)
        self._lbl(vf, "Cámara nº:", 2)
        self._entry(vf, "camera_index", 2, w=6)
        self._lbl(vf, "Tamaño máx. enviado (px):", 3)
        self._scale(vf, "vision_max_side", 3, frm=800, to=2400, res=100)
        self._lbl(vf, "Capturas a conservar:", 4)
        self._scale(vf, "captures_keep", 4, frm=5, to=200, res=5)

        status = tk.Label(vf, text="", bg=C["bg"], fg=C["muted"], font=("Segoe UI", 9), justify='left')
        status.grid(row=6, column=0, columnspan=2, sticky='w', padx=8, pady=(2, 4))

        def _set(msg, color=None):
            try:
                status.config(text=msg, fg=color or C["muted"])
            except Exception:
                pass

        def test_screen():
            _set("⏳  Capturando…")
            self.withdraw()
            def grab():
                try:
                    img, desc = capture_screen()
                    path = save_capture(img, "pantalla", 1000)
                    _set(f"✅  {desc}: {img.size[0]}×{img.size[1]} px → {path}", "#44ff88")
                    if path:
                        _open_path(path)
                except Exception as e:
                    _set(f"❌  {e}", "#ff5566")
                finally:
                    self.deiconify()
            self.after(350, grab)

        def test_camera():
            try:
                idx = int(float(self._vars["camera_index"].get()))
            except Exception:
                idx = 0
            _set(f"⏳  Abriendo la cámara nº {idx}…")
            def work():
                try:
                    img, desc = capture_camera(idx)
                    path = save_capture(img, "camara", 1000)
                    self._ui(lambda: _set(f"✅  {desc}: {img.size[0]}×{img.size[1]} px", "#44ff88"))
                    if path:
                        _open_path(path)
                except Exception as e:
                    msg = f"❌  {e}"
                    self._ui(lambda: _set(msg, "#ff5566"))
            threading.Thread(target=work, daemon=True).start()

        brow = tk.Frame(vf, bg=C["bg"])
        brow.grid(row=5, column=0, columnspan=2, sticky='w', padx=8, pady=(6, 2))
        for txt, cmd in (("🖥  Probar captura", test_screen), ("📷  Probar cámara", test_camera),
                         ("📂  Abrir carpeta de capturas",
                          lambda: (CAPTURES_DIR.mkdir(parents=True, exist_ok=True), _open_path(CAPTURES_DIR)))):
            tk.Button(brow, text=txt, bg=C["deep"], fg=C["text"], relief='flat', cursor="hand2",
                      font=("Segoe UI", 9), padx=10, pady=5, command=cmd).pack(side='left', padx=(0, 6))

        mf = ttk.LabelFrame(p, text="🧠  Modelo que analiza las imágenes", padding=12)
        mf.pack(fill='x', pady=6)
        mf.columnconfigure(1, weight=1)
        self._lbl(mf, "Modelo de visión:", 0)
        vm = self._v("vision_model")
        vcb = ttk.Combobox(mf, textvariable=vm, width=30, font=("Segoe UI", 10))
        vcb.grid(row=0, column=1, sticky='ew', padx=8, pady=5)
        caps_lbl = tk.Label(mf, text="", bg=C["bg"], fg=C["muted"], font=("Segoe UI", 9), justify='left')
        caps_lbl.grid(row=2, column=0, columnspan=2, sticky='w', padx=8, pady=2)

        def detect(host: str, main: str):
            try:
                r = requests.get(f"{host}/api/tags", timeout=5)
                names = [m["name"] for m in r.json().get("models", [])]
                vision = [n for n in names if "vision" in (ollama_capabilities(host, n) or set())]
                self._ui(lambda: vcb.configure(values=[""] + vision))
                caps = ollama_capabilities(host, main)
                if main and names and main not in names and not is_cloud_model(main):
                    msg, col = (f"⚠️  Tu modelo principal «{main}» no está instalado en Ollama "
                                f"(ollama pull {main}).", "#ffaa44")
                elif caps is None:
                    msg, col = f"ℹ️  No se pudo saber si «{main}» admite imágenes.", C["muted"]
                elif "vision" in caps:
                    msg, col = (f"✅  Tu modelo principal «{main}» admite imágenes: puedes dejar "
                                f"el campo vacío.", "#44ff88")
                else:
                    msg, col = (f"⚠️  «{main}» NO admite imágenes: elige un modelo de visión "
                                f"({', '.join(vision[:4]) or 'p.ej. gemma3:4b, qwen2.5vl:3b'}).", "#ffaa44")
                self._ui(lambda: caps_lbl.config(text=msg, fg=col))
            except Exception as e:
                err = f"❌  {e}"
                self._ui(lambda: caps_lbl.config(text=err, fg="#ff5566"))
        def start_detect():
            # Los valores de la interfaz se leen aquí (hilo principal), no en el hilo
            caps_lbl.config(text="⏳  Consultando Ollama…", fg=C["muted"])
            threading.Thread(target=detect, daemon=True,
                             args=(self._var_value("ollama_host"),
                                   self._var_value("ollama_model"))).start()
        tk.Button(mf, text="🔄  Detectar modelos con visión", bg=C["deep"], fg="white",
                  relief='flat', cursor="hand2", font=("Segoe UI", 9), padx=10, pady=5,
                  command=start_detect
                  ).grid(row=1, column=0, columnspan=2, sticky='w', padx=8, pady=4)
        start_detect()

        self._info(p, [
            "ℹ️  Vacío = las imágenes las analiza tu modelo principal (si admite visión).",
            "ℹ️  Si eliges otro modelo, ese modelo describe la imagen y tu modelo principal responde.",
            "🔒  Con modelos «cloud» las imágenes se envían a los servidores de Ollama. Para que no",
            "     salgan de tu PC, elige aquí un modelo local con visión (p.ej. gemma4:12b).",
            "ℹ️  Las capturas se guardan en la carpeta «capturas» de los datos de Rubencho AI",
            "     (General → Abrir la carpeta de datos). Se borran las más antiguas.",
            "ℹ️  La IA usa <CAPTURA/> para la pantalla y <CAMARA/> para la webcam.",
        ])

    # ── Control del PC ────────────────────────────────────────────────────────
    def _tab_pc(self, p):
        C = self.C
        top = ttk.LabelFrame(p, text="🖱  Control del ordenador", padding=12)
        top.pack(fill='x', pady=6)
        top.columnconfigure(1, weight=1)
        self._check(top, "pc_control_enabled",
                    "🖱  Permitir que la IA use el ratón y el teclado (clics, escribir, teclas, arrastrar…)", 0)
        ok_input, ok_uia = HAS_PC_INPUT, uia_available()
        if ok_input and ok_uia:
            st, col = "✅  Todo listo. También se puede activar o desactivar desde el icono de la bandeja.", "#44ff88"
        elif not IS_WINDOWS:
            st, col = "⚠️  El control del PC solo funciona en Windows.", "#ffaa44"
        elif not ok_input:
            st, col = "⚠️  Falta la librería pynput:  pip install pynput", "#ffaa44"
        else:
            st, col = ("⚠️  Falta comtypes (pip install comtypes): no se podrán leer los elementos "
                       "de las ventanas; solo la cuadrícula.", "#ffaa44")
        tk.Label(top, text=st, bg=C["bg"], fg=col, font=("Segoe UI", 9), justify='left',
                 wraplength=640).grid(row=1, column=0, columnspan=2, sticky='w', padx=8, pady=(0, 4))

        how = ttk.LabelFrame(p, text="🔎  Cómo localiza las cosas en la pantalla", padding=12)
        how.pack(fill='x', pady=6)
        how.columnconfigure(1, weight=1)
        self._check(how, "pc_use_elements",
                    "🔢  Numerar los elementos de las ventanas: botones, campos, menús… (recomendado)", 0)
        self._check(how, "pc_use_grid",
                    "▦  Dibujar una cuadrícula para lo que no tiene elementos (juegos, imágenes, mapas…)", 1)
        self._check(how, "pc_verify",
                    "📸  Hacer una captura después de cada acción para comprobar el resultado", 2)
        self._lbl(how, "Resolución enviada a la IA (px de ancho):", 3)
        self._scale(how, "pc_image_width", 3, frm=960, to=1920, res=160)

        status = tk.Label(how, text="", bg=C["bg"], fg=C["muted"], font=("Segoe UI", 9),
                          justify='left', wraplength=640)
        status.grid(row=5, column=0, columnspan=2, sticky='w', padx=8, pady=(2, 4))

        def preview():
            cfg = dict(self._cfg)
            for k in ("pc_use_elements", "pc_use_grid", "pc_image_width"):
                cfg[k] = self._var_value(k)
            try:
                cfg["pc_image_width"] = int(float(cfg["pc_image_width"]))
            except Exception:
                cfg["pc_image_width"] = 1280
            status.config(text="⏳  Mirando la pantalla como la IA… (esta ventana se oculta un momento)",
                          fg=C["muted"])
            self.withdraw()

            def work():
                try:
                    path, summary = pc_preview(cfg)
                    msg, colr = f"✅  {summary}. Imagen: {path}", "#44ff88"
                    if path:
                        _open_path(path)
                except Exception as e:
                    msg, colr = f"❌  {e}", "#ff5566"
                self._ui(lambda: (self.deiconify(), status.config(text=msg, fg=colr)))
            self.after(450, lambda: threading.Thread(target=work, daemon=True).start())
        tk.Button(how, text="👁  Ver lo que ve la IA (prueba)", bg=C["deep"], fg=C["text"],
                  relief='flat', cursor="hand2", font=("Segoe UI", 9), padx=10, pady=5,
                  command=preview).grid(row=4, column=0, columnspan=2, sticky='w', padx=8, pady=(6, 2))

        safe = ttk.LabelFrame(p, text="🛡  Precauciones", padding=12)
        safe.pack(fill='x', pady=6)
        safe.columnconfigure(1, weight=1)
        self._check(safe, "pc_confirm_dangerous",
                    "✋  Pedirme confirmación antes de acciones peligrosas (borrar, enviar, comprar, pagar…)", 0)
        self._check(safe, "pc_stop_hotkey_enabled",
                    "⛔  Freno de emergencia con una tecla", 1)
        self._lbl(safe, "      Tecla de parada (esc, f10, f12…):", 2)
        self._entry(safe, "pc_stop_hotkey", 2, w=10)
        self._check(safe, "pc_stop_corner",
                    "↖️  Freno de emergencia al llevar el ratón a una esquina de la pantalla", 3)
        self._check(safe, "pc_stop_on_user_mouse",
                    "🖐  Detener en cuanto muevas el ratón mientras la IA trabaja", 4)
        self._check(safe, "pc_block_fullscreen",
                    "🎮  No actuar si hay un juego o una app a pantalla completa", 5)
        self._check(safe, "pc_show_banner",
                    "🪧  Mostrar un aviso arriba de la pantalla mientras la IA controla el PC", 6)
        self._lbl(safe, "Límite de pasos por orden:", 7)
        self._scale(safe, "pc_max_steps", 7, frm=5, to=60, res=1)
        self._lbl(safe, "Pausa tras cada acción (s):", 8)
        self._scale(safe, "pc_action_delay", 8, frm=0.2, to=3.0, res=0.1)

        self._info(p, [
            "ℹ️  Pídeselo con normalidad: «abre el bloc de notas y escribe…», «pon música en Spotify»,",
            "     «cierra todas las pestañas de Chrome menos esta», «mueve este archivo a la papelera»…",
            "ℹ️  La IA ve la pantalla donde está el ratón. El orbe, el popup y los avisos de Rubencho no",
            "     salen en sus capturas y los clics los atraviesan mientras trabaja.",
            "ℹ️  Freno de emergencia: la tecla (por defecto ESC), el ratón a una esquina o",
            "     «⛔ Detener el control del PC» en el menú de la bandeja.",
            "🔒  Con modelos «cloud» las capturas se envían a los servidores de Ollama.",
            "ℹ️  Las capturas que ve la IA se guardan en la carpeta «capturas» (control_*.jpg).",
        ])

    # ── Memoria ───────────────────────────────────────────────────────────────
    def _tab_memory(self, p):
        C = self.C
        store = self._app._memory if self._app else MemoryStore()
        lf = ttk.LabelFrame(p, text="🧠  Memoria persistente de la IA", padding=12)
        lf.pack(fill='x', pady=6)
        lf.columnconfigure(1, weight=1)
        self._check(lf, "memory_enabled", "🧠  Activar la memoria a largo plazo", 0)
        tk.Label(lf, text=("La IA guarda aquí lo importante (solo si lo ve necesario) y puede añadir,\n"
                           "modificar o borrar datos en cualquier momento. Se le envía en cada mensaje.\n"
                           "También puedes gestionarla tú: los cambios se guardan al momento."),
                 bg=C["bg"], fg=C["muted"], font=("Segoe UI", 8), justify='left'
                 ).grid(row=1, column=0, columnspan=2, sticky='w', padx=8, pady=(0, 4))

        lst = tk.Frame(p, bg=C["bg"])
        lst.pack(fill='both', expand=True, pady=4)
        tree = ttk.Treeview(lst, columns=("id", "texto"), show="headings", height=12, selectmode="browse")
        tree.heading("id", text="#")
        tree.heading("texto", text="Dato guardado")
        tree.column("id", width=50, minwidth=40, stretch=False, anchor="center")
        tree.column("texto", width=560, stretch=True)
        sb = tk.Scrollbar(lst, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=sb.set)
        tree.pack(side='left', fill='both', expand=True)
        sb.pack(side='right', fill='y')
        count = tk.Label(p, text="", bg=C["bg"], fg=C["muted"], font=("Segoe UI", 8))

        def refresh():
            tree.delete(*tree.get_children())
            items = store.all()
            for e in items:
                tree.insert("", "end", iid=str(e["id"]), values=(e["id"], e["texto"]))
            count.config(text=f"{len(items)} dato(s) guardado(s)  ·  {MEMORY_FILE}")

        def selected_id():
            sel = tree.selection()
            return int(sel[0]) if sel else None

        def add():
            txt = simpledialog.askstring("Añadir a la memoria", "Dato que debe recordar la IA:",
                                         parent=self)
            if txt and txt.strip():
                store.add(txt)
                refresh()

        def edit(_e=None):
            mid = selected_id()
            if mid is None:
                return
            cur = next((e["texto"] for e in store.all() if e["id"] == mid), "")
            txt = simpledialog.askstring("Editar dato", f"Dato #{mid}:", initialvalue=cur, parent=self)
            if txt and txt.strip():
                store.edit(mid, txt)
                refresh()

        def delete():
            mid = selected_id()
            if mid is not None and messagebox.askyesno("Borrar", f"¿Borrar el dato #{mid}?", parent=self):
                store.delete(mid)
                refresh()

        def clear():
            if messagebox.askyesno("Borrar toda la memoria",
                                   "¿Seguro que quieres borrar TODA la memoria de la IA?", parent=self):
                store.clear()
                refresh()

        tree.bind("<Double-1>", edit)
        bar = tk.Frame(p, bg=C["bg"])
        bar.pack(fill='x', pady=4)
        for txt, cmd in (("➕  Añadir", add), ("✏️  Editar", edit), ("🗑  Borrar", delete),
                         ("🧹  Borrar todo", clear), ("🔄  Actualizar", refresh)):
            tk.Button(bar, text=txt, bg=C["deep"], fg=C["text"], relief='flat', cursor="hand2",
                      font=("Segoe UI", 9), padx=10, pady=5, command=cmd).pack(side='left', padx=(0, 6))
        count.pack(anchor='w', pady=(2, 0))
        refresh()

    # ── Recordatorios ─────────────────────────────────────────────────────────
    def _pending_list(self, p, store, new_title="Nuevo recordatorio", text_label="Texto:",
                      text_col="Texto"):
        """Lista de pendientes con «Nuevo», «Borrar» y «Actualizar» (recordatorios y tareas)."""
        C = self.C
        tk.Label(p, text="Pendientes", bg=C["bg"], fg=C["accent"],
                 font=("Segoe UI", 10, "bold")).pack(anchor='w', pady=(10, 2))
        lst = tk.Frame(p, bg=C["bg"])
        lst.pack(fill='both', expand=True)
        tree = ttk.Treeview(lst, columns=("id", "cuando", "repetir", "texto"), show="headings",
                            height=9, selectmode="browse")
        for col, title, w, st in (("id", "#", 46, False), ("cuando", "Cuándo", 215, False),
                                  ("repetir", "Repetir", 110, False), ("texto", text_col, 320, True)):
            tree.heading(col, text=title)
            tree.column(col, width=w, minwidth=40, stretch=st, anchor="center" if col == "id" else "w")
        sb = tk.Scrollbar(lst, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=sb.set)
        tree.pack(side='left', fill='both', expand=True)
        sb.pack(side='right', fill='y')

        def refresh():
            tree.delete(*tree.get_children())
            now = datetime.now()
            for r in store.pending():
                when = datetime.fromisoformat(r["cuando"])
                tree.insert("", "end", iid=str(r["id"]), values=(
                    r["id"], f"{fecha_corta(when, now)}  (en {duracion_humana(when - now)})",
                    REPEAT_LABELS.get(r.get("repetir", ""), ""), r["texto"]))

        def delete():
            sel = tree.selection()
            if sel and messagebox.askyesno("Borrar", f"¿Borrar {store.NOUN} #{sel[0]}?", parent=self):
                store.delete(int(sel[0]))
                refresh()

        def new():
            dlg = tk.Toplevel(self)
            dlg.title(new_title)
            dlg.configure(bg=C["bg"])
            dlg.transient(self)
            dlg.resizable(False, False)
            frm = tk.Frame(dlg, bg=C["bg"], padx=16, pady=12)
            frm.pack(fill='both', expand=True)
            vals = {}
            for i, (lbl, key, default) in enumerate(((text_label, "texto", ""),
                                                     ("Cuándo:", "cuando", "mañana 9:00"))):
                tk.Label(frm, text=lbl, bg=C["bg"], fg=C["text"], font=("Segoe UI", 10)
                         ).grid(row=i, column=0, sticky='w', pady=4)
                v = tk.StringVar(value=default)
                tk.Entry(frm, textvariable=v, width=36, bg=C["panel"], fg=C["text"],
                         insertbackground=C["accent"], relief='flat', font=("Segoe UI", 10)
                         ).grid(row=i, column=1, sticky='ew', padx=8, pady=4)
                vals[key] = v
            tk.Label(frm, text="Repetir:", bg=C["bg"], fg=C["text"], font=("Segoe UI", 10)
                     ).grid(row=2, column=0, sticky='w', pady=4)
            rep = tk.StringVar(value="una vez")
            ttk.Combobox(frm, textvariable=rep, state='readonly', width=20,
                         values=[REPEAT_LABELS[k] for k in ("", "diario", "laborables",
                                                            "semanal", "mensual", "anual")]
                         ).grid(row=2, column=1, sticky='w', padx=8, pady=4)
            msg = tk.Label(frm, text="Ejemplos: +10m · en 2 horas · hoy 18:30 · viernes 17:00 · 24/12 20:00",
                           bg=C["bg"], fg=C["muted"], font=("Segoe UI", 8))
            msg.grid(row=3, column=0, columnspan=2, sticky='w', pady=(4, 8))

            def create():
                try:
                    when = parse_when(vals["cuando"].get())
                    rkey = next(k for k, v in REPEAT_LABELS.items() if v == rep.get())
                    texto = vals["texto"].get().strip() or store.DEFAULT_TEXT
                    if not texto:
                        raise ValueError("escribe qué tiene que hacer")
                    store.add(texto, when, rkey)
                    refresh()
                    dlg.destroy()
                except ValueError as e:
                    msg.config(text=f"❌  {e}", fg="#ff5566")
            tk.Button(frm, text="Crear", bg=C["accent"], fg="white", relief='flat', cursor="hand2",
                      font=("Segoe UI", 10, "bold"), padx=16, pady=4, command=create
                      ).grid(row=4, column=1, sticky='e', padx=8)
            dlg.bind("<Return>", lambda _e: create())
            dlg.grab_set()

        bar = tk.Frame(p, bg=C["bg"])
        bar.pack(fill='x', pady=4)
        for txt, cmd in (("➕  Nuevo", new), ("🗑  Borrar", delete), ("🔄  Actualizar", refresh)):
            tk.Button(bar, text=txt, bg=C["deep"], fg=C["text"], relief='flat', cursor="hand2",
                      font=("Segoe UI", 9), padx=10, pady=5, command=cmd).pack(side='left', padx=(0, 6))
        refresh()

    def _tab_ai_tasks(self, p):
        store = self._app._ai_tasks if self._app else AITaskStore()
        of = ttk.LabelFrame(p, text="🤖  Tareas que la IA se programa a sí misma", padding=12)
        of.pack(fill='x', pady=6)
        of.columnconfigure(1, weight=1)
        self._check(of, "ai_tasks_enabled",
                    "🤖  Permitir que la IA se programe tareas para hacerlas más tarde", 0)
        self._check(of, "ai_tasks_whatsapp",
                    "📱  Mandarme por WhatsApp lo que ha hecho (si la integración está activa)", 1)
        self._check(of, "ai_tasks_confirm",
                    "✋  Pedir confirmación en el PC antes de enviar un WhatsApp desde una tarea", 2)
        tk.Label(of, text=("Con la confirmación, si no estás delante para aceptarla, el mensaje no se envía.\n"
                           "Sin ella se envía solo (se lo pediste al programarla), y solo a los contactos "
                           "permitidos en WhatsApp."),
                 bg=self.C["bg"], fg=self.C["muted"], font=("Segoe UI", 8), justify='left'
                 ).grid(row=3, column=0, columnspan=2, sticky='w', padx=8, pady=(0, 4))
        self._pending_list(p, store, new_title="Nueva tarea para la IA",
                           text_label="Qué tiene que hacer:", text_col="Qué tiene que hacer")
        self._info(p, [
            "💡  Ejemplo: «mañana a las 8 mándale a mi padre que llego a las 3». A las 8 la IA",
            "      recibe la tarea y envía el WhatsApp ella sola, aunque no estés delante del PC.",
            "💡  Los recordatorios te avisan a ti; las tareas las hace la IA.",
            "💡  Si Rubencho estaba cerrado a esa hora, la hace al abrirse (o explica por qué ya no).",
        ])

    def _tab_reminders(self, p):
        C = self.C
        store = self._app._reminders if self._app else ReminderStore()
        of = ttk.LabelFrame(p, text="⏰  Recordatorios y alarmas", padding=12)
        of.pack(fill='x', pady=6)
        of.columnconfigure(1, weight=1)
        self._check(of, "reminders_enabled", "⏰  Permitir que la IA cree recordatorios", 0)
        self._check(of, "reminder_sound", "🔔  Sonar al llegar la hora", 1)
        self._lbl(of, "Repeticiones del sonido:", 2)
        self._scale(of, "reminder_sound_repeats", 2, frm=1, to=10, res=1)
        self._lbl(of, "Sonido propio (.wav/.mp3):", 3)
        sfv = self._entry(of, "reminder_sound_file", 3, w=30)
        def browse():
            f = filedialog.askopenfilename(parent=self, filetypes=[("Audio", "*.wav *.mp3 *.ogg"),
                                                                   ("Todos", "*.*")])
            if f:
                sfv.set(f)
        tk.Button(of, text="📁", bg=C["deep"], fg="white", relief='flat', cursor="hand2",
                  command=browse).grid(row=3, column=2, padx=4)
        self._check(of, "reminder_tts", "🗣  Leer el recordatorio en voz alta", 4)
        self._check(of, "reminder_whatsapp",
                    "📱  Enviármelo también por WhatsApp (si la integración está activa)", 5)
        self._lbl(of, "Posponer (minutos):", 6)
        self._scale(of, "reminder_snooze_minutes", 6, frm=1, to=60, res=1)

        def test_sound():
            path = sfv.get().strip() or "recordatorio"
            threading.Thread(target=play_sound, args=(path, True), daemon=True).start()
        def test_notify():
            if self._app:
                self._app._ui_q.put(("reminder_test", None))
        brow = tk.Frame(of, bg=C["bg"])
        brow.grid(row=7, column=0, columnspan=3, sticky='w', padx=8, pady=(6, 0))
        for txt, cmd in (("🔔  Probar sonido", test_sound), ("🪟  Probar aviso completo", test_notify)):
            tk.Button(brow, text=txt, bg=C["deep"], fg=C["text"], relief='flat', cursor="hand2",
                      font=("Segoe UI", 9), padx=10, pady=5, command=cmd).pack(side='left', padx=(0, 6))

        self._pending_list(p, store)
        self._info(p, [
            "🗣  Pídeselo a la IA: «recuérdame en 20 minutos que saque la ropa»,",
            "     «despiértame mañana a las 7:30», «cada día a las 22:00 recuérdame la pastilla».",
            "ℹ️  Si el PC estaba apagado a la hora del aviso, suena al volver a abrir Rubencho AI.",
            f"ℹ️  Se guardan en {REMINDERS_FILE}",
        ])

    def _tab_popup(self, p):
        p.columnconfigure(1, weight=1)
        cf = ttk.LabelFrame(p, text="Colores", padding=12)
        cf.pack(fill='x', pady=8)
        cf.columnconfigure(1, weight=1)
        for i,(lbl,key) in enumerate([
            ("Fondo:",   "popup_bg"),
            ("Texto:",   "popup_text_color"),
            ("Acento:",  "popup_accent"),
        ]):
            self._lbl(cf, lbl, i)
            self._color_btn(cf, key, i)
        self._lbl(cf, "Opacidad:", 3)
        self._scale(cf, "popup_opacity", 3, frm=0.3, to=1.0, res=0.05)
        sf = ttk.LabelFrame(p, text="Tamaño, posición y tiempo", padding=12)
        sf.pack(fill='x', pady=8)
        sf.columnconfigure(1, weight=1)
        for i,(lbl,key,frm,to,res) in enumerate([
            ("Ancho (px):",      "popup_width",     280, 900, 10),
            ("Alto (px):",       "popup_height",    180, 700, 10),
            ("Cierre auto (s):", "popup_auto_close",   0, 120,  5),
        ]):
            self._lbl(sf, lbl, i)
            self._scale(sf, key, i, frm=frm, to=to, res=res)
        tk.Label(sf, text="Cierre auto = 0 → el popup no se cierra solo. El contador empieza "
                          "cuando la respuesta termina y se pausa con el ratón encima.",
                 bg=self.C["bg"], fg=self.C["muted"], font=("Segoe UI", 8), justify='left'
                 ).grid(row=7, column=0, columnspan=2, sticky='w', padx=8, pady=(2, 0))
        self._lbl(sf, "Posición:", 3)
        pv = self._v("popup_position")
        ttk.Combobox(sf, textvariable=pv,
                     values=["center","top-right","top-left",
                             "bottom-right","bottom-left","custom"],
                     state='readonly', width=18
                     ).grid(row=3, column=1, sticky='w', padx=8, pady=5)
        for i,(lbl,key) in enumerate([("X custom:","popup_custom_x"),
                                       ("Y custom:","popup_custom_y")], start=4):
            self._lbl(sf, lbl, i)
            self._entry(sf, key, i, w=8)

        tf = ttk.LabelFrame(p, text="🔊  Cierre automático tras TTS", padding=12)
        tf.pack(fill='x', pady=8)
        tf.columnconfigure(1, weight=1)
        self._check(tf, "popup_close_on_tts_end",
                    "⏹️  Cerrar el popup cuando la IA termina de hablar", 0)
        self._lbl(tf, "Espera tras TTS (s):", 1)
        self._scale(tf, "popup_close_on_tts_end_delay", 1, frm=0, to=15, res=1)
        tk.Label(tf, text="Si el TTS está desactivado, el cierre automático usa el contador normal de arriba.",
                 bg=self.C["bg"], fg=self.C["muted"], font=("Segoe UI",8), justify='left'
                 ).grid(row=2, column=0, columnspan=2, sticky='w', padx=8, pady=2)

    def _tab_log(self, p):
        p.columnconfigure(1, weight=1)
        hf = ttk.LabelFrame(p, text="💬  Memoria de la conversación", padding=12)
        hf.pack(fill='x', pady=6)
        hf.columnconfigure(1, weight=1)
        self._check(hf, "conversation_memory",
                    "💬  Enviarle los mensajes anteriores de la conversación", 0)
        self._lbl(hf, "Mensajes anteriores que se le envían:", 1)
        self._scale(hf, "max_history_turns", 1, frm=0, to=100, res=1)
        tk.Label(hf, text=("Cada mensaje tuyo va con su respuesta. Los más antiguos se olvidan solos.\n"
                           "Cuantos más, más contexto tiene, pero más gasta y más tarda en responder."),
                 bg=self.C["bg"], fg=self.C["muted"], font=("Segoe UI", 8), justify='left'
                 ).grid(row=2, column=0, columnspan=2, sticky='w', padx=8, pady=(0, 4))
        self._lbl(hf, "Olvidar los de hace más de (horas):", 3)
        self._scale(hf, "history_max_hours", 3, frm=0, to=168, res=1)
        tk.Label(hf, text="0 = no olvidarlos por tiempo (solo cuenta el máximo de arriba).",
                 bg=self.C["bg"], fg=self.C["muted"], font=("Segoe UI", 8), justify='left'
                 ).grid(row=4, column=0, columnspan=2, sticky='w', padx=8, pady=(0, 2))

        lf = ttk.LabelFrame(p, text="📋  Registro de conversaciones (fichero .txt)", padding=12)
        lf.pack(fill='x', pady=6)
        lf.columnconfigure(1, weight=1)
        self._check(lf, "log_enabled",
                    "💾  Guardar las conversaciones en un fichero .txt", 0)
        self._check(lf, "log_load_as_memory",
                    "🧠  Al iniciar, recuperar del log los últimos mensajes  (recuerda días anteriores)", 1)
        tk.Label(lf, text="Solo se recuperan los últimos (el máximo de arriba), nunca el log entero.",
                 bg=self.C["bg"], fg=self.C["muted"], font=("Segoe UI",8), justify='left'
                 ).grid(row=2, column=0, columnspan=2, sticky='w', padx=8, pady=2)
        self._lbl(lf, "Conversaciones que se guardan:", 3)
        self._scale(lf, "log_max_entries", 3, frm=0, to=2000, res=50)
        tk.Label(lf, text="0 = guardarlas todas. Si pones un número, las más antiguas se borran solas.",
                 bg=self.C["bg"], fg=self.C["muted"], font=("Segoe UI",8), justify='left'
                 ).grid(row=4, column=0, columnspan=2, sticky='w', padx=8, pady=2)
        pf = ttk.LabelFrame(p, text="Ruta del fichero .txt", padding=12)
        pf.pack(fill='x', pady=6)
        pf.columnconfigure(1, weight=1)
        lp = self._entry(pf, "log_file_path", 0, w=34)
        def browse_log():
            f = filedialog.asksaveasfilename(
                parent=self, defaultextension=".txt",
                filetypes=[("Texto","*.txt"),("Todos","*.*")],
                initialfile="historial_conversaciones.txt")
            if f: lp.set(f)
        tk.Button(pf, text="📁", bg=self.C["deep"], fg="white",
                  relief='flat', cursor="hand2", command=browse_log
                  ).grid(row=0, column=2, padx=4)
        def open_log():
            path = self._vars["log_file_path"].get()
            if path and os.path.exists(path):
                os.startfile(path) if platform.system()=="Windows" else os.system(f"xdg-open '{path}'")
            else:
                messagebox.showwarning("Fichero no encontrado", "El fichero de log no existe aún.", parent=self)
        def clear_log():
            path = self._vars["log_file_path"].get()
            if path and os.path.exists(path):
                if messagebox.askyesno("Borrar log", "¿Borrar el contenido del log?", parent=self):
                    open(path,'w').close()
            else:
                messagebox.showinfo("Log", "No hay fichero de log.", parent=self)
        bf = tk.Frame(p, bg=self.C["bg"])
        bf.pack(fill='x', pady=4)
        for txt, cmd in [("📂  Abrir log", open_log), ("🗑  Borrar log", clear_log)]:
            tk.Button(bf, text=txt, bg=self.C["deep"], fg=self.C["text"],
                      relief='flat', cursor="hand2", font=("Segoe UI",9),
                      padx=12, pady=6, command=cmd).pack(side='left', padx=4)
        self._info(p, [
            "ℹ️  Formato del log:  fecha | tú dijiste → IA respondió",
            "ℹ️  El log es solo un registro: lo que se le envía a la IA lo decide «Memoria de la conversación»",
        ])

    def _tab_tts(self, p):
        p.columnconfigure(1, weight=1)
        ef = ttk.LabelFrame(p, text="🔊  Voz de la IA  (Text-to-Speech)", padding=12)
        ef.pack(fill='x', pady=6)
        ef.columnconfigure(1, weight=1)
        self._check(ef, "tts_enabled", "🔊  Leer la respuesta en voz alta", 0)
        self._lbl(ef, "Motor:", 1)
        tv = self._v("tts_engine")
        ttk.Combobox(ef, textvariable=tv,
                     values=["pyttsx3  (offline, sin internet)",
                             "gtts     (Google, requiere internet)"],
                     state='readonly', width=32
                     ).grid(row=1, column=1, sticky='w', padx=8, pady=5)
        self._lbl(ef, "Velocidad:", 2)
        self._scale(ef, "tts_rate",   2, frm=80,  to=300, res=10)
        self._lbl(ef, "Volumen:",     3)
        self._scale(ef, "tts_volume", 3, frm=0.1, to=1.0, res=0.05)
        self._check(ef, "text_input_tts",
                    "✍️  Leer también las respuestas a los mensajes escritos", 4)

        vf = ttk.LabelFrame(p, text="🎤  Voz del sistema  (solo pyttsx3)", padding=12)
        vf.pack(fill='x', pady=6)
        vf.columnconfigure(1, weight=1)
        self._voice_map: dict = {}
        cur_id  = self._cfg.get("tts_voice_id","")
        voice_v = tk.StringVar(value=cur_id)
        self._vars["tts_voice_id"] = voice_v
        voice_cb = ttk.Combobox(vf, state='readonly', width=42, font=("Segoe UI",9))
        voice_cb.grid(row=0, column=0, columnspan=2, sticky='ew', padx=8, pady=4)
        status_lbl = tk.Label(vf, text="Pulsa 'Detectar voces' para ver las disponibles",
                               bg=self.C["bg"], fg=self.C["muted"], font=("Segoe UI",8))
        status_lbl.grid(row=1, column=0, columnspan=2, sticky='w', padx=8)

        def on_voice_select(event=None):
            name = voice_cb.get()
            vid  = self._voice_map.get(name, "")
            voice_v.set(vid)
        voice_cb.bind("<<ComboboxSelected>>", on_voice_select)

        def _get_all_voices():
            import pyttsx3 as _p
            eng    = _p.init()
            voices = list(eng.getProperty("voices"))
            eng.stop()
            if platform.system() == "Windows":
                try:
                    import winreg
                    ONECORE_KEY = r"SOFTWARE\Microsoft\Speech_OneCore\Voices\Tokens"
                    seen_ids = {v.id for v in voices}
                    for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
                        try:
                            reg = winreg.OpenKey(hive, ONECORE_KEY)
                        except FileNotFoundError:
                            continue
                        i = 0
                        while True:
                            try:
                                token_name = winreg.EnumKey(reg, i); i += 1
                            except OSError:
                                break
                            token_path = ONECORE_KEY + "\\" + token_name
                            try:
                                tok      = winreg.OpenKey(hive, token_path)
                                name_val = winreg.QueryValue(tok, "")
                                full_id  = (f"HKEY_LOCAL_MACHINE\\{token_path}"
                                            if hive == winreg.HKEY_LOCAL_MACHINE
                                            else f"HKEY_CURRENT_USER\\{token_path}")
                                if full_id in seen_ids:
                                    continue
                                seen_ids.add(full_id)
                                class _FakeVoice: pass
                                fv = _FakeVoice()
                                fv.id   = full_id
                                fv.name = name_val or token_name
                                fv.languages = []; fv.age = ""; fv.gender = ""
                                try:
                                    attr = winreg.OpenKey(hive, token_path + "\\Attributes")
                                    for aname in ("Language","Gender","Age"):
                                        try:
                                            val, _ = winreg.QueryValueEx(attr, aname)
                                            if aname == "Language": fv.languages = [val]
                                            elif aname == "Gender": fv.gender = val
                                            elif aname == "Age":    fv.age = val
                                        except Exception: pass
                                except Exception: pass
                                voices.append(fv)
                            except Exception: pass
                except Exception as e:
                    print(f"[TTS] OneCore scan error: {e}")
            return voices

        def detect_voices():                     # hilo secundario
            try:
                voices, err = _get_all_voices(), None
            except ImportError:
                voices, err = None, "❌  pyttsx3 no instalado: pip install pyttsx3"
            except Exception as e:
                voices, err = None, f"❌  Error: {e}"
            self._ui(lambda: _fill_voices(voices, err))

        def _fill_voices(voices, err):             # hilo de la interfaz
            if err:
                status_lbl.config(text=err, fg="#ff5566")
                return
            try:
                self._voice_map.clear()
                names = []; cur_name = ""
                FEMALE_NAMES = {"zira","helena","sabina","laura","lucia","eva","monica","paula","maria","rosa"}
                MALE_NAMES   = {"david","mark","pablo","jorge","carlos","antonio","miguel","juan","pedro","raul"}
                for v in voices:
                    lang = ""
                    if getattr(v,"languages",[]):
                        try:
                            raw = v.languages[0]
                            lang = raw.decode() if isinstance(raw, bytes) else str(raw)
                            try:
                                import locale
                                code = int(lang, 16)
                                lang = locale.windows_locale.get(code, lang)
                            except Exception: pass
                        except Exception: pass
                    gender_attr = getattr(v, "gender", "").lower()
                    vname_low   = v.name.lower()
                    if gender_attr == "female" or any(x in vname_low for x in FEMALE_NAMES):
                        gender = " ♀"
                    elif gender_attr == "male" or any(x in vname_low for x in MALE_NAMES):
                        gender = " ♂"
                    else:
                        gender = ""
                    onecore = " [OneCore]" if "Speech_OneCore" in str(v.id) else ""
                    display = f"{v.name}{gender}{onecore}  {lang}".strip()
                    self._voice_map[display] = v.id
                    names.append(display)
                    if v.id == cur_id:
                        cur_name = display
                voice_cb["values"] = names
                if cur_name:   voice_cb.set(cur_name)
                elif names:    voice_cb.set(names[0]); voice_v.set(self._voice_map[names[0]])
                n_oc = sum(1 for n in names if "OneCore" in n)
                status_lbl.config(text=f"✅  {len(names)} voces  ({n_oc} OneCore)  —  ♂ masc  ♀ fem", fg="#44ff88")
            except Exception as e:
                status_lbl.config(text=f"❌  Error: {e}", fg="#ff5566")

        tk.Button(vf, text="🔍  Detectar voces",
                  bg=self.C["deep"], fg="white", relief='flat', cursor="hand2",
                  font=("Segoe UI",9), padx=10, pady=5,
                  command=lambda: (status_lbl.config(text="⏳  Detectando voces (incluyendo OneCore)...",
                                                     fg=self.C["muted"]),
                                   threading.Thread(target=detect_voices, daemon=True).start())
                  ).grid(row=2, column=0, sticky='w', padx=8, pady=6)

        def test_tts():
            engine_raw = self._vars.get("tts_engine", tv).get()
            engine     = "gtts" if "gtts" in engine_raw else "pyttsx3"
            rate       = float(self._vars["tts_rate"].get())
            vol        = float(self._vars["tts_volume"].get())
            vid        = voice_v.get()
            threading.Thread(
                target=speak,
                args=("Hola, soy tu asistente de voz Rubencho AI.", engine, rate, vol, vid),
                daemon=True).start()

        tk.Button(vf, text="🔊  Probar voz seleccionada",
                  bg=self.C["accent"], fg="white", relief='flat', cursor="hand2",
                  font=("Segoe UI",9,"bold"), padx=12, pady=5, command=test_tts
                  ).grid(row=2, column=1, sticky='w', padx=8, pady=6)

        self._info(p, [
            "ℹ️  pyttsx3 usa las voces instaladas en tu sistema operativo",
            "ℹ️  Windows: Panel de control → Voz → instalar paquetes de idioma adicionales",
            "ℹ️  Las voces ♂ masculinas suelen llevar nombres como 'David' o 'Pablo'",
            "ℹ️  gtts siempre usa la voz de Google — no permite elegir género",
        ])

    def _tab_whatsapp(self, p):
        p.columnconfigure(1, weight=1)

        # ── Activar integración ───────────────────────────────────────────────
        mf = ttk.LabelFrame(p, text="📱  Integración WhatsApp (Baileys)", padding=12)
        mf.pack(fill='x', pady=6)
        mf.columnconfigure(1, weight=1)
        self._check(mf, "whatsapp_enabled",
                    "✅  Activar integración WhatsApp", 0)
        self._check(mf, "whatsapp_bridge_autostart",
                    "🚀  Arrancar el bridge automáticamente al iniciar", 1)
        self._check(mf, "whatsapp_notify_self",
                    "🔔  Permitir mandarte notas a ti mismo por WhatsApp", 2)
        self._check(mf, "whatsapp_self_reply",
                    "💬  Responder a lo que me escribo en mi chat propio de WhatsApp", 3)
        self._check(mf, "whatsapp_self_popup",
                    "🪟  …y mostrar en el PC lo que me contesta ahí (panel)", 4)
        self._check(mf, "whatsapp_self_trigger",
                    "🏷  …solo si le llamo por una de estas palabras (también en audios):", 5)
        self._lbl(mf, "      Palabras (separadas por comas):", 6)
        self._entry(mf, "whatsapp_self_trigger_words", 6, w=30)
        tk.Label(mf, text=("      Ej.: «asistente, rubencho». Si el mensaje no lleva ninguna, no contesta "
                           "aunque sea tu chat propio.\n      Da igual mayúsculas y tildes."),
                 bg=self.C["bg"], fg=self.C["muted"], font=("Segoe UI", 8), justify='left'
                 ).grid(row=7, column=0, columnspan=3, sticky='w', padx=8, pady=(0, 4))
        self._lbl(mf, "Puerto del bridge:", 8)
        self._entry(mf, "whatsapp_bridge_port", 8, w=8)

        # ── Estado del bridge ─────────────────────────────────────────────────
        sf = ttk.LabelFrame(p, text="📡  Estado de la conexión", padding=12)
        sf.pack(fill='x', pady=6)
        sf.columnconfigure(0, weight=1)
        status_lbl = tk.Label(sf, text="Pulsa 'Verificar estado' para comprobar",
                               bg=self.C["bg"], fg=self.C["muted"],
                               font=("Segoe UI", 9), anchor='w')
        status_lbl.pack(fill='x', padx=4, pady=(0, 6))

        def _get_port():
            try:
                return int(self._vars.get("whatsapp_bridge_port",
                           tk.StringVar(value="3847")).get())
            except Exception:
                return 3847

        def check_status():
            port = _get_port()
            st = wa_status(port=port)
            if st.get("connected"):
                me = st.get("self", "—")
                status_lbl.config(
                    text=f"✅  Conectado  |  Número: {me}",
                    fg="#44ff88")
            elif st.get("has_qr"):
                status_lbl.config(
                    text=f"📱  QR disponible — abre http://localhost:{port}/qr-page en el navegador",
                    fg="#ffaa00")
            elif "error" in st:
                status_lbl.config(
                    text=f"❌  Bridge no responde: {st['error']}",
                    fg="#ff5566")
            else:
                status_lbl.config(
                    text="⏳  Bridge activo pero WhatsApp no conectado todavía",
                    fg="#ffaa00")

        def open_qr_page():
            port = _get_port()
            import webbrowser
            webbrowser.open(f"http://localhost:{port}/qr-page")

        def start_bridge_manual():
            port = _get_port()
            status_lbl.config(text="⏳  Comprobando bridge…", fg=self.C["muted"])
            def set_status(text, color):
                self._ui(lambda: status_lbl.config(text=text, fg=color))
            def _do():
                # Primero comprobar si ya está corriendo
                st = wa_status(port=port)
                if st.get("connected") or st.get("has_qr") or (
                        "error" not in st and st != {"ok": False}):
                    # El bridge ya responde → no arrancar otro
                    if st.get("connected"):
                        set_status("✅  Bridge ya en marcha y WhatsApp conectado.", "#44ff88")
                    else:
                        set_status("✅  Bridge ya en marcha. Abre el QR para vincular.", "#44ff88")
                    return
                # No responde → arrancar
                proc = wa_start_bridge(port=port)
                time.sleep(2)
                if proc and proc.poll() is None:
                    set_status("✅  Bridge arrancado. Abre el QR para vincular.", "#44ff88")
                else:
                    set_status("❌  No se pudo arrancar. ¿Node.js instalado? ¿npm install hecho?",
                               "#ff5566")
            threading.Thread(target=_do, daemon=True).start()

        def show_contacts():
            port = _get_port()
            contacts = wa_contacts(port=port)
            if not contacts:
                messagebox.showinfo("Contactos WhatsApp",
                    "No hay contactos disponibles o WhatsApp no está conectado.",
                    parent=self)
                return
            lines = [f"{'Nombre':<28}  Número", "─" * 48]
            for c in contacts[:40]:
                lines.append(f"{c['name']:<28}  +{c['phone']}")
            if len(contacts) > 40:
                lines.append(f"… y {len(contacts)-40} más")
            messagebox.showinfo(
                f"Contactos WhatsApp ({len(contacts)})",
                "\n".join(lines),
                parent=self)

        def relink():
            if not messagebox.askyesno(
                    "Volver a vincular WhatsApp",
                    "Rubencho se desvinculará de tu WhatsApp y aparecerá un QR nuevo para "
                    "escanearlo desde el móvil (WhatsApp → Dispositivos vinculados → Vincular).\n\n"
                    "Al volver a vincular, WhatsApp le envía tu agenda de contactos y los mensajes "
                    "recientes de tus chats.\n\n¿Continuar?", parent=self):
                return
            port = _get_port()
            status_lbl.config(text="⏳  Desvinculando… en unos segundos se abrirá el QR", fg="#ffaa00")
            def _do():
                r = wa_relink(port=port)
                if not r.get("ok"):
                    self._ui(lambda: status_lbl.config(
                        text=f"❌  {r.get('error', 'El puente no responde')}", fg="#ff5566"))
                    return
                time.sleep(7)
                import webbrowser
                webbrowser.open(f"http://localhost:{port}/qr-page")
                self._ui(lambda: status_lbl.config(
                    text="📱  Escanea el QR con el móvil. Después pulsa «Actualizar contactos».",
                    fg="#ffaa00"))
            threading.Thread(target=_do, daemon=True).start()

        btn_row = tk.Frame(sf, bg=self.C["bg"])
        btn_row.pack(fill='x', pady=4)
        for btn_txt, btn_cmd in [
            ("🔍  Verificar estado",  check_status),
            ("📱  Abrir QR",          open_qr_page),
            ("▶️  Arrancar bridge",    start_bridge_manual),
            ("🔗  Volver a vincular", relink),
        ]:
            tk.Button(btn_row, text=btn_txt,
                      bg=self.C["deep"], fg=self.C["text"],
                      relief='flat', cursor="hand2",
                      font=("Segoe UI", 9), padx=10, pady=5,
                      command=btn_cmd).pack(side='left', padx=4, pady=4)

        # ── Contactos y mensajes ──────────────────────────────────────────────
        rf = ttk.LabelFrame(p, text="👥  Contactos y mensajes", padding=12)
        rf.pack(fill='x', pady=6)
        rf.columnconfigure(1, weight=1)
        self._check(rf, "whatsapp_read_enabled",
                    "📖  Permitir que lea mis mensajes cuando se lo pida", 0)
        self._check(rf, "whatsapp_read_images",
                    "📷  Que vea las fotos que me mandan", 1)
        self._check(rf, "whatsapp_read_audio",
                    "🎤  Que escuche los audios (los transcribe con Whisper)", 2)
        self._lbl(rf, "Máximo de mensajes que puede leer hacia atrás:", 3)
        self._scale(rf, "whatsapp_read_max", 3, frm=1, to=100, res=1)
        self._check(rf, "whatsapp_confirm_send",
                    "✋  Pedirme confirmación antes de enviar un mensaje", 4)
        self._check(rf, "whatsapp_send_all",
                    "👥  Permitir que escriba a TODOS mis contactos (si no, solo a los marcados abajo)", 5)
        tk.Label(rf, text="Los mensajes de los demás nunca le llegan solos a la IA: solo los lee cuando "
                          "tú se lo pides.\nSolo puede leer los mensajes recibidos mientras el puente de "
                          "WhatsApp está en marcha (se guardan en tu PC).",
                 bg=self.C["bg"], fg=self.C["muted"], font=("Segoe UI", 8), justify='left'
                 ).grid(row=6, column=0, columnspan=2, sticky='w', padx=8, pady=(2, 6))

        # Lista de contactos con la casilla «puede escribirle»
        allowed = set(self._cfg.get("whatsapp_allowed_contacts") or [])

        class _ListVar:
            def get(self_inner):
                return sorted(allowed)
        self._vars["whatsapp_allowed_contacts"] = _ListVar()

        top = tk.Frame(rf, bg=self.C["bg"])
        top.grid(row=7, column=0, columnspan=2, sticky='ew', padx=8, pady=(4, 2))
        tk.Label(top, text="🔎", bg=self.C["bg"], fg=self.C["muted"]).pack(side='left')
        search_v = tk.StringVar()
        tk.Entry(top, textvariable=search_v, bg=self.C["panel"], fg=self.C["text"],
                 font=("Segoe UI", 10), relief='flat', width=24,
                 insertbackground=self.C["accent"]).pack(side='left', padx=(4, 8))
        count_lbl = tk.Label(top, text="", bg=self.C["bg"], fg=self.C["muted"], font=("Segoe UI", 9))
        count_lbl.pack(side='left')

        tv_fr = tk.Frame(rf, bg=self.C["bg"])
        tv_fr.grid(row=8, column=0, columnspan=2, sticky='ew', padx=8, pady=2)
        tv = ttk.Treeview(tv_fr, columns=("ok", "name", "phone"), show="headings", height=9,
                          selectmode="browse")
        tv.heading("ok", text="Puede escribirle")
        tv.heading("name", text="Contacto")
        tv.heading("phone", text="Número")
        tv.column("ok", width=120, anchor='center', stretch=False)
        tv.column("name", width=260)
        tv.column("phone", width=140, stretch=False)
        sb = ttk.Scrollbar(tv_fr, orient="vertical", command=tv.yview)
        tv.configure(yscrollcommand=sb.set)
        tv.pack(side='left', fill='both', expand=True)
        sb.pack(side='right', fill='y')
        all_contacts = []

        def fill():
            q = _norm_text(search_v.get())
            tv.delete(*tv.get_children())
            shown = 0
            for c in all_contacts:
                if q and q not in _norm_text(c["name"]):
                    continue
                mark = "✅  Sí" if c["jid"] in allowed else "—"
                tv.insert("", "end", iid=c["jid"], values=(mark, c["name"], f"+{c['phone']}" if c.get("phone") else ""))
                shown += 1
            count_lbl.config(text=(f"{len(all_contacts)} contactos · {len(allowed)} permitidos"
                                   if all_contacts else "Sin contactos todavía"))
        search_v.trace_add("write", lambda *_: fill())

        def toggle(event=None):
            iid = tv.focus()
            if not iid:
                return
            if iid in allowed:
                allowed.discard(iid)
            else:
                allowed.add(iid)
            fill()
            try:
                tv.selection_set(iid)
                tv.focus(iid)
                tv.see(iid)
            except Exception:
                pass
        tv.bind("<Double-1>", toggle)
        tv.bind("<space>", toggle)
        tv.bind("<Return>", toggle)

        def load(refresh: bool = False):
            port = _get_port()
            count_lbl.config(text="⏳  " + ("Descargando la agenda de WhatsApp…" if refresh
                                          else "Cargando contactos…"))
            def work():
                if refresh:
                    wa_refresh_contacts(port=port)
                lst = wa_contacts(port=port)
                def done():
                    all_contacts[:] = [c for c in lst if c.get("name")]
                    fill()
                    if not lst:
                        st = wa_status(port=port)
                        count_lbl.config(text=(
                            "⚠️  WhatsApp no envía la agenda con esta vinculación: pulsa «Volver a vincular»"
                            if st.get("needs_relink") else
                            "Sin contactos: pulsa «Actualizar contactos»" if st.get("connected") else
                            "WhatsApp no está conectado"))
                self._ui(done)
            threading.Thread(target=work, daemon=True).start()

        def mark(all_on: bool):
            visible = tv.get_children()
            for iid in visible:
                (allowed.add if all_on else allowed.discard)(iid)
            fill()

        brow = tk.Frame(rf, bg=self.C["bg"])
        brow.grid(row=9, column=0, columnspan=2, sticky='w', padx=8, pady=(4, 2))
        for txt, cmd in (("✔  Permitir / quitar el seleccionado", toggle),
                         ("✅  Marcar los visibles", lambda: mark(True)),
                         ("—  Desmarcar los visibles", lambda: mark(False)),
                         ("🔄  Actualizar contactos", lambda: load(True))):
            tk.Button(brow, text=txt, bg=self.C["deep"], fg=self.C["text"], relief='flat',
                      cursor="hand2", font=("Segoe UI", 9), padx=8, pady=4,
                      command=cmd).pack(side='left', padx=(0, 6))
        tk.Label(rf, text="Doble clic (o Espacio) en un contacto para permitir o quitar. "
                          "Los cambios se aplican al pulsar Guardar.",
                 bg=self.C["bg"], fg=self.C["muted"], font=("Segoe UI", 8)
                 ).grid(row=10, column=0, columnspan=2, sticky='w', padx=8, pady=(0, 2))
        load()

        # ── Test de envío ─────────────────────────────────────────────────────
        tf = ttk.LabelFrame(p, text="✉️  Prueba de envío", padding=12)
        tf.pack(fill='x', pady=6)
        tf.columnconfigure(1, weight=1)

        ttk.Label(tf, text="Destinatario:").grid(
            row=0, column=0, sticky='w', padx=8, pady=4)
        dest_v = tk.StringVar(value="yo mismo")
        tk.Entry(tf, textvariable=dest_v,
                 bg=self.C["panel"], fg=self.C["text"],
                 font=("Segoe UI", 10), relief='flat', width=28,
                 insertbackground=self.C["accent"]
                 ).grid(row=0, column=1, sticky='ew', padx=8, pady=4)

        ttk.Label(tf, text="Mensaje:").grid(
            row=1, column=0, sticky='w', padx=8, pady=4)
        msg_v = tk.StringVar(
            value="✅ Rubencho AI conectado correctamente a WhatsApp")
        tk.Entry(tf, textvariable=msg_v,
                 bg=self.C["panel"], fg=self.C["text"],
                 font=("Segoe UI", 10), relief='flat', width=28,
                 insertbackground=self.C["accent"]
                 ).grid(row=1, column=1, sticky='ew', padx=8, pady=4)

        send_lbl = tk.Label(tf, text="", bg=self.C["bg"],
                             font=("Segoe UI", 9), anchor='w')
        send_lbl.grid(row=2, column=0, columnspan=2, sticky='w', padx=8, pady=4)

        def test_send():
            port = _get_port()
            dest = dest_v.get().strip()
            msg  = msg_v.get().strip()
            if not msg:
                send_lbl.config(text="❌  Escribe un mensaje primero.", fg="#ff5566")
                return
            send_lbl.config(text="⏳  Enviando…", fg=self.C["muted"])
            def _do():
                if dest.lower() in ("yo", "yo mismo", "self", "mi"):
                    res = wa_send_self(msg, port=port)
                else:
                    res = wa_send(dest, msg, port=port)
                self._ui(lambda: send_lbl.config(
                    text=res, fg="#44ff88" if res.startswith("✅") else "#ff5566"))
            threading.Thread(target=_do, daemon=True).start()

        tk.Button(tf, text="📤  Enviar prueba",
                  bg=self.C["accent"], fg="white",
                  relief='flat', cursor="hand2",
                  font=("Segoe UI", 9, "bold"), padx=12, pady=5,
                  command=test_send
                  ).grid(row=3, column=0, columnspan=2, sticky='w', padx=8, pady=6)

        # ── Instrucciones de instalación ──────────────────────────────────────
        self._info(p, [
            "📋  INSTALACIÓN DEL BRIDGE:",
            "1.  Instala Node.js 20+ desde https://nodejs.org",
            "2.  Copia whatsapp_bridge.js y package.json junto a Rubencho_AI.pyw",
            "3.  Abre una terminal en esa carpeta y ejecuta:  npm install",
            "4.  Activa la integración arriba y guarda la configuración",
            "5.  Al iniciar Rubencho AI, el bridge arrancará automáticamente",
            "6.  Ve a 'Abrir QR' y escanea el código con WhatsApp en tu móvil",
            "ℹ️  La sesión se guarda en la carpeta de datos, en whatsapp_session (no la borres)",
            "ℹ️  Pídele: «escríbele a Mamá que llego tarde», «¿qué me ha mandado Juan?»,",
            "     «resúmeme el audio de Ana», «léeme los últimos mensajes de Pedro»…",
        ])

    def _tab_ptt(self, p):
        """Pestaña Push-to-Talk: activa la escucha mientras mantienes una tecla."""
        p.columnconfigure(1, weight=1)
        C = self.C

        # ── Activar PTT ───────────────────────────────────────────────────────
        ef = ttk.LabelFrame(p, text="🎙  Push-to-Talk (PTT)", padding=12)
        ef.pack(fill='x', pady=8)
        self._check(ef, "ptt_enabled",
                    "Activar modo Push-to-Talk (mantén la tecla para hablar)", 0)
        self._check(ef, "ptt_no_continuous",
                    "Al soltar, volver al modo espera (sin conversación continua)", 1)

        # ── Configurar tecla ──────────────────────────────────────────────────
        kf = ttk.LabelFrame(p, text="⌨️  Tecla de activación", padding=12)
        kf.pack(fill='x', pady=8)
        kf.columnconfigure(1, weight=1)

        ttk.Label(kf, text="Tecla / Combinación:").grid(
            row=0, column=0, sticky='w', padx=8, pady=6)

        hotkey_var = self._v("ptt_hotkey")
        hotkey_entry = tk.Entry(
            kf, textvariable=hotkey_var,
            bg=C["panel"], fg=C["text"],
            font=("Segoe UI", 11, "bold"),
            relief='flat', width=20,
            insertbackground=C["accent"])
        hotkey_entry.grid(row=0, column=1, sticky='w', padx=8, pady=6)

        status_lbl = tk.Label(kf, text="", bg=C["bg"], fg=C["muted"],
                              font=("Segoe UI", 9))
        status_lbl.grid(row=1, column=0, columnspan=2, sticky='w', padx=8, pady=2)

        # ── Botón Capturar ────────────────────────────────────────────────────
        capture_state = {"active": False, "listener": None}

        def _stop_capture(clear_status: bool = False):
            capture_state["active"] = False
            if capture_state["listener"]:
                try:
                    capture_state["listener"].stop()
                except Exception:
                    pass
                capture_state["listener"] = None
            try:
                cap_btn.config(text="🎯  Capturar tecla")
                if clear_status:
                    status_lbl.config(text="")
            except Exception:
                pass

        def _start_capture():
            if not HAS_PYNPUT:
                status_lbl.config(
                    text="❌  Instala pynput y pyaudio: pip install pynput pyaudio",
                    fg="#ff5566")
                return
            if capture_state["active"]:
                _stop_capture(clear_status=True)
                return
            capture_state["active"] = True
            cap_btn.config(text="⏳  Esperando tecla…")
            status_lbl.config(text="Pulsa la tecla o combinación que quieras usar…",
                              fg=C["accent"])

            pressed_mods = set()
            main_pressed = [None]

            mod_names = {
                _pynput_kb.Key.ctrl_l:  "ctrl",
                _pynput_kb.Key.ctrl_r:  "ctrl",
                _pynput_kb.Key.shift_l: "shift",
                _pynput_kb.Key.shift_r: "shift",
                _pynput_kb.Key.alt_l:   "alt",
                _pynput_kb.Key.alt_r:   "alt",
                _pynput_kb.Key.cmd:     "win",
                _pynput_kb.Key.cmd_l:   "win",
                _pynput_kb.Key.cmd_r:   "win",
            }
            MOD_KEYS = set(mod_names.keys())

            def _on_press(key):
                if not capture_state["active"]:
                    return False
                if key in MOD_KEYS:
                    pressed_mods.add(mod_names[key])
                else:
                    main_pressed[0] = key
                    # Build combo string
                    parts = []
                    for m in ("ctrl", "shift", "alt", "win"):
                        if m in pressed_mods:
                            parts.append(m)
                    # Nombre de la tecla (con Ctrl pulsado las letras llegan como
                    # caracteres de control, así que se usa el código virtual)
                    vk = getattr(key, 'vk', None)
                    if hasattr(key, 'name') and key.name:
                        parts.append(key.name)
                    elif vk is not None and (48 <= vk <= 57 or 65 <= vk <= 90):
                        parts.append(chr(vk).lower())
                    elif hasattr(key, 'char') and key.char and key.char.isprintable():
                        parts.append(key.char.lower())
                    else:
                        parts.append(str(key))
                    combo = "+".join(parts)

                    def _apply():
                        hotkey_var.set(combo)
                        status_lbl.config(text=f"✅  Capturado: {combo}", fg="#44ff88")
                        _stop_capture()
                    # Los widgets de Tk solo se tocan desde el hilo principal
                    self._ui(_apply)
                    return False  # stop listener

            listener = _pynput_kb.Listener(on_press=_on_press)
            listener.daemon = True
            listener.start()
            capture_state["listener"] = listener

        cap_btn = tk.Button(
            kf, text="🎯  Capturar tecla",
            bg=C["accent"], fg="white",
            font=("Segoe UI", 10, "bold"),
            relief='flat', cursor="hand2", padx=12, pady=6,
            activebackground="#2563eb",
            command=_start_capture)
        cap_btn.grid(row=2, column=0, columnspan=2, sticky='w', padx=8, pady=8)

        # ── Info ──────────────────────────────────────────────────────────────
        self._info(p, [
            "📋  MODO PTT (Push-to-Talk):",
            "• Mantén la tecla configurada → el micrófono graba tu voz",
            "• Suelta la tecla → se transcribe y se envía automáticamente a la IA",
            "• Si 'sin conversación continua' está activo, vuelve al modo espera tras responder",
            "• La respuesta se lee en voz alta si la «Voz IA» está activada",
            "• Combinaciones válidas: f9 · ctrl+space · ctrl+shift+f10 · alt+v",
            "⚠️  Requiere:  pip install pynput pyaudio",
            f"{'✅  pynput y pyaudio detectados' if HAS_PYNPUT else '❌  pynput/pyaudio NO detectados — instálalos para usar PTT'}",
        ])

    # ── Guardar ───────────────────────────────────────────────────────────────
    def _save(self):
        if hasattr(self, "_sp_text_widget"):
            self._vars["system_prompt"].set(
                self._sp_text_widget.get("1.0", "end-1c").strip())
        if "tts_engine" in self._vars:
            raw = self._vars["tts_engine"].get()
            self._vars["tts_engine"].set("gtts" if "gtts" in raw else "pyttsx3")
        # Se parte de la configuración ACTUAL (no de la copia de cuando se abrió la
        # ventana) y solo se aplican las opciones que se han visto/editado aquí.
        cfg = dict(self._app.config) if self._app else dict(self._cfg)
        for key, var in self._vars.items():
            if not key.startswith("_"):
                try:
                    cfg[key] = var.get()
                except Exception:
                    pass
        if "_lang_display" in self._vars:
            display = self._vars["_lang_display"].get()
            try:
                idx = self._lang_names.index(display)
                cfg["language"] = self._lang_codes[idx]
            except ValueError: pass
        for key in ("orb_size","popup_width","popup_height",
                    "popup_custom_x","popup_custom_y","popup_auto_close",
                    "orb_x","orb_y","max_history_turns","history_max_hours","log_max_entries",
                    "energy_threshold","tts_rate",
                    "popup_close_on_tts_end_delay","whatsapp_bridge_port","whatsapp_read_max",
                    "whisper_beam_size","ollama_num_ctx","camera_index","vision_max_side",
                    "captures_keep","reminder_sound_repeats","reminder_snooze_minutes",
                    "pc_max_steps","pc_image_width","pc_max_elements"):
            try: cfg[key] = int(float(cfg.get(key, DEFAULT_CONFIG.get(key,0))))
            except Exception: cfg[key] = DEFAULT_CONFIG.get(key, 0)
        # Campos de texto — proteger de coerción numérica
        if "ptt_hotkey" in cfg:
            cfg["ptt_hotkey"] = str(cfg["ptt_hotkey"]).strip() or "f9"
        if "pc_stop_hotkey" in cfg:
            cfg["pc_stop_hotkey"] = str(cfg["pc_stop_hotkey"]).strip().lower() or "esc"
        for key in ("ollama_keep_alive", "vision_model", "reminder_sound_file", "ollama_model",
                    "ollama_host", "whatsapp_self_trigger_words", "ollama_think_mode"):
            if key in cfg:
                cfg[key] = str(cfg[key]).strip()
        for key in ("orb_opacity","orb_opacity_min","popup_opacity",
                    "silence_timeout","phrase_time_limit","wake_phrase_limit",
                    "pause_threshold","phrase_threshold","non_speaking_duration",
                    "dynamic_energy_ratio","tts_volume","pc_action_delay"):
            try: cfg[key] = round(float(cfg.get(key,1.0)), 3)
            except Exception: pass
        if "ollama_think_mode" in self._vars:       # la opción antigua se mantiene al día
            cfg["ollama_no_think"] = think_mode(cfg) != "always"
        save_config(cfg)
        self._on_save(cfg)
        messagebox.showinfo("✅ Guardado",
            "Configuración guardada y aplicada.", parent=self)
        self.destroy()


# ── TTS ───────────────────────────────────────────────────────────────────────
def speak(text: str, engine: str = "pyttsx3", rate: int = 180, volume: float = 1.0, voice_id: str = ""):
    global _TTS_MUTED
    if _TTS_MUTED:
        return
    clean = strip_action_tags(text)                         # nunca leer etiquetas
    clean = re.sub(r"```.*?```", " ", clean, flags=re.DOTALL)   # ni bloques de código
    clean = re.sub(r"https?://\S+", "", clean)              # ni URLs
    clean = re.sub(r"#{1,6}\s*", "", clean)
    clean = re.sub(r"[*_`>]", "", clean)
    clean = re.sub(r"-{3,}", "", clean)
    clean = re.sub(r"\s+", " ", clean).strip()
    if not clean:
        return

    if engine == "gtts":
        try:
            from gtts import gTTS
            import io as _io
            tts = gTTS(text=clean, lang="es", slow=False)
            buf = _io.BytesIO()
            tts.write_to_fp(buf)
            buf.seek(0)
            try:
                import pygame
                pygame.mixer.init()
                pygame.mixer.music.load(buf, "mp3")
                pygame.mixer.music.play()
                while pygame.mixer.music.get_busy():
                    time.sleep(0.1)
                return
            except Exception:
                pass
            import tempfile
            buf.seek(0)
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
                f.write(buf.read()); tmp = f.name
            if platform.system() == "Windows":
                os.startfile(tmp)
            elif platform.system() == "Darwin":
                subprocess.Popen(["afplay", tmp])
            else:
                subprocess.Popen(["mpg123", tmp])
        except ImportError:
            print("[TTS] gtts no instalado. Ejecuta:  pip install gtts")
        except Exception as e:
            print(f"[TTS] gtts error: {e}")
    else:
        try:
            import pyttsx3 as _pyttsx3
            is_onecore = "Speech_OneCore" in str(voice_id)
            if is_onecore and platform.system() == "Windows":
                try:
                    import win32com.client
                    sapi = win32com.client.Dispatch("SAPI.SpVoice")
                    cat = win32com.client.Dispatch("SAPI.SpObjectTokenCategory")
                    cat.SetId(r"HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Speech_OneCore\Voices", False)
                    tokens = cat.EnumerateTokens()
                    for tok in tokens:
                        if tok.Id.lower() == voice_id.lower().replace("\\\\", "\\"):
                            sapi.Voice = tok
                            break
                    sapi.Rate   = max(-10, min(10, int((int(rate) - 180) / 18)))
                    sapi.Volume = int(float(volume) * 100)
                    sapi.Speak(clean)
                except Exception as e_oc:
                    print(f"[TTS] OneCore via win32com error: {e_oc}")
                    eng = _pyttsx3.init()
                    eng.setProperty("rate",   int(rate))
                    eng.setProperty("volume", float(volume))
                    eng.say(clean)
                    eng.runAndWait()
            else:
                eng = _pyttsx3.init()
                eng.setProperty("rate",   int(rate))
                eng.setProperty("volume", float(volume))
                if voice_id:
                    eng.setProperty("voice", voice_id)
                eng.say(clean)
                eng.runAndWait()
        except ImportError:
            print("[TTS] pyttsx3 no instalado. Ejecuta:  pip install pyttsx3")
        except Exception as e:
            print(f"[TTS] pyttsx3 error: {e}")


# ── Log helpers ───────────────────────────────────────────────────────────────
def append_log(path: str, user_msg: str, ai_msg: str, max_entries: int = 0):
    """Añade una conversación al log. Con max_entries > 0 borra las más antiguas."""
    try:
        ts = time.strftime("%Y-%m-%d %H:%M")
        sep = '─' * 60
        entry = f"[{ts}]\nTú: {user_msg}\nIA:  {ai_msg}\n{sep}\n"
        with _LOG_LOCK:
            with open(path, "a", encoding="utf-8") as f:
                f.write(entry)
            if max_entries > 0:
                raw = open(path, encoding="utf-8", errors="replace").read()
                blocks = [b for b in raw.split(sep + "\n") if b.strip()]
                if len(blocks) > max_entries:
                    tmp = path + ".tmp"
                    with open(tmp, "w", encoding="utf-8") as f:
                        f.write("".join(b + sep + "\n" for b in blocks[-max_entries:]))
                    os.replace(tmp, path)
    except Exception as e:
        print(f"[Log] Error al escribir: {e}")


_LOG_LOCK = threading.Lock()


def load_log_as_context(path: str, with_dates: bool = False, max_turns: int = 0) -> list:
    """
    Convierte el log de conversaciones en historial para la IA.
    Con with_dates, cada mensaje lleva la fecha en que se dijo (igual que los nuevos).
    """
    if not path or not os.path.exists(path):
        return []
    try:
        raw     = open(path, encoding="utf-8", errors="replace").read()
        blocks  = re.split(r"─{10,}", raw)
        history = []
        for block in blocks:
            um = re.search(r"^Tú:\s*(.+)$", block, re.MULTILINE)
            am = re.search(r"^IA:\s*(.+)", block, re.MULTILINE | re.DOTALL)
            if um and am:
                user = um.group(1).strip()
                when = None                       # fecha de la conversación (para olvidar por tiempo)
                dm = re.search(r"\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2})\]", block)
                if dm:
                    try:
                        when = datetime.strptime(dm.group(1), '%Y-%m-%d %H:%M')
                    except ValueError:
                        pass
                if with_dates and when:
                    user = f"[{fecha_larga(when)}] {user}"
                ts = when.timestamp() if when else None
                history.append({"role": "user",      "content": user, "ts": ts})
                history.append({"role": "assistant", "content": am.group(1).strip(), "ts": ts})
        if max_turns > 0:
            history = history[-max_turns * 2:]
        return history
    except Exception as e:
        print(f"[Log] Error al leer: {e}")
        return []


# ── Main Application ──────────────────────────────────────────────────────────
class VoiceAIApp:

    def __init__(self):
        self.config   = load_config()
        self.root     = tk.Tk(className="Rubencho AI")
        self.root.withdraw()
        try:
            self.root.tk.call("tk", "appname", APP_NAME)   # título por defecto de las ventanas
            self.root.title(APP_NAME)
        except Exception:
            pass
        try:
            if ICON_ICO.exists():
                self.root.iconbitmap(default=str(ICON_ICO))   # todas las ventanas usan el icono
        except Exception:
            pass
        self.root.report_callback_exception = self._tk_error
        self._ui_q    = queue.Queue()
        self._listening  = False        # capturando una orden de voz
        self._processing = False        # la IA está respondiendo
        self._chat_lock  = threading.Lock()   # una petición a la IA cada vez
        self._orb     = None
        self._popup   = None
        self._popup_alpha = None
        self._quick_input  = None
        self._settings_win = None
        self._notifications: list = []
        self._whisper_model    = None
        self._whisper_key      = None
        self._whisper_lock     = threading.Lock()
        self._vosk_model       = None
        self._vosk_model_path  = None
        self._vosk_lock        = threading.Lock()
        self._tts_playing      = False
        self._tts_last         = 0.0
        self._continuous_active= False
        self._wa_proc          = None
        self._wa_listen_active = False
        self._tray             = None
        self._capture_restore  = False
        # Control del PC
        self._pc_session       = None     # PcController de la orden en curso
        self._pc_banner        = None
        self._pc_dialog        = None

        # Memoria persistente y recordatorios
        self._memory    = MemoryStore()
        self._reminders = ReminderStore()
        self._ai_tasks  = AITaskStore()

        self._history: list = []
        if (self.config.get("log_load_as_memory") and
                self.config.get("log_enabled") and
                self.config.get("log_file_path")):
            self._history = load_log_as_context(
                self.config["log_file_path"],
                with_dates=bool(self.config.get("datetime_in_messages", True)),
                max_turns=max(1, int(self.config.get("max_history_turns", 10))))
            print(f"📖  Log cargado: {len(self._history)//2} turnos anteriores")

        # PTT state
        self._ptt_active   = False
        self._ptt_ctrl     = False
        self._ptt_shift    = False
        self._ptt_alt      = False
        self._ptt_win      = False
        self._ptt_listener = None

        # Arrancar bridge WhatsApp si está activado
        if self.config.get("whatsapp_enabled"):
            self._start_whatsapp()

        self._create_orb()
        self._setup_tray()
        self._start_listener()
        self._start_ptt_listener()
        self._preload_models()
        self._scheduler = ReminderScheduler(self._reminders, self._on_reminder_due)
        self._scheduler.start()
        self._task_scheduler = ReminderScheduler(self._ai_tasks, self._on_ai_task_due)
        self._task_scheduler.start()
        self.root.after(50, self._process_queue)

        if "--settings" in sys.argv:
            self.root.after(400, self.open_settings)
        elif "--tray" not in sys.argv:
            # Abierta a mano (menú Inicio, escritorio, barra de tareas): avisar de dónde está
            self.root.after(1500, lambda: self._notify(
                APP_NAME, "Rubencho AI está en marcha. Lo tienes en el icono junto al reloj; "
                          "haz clic en él para escribirle."))
        self._sync_autostart()
        _listen_for_other_instances(self._ui_q)

        self.root.mainloop()

    def _tk_error(self, exc, val, tb):
        import traceback
        print("[Tk] Error en la interfaz:")
        traceback.print_exception(exc, val, tb)

    # ── Orbe, bandeja y avisos ────────────────────────────────────────────────
    def _create_orb(self):
        try:
            self._orb = OrbWindow(
                self.root, self.config,
                on_open_settings=lambda: self._ui_q.put(("settings",      None)),
                on_listen_now=   lambda: self._ui_q.put(("manual_listen", None)),
                on_stop_listening=lambda: self._ui_q.put(("stop_listening", None)),
                on_write=        lambda: self._ui_q.put(("quick_input",   None)),
                is_speaking=self._is_speaking,
            )
            self._orb.bind("<<Quit>>", lambda _: self._ui_q.put(("quit", None)))
        except Exception as e:
            print(f"[Orb] {e}")

    def _is_speaking(self) -> bool:
        return self._tts_playing or (time.time() - self._tts_last) < 0.35

    def _setup_tray(self):
        if not HAS_TRAY:
            self._setup_fallback_window()
            return
        try:
            img = Image.open(ICON_TRAY).convert("RGBA")
        except Exception:
            img = Image.new('RGBA', (64,64), (0,0,0,0))
            d   = ImageDraw.Draw(img)
            d.ellipse([4,4,60,60],  fill=(79,142,247,230))
            d.ellipse([12,12,28,28],fill=(200,220,255,140))
        q = self._ui_q
        menu = pystray.Menu(
            pystray.MenuItem(APP_NAME, None, enabled=False),
            pystray.Menu.SEPARATOR,
            # default=True → también se abre con un clic izquierdo en el icono
            pystray.MenuItem("✍️  Escribir mensaje",
                             lambda *_: q.put(("quick_input", None)), default=True),
            pystray.MenuItem("🎙  Escuchar ahora",
                             lambda *_: q.put(("manual_listen", None))),
            pystray.MenuItem("🛑  Detener escucha",
                             lambda *_: q.put(("stop_listening", None))),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("🖱  Control del PC",
                             lambda *_: q.put(("pc_toggle", None)),
                             checked=lambda _i: bool(self.config.get("pc_control_enabled", False))),
            pystray.MenuItem("⛔  Detener el control del PC",
                             lambda *_: q.put(("pc_stop", "lo has detenido desde la bandeja")),
                             visible=lambda _i: self._pc_session is not None),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("⏰  Recordatorios…",
                             lambda *_: q.put(("settings", "reminders"))),
            pystray.MenuItem("🧠  Memoria…",
                             lambda *_: q.put(("settings", "memory"))),
            pystray.MenuItem("👁  Mostrar orbe",
                             lambda *_: q.put(("show_orb",      None))),
            pystray.MenuItem("🗑  Limpiar historial",
                             lambda *_: q.put(("clear_history", None))),
            pystray.MenuItem("⚙️  Configuración",
                             lambda *_: q.put(("settings",      None))),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("❌  Salir",
                             lambda *_: q.put(("quit",          None))),
        )
        self._tray = pystray.Icon("RubenchoAI", img, APP_NAME, menu)
        threading.Thread(target=self._tray.run, daemon=True, name="bandeja").start()

    def _set_tray_title(self, text: str):
        """El texto del icono de la bandeja es siempre el nombre; el estado va al log."""
        print(f"[Estado] {text}")
        if self._tray is not None:
            try:
                if self._tray.title != APP_NAME:
                    self._tray.title = APP_NAME
            except Exception:
                pass

    def _notify(self, title: str, msg: str):
        """Notificación del sistema (bandeja); si no hay bandeja, un cuadro de diálogo."""
        if self._tray is not None and getattr(self._tray, "HAS_NOTIFICATION", True):
            try:
                self._tray.notify(msg, title)
                return
            except Exception as e:
                print(f"[Bandeja] {e}")
        try:
            messagebox.showinfo(title, msg, parent=self.root)
        except Exception:
            pass

    def _setup_fallback_window(self):
        bg = "#0d1117"
        self.root.deiconify()
        self.root.title("🐢  Rubencho AI")
        self.root.geometry("340x90")
        self.root.resizable(False, False)
        self.root.configure(bg=bg)
        self.root.protocol("WM_DELETE_WINDOW", self.root.iconify)
        tk.Label(self.root, text="🐢  Rubencho AI  —  escuchando...",
                 bg=bg, fg="#4f8ef7",
                 font=("Segoe UI",12,"bold")).pack(expand=True, pady=6)
        fr = tk.Frame(self.root, bg=bg)
        fr.pack(pady=4)
        for txt, cmd in [
            ("✍️", self._open_quick_input),
            ("🎙", self._manual_listen_trigger),
            ("⚙️", self.open_settings),
            ("🗑", lambda: self._history.clear()),
            ("✕", self._quit),
        ]:
            tk.Button(fr, text=txt, bg="#21262d", fg="white",
                      relief='flat', cursor="hand2", padx=8,
                      command=cmd).pack(side='left', padx=3)

    # ── Cola de la interfaz (todo lo que toca Tk pasa por aquí) ──────────────
    def _process_queue(self):
        try:
            while True:
                cmd, data = self._ui_q.get_nowait()
                try:
                    self._handle_ui(cmd, data)
                except Exception as e:
                    import traceback
                    print(f"[UI] Error procesando '{cmd}': {e}")
                    traceback.print_exc()
        except queue.Empty:
            pass
        self.root.after(40, self._process_queue)

    def _handle_ui(self, cmd: str, data):
        if   cmd == "orb_state":         self._orb and self._orb.set_state(data)
        elif cmd == "open_popup_stream": self._open_stream_popup(data)
        elif cmd == "popup_chunk":       self._append_popup_chunk(data)
        elif cmd == "popup_stream_done": self._finalize_popup(data)
        elif cmd == "popup_image":       self._add_popup_image(*data)
        elif cmd == "show_popup":        self._show_popup(*data)
        elif cmd == "show_orb":          self._orb and self._orb.show_orb()
        elif cmd == "settings":          self.open_settings(data)
        elif cmd == "quick_input":       self._open_quick_input()
        elif cmd == "manual_listen":     self._manual_listen_trigger()
        elif cmd == "stop_listening":    self._stop_listening()
        elif cmd == "hide_for_capture":  self._hide_for_capture(data)
        elif cmd == "restore_after_capture": self._restore_after_capture()
        elif cmd == "reminder_fire":     self._show_reminder(*data)
        elif cmd == "reminder_test":     self._test_reminder()
        elif cmd == "notify":            self._notify(*data)
        elif cmd == "ui_call":
            fn, evt, holder = data
            try:
                holder["r"] = fn()
            finally:
                evt.set()
        elif cmd == "pc_banner":         self._pc_set_banner(data)
        elif cmd == "pc_confirm":        self._pc_show_confirm(*data)
        elif cmd == "pc_toggle":         self._pc_toggle()
        elif cmd == "pc_stop":
            if self._pc_session is not None:
                self._pc_session.request_stop(data or "lo has detenido")
        elif cmd == "tray_refresh":      self._tray_refresh()
        elif cmd == "loading_done":
            if self._orb and self._orb.state == "loading":
                self._orb.set_state("idle")
        elif cmd == "clear_history":
            self._history.clear()
            self._notify("Rubencho AI", "🗑  Historial de conversación borrado.")
        elif cmd == "close_popup":
            self._destroy_popup()
        elif cmd == "quit":              self._quit()

    # ── Popup de respuesta ───────────────────────────────────────────────────
    def _popup_alive(self) -> bool:
        try:
            return self._popup is not None and bool(self._popup.winfo_exists())
        except Exception:
            return False

    def _destroy_popup(self):
        if self._popup is not None:
            try: self._popup.destroy()
            except Exception: pass
            self._popup = None

    def _show_popup(self, transcript: str, response: str):
        self._destroy_popup()
        try:
            self._popup = ResponsePopup(
                self.root, self.config, transcript, response,
                on_send=self._handle_text_input,
                on_mute=self._toggle_mute)
        except Exception as e:
            import traceback
            print(f"[Popup] {e}")
            traceback.print_exc()

    def _open_stream_popup(self, transcript: str):
        self._destroy_popup()
        try:
            self._popup = ResponsePopup(
                self.root, self.config, transcript, "",
                streaming=True,
                on_send=self._handle_text_input,
                on_mute=self._toggle_mute)
        except Exception as e:
            import traceback
            print(f"[Popup-stream] {e}")
            traceback.print_exc()

    def _append_popup_chunk(self, chunk: str):
        if self._popup_alive():
            try:
                self._popup.append_chunk(chunk)
            except Exception:
                pass

    def _finalize_popup(self, full_response: str):
        if self._popup_alive():
            try:
                self._popup.finalize(full_response)
            except Exception:
                pass

    def _add_popup_image(self, thumb, path):
        if self._popup_alive():
            self._popup.add_image(thumb, path)

    def _toggle_mute(self) -> bool:
        """Alterna el silencio del TTS. Devuelve el nuevo estado (True=silenciado).
        Al silenciar, libera _tts_playing para que el bucle de conversación continua
        pueda escuchar en cuanto termine la frase actual."""
        global _TTS_MUTED
        _TTS_MUTED = not _TTS_MUTED
        if _TTS_MUTED:
            # Liberar el flag inmediatamente: la frase en curso terminará sola
            # (pyttsx3 es bloqueante por frase), pero la siguiente no sonará
            # y el bucle continuo no se quedará esperando indefinidamente.
            self._tts_playing = False
        print(f"🔇 TTS {'silenciado' if _TTS_MUTED else 'activado'}")
        return _TTS_MUTED

    # ── Mensajes escritos ────────────────────────────────────────────────────
    def _open_quick_input(self):
        try:
            if self._quick_input is not None and self._quick_input.winfo_exists():
                self._quick_input.focus_input()
                return
        except Exception:
            pass
        self._quick_input = QuickInputWindow(
            self.root, self.config, on_send=self._handle_text_input,
            on_close=lambda: setattr(self, "_quick_input", None))

    def _handle_text_input(self, text: str):
        """Envía a la IA un mensaje escrito (popup o «Escribir mensaje»)."""
        text = (text or "").strip()
        if not text:
            return
        threading.Thread(target=self._stream_ollama, args=(text,),
                         kwargs={"origin": "texto"}, daemon=True).start()

    # ── Escucha por voz ──────────────────────────────────────────────────────
    def _start_listener(self):
        if not HAS_SR:
            print("⚠️  SpeechRecognition no instalado.")
            return
        threading.Thread(target=self._listener_loop, daemon=True, name="palabra-clave").start()

    def _apply_vad(self, r):
        cfg = self.config
        r.pause_threshold         = float(cfg.get("pause_threshold",         1.8))
        r.phrase_threshold        = float(cfg.get("phrase_threshold",        0.1))
        r.non_speaking_duration   = float(cfg.get("non_speaking_duration",   0.4))
        r.dynamic_energy_threshold= bool(cfg.get("dynamic_energy_threshold", True))
        r.dynamic_energy_ratio    = float(cfg.get("dynamic_energy_ratio",    1.5))
        if not r.dynamic_energy_threshold:
            r.energy_threshold    = float(cfg.get("energy_threshold",        300))

    def _is_busy(self) -> bool:
        """¿Hay ya algo en marcha? (para no abrir dos escuchas ni dos peticiones a la vez)"""
        return (self._listening or self._processing or
                self._continuous_active or self._ptt_active)

    def _wake_word(self) -> str:
        cfg = self.config
        if cfg.get("use_custom_wake_word") and str(cfg.get("custom_wake_word", "")).strip():
            return str(cfg["custom_wake_word"]).strip()
        return str(cfg.get("wake_word", "asistente"))

    @staticmethod
    def _contains_wake(phrase: str, wake: str) -> bool:
        w = _norm_text(wake)
        return bool(w) and w in _norm_text(phrase)      # sin tildes ni mayúsculas

    def _listener_loop(self):
        """
        Espera la palabra clave. Con el motor «vosk» la reconoce en local mientras
        hablas (al instante); con «google», al acabar cada frase y por internet.
        """
        print("🐢  Rubencho AI iniciado — esperando palabra clave...")
        r = mic = None
        retry_local = 0.0
        while True:
            if self.config.get("speech_engine", "vosk") == "vosk" and time.time() >= retry_local:
                if self._stream_listener():
                    continue                      # se ha cambiado de motor en la configuración
                retry_local = time.time() + 60
                print("ℹ️  Palabra clave local no disponible: se usa la clásica (se reintenta en 1 min)")
            if mic is None:
                r, mic = self._classic_mic()
                if mic is None:
                    time.sleep(5)
                    continue
            self._classic_listen_once(r, mic)

    def _classic_mic(self):
        r = sr.Recognizer()
        r.energy_threshold = float(self.config.get("energy_threshold", 300))
        self._apply_vad(r)
        try:
            mic = sr.Microphone()
            with mic as src:
                r.adjust_for_ambient_noise(src, duration=1.5)
            print(f"✅  Calibrado. Umbral: {r.energy_threshold:.0f}  |  pausa: {r.pause_threshold}s")
        except Exception as e:
            print(f"⚠️  Error calibrando: {e}")
            try:
                mic = sr.Microphone()
            except Exception as e2:
                print(f"❌  No hay micrófono disponible: {e2}")
                return r, None
        return r, mic

    def _classic_listen_once(self, r, mic):
        """Palabra clave «clásica»: escucha una frase entera y la reconoce (Google)."""
        try:
            # Mientras se procesa una orden, hay conversación continua o PTT,
            # no se escucha la palabra clave (evita dos micrófonos y peticiones dobles)
            if self._is_busy():
                time.sleep(0.25)
                return
            cfg  = self.config
            wake = self._wake_word()
            phrase = self._sr_listen(r, mic,
                phrase_time_limit=float(cfg.get("wake_phrase_limit", 3.0)))
            if not phrase or self._is_busy() or not self._contains_wake(phrase, wake):
                return
            self._listening = True

            print(f"✅  '{wake}' detectado → escuchando comando...")
            self._ui_q.put(("orb_state", "listening"))
            if cfg.get("sound_feedback", False):
                play_sound("activacion", wait=True)
            self._apply_vad(r)
            command = self._capture_command(r, mic)

            if not command:
                print("⚠️  Sin comando.")
                self._ui_q.put(("orb_state", "idle"))
                self._listening = False
                return

            print(f"📝  Comando: {command}")
            threading.Thread(
                target=self._stream_ollama,
                args=(command,), kwargs={"origin": "voz"},
                daemon=True).start()

        except Exception as e:
            print(f"[Listener] {e}")
            self._listening = False
            time.sleep(1)

    # ── Palabra clave local en tiempo real (Vosk) ────────────────────────────
    def _stream_listener(self) -> bool:
        """
        Escucha continua con Vosk: reconoce la palabra clave mientras la dices (sin
        esperar a que acabes la frase ni a internet) y graba la orden del mismo audio,
        así que también vale decirlo de corrido: «asistente, ¿qué hora es?».
        Devuelve True si se ha cambiado de motor en la configuración y False si falla.
        """
        try:
            import sounddevice as sd
            from vosk import KaldiRecognizer
        except ImportError as e:
            print(f"⚠️  Palabra clave local: falta {e.name} (pip install vosk sounddevice)")
            return False
        model = self._get_vosk_model()
        if model is None:
            print("⚠️  Palabra clave local: no se encuentra el modelo de Vosk")
            return False
        RATE, BLOCK = 16000, 1600                       # bloques de 0,1 s
        audio_q: queue.Queue = queue.Queue(maxsize=600)

        def on_audio(indata, frames, t, status):
            try:
                audio_q.put_nowait(bytes(indata))
            except queue.Full:
                pass

        gap  = max(1, round(float(self.config.get("non_speaking_duration", 0.5)) / 0.1))
        rec  = KaldiRecognizer(model, RATE)
        ring = collections.deque(maxlen=40)             # últimos 4 s: (nº de bloque, audio, ¿voz?)
        seq = utt_start = 0
        quiet, noise, was_busy = gap, None, False
        try:
            with sd.RawInputStream(samplerate=RATE, blocksize=BLOCK, channels=1,
                                   dtype="int16", callback=on_audio):
                print(f"✅  Palabra clave local activa («{self._wake_word()}»): te escucho al instante")
                while True:
                    if self.config.get("speech_engine", "vosk") != "vosk":
                        return True
                    try:
                        data = audio_q.get(timeout=3)
                    except queue.Empty:
                        raise RuntimeError("el micrófono no envía audio")
                    # Mientras responde, hay conversación continua o PTT, el audio se descarta
                    if self._is_busy():
                        if not was_busy:
                            rec.Reset()
                            ring.clear()
                            was_busy = True
                        continue
                    was_busy = False
                    seq += 1
                    loud, noise = self._chunk_is_voice(data, noise)
                    if loud:
                        if quiet >= gap:
                            utt_start = seq                 # empieza una frase nueva
                        quiet = 0
                    else:
                        quiet += 1
                    ring.append((seq, data, loud))
                    final = rec.AcceptWaveform(data)
                    res = json.loads(rec.Result() if final else rec.PartialResult())
                    wake = self._wake_word()
                    if not self._contains_wake(res.get("text" if final else "partial", ""), wake):
                        continue

                    print(f"✅  '{wake}' detectado → escuchando comando...")
                    self._listening = True
                    self._ui_q.put(("orb_state", "listening"))
                    # El audio desde 0,3 s antes de que empezaras a hablar: así la orden
                    # dicha de corrido con la palabra clave no pierde el principio
                    first = max(utt_start - 3, seq - 39)
                    pre = [d for n, d, _ in ring if n >= first]
                    try:
                        command = self._stream_capture_command(audio_q, pre, noise, wake)
                    except Exception as e:
                        print(f"[Escucha] {e}")
                        command = ""
                    rec.Reset()
                    ring.clear()
                    quiet = gap
                    if not command:
                        print("⚠️  Sin comando.")
                        self._ui_q.put(("orb_state", "idle"))
                        self._listening = False
                        continue
                    print(f"📝  Comando: {command}")
                    threading.Thread(
                        target=self._stream_ollama,
                        args=(command,), kwargs={"origin": "voz"},
                        daemon=True).start()
        except Exception as e:
            print(f"⚠️  Palabra clave local: {e}")
            self._listening = False
            return False

    def _chunk_is_voice(self, data: bytes, noise):
        """¿Hay voz en este trozo de audio? (por volumen, con los ajustes de Reconocimiento)"""
        import numpy as np
        x = np.frombuffer(data, dtype=np.int16).astype(np.float32)
        rms = float(np.sqrt(np.mean(x * x))) if x.size else 0.0
        # Nivel del ruido de fondo: baja rápido y sube despacio (la voz no lo sube)
        noise = rms if noise is None else (
            noise * 0.7 + rms * 0.3 if rms < noise else noise * 0.995 + rms * 0.005)
        cfg = self.config
        if cfg.get("dynamic_energy_threshold", True):
            thr = max(150.0, noise * float(cfg.get("dynamic_energy_ratio", 1.5)) * 1.5)
        else:
            thr = float(cfg.get("energy_threshold", 300))
        return rms > thr, noise

    def _stream_capture_command(self, audio_q, pre: list, noise, wake: str) -> str:
        """Graba la orden (después de la palabra clave) del flujo de audio y la transcribe."""
        cfg    = self.config
        pause  = float(cfg.get("pause_threshold", 1.8))
        wait   = float(cfg.get("silence_timeout", 2.5))
        maxlen = float(cfg.get("phrase_time_limit", 15.0))
        chunks = list(pre)
        # El pitido y el final de la palabra clave no cuentan como voz de la orden
        neutral = 0.2
        if cfg.get("sound_feedback", False):
            neutral = max(neutral, self._sound_seconds("activacion") + 0.1)
            play_sound("activacion")                    # sin esperar: se sigue grabando
        spoke = maybe = False
        quiet = t = 0.0
        while t < maxlen:
            try:
                data = audio_q.get(timeout=2)
            except queue.Empty:
                break
            chunks.append(data)
            t += 0.1
            loud, noise = self._chunk_is_voice(data, noise)
            if t <= neutral:
                maybe = maybe or (loud and t > 0.2)     # ¿orden muy corta dicha de corrido?
                continue
            if loud:
                spoke, quiet = True, 0.0
            else:
                quiet += 0.1
                if spoke and quiet >= pause:
                    break
                if not spoke and t >= wait + neutral:
                    break
        if not (spoke or maybe):
            return ""
        self._ui_q.put(("orb_state", "thinking"))      # transcribiendo…
        audio = sr.AudioData(b"".join(chunks), 16000, 2)
        text = (self._recognize(audio, cfg.get("command_engine", "whisper")) or "").strip()
        return self._strip_wake(text, wake)

    @staticmethod
    def _strip_wake(text: str, wake: str) -> str:
        """Quita la palabra clave del principio: «Oye asistente, ¿qué hora es?» → «¿qué hora es?»."""
        import difflib
        target = _norm_text(wake)
        n = len(target.split())
        words = list(re.finditer(r"\w+", text or ""))
        if not target or not words:
            return (text or "").strip()
        for i in range(min(3, len(words) - n + 1)):     # entre las primeras palabras
            cand = _norm_text(" ".join(m.group() for m in words[i:i + n]))
            if difflib.SequenceMatcher(None, cand, target).ratio() >= 0.75:
                return text[words[i + n - 1].end():].lstrip(" ,.;:!-–—…").strip()
        return text.strip()

    @staticmethod
    def _sound_seconds(name: str) -> float:
        try:
            import wave
            with wave.open(str(_sound_file(name)), "rb") as w:
                return w.getnframes() / float(w.getframerate())
        except Exception:
            return 0.3

    def _capture_command(self, r, mic) -> str:
        """Graba la orden y la transcribe con el motor elegido."""
        cfg    = self.config
        audio  = self._record_raw_audio(
            r, mic,
            phrase_time_limit=float(cfg.get("phrase_time_limit", 15.0)),
            timeout=float(cfg.get("silence_timeout", 2.5)))
        if audio is None:
            return ""
        self._ui_q.put(("orb_state", "thinking"))      # transcribiendo…
        return (self._recognize(audio, cfg.get("command_engine", "whisper")) or "").strip()

    def _recognize(self, audio, engine: str) -> str:
        if audio is None:
            return ""
        if engine == "whisper":
            return self._whisper_transcribe(audio)
        if engine == "vosk":
            txt = self._vosk_transcribe(audio)
            if txt is not None:
                return txt
        try:
            return sr.Recognizer().recognize_google(
                audio, language=self.config.get("language", "es-ES"))
        except sr.UnknownValueError:
            return ""
        except sr.RequestError as e:
            print(f"[SR] Google no disponible: {e}")
            return ""
        except Exception as e:
            print(f"[SR] {e}")
            return ""

    # ── Precarga de modelos ──────────────────────────────────────────────────
    def _preload_models(self):
        """
        Carga al arrancar el modelo de transcripción (Whisper/Vosk) y el de Ollama,
        para que la primera orden no tenga que esperar. El orbe muestra «cargando».
        """
        def work():
            cfg = self.config
            t0  = time.time()
            self._ui_q.put(("orb_state", "loading"))
            self._set_tray_title("cargando modelos…")
            try:
                _sound_file("activacion")
                _sound_file("recordatorio")
                if cfg.get("command_engine", "whisper") == "whisper" and cfg.get("whisper_preload", True):
                    self._ensure_whisper(warmup=True)
                if "vosk" in (cfg.get("command_engine"), cfg.get("speech_engine")):
                    self._get_vosk_model()
            except Exception as e:
                print(f"[Precarga] {e}")
            finally:
                print(f"✅  Rubencho AI listo ({time.time() - t0:.1f}s)")
                dev = getattr(self, "_whisper_device_used", None)
                extra = f" · Whisper en {dev.upper()}" if dev else ""
                self._set_tray_title(f"listo{extra}")
                self._ui_q.put(("loading_done", None))
        threading.Thread(target=work, daemon=True, name="precarga").start()
        threading.Thread(target=self._preload_ollama, daemon=True, name="precarga-ollama").start()

    def _preload_ollama(self):
        cfg   = self.config
        host  = cfg.get("ollama_host", "http://localhost:11434")
        model = cfg.get("ollama_model", "")
        if not HAS_REQUESTS or not model:
            return
        ollama_capabilities(host, model)                 # deja en caché si admite visión, etc.
        if not cfg.get("ollama_preload", True) or is_cloud_model(model):
            return
        try:
            body = {"model": model}
            ka = self._keep_alive()
            if ka is not None:
                body["keep_alive"] = ka
            t = time.time()
            r = requests.post(f"{host}/api/generate", json=body, timeout=300)
            if r.status_code == 200:
                print(f"✅  Modelo de Ollama '{model}' cargado en memoria ({time.time() - t:.1f}s)")
            else:
                print(f"[Ollama] Precarga: {_ollama_error_message(r, model)}")
        except Exception as e:
            print(f"[Ollama] Precarga no disponible: {e}")

    # ── Whisper ──────────────────────────────────────────────────────────────
    def _ensure_whisper(self, warmup: bool = False) -> bool:
        cfg = self.config
        key = (cfg.get("whisper_model", "small"), cfg.get("whisper_device", "cpu"))
        if self._whisper_model is not None and self._whisper_key == key:
            return True
        # Evita que dos hilos (la precarga y una orden que llega antes de que
        # termine) carguen el modelo a la vez.
        with self._whisper_lock:
            if self._whisper_model is not None and self._whisper_key == key:
                return True
            try:
                from faster_whisper import WhisperModel
            except ImportError:
                print("❌  faster-whisper no instalado: pip install faster-whisper")
                return False
            msize, dev = key
            model, used = None, None
            if dev in ("cuda", "auto"):
                ok, why = cuda_whisper_available()
                if ok:
                    try:
                        # int8_float16: ~1 GB de memoria de vídeo con «medium» (float16 ocupa
                        # ~2 GB) con la misma precisión y casi la misma velocidad.
                        model = self._load_whisper(WhisperModel, msize, "cuda", "int8_float16")
                        # La 1ª transcripción en GPU inicializa CUDA (~7 s): se hace ya, y de
                        # paso se comprueba que la GPU funciona de verdad.
                        if not self._whisper_warmup(model, timeout=90):
                            raise RuntimeError("la prueba en la GPU no terminó a tiempo")
                        used = "cuda"
                    except Exception as e:
                        print(f"⚠️  Whisper en GPU no disponible ({e}); se usa la CPU")
                        model = None
                else:
                    print(f"ℹ️  Whisper no puede usar la GPU: {why}. Se usa la CPU.")
            if model is None:
                try:
                    model = self._load_whisper(WhisperModel, msize, "cpu", "int8")
                    used = "cpu"
                except Exception as e:
                    print(f"❌  Error cargando whisper: {e}")
                    return False
            # El detector de voz (VAD) se cargaba en la primera orden: se precarga ya.
            # (En CPU una transcripción de prueba no acelera la primera orden; en GPU
            # sí se hace arriba porque sirve para comprobar que CUDA funciona.)
            try:
                from faster_whisper.vad import get_vad_model
                get_vad_model()
            except Exception:
                pass
            self._whisper_model, self._whisper_key = model, key
            self._whisper_device_used = used
            print(f"✅  Whisper '{msize}' listo en {used.upper()}")
            return True

    @staticmethod
    def _load_whisper(WhisperModel, msize: str, device: str, ctype: str):
        t = time.time()
        print(f"⏳  Cargando faster-whisper '{msize}' en {device}...")
        try:      # primero sin conexión: no comprueba actualizaciones en internet
            m = WhisperModel(msize, device=device, compute_type=ctype, local_files_only=True)
        except Exception:
            m = WhisperModel(msize, device=device, compute_type=ctype)   # lo descarga si falta
        print(f"   modelo cargado en {time.time() - t:.1f}s")
        return m

    def _whisper_warmup(self, model, timeout: float = 60) -> bool:
        """Inferencia corta de prueba: inicializa todo antes de la primera orden real."""
        done, errors = threading.Event(), []
        def run():
            try:
                import numpy as np
                dummy = (np.random.RandomState(0).randn(16000) * 0.003).astype(np.float32)
                segs, _ = model.transcribe(
                    dummy, language=self.config.get("whisper_language", "es") or None,
                    beam_size=1, temperature=0.0, vad_filter=False,
                    condition_on_previous_text=False, without_timestamps=True,
                    max_new_tokens=4)
                for _ in segs:
                    pass
            except Exception as e:
                errors.append(e)
            finally:
                done.set()
        threading.Thread(target=run, daemon=True, name="whisper-prueba").start()
        if not done.wait(timeout):
            return False
        if errors:
            raise errors[0]
        return True

    def _record_raw_audio(self, r, mic, phrase_time_limit, timeout=None):
        try:
            with mic as src:
                audio = r.listen(src, timeout=timeout, phrase_time_limit=phrase_time_limit)
            return audio
        except sr.WaitTimeoutError:
            return None
        except Exception as e:
            print(f"[Record] {e}")
            return None

    def _whisper_transcribe(self, audio) -> str:
        if audio is None or not self._ensure_whisper():
            return ""
        try:
            import numpy as np
            raw = audio.get_raw_data(convert_rate=16000, convert_width=2)
            samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
            return self._whisper_transcribe_samples(samples)
        except Exception as e:
            print(f"[Whisper] Error: {e}")
            return ""

    def _whisper_transcribe_samples(self, samples) -> str:
        """Transcribe audio a 16 kHz (numpy float32). Lo usan el micrófono y los audios de WhatsApp."""
        if samples is None or not self._ensure_whisper():
            return ""
        try:
            if samples.size < 3200:                         # < 0,2 s: nada que transcribir
                return ""
            lang = self.config.get("whisper_language", "es") or None
            try:
                beam = max(1, min(5, int(float(self.config.get("whisper_beam_size", 5)))))
            except (TypeError, ValueError):
                beam = 5
            segs, _ = self._whisper_model.transcribe(
                samples, language=lang, beam_size=beam,
                vad_filter=True,
                vad_parameters={"min_silence_duration_ms": 500},
                condition_on_previous_text=False,
                temperature=(0.0, 0.2, 0.4))
            parts = []
            for s in segs:
                txt = (s.text or "").strip()
                if not txt:
                    continue
                if getattr(s, "no_speech_prob", 0.0) > 0.6 and getattr(s, "avg_logprob", 0.0) < -1.0:
                    continue                               # Whisper cree que no era voz
                if is_whisper_hallucination(txt):
                    print(f"[Whisper] Ignorado (alucinación típica): {txt}")
                    continue
                parts.append(txt)
            return " ".join(parts).strip()
        except Exception as e:
            print(f"[Whisper] Error: {e}")
            return ""

    # ── Vosk (modelo en caché: antes se cargaba en CADA frase) ───────────────
    def _vosk_model_dir(self) -> str:
        """Carpeta del modelo de Vosk: la configurada o, si no existe, la que venga con Rubencho."""
        def is_model(d: Path) -> bool:
            return (d / "am").is_dir() and (d / "conf").is_dir()
        path = str(self.config.get("vosk_model_path", "") or "").strip()
        if path and is_model(Path(path)):
            return path
        here = (Path(sys.executable).resolve().parent if getattr(sys, "frozen", False)
                else Path(os.path.abspath(__file__)).parent)
        for base in (here / "modelos", here, here.parent, APP_DIR / "modelos"):
            try:
                for d in sorted(base.glob("vosk-model*")):
                    if is_model(d):
                        return str(d)
            except OSError:
                pass
        return ""

    def _get_vosk_model(self):
        path = self._vosk_model_dir()
        if not path:
            return None
        with self._vosk_lock:
            if self._vosk_model is not None and self._vosk_model_path == path:
                return self._vosk_model
            try:
                from vosk import Model, SetLogLevel
                try:
                    SetLogLevel(-1)
                except Exception:
                    pass
                print(f"⏳  Cargando modelo Vosk: {path}")
                self._vosk_model, self._vosk_model_path = Model(path), path
                print("✅  Vosk listo")
                return self._vosk_model
            except Exception as e:
                print(f"[Vosk] No se pudo cargar el modelo: {e}")
                return None

    def _vosk_transcribe(self, audio):
        """Texto reconocido, o None si Vosk no está disponible (entonces se usa Google)."""
        model = self._get_vosk_model()
        if model is None:
            return None
        try:
            from vosk import KaldiRecognizer
            rec = KaldiRecognizer(model, 16000)
            rec.AcceptWaveform(audio.get_raw_data(convert_rate=16000, convert_width=2))
            return json.loads(rec.FinalResult()).get("text", "")
        except Exception as e:
            print(f"[Vosk] {e}")
            return None

    def _sr_listen(self, r, mic, phrase_time_limit, timeout=None):
        """Escucha una frase corta (palabra clave) y la reconoce con Google o Vosk."""
        try:
            with mic as src:
                audio = r.listen(src, timeout=timeout, phrase_time_limit=phrase_time_limit)
        except sr.WaitTimeoutError:
            return None
        except Exception as e:
            print(f"[SR] {e}")
            time.sleep(0.5)
            return None
        if self.config.get("speech_engine", "google") == "vosk":
            txt = self._vosk_transcribe(audio)
            if txt is not None:
                return txt
        try:
            return r.recognize_google(audio, language=self.config.get("language", "es-ES"))
        except sr.UnknownValueError:
            return ""
        except sr.RequestError as e:
            print(f"[SR] {e}")
            time.sleep(2)
            return None
        except Exception as e:
            print(f"[SR] {e}")
            return None

    # ── Ollama ───────────────────────────────────────────────────────────────
    def _keep_alive(self):
        ka = str(self.config.get("ollama_keep_alive", "30m") or "").strip()
        if not ka:
            return None
        try:
            return int(ka)               # "-1" → -1: mantener siempre cargado
        except ValueError:
            return ka

    def _ollama_body(self, model: str, messages: list, stream: bool,
                     no_think: bool, host: str) -> dict:
        body = {"model": model, "messages": messages, "stream": stream}
        caps = ollama_capabilities(host, model)
        if caps is None:
            if no_think:
                body["think"] = False
        elif "thinking" in caps:         # solo se envía a modelos que razonan
            body["think"] = not no_think
        ka = self._keep_alive()
        if ka is not None:
            body["keep_alive"] = ka
        try:
            num_ctx = int(float(self.config.get("ollama_num_ctx", 0) or 0))
        except (TypeError, ValueError):
            num_ctx = 0
        if num_ctx > 0:
            body["options"] = {"num_ctx": num_ctx}
        return body

    def _ollama_post(self, host: str, body: dict, stream: bool):
        resp = requests.post(f"{host}/api/chat", json=body, timeout=240, stream=stream)
        if resp.status_code != 200 and "think" in body and "think" in (resp.text or "").lower():
            resp.close()
            body = dict(body)
            body.pop("think", None)      # el modelo no admite el parámetro think
            resp = requests.post(f"{host}/api/chat", json=body, timeout=240, stream=stream)
        if resp.status_code != 200:
            raise OllamaError(_ollama_error_message(resp, body.get("model", "")))
        return resp

    def _ollama_chat(self, messages: list, no_think: bool, host: str, model: str) -> str:
        """Llama a Ollama sin streaming y devuelve el texto de respuesta."""
        body = self._ollama_body(model, messages, False, no_think, host)
        resp = self._ollama_post(host, body, stream=False)
        text = (resp.json().get("message") or {}).get("content", "") or ""
        return re.sub(r"<think>.*?</think>", "", text,
                      flags=re.DOTALL | re.IGNORECASE).strip()

    def _system_prompt(self, cfg: dict = None) -> str:
        """Instrucciones completas para la IA (se regeneran en cada mensaje)."""
        cfg = cfg or self.config
        flags = self._flags(cfg)
        return _build_system_prompt(
            cfg.get("system_prompt", ""),
            flags["cmd"],
            wa_enabled=flags["wa"],
            browser_enabled=flags["browser"],
            web_enabled=flags["web"],
            datetime_enabled=bool(cfg.get("datetime_in_messages", True)),
            vision_enabled=flags["vision"],
            memory_enabled=flags["memory"],
            reminders_enabled=flags["reminders"],
            ai_tasks_enabled=flags["ai_tasks"],
            think_auto=(think_mode(cfg) == "auto" and self._model_can_think(
                cfg.get("ollama_host", "http://localhost:11434"), cfg.get("ollama_model", ""))),
            memory_block=self._memory.prompt_block(),
            reminders_block=self._reminders.prompt_block(),
            ai_tasks_block=self._ai_tasks.prompt_block(),
            pc_block=(_pc_system_addon(cfg, flags["cmd"], flags["browser"]) if flags["pc"] else ""),
            wa_block=(_wa_system_addon(cfg) if flags["wa"] else ""),
        )

    @staticmethod
    def _model_can_think(host: str, model: str) -> bool:
        """¿El modelo tiene modo de razonamiento? (si no se sabe, se supone que sí)"""
        caps = ollama_capabilities(host, model)
        return caps is None or "thinking" in caps

    @staticmethod
    def _thinking_messages(msgs: list) -> list:
        """Los mismos mensajes, avisando de que ahora está en modo razonamiento."""
        out = [dict(m) for m in msgs]
        if out and out[0].get("role") == "system" and _THINK_ON_NOTE not in out[0]["content"]:
            out[0]["content"] += _THINK_ON_NOTE
        return out

    @staticmethod
    def _flags(cfg: dict) -> dict:
        return {
            "cmd":       bool(cfg.get("cmd_enabled", True)),
            "web":       bool(cfg.get("web_enabled", True)),
            "browser":   bool(cfg.get("browser_enabled", False)) and _PLAYWRIGHT_AVAILABLE,
            "wa":        bool(cfg.get("whatsapp_enabled", False)),
            "vision":    bool(cfg.get("vision_enabled", True)) and HAS_PIL,
            "memory":    bool(cfg.get("memory_enabled", True)),
            "reminders": bool(cfg.get("reminders_enabled", True)),
            "ai_tasks":  bool(cfg.get("ai_tasks_enabled", True)),
            "pc":        bool(cfg.get("pc_control_enabled", False)) and HAS_PC_INPUT and HAS_PIL,
        }

    @staticmethod
    def _has_followup(text: str, flags: dict) -> bool:
        """¿La respuesta pide una herramienta cuyo resultado debe volver a la IA?"""
        if not text:
            return False
        return bool(
            (flags["cmd"] and _CMD_PATTERN.search(text)) or
            (flags["web"] and (_SEARCH_PATTERN.search(text) or _FETCH_PATTERN.search(text))) or
            (flags["browser"] and _has_web_action(text)) or
            (flags["wa"] and (_WA_PATTERN.search(text) or _WA_SELF_PATTERN.search(text) or
                              _WA_CONTACTS_PAT.search(text) or _WA_READ_PAT.search(text))) or
            (flags["vision"] and (_CAPTURA_PAT.search(text) or _CAMARA_PAT.search(text))) or
            (flags.get("pc") and _PC_ANY_RE.search(text)))

    # ── Herramientas instantáneas: memoria y recordatorios ───────────────────
    def _process_instant_actions(self, text: str, ctx: dict) -> str:
        """
        Ejecuta al momento las etiquetas de memoria y recordatorios (no hace falta
        otra llamada a la IA). Añade una nota visible por cada acción y devuelve
        los errores para que la IA pueda corregirlos.
        """
        flags, notes, done = ctx["flags"], ctx["notes"], ctx["done"]
        errors = []

        def first_time(key) -> bool:
            if key in done:
                return False
            done.add(key)
            return True

        if flags["memory"]:
            for m in _MEM_SAVE_PAT.finditer(text):
                body = _one_line(m.group("body"))
                if not first_time(("mem+", _norm_text(body))):
                    continue
                ok, msg, mid = self._memory.add(body)
                if ok:
                    notes.append(f"🧠 Memoria #{mid}: {body}" + ("" if msg == "guardado" else f" ({msg})"))
                    print(f"🧠  Memoria #{mid} {msg}: {body}")
                else:
                    errors.append(f"<MEMORIA_GUARDAR> → ❌ {msg}")
            for m in _MEM_EDIT_PAT.finditer(text):
                mid, body = _tag_id(m.group("attrs")), _one_line(m.group("body"))
                if not first_time(("mem~", mid, _norm_text(body))):
                    continue
                if mid is None:
                    errors.append('<MEMORIA_EDITAR> → ❌ falta el número: usa id="N"')
                    continue
                ok, msg = self._memory.edit(mid, body)
                if ok:
                    notes.append(f"🧠 Memoria #{mid} modificada: {body}")
                    print(f"🧠  Memoria #{mid} modificada: {body}")
                else:
                    errors.append(f'<MEMORIA_EDITAR id="{mid}"> → ❌ {msg}')
            for m in _MEM_DEL_PAT.finditer(text):
                mid = _tag_id(m.group("attrs"), m.group("body") or "")
                if not first_time(("mem-", mid)):
                    continue
                if mid is None:
                    errors.append('<MEMORIA_BORRAR> → ❌ falta el número: usa id="N"')
                    continue
                ok, msg = self._memory.delete(mid)
                if ok:
                    notes.append(f"🧠 Memoria #{mid} borrada")
                    print(f"🧠  Memoria #{mid} {msg}")
                else:
                    errors.append(f'<MEMORIA_BORRAR id="{mid}"> → ❌ {msg}')

        if flags["reminders"]:
            for m in _REM_ADD_PAT.finditer(text):
                attrs  = _parse_attrs(m.group("attrs"))
                body   = _one_line(m.group("body")) or "Recordatorio"
                cuando = (attrs.get("cuando") or attrs.get("en") or
                          " ".join(x for x in (attrs.get("fecha", ""), attrs.get("hora", "")) if x)).strip()
                rep    = attrs.get("repetir", "")
                if not first_time(("rec+", _norm_text(body), _norm_text(cuando), _norm_text(rep))):
                    continue
                try:
                    when = parse_when(cuando)
                    r = self._reminders.add(body, when, rep)
                    left = duracion_humana(when - datetime.now())
                    notes.append(f"⏰ Recordatorio #{r['id']}: {self._reminders.describe(r)} — "
                                 f"{body} (dentro de {left})")
                    print(f"⏰  Recordatorio #{r['id']} → {when:%Y-%m-%d %H:%M}: {body}")
                except ValueError as e:
                    errors.append(
                        f'<RECORDATORIO cuando="{cuando}"> → ❌ NO se ha programado: {e}. '
                        'Vuelve a escribir la etiqueta con un "cuando" válido, por ejemplo '
                        '"+10m", "mañana 9:00", "viernes 17:00" o "2026-12-24 20:00".')
            for m in _REM_DEL_PAT.finditer(text):
                rid = _tag_id(m.group("attrs"), m.group("body") or "")
                if not first_time(("rec-", rid)):
                    continue
                if rid is None:
                    errors.append('<RECORDATORIO_BORRAR> → ❌ falta el número: usa id="N"')
                    continue
                ok, msg = self._reminders.delete(rid)
                if ok:
                    notes.append(f"⏰ Recordatorio #{rid} borrado")
                else:
                    errors.append(f'<RECORDATORIO_BORRAR id="{rid}"> → ❌ {msg}')

        if flags["ai_tasks"]:
            for m in _TASK_ADD_PAT.finditer(text):
                attrs  = _parse_attrs(m.group("attrs"))
                body   = _one_line(m.group("body"))
                cuando = (attrs.get("cuando") or attrs.get("en") or
                          " ".join(x for x in (attrs.get("fecha", ""), attrs.get("hora", "")) if x)).strip()
                rep    = attrs.get("repetir", "")
                if not first_time(("tarea+", _norm_text(body), _norm_text(cuando), _norm_text(rep))):
                    continue
                if not body:
                    errors.append('<TAREA> → ❌ está vacía: escribe dentro qué tienes que hacer.')
                    continue
                try:
                    when = parse_when(cuando)
                    # Lo que dijo el usuario, para tener el contexto cuando llegue la hora
                    pedido = "" if ctx.get("origin") == "tarea" else _one_line(ctx.get("prompt", ""))[:300]
                    t = self._ai_tasks.add(body, when, rep, extra={"pedido": pedido} if pedido else None)
                    left = duracion_humana(when - datetime.now())
                    notes.append(f"🤖 Tarea #{t['id']}: {self._ai_tasks.describe(t)} — "
                                 f"{body} (dentro de {left})")
                    print(f"🤖  Tarea #{t['id']} → {when:%Y-%m-%d %H:%M}: {body}")
                except ValueError as e:
                    errors.append(
                        f'<TAREA cuando="{cuando}"> → ❌ NO se ha programado: {e}. '
                        'Vuelve a escribir la etiqueta con un "cuando" válido, por ejemplo '
                        '"+10m", "mañana 9:00", "viernes 17:00" o "2026-12-24 20:00".')
            for m in _TASK_DEL_PAT.finditer(text):
                tid = _tag_id(m.group("attrs"), m.group("body") or "")
                if not first_time(("tarea-", tid)):
                    continue
                if tid is None:
                    errors.append('<TAREA_BORRAR> → ❌ falta el número: usa id="N"')
                    continue
                ok, msg = self._ai_tasks.delete(tid)
                if ok:
                    notes.append(f"🤖 Tarea #{tid} borrada")
                else:
                    errors.append(f'<TAREA_BORRAR id="{tid}"> → ❌ {msg}')
        return "\n".join(errors)

    # ── Herramientas con resultado (CMD, web, navegador, WhatsApp, visión) ──
    def _execute_followup_actions(self, text: str, ctx: dict):
        """Ejecuta las etiquetas cuyo resultado hay que devolver a la IA. → (texto, [imágenes b64])"""
        flags   = ctx["flags"]
        results = []
        images  = []
        post    = lambda s: self._ui_q.put(("popup_chunk", s))

        if flags["cmd"]:
            for raw_cmd in _CMD_PATTERN.findall(text):
                cmd = raw_cmd.strip()
                print(f"⚙️   CMD: {cmd}")
                post(f"⚙️  Ejecutando: `{cmd}`\n")
                result = execute_command(cmd)
                results.append(f"<CMD>{cmd}</CMD>\n<RESULTADO>\n{result}\n</RESULTADO>")
                print(f"     → {result[:160]}{'…' if len(result)>160 else ''}")

        if flags["web"]:
            for raw_q in _SEARCH_PATTERN.findall(text):
                query = raw_q.strip()
                print(f"🔍   SEARCH: {query}")
                post(f"🔍  Buscando: *{query}*\n")
                results.append(f"<SEARCH>{query}</SEARCH>\n<RESULTADO_WEB>\n{web_search(query)}\n</RESULTADO_WEB>")
            for raw_url in _FETCH_PATTERN.findall(text):
                url = raw_url.strip()
                print(f"🌐   FETCH: {url}")
                post(f"🌐  Leyendo: {url}\n")
                results.append(f"<FETCH>{url}</FETCH>\n<RESULTADO_WEB>\n{web_fetch(url)}\n</RESULTADO_WEB>")

        if flags["browser"] and _has_web_action(text):
            web_result = _execute_web_actions(text, self._ui_q)
            if web_result:
                results.append(web_result)

        if flags["wa"]:
            wa_res, wa_imgs = self._wa_actions(text, ctx)
            results += wa_res
            images += wa_imgs

        if flags["vision"]:
            m = _CAPTURA_PAT.search(text)
            if m:
                todas = "tod" in _norm_text(_parse_attrs(m.group("attrs")).get("pantalla", ""))
                res, img = self._do_capture("pantalla", ctx, all_screens=todas)
                results.append(res)
                if img:
                    images.append(img)
            if _CAMARA_PAT.search(text):
                res, img = self._do_capture("camara", ctx)
                results.append(res)
                if img:
                    images.append(img)

        if flags.get("pc") and _PC_ANY_RE.search(text):
            res, img = self._pc_run(text, ctx)
            results.append(res)
            if img:
                images.append(img)

        return "\n\n".join(results), images

    # ── WhatsApp: contactos, lectura y envío (solo cuando lo pide el usuario) ─
    def _wa_contacts_cached(self, port: int, max_age: float = 60) -> list:
        cache = getattr(self, "_wa_contacts_cache", None)
        if cache and time.time() - cache[0] < max_age:
            return cache[1]
        lst = wa_contacts(port=port)
        if lst:
            self._wa_contacts_cache = (time.time(), lst)
        return lst

    def _wa_can_write(self, contact: dict) -> bool:
        cfg = self.config
        if cfg.get("whatsapp_send_all", False):
            return True
        return contact.get("jid") in set(cfg.get("whatsapp_allowed_contacts") or [])

    def _wa_find(self, who: str, port: int):
        """→ (contacto, texto de error para la IA | None)"""
        contacts = self._wa_contacts_cached(port)
        if not contacts:
            st = wa_status(port=port)
            if not st.get("connected"):
                return None, "❌ WhatsApp no está conectado (el puente no responde o falta vincularlo)."
            if st.get("needs_relink"):
                return None, ("❌ No tengo la lista de contactos: WhatsApp no la envía con la "
                              "vinculación actual. Dile al usuario que vuelva a vincular WhatsApp "
                              "una vez (Configuración → WhatsApp → «Volver a vincular» y escanear el QR).")
            return None, ("❌ Todavía no tengo la lista de contactos. El usuario puede pulsar "
                          "«Actualizar contactos» en Configuración → WhatsApp.")
        c, cands = wa_match_contact(who, contacts)
        if c:
            return c, None
        if cands:
            names = ", ".join(f"«{x['name']}»" for x in cands[:12])
            return None, (f"❌ Hay varios contactos que encajan con «{who}»: {names}. "
                          "Pregunta al usuario a cuál se refiere.")
        return None, (f"❌ No encuentro a «{who}» en los contactos. Mira la lista con "
                      "<WA_CONTACTOS/> o pregunta al usuario cómo lo tiene guardado.")

    def _wa_list_contacts(self, attrs: dict, port: int) -> str:
        contacts = self._wa_contacts_cached(port, max_age=10)
        if not contacts:
            _c, err = self._wa_find("x", port)
            return err or "❌ No hay contactos."
        q = _norm_text(_parse_attrs(attrs).get("buscar", "") or _parse_attrs(attrs).get("nombre", ""))
        lst = [c for c in contacts if c.get("name") and (not q or q in _norm_text(c["name"]))]
        if not lst:
            return f"No hay ningún contacto que contenga «{q}»."
        names = lambda xs: ", ".join(c["name"] for c in xs)
        if self.config.get("whatsapp_send_all", False):
            return (f"Contactos ({len(lst)}): {names(lst)}\n"
                    "Puedes escribir a cualquiera de ellos.")
        ok = [c for c in lst if self._wa_can_write(c)]
        rest = [c for c in lst if not self._wa_can_write(c)]
        out = [f"Contactos a los que PUEDES escribir ({len(ok)}): {names(ok) or 'ninguno todavía'}"]
        if rest:
            out.append(f"Otros contactos (puedes leer sus mensajes, pero no escribirles) "
                       f"({len(rest)}): {names(rest)}")
        if not ok:
            out.append("El usuario elige a quién puedes escribir en Configuración → WhatsApp.")
        return "\n".join(out)

    def _wa_transcribe(self, b64: str, mimetype: str, msg_id: str) -> Tuple[Optional[str], str]:
        """Transcribe un audio de WhatsApp con Whisper. → (texto | None, error)"""
        store = APP_DIR / "whatsapp_store"
        cache_file = store / "transcripciones.json"
        if not hasattr(self, "_wa_tr_cache"):
            self._wa_tr_cache = _read_json(cache_file, {}) if cache_file.exists() else {}
        if msg_id in self._wa_tr_cache:
            return self._wa_tr_cache[msg_id], ""
        if not self._ensure_whisper():
            return None, "Whisper no está disponible"
        import tempfile
        ext = ".ogg" if "ogg" in (mimetype or "") else (".m4a" if "mp4" in (mimetype or "") else ".audio")
        tmp = Path(tempfile.gettempdir()) / f"rubencho_wa_{msg_id[:16]}{ext}"
        try:
            tmp.write_bytes(base64.b64decode(b64))
            from faster_whisper import decode_audio
            samples = decode_audio(str(tmp), sampling_rate=16000)
            text = self._whisper_transcribe_samples(samples)
        except Exception as e:
            return None, f"no se pudo transcribir ({e})"
        finally:
            try:
                tmp.unlink()
            except Exception:
                pass
        text = text or "(no se entiende nada / no hay voz)"
        self._wa_tr_cache[msg_id] = text
        try:
            store.mkdir(parents=True, exist_ok=True)
            if len(self._wa_tr_cache) > 800:
                self._wa_tr_cache = dict(list(self._wa_tr_cache.items())[-600:])
            _atomic_write_json(cache_file, self._wa_tr_cache)
        except Exception:
            pass
        return text, ""

    def _wa_show_image(self, img, msg_id: str):
        """Miniatura en el popup (la foto se guarda en whatsapp_store/vistas para abrirla)."""
        try:
            d = APP_DIR / "whatsapp_store" / "vistas"
            d.mkdir(parents=True, exist_ok=True)
            path = d / f"{msg_id[:24]}.jpg"
            img.save(path, "JPEG", quality=90)
            files = sorted(d.glob("*.jpg"), key=lambda p: p.stat().st_mtime, reverse=True)
            for old in files[40:]:
                try:
                    old.unlink()
                except Exception:
                    pass
            thumb = img.copy()
            thumb.thumbnail((300, 170))
            self._ui_q.put(("popup_image", (thumb, path)))
        except Exception as e:
            print(f"[WA] Miniatura: {e}")

    def _wa_read(self, attrs: str, body: str, ctx: dict, port: int) -> Tuple[str, list]:
        """<WA_LEER contacto="…" cantidad="N"/> → (texto para la IA, [imágenes b64])"""
        cfg  = self.config
        post = lambda s: self._ui_q.put(("popup_chunk", s))
        a = _parse_attrs(attrs)
        who = (a.get("contacto") or a.get("de") or a.get("nombre") or a.get("chat") or body or "").strip()
        tag = f'<RESULTADO_WA_LEER contacto="{who}">'
        if not cfg.get("whatsapp_read_enabled", True):
            return (f"{tag}\n❌ El usuario ha desactivado la lectura de mensajes "
                    f"(Configuración → WhatsApp).\n</RESULTADO_WA_LEER>"), []
        if not who:
            return f"{tag}\n❌ Falta el contacto: contacto=\"Nombre\".\n</RESULTADO_WA_LEER>", []
        try:
            mx = max(1, int(float(cfg.get("whatsapp_read_max", 20) or 20)))
        except (TypeError, ValueError):
            mx = 20
        try:
            want = int(float(re.sub(r"[^\d.]", "", a.get("cantidad") or a.get("n") or "5") or 5))
        except ValueError:
            want = 5
        n = max(1, min(want, mx))
        c, err = self._wa_find(who, port)
        if not c:
            return f"{tag}\n{err}\n</RESULTADO_WA_LEER>", []
        name = c["name"]
        post(f"📖  Leyendo los últimos mensajes de {name}…\n")
        print(f"[WA] Leyendo {n} mensajes de {name}")
        h = wa_history(c["jid"], n, port=port)
        if not h.get("ok"):
            return (f'<RESULTADO_WA_LEER contacto="{name}">\n❌ No se pudieron leer: '
                    f'{h.get("error", "error desconocido")}\n</RESULTADO_WA_LEER>'), []
        msgs = h.get("messages") or []
        if not msgs:
            return (f'<RESULTADO_WA_LEER contacto="{name}">\nNo hay mensajes guardados del chat con '
                    f'{name}. (Rubencho solo puede leer los mensajes que han llegado mientras el '
                    f'puente de WhatsApp estaba en marcha.)\n</RESULTADO_WA_LEER>'), []

        caps = ollama_capabilities(ctx["host"], ctx["model"])
        can_see = (caps is None or "vision" in caps) and bool(cfg.get("whatsapp_read_images", True))
        hear = bool(cfg.get("whatsapp_read_audio", True))
        # Las fotos más recientes primero (máximo 4 por lectura)
        img_ids = [m["id"] for m in reversed(msgs)
                   if m.get("media") and m.get("kind") in ("imageMessage", "stickerMessage")][:4]
        images, lines, n_img = [], [], 0
        for m in msgs:
            who_m = "Tú" if m.get("fromMe") else name
            try:
                when = fecha_corta(datetime.fromtimestamp(float(m.get("ts", 0)) / 1000))
            except Exception:
                when = "?"
            kind, cap = m.get("kind", ""), (m.get("caption") or "").strip()
            cap_s = f" «{cap}»" if cap else ""
            if kind in ("conversation", "extendedTextMessage"):
                txt = (m.get("text") or "").strip() or "(mensaje vacío)"
            elif kind in ("imageMessage", "stickerMessage"):
                label = "📷 Foto" if kind == "imageMessage" else "🙂 Sticker"
                txt = f"{label}{cap_s}"
                if can_see and m["id"] in img_ids:
                    r = wa_media(c["jid"], m["id"], port=port)
                    if r.get("ok"):
                        try:
                            img = Image.open(io.BytesIO(base64.b64decode(r["base64"]))).convert("RGB")
                            images.append(_image_to_b64_jpeg(img, max_side=1280))
                            n_img += 1
                            txt += f" [imagen {n_img} adjunta]"
                            self._wa_show_image(img, m["id"])
                        except Exception as e:
                            txt += f" (no se pudo abrir: {e})"
                    else:
                        txt += f" (no se pudo descargar: {r.get('error', '')})"
                elif m.get("media") and not can_see:
                    txt += " (no puedo ver imágenes)"
                else:
                    txt += " (foto antigua: no adjunta)"
            elif kind == "audioMessage":
                secs = int(m.get("seconds") or 0)
                dur = f" de {secs // 60}:{secs % 60:02d}" if secs else ""
                txt = f"🎤 Audio{dur}"
                if hear and m.get("media"):
                    post(f"🎧  Escuchando un audio de {who_m if who_m != 'Tú' else 'ti'}…\n")
                    r = wa_media(c["jid"], m["id"], port=port)
                    if r.get("ok"):
                        t, e = self._wa_transcribe(r["base64"], r.get("mimetype", ""), m["id"])
                        txt += f" → transcripción: «{t}»" if t else f" ({e})"
                    else:
                        txt += f" (no se pudo descargar: {r.get('error', '')})"
                elif not hear:
                    txt += " (la escucha de audios está desactivada)"
            elif kind in ("videoMessage", "ptvMessage"):
                txt = f"🎬 Vídeo{cap_s} (no puedo ver vídeos)"
            elif kind == "documentMessage":
                txt = f"📄 Documento «{m.get('fileName') or 'sin nombre'}»{cap_s}"
            elif kind == "contactMessage":
                txt = f"👤 Contacto compartido «{m.get('text') or ''}»"
            elif kind in ("locationMessage", "liveLocationMessage"):
                txt = "📍 Ubicación" + (f" «{m['text']}»" if m.get("text") else "")
            elif kind.startswith("pollCreationMessage"):
                txt = f"📊 Encuesta «{m.get('text') or ''}»"
            else:
                txt = (m.get("text") or "").strip() or f"(mensaje de tipo {kind})"
            lines.append(f"[{when}] {who_m}: {txt}")
        head = (f"Últimos {len(msgs)} mensajes del chat con {name} (del más antiguo al más "
                f"reciente; «Tú» es el usuario):")
        tail = []
        if len(msgs) < n:
            tail.append(f"(Solo hay {len(msgs)} mensajes guardados de este chat.)")
        if want > mx:
            tail.append(f"(Pediste {want}, pero el usuario ha puesto un máximo de {mx}.)")
        if images:
            tail.append("La foto va adjunta a este mensaje." if len(images) == 1 else
                        f"Las {len(images)} fotos van adjuntas a este mensaje, en el mismo orden.")
        ctx["notes"].append(f"📖 Leídos {len(msgs)} mensajes de {name}")
        return (f'<RESULTADO_WA_LEER contacto="{name}">\n{head}\n' + "\n".join(lines) +
                ("\n" + "\n".join(tail) if tail else "") + "\n</RESULTADO_WA_LEER>"), images

    def _wa_confirm_send(self, name: str, msg: str, ctx: dict) -> bool:
        """Pide permiso antes de enviar (si está activado y la orden no viene del propio WhatsApp)."""
        if not self.config.get("whatsapp_confirm_send", True) or ctx.get("origin") == "whatsapp" \
                or ctx.get("wa_allow_all"):
            return True
        # Una tarea programada: se lo pediste al programarla y puede que no estés delante
        if ctx.get("origin") == "tarea" and not self.config.get("ai_tasks_confirm", False):
            return True
        evt, holder = threading.Event(), {}
        short = msg if len(msg) <= 160 else msg[:157] + "…"
        play_sound("confirmar")
        self._ui_q.put(("pc_confirm", (f"Enviar un WhatsApp a {name}:\n«{short}»",
                                       "vas a enviar un mensaje en tu nombre (esta pregunta se "
                                       "quita en Configuración → WhatsApp)", holder, evt)))
        evt.wait(PcConfirmDialog.TIMEOUT + 10)
        ans = holder.get("ans", "no")
        if ans == "todo":
            ctx["wa_allow_all"] = True
        return ans in ("si", "todo")

    def _wa_send_to(self, who: str, msg: str, ctx: dict, port: int) -> str:
        c, err = self._wa_find(who, port)
        if not c:
            return err
        name = c["name"]
        if not self._wa_can_write(c):
            return (f"❌ No tienes permiso para escribir a «{name}». Díselo al usuario: puede "
                    f"permitirlo en Configuración → WhatsApp → Contactos.")
        if not msg.strip():
            return "❌ El mensaje está vacío."
        if not self._wa_confirm_send(name, msg, ctx):
            return f"🚫 El usuario NO ha querido enviar el mensaje a {name}. No lo reenvíes."
        self._ui_q.put(("popup_chunk", f"\n📱  Enviando WhatsApp a {name}…\n"))
        r = _wa_request("send", method="POST", body={"to": c["jid"], "message": msg}, port=port)
        if r.get("ok"):
            ctx["notes"].append(f"📱 WhatsApp a {name}: {_one_line(msg)[:70]}")
            return f"✅ Mensaje enviado a {name}."
        return f"❌ No se pudo enviar a {name}: {r.get('error', 'error desconocido')}"

    def _wa_actions(self, text: str, ctx: dict) -> Tuple[list, list]:
        """Herramientas de WhatsApp de una respuesta. → ([resultados], [imágenes b64])"""
        port = int(self.config.get("whatsapp_bridge_port", 3847))
        post = lambda s: self._ui_q.put(("popup_chunk", s))
        results, images = [], []
        for m in _WA_CONTACTS_PAT.finditer(text):
            post("👥  Consultando tus contactos…\n")
            results.append(f"<RESULTADO_WA_CONTACTOS>\n{self._wa_list_contacts(m.group('attrs'), port)}"
                           f"\n</RESULTADO_WA_CONTACTOS>")
        for m in _WA_READ_PAT.finditer(text):
            res, imgs = self._wa_read(m.group("attrs"), m.group("body") or "", ctx, port)
            results.append(res)
            images += imgs
        for m in _WA_SELF_PATTERN.finditer(text):
            msg = m.group(1).strip()
            print(f"[WA] Enviando a mí mismo: {msg[:60]}…")
            post("\n📱  Enviando WA a ti mismo…\n")
            res = wa_send_self(msg, port=port)
            results.append(f"<WA_SELF>\n{msg}\n</WA_SELF>\n<RESULTADO_WA>\n{res}\n</RESULTADO_WA>")
        for m in _WA_PATTERN.finditer(text):
            to, msg = m.group(1).strip(), m.group(2).strip()
            print(f"[WA] Enviando a '{to}': {len(msg)} caracteres")
            res = self._wa_send_to(to, msg, ctx, port)
            results.append(f'<WA to="{to}">\n{msg}\n</WA>\n<RESULTADO_WA>\n{res}\n</RESULTADO_WA>')
        return results, images

    # ── Visión ───────────────────────────────────────────────────────────────
    def _grab_screen(self, all_screens: bool):
        """Captura la pantalla ocultando antes el orbe y el popup (si está configurado)."""
        hide = bool(self.config.get("vision_hide_windows", True))
        if hide:
            evt = threading.Event()
            self._ui_q.put(("hide_for_capture", evt))
            evt.wait(2.0)
        try:
            return capture_screen(all_screens)
        finally:
            if hide:
                self._ui_q.put(("restore_after_capture", None))

    def _hide_for_capture(self, evt: threading.Event):
        self._capture_restore = False
        if self._popup_alive():
            try:
                self._popup_alpha = float(self._popup.wm_attributes("-alpha"))
                self._popup.wm_attributes("-alpha", 0.0)
                self._capture_restore = True
            except Exception:
                pass
        if self._orb:
            self._orb.suspend(True)
        try:
            self.root.update_idletasks()
        except Exception:
            pass
        self.root.after(250, evt.set)       # da tiempo a Windows a repintar lo de debajo

    def _restore_after_capture(self):
        if self._orb:
            self._orb.suspend(False)
        if self._capture_restore and self._popup_alive():
            try:
                self._popup.wm_attributes("-alpha", self._popup_alpha or
                                          float(self.config.get("popup_opacity", 0.94)))
            except Exception:
                pass
        self._capture_restore = False

    def _do_capture(self, kind: str, ctx: dict, all_screens: bool = False):
        """Hace la captura y prepara el resultado para la IA. → (texto, imagen_b64 | None)"""
        cfg  = self.config
        post = lambda s: self._ui_q.put(("popup_chunk", s))
        tag  = f'<RESULTADO_CAPTURA tipo="{kind}">'
        try:
            if kind == "pantalla":
                post("📸  Capturando la pantalla…\n")
                img, desc = self._grab_screen(all_screens)
            else:
                post("📷  Haciendo una foto con la cámara…\n")
                img, desc = capture_camera(int(float(cfg.get("camera_index", 0) or 0)))
        except Exception as e:
            print(f"[Captura] {e}")
            return f"{tag}\n❌ No se pudo hacer la captura: {e}\n</RESULTADO_CAPTURA>", None
        print(f"📸  {kind}: {desc} {img.size[0]}x{img.size[1]}")

        path = save_capture(img, kind, int(cfg.get("captures_keep", 30)))
        try:
            thumb = img.copy()
            thumb.thumbnail((300, 170))
            self._ui_q.put(("popup_image", (thumb, path)))
        except Exception:
            pass

        b64 = _image_to_b64_jpeg(img, max_side=int(cfg.get("vision_max_side", 1600)))
        what = "Captura de pantalla" if kind == "pantalla" else "Foto de la cámara web"
        header = (f"{what} ({desc}, {img.size[0]}×{img.size[1]} px) tomada a las "
                  f"{datetime.now():%H:%M:%S}" + (f" y guardada en {path}" if path else ""))
        host, main_model = ctx["host"], ctx["model"]
        vision_model = str(cfg.get("vision_model", "") or "").strip()

        if vision_model and vision_model != main_model:
            post(f"👁  Analizando la imagen con {vision_model}…\n")
            try:
                description = self._describe_image(b64, kind, ctx["prompt"], vision_model, host)
                return (f"{tag}\n{header}.\nDescripción detallada de la imagen (hecha por el modelo "
                        f"de visión):\n{description}\n</RESULTADO_CAPTURA>"), None
            except Exception as e:
                return (f"{tag}\n{header}.\n❌ El modelo de visión '{vision_model}' falló: {e}\n"
                        f"</RESULTADO_CAPTURA>"), None

        caps = ollama_capabilities(host, main_model)
        if caps is not None and "vision" not in caps:
            return (f"{tag}\n{header}.\n❌ Tu modelo actual ({main_model}) no puede ver imágenes. "
                    "Explícale al usuario que elija un modelo con visión en Configuración → Visión."
                    "\n</RESULTADO_CAPTURA>"), None
        return (f"{tag}\n{header}. La imagen va adjunta a este mensaje: analízala para "
                f"responder a lo que pidió el usuario.\n</RESULTADO_CAPTURA>"), b64

    def _describe_image(self, b64: str, kind: str, prompt: str, model: str, host: str) -> str:
        what = ("una captura de pantalla del PC del usuario" if kind == "pantalla"
                else "una foto hecha con la cámara web del usuario")
        msgs = [{"role": "user", "images": [b64], "content": (
            f"Esta imagen es {what}. El usuario ha pedido: «{prompt}».\n"
            "Describe con detalle todo lo relevante para esa petición: programas y ventanas "
            "abiertos, texto visible (transcríbelo literalmente si es importante), personas, "
            "objetos, colores y cualquier error o aviso. Responde en español.")}]
        return self._ollama_chat(msgs, True, host, model)

    # ── Control del PC ───────────────────────────────────────────────────────
    def _ui_sync(self, fn, timeout: float = 3.0):
        """Ejecuta fn en el hilo de Tk y espera el resultado (desde otro hilo)."""
        if threading.current_thread() is threading.main_thread():
            return fn()
        evt, holder = threading.Event(), {}
        self._ui_q.put(("ui_call", (fn, evt, holder)))
        evt.wait(timeout)
        return holder.get("r")

    def _pc_hooks(self) -> dict:
        def confirm(action, reason):
            evt, holder = threading.Event(), {}
            self._ui_q.put(("pc_confirm", (action, reason, holder, evt)))
            evt.wait(PcConfirmDialog.TIMEOUT + 10)
            return holder.get("ans", "no")
        return {
            "protect": lambda on: self._ui_sync(lambda: self._pc_protect(on)),
            "banner":  lambda text: self._ui_q.put(("pc_banner", text)),
            "confirm": confirm,
            "post":    lambda text: self._ui_q.put(("popup_chunk", text)),
        }

    def _pc_protect(self, on: bool):
        """Orbe, popup y avisos: fuera de las capturas y sin estorbar a los clics de la IA."""
        for w, through in ((self._orb, True),
                           (self._popup if self._popup_alive() else None, True),
                           (self._pc_banner, False), (self._pc_dialog, False)):
            if w is None:
                continue
            try:
                if not w.winfo_exists():
                    continue
                _tk_exclude_from_capture(w, on)
                if through:
                    _tk_click_through(w, on)
            except Exception:
                pass
        try:
            self.root.update_idletasks()
        except Exception:
            pass

    def _pc_set_banner(self, text):
        sess = self._pc_session
        if text is None or sess is None:
            if self._pc_banner is not None:
                try:
                    self._pc_banner.destroy()
                except Exception:
                    pass
                self._pc_banner = None
            return
        if not self.config.get("pc_show_banner", True):
            return
        try:
            if self._pc_banner is None or not self._pc_banner.winfo_exists():
                self._pc_banner = PcBanner(self.root, self.config, sess.monitor)
            self._pc_banner.set_text(text)
        except Exception as e:
            print(f"[PC] Aviso: {e}")

    def _pc_show_confirm(self, action, reason, holder, evt):
        def done(ans):
            self._pc_dialog = None
            holder["ans"] = ans
            evt.set()
        try:
            self._pc_dialog = PcConfirmDialog(self.root, action, reason, done)
        except Exception as e:
            print(f"[PC] Confirmación: {e}")
            done("no")

    def _pc_toggle(self):
        on = not bool(self.config.get("pc_control_enabled", False))
        self.config["pc_control_enabled"] = on
        save_config(self.config)
        if not on and self._pc_session is not None:
            self._pc_session.request_stop("has desactivado el control del PC")
        self._tray_refresh()
        self._notify("Rubencho AI", "🖱  Control del PC activado: la IA puede usar el ratón y el teclado."
                     if on else "🖱  Control del PC desactivado.")

    def _tray_refresh(self):
        if self._tray is not None:
            try:
                self._tray.update_menu()
            except Exception:
                pass

    def _pc_run(self, text: str, ctx: dict):
        """Ejecuta las acciones de control del PC de una respuesta. → (resultado, imagen b64)"""
        post = lambda s: self._ui_q.put(("popup_chunk", s))
        sess = ctx.get("pc")
        if sess is None:
            sess = PcController(self.config, self._pc_hooks())
            self._pc_session = sess
            ok, msg = sess.start()
            if not ok:
                self._pc_session = None
                ctx["flags"] = dict(ctx["flags"], pc=False)
                return f"<RESULTADO_PC>\n❌ No puedo controlar el PC: {msg}\n</RESULTADO_PC>", None
            ctx["pc"] = sess
            self._ui_q.put(("tray_refresh", None))
            hk = str(self.config.get("pc_stop_hotkey", "esc")).strip().upper()
            hint = (f" — pulsa {hk} para detenerlo" if self.config.get("pc_stop_hotkey_enabled", True)
                    and hk else "")
            post(f"🖱  *Controlando el PC{hint}*\n")
            print("🖱  [PC] Sesión de control iniciada")
        caps = ollama_capabilities(ctx["host"], ctx["model"])
        can_see = caps is None or "vision" in caps
        actions = parse_pc_actions(text)
        print(f"🖱  [PC] {len(actions)} acciones: " + ", ".join(a["tag"][3:] for a in actions))
        res, img = sess.run(actions, can_see=can_see)
        return f"<RESULTADO_PC>\n{res}\n</RESULTADO_PC>", img

    def _pc_finish(self, ctx: dict):
        sess = ctx.get("pc")
        if sess is None:
            return
        try:
            sess.stop()
        except Exception as e:
            print(f"[PC] {e}")
        if self._pc_session is sess:
            self._pc_session = None
        self._ui_q.put(("tray_refresh", None))
        if getattr(sess, "last_image", None) is not None:
            save_capture(sess.last_image, "control", int(self.config.get("captures_keep", 30)))
        n = sess.actions_done
        acc = f"{n} acción" if n == 1 else f"{n} acciones"
        if sess.stop_event.is_set():
            ctx["notes"].append(f"⛔ Control del PC detenido ({sess.stop_reason}) tras {acc}")
        else:
            ctx["notes"].append(f"🖱 Control del PC: {acc}")
        print(f"🖱  [PC] Sesión terminada: {acc}")

    # ── Bucle agente ─────────────────────────────────────────────────────────
    def _run_agentic_loop(self, first_response: str, messages: list,
                          host: str, model: str, no_think: bool,
                          ctx: dict, max_iterations: int = 10) -> str:
        """
        Mientras la IA use herramientas, se ejecutan, se le devuelven los resultados
        (con las capturas adjuntas como imágenes) y se le vuelve a preguntar.
        La memoria y los recordatorios se aplican al momento en cada respuesta.
        Termina cuando la respuesta ya no pide más herramientas.
        """
        current       = first_response
        turn_messages = list(messages)
        iteration     = 0
        post          = lambda s: self._ui_q.put(("popup_chunk", s))
        if ctx["flags"].get("pc"):
            try:
                max_iterations = max(max_iterations,
                                     int(float(self.config.get("pc_max_steps", 25) or 25)))
            except (TypeError, ValueError):
                pass

        while True:
            if ctx.get("think_auto") and not ctx.get("thinking") and _THINK_PAT.search(current):
                ctx["thinking"], no_think = True, False
                print("💭  La IA ha decidido pensar los siguientes pasos")
                post("\n💭 *Lo pienso con calma…*\n")
                turn_messages = self._thinking_messages(turn_messages)
                current = self._ollama_chat(turn_messages, no_think, host, model)
                continue
            errors = self._process_instant_actions(current, ctx)
            needs  = self._has_followup(current, ctx["flags"])
            if not needs and not errors:
                break
            if iteration >= max_iterations:
                warn = f"\n\n⚠️ *[Límite de {max_iterations} pasos alcanzado.]*"
                current += warn
                post(warn)
                break
            pc = ctx.get("pc")
            if pc is not None and pc.stop_event.is_set() and ctx.get("pc_stop_told"):
                break                     # ya se le dijo que parara y sigue pidiendo acciones
            iteration += 1
            ctx.setdefault("trace", []).extend(action_tags(current))   # para el historial
            sep = "─" * 38
            post(f"\n{sep}\n🔄  *Paso {iteration}*\n")
            print(f"🔄  [Agente] Paso {iteration}/{max_iterations}")

            results, images = self._execute_followup_actions(current, ctx) if needs else ("", [])
            parts = []
            if results:
                parts.append("Aquí están los resultados de las acciones ejecutadas en este paso:\n\n"
                             + results)
            if errors:
                parts.append("⚠️ Estas etiquetas NO se pudieron aplicar:\n" + errors)
            if ctx.get("think_auto") and not ctx.get("thinking") and (errors or "❌" in results):
                parts.append("(Si ves que esto es más difícil de lo que parecía, escribe solo <PENSAR/> "
                             "y podrás pensar con calma los siguientes pasos.)")
            followup = ("\n\n".join(parts) +
                        "\n\nSi necesitas más pasos para completar la tarea del usuario (más "
                        "comandos, búsquedas, capturas o acciones), hazlo ahora. Cuando hayas "
                        "terminado, responde al usuario de forma clara y natural sin etiquetas de "
                        "herramientas (salvo memoria o recordatorios si de verdad hacen falta).")
            user_msg = {"role": "user", "content": followup}
            if images:
                user_msg["images"] = images
                turn_messages = self._prune_old_images(turn_messages)
            turn_messages = turn_messages + [
                {"role": "assistant", "content": current},
                user_msg,
            ]
            pc = ctx.get("pc")
            if pc is not None and pc.stop_event.is_set():
                ctx["pc_stop_told"] = True
                ctx["flags"] = dict(ctx["flags"], pc=False)    # no más acciones de control
            post(f"{sep}\n")
            if pc is not None and pc.observations:
                self._ui_q.put(("pc_banner", "Pensando…"))
            current = self._ollama_chat(turn_messages, no_think, host, model)
        return current

    @staticmethod
    def _prune_old_images(msgs: list, keep: int = 1) -> list:
        """
        Para no llenar el contexto en tareas largas: solo las `keep` últimas capturas
        siguen adjuntas y las listas de elementos antiguas se resumen.
        """
        out, seen = [], 0
        for m in reversed(msgs):
            if m.get("images"):
                seen += 1
                if seen > keep:
                    m = {k: v for k, v in m.items() if k != "images"}
                    m["content"] = re.sub(r"<ELEMENTOS>.*?</ELEMENTOS>",
                                          "(lista de elementos antigua omitida)",
                                          m.get("content", ""), flags=re.DOTALL)
            out.append(m)
        return list(reversed(out))

    # ── WhatsApp ─────────────────────────────────────────────────────────────
    def _start_whatsapp(self):
        port = int(self.config.get("whatsapp_bridge_port", 3847))
        # El bridge solo arranca si autostart está activado; el hilo de escucha
        # arranca SIEMPRE que WhatsApp esté habilitado
        if self.config.get("whatsapp_bridge_autostart", True) and (
                self._wa_proc is None or self._wa_proc.poll() is not None):
            self._wa_proc = wa_start_bridge(port=port)
        if not self._wa_listen_active:
            self._wa_listen_active = True
            threading.Thread(target=self._wa_listen_loop,
                             daemon=True, name="wa-listen").start()

    def _wa_listen_loop(self):
        """
        Hilo de fondo que cada 3 s consulta el bridge por mensajes nuevos en el
        chat propio, los procesa con la IA (mismas herramientas que por voz) y
        contesta por WhatsApp. Ignora grupos y otros chats.
        """
        print("[WA] Escucha activa del chat propio iniciada")
        while self._wa_listen_active:
            try:
                port = int(self.config.get("whatsapp_bridge_port", 3847))
                for m in wa_poll_messages(port=port):
                    text  = (m.get("text") or "").strip()
                    audio = m.get("audio")
                    # Desactivado: se recogen igual (para que no se acumulen y se
                    # contesten de golpe al reactivarlo) pero no se procesan
                    if not (text or audio) or not self.config.get("whatsapp_self_reply", True):
                        continue
                    if audio:
                        heard, err = self._wa_self_audio(m, port)
                        if not heard:
                            print(f"[WA] Audio del chat propio sin transcribir: {err}")
                            # Si solo contesta cuando le llamas, no se sabe si era para él
                            if not self.config.get("whatsapp_self_trigger", False):
                                wa_send_self(f"🎤 No he podido escuchar tu audio ({err}).", port=port)
                            continue
                        print(f"[WA] Audio del chat propio transcrito ({len(heard)} caracteres)")
                        text = f"{text} {heard}".strip()
                    if not wa_self_trigger_ok(text, self.config):
                        print("[WA] Mensaje del chat propio sin tu palabra: no se contesta")
                        continue
                    print(f"[WA] Procesando mensaje entrante: {text[:60]}")
                    prompt = f"[Mensaje de voz de WhatsApp, transcrito] {text}" if audio else text
                    extra = {}
                    reply = self._stream_ollama(prompt, origin="whatsapp",
                                                display=f"📱 [WhatsApp propio{' · audio' if audio else ''}] {text}",
                                                result=extra)
                    notes = extra.get("notes") or []
                    if reply or notes:
                        wa_send_self("\n".join([reply] + notes).strip(), port=port)
            except Exception as e:
                print(f"[WA] Error en escucha: {e}")
            time.sleep(3)

    def _wa_self_audio(self, m: dict, port: int) -> Tuple[Optional[str], str]:
        """Descarga y transcribe un audio de tu chat propio. → (texto | None, motivo del fallo)"""
        res = wa_media((m.get("audio") or {}).get("jid", ""), m.get("id", ""), port=port)
        if not res.get("ok"):
            return None, res.get("error") or "no se pudo descargar"
        text, err = self._wa_transcribe(res.get("base64", ""), res.get("mimetype", ""), m.get("id", ""))
        if text and text.startswith("(no se entiende"):
            return None, "no se entiende nada"
        return text, err or ("no se pudo transcribir" if not text else "")

    # ── Escucha manual / detener ─────────────────────────────────────────────
    def _stop_listening(self):
        """
        Corta de golpe cualquier escucha activa (conversación continua o PTT
        en curso) sin cerrar la aplicación. El asistente vuelve a esperar
        la wake word como si nada.
        """
        was_active = self._continuous_active or self._ptt_active or self._listening
        self._continuous_active = False
        self._ptt_active        = False
        if not self._processing:
            self._listening = False
            self._ui_q.put(("orb_state", "idle"))
        if was_active:
            print("⏹️  Escucha detenida manualmente.")

    def _manual_listen_trigger(self):
        if not HAS_SR:
            self._notify("Rubencho AI", "Falta SpeechRecognition: pip install SpeechRecognition pyaudio")
            return
        if self._listening or self._processing or self._ptt_active or self._continuous_active:
            return
        self._listening = True
        self._ui_q.put(("orb_state","listening"))
        threading.Thread(target=self._manual_listen_thread, daemon=True).start()

    def _manual_listen_thread(self):
        try:
            r   = sr.Recognizer()
            r.energy_threshold = float(self.config.get("energy_threshold", 300))
            self._apply_vad(r)
            command = self._capture_command(r, sr.Microphone())
            if not command:
                self._ui_q.put(("orb_state","idle"))
                return
            self._stream_ollama(command, origin="voz")
        except Exception as e:
            print(f"[Manual] {e}")
            self._ui_q.put(("orb_state","idle"))
        finally:
            self._listening = False

    def _history_for_request(self, cfg) -> list:
        """
        Mensajes anteriores que se le envían a la IA: como mucho los últimos
        «max_history_turns» (cada uno con su respuesta y las herramientas que usó)
        y, si se ha puesto, solo los de las últimas «history_max_hours» horas.
        """
        try:
            turns = max(0, int(float(cfg.get("max_history_turns", 10))))
        except (TypeError, ValueError):
            turns = 10
        groups = self._turn_groups(self._history)[-turns:] if turns else []
        try:
            hours = float(cfg.get("history_max_hours", 0) or 0)
        except (TypeError, ValueError):
            hours = 0
        if hours > 0:
            limit = time.time() - hours * 3600
            groups = [g for g in groups if (g[0].get("ts") or limit) >= limit]
        hist = [m for g in groups for m in g]
        while hist and hist[0].get("role") != "user":   # que empiece por un mensaje tuyo
            hist.pop(0)
        return [{k: v for k, v in m.items() if k not in ("ts", "tool_results")} for m in hist]

    @staticmethod
    def _turn_groups(history: list) -> list:
        """Agrupa el historial por turnos: cada mensaje tuyo con todo lo que vino después."""
        groups = []
        for m in history:
            if not groups or (m.get("role") == "user" and not m.get("tool_results")):
                groups.append([m])
            else:
                groups[-1].append(m)
        return groups

    # ── Petición a la IA (streaming) ─────────────────────────────────────────
    def _stream_ollama(self, prompt: str, ptt_mode: bool = False, origin: str = "voz",
                       display: str = None, result: dict = None) -> str:
        """
        Envía un mensaje a la IA y muestra la respuesta en el popup a medida que llega.
        origin: "voz" (palabra clave, PTT, manual, continua) · "texto" · "whatsapp".
        Devuelve el texto final limpio (sin etiquetas).
        """
        with self._chat_lock:                # una petición cada vez (historial coherente)
            self._processing = True
            # Lo que llega por tu chat propio se contesta allí: sin panel en el PC
            # (la voz ya va apagada para WhatsApp)
            real_q = self._ui_q
            if origin == "whatsapp" and not self.config.get("whatsapp_self_popup", False):
                self._ui_q = _NoPopupQueue(real_q)
            try:
                return self._stream_ollama_locked(prompt, ptt_mode, origin, display, result)
            except Exception as e:
                import traceback
                traceback.print_exc()
                self._ui_q.put(("popup_stream_done", f"❌  Error inesperado: {e}"))
                self._ui_q.put(("orb_state", "continuous" if self._continuous_active else "idle"))
                return ""
            finally:
                self._ui_q = real_q
                self._processing = False
                self._tts_playing = False
                if origin == "voz":
                    self._listening = False

    def _stream_ollama_locked(self, prompt, ptt_mode, origin, display, result) -> str:
        cfg       = self.config
        host      = cfg.get("ollama_host","http://localhost:11434")
        model     = cfg.get("ollama_model","gemma3:4b")
        mode      = think_mode(cfg)
        no_think  = mode != "always"
        think_auto = mode == "auto" and self._model_can_think(host, model)
        use_mem   = bool(cfg.get("conversation_memory", True))
        max_hist  = int(cfg.get("max_history_turns", 10))
        flags     = self._flags(cfg)
        tts_on    = bool(cfg.get("tts_enabled", False))
        if origin == "whatsapp":
            tts_on = False
        elif origin == "texto":
            tts_on = tts_on and bool(cfg.get("text_input_tts", True))
        close_on_tts  = bool(cfg.get("popup_close_on_tts_end", False))
        close_delay   = int(cfg.get("popup_close_on_tts_end_delay", 2))

        self._ui_q.put(("open_popup_stream", display if display is not None else prompt))
        self._ui_q.put(("orb_state", "thinking"))

        # Mensajes: instrucciones + historial + mensaje (con fecha y hora si procede)
        user_content = prompt
        if cfg.get("datetime_in_messages", True):
            user_content = f"[{fecha_larga()}] {prompt}"
        user_entry = {"role": "user", "content": user_content}
        history    = self._history_for_request(cfg) if use_mem else []
        messages   = ([{"role": "system", "content": self._system_prompt(cfg)}]
                      + history + [user_entry])
        ctx = {"flags": flags, "notes": [], "done": set(),
               "prompt": prompt, "host": host, "model": model, "origin": origin,
               "think_auto": think_auto, "thinking": False}

        # ── TTS: una sola cola para toda la respuesta ────────────────────────
        def _make_tts_worker(tts_q: queue.Queue):
            engine   = cfg.get("tts_engine","pyttsx3")
            rate     = int(cfg.get("tts_rate", 180))
            vol      = float(cfg.get("tts_volume", 1.0))
            voice_id = cfg.get("tts_voice_id","")

            def _consumer():
                while True:
                    sentence = tts_q.get()
                    if sentence is None:
                        tts_q.task_done()
                        break
                    if not _TTS_MUTED:          # solo bloquea el bucle si no está silenciado
                        self._tts_playing = True
                        self._tts_last = time.time()
                        speak(sentence, engine, rate, vol, voice_id)
                        self._tts_last = time.time()
                    self._tts_playing = False   # siempre liberar al terminar
                    tts_q.task_done()

            t = threading.Thread(target=_consumer, daemon=True, name="tts")
            t.start()
            return t

        sentence_buf = ""
        SENT_END = set(".!?。！？\n")

        def _flush_tts(tts_q: queue.Queue, text: str = "", force: bool = False):
            """Acumula texto en sentence_buf y envía frases completas a la cola TTS."""
            nonlocal sentence_buf
            if not tts_on or tts_q is None:
                return
            sentence_buf += text
            while True:
                idx = -1
                for i, ch in enumerate(sentence_buf):
                    if ch in SENT_END:
                        idx = i
                        break
                if idx == -1:
                    if force and sentence_buf.strip():
                        last = re.sub(r"<[^>]*$", "", sentence_buf)        # etiqueta a medias
                        last = re.sub(r"#{1,6}\s*|[*_`>]|-{3,}", "", last).strip()
                        if last:
                            tts_q.put(last)
                        sentence_buf = ""
                    break
                sentence = sentence_buf[:idx + 1].strip()
                sentence_buf = sentence_buf[idx + 1:]
                clean = re.sub(r"#{1,6}\s*|[*_`>]|-{3,}", "", sentence).strip()
                if clean:
                    tts_q.put(clean)

        tts_q      = queue.Queue() if tts_on else None
        tts_worker = _make_tts_worker(tts_q) if tts_on else None
        tts_filter = TagStreamFilter()       # el TTS nunca lee etiquetas
        disp_filter= TagStreamFilter()       # el popup tampoco las muestra
        tts_paused = False                   # tras una herramienta, se espera al resultado

        # ── Petición streaming a Ollama ───────────────────────────────────────
        full_response = ""
        error = None
        try:
            body = self._ollama_body(model, messages, True, no_think, host)
            resp = self._ollama_post(host, body, stream=True)
            with resp:
                in_think = False
                for raw_line in resp.iter_lines():
                    if not raw_line:
                        continue
                    try:
                        data = json.loads(raw_line)
                    except Exception:
                        continue
                    if data.get("error"):
                        raise OllamaError(str(data["error"]))
                    chunk = (data.get("message") or {}).get("content", "") or ""
                    if chunk:
                        if "<think>" in chunk:
                            in_think = True
                        if in_think:
                            if "</think>" in chunk:
                                in_think = False
                                chunk = chunk.split("</think>", 1)[-1]
                            else:
                                chunk = ""
                    if chunk:
                        full_response += chunk
                        visible = disp_filter.feed(chunk)
                        if visible:
                            self._ui_q.put(("popup_chunk", visible))
                        if tts_on and not tts_paused:
                            if self._has_followup(full_response, flags):
                                tts_paused = True      # se leerá la respuesta final
                            else:
                                _flush_tts(tts_q, tts_filter.feed(chunk))
                    if data.get("done"):
                        break
        except requests.exceptions.ConnectionError:
            error = "❌  No puedo conectar con Ollama.\n\n¿Está en ejecución?  →  ollama serve"
        except requests.exceptions.Timeout:
            error = "❌  Ollama tardó demasiado. Prueba con un modelo más pequeño."
        except OllamaError as e:
            error = f"❌  {e}"
        except Exception as e:
            error = f"❌  Error: {e}"

        tail = disp_filter.flush()
        if tail and not error:
            self._ui_q.put(("popup_chunk", tail))

        if error:
            print(f"[IA] {error}")
            partial = strip_action_tags(full_response)
            self._ui_q.put(("popup_stream_done", f"{partial}\n\n{error}".strip()))
            self._ui_q.put(("orb_state", "continuous" if self._continuous_active else "idle"))
            if tts_q is not None:
                tts_q.put(None)
                tts_worker.join(timeout=120)
            return ""                         # sin historial, log ni conversación continua

        # ── ¿Ha decidido pensarlo? Se le vuelve a preguntar con el razonamiento ──
        if think_auto and _THINK_PAT.search(full_response):
            ctx["thinking"], no_think = True, False
            print("💭  La IA ha decidido pensarlo")
            self._ui_q.put(("popup_chunk", "💭 *Lo pienso con calma…*\n\n"))
            messages = self._thinking_messages(messages)
            try:
                full_response = self._ollama_chat(messages, False, host, model)
            except Exception as e:
                full_response = f"❌  No he podido pensarlo: {e}"
            visible = strip_action_tags(full_response)
            if visible:
                self._ui_q.put(("popup_chunk", visible))
            if tts_on and not tts_paused:
                if self._has_followup(full_response, flags):
                    tts_paused = True
                else:
                    _flush_tts(tts_q, tts_filter.feed(full_response))

        # ── Herramientas (memoria/recordatorios al momento; el resto con más pasos) ─
        try:
            final_response = self._run_agentic_loop(
                full_response, messages, host, model, no_think, ctx)
        except requests.exceptions.ConnectionError:
            final_response = full_response + "\n\n❌  Se perdió la conexión con Ollama."
        except OllamaError as e:
            final_response = full_response + f"\n\n❌  {e}"
        except Exception as e:
            final_response = full_response + f"\n\n❌  Error ejecutando herramientas: {e}"
        finally:
            self._pc_finish(ctx)

        clean = strip_action_tags(final_response)
        if not clean and ctx["notes"]:
            clean = "Hecho."
        display_text = clean
        if ctx["notes"]:
            display_text += "\n\n" + "\n".join(f"> {n}" for n in ctx["notes"])
        self._ui_q.put(("popup_stream_done", display_text))

        ptt_no_cont   = ptt_mode and bool(cfg.get("ptt_no_continuous", True))
        will_continue = (origin == "voz" and not ptt_no_cont and
                         bool(cfg.get("continuous_conv", True)) and bool(clean) and
                         not clean.startswith("❌"))
        # El orbe pasa a su estado siguiente ya; mientras hable lo mostrará como «hablando»
        self._ui_q.put(("orb_state", "continuous" if (self._continuous_active or will_continue)
                        else "idle"))

        if tts_on and tts_q is not None:
            if final_response != full_response:
                _flush_tts(tts_q, strip_action_tags(final_response), force=True)
            else:
                _flush_tts(tts_q, tts_filter.flush(), force=True)
            tts_q.put(None)
            tts_worker.join()
            self._tts_playing = False

        # ── Cerrar popup al terminar TTS (si está configurado) ────────────────
        if tts_on and close_on_tts and not _TTS_MUTED:
            def _close_after_delay():
                time.sleep(max(0, close_delay))
                self._ui_q.put(("close_popup", None))
            threading.Thread(target=_close_after_delay, daemon=True).start()

        # Historial: el mensaje con su fecha y la respuesta con sus etiquetas de
        # memoria/recordatorio (así la IA ve cómo las usó)
        if use_mem and clean:
            now = time.time()
            turn = [{**user_entry, "ts": now}]
            # Qué herramientas usó (sin los resultados): así, si le vuelves a preguntar
            # «¿y ahora qué dice?», las vuelve a usar en vez de contestar de memoria
            used = ctx.get("trace") or []
            trace = tools_trace((["<PENSAR/>"] if ctx.get("thinking") else []) + used)
            if trace:
                note = (f"(Aquí estaban los resultados de esas herramientas, de las "
                        f"{datetime.now():%H:%M}. No se guardan en el historial: si te vuelven "
                        f"a preguntar por lo mismo, vuelve a usar la herramienta.)" if used else
                        "(Aquí lo pensaste con calma antes de responder.)")
                turn += [{"role": "assistant", "ts": now, "content": trace},
                         {"role": "user", "ts": now, "tool_results": True, "content": note}]
            turn.append({"role": "assistant", "ts": now,
                         "content": _LEADING_STAMP_RE.sub("", final_response).strip()})
            self._history.extend(turn)
            groups = self._turn_groups(self._history)
            if len(groups) > max_hist:
                self._history = [m for g in groups[-max_hist:] for m in g] if max_hist > 0 else []

        # Log
        if cfg.get("log_enabled") and cfg.get("log_file_path") and clean:
            threading.Thread(
                target=append_log,
                args=(cfg["log_file_path"], prompt, clean,
                      int(cfg.get("log_max_entries", 0) or 0)),
                daemon=True).start()

        if result is not None:
            result["notes"] = list(ctx["notes"])

        # Conversación continua — solo por voz y no en PTT con ptt_no_continuous
        if will_continue and not self._continuous_active:
            self._continuous_active = True
            threading.Thread(
                target=self._continuous_conv_loop,
                daemon=True, name="conversacion-continua").start()
        return clean

    def _continuous_conv_loop(self):
        cfg       = self.config
        timeout_s = float(cfg.get("continuous_timeout",   8.0))
        stop_word = _norm_text(cfg.get("continuous_stop_word", "para"))
        cmd_engine= cfg.get("command_engine", "whisper")

        print(f"🔁  Conversación continua activa (timeout {timeout_s}s)")
        self._ui_q.put(("orb_state", "continuous"))

        try:
            r   = sr.Recognizer()
            r.energy_threshold = float(cfg.get("energy_threshold", 300))
            self._apply_vad(r)
            mic = sr.Microphone()
        except Exception as e:
            print(f"[ContConv] Mic error: {e}")
            self._continuous_active = False
            self._ui_q.put(("orb_state", "idle"))
            return

        deadline = None
        try:
            while self._continuous_active:
                if self._tts_playing or self._processing:
                    time.sleep(0.15)               # no escuchar mientras habla la IA
                    deadline = None
                    continue

                if deadline is None:
                    deadline = time.time() + timeout_s
                    print(f"🕐  Escuchando {timeout_s}s más...")

                remaining = deadline - time.time()
                if remaining <= 0:
                    print("⏹️  Timeout conversación continua")
                    break

                audio = self._record_raw_audio(
                    r, mic,
                    phrase_time_limit=float(cfg.get("phrase_time_limit", 15.0)),
                    timeout=min(remaining, 4.0))
                if not self._continuous_active:      # «Terminar» mientras escuchaba
                    break
                if audio is None:
                    continue

                self._ui_q.put(("orb_state", "thinking"))
                command = (self._recognize(audio, cmd_engine) or "").strip()
                if not self._continuous_active:
                    break
                if not command:
                    self._ui_q.put(("orb_state", "continuous"))
                    continue

                print(f"📝  Follow-up: {command}")
                if self._is_stop_word(command, stop_word):
                    print(f"🛑  Palabra de parada '{stop_word}'")
                    break

                self._listening = True
                self._stream_ollama(command, origin="voz")
                deadline = None
                if self._continuous_active:
                    self._ui_q.put(("orb_state", "continuous"))
                print("🔁  Esperando siguiente follow-up...")
        finally:
            self._continuous_active = False
            self._listening         = False
            self._ui_q.put(("orb_state", "idle"))
            print("✅  Volviendo al modo wake word")

    @staticmethod
    def _is_stop_word(command: str, stop_word: str) -> bool:
        """
        ¿El usuario quiere terminar? Solo cuenta si dice la palabra de parada sola o en
        una frase muy corta («para», «ya puedes parar»): «busca recetas para la cena»
        no debe cortar la conversación (antes bastaba con que apareciera el texto).
        """
        if not stop_word:
            return False
        words = re.sub(r"[^\w\s]", " ", _norm_text(command)).split()
        if " ".join(words) == stop_word:
            return True
        return len(words) <= 3 and bool(re.search(rf"\b{re.escape(stop_word)}\b", " ".join(words)))

    # ── Configuración ────────────────────────────────────────────────────────
    def open_settings(self, section: str = None):
        try:
            if self._settings_win is not None and self._settings_win.winfo_exists():
                if section:
                    self._settings_win._show_section(section)
                _force_foreground(self._settings_win)
                return
        except Exception:
            pass

        def on_save(new_cfg):
            old = dict(self.config)
            # Se actualiza el MISMO diccionario: el orbe y el resto ven los cambios
            # (antes se sustituía y el orbe seguía guardando la configuración vieja)
            self.config.clear()
            self.config.update(new_cfg)
            self._apply_settings(old)

        self._settings_win = SettingsWindow(self.root, self.config, on_save,
                                            app=self, section=section)

    def _apply_settings(self, old: dict):
        """Aplica al momento los cambios de configuración."""
        cfg = self.config
        if bool(old.get("autostart")) != bool(cfg.get("autostart")) or cfg.get("autostart"):
            self._apply_autostart(cfg.get("autostart", False))
        self._start_ptt_listener()           # reiniciar con la nueva tecla
        if self._orb:
            self._orb.apply_config()
        if cfg.get("command_engine") == "whisper":
            threading.Thread(target=self._ensure_whisper, kwargs={"warmup": True},
                             daemon=True).start()
        if "vosk" in (cfg.get("command_engine"), cfg.get("speech_engine")):
            threading.Thread(target=self._get_vosk_model, daemon=True).start()
        if (old.get("ollama_model"), old.get("ollama_host")) != (cfg.get("ollama_model"),
                                                                  cfg.get("ollama_host")):
            threading.Thread(target=self._preload_ollama, daemon=True).start()
        if cfg.get("whatsapp_enabled"):
            self._start_whatsapp()
        else:
            self._wa_listen_active = False
        if not cfg.get("pc_control_enabled") and self._pc_session is not None:
            self._pc_session.request_stop("has desactivado el control del PC")
        self._tray_refresh()

    def _sync_autostart(self):
        """
        En la aplicación compilada, el inicio con Windows se ajusta a la opción de la
        configuración (o al instalador, si allí se marcó) y apunta a este .exe.
        """
        if not (IS_WINDOWS and IS_FROZEN) or os.environ.get("RUBENCHO_DATA_DIR"):
            return                       # (las instancias de prueba no tocan el registro)
        want = bool(self.config.get("autostart")) or _autostart_registered()
        if want != bool(self.config.get("autostart")):
            self.config["autostart"] = want
            save_config(self.config)
        threading.Thread(target=self._apply_autostart, args=(want,), daemon=True).start()

    def _apply_autostart(self, enable: bool):
        if os.environ.get("RUBENCHO_DATA_DIR"):
            print(f"[Autostart] (instancia de prueba) no se cambia: {enable}")
            return
        system = platform.system()
        exe    = sys.executable
        script = os.path.abspath(__file__)
        if system == "Windows" and IS_FROZEN:
            try:
                import winreg
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                    r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_SET_VALUE)
                if enable:
                    winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, f'"{exe}" --tray')
                else:
                    try: winreg.DeleteValue(key, APP_NAME)
                    except FileNotFoundError: pass
                # La versión anterior (script de Python) ya no debe arrancar sola
                try: winreg.DeleteValue(key, "VoiceAI")
                except FileNotFoundError: pass
                winreg.CloseKey(key)
            except Exception as e: print(f"[Autostart] {e}")
            return
        if system == "Windows":
            # Siempre con pythonw.exe para que no se abra una consola al iniciar Windows
            p = Path(exe)
            if p.name.lower().startswith("python") and not p.name.lower().startswith("pythonw"):
                cand = p.with_name("pythonw" + p.name[len("python"):])
                if cand.exists():
                    exe = str(cand)
            try:
                import winreg
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                    r"Software\Microsoft\Windows\CurrentVersion\Run",
                    0, winreg.KEY_SET_VALUE)
                if enable:
                    winreg.SetValueEx(key,"VoiceAI",0,winreg.REG_SZ,
                        f'"{exe}" "{script}" --tray')
                else:
                    try: winreg.DeleteValue(key,"VoiceAI")
                    except FileNotFoundError: pass
                winreg.CloseKey(key)
            except Exception as e: print(f"[Autostart] {e}")
        elif system == "Darwin":
            plist = Path.home()/"Library/LaunchAgents/com.voiceai.desktop.plist"
            if enable:
                plist.write_text(
                    f'<?xml version="1.0"?><plist version="1.0"><dict>'
                    f'<key>Label</key><string>com.voiceai.desktop</string>'
                    f'<key>ProgramArguments</key><array>'
                    f'<string>{exe}</string><string>{script}</string></array>'
                    f'<key>RunAtLoad</key><true/></dict></plist>')
            elif plist.exists(): plist.unlink()
        elif system == "Linux":
            dst = Path.home()/".config/autostart/voiceai.desktop"
            dst.parent.mkdir(parents=True, exist_ok=True)
            if enable:
                dst.write_text(
                    "[Desktop Entry]\nType=Application\nName=Rubencho AI\n"
                    f"Exec={exe} {script} --tray\n"
                    "Hidden=false\nNoDisplay=false\n"
                    "X-GNOME-Autostart-enabled=true\n")
            elif dst.exists(): dst.unlink()

    # ── Recordatorios ────────────────────────────────────────────────────────
    def _on_reminder_due(self, reminder: dict, late: bool):
        """Lo llama el hilo planificador: el aviso se muestra desde el hilo de Tk."""
        print(f"⏰  ¡Recordatorio #{reminder.get('id')}!  {reminder.get('texto')}"
              + ("  (atrasado)" if late else ""))
        self._ui_q.put(("reminder_fire", (reminder, late)))

    def _show_reminder(self, reminder: dict, late: bool):
        cfg = self.config
        self._notifications = [n for n in self._notifications if not getattr(n, "_closed", True)]
        stop_alert = threading.Event()

        def snooze(minutes: int):
            stop_alert.set()
            when = datetime.now() + timedelta(minutes=minutes)
            self._reminders.add(reminder.get("texto", "Recordatorio"), when, "")
            self._notify("⏰  Recordatorio pospuesto",
                         f"{reminder.get('texto', '')} — {fecha_corta(when)}")

        def closed(win):
            if win in self._notifications:
                self._notifications.remove(win)

        n = ReminderNotification(self.root, cfg, reminder, late, len(self._notifications),
                                 on_snooze=snooze, on_done=stop_alert.set, on_close=closed)
        self._notifications.append(n)
        self._notify("⏰  Recordatorio", reminder.get("texto", ""))
        threading.Thread(target=self._reminder_alert, args=(reminder, stop_alert),
                         daemon=True, name="aviso").start()
        if cfg.get("reminder_whatsapp") and cfg.get("whatsapp_enabled"):
            threading.Thread(
                target=wa_send_self,
                args=(f"⏰ Recordatorio: {reminder.get('texto', '')}",),
                kwargs={"port": int(cfg.get("whatsapp_bridge_port", 3847))},
                daemon=True).start()

    def _reminder_alert(self, reminder: dict, stop: threading.Event):
        """Sonido (varias veces, hasta que se pulse Hecho/Posponer) y lectura en voz alta."""
        cfg = self.config
        say = f"Recordatorio: {reminder.get('texto', '')}"
        try:
            reps = max(1, int(float(cfg.get("reminder_sound_repeats", 3))))
        except (TypeError, ValueError):
            reps = 3
        sound = str(cfg.get("reminder_sound_file", "") or "").strip() or "recordatorio"
        spoken = False
        for i in range(reps if cfg.get("reminder_sound", True) else 0):
            if stop.is_set():
                break
            play_sound(sound, wait=True)
            if i == 0 and cfg.get("reminder_tts", True) and not stop.is_set():
                self._speak_now(say)
                spoken = True
            stop.wait(1.2)
        if not spoken and cfg.get("reminder_tts", True) and not stop.is_set():
            self._speak_now(say)

    def _speak_now(self, text: str):
        cfg = self.config
        self._tts_playing = True
        self._tts_last = time.time()
        try:
            speak(text, cfg.get("tts_engine", "pyttsx3"), int(cfg.get("tts_rate", 180)),
                  float(cfg.get("tts_volume", 1.0)), cfg.get("tts_voice_id", ""))
        finally:
            self._tts_last = time.time()
            self._tts_playing = False

    # ── Tareas de la IA ──────────────────────────────────────────────────────
    def _on_ai_task_due(self, task: dict, late: bool):
        """Lo llama el planificador de tareas: se le manda a la IA lo que tenía que hacer."""
        if not self.config.get("ai_tasks_enabled", True):
            print(f"🤖  Tarea #{task.get('id')} no hecha: las tareas de la IA están desactivadas")
            return
        threading.Thread(target=self._run_ai_task, args=(task,), daemon=True,
                         name=f"tarea-{task.get('id')}").start()

    def _run_ai_task(self, task: dict):
        cfg   = self.config
        texto = task.get("texto", "")
        print(f"🤖  ¡Tarea #{task.get('id')}!  {texto}")
        now = datetime.now()
        lines = [f"[TAREA PROGRAMADA #{task.get('id')}] Ha llegado la hora de hacer esta "
                 f"tarea que te programaste:", f"«{texto}»"]
        if task.get("pedido"):
            try:
                cuando = fecha_corta(datetime.fromisoformat(task["creado"]), now)
            except Exception:
                cuando = "antes"
            lines.append(f"(El usuario te la pidió {cuando}, diciendo: «{task['pedido']}»)")
        try:
            delay = now - datetime.fromisoformat(task["cuando"])
        except Exception:
            delay = timedelta(0)
        if delay.total_seconds() > 120:
            lines.append(f"⚠️ Llega con {duracion_humana(delay)} de retraso (el PC estaba apagado o "
                         "Rubencho cerrado). Si dependía de la hora y ya no tiene sentido, no la "
                         "hagas y explica por qué.")
        lines.append("Hazla ahora con tus herramientas. El usuario puede no estar delante: no le "
                     "preguntes nada. Si no puedes hacerla, di brevemente por qué. Termina con "
                     "una frase corta que diga lo que has hecho.")
        extra = {}
        reply = self._stream_ollama("\n".join(lines), origin="tarea",
                                    display=f"🤖⏰ Tarea programada: {texto}", result=extra)
        if cfg.get("ai_tasks_whatsapp") and cfg.get("whatsapp_enabled"):
            done = "\n".join([reply] + (extra.get("notes") or [])).strip() or "(sin respuesta)"
            wa_send_self(f"🤖⏰ Tarea: {texto}\n{done}",
                         port=int(cfg.get("whatsapp_bridge_port", 3847)))

    def _test_reminder(self):
        self._show_reminder({"id": 0, "texto": "Esto es un recordatorio de prueba",
                             "cuando": datetime.now().isoformat(timespec="seconds"),
                             "repetir": ""}, False)

    # ── PTT – Push to Talk ────────────────────────────────────────────────────

    @staticmethod
    def _parse_ptt_hotkey(hotkey_str: str):
        """
        Convierte una cadena como 'ctrl+f9' en (req_mods: set[str], main_key).
        req_mods puede contener: 'ctrl', 'shift', 'alt', 'win'.
        main_key es un pynput Key o KeyCode, o None si no se pudo parsear.
        """
        if not HAS_PYNPUT:
            return set(), None
        parts    = [p.strip().lower() for p in hotkey_str.split("+")]
        MOD_SET  = {"ctrl", "control", "shift", "alt", "win", "cmd", "super"}
        MOD_NORM = {"control": "ctrl", "cmd": "win", "super": "win"}
        req_mods = set()
        main_key = None
        for part in parts:
            if part in MOD_SET:
                req_mods.add(MOD_NORM.get(part, part))
            else:
                try:
                    main_key = getattr(_pynput_kb.Key, part)
                except AttributeError:
                    if len(part) == 1:
                        main_key = _pynput_kb.KeyCode.from_char(part)
                    else:
                        main_key = _pynput_kb.KeyCode.from_char(part[0]) if part else None
        return req_mods, main_key

    @staticmethod
    def _ptt_key_matches(key, main_key) -> bool:
        """Compara teclas; con Ctrl pulsado las letras llegan como caracteres de control,
        así que también se compara por código virtual."""
        if key == main_key:
            return True
        mc = getattr(main_key, "char", None)
        if mc and len(mc) == 1 and mc.isalnum():
            vk = getattr(key, "vk", None)
            return vk is not None and vk == ord(mc.upper())
        return False

    def _start_ptt_listener(self):
        """Arranca (o reinicia) el listener global de teclado para PTT."""
        # Parar listener anterior si existe
        if self._ptt_listener is not None:
            try:
                self._ptt_listener.stop()
            except Exception:
                pass
            self._ptt_listener = None

        if not self.config.get("ptt_enabled", False):
            return

        if not HAS_PYNPUT:
            print("[PTT] ⚠️  pynput/pyaudio no instalados. Ejecuta: pip install pynput pyaudio")
            return

        hotkey_str         = self.config.get("ptt_hotkey", "f9")
        req_mods, main_key = self._parse_ptt_hotkey(hotkey_str)
        if main_key is None:
            print(f"[PTT] ⚠️  No se pudo parsear la tecla: '{hotkey_str}'")
            return

        print(f"[PTT] Activado — tecla: '{hotkey_str}'")

        # Contadores de modificadores (soporta L/R)
        _CTRL_KEYS  = {_pynput_kb.Key.ctrl,   _pynput_kb.Key.ctrl_l,  _pynput_kb.Key.ctrl_r}
        _SHIFT_KEYS = {_pynput_kb.Key.shift,  _pynput_kb.Key.shift_l, _pynput_kb.Key.shift_r}
        _ALT_KEYS   = {_pynput_kb.Key.alt,    _pynput_kb.Key.alt_l,   _pynput_kb.Key.alt_r}
        _WIN_KEYS   = {_pynput_kb.Key.cmd,    _pynput_kb.Key.cmd_l,   _pynput_kb.Key.cmd_r}

        def _mods_ok():
            return (
                ("ctrl"  not in req_mods or self._ptt_ctrl)  and
                ("shift" not in req_mods or self._ptt_shift) and
                ("alt"   not in req_mods or self._ptt_alt)   and
                ("win"   not in req_mods or self._ptt_win)
            )

        def on_press(key):
            # Actualizar estado de modificadores
            if key in _CTRL_KEYS:   self._ptt_ctrl  = True
            if key in _SHIFT_KEYS:  self._ptt_shift = True
            if key in _ALT_KEYS:    self._ptt_alt   = True
            if key in _WIN_KEYS:    self._ptt_win   = True

            # ¿Es la tecla principal?
            if self._ptt_key_matches(key, main_key) and _mods_ok():
                if not self._ptt_active and not self._listening:
                    self._ptt_active = True
                    threading.Thread(
                        target=self._ptt_record_and_send,
                        daemon=True).start()

        def on_release(key):
            # Soltar modificadores
            if key in _CTRL_KEYS:   self._ptt_ctrl  = False
            if key in _SHIFT_KEYS:  self._ptt_shift = False
            if key in _ALT_KEYS:    self._ptt_alt   = False
            if key in _WIN_KEYS:    self._ptt_win   = False

            # Soltar tecla principal → parar grabación
            if self._ptt_key_matches(key, main_key) and self._ptt_active:
                self._ptt_active = False

        listener = _pynput_kb.Listener(on_press=on_press, on_release=on_release)
        listener.daemon = True
        listener.start()
        self._ptt_listener = listener

    def _ptt_record_and_send(self):
        """
        Graba audio mientras la tecla PTT está presionada.
        Al soltar, transcribe y lo envía a la IA.
        """
        CHUNK    = 1024
        FORMAT   = _pyaudio.paInt16
        CHANNELS = 1
        RATE     = 16000

        self._listening = True
        self._ui_q.put(("orb_state", "listening"))
        print("🎙  PTT: grabando...")

        try:
            pa     = _pyaudio.PyAudio()
            stream = pa.open(format=FORMAT, channels=CHANNELS, rate=RATE,
                             input=True, frames_per_buffer=CHUNK)
            frames = []
            while self._ptt_active:
                data = stream.read(CHUNK, exception_on_overflow=False)
                frames.append(data)
            stream.stop_stream()
            stream.close()
            pa.terminate()
        except Exception as e:
            print(f"[PTT] Error de audio: {e}")
            self._ptt_active  = False
            self._listening   = False
            self._ui_q.put(("orb_state", "idle"))
            return

        if not frames or not HAS_SR:
            self._listening = False
            self._ui_q.put(("orb_state", "idle"))
            return

        # ── Transcripción ─────────────────────────────────────────────────────
        self._ui_q.put(("orb_state", "thinking"))
        audio   = sr.AudioData(b"".join(frames), RATE, 2)   # sample_width=2 → paInt16
        command = (self._recognize(audio, self.config.get("command_engine", "whisper")) or "").strip()
        if not command:
            print("⚠️  PTT: Sin comando detectado.")
            self._ui_q.put(("orb_state", "idle"))
            self._listening = False
            return

        print(f"📝  PTT Comando: {command}")
        self._stream_ollama(command, ptt_mode=True, origin="voz")
        self._listening = False

    # ── Salir ────────────────────────────────────────────────────────────────
    def _quit(self):
        print("👋  Cerrando Rubencho AI…")
        if self._pc_session is not None:
            self._pc_session.request_stop("Rubencho se está cerrando")
        for sched in (self._scheduler, getattr(self, "_task_scheduler", None)):
            try:
                sched.stop()
            except Exception:
                pass
        if self._ptt_listener is not None:
            try:
                self._ptt_listener.stop()
            except Exception:
                pass
        if HAS_TRAY and self._tray is not None:
            try: self._tray.stop()
            except Exception: pass
        # Detener hilo de escucha WA (independiente de si hay bridge proc)
        self._wa_listen_active = False
        if self._wa_proc:
            try:
                port = int(self.config.get("whatsapp_bridge_port", 3847))
                wa_stop_bridge(self._wa_proc, port=port)
            except Exception:
                pass
        if _browser_agent is not None:
            threading.Thread(target=_browser_agent.close, daemon=True).start()
        self.root.quit()


def _autostart_registered() -> bool:
    """¿Está registrado el inicio con Windows de esta aplicación?"""
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                             r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_READ)
        try:
            val, _t = winreg.QueryValueEx(key, APP_NAME)
            return bool(str(val).strip())
        except FileNotFoundError:
            return False
        finally:
            winreg.CloseKey(key)
    except Exception:
        return False


# Si se abre Rubencho AI cuando ya está en marcha, el nuevo proceso avisa al que
# está abierto (con un evento de Windows) y este abre «Escribir mensaje» o la
# Configuración. Así, el icono fijado en la barra de tareas siempre hace algo útil.
_EVENT_SHOW     = "Local\\RubenchoAI_Mostrar"
_EVENT_SETTINGS = "Local\\RubenchoAI_Ajustes"


def _instance_suffix() -> str:
    """Las instancias de prueba (RUBENCHO_DATA_DIR) no chocan con la normal."""
    custom = os.environ.get("RUBENCHO_DATA_DIR", "").strip()
    if not custom:
        return ""
    import hashlib
    return "_" + hashlib.md5(custom.lower().encode("utf-8")).hexdigest()[:8]


def _listen_for_other_instances(ui_q: "queue.Queue"):
    if not IS_WINDOWS:
        return
    import ctypes
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateEventW.restype = ctypes.c_void_p
    k32.WaitForMultipleObjects.argtypes = [ctypes.c_ulong, ctypes.c_void_p, ctypes.c_int, ctypes.c_ulong]
    sfx = _instance_suffix()
    handles = [k32.CreateEventW(None, False, False, _EVENT_SHOW + sfx),
               k32.CreateEventW(None, False, False, _EVENT_SETTINGS + sfx)]
    if not all(handles):
        return
    arr = (ctypes.c_void_p * 2)(*handles)
    globals()["_INSTANCE_EVENTS"] = (handles, arr)

    def loop():
        while True:
            r = k32.WaitForMultipleObjects(2, arr, False, 0xFFFFFFFF)
            if r == 0:
                ui_q.put(("quick_input", None))
            elif r == 1:
                ui_q.put(("settings", None))
            else:
                time.sleep(1)
    threading.Thread(target=loop, daemon=True, name="otra-instancia").start()


def _signal_running_instance(settings: bool) -> bool:
    """Pide a la instancia abierta que se muestre. False si no responde (versión antigua)."""
    try:
        import ctypes
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.OpenEventW.restype = ctypes.c_void_p
        name = (_EVENT_SETTINGS if settings else _EVENT_SHOW) + _instance_suffix()
        h = k32.OpenEventW(0x0002, False, name)              # EVENT_MODIFY_STATE
        if not h:
            return False
        k32.SetEvent(ctypes.c_void_p(h))
        k32.CloseHandle(ctypes.c_void_p(h))
        return True
    except Exception:
        return False


def install_playwright_chromium() -> Tuple[bool, str]:
    """Descarga Chromium para el control del navegador con el Playwright incluido."""
    try:
        from playwright._impl._driver import compute_driver_executable, get_driver_env
        drv = compute_driver_executable()
        cmd = list(drv) if isinstance(drv, (tuple, list)) else [str(drv)]
        r = subprocess.run(cmd + ["install", "chromium"], env=get_driver_env(),
                           capture_output=True, text=True, timeout=1800,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        out = (r.stdout or "") + (r.stderr or "")
        print(out[-2000:])
        return r.returncode == 0, out.strip().splitlines()[-1] if out.strip() else ""
    except Exception as e:
        return False, str(e)


def _run_diagnostics() -> int:
    """
    `Rubencho AI.exe --diagnostico`: comprueba que todas las piezas cargan y lo
    escribe en diagnostico.txt (carpeta de datos). Útil si algo no funciona.
    """
    import traceback
    lines = [f"Rubencho AI · {datetime.now():%Y-%m-%d %H:%M:%S}",
             f"Ejecutable: {sys.executable} (compilada: {IS_FROZEN})",
             f"Datos: {APP_DIR}", ""]

    def check(name, fn):
        try:
            res = fn()
            lines.append(f"OK    {name}: {res if res is not None else ''}")
        except Exception as e:
            lines.append(f"FALLO {name}: {e}")
            lines.append("      " + traceback.format_exc().strip().splitlines()[-1])

    check("icono", lambda: ICON_ICO.exists() and ICON_TRAY.exists())
    check("requests", lambda: __import__("requests").__version__)
    check("SpeechRecognition", lambda: __import__("speech_recognition").__version__)
    check("flac (Google)", lambda: bool(__import__("speech_recognition").get_flac_converter()))
    check("pyaudio", lambda: __import__("pyaudio").get_portaudio_version_text())
    check("pystray", lambda: HAS_TRAY)
    check("pynput", lambda: HAS_PC_INPUT)
    check("faster-whisper", lambda: __import__("faster_whisper").__version__)
    check("VAD de Whisper", lambda: __import__("faster_whisper.vad", fromlist=["x"]).get_vad_model() is not None)
    check("GPU para Whisper", lambda: cuda_whisper_available())
    check("vosk", lambda: bool(__import__("vosk").Model))
    check("sounddevice (micrófono continuo)", lambda: __import__("sounddevice").query_devices(kind="input")["name"])

    def vosk_model():
        import types
        d = VoiceAIApp._vosk_model_dir(types.SimpleNamespace(config=load_config()))
        if not d:
            raise RuntimeError("no se encuentra la carpeta del modelo")
        __import__("vosk").Model(d)
        return Path(d).name
    check("Modelo de Vosk (palabra clave local)", vosk_model)
    check("opencv (cámara)", lambda: __import__("cv2").__version__)
    check("pyttsx3 (voz)", lambda: len(__import__("pyttsx3").init().getProperty("voices")))
    check("gTTS", lambda: bool(__import__("gtts").gTTS))
    check("pygame", lambda: __import__("pygame").version.ver)
    check("UI Automation (control del PC)", lambda: bool(_uia()))
    check("Playwright", lambda: _PLAYWRIGHT_AVAILABLE)
    check("Playwright: driver", lambda: str(
        __import__("playwright._impl._driver", fromlist=["x"]).compute_driver_executable()))
    check("WhatsApp: puente", lambda: (APP_HOME / "whatsapp" / "whatsapp_bridge.js").exists()
          or (APP_HOME / "whatsapp_bridge.js").exists())
    check("Node.js", lambda: subprocess.run(["node", "--version"], capture_output=True, text=True,
                                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
                                            ).stdout.strip())
    check("Ollama", lambda: requests.get(load_config().get("ollama_host", "http://localhost:11434")
                                         + "/api/version", timeout=3).json().get("version"))
    report = "\n".join(lines)
    print(report)
    try:
        APP_DIR.mkdir(parents=True, exist_ok=True)
        (APP_DIR / "diagnostico.txt").write_text(report + "\n", encoding="utf-8")
    except Exception:
        pass
    return 0 if not any(l.startswith("FALLO") for l in lines) else 1


def _single_instance() -> bool:
    """Evita abrir Rubencho AI dos veces (dos asistentes escuchando a la vez)."""
    if not IS_WINDOWS:
        return True
    try:
        import ctypes
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.CreateMutexW.restype = ctypes.c_void_p
        handle = k32.CreateMutexW(None, False, "Local\\RubenchoAI_InstanciaUnica" + _instance_suffix())
        if ctypes.get_last_error() == 183:          # ERROR_ALREADY_EXISTS
            return False
        globals()["_INSTANCE_MUTEX"] = handle       # se mantiene mientras viva el proceso
    except Exception:
        pass
    return True


if __name__ == "__main__":
    if "--diagnostico" in sys.argv:
        sys.exit(_run_diagnostics())
    if "--instalar-navegador" in sys.argv:
        _ok, _msg = install_playwright_chromium()
        print("Chromium:", "instalado" if _ok else f"error: {_msg}")
        sys.exit(0 if _ok else 1)
    if not _single_instance():
        # Ya hay uno abierto: se le pide que se muestre (si es una versión antigua, se avisa)
        if not _signal_running_instance(settings="--settings" in sys.argv):
            try:
                _r = tk.Tk()
                _r.withdraw()
                if ICON_ICO.exists():
                    _r.iconbitmap(default=str(ICON_ICO))
                messagebox.showinfo("Rubencho AI",
                                    "Rubencho AI ya está en marcha.\n"
                                    "Búscalo en el icono de la bandeja del sistema.", parent=_r)
                _r.destroy()
            except Exception:
                pass
        sys.exit(0)
    missing = []
    if not HAS_REQUESTS: missing.append("requests")
    if not HAS_SR:       missing.append("SpeechRecognition")
    if missing:
        print(f"\n⚠️  Instala: pip install {' '.join(missing)} pyaudio\n")
    if not HAS_TRAY:
        print("ℹ️  Para bandeja del sistema: pip install pystray pillow\n")
    if not HAS_PYNPUT:
        print("ℹ️  Para Push-to-Talk (PTT): pip install pynput pyaudio\n")
    VoiceAIApp()
