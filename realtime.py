import asyncio
import base64
from typing import Any, cast

import pyaudio
from openai import AsyncOpenAI

async_client = AsyncOpenAI(api_key="")

# Audio properties
RATE = 24000  # Sample rate (Hz)
CHANNELS = 1  # Mono audio
FORMAT = pyaudio.paInt16  # PCM format (16-bit)
BUFFER_SIZE = 1024  # Number of frames per buffer
THRESHOLD = 1000  # Threshold for audio volume detection (RMS value)
p = pyaudio.PyAudio()  # Open the audio stream
stream = p.open(
    format=FORMAT,
    channels=CHANNELS,
    rate=RATE,
    output=True,
    input=True,
    frames_per_buffer=BUFFER_SIZE,
)


async def main() -> None:
    """
    When prompted for user input, type a message and hit enter to send it to the model. Enter "q" to quit the conversation.
    """
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
        # After the session is configured, data can be sent to the session.
        while True:
            input_audio = stream.read(BUFFER_SIZE)
            await connection.conversation.item.create(
                item={
                    "type": "message",
                    "role": "system",
                    "content": [
                        {"type": "input_text", "text": "say the greeting response."}
                    ],
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
