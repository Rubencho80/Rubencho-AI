# Cómo volver a compilar Rubencho AI

Si cambias el código (`Rubencho AI.pyw`), haz doble clic en **`compilar.bat`**.
En unos 3 minutos crea un instalador nuevo en la carpeta de arriba:
`..\Instalar Rubencho AI.exe`. Después solo tienes que ejecutarlo: actualiza la
aplicación instalada y conserva tus datos.

## Qué necesita

- **Python 3.13** con las librerías de `requirements.txt` y **PyInstaller**:
  `python -m pip install -r requirements.txt`
  (`compilar.bat` busca primero el Python 3.13 de la Microsoft Store y después
  `py -3.13` o `python`; también se le puede indicar otro:
  `compilar.bat "C:\ruta\python.exe"`).
- **Inno Setup 6**: `winget install JRSoftware.InnoSetup`.
- **Node.js 20+**: las librerías del puente de WhatsApp van dentro del instalador.
  Si falta `whatsapp\node_modules`, `compilar.bat` las instala con `npm ci`.

## Archivos

| Archivo | Para qué sirve |
|---|---|
| `Rubencho AI.pyw` | El programa. También se puede ejecutar sin compilar: `pythonw "Rubencho AI.pyw"` |
| `Rubencho AI.spec` | Receta de PyInstaller: qué librerías se incluyen y cuáles se excluyen |
| `version_info.txt` | Nombre y descripción del `.exe` que muestra Windows («Rubencho AI») |
| `instalador.iss` | Script de Inno Setup: asistente, accesos directos, inicio con Windows y desinstalador |
| `compilar.bat` | Hace los dos pasos (PyInstaller e Inno Setup) |
| `recursos\` | Icono e imágenes del instalador (`crear_icono.py` los vuelve a generar) |
| `whatsapp\` | Puente de WhatsApp (Node.js) que se instala junto a la aplicación |
| `requirements.txt` | Librerías de Python necesarias |

## Notas

- La versión interna está en `APP_VERSION` (código), `version_info.txt` e
  `instalador.iss` (`AppBuild`). No se muestra en ningún sitio visible para el
  usuario; solo en *Propiedades → Detalles* de los `.exe`.
- La carpeta de datos es `%APPDATA%\Rubencho AI`. Con la variable de entorno
  `RUBENCHO_DATA_DIR` se puede usar otra (útil para hacer pruebas sin tocar los
  datos reales: esa instancia tampoco toca el inicio con Windows).
- `"Rubencho AI.exe" --diagnostico` comprueba todas las piezas y escribe
  `diagnostico.txt` en la carpeta de datos.
- Las librerías de la GPU (cuBLAS/cuDNN, ~1,8 GB) **no** van en el instalador:
  la aplicación las busca en los Python instalados, en el CUDA Toolkit o en una
  carpeta `gpu` junto a `Rubencho AI.exe` (copiando ahí sus DLL, la GPU funciona
  en cualquier PC con NVIDIA).
- No compiles desde una carpeta con una ruta muy larga: algunos archivos de
  Playwright superan el límite de 260 caracteres de Windows.
