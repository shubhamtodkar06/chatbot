# chat/consumers.py
import json
import os
import asyncio
import numpy as np  # Import numpy
from scipy.signal import resample as scipy_resample  # Import scipy's resample function
from google.cloud import speech
from channels.generic.websocket import AsyncWebsocketConsumer
# Import the Google Cloud service module
from .services import google_cloud_voice
# Import the refactored chatbot logic module
from . import chatbot_logic
# Import Django's User model to verify user
from django.contrib.auth import get_user_model

User = get_user_model()  # Get the active User model


# --- Define resampling function ---
def resample_audio(audio_bytes_48khz, original_sample_rate, target_sample_rate):
    """
    Resamples raw 16-bit PCM mono audio bytes from original_sample_rate to target_sample_rate.
    Uses numpy and scipy.signal.resample.
    """

    # Convert bytes to numpy array (assuming little-endian, 16-bit signed integers)
    # The frontend sends Int16Array buffer, which is 16-bit signed.
    audio_array_48khz = np.frombuffer(audio_bytes_48khz, dtype=np.int16)


    # Normalize to float range [-1, 1] for resampling
    audio_array_48khz_float = audio_array_48khz.astype(np.float32) / 32768.0  # Use float32 and divide by max int value

    # Calculate the number of samples after resampling
    num_samples_48khz = len(audio_array_48khz_float)
    num_samples_16khz = int(num_samples_48khz * target_sample_rate / original_sample_rate)


    # Perform resampling using scipy.signal.resample
    try:
        audio_array_16khz_float = scipy_resample(audio_array_48khz_float, num_samples_16khz)
    except Exception as e:
        print(f"Resampling Error: SciPy resampling failed - {e}")
        # Return empty bytes or raise an exception depending on desired error handling
        return b''


    # Denormalize back to 16-bit signed integers
    # Ensure clipping to avoid exceeding Int16 range after resampling artifacts
    audio_array_16khz = (audio_array_16khz_float * 32768.0).astype(np.int16)
    # Use 32768 for [-1, 1] range for signed 16-bit, scipy resample can sometimes go slightly outside -1,1
    audio_array_16khz = np.clip(audio_array_16khz, -32768, 32767) # Ensure data is within Int16 range


    # Convert numpy array back to bytes
    resampled_audio_bytes_16khz = audio_array_16khz.tobytes()

    return resampled_audio_bytes_16khz

