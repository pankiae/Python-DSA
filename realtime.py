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


async def main() -> None:
    """
    When prompted for user input, type a message and hit enter to send it to the model. Enter "q" to quit the conversation.
    """
    global ai_speaking, last_audio_time

    async with async_client.realtime.connect(
        model="gpt-realtime",
    ) as connection:
        # after the connection is created, configure the session.
        await connection.session.update(
            session={
                "type": "realtime",
                "instructions": "You are a helpful assistant. You respond by voice and text. You have the access to the knowledge assistant and you can call it when you have no information related to the user query in your knowledge. That knowledge assistant may retrieve some information if they have related to that query.So format the query/question and pass to that knowledge assistant whenever needed.",
                "output_modalities": ["audio", "text"],
                "audio": {
                    "input": {
                        "transcription": {
                            "model": "whisper-1",
                        },
                        "format": {
                            "type": "audio/pcm",
                            "rate": 24000,
                        },
                        "turn_detection": {
                            "type": "server_vad",
                            # "threshold": 0.5,
                            # "prefix_padding_ms": 300,
                            # "silence_duration_ms": 200,
                            # "create_response": True,
                        },
                    },
                    "output": {
                        "voice": "marin",
                        "format": {
                            "type": "audio/pcm",
                            "rate": 24000,
                        },
                    },
                },
            }
        )
        # user_input = input("Enter a message: ")
        user_input = "say the greeting message"
        await connection.conversation.item.create(
            item={
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": user_input}],
            }
        )

        await connection.session.update(
            session={
                "type": "realtime",
                "tools": [
                    {
                        "type": "function",
                        "name": "get_knowledge",
                        "description": "Get the knowledge from the uploaded files and instructions from the Vector Store Assistant.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "query": {
                                    "type": "string",
                                    "description": "user query to retrieve the sematic information from the uploaded vector store assistant.",
                                }
                            },
                            "required": ["query"],
                        },
                    }
                ],
                "tool_choice": "auto",
            }
        )
        await connection.response.create()
        # After the session is configured, data can be sent to the session.
        while True:
            input_audio = stream.read(BUFFER_SIZE)
            print(input_audio)
            rms_value = calculate_rms(input_audio)
            print(f"{rms_value= }")
            # Scenario 1: Silence detection after user speaks
            if rms_value > THRESHOLD:
                last_audio_time = time.time()  # Reset silence timer
                if ai_speaking:
                    # If AI is speaking, cancel AI response
                    print("Barge-in detected, canceling AI response.")
                    await connection.send({"type": "response.cancel"})
            else:
                # Check for 2 seconds of silence
                if time.time() - last_audio_time > SILENCE_DURATION:
                    print("Detected 2 seconds of silence, processing user input.")
                    # Send audio to AI for processing
                    await connection.input_audio_buffer.append(
                        audio=base64.b64encode(cast(Any, input_audio)).decode("utf-8")
                    )
                    await connection.response.create()

            async for event in connection:
                print(f"\n\n{event= }\n\n")
                if event.type == "response.output_text.delta":
                    print(event.delta, flush=True, end="")
                elif event.type == "session.created":
                    print(f"Session ID: {event.session.id}")
                elif event.type == "response.output_audio.delta":
                    audio_data = base64.b64decode(event.delta)
                    stream.write(audio_data)
                    print(f"Received {len(audio_data)} bytes of audio data.")
                elif event.type == "response.input_audio_transcript.delta":
                    print(f"User text delta: {event.delta}")
                elif event.type == "response.output_audio_transcript.delta":
                    print(f"Received text delta: {event.delta}")
                elif event.type == "response.function_call_arguments.delta":
                    print("function call event ...")
                    print(event)
                elif event.type == "response.output_text.done":
                    print()
                elif event.type == "error":
                    print("Received an error event.")
                    print(f"Error code: {event.error.code}")
                    print(f"Error Event ID: {event.error.event_id}")
                    print(f"Error message: {event.error.message}")
                elif event.type == "response.done":
                    print("response.done event ...")
                    print(event)
                    break

    print("Conversation ended.")
    connection.close()
    # Close the stream and terminate PyAudio
    stream.stop_stream()
    stream.close()
    p.terminate()


asyncio.run(main())
