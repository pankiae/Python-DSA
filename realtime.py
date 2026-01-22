import asyncio
import base64
import time
from typing import Any, cast

import numpy as np
import pyaudio
from openai import AsyncOpenAI

async_client = AsyncOpenAI(api_key="")

# Audio properties
SILENCE_DURATION = 2  # seconds of silence to wait before sending audio for processing
RATE = 24000  # Sample rate (Hz)
CHANNELS = 1  # Mono audio
FORMAT = pyaudio.paInt16  # PCM format (16-bit)
BUFFER_SIZE = 1024  # Number of frames per buffer
THRESHOLD = 30  # Threshold for audio volume detection (RMS value)
p = pyaudio.PyAudio()  # Open the audio stream

stream = p.open(
    format=FORMAT,
    channels=CHANNELS,
    rate=RATE,
    output=True,
    input=True,
    frames_per_buffer=BUFFER_SIZE,
)

ai_speaking = False
last_audio_time = time.time()


# Helper functions
def calculate_rms(audio_data: bytes) -> float:
    """Calculate RMS value from audio data."""
    audio_np = np.frombuffer(audio_data, dtype=np.int16)
    if audio_np.size == 0:
        return float("nan")  # Handle empty buffers
    rms = np.sqrt(np.mean(audio_np**2))
    return rms


async def capture_and_send_audio(connection):
    """Continuously capture audio from mic and send to AI"""
    global ai_speaking, last_audio_time

    while True:
        try:
            # Read audio from microphone
            input_audio = stream.read(BUFFER_SIZE, exception_on_overflow=False)
            print(f"Read {len(input_audio)} bytes")

            rms_value = calculate_rms(input_audio)
            print(f"{rms_value= }")

            # Detect speech
            if rms_value > THRESHOLD:
                last_audio_time = time.time()

                # Barge-in: cancel AI if user starts speaking
                if ai_speaking:
                    print("🎤 Barge-in detected, canceling AI response.")
                    await connection.response.cancel()
                    ai_speaking = False

                # Send audio to buffer
                base64_audio = base64.b64encode(input_audio).decode("utf-8")

                await connection.input_audio_buffer.append(audio=base64_audio)
                print("📤 Audio appended to buffer")

            # Detect silence after speech
            elif time.time() - last_audio_time > SILENCE_DURATION and not ai_speaking:
                print("🔇 Silence detected, creating response...")
                await connection.response.create()
                last_audio_time = time.time()  # Reset to avoid repeat triggers

            await asyncio.sleep(0.01)  # Small delay to prevent CPU spinning

        except Exception as e:
            print(f"❌ Error in audio capture: {e}")
            await asyncio.sleep(0.1)


async def handle_ai_events(connection):
    """Handle events from the AI"""
    global ai_speaking

    async for event in connection:
        print(f"\n📨 Event: {event.type}\n")

        if event.type == "response.output_text.delta":
            print(event.delta, flush=True, end="")

        # elif event.type == "session.created":
        #     # print(f"✅ Session ID: {event.session.id}")

        elif event.type == "response.output_audio.delta":
            ai_speaking = True
            audio_data = base64.b64decode(event.delta)
            stream.write(audio_data)
            print(f"🔊 Playing {len(audio_data)} bytes of audio")

        elif event.type == "response.input_audio_transcript.delta":
            print(f"👤 User said: {event.delta}")

        elif event.type == "response.output_audio_transcript.delta":
            print(f"🤖 AI said: {event.delta}")

        elif event.type == "response.function_call_arguments.delta":
            print("🔧 Function call event:")
            print(event)

        elif event.type == "response.output_text.done":
            print()

        elif event.type == "error":
            print("❌ Error event:")
            print(f"  Code: {event.error.code}")
            print(f"  Message: {event.error.message}")

        elif event.type == "response.done":
            ai_speaking = False
            print("✅ Response complete")


async def main() -> None:
    global ai_speaking, last_audio_time

    try:
        async with async_client.realtime.connect(
            model="gpt-4o-realtime-preview",
        ) as connection:
            print("🔗 Connected to OpenAI Realtime API")

            # Configure session
            await connection.session.update(
                session={
                    "type": "realtime",
                    "instructions": "You are a helpful assistant. You respond by voice and text. You have access to a knowledge assistant and can call it when you need information not in your knowledge. Alway answer in the English",
                    "output_modalities": ["audio", "text"],
                    "audio": {
                        "input": {
                            "transcription": {"model": "whisper-1"},
                            "format": {"type": "audio/pcm", "rate": 24000},
                            "turn_detection": {"type": "server_vad"},
                        },
                        "output": {
                            "voice": "alloy",
                            "format": {"type": "audio/pcm", "rate": 24000},
                        },
                    },
                }
            )

            # Configure tools
            await connection.session.update(
                session={
                    "type": "realtime",
                    "tools": [
                        {
                            "type": "function",
                            "name": "get_knowledge",
                            "description": "Get knowledge from uploaded files and vector store",
                            "parameters": {
                                "type": "object",
                                "properties": {
                                    "query": {
                                        "type": "string",
                                        "description": "Query to retrieve semantic information",
                                    }
                                },
                                "required": ["query"],
                            },
                        }
                    ],
                    "tool_choice": "auto",
                }
            )

            # Send initial greeting
            await connection.conversation.item.create(
                item={
                    "type": "message",
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": "Say a greeting message"}
                    ],
                }
            )
            await connection.response.create()

            print("🎤 Starting audio capture and event handling...\n")

            # Run both tasks concurrently - THIS IS THE KEY!
            await asyncio.gather(
                capture_and_send_audio(connection),
                handle_ai_events(connection),
            )

    except KeyboardInterrupt:
        print("\n👋 Shutting down...")
    except Exception as e:
        print(f"❌ Fatal error: {e}")
    finally:
        stream.stop_stream()
        stream.close()
        p.terminate()
        print("🔌 Audio stream closed")


if __name__ == "__main__":
    asyncio.run(main())
