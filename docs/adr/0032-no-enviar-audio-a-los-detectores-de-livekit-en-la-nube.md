# AD-32: no enviar audio a los detectores de LiveKit en la nube

- **Estado:** propuesta (pasa a aceptada al integrarse este PR)
- **Fecha:** 2026-10-26
- **Deciden:** Diego, Angélica
- **Historia:** AGI-62 (subtarea AGI-156)

## Contexto

Agilina habla en la sala con una `AgentSession` de livekit-agents (1.8.4) y la voz de ElevenLabs.
El spike de voz (HU-01) mostró que, sin pedirlo, la sesión manda el audio de las personas a
servicios de LiveKit en la nube:

- **Detector de fin de turno.** Si nadie fija la detección de turno, livekit-agents usa el modelo
  `turn-detector-v1`, que corre en el gateway de inferencia de LiveKit, cuando el worker corre en
  modo `dev` (`LIVEKIT_DEV_MODE`) o alojado en LiveKit Cloud; en `start` usa el modelo local
  `turn-detector-v1-mini`.
- **Detector de interrupciones.** Con las mismas condiciones crea un
  `AdaptiveInterruptionDetector`, que también analiza el audio en la nube.
- **Grabación.** `AgentSession.start` graba según el `enable_recording` del proyecto de LiveKit, y
  la observabilidad del proyecto se enciende desde su consola sin cambiar código.

Que el audio de la conversación salga a un tercero sin que el equipo lo sepa es un problema de
privacidad, y la historia AGI-62 lo prohíbe (CA8). Además, lo que se dice antes de iniciar la
ceremonia no puede quedar registrado (CA6). Por otro lado, lo que dice Agilina son plantillas
cortas: un saludo o un aviso, no una conversación, así que no necesita detectar turnos ni que la
interrumpan para cumplir su papel en esta historia.

## Decisión

La sesión de voz de Agilina solo habla y nunca analiza el audio de la sala: se crea sin STT, sin
LLM y con `vad=None`; la detección de fin de turno es **manual**, las **interrupciones están
apagadas** (`interruption.enabled = False`), la sesión no toma el audio de la sala
(`audio_input=False`), se inicia con `record=False` y el worker corre en modo `start`. En espera
el transcriptor propio (Whisper) tampoco se llama. Todo eso queda fijado explícitamente en el
código (`agent/src/agilina_agent/infrastructure/speech_synthesizers.py`), sin depender de los
valores por defecto de livekit-agents ni del modo en que corra el worker.

ElevenLabs solo recibe el texto de la plantilla, nunca audio de la sala.

## Alternativas descartadas

| Alternativa | Por qué no |
| --- | --- |
| Mantener los detectores en la nube | Mandan el audio de las personas a LiveKit sin que el equipo lo sepa (CA8). Agilina no conversa: sus mensajes son plantillas cortas y no gana nada con detectar turnos |
| Apagar el de fin de turno y mantener el de interrupciones durante la ceremonia, documentando el riesgo | El de interrupciones también analiza el audio en la nube; aceptarlo sería aceptar la misma fuga que el CA8 prohíbe |
| Confiar en los valores por defecto de `start` | Basta correr el worker en `dev` o alojarlo en LiveKit Cloud para que vuelvan a encenderse, sin ningún cambio visible en el código |
| Usar el detector local `turn-detector-v1-mini` o el VAD local (Silero) | No envían audio afuera, pero hoy no hay nada que detectar: se decide cuando la facilitación por turnos lo necesite (AGI-65 y siguientes) |

## Consecuencias

- Agilina no reacciona a lo que se dice: si alguien habla encima de ella, termina la frase. Para
  plantillas de una o dos oraciones es aceptable.
- Cuando la facilitación necesite escuchar (iniciar la daily, turnos, palabra de activación), el
  audio irá al servicio de transcripción propio (`stt/`), no a LiveKit. Reactivar un detector en
  la nube exige un ADR que supersede este.
- `record=False` evita la grabación de la sesión, pero no controla la observabilidad del proyecto
  de LiveKit Cloud: hay que mantenerla apagada en su consola y revisarlo al verificar
  ([ciclo-de-vida-del-agente.md](../ciclo-de-vida-del-agente.md#8-cómo-se-verifica)).
- Una versión nueva de livekit-agents puede cambiar sus valores por defecto; como la
  configuración es explícita y está probada, el cambio no la enciende sola.
- Revertir es barato: es configuración de la sesión en un solo adaptador.

## Cómo se verifica

- `tests/agent/unit/infrastructure/test_speech_synthesizers.py`: la sesión tiene el fin de turno
  manual, las interrupciones apagadas, ni STT ni VAD, no toma el audio de la sala, y se inicia una
  sola vez con `record=False`.
- `tests/agent/unit/presentation/test_room_job.py`: en espera, con o sin contexto, el transcriptor
  nunca se llama.
- En los logs del worker (`make logs s=agent`), `received job request` trae
  `"enable_recording": false`.
