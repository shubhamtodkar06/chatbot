# chat/consumers.py
import json
import os
import asyncio
# Remove numpy and scipy imports as resampling is removed
# import numpy as np
# from scipy.signal import resample as scipy_resample

from google.cloud import speech # Assuming this is google-cloud-speech
from channels.generic.websocket import AsyncWebsocketConsumer
# Import the Google Cloud service module (adjust import path if necessary)
# Make sure this import path is correct relative to your Django app structure
from .services import google_cloud_voice
# Import the refactored chatbot logic module (adjust import path if necessary)
from . import chatbot_logic
# Import Django's User model to verify user
from django.contrib.auth import get_user_model

# *** FIX: Import sync_to_async ***
from asgiref.sync import sync_to_async # <--- ADD THIS IMPORT

User = get_user_model()  # Get the active User model

# --- UNIQUE PRINT STATEMENT TO VERIFY CONSUMER LOADING ---
print("--- Loading chat/consumers.py (Version 6 - Function Name Fix) ---")
# -----------------------------------------------------------------------


# Helper function for async iterators (used by anext)
# This might be needed if not using Python 3.10+ or if asyncio isn't patching builtins
async def anext(async_iterator):
    return await async_iterator.__anext__()


class VoiceChatConsumer(AsyncWebsocketConsumer):
    # --- Initialization and State ---

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # asyncio.Queue is thread-safe and suitable for passing data between sync/async parts
        self.audio_queue = asyncio.Queue()  # Queue to hold incoming audio chunks (expecting 16kHz)
        self.stt_task = None  # asyncio task for the STT streaming handler
        self.thread_id = None  # OpenAI Assistant Thread ID for this connection
        self.user = None  # Will hold the authenticated Django User instance

        # State for managing the STT stream life cycle
        self._audio_stream_ended = False

        print("VoiceChatConsumer: __init__ completed.") # Keep this log


    # --- Connection Handling ---

    async def connect(self):
        # This relies on AuthMiddlewareStack being configured in asgi.py
        # to populate self.scope['user'] based on the token in the URL.
        self.user = self.scope["user"]
        print(f"Voice WebSocket: Attempting connection for user: {self.user.username if self.user and not self.user.is_anonymous else 'Anonymous'})") # Keep this log

        if self.user.is_anonymous:
            print("Voice WebSocket: Anonymous user attempted connection. Closing.") # Keep this log
            # 4003 is a standard close code for "Policy Violation" (often used for auth failure)
            await self.close(code=4003)
            return

        # Accept the WebSocket connection ONLY after successful authentication
        await self.accept()
        print(f"Voice WebSocket connection accepted for user: {self.user.username} (ID: {self.user.id})") # Keep this log

        try:
            # Load or create the OpenAI Assistant thread for this user
            # This function is now async, so await it directly
            print("Voice WebSocket: Loading or creating OpenAI thread...") # Keep this log
            # *** FIX: Call the async function directly ***
            self.thread_id = await chatbot_logic.load_or_create_openai_thread_async(self.user)
            print(f"Voice WebSocket: Associated user {self.user.username} with thread ID: {self.thread_id}") # Keep this log

            # Start the background task that handles the STT stream and chatbot interaction.
            # This task will now run continuously for the connection's life.
            print("Voice WebSocket: Creating STT stream handler task...") # Keep this log
            self.stt_task = asyncio.create_task(self.handle_stt_stream())
            print("Voice WebSocket: STT stream handler task created.") # Keep this log

            # Send a control message to the frontend indicating readiness
            await self.send(text_data=json.dumps({
                'type': 'status',
                'message': 'ready',
                'detail': 'Backend ready for voice input.'
            }))
            print("Voice WebSocket: Sent 'ready' status to frontend.") # Keep this log

        except Exception as e:
            print(f"Voice WebSocket: Exception during connection setup for user {self.user.username}: {e}") # Keep this log
            # Send an error message to the frontend
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Backend connection setup failed',
                'detail': str(e)
            }))
            print("Voice WebSocket: Sent setup failed error to frontend.") # Keep this log
            # Close the connection
            await self.close(code=4000) # 4000 is a generic "Application Error" close code

        print("VoiceChatConsumer: connect completed.") # Keep this log


    async def disconnect(self, close_code):
        print(f"Voice WebSocket disconnected ({close_code}) for user: {self.user.username if self.user and not self.user.is_anonymous else 'Anonymous'})") # Keep this log

        # Signal the audio stream generator to stop gracefully
        # Putting None into the queue is the way to signal the audio_stream_generator to exit its loop.
        print("Voice WebSocket: Signaling audio stream end to queue...") # Keep this log
        try:
            # Using put_nowait might raise QueueFull, wait_for helps handle that
            await asyncio.wait_for(self.audio_queue.put(None), timeout=0.5)
            self._audio_stream_ended = True # Update state
            print("Voice WebSocket: Signaled audio stream end to queue.") # Keep this log
        except asyncio.TimeoutError:
            print("Voice WebSocket: Timed out putting None into audio queue during disconnect.") # Keep this log
        except Exception as e:
            print(f"Voice WebSocket: Error signaling audio queue end during disconnect: {e}") # Keep this log


        # Cancel the STT background task
        # This task runs the Google Cloud streaming logic and processes results.
        if self.stt_task and not self.stt_task.done():
            print("Voice WebSocket: Cancelling STT task.") # Keep this log
            self.stt_task.cancel() # Request the task to cancel
            try:
                # Wait briefly for the task to acknowledge cancellation and finish cleanup
                await asyncio.wait_for(self.stt_task, timeout=2.0)
                print("Voice WebSocket: STT task cancelled successfully.") # Keep this log
            except asyncio.CancelledError:
                 # This is the expected exception when a task is cancelled
                 print("Voice WebSocket: STT task acknowledged cancellation.") # Keep this log
            except asyncio.TimeoutError:
                 print("Voice WebSocket: STT task cancellation wait timed out.") # Keep this log
            except Exception as e:
                 print(f"Voice WebSocket: Error waiting for STT task cancellation: {e}") # Keep this log
        elif self.stt_task and self.stt_task.done():
            print("Voice WebSocket: STT task was already done.") # Keep this log


        # Clean up audio queue (optional, mostly for good measure after signalling None)
        # The generator marks tasks as done, but this ensures it's empty.
        print("Voice WebSocket: Clearing audio queue...") # Keep this log
        while not self.audio_queue.empty():
            try:
                self.audio_queue.get_nowait()
                self.audio_queue.task_done() # Mark as done if retrieved
            except asyncio.QueueEmpty:
                break
        print("Voice WebSocket: Audio queue cleared.") # Keep this log

        # Perform any other necessary cleanup
        print("Voice WebSocket: Disconnect cleanup finished.") # Keep this log


    # --- Receiving Messages from Frontend ---

    async def receive(self, text_data=None, bytes_data=None):
        # This method receives messages from the frontend WebSocket.
        # We expect either binary audio data (16kHz) or JSON text control messages.

        if bytes_data:
            # Received binary audio data chunk (EXPECTING 16kHz from frontend's AudioContext/Worklet)
            print(f"Receive: Received {len(bytes_data)} bytes of audio data (expecting 16kHz).") # Keep this log

            # Put the audio chunk into the queue for the STT task to consume.
            # Only put if the STT stream hasn't been signaled to end for the session.
            if not self._audio_stream_ended:
                 try:
                     # put_nowait is non-blocking, suitable for async receive.
                     self.audio_queue.put_nowait(bytes_data)
                     print(f"Receive: Successfully put {len(bytes_data)} bytes in queue.") # Keep this log

                 except asyncio.QueueFull:
                     print("Receive: WARNING: Audio queue is full, dropping audio chunk.") # Keep this log
                     # Optionally send a warning to the frontend
                     # await self.send(text_data=json.dumps({
                     #     'type': 'warning',
                     #     'message': 'Audio buffer overloaded',
                     #     'detail': 'Sending audio too fast or backend processing is slow.'
                     # }))
                 except Exception as e:
                     print(f"Receive: Error putting audio in queue: {e}") # Keep this log
                     # Send an error to the frontend
                     await self.send(text_data=json.dumps({
                         'type': 'error',
                         'message': 'Backend audio processing error',
                         'detail': f'Error queuing audio: {str(e)}'
                     }))


        elif text_data:
            # Received text data - likely a control message
            try:
                message = json.loads(text_data)
                print(f"Receive: Received text message: {message}") # Keep this log

                # --- Handle specific control message types ---
                message_type = message.get('type')

                if message_type == 'stop_recording':
                    # This signal indicates the end of a user's utterance/speaking turn.
                    # For a continuous STT stream, this doesn't necessarily mean
                    # stopping the Google Cloud client entirely, but might
                    # signal the backend to process the current buffered audio
                    # or aid in utterance boundary detection if relying on backend VAD.
                    # In this continuous model, receiving 'stop_recording' after
                    # the STT task has processed initial chunks is expected behavior
                    # for signalling utterance end.
                    print("Receive: Frontend requested stop recording (end of user utterance).") # Keep this log

                    # If you were implementing backend VAD, you might process the last
                    # buffered audio here. With Google Cloud's stream, it often handles
                    # utterance detection based on pauses, but the explicit frontend
                    # stop signal can be a reliable trigger.

                    # Note: We do NOT put 'None' into the queue here for a continuous stream,
                    # as 'None' signals the END of the ENTIRE stream for the connection.
                    pass # Just acknowledge the message for now

                # Add other control messages as needed (e.g., 'settings', 'cancel_utterance')

            except json.JSONDecodeError:
                print(f"Receive: Received invalid JSON text message: {text_data}") # Keep this log
                await self.send(text_data=json.dumps({
                    'type': 'error',
                    'message': 'Invalid text message format'
                }))
            except Exception as e:
                print(f"Receive: Error processing text message: {e}") # Keep this log
                await self.send(text_data=json.dumps({
                    'type': 'error',
                    'message': 'Error handling text command',
                    'detail': f'Error handling text command: {str(e)}'
                }))
        else:
            print("Receive: Received empty message.") # Keep this log


    # --- Background Task Components ---

    async def audio_stream_generator(self):
        # This async generator continuously yields audio chunks from the queue.
        # It serves as the input source for the Google Cloud STT streaming client.
        print("Audio stream generator started.") # Keep this log
        while True:
            try:
                # Wait for the next audio chunk or the stop signal (None).
                # This will block until data is available or None is put.
                chunk = await self.audio_queue.get()
                print(f"Generator: Got item from queue (size: {len(chunk) if chunk is not None else 'None'}).") # Keep this log

                if chunk is None: # Check for the signal to stop the ENTIRE stream (e.g., on disconnect)
                    print("Audio stream generator: Received stop signal (None). Exiting loop.") # Keep this log
                    break # Exit the generator loop, ending the input to the Google Cloud STT stream

                yield chunk # Yield the audio chunk to the Google Cloud client

                # Mark the task as done for the item retrieved from the queue
                self.audio_queue.task_done() # This is good practice


            except asyncio.CancelledError:
                print("Audio stream generator: Task cancelled.") # Keep this log
                break # Exit the generator loop if the task is cancelled
            except Exception as e:
                print(f"Audio stream generator error: {e}") # Keep this log
                # Depending on desired error handling, you might break or propagate
                break # Exit on other exceptions

        print("Audio stream generator finished.") # Keep this log


    async def handle_stt_stream(self):
        """
        Handles the continuous streaming interaction with Google Cloud STT
        for back-and-forth conversation within the same connection.
        This task runs for the life of the WebSocket connection.
        """
        print("STT stream handler task started for live conversation.") # Keep this log

        # Define the streaming configuration for Google Cloud STT.
        # This needs to be consistent with the audio format from the frontend (16kHz, LINEAR16).
        streaming_config = speech.StreamingRecognitionConfig(
            config=speech.RecognitionConfig(
                encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16, # Ensure this matches frontend output
                sample_rate_hertz=16000, # Ensure this matches frontend sample rate
                language_code="en-US",
                # Add other recognition features if needed, e.g.:
                # enable_automatic_punctuation=True, # Consider enabling punctuation
                # model="default", # "video", "phone_call", "command_and_search"
            ),
            interim_results=True, # Keep interim results if you want to display them in the UI
            # For continuous back-and-forth, set single_utterance to False.
            # If single_utterance=True, the stream might close automatically after a pause.
            single_utterance=False,
        )

        # Define an async generator that yields requests for the Google Cloud streaming API.
        # The first request must contain the configuration, subsequent requests contain audio content.
        async def audio_requests_iterator():
            print("GC_STT: Audio requests iterator started.") # Keep this log
            # The very first request sent to the API must be the config
            yield speech.StreamingRecognizeRequest(streaming_config=streaming_config)
            print("GC_STT: Sent initial request with config (16kHz).") # Keep this log

            # Now, continuously yield audio chunks received from the audio_queue
            # The audio_stream_generator feeds this iterator.
            # This loop will run as long as the audio_stream_generator yields data (until it yields None).
            async for chunk in self.audio_stream_generator():
                # The audio_stream_generator handles waiting for chunks and the 'None' signal.
                # When the audio_stream_generator yields None, the async for loop here will naturally break,
                # signaling the end of input to the Google Cloud client.
                # print(f"GC_STT: Audio requests iterator yielding chunk ({len(chunk)} bytes).") # Keep noisy logs commented
                yield speech.StreamingRecognizeRequest(audio_content=chunk) # Subsequent requests only contain audio_content

            print("GC_STT: Audio requests iterator finished.") # Keep this log


        # --- Main loop to run the Google Cloud STT stream and process results ---
        # This loop runs as long as the Google Cloud stream is active and yielding responses.
        final_transcript_parts = [] # Buffer to collect final transcript parts for one utterance

        print("STT stream handler: Preparing to call google_cloud_voice.stream_transcribe_async()...") # Keep this log

        try:
            requests_iterator = audio_requests_iterator()

            print("STT stream handler: Calling google_cloud_voice.stream_transcribe_async()...") # Keep this log

            # This is the critical loop that interacts with the Google Cloud API.
            # Iterate over the results yielded by stream_transcribe_async.
            # Assuming google_cloud_voice.stream_transcribe_async is a wrapper
            # around the Google Cloud client's stream API that yields results.
            # Let's assume it yields speech.StreamingRecognizeResponse objects or similar structures
            # that contain a list of results (res.results).

            # Note: The exact structure of the 'result' yielded by stream_transcribe_async
            # depends on its implementation. Assuming it yields objects where result.results
            # is a list of StreamingRecognitionResult objects.
            async for transcript, is_final in google_cloud_voice.stream_transcribe_async(requests_iterator): # Expecting tuple (transcript, is_final) based on google_cloud_voice.py yield

                # Process the results yielded by our google_cloud_voice function
                # The google_cloud_voice.stream_transcribe_async generator yields (transcript, is_final)
                print(f"STT stream handler: Received yielded result: Transcript='{transcript}', IsFinal={is_final}") # Keep this log

                if is_final:
                    print(f"STT stream handler: Received Final Transcript: '{transcript}'") # Keep this log

                    # --- Trigger processing of the final transcript ---
                    # Put the processing into a separate task so the STT result
                    # processing loop can continue without blocking.
                    if transcript.strip(): # Only process if there is actual text
                        print("STT stream handler: Triggering process_final_transcript task.") # Keep this log
                        # This will create a new asyncio task to run process_final_transcript
                        # This allows handle_stt_stream to keep processing incoming STT results
                        # while process_final_transcript is interacting with the chatbot/TTS.
                        asyncio.create_task(self.process_final_transcript(transcript))

                    # No need to manage final_transcript_parts buffer with the current yield structure


                else:
                    # Interim result - optionally send to frontend
                    interim_transcript = transcript # The yielded transcript is already interim
                    print(f"STT stream handler: Received Interim Transcript: '{interim_transcript}'") # Keep this log
                    # await self.send(text_data=json.dumps({'type': 'transcript_interim', 'transcript': interim_transcript})) # Uncomment to send interim results


            # The async for loop above finishes when the audio_requests_iterator stops yielding
            # (i.e., when None is received from the audio_queue, typically on disconnect).
            print("STT stream handler: google_cloud_voice.stream_transcribe_async loop finished.") # Keep this log

            # --- This code runs AFTER the async for loop finishes ---
            # Any final cleanup after the entire stream ends would go here.
            print("STT stream handler: Stream processing ended.") # Keep this log


        except asyncio.CancelledError:
            print("STT stream handler task cancelled gracefully.") # Keep this log
            # Perform any necessary cleanup if the task is cancelled unexpectedly
            # Ensure any ongoing Google Cloud operations are cancelled gracefully
            # If you have a Google Cloud client instance, you might need to close it here.
            # if google_cloud_client:
            #      await google_cloud_client.close() # Assuming client has an async close method
        except Exception as e:
            print(f"STT stream handler: Error during STT stream processing: {e}") # Keep this log
            await self.send(text_data=json.dumps({'type': 'error', 'message': f'Backend STT Stream Error: {e}', 'detail': str(e)}))
        finally:
            print("STT stream handler task finishing.") # Keep this log
            # Ensure the audio queue is signaled as finished if not already (important for cleanup)
            # This should be handled by the iterator's break and setting _audio_stream_ended
            # if not self._audio_stream_ended:
            #      try:
            #           self.audio_queue.put_nowait(None)
            #           self._audio_stream_ended = True
            #           print("STT stream handler task finishing: Signaled queue end.")
            #      except asyncio.QueueFull:
            #          print("STT stream handler task finishing: Queue full when signaling end.")
            #      except Exception as e:
            #          print(f"STT stream handler task finishing: Error signaling queue end: {e}")

            print("STT stream handler task finished.") # Keep this log


    # --- Keep your existing process_final_transcript method as is ---
    # This method processes the final transcript and interacts with the chatbot logic and TTS.
    async def process_final_transcript(self, transcript):
        """Processes a final transcript received from the STT stream."""
        print(f"Processing final transcript: '{transcript}' for user {self.user.username}") # Keep this log

        if not transcript or not transcript.strip():
             print("process_final_transcript: Received empty or whitespace transcript, skipping processing.") # Keep this log
             # Optionally send a status to the frontend
             # await self.send(text_data=json.dumps({'type': 'status', 'message': 'No speech detected.', 'detail': 'Transcript was empty.'}))
             return


        try:
            # Send a status message indicating processing
            await self.send(text_data=json.dumps({
                'type': 'status',
                'message': 'processing',
                'detail': 'Processing your request...'
            }))
            print("process_final_transcript: Sent 'processing' status.") # Keep this log


            # Call your refactored chatbot logic function
            # This function is async and handles OpenAI interaction and DB saving
            # Assumes chatbot_logic.process_voice_transcript returns {"response": "...", "suggested_products": [...]}
            print("process_final_transcript: Calling chatbot_logic.process_voice_transcript...") # Keep this log
            # *** FIX: Call the async function directly without sync_to_async ***
            response_data = await chatbot_logic.process_voice_transcript(
                user=self.user,
                user_message=transcript, # Pass the user's transcribed text
                thread_id=self.thread_id # Pass the thread ID
            )
            chatbot_text_response = response_data.get("response", "").strip()
            suggested_products = response_data.get("suggested_products", []) # Get suggestions


            print(f"process_final_transcript: Chatbot returned text response: '{chatbot_text_response}'") # Keep this log

            # Send the chatbot's text response and suggestions back to the frontend
            # It's generally good to send the user's transcribed text back too for display.
            await self.send(text_data=json.dumps({
                'type': 'bot_response', # Use 'bot_response' type as expected by frontend
                'user_text': transcript, # Include the user's transcribed text
                'text': chatbot_text_response, # The bot's text response
                'suggested_products': suggested_products # Include suggestions
            }))
            print("process_final_transcript: Sent text response and suggestions to frontend.") # Keep this log


            # Send a status message indicating synthesis and speaking (if TTS is successful)
            if chatbot_text_response: # Only synthesize if there's text to speak
                await self.send(text_data=json.dumps({
                    'type': 'status',
                    'message': 'speaking',
                    'detail': 'Synthesizing response...'
                }))
                print("process_final_transcript: Sent 'speaking' status.") # Keep this log

                # Send the text response to Google Cloud Text-to-Speech
                print("process_final_transcript: Calling google_cloud_voice.synthesize_text()...") # Keep this log
                audio_bytes = await google_cloud_voice.synthesize_text(chatbot_text_response)

                if audio_bytes:
                    print(f"process_final_transcript: Sending {len(audio_bytes)} bytes of synthesized audio to frontend.") # Keep this log
                    # Send the synthesized audio data back to the frontend over the WebSocket
                    # The frontend will need to play this binary data.
                    await self.send(bytes_data=audio_bytes)

                    # After sending audio, frontend's audio playback 'onended' should trigger UI reset.
                    # No need to send 'ready' status from backend here if audio is sent.
                    # await self.send(text_data=json.dumps({
                    #      'type': 'status',
                    #      'message': 'ready',
                    #      'detail': 'Ready for next input.'
                    # }))
                    # print("process_final_transcript: Sent 'ready' status after sending audio.")


                else:
                    # Handle cases where TTS returned no audio (e.g., empty response)
                    print("process_final_transcript: TTS returned no audio bytes for a non-empty text response.") # Keep this log
                    # If TTS fails, signal backend is ready for next input immediately
                    await self.send(text_data=json.dumps({
                         'type': 'status',
                         'message': 'ready',
                         'detail': 'Bot returned empty text response, or TTS failed.'
                    }))
                    print("process_final_transcript: Sent 'ready' status after empty TTS response or TTS failed.") # Keep this log

            else:
                 # If chatbot text response was empty, signal backend is ready immediately
                 print("process_final_transcript: Chatbot returned empty text response.") # Keep this log
                 await self.send(text_data=json.dumps({
                     'type': 'status',
                     'message': 'ready',
                     'detail': 'Bot returned empty text response.'
                 }))
                 print("process_final_transcript: Sent 'ready' status after empty chatbot response.") # Keep this log


        except Exception as e:
            print(f"process_final_transcript: Error during processing final transcript or TTS: {e}") # Keep this log
            # Send error message to frontend
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Backend processing error',
                'detail': f'Processing/TTS failed: {str(e)}'
            }))
            print("process_final_transcript: Sent backend processing error to frontend.") # Keep this log
            # After an error, indicate readiness for next input
            await self.send(text_data=json.dumps({
                'type': 'status',
                'message': 'ready',
                'detail': 'An error occurred during processing.'
            }))
            print("process_final_transcript: Sent 'ready' status after error.") # Keep this log
            # Consider closing the connection on persistent errors: await self.close()
