# Rubencho AI

Asistente de voz para Windows con inteligencia artificial (a través de **Ollama**).
Le hablas con una palabra clave, una tecla o por escrito, y te responde en un
pequeño panel y, si quieres, en voz alta. Además puede **usar tu PC**: abrir
programas y webs, buscar en internet, **ver tu pantalla**, **hacer fotos con la
cámara**, **recordar cosas sobre ti**, **ponerte recordatorios** que suenan a la
hora indicada y hasta **manejar el ratón y el teclado** como lo harías tú.

### ⬇️ Descargar

**[Descarga el instalador (`Instalar Rubencho AI.exe`) desde la última versión](https://github.com/Rubencho80/Rubencho-AI/releases/latest)**
→ ejecútalo y sigue el asistente. Solo para **Windows 10/11 de 64 bits**; necesitas
[Ollama](https://ollama.com/download) (ver [Requisitos](#2-requisitos)).

> Windows puede avisar de que el instalador «no es de un editor conocido» porque
> no está firmado: pulsa **Más información → Ejecutar de todas formas**.

Novedades de cada versión: [CHANGELOG.md](CHANGELOG.md).

---

## Índice

1. [Qué puede hacer](#1-qué-puede-hacer)
2. [Requisitos](#2-requisitos)
3. [Instalación](#3-instalación)
4. [Primer arranque](#4-primer-arranque)
5. [Cómo usarlo](#5-cómo-usarlo)
6. [Configuración](#6-configuración)
7. [Dónde se guardan los datos](#7-dónde-se-guardan-los-datos)
8. [Privacidad y seguridad](#8-privacidad-y-seguridad)
9. [Solución de problemas](#9-solución-de-problemas)
10. [Desinstalar](#10-desinstalar)
11. [Contenido del repositorio y cómo compilar](#11-contenido-del-repositorio-y-cómo-compilar)
12. [Licencia](#12-licencia)

---

## 1. Qué puede hacer

### 🎙️ Formas de hablarle

| Forma | Cómo |
|---|---|
| **Palabra clave** | Di la palabra (por defecto **«asistente»**) y tu orden, con pausa o de corrido: «asistente, ¿qué hora es?». Te escucha al instante, sin internet. Se puede elegir otra o una personalizada. |
| **Conversación continua** | Después de responder sigue escuchando unos segundos, sin repetir la palabra clave. Termina en silencio o diciendo la palabra de parada (por defecto «para»). |
| **Push-to-Talk** | Mantén pulsada una tecla (por defecto **F9**) mientras hablas y suéltala para enviar. Se activa en Configuración. |
| **Escuchar ahora** | Desde el menú del icono de la bandeja o del orbe. |
| **Por escrito** | Clic izquierdo en el icono de la bandeja (o clic derecho → «Escribir mensaje»), doble clic en el orbe o en la caja de texto del panel de respuesta. |
| **WhatsApp** | Escribe en tu chat contigo mismo y te contesta allí (opcional). |

La orden se transcribe con **Whisper** (sin internet y muy preciso). La palabra
clave se reconoce en tu PC con **Vosk**, mientras la dices: no espera a que acabes
la frase ni a internet. Vosk conoce las palabras en español (asistente, oye,
despierta…); para una inventada o en inglés (Jarvis, Rubencho) elige Google en
Configuración → Reconocimiento.

### 🛠️ Lo que puede hacer por ti

| Función | Ejemplos de lo que puedes decirle |
|---|---|
| **Comandos de Windows** | «Abre YouTube», «abre la calculadora», «¿cuánta RAM libre tengo?», «¿qué hay en mi escritorio?», «crea una carpeta Pruebas», «¿cuánto es 3.312 entre 0,9?» (calcula con exactitud) |
| **Buscar en internet** | «¿Qué tiempo hará mañana en Barcelona?», «noticias de hoy», «¿qué dice esta página?» |
| **Ver tu pantalla** 📸 | «¿Qué ves en mi pantalla?», «ayúdame con este error», «resume lo que estoy leyendo» |
| **Usar la cámara** 📷 | «Hazme una foto», «¿qué tengo en la mano?», «¿cómo voy vestido?» |
| **Memoria** 🧠 | «Acuérdate de que mi color favorito es el azul», «olvida lo de…». La IA guarda sola lo importante (solo si lo ve necesario) y puede modificarlo o borrarlo. |
| **Recordatorios** ⏰ | «Recuérdame en 20 minutos que saque la pizza», «despiértame mañana a las 7:30», «de lunes a viernes a las 8 recuérdame el café», «quita el recordatorio de la pizza» |
| **Tareas para más tarde** 🤖 | «Mañana a las 8 mándale a mi padre que llego a las 3», «esta noche a las 10 mira el tiempo de mañana y dímelo». A esa hora la IA lo hace ella sola, aunque no estés delante. |
| **WhatsApp** 📱 | «Dile a Mamá que llego tarde», «¿qué me ha mandado Juan?», «resúmeme el audio de Ana», «contéstale a Pedro que sí» (solo contactos, nunca grupos; ve las fotos y escucha los audios) |
| **Navegador** 🌐 | «Busca monitores 4K en Amazon» (abre un Chromium que la IA controla; opcional) |
| **Control del PC** 🖱️ | «Abre el bloc de notas y escribe la lista de la compra», «pon en pausa Spotify», «cierra las pestañas de Chrome menos esta», «arrastra este archivo a la carpeta Fotos» (opcional, ver abajo) |
| **Fecha y hora** 🕐 | Sabe qué día y hora es en cada mensaje y cuánto tiempo ha pasado desde el anterior. |

No necesita pedirte permiso para usar estas herramientas: lo hace cuando hace
falta (las capturas de pantalla y la cámara se pueden desactivar).

### ⏰ Recordatorios

- A la hora indicada **suena un aviso** (varias veces), aparece una **ventana**
  con los botones *Posponer* / *1 hora* / *Hecho*, una **notificación de Windows**
  y, si quieres, se **lee en voz alta** y te llega **por WhatsApp**.
- Pueden repetirse: cada día, de lunes a viernes, cada semana, cada mes o cada año.
- Si el PC estaba apagado a esa hora, el aviso salta al abrir Rubencho AI.
- Se pueden ver, crear y borrar en Configuración → Recordatorios.

### 🤖 Tareas de la IA

Son recordatorios que la IA se pone **a sí misma**: en vez de avisarte a ti, a la
hora indicada le llega a la IA lo que tenía que hacer, y lo hace con sus
herramientas (enviar un WhatsApp, buscar algo, mirar el tiempo…).

- Pídeselo con naturalidad: «mañana a las 8 mándale a mi padre que llego a las 3».
  La IA decide si es un recordatorio (avisarte a ti) o una tarea (hacerlo ella).
- Al hacerla, la respuesta aparece en el panel (y se lee en voz alta si tienes la
  voz activada). Si quieres, también te manda por WhatsApp lo que ha hecho.
- Los WhatsApps de una tarea se envían sin preguntar, porque se lo pediste al
  programarla (y solo a los contactos permitidos). Si prefieres confirmarlos,
  actívalo en Configuración → Tareas de la IA; si no estás delante, no se envían.
- Si Rubencho estaba cerrado a esa hora, la hace al abrirse, o te explica por qué
  ya no tiene sentido.
- Se pueden ver, crear y borrar en Configuración → Tareas de la IA.

### 🖱️ Control del PC (ratón y teclado)

Con esta función activada, la IA puede usar el PC como una persona: hace clic,
escribe, pulsa teclas y atajos, arrastra cosas y usa la rueda del ratón. Viene
**desactivada**: actívala en Configuración → Control del PC o con un clic en el
menú del icono de la bandeja (**🖱 Control del PC**).

**Cómo encuentra las cosas.** En vez de adivinar coordenadas (algo que a los
modelos de IA se les da mal), recibe una captura con:

- **Los elementos de las ventanas numerados**: botones, campos de texto, menús,
  pestañas… (los mismos que Windows ofrece a los lectores de pantalla). La IA
  dice «clic en el 12» y Rubencho sabe el punto exacto.
- **Una cuadrícula** (columnas A, B, C… y filas 1, 2, 3…) para lo que no tiene
  elementos, como juegos, imágenes o mapas. Puede hacer **zoom** en una casilla
  para afinar con subcasillas.
- **Una captura después de cada acción**, para comprobar que ha salido bien.
  Rubencho le avisa si la pantalla no ha cambiado, para que lo vuelva a intentar.

**Precauciones** (cada una se puede activar o desactivar):

| Precaución | Qué hace |
|---|---|
| ✋ Confirmar acciones peligrosas | Antes de borrar, enviar, comprar, pagar, cerrar sin guardar… aparece una ventana para **Permitir**, **Permitir todo en esta tarea** o **Cancelar** (se cancela sola a los 60 s). |
| ⛔ Freno de emergencia con una tecla | Pulsa **Esc** (o la tecla que elijas) y se detiene al instante. Las teclas que pulsa la propia IA no lo activan. |
| ↖️ Freno con el ratón | Lleva el ratón a **una esquina de la pantalla** y se detiene. |
| 🖐 Parar si mueves el ratón | Opcional (desactivado por defecto): se detiene en cuanto tocas el ratón. |
| 🎮 Juegos a pantalla completa | No actúa si hay un juego o un vídeo a pantalla completa. |
| 🪧 Aviso en pantalla | Un cartel arriba indica que la IA está controlando el PC y qué está haciendo. |
| 🔢 Límite de pasos | Máximo de pasos por orden (25 por defecto). |

También se detiene desde la bandeja → **⛔ Detener el control del PC**. Mientras
trabaja, el orbe, el panel y los avisos de Rubencho **no salen en sus capturas**
y los clics los atraviesan, así que no le estorban.

### 🔵 El orbe

Una bolita flotante que indica qué está haciendo el asistente. Se puede arrastrar
a cualquier sitio (también a un segundo monitor) y recuerda la posición.

| Color | Significado |
|---|---|
| 🔵 Azul con onda | Te está escuchando |
| 🟠 Naranja con puntos | Transcribiendo, pensando o usando una herramienta |
| 🟣 Morado | Está hablando |
| 🟢 Verde | Conversación continua: esperando tu siguiente frase |
| ⚪ Gris con arco | Cargando los modelos al iniciar |

En reposo se oculta (se puede dejar visible). Los colores se pueden cambiar.
**Clic derecho**: escribir, escuchar, terminar, ocultar, configuración, salir.
**Doble clic**: escribir un mensaje.

### 💬 El panel de respuesta

Muestra lo que dijiste y la respuesta mientras se genera, con formato (negritas,
listas, código), miniaturas de las capturas (clic para abrirlas) y notas de lo
que ha hecho (memoria, recordatorios). Botones: 🔊 silenciar la voz, ⎘ copiar,
× cerrar, y una caja para seguir escribiendo. Se cierra solo tras unos segundos
(el contador se detiene con el ratón encima).

### ⚡ Rendimiento

- Los modelos se **cargan al iniciar**, así que la primera orden no espera.
- Con una **gráfica NVIDIA**, Whisper transcribe en ~0,5 s (en CPU, varios segundos).
- Whisper descarta las frases que se inventa con ruido («¡Gracias por ver el vídeo!»…).

---

## 2. Requisitos

**Imprescindible**

- **Windows 10 u 11** de 64 bits.
- **Ollama** → <https://ollama.com/download> y al menos un modelo (ver abajo).
- Un **micrófono**.

No hace falta instalar Python ni nada más: la aplicación lo lleva todo dentro.

**Opcional**

- **Cámara web**, para las fotos.
- **Gráfica NVIDIA**, para transcribir mucho más rápido (ver *Gráfica NVIDIA* más abajo).
- **Node.js 20 o superior** (<https://nodejs.org>), solo para WhatsApp.
- **Internet**: para la palabra clave si eliges Google, buscar en la web,
  usar modelos *cloud* y descargar los modelos la primera vez.

**¿Qué modelo de Ollama elegir?**

| Modelo | Tamaño | Notas |
|---|---|---|
| `gemma3:4b` | ~3,3 GB | **Recomendado** para empezar: buen español y **ve imágenes**. Es el modelo por defecto. |
| `gemma3:12b` | ~8 GB | Más listo; necesita más memoria (ideal con una gráfica de 12 GB o más). |
| Modelos *cloud* (terminan en `-cloud`) | — | Se ejecutan en los servidores de Ollama: muy potentes y rápidos sin gastar tu PC. Requieren `ollama signin`. |

Para descargar un modelo abre una terminal y escribe, por ejemplo, `ollama pull gemma3:4b`.
Para que funcionen la pantalla, la cámara y el control del PC, el modelo debe
**admitir imágenes** (o puedes elegir un modelo de visión aparte en Configuración → Visión).

---

## 3. Instalación

1. Descarga **`Instalar Rubencho AI.exe`** de [Releases](https://github.com/Rubencho80/Rubencho-AI/releases/latest),
   haz doble clic en él y sigue el asistente:
   - **Acceso directo en el escritorio** (opcional).
   - **Abrir Rubencho AI automáticamente al iniciar Windows** (recomendado).
   - **Descargar el navegador** para que la IA pueda usar páginas web (opcional;
     si no lo marcas, se descarga solo la primera vez que haga falta).
2. Se instala para tu usuario (no pide permisos de administrador) en
   `%LOCALAPPDATA%\Programs\Rubencho AI`.
3. Al terminar, marca **«Abrir Rubencho AI ahora»**.

> Si el instalador dice que **Rubencho AI está en ejecución**, ciérralo (clic
> derecho en su icono junto al reloj → **Salir**) y pulsa **Reintentar**. Pasa
> también si tenías abierta la versión anterior.

### Si ya usabas la versión anterior (el archivo .pyw)

- La primera vez que se abre, **copia todos tus datos** (configuración, memoria,
  recordatorios, capturas, sesión de WhatsApp e historial de conversaciones) a la
  carpeta nueva **`%APPDATA%\Rubencho AI`**. La carpeta antigua `.voiceai` no se
  toca, por si quieres volver a la versión anterior.
- Si marcas *Abrir Rubencho AI automáticamente al iniciar Windows*, la versión
  anterior deja de arrancar sola, para que no se abran las dos.

### Fijarlo en la barra de tareas

- **Menú Inicio** → busca «Rubencho AI» → clic derecho → **Anclar a la barra de tareas**.
- O con la Configuración abierta: clic derecho en su icono de la barra de tareas →
  **Anclar a la barra de tareas**.

Al pulsar el icono fijado: si Rubencho AI está cerrado, se abre; si ya está
abierto, aparece la ventana **«Escribir a Rubencho AI»**.

---

## 4. Primer arranque

1. Aparece el **orbe gris** mientras se cargan los modelos y un aviso de que
   Rubencho AI está en marcha. La primera vez, Whisper descarga su modelo
   (`small` ≈ 250 MB; `medium` ≈ 770 MB), así que puede tardar un poco.
2. Abre la **Configuración** (clic derecho en el icono de la bandeja) y revisa:
   - **IA / Ollama** → *Detectar modelos* y elige el tuyo. En *Prompt de sistema*
     escribe cómo quieres que sea (tu nombre, cómo debe hablarte, su
     personalidad…). Las instrucciones de las herramientas se añaden solas.
   - **General** → *Iniciar con el sistema operativo* si quieres que arranque
     con Windows.
   - **Palabra clave** → la palabra para llamarle.
   - **Voz IA** → activa *Leer la respuesta en voz alta*, pulsa *Detectar voces*
     y elige una (las voces «OneCore» suenan más naturales).
   - **Reconocimiento** → modelo de Whisper (`small` va bien; `medium` es más
     preciso) y dispositivo (`auto` usa la GPU si puede).
3. Pulsa **Guardar**: los cambios se aplican al momento.
4. Prueba: di la palabra clave y luego «¿qué hora es?», o haz clic en el icono
   de la bandeja y escríbelo.

---

## 5. Cómo usarlo

### Menú del icono de la bandeja

| Opción | Qué hace |
|---|---|
| *Rubencho AI* | El nombre de la aplicación (es el texto que ves al pasar el ratón por el icono). |
| ✍️ Escribir mensaje | Abre la caja para escribir (también con **clic izquierdo** en el icono). *Enter* envía · *Shift+Enter* salto de línea · *Esc* cierra. |
| 🎙 Escuchar ahora | Empieza a escuchar sin decir la palabra clave. |
| 🛑 Detener escucha | Corta la escucha o la conversación continua. |
| 🖱 Control del PC | Activa o desactiva que la IA use el ratón y el teclado (✔ = activado). |
| ⛔ Detener el control del PC | Solo aparece mientras la IA está usando el PC: lo detiene al momento. |
| ⏰ Recordatorios… / 🧠 Memoria… | Abre esas secciones de la configuración. |
| 👁 Mostrar orbe | Vuelve a mostrar el orbe si lo ocultaste. |
| 🗑 Limpiar historial | Olvida la conversación actual (no la memoria). |
| ⚙️ Configuración · ❌ Salir | — |

### Consejos

- Habla con naturalidad: «oye, recuérdame el viernes a las cinco de la tarde que
  llame al taller» funciona.
- Para tiempos relativos no hace falta calcular: «en 45 minutos», «dentro de 2
  horas y media»…
- Si quieres que recuerde algo para siempre, díselo: «apúntate que…».
- Para ver qué recuerda o qué recordatorios tienes, pregúntaselo o mira la
  Configuración.

---

## 6. Configuración

| Sección | Qué se ajusta |
|---|---|
| **General** | Inicio con Windows, popup siempre encima, pitido al detectar la palabra, conversación continua (tiempo y palabra de parada), idioma, **fecha y hora en cada mensaje** y el botón **Abrir la carpeta de datos**. |
| **Palabra clave** | Palabra de activación (lista o personalizada). |
| **Reconocimiento** | Motor de la palabra clave (local al instante con Vosk, o Google), tiempos de escucha, detección de fin de frase, motor de la orden (Whisper/Google/Vosk), modelo, dispositivo (auto/cpu/cuda), precisión y precarga de Whisper. |
| **IA / Ollama** | Servidor y modelo, mantener el modelo cargado, tamaño de contexto, **razonamiento** (nunca, siempre o que decida la IA según lo complicado que sea), herramientas (comandos, búsqueda web, navegador), **prompt de sistema** y botón para ver las instrucciones completas que recibe la IA. |
| **Control del PC** | Activarlo, elementos numerados, cuadrícula, captura de comprobación, resolución enviada, todas las **precauciones** (confirmación, freno con tecla y con esquina, parar al mover el ratón, juegos a pantalla completa, aviso, límite de pasos, pausa entre acciones) y el botón *Ver lo que ve la IA*. |
| **Visión** | Permitir capturas y cámara, ocultar el orbe/popup al capturar, nº de cámara, tamaño de las imágenes, cuántas conservar, modelo de visión opcional, botones de prueba. |
| **Memoria** | Activarla y ver, añadir, editar o borrar lo que recuerda. |
| **Recordatorios** | Activarlos, sonido (repeticiones o un sonido propio .wav/.mp3), lectura en voz alta, aviso por WhatsApp, minutos al posponer, lista de pendientes y pruebas. |
| **Tareas de la IA** | Permitir que la IA se programe tareas, mandarte por WhatsApp lo que ha hecho, confirmar o no sus WhatsApps, y lista de tareas pendientes. |
| **Orbe** | Visibilidad, opacidad, tamaño, **color de cada modo** (con vista previa) y posición. |
| **Popup** | Colores, opacidad, tamaño, posición, cierre automático (0 = nunca) y cierre al terminar de hablar. |
| **Voz IA** | Activar la voz, motor (Windows/Google), velocidad, volumen y voz, y si se leen también las respuestas a mensajes escritos. |
| **Conversación** | **Cuántos mensajes anteriores se le envían** (los más antiguos se olvidan solos) y si se olvidan los de hace más de X horas; guardar las conversaciones en un .txt, recuperar las últimas al iniciar y cuántas se guardan en el fichero. |
| **WhatsApp** | Activar la integración, arrancar el puente, **responder o no a lo que te escribes en tu chat propio** (o solo si le llamas por tus palabras), ver el QR, volver a vincular, **a qué contactos puede escribir**, si puede leer tus mensajes, ver fotos y escuchar audios, **máximo de mensajes que puede leer hacia atrás**, confirmación antes de enviar y envío de prueba. |
| **Push-to-Talk** | Activar y elegir la tecla o combinación. |

La memoria y los recordatorios se guardan al momento; el resto, al pulsar **Guardar**.

### WhatsApp (opcional)

1. Necesitas tener instalado **Node.js** (el resto ya viene con la aplicación).
2. Configuración → WhatsApp → activa la integración y guarda.
3. Pulsa *Abrir QR* y escanéalo desde WhatsApp → *Dispositivos vinculados*.
4. En **Contactos y mensajes** marca (doble clic) a quién puede escribir Rubencho,
   o permite que escriba a todos. Ahí eliges también si puede leer tus mensajes,
   ver las fotos, escuchar los audios y cuántos mensajes como máximo puede leer.
5. Pídeselo con naturalidad: «escríbele a Mamá que llego tarde», «¿qué me ha
   dicho Juan?», «resúmeme el audio de Ana». La IA decide cuántos mensajes leer
   antes de responder (pocos si basta con lo último, más si le pides un resumen).
6. También puedes escribirle en tu chat contigo mismo: te contesta allí. Si
   usas ese chat también para tus notas, activa **«solo si le llamo por una de
   estas palabras»** (por ejemplo «asistente, rubencho»): entonces solo contesta a
   los mensajes que lleven una de ellas.

> Rubencho solo puede leer los mensajes que llegan mientras el puente está en
> marcha y los que WhatsApp envía al vincular. Si la lista de contactos sale
> vacía, pulsa **Volver a vincular** y escanea el QR otra vez: al vincular,
> WhatsApp envía la agenda completa y los mensajes recientes de tus chats.

### Gráfica NVIDIA

Con el dispositivo en `auto` (Configuración → Reconocimiento), Whisper usa la
gráfica si encuentra las librerías de NVIDIA **cuBLAS 12** y **cuDNN 9**: ~0,5 s
por orden en vez de varios segundos. La aplicación las busca en los Python que
tengas instalados (paquetes `nvidia-cublas-cu12` y `nvidia-cudnn-cu12`), en el
CUDA Toolkit o en una carpeta `gpu` junto a `Rubencho AI.exe`. A cambio **ocupa memoria de vídeo mientras el programa está abierto**
(≈1 GB con `medium`); si algún juego va justo, elige `cpu`.

---

## 7. Dónde se guardan los datos

Todo está en **`%APPDATA%\Rubencho AI`** (Configuración → General → **Abrir la
carpeta de datos**):

| Archivo / carpeta | Contenido |
|---|---|
| `config.json` | La configuración |
| `memoria.json` | Lo que la IA recuerda de ti |
| `recordatorios.json` | Los recordatorios |
| `tareas_ia.json` | Las tareas que la IA se ha programado |
| `historial_conversaciones.txt` | Las conversaciones (si activas el log) |
| `capturas\` | Capturas de pantalla, fotos y lo último que vio la IA al controlar el PC (`control_*.jpg`); se borran las más antiguas |
| `sonidos\` | Sonidos de aviso generados por el programa |
| `cmd_log.txt` | Registro de los comandos que ha ejecutado la IA |
| `whatsapp_session\` | Sesión de WhatsApp vinculada (no la borres si usas WhatsApp) |
| `whatsapp_store\` | Tu agenda (nombres) y los mensajes de tus chats individuales, para poder leerlos cuando se lo pidas; también las transcripciones de los audios y las fotos vistas |
| `rubencho_consola.log` | Mensajes y errores del programa (útil si algo falla) |

La aplicación está en `%LOCALAPPDATA%\Programs\Rubencho AI`. Los modelos de
Whisper se guardan en `%USERPROFILE%\.cache\huggingface\`.

---

## 8. Privacidad y seguridad

- **Pantalla y cámara**: la IA las usa sin pedir confirmación cuando cree que
  hace falta. Se pueden desactivar en Configuración → Visión. La luz de la cámara
  se enciende al hacer una foto.
- **Modelos cloud**: con un modelo que termina en `-cloud`, tus mensajes y las
  imágenes se envían a los servidores de Ollama. Con un modelo local todo se
  queda en tu PC. También puedes elegir en Configuración → Visión un modelo local
  solo para las imágenes.
- **Palabra clave**: con el modo local (el predeterminado) el micrófono se
  analiza en tu PC con Vosk y no sale nada de él hasta que dices la palabra. Si
  eliges Google, las frases cortas que oye el micrófono se envían a Google.
- **Comandos**: se bloquean los destructivos (borrar, formatear, apagar,
  registro…), cada comando tiene un límite de 15 s y todos quedan anotados en
  `cmd_log.txt`. Si no quieres que ejecute comandos, desactívalo en
  Configuración → IA.
- **WhatsApp**: solo envía mensajes cuando se lo pides, nunca a grupos y solo a los
  contactos que permitas (y, si quieres, te pide confirmación antes). Los mensajes
  que te mandan **nunca le llegan solos a la IA**: solo los lee cuando tú se lo
  pides, y como mucho los que hayas puesto como máximo. La IA nunca ve números de
  teléfono, solo los nombres de tu agenda. Los mensajes se guardan solo en tu PC.
- **Control del PC**: viene desactivado. Cuando está activo, la IA ve la pantalla
  (y los títulos de las ventanas abiertas) cada vez que actúa; con un modelo
  *cloud* esas capturas se envían a Ollama. Las acciones peligrosas piden
  confirmación y siempre puedes pararla con **Esc**, llevando el ratón a una
  esquina o desde la bandeja. Nunca le dejes escribir contraseñas ni datos
  bancarios: está instruida para pedirte que lo hagas tú.

---

## 9. Solución de problemas

**Lo primero**: mira `rubencho_consola.log` en la carpeta de datos (Configuración →
General → Abrir la carpeta de datos); ahí se anota lo que hace el programa y por
qué falla algo. Para comprobar todas las piezas de golpe, abre una terminal y ejecuta:

```bat
"%LOCALAPPDATA%\Programs\Rubencho AI\Rubencho AI.exe" --diagnostico
```

y mira el archivo `diagnostico.txt` que aparece en la carpeta de datos.

| Problema | Solución |
|---|---|
| No responde a la palabra clave | Comprueba el micrófono predeterminado de Windows. Con Google hace falta internet. Ajusta *Pausa para terminar frase* y el *Umbral de energía* en Reconocimiento. |
| «No puedo conectar con Ollama» | Abre Ollama (debe aparecer en la bandeja) o ejecuta `ollama serve`. |
| «El modelo … no está instalado» | `ollama pull nombre-del-modelo`, o elige otro en Configuración → IA → *Detectar modelos*. |
| No entiende las capturas ni las fotos | Tu modelo no admite imágenes: usa uno con visión (p. ej. `gemma3:4b`) o elige un modelo de visión en Configuración → Visión. |
| La cámara no abre o sale negra | Cierra otras apps que la usen, revisa la tapa y prueba otro *Cámara nº* (0, 1, 2…) con *Probar cámara*. |
| Transcribe lento | Usa la GPU, el modelo `small` o *Precisión (beam)* = 1. |
| No suena el recordatorio | Revisa el volumen y Configuración → Recordatorios → *Probar sonido*. Aunque Windows esté en «No molestar», la ventana del aviso aparece igualmente. |
| No tengo voz | Activa la voz en Configuración → Voz IA y pulsa *Detectar voces*. Comprueba que no esté silenciada (🔇 en el panel). |
| Whisper va en CPU teniendo NVIDIA | Faltan las librerías de NVIDIA (ver *Gráfica NVIDIA*). El log dice el motivo. |
| WhatsApp no conecta | Instala Node.js, pulsa *Arrancar bridge* en Configuración → WhatsApp y escanea el QR. |
| La IA dice que no puede controlar el PC | Actívalo en Configuración → Control del PC o en el menú del icono. |
| El control web dice que falta el navegador | Se descarga solo la primera vez (≈150 MB, hace falta internet). |
| «Rubencho AI ya está en marcha» | La versión anterior está abierta: ciérrala desde su icono (Salir) y abre la nueva. |
| Hace clic en el sitio equivocado | Deja activados los *elementos numerados* y la *cuadrícula*; usa un modelo con visión potente. Con *Ver lo que ve la IA* compruebas qué recibe. |
| Se para sola al trabajar | Puede que el ratón estuviera en una esquina o que tocaras **Esc**; también se para con un juego a pantalla completa. |

---

## 10. Desinstalar

1. **Configuración de Windows → Aplicaciones → Aplicaciones instaladas** →
   **Rubencho AI** → **Desinstalar** (o desde el menú Inicio: clic derecho →
   Desinstalar).
2. Al final te pregunta si quieres **borrar también tus datos** (configuración,
   memoria, recordatorios…). Si vas a reinstalarlo, di que **no** para conservarlos.
3. Opcional: borra `%USERPROFILE%\.cache\huggingface\` (modelos de Whisper) y los
   modelos de Ollama con `ollama rm nombre-del-modelo`.

---

## 11. Contenido del repositorio y cómo compilar

| Archivo / carpeta | Para qué sirve |
|---|---|
| `README.md` | Este documento |
| `CHANGELOG.md` | Novedades de cada versión |
| `Código fuente/Rubencho AI.pyw` | El programa entero (Python + Tkinter) |
| `Código fuente/whatsapp/` | Puente de WhatsApp en Node.js ([Baileys](https://github.com/WhiskeySockets/Baileys)) |
| `Código fuente/recursos/` | Icono e imágenes del instalador (`crear_icono.py` los vuelve a generar) |
| `Código fuente/Rubencho AI.spec` | Receta de PyInstaller |
| `Código fuente/instalador.iss` | Script de Inno Setup (asistente, accesos directos, inicio con Windows, desinstalador) |
| `Código fuente/version_info.txt` | Nombre, descripción y versión del `.exe` |
| `Código fuente/compilar.bat` | Compila la aplicación y crea el instalador |
| `Código fuente/requirements.txt` | Librerías de Python |
| `Código fuente/COMPILAR.md` | Detalles de la compilación |

El instalador no está en el repositorio (pesa ~190 MB): se publica en
[Releases](https://github.com/Rubencho80/Rubencho-AI/releases).

### Ejecutar desde el código (sin compilar)

Necesitas **Python 3.13** y, para WhatsApp, **Node.js 20+**:

```bat
cd "Código fuente"
python -m pip install -r requirements.txt
cd whatsapp && npm ci && cd ..
pythonw "Rubencho AI.pyw"
```

### Compilar el instalador

Necesitas además **Inno Setup 6** (`winget install JRSoftware.InnoSetup`).
Ejecuta `Código fuente\compilar.bat`: en unos minutos crea
`Instalar Rubencho AI.exe` en la carpeta raíz del repositorio. Más detalles en
[`COMPILAR.md`](Código%20fuente/COMPILAR.md).

---

## 12. Licencia

[MIT](LICENSE): puedes usarlo, modificarlo y compartirlo libremente, manteniendo
el aviso de copyright. Se entrega «tal cual», sin garantías.

Usa, entre otros, [Ollama](https://ollama.com),
[faster-whisper](https://github.com/SYSTRAN/faster-whisper),
[Vosk](https://alphacephei.com/vosk), [Baileys](https://github.com/WhiskeySockets/Baileys)
y [Playwright](https://playwright.dev). WhatsApp funciona mediante una conexión
no oficial (como un dispositivo vinculado más): úsala con responsabilidad.