class VoiceChatConsumer(AsyncWebsocketConsumer):
    # --- Initialization and State ---

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # asyncio.Queue is thread-safe and suitable for passing data between sync/async parts
        # and between different async tasks within the consumer.
        self.audio_queue = asyncio.Queue()  # Queue to hold incoming audio chunks from receive()
        self.stt_task = None  # asyncio task for the STT streaming handler
        self.thread_id = None  # OpenAI Assistant Thread ID for this connection
        self.user = None  # Will hold the authenticated Django User instance

        # State for managing the STT stream life cycle if needed
        self._audio_stream_ended = False

        # You might want a buffer to accumulate small chunks before resampling larger ones
        # for potentially better quality, but for simplicity, we resample chunk-by-chunk for now.
        # self._resample_buffer = b''


    # --- Connection Handling ---

    async def connect(self):
        # This relies on AuthMiddlewareStack being configured in asgi.py
        # to populate self.scope['user'] based on the token in the URL.
        self.user = self.scope["user"]
        print(f"Voice WebSocket: Attempting connection for user: {self.user.username if self.user and not self.user.is_anonymous else 'Anonymous'})")

        if self.user.is_anonymous:
            print("Voice WebSocket: Anonymous user attempted connection. Closing.")
            # 4003 is a standard close code for "Policy Violation" (often used for auth failure)
            await self.close(code=4003)
            return

        # Accept the WebSocket connection ONLY after successful authentication
        await self.accept()
        print(f"Voice WebSocket connection accepted for user: {self.user.username} (ID: {self.user.id})")


        try:
            # Load or create the OpenAI Assistant thread for this user
            self.thread_id = await chatbot_logic.load_or_create_openai_thread_async(self.user)
            print(f"Voice WebSocket: Associated user {self.user.username} with thread ID: {self.thread_id}")

            # Start the background task that handles the STT stream and chatbot interaction.
            self.stt_task = asyncio.create_task(self.handle_stt_stream())
            print("Voice WebSocket: STT stream handler task created.")

            # Send a control message to the frontend indicating readiness
            await self.send(text_data=json.dumps({
                'type': 'status',
                'message': 'ready',
                'detail': 'Backend ready for voice input.'
            }))
            print("Voice WebSocket: Sent 'ready' status to frontend.")


        except Exception as e:
            print(f"Voice WebSocket: Exception during connection setup for user {self.user.username}: {e}")
            # Send an error message to the frontend
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Backend connection setup failed',
                'detail': str(e)
            }))
            print("Voice WebSocket: Sent setup failed error to frontend.")
            # Close the connection
            await self.close(code=4000) # 4000 is a generic "Application Error" close code

    async def disconnect(self, close_code):
        print(f"Voice WebSocket disconnected ({close_code}) for user: {self.user.username if self.user and not self.user.is_anonymous else 'Anonymous'})")

        # Signal the audio stream generator to stop gracefully
        # Put None even if _audio_stream_ended is already True, in case the generator is still waiting
        try:
            await asyncio.wait_for(self.audio_queue.put(None), timeout=0.5)
            self._audio_stream_ended = True # Update state
            print("Voice WebSocket: Signaled audio stream end to queue.")
        except asyncio.TimeoutError:
            print("Voice WebSocket: Timed out putting None into audio queue during disconnect.")
        except Exception as e:
            print(f"Voice WebSocket: Error signaling audio queue end during disconnect: {e}")


        # Cancel the STT background task
        if self.stt_task and not self.stt_task.done():
            print("Voice WebSocket: Cancelling STT task.")
            self.stt_task.cancel()
            try:
                # Wait briefly for the task to acknowledge cancellation and finish cleanup
                await asyncio.wait_for(self.stt_task, timeout=2.0)
                print("Voice WebSocket: STT task cancelled successfully.")
            except asyncio.CancelledError:
                 # This is the expected exception when a task is cancelled
                 print("Voice WebSocket: STT task acknowledged cancellation.")
            except asyncio.TimeoutError:
                 print("Voice WebSocket: STT task cancellation wait timed out.")
            except Exception as e:
                 print(f"Voice WebSocket: Error waiting for STT task cancellation: {e}")
        elif self.stt_task and self.stt_task.done():
            print("Voice WebSocket: STT task was already done.")


        # Clean up audio queue (optional, mostly for good measure after signalling None)
        while not self.audio_queue.empty():
            try:
                self.audio_queue.get_nowait()
                self.audio_queue.task_done() # Mark as done if retrieved
            except asyncio.QueueEmpty:
                break
        print("Voice WebSocket: Audio queue cleared.")

        # Perform any other necessary cleanup

    # --- Receiving Messages from Frontend ---

    async def receive(self, text_data=None, bytes_data=None):
        # This method receives messages from the frontend WebSocket.
        # We expect either binary audio data or JSON text control messages.

        if bytes_data:
            # Received binary audio data chunk (This is 48kHz from the frontend)

            if not self._audio_stream_ended: # Only process if we haven't sent the stop signal
                try:
                    # --- *** NEW RESAMPLING LOGIC *** ---
                    original_sample_rate = 48000
                    target_sample_rate = 16000

                    # Resample the 48kHz audio chunk to 16kHz
                    # Note: Processing chunk by chunk like this can sometimes
                    # introduce artifacts at chunk boundaries.
                    resampled_audio_16khz_bytes = resample_audio(
                        bytes_data, # Pass the raw 48kHz bytes
                        original_sample_rate,
                        target_sample_rate
                    )
                    # --- *** END RESAMPLING LOGIC *** ---

                    # Put the RESAMPLED audio chunk (now 16kHz) into the queue
                    if resampled_audio_16khz_bytes: # Only put if resampling returned data
                        self.audio_queue.put_nowait(resampled_audio_16khz_bytes)
                        # print(f"Receive: Put {len(resampled_audio_16khz_bytes)} bytes of 16kHz audio in queue.")
                    else:
                         print("Receive: Resampling returned empty bytes, skipping put_nowait.")


                except asyncio.QueueFull:
                    print("Receive: WARNING: Audio queue is full, dropping audio chunk.")
                    await self.send(text_data=json.dumps({
                         'type': 'warning',
                         'message': 'Audio buffer overloaded',
                         'detail': 'Sending audio too fast or backend processing is slow.'
                    }))
                except Exception as e:
                    print(f"Receive: Error during resampling or putting audio in queue: {e}")
                    # Send an error back to the frontend
                    await self.send(text_data=json.dumps({
                        'type': 'error',
                        'message': 'Backend audio processing error',
                        'detail': f'Resampling failed: {str(e)}'
                    }))
                    # Consider signaling the audio stream end or closing the connection
                    # await self.audio_queue.put(None)
                    # self._audio_stream_ended = True
                    # await self.close()


        elif text_data:
            # Received text data - likely a control message
            try:
                message = json.loads(text_data)
                print(f"Receive: Received text message: {message}")

                # --- Handle specific control message types ---
                message_type = message.get('type')

                if message_type == 'stop_recording':
                    print("Receive: Frontend requested stop recording (end of user utterance).")
                    # Signal the end of the audio stream for the current turn/utterance.
                    if not self._audio_stream_ended:
                         # Ensure any remaining data in a potential resample buffer is processed
                         # If you added buffering, process and put the final buffer here
                         # ... process and put self._resample_buffer if it exists ...

                         try:
                             await asyncio.wait_for(self.audio_queue.put(None), timeout=0.5)
                             self._audio_stream_ended = True
                             print("Receive: Sent stop signal (None) to audio stream generator.")
                         except asyncio.TimeoutError:
                             print("Receive: Timed out putting None into audio queue during stop_recording.")
                         except Exception as e:
                            print(f"Receive: Error signaling audio queue end during stop_recording: {e}")

                    else:
                         print("Receive: Received stop_recording but stream already signalled end.")

                # Add other control messages as needed (e.g., 'start_recording', 'settings', 'cancel')
                # If you implement 'start_recording' again for multi-turn, you'd need
                # to reset _audio_stream_ended = False and potentially restart the STT stream/task
                # or manage turns within the existing stream based on STT API capabilities.

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
                    'detail': str(e)
                }))
        else:
            print("Receive: Received empty message.")


    # --- Background Task Components ---

    async def audio_stream_generator(self):
        # This async generator continuously yields audio chunks from the queue
        # for the Google Cloud STT streaming client.
        print("Audio stream generator started.")
        while True:
            try:
                # Wait for the next audio chunk from the queue
                chunk = await self.audio_queue.get()
                # print(f"Generator: Got item from queue (size: {len(chunk) if chunk is not None else 'None'}).")

                if chunk is None: # Check for the signal to stop streaming
                    print("Audio stream generator: Received stop signal (None). Exiting loop.")
                    break # Exit the generator loop, ending the Google Cloud STT stream

                yield chunk

                # Mark the task as done for the item retrieved from the queue
                # This is good practice if you ever need to join the queue (e.g., queue.join())
                self.audio_queue.task_done()


            except asyncio.CancelledError:
                print("Audio stream generator: Task cancelled.")
                break # Exit the generator loop
            except Exception as e:
                print(f"Audio stream generator error: {e}")
                # Depending on how you want to handle errors, you might break or re-raise
                break

        print("Audio stream generator finished.")


