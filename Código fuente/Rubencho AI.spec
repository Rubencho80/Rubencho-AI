# -*- mode: python ; coding: utf-8 -*-
# Receta de PyInstaller para compilar Rubencho AI como aplicación de Windows.
# Se usa desde compilar.bat:  python -m PyInstaller "Rubencho AI.spec"
from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_submodules

datas = [("recursos/rubencho.ico", "recursos"),
         ("recursos/rubencho_bandeja.png", "recursos"),
         ("recursos/rubencho.png", "recursos")]
binaries = []
hiddenimports = [
    "pystray._win32",
    "pynput.keyboard._win32", "pynput.mouse._win32",
    "pyttsx3.drivers", "pyttsx3.drivers.sapi5",
    "comtypes.client", "comtypes.stream",
    "win32com.client", "pythoncom", "pywintypes",
    "pyaudio", "gtts", "pygame", "sounddevice",
]

# Paquetes con ficheros propios (modelos, DLL, ejecutables) que hay que llevar enteros
for pkg in ("faster_whisper", "ctranslate2", "vosk", "speech_recognition", "playwright",
            "_sounddevice_data"):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h
hiddenimports += collect_submodules("pyttsx3")

# Cosas instaladas en el Python de desarrollo que la app NO usa (algunas pesan GB)
excludes = [
    "torch", "torchvision", "torchaudio", "transformers", "tensorflow", "keras", "jax",
    "matplotlib", "pandas", "scipy", "sympy", "sklearn", "numba", "llvmlite",
    "IPython", "jupyter", "notebook", "pytest", "PyQt5", "PyQt6", "PySide2", "PySide6",
    "wx", "gi", "nvidia",
    # Reconocedores de voz de pago que SpeechRecognition trae opcionales (no se usan)
    "boto3", "botocore", "openai", "groq", "google.cloud", "ibm_watson",
]

a = Analysis(
    ["Rubencho AI.pyw"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Rubencho AI",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,                       # aplicación de ventanas: sin consola
    disable_windowed_traceback=False,
    icon="recursos/rubencho.ico",
    version="version_info.txt",          # nombre y descripción que muestra Windows
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="Rubencho AI",
)
