# Historial de versiones

Las versiones se publican en [Releases](../../releases) con su instalador
(`Instalar Rubencho AI.exe`).

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