# Inside your VoiceChatConsumer class in chat/consumers.py

    async def handle_stt_stream(self):
        """Handles the streaming interaction with Google Cloud STT."""
        print("STT stream handler task started.")
        final_transcript_parts = []
        google_cloud_client = None # Keep client reference for potential explicit close

        try:
            # --- Wait for the first audio chunk before starting Google STT ---
            print("STT stream handler: Waiting for first audio chunk from queue...")
            try:
                # anext() gets the next item from an async iterator.
                # self.audio_stream_generator() is an async iterator that yields
                # audio chunks or None when stop_recording is received.
                # Using await self.audio_stream_generator().__anext__() is also an option
                initial_chunk = await asyncio.wait_for(anext(self.audio_stream_generator()), timeout=10.0) # Add a timeout in case no audio ever comes
            except asyncio.TimeoutError:
                print("STT stream handler: Timeout waiting for initial audio chunk. User did not speak?")
                await self.send(text_data=json.dumps({'type': 'status', 'message': 'No audio received.', 'detail': 'Timeout waiting for speech.'}))
                return # Exit task if no audio within timeout
            except StopAsyncIteration:
                 print("STT stream handler: Generator stopped before first chunk.")
                 return # Exit task gracefully if generator is empty

            if initial_chunk is None:
                print("STT stream handler: Received None immediately for initial chunk, no audio.")
                await self.send(text_data=json.dumps({'type': 'status', 'message': 'No speech detected.', 'detail': 'No audio received.'}))
                return # Exit task if no audio received

            print(f"STT stream handler: Received first audio chunk ({len(initial_chunk)} bytes). Initiating Google Cloud STT stream...")

            # --- Define an async generator that yields the first chunk (with config)
            # and then subsequent chunks from the audio stream generator. ---
            async def audio_requests_iterator():
                print("GC_STT: Audio requests iterator started.")
                # The first request must contain the config AND the first audio content
                # Define config here or ensure it's accessible. Let's define it here for clarity.
                streaming_config = speech.StreamingRecognitionConfig(
                    config=speech.RecognitionConfig(
                        encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
                        sample_rate_hertz=16000,
                        language_code="en-US",
                    ),
                    interim_results=True, # Keep interim results if you want to display them
                )
                yield speech.StreamingRecognizeRequest(audio_content=initial_chunk, streaming_config=streaming_config)
                print("GC_STT: Sent initial request with config and first chunk.")

                # Now yield the rest of the audio chunks as they arrive
                async for chunk in self.audio_stream_generator():
                    if chunk is None:
                        print("GC_STT: Audio requests iterator received None, signaling end of audio.")
                        # When the audio_stream_generator yields None, the async for loop
                        # here will break, ending the iterator. This signals the end of
                        # input to the Google Cloud client library.
                        break
                    # print(f"GC_STT: Audio requests iterator yielding subsequent chunk ({len(chunk)} bytes).") # Too noisy
                    yield speech.StreamingRecognizeRequest(audio_content=chunk) # Subsequent requests only contain audio_content
                print("GC_STT: Audio requests iterator finished.")


            # --- Perform the streaming recognition using the iterator ---
            requests_iterator = audio_requests_iterator()

            # --- THIS IS THE CRITICAL CALL ---
            # Ensure you are calling the async function from google_cloud_voice
            # and iterating over its results using async for.
            
            streaming_config = speech.StreamingRecognitionConfig(
                config=speech.RecognitionConfig(
                    encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
                    sample_rate_hertz=16000,
                    language_code="en-US",
                ),
                interim_results=True,
            )

            print("STT stream handler: Calling google_cloud_voice.stream_transcribe_async()...") # ADD THIS LOG
            print(requests_iterator)
            print("hello world")
            async for transcript, is_final in google_cloud_voice.stream_transcribe_async(requests_iterator): # <--- VERIFY THIS LINE
                 # Process the transcript results yielded by stream_transcribe_async
                 if is_final:
                      print(f"STT stream handler: Received Final Transcript Part: '{transcript}'")
                      final_transcript_parts.append(transcript)
                 # else:
                      # print(f"STT stream handler: Received Interim Transcript: '{transcript}'")
                      # Optionally send interim results to frontend:
                      # await self.send(text_data=json.dumps({'type': 'transcript_interim', 'transcript': transcript}))


            print("STT stream handler: google_cloud_voice.stream_transcribe_async loop finished.") # ADD THIS LOG

            # --- This code runs AFTER the async for loop finishes ---
            # ... (rest of your logic to join final_transcript_parts,
            # call process_final_transcript, etc.) ...


        except asyncio.CancelledError:
            print("STT stream handler task cancelled.")
            # Clean up resources if the task is cancelled unexpectedly
        except Exception as e:
            print(f"STT stream handler: Error during STT process: {e}")
            # Send an error status to the frontend
            await self.send(text_data=json.dumps({'type': 'error', 'message': f'Backend STT Error: {e}', 'detail': str(e)}))
        finally:
            print("STT stream handler task finishing.")
            # ... (cleanup code) ...
            print("STT stream handler task finished.")

    # ... (your process_final_transcript method and other consumer methods) ...            
    async def process_final_transcript(self, transcript):
        # This method is called when a final transcript is received from STT.
        # It passes the text to the chatbot logic and handles the response.
        print(f"Processing final transcript: '{transcript}' for user {self.user.username}")

        try:
            # Send a status message indicating processing
            await self.send(text_data=json.dumps({
                 'type': 'status',
                 'message': 'processing',
                 'detail': 'Processing your request...'
             }))
            print("process_final_transcript: Sent 'processing' status.")


            # Call your refactored chatbot logic function
            # This function is async and handles OpenAI interaction and DB saving
            # Assumes chatbot_logic.process_voice_transcript returns {"response": "...", "suggested_products": [...]}
            response_data = await chatbot_logic.process_voice_transcript(
                user=self.user,
                user_message=transcript,
                thread_id=self.thread_id
            )
            chatbot_text_response = response_data.get("response", "").strip()
            # suggested_products = response_data.get("suggested_products", []) # Use if you want to send suggestions via WS

            print(f"process_final_transcript: Chatbot returned text response: '{chatbot_text_response}'")

            # Send a status message indicating synthesis and speaking
            await self.send(text_data=json.dumps({
                 'type': 'status',
                 'message': 'speaking',
                 'detail': 'Synthesizing response...'
             }))
            print("process_final_transcript: Sent 'speaking' status.")


            # Send the text response to Google Cloud Text-to-Speech
            audio_bytes = await google_cloud_voice.synthesize_text(chatbot_text_response)

            if audio_bytes:
                print(f"process_final_transcript: Sending {len(audio_bytes)} bytes of synthesized audio to frontend.")
                # Send the synthesized audio data back to the frontend over the WebSocket
                # The frontend will need to play this binary data.
                await self.send(bytes_data=audio_bytes)

                # After sending audio, send a status indicating backend is ready for next input
                await self.send(text_data=json.dumps({
                     'type': 'status',
                     'message': 'ready',
                     'detail': 'Ready for next input.'
                 }))
                print("process_final_transcript: Sent 'ready' status after sending audio.")


            else:
                # Handle cases where TTS returned no audio (e.g., empty response)
                print("process_final_transcript: TTS returned no audio bytes.")
                await self.send(text_data=json.dumps({
                     'type': 'status',
                     'message': 'ready', # Or a warning/error
                     'detail': 'Received empty response from bot.'
                 }))
                print("process_final_transcript: Sent 'ready' status after empty TTS response.")
                # Send the text response as a fallback if no audio
                if chatbot_text_response: # Only send text if there was a text response
                     await self.send(text_data=json.dumps({
                          'type': 'chatbot_response_text',
                          'response': chatbot_text_response,
                     }))
                     print("process_final_transcript: Sent text fallback response.")


            # Optional: Send suggestions or other data as separate messages if needed
            # await self.send(text_data=json.dumps({
            #     'type': 'suggestions',
            #     'suggestions': suggested_products
            # }))


        except Exception as e:
            print(f"process_final_transcript: Error during processing final transcript or TTS: {e}")
            # Send error message to frontend
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Backend processing error',
                'detail': f'Processing/TTS failed: {str(e)}'
            }))
            print("process_final_transcript: Sent backend processing error to frontend.")
            # After an error, indicate readiness for next input if possible
            await self.send(text_data=json.dumps({
                 'type': 'status',
                 'message': 'ready',
                 'detail': 'An error occurred during processing.'
             }))
            print("process_final_transcript: Sent 'ready' status after error.")
            # Consider closing the connection on persistent errors: await self.close()


# --- Add the helper resampling function outside the class ---
# You can put this function above or below the VoiceChatConsumer class definition.
# Make sure you have numpy and scipy installed (`pip install numpy scipy`)
def resample_audio(audio_bytes_48khz, original_sample_rate, target_sample_rate):
    """
    Resamples raw 16-bit PCM mono audio bytes from original_sample_rate to target_sample_rate.
    Uses numpy and scipy.signal.resample.
    """

    # Convert bytes to numpy array (assuming little-endian, 16-bit signed integers)
    # The frontend sends Int16Array buffer, which is 16-bit signed.
    audio_array_48khz = np.frombuffer(audio_bytes_48khz, dtype=np.int16)


    # Normalize to float range [-1, 1] for resampling
    audio_array_48khz_float = audio_array_48khz.astype(np.float32) / 32768.0  # Use float32 and divide by max int value

    # Calculate the number of samples after resampling
    num_samples_48khz = len(audio_array_48khz_float)
    num_samples_16khz = int(num_samples_48khz * target_sample_rate / original_sample_rate)


    # Perform resampling using scipy.signal.resample
    try:
        audio_array_16khz_float = scipy_resample(audio_array_48khz_float, num_samples_16khz)
    except Exception as e:
        # Return empty bytes or raise an exception depending on desired error handling
        return b'' # Return empty bytes on error

    # Denormalize back to 16-bit signed integers
    # Ensure clipping to avoid exceeding Int16 range after resampling artifacts
    audio_array_16khz = (audio_array_16khz_float * 32768.0).astype(np.int16)
    # Use 32768 for [-1, 1] range for signed 16-bit, scipy resample can sometimes go slightly outside -1,1
    audio_array_16khz = np.clip(audio_array_16khz, -32768, 32767) # Ensure data is within Int16 range


    # Convert numpy array back to bytes
    resampled_audio_bytes_16khz = audio_array_16khz.tobytes()

    return resampled_audio_bytes_16khz