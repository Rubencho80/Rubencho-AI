# Historial de versiones

Las versiones se publican en [Releases](../../releases) con su instalador
(`Instalar Rubencho AI.exe`).

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
