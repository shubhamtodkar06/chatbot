# chat/consumers.py
import json
import os
import asyncio
import base64 # Import base64 for encoding audio

from channels.generic.websocket import AsyncWebsocketConsumer
from .services import google_cloud_voice
from . import chatbot_logic # Assuming this handles interaction with OpenAI
from django.contrib.auth import get_user_model



User = get_user_model()

# Removed anext helper function as it was for the STT generator
# async def anext(async_iterator):
#     return await async_iterator.__anext__()

print("--- Loading chat/consumers.py (Voice Consumer - Flow Slug Removed) ---") # Updated print for clarity

class VoiceChatConsumer(AsyncWebsocketConsumer):
    # --- Initialization and State ---

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Removed audio_queue, stt_task, _audio_stream_ended as STT is client-side
        self.thread_id = None  # OpenAI Assistant Thread ID for this connection
        self.user = None  # Authenticated Django User instance
        # REMOVED: self.flow_slug attribute is no longer needed


        print("VoiceChatConsumer: __init__ completed.")

    # --- Connection Handling ---

    async def connect(self):
        """Handles new WebSocket connections."""
        # This relies on AuthMiddlewareStack being configured in asgi.py
        # to populate self.scope['user'] based on the token in the URL.
        self.user = self.scope["user"]


        print(f"Voice WebSocket: Attempting connection for user: {self.user.username if self.user and not self.user.is_anonymous else 'Anonymous'})")
        # REMOVED: print(f"Voice WebSocket: Flow slug from URL: {self.flow_slug}")


        if self.user.is_anonymous:
            print("Voice WebSocket: Authentication failed (user is anonymous). Closing.")
            await self.close(code=4003) # Policy Violation (Auth Failure)
            return

        # Accept the WebSocket connection ONLY after successful authentication
        await self.accept()
        print(f"Voice WebSocket connection accepted for user: {self.user.username} (ID: {self.user.id})")


        try:
            # Load or create the OpenAI Assistant thread for this user
            print("Voice WebSocket: Loading or creating OpenAI thread...")
            # Assuming chatbot_logic.load_or_create_openai_thread_async is async and doesn't require flow_slug from here
            self.thread_id = await chatbot_logic.load_or_create_openai_thread_async(self.user)
            print(f"Voice WebSocket: Associated user {self.user.username} with thread ID: {self.thread_id}")

            # STT is handled by the frontend, no backend STT task to start here.

            # Send a control message to the frontend indicating readiness
            await self.send(text_data=json.dumps({
                'type': 'status',
                'message': 'ready',
                'detail': 'Backend connected and ready for voice input.' # Adjusted detail message
            }))
            print("Voice WebSocket: Sent 'ready' status to frontend.")

        except Exception as e:
            print(f"Voice WebSocket: Exception during connection setup for user {self.user.username}: {e}")
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Backend connection setup failed',
                'detail': str(e)
            }))
            await self.close(code=4000) # Generic Application Error

        print("VoiceChatConsumer: connect completed.")

    async def disconnect(self, close_code):
        """Handles WebSocket disconnection."""
        print(f"Voice WebSocket disconnected ({close_code}) for user: {self.user.username if self.user and not self.user.is_anonymous else 'Anonymous'})")
        # No backend STT tasks or queues to clean up here.
        print("Voice WebSocket: Disconnect cleanup finished.")

    # --- Receiving Messages from Frontend ---

    async def receive(self, text_data=None, bytes_data=None):
        """Receives messages from the frontend WebSocket."""
        # Based on the new frontend, we expect JSON text messages with transcribed text.
        # Raw audio (bytes_data) is NOT expected from this frontend.

        if text_data:
            try:
                message = json.loads(text_data)
                print(f"Receive: Received text message: {message}")

                # Expected format from new frontend: { text: "...", session_id: "..." }
                user_text = message.get('text')
                # REMOVED: flow_slug = message.get('flow_slug')
                session_id = message.get('session_id') # Session ID for this utterance stream

                if user_text is not None and session_id is not None:
                    print(f"Receive: Processing user text: '{user_text}' with session ID: {session_id}")
                    # Process the user's text input in a separate handler
                    await self.handle_user_text(user_text, session_id)

                elif message.get('type') == 'stop_recording':
                    # Frontend signals end of user's speech. Acknowledge if needed.
                    print("Receive: Frontend sent 'stop_recording' message.")
                    pass

                else:
                    print(f"Receive: Received unknown or incomplete text message format: {message}")
                    await self.send(text_data=json.dumps({
                        'type': 'error',
                        'message': 'Unknown or incomplete text message',
                        'detail': 'Expected {"text": "...", "session_id": "..."}, or {"type": "stop_recording"}'
                    }))

            except json.JSONDecodeError:
                print(f"Receive: Received invalid JSON text message: {text_data}")
                await self.send(text_data=json.dumps({
                    'type': 'error',
                    'message': 'Invalid text message format'
                }))
            except Exception as e:
                print(f"Receive: Error processing text message: {e}")
                await self.send(text_data=json.dumps({
                    'type': 'error',
                    'message': 'Error handling text command',
                    'detail': f'Error handling text command: {str(e)}'
                }))
        elif bytes_data:
            # This frontend should not send binary audio data for STT.
            print(f"Receive: WARNING: Received unexpected {len(bytes_data)} bytes_data.")
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Unexpected binary data received',
                'detail': 'This endpoint expects only text messages from the current frontend.'
            }))
        else:
            print("Receive: Received empty message.")

    # --- Handler for User Text Input ---

    async def handle_user_text(self, user_text, session_id):
        """Processes transcribed user text, interacts with chatbot, and handles TTS."""
        print(f"handle_user_text: Processing text: '{user_text}' for session ID: {session_id}, user: {self.user.username}")

        if not user_text or not user_text.strip():
            print("handle_user_text: Received empty or whitespace text, skipping processing.")
            return

        try:
            # Send a status message indicating processing
            await self.send(text_data=json.dumps({
                'type': 'status',
                'message': 'processing',
                'detail': 'Processing your text request...'
            }))
            print("handle_user_text: Sent 'processing' status.")

            # Call your chatbot logic function (assuming it's async)
            print("handle_user_text: Calling chatbot_logic.process_voice_transcript...")
            # Ensure your chatbot_logic.process_voice_transcript function does NOT require flow_slug if it's removed
            response_data = await chatbot_logic.process_voice_transcript(
                user=self.user,
                user_message=user_text,
                thread_id=self.thread_id
                # REMOVED: , flow_slug=self.flow_slug # Argument should be removed if chatbot_logic doesn't use it
            )
            chatbot_text_response = response_data.get("response", "").strip()
            suggested_products = response_data.get("suggested_products", [])

            print(f"handle_user_text: Chatbot returned text response: '{chatbot_text_response}'")

            # --- Send Bot's Text Response and Suggestions to Frontend ---
            # This message updates the log on the frontend.
            await self.send(text_data=json.dumps({
                'type': 'bot_response',
                'user_text': user_text, # Include the user's transcribed text
                'text': chatbot_text_response, # The bot's text response
                'suggested_products': suggested_products
            }))
            print("handle_user_text: Sent text response and suggestions to frontend.")

            # --- Handle TTS if there is text to speak ---
            if chatbot_text_response:
                await self.send(text_data=json.dumps({
                    'type': 'status',
                    'message': 'speaking',
                    'detail': 'Synthesizing response audio...'
                }))
                print("handle_user_text: Sent 'speaking' status.")

                # Call your TTS service (assuming google_cloud_voice.synthesize_text is async
                # and returns audio bytes AND mime type).
                print("handle_user_text: Calling google_cloud_voice.synthesize_text()...")
                audio_bytes, audio_mime_type = await google_cloud_voice.synthesize_text(chatbot_text_response)

                if audio_bytes:
                    print(f"handle_user_text: Received {len(audio_bytes)} bytes of synthesized audio with MIME type {audio_mime_type}.")

                    # --- Chunk and Send Audio as Base64 via WebSocket ---
                    # Send as one chunk matching the original example is simplest here.
                    # If you need smaller chunks, implement the loop from your old consumer.

                    encoded_audio = base64.b64encode(audio_bytes).decode('utf-8')

                    message = {
                         'event': 'tts_chunk', # Match frontend expectation for audio playback
                         'session_id': session_id, # Use the session ID from the incoming message
                         'payload': encoded_audio, # Base64 encoded audio
                         'mime': audio_mime_type # Audio MIME type from your TTS service
                     }
                    # Send the audio chunk
                    print(f"handle_user_text: Sending audio chunk ({len(encoded_audio)} base64 bytes).")
                    await self.send(text_data=json.dumps(message))
                    print("handle_user_text: Finished sending audio chunk.")

                    # Frontend's audio playback 'onended' handles the transition back to 'ready'.
                    # No final status needed from backend unless TTS failed.

                else:
                    print("handle_user_text: TTS returned no audio bytes.")
                    # Send 'ready' status if TTS failed
                    await self.send(text_data=json.dumps({
                         'type': 'status',
                         'message': 'ready',
                         'detail': 'Bot responded, but audio synthesis failed.'
                    }))
                    print("handle_user_text: Sent 'ready' status after TTS failure.")

            else:
                 print("handle_user_text: Chatbot returned empty text response.")
                 await self.send(text_data=json.dumps({
                      'type': 'status',
                      'message': 'ready',
                      'detail': 'Bot returned empty text response.'
                 }))
                 print("handle_user_text: Sent 'ready' status after empty chatbot response.")

        except Exception as e:
            print(f"handle_user_text: Error during processing text or TTS: {e}")
            # Send error status
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Backend processing error',
                'detail': str(e)
            }))
            print("handle_user_text: Sent backend processing error to frontend.")
            # Send 'ready' status after error
            await self.send(text_data=json.dumps({
                'type': 'status',
                'message': 'ready',
                'detail': 'An error occurred during processing.'
            }))
            print("handle_user_text: Sent 'ready' status after error.")