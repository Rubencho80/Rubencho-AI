# Historial de versiones

Las versiones se publican en [Releases](../../releases) con su instalador
(`Instalar Rubencho AI.exe`).

## 1.3.6 — 22-10-2026

- **Audios en tu chat propio de WhatsApp**: si te mandas una nota de voz, Rubencho
  la transcribe con Whisper y te contesta como a un mensaje escrito (antes los
  audios se ignoraban). La IA sabe que era un audio. Con «solo si le llamo por una
  de estas palabras», el audio tiene que llevar una de ellas.
- Lo que llega por tu chat propio se contesta solo allí: **sin panel ni voz en el
  PC** (el panel no se cerraba nunca). Se puede volver a mostrar en
  Configuración → WhatsApp → «…y mostrar en el PC lo que me contesta ahí».

## 1.3.5 — 20-10-2026

- **Razonamiento: «Que decida la IA»** (Configuración → IA / Ollama), además de
  «Nunca» y «Siempre». Responde directamente y, si ve que es algo realmente
  complicado (un problema de lógica, un plan con muchas condiciones, programar…)
  o que se ha equivocado, lo vuelve a hacer con el razonamiento de Ollama
  activado. También puede decidirlo a mitad de una tarea si un paso falla, y
  guardar en la memoria qué cosas le cuesta hacer para pensarlas a la primera
  la próxima vez. Solo con modelos que razonan (como Gemma 4).
- En la prueba con casos nuevos acertó cuándo pensar en 12 de 14 (y nunca pensó
  en lo sencillo); con el razonamiento, el acertijo de las cajas pasa de mal a
  bien (de 1,4 s a unos 6 s).

## 1.3.4 — 20-10-2026

- **Ya no contesta de memoria cuando le vuelves a preguntar** («¿y ahora qué
  dice?», «¿me ha contestado?»). El historial solo guardaba tu pregunta y la
  respuesta final, así que la IA veía que había contado unos mensajes sin
  mirar nada y a la segunda copiaba ese ejemplo: a veces se inventaba lo que
  ponían. Ahora el historial guarda también qué herramientas usó (sin los
  resultados, que caducan) y una nota de que, para volver a saberlo, hay que
  usarlas otra vez. El control del PC solo se apunta contado, para que nunca
  repita clics antiguos. Además, una regla nueva de WhatsApp: si le vuelves a
  preguntar por los mensajes de alguien, los vuelve a leer.
- En la prueba, a la segunda pregunta volvía a mirar WhatsApp 4 de cada 8
  veces; ahora, todas.

## 1.3.3 — 19-10-2026

- **Tareas de la IA**: recordatorios que la IA se pone a sí misma. Al llegar la
  hora le llega lo que tenía que hacer y lo hace con sus herramientas, aunque no
  estés delante («mañana a las 8 mándale a mi padre que llego a las 3»). Son
  distintos de los recordatorios normales, que te avisan a ti. Tienen su propia
  sección en la configuración (lista, crear, borrar), opción de mandarte por
  WhatsApp lo que ha hecho y de confirmar sus WhatsApps.
- **Chat propio de WhatsApp**: opción para que solo conteste si le llamas por una
  de tus palabras (por ejemplo «asistente, rubencho»); si no, aunque sea tu chat
  contigo mismo, no contesta.

## 1.3.2 — 18-10-2026

- **Palabra clave al instante**: se reconoce en el PC con Vosk mientras la dices,
  sin esperar a que acabes la frase ni a Google. Ya no hay que hacer pausa:
  «asistente, ¿qué hora es?» de corrido también funciona, porque la orden se graba
  del mismo audio. Gasta muy poca CPU y no envía nada a internet. La palabra
  clave predeterminada pasa a ser «asistente» (Vosk no conoce «jarvis»; con
  palabras inventadas o en inglés se puede seguir usando Google).
- El instalador incluye el modelo de Vosk en español (unos 40 MB).
- **Memoria de la conversación** (Configuración → Conversación): número de
  mensajes anteriores que se le envían (0–100, los más antiguos se olvidan solos),
  opción para olvidar los de hace más de X horas y número de conversaciones que se
  guardan en el log (las más antiguas se borran solas). Al iniciar solo se
  recuperan del log los últimos mensajes, nunca el log entero.

## 1.3.1 — 18-10-2026

- **WhatsApp: los mensajes enviados ya no se quedan en «Esperando el mensaje»**.
  El puente usaba Baileys 6.7, que cifraba los mensajes para el número de
  teléfono, pero WhatsApp ya identifica los dispositivos por su LID y el móvil
  que los recibía no podía descifrarlos. Ahora usa Baileys 7.0.0-rc14, con
  direcciones LID.
- Si un móvil no consigue descifrar un mensaje y pide que se le reenvíe, el puente
  se lo reenvía (antes no podía).
- Los mensajes que manda el puente se marcan antes de enviarlos, para que su eco
  en el chat propio nunca se tome como una orden.
- Ahora hace falta **Node.js 20 o superior** (antes 18).

## 1.3.0 — 17-10-2026

Primera versión publicada en GitHub.

- **Aplicación de escritorio real**: instalador `.exe` con su icono y nombre,
  se puede fijar en la barra de tareas, datos en `%APPDATA%\Rubencho AI`,
  inicio con Windows y desinstalador.
- **WhatsApp**: escribir a tus contactos (solo a los que permitas, con
  confirmación opcional), lista de contactos por nombre (nunca números), leer
  mensajes anteriores cuando se lo pides (la IA decide cuántos, hasta el máximo
  que elijas), ver fotos y escuchar audios con Whisper. Los mensajes recibidos
  nunca le llegan solos a la IA.
- Opción para activar o desactivar que conteste a lo que te escribes en tu chat
  propio de WhatsApp.
- Puente de WhatsApp más robusto: claves de sincronización a salvo del sistema de
  archivos de Windows (que no distingue mayúsculas) y uso del historial reciente
  que WhatsApp envía al vincular.
- **Control del PC** con ratón y teclado: elementos numerados, cuadrícula con zoom,
  captura de comprobación y precauciones activables (confirmación de acciones
  peligrosas, freno con Esc o con una esquina, límite de pasos…).
- Whisper en la gráfica NVIDIA (≈0,5 s por orden).
- Pantalla, cámara, memoria, recordatorios, búsqueda web, navegador y voz.
