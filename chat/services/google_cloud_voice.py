import os
import asyncio
import json  # Import json if needed for messages, often done in the consumer
# Ensure you have the google-cloud-speech and google-cloud-texttospeech libraries installed:
# pip install google-cloud-speech google-cloud-texttospeech
from google.cloud import speech  # Used for RecognitionConfig and StreamingRecognitionConfig
# For asynchronous streaming with google-cloud-speech >= 2.0, SpeechAsyncClient from v1 is preferred
# try:
#     from google.cloud.speech_v1 import SpeechAsyncClient
# except ImportError:
#     SpeechAsyncClient = None  # Fallback if async client is not installed

from google.cloud import texttospeech  # TTS client is typically synchronous
from google.oauth2 import service_account
from django.conf import settings
# Needed to run synchronous code (like the TTS client) from an asynchronous context (like Channels consumer)
from asgiref.sync import sync_to_async
# Ensure you have the google-cloud-speech>=2.0 library installed.
# Use the async client from v1
from google.cloud.speech_v1 import SpeechAsyncClient # <-- Import the async client
# You likely don't need the standard speech import anymore if only using async
# from google.cloud import speech # <-- Can probably remove this line

# --- Configuration and Client Initialization ---
# Prefer loading credentials from GOOGLE_APPLICATION_CREDENTIALS environment variable.
# This is the standard and recommended way for server applications.
# If the environment variable is not set, fallback to a file path relative to settings.BASE_DIR.
# WARNING: Storing credentials file directly in the project directory is risky if not
# properly excluded from version control (.gitignore).
KEY_FILE_NAME = 'big-buttress-457415-v1-2a505cf38889.json'  # Your credentials file name
KEY_FILE_PATH = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")

# --- UNIQUE PRINT STATEMENT TO VERIFY FILE LOADING ---
print("--- Loading chat/services/google_cloud_voice.py (Version 4 - Final Attempt) ---")
# -----------------------------------------------------------------------


if not KEY_FILE_PATH:
    KEY_FILE_PATH = os.path.join(settings.BASE_DIR, KEY_FILE_NAME)
    # Check if the fallback path exists before trying to load from it
    if not os.path.exists(KEY_FILE_PATH):
        print(f"WARNING: GOOGLE_APPLICATION_CREDENTIALS environment variable not set AND fallback file not found at: {KEY_FILE_PATH}")
        print("Please set the GOOGLE_APPLICATION_CREDENTIALS env var or ensure the key file is in the project base directory.")
        KEY_FILE_PATH = None  # Set to None so we don't try to load a non-existent file
    else:
        print(f"GOOGLE_APPLICATION_CREDENTIALS environment variable not set, attempting to load from fallback file: {KEY_FILE_PATH}")
else:
    # Check if the path from the environment variable exists
    if not os.path.exists(KEY_FILE_PATH):
        print(f"ERROR: Google Cloud credentials file specified by GOOGLE_APPLICATION_CREDENTIALS not found at: {KEY_FILE_PATH}")
        print("Please check the path set in the environment variable.")
        KEY_FILE_PATH = None  # Set to None so we don't try to load non-existent file
    else:
        print(f"Loading Google Cloud credentials from GOOGLE_APPLICATION_CREDENTIALS environment variable: {KEY_FILE_PATH}")


# Initialize clients - explicitly loading credentials from the file if a path is found
credentials = None
speech_client_async  = None  # Will hold the SpeechClient instance
tts_client = None  # Will hold the TextToSpeechClient instance

if KEY_FILE_PATH and os.path.exists(KEY_FILE_PATH):
    try:
        credentials = service_account.Credentials.from_service_account_file(KEY_FILE_PATH)

        # --- Initialize Speech Async Client ---
        # Use the SpeechAsyncClient here
        speech_client_async = SpeechAsyncClient(credentials=credentials)
        print("Google Cloud Speech ASYNC Client initialized.")

        # --- Initialize TTS Client (Synchronous) ---
        tts_client = texttospeech.TextToSpeechClient(credentials=credentials)
        print("Google Cloud Text-to-Speech Client initialized.")

    except Exception as e:
        print(f"ERROR: Failed to initialize Google Cloud clients: {e}")
        # Ensure both are None on failure
        speech_client_async = None
        tts_client = None
else:
    print("WARNING: Skipping Google Cloud client initialization due to missing credentials path or file.")

# --- Speech-to-Text Streaming Function ---
# This function is an async generator that takes an async iterator of requests
# (created by the consumer) and yields back the transcription results from Google.
# Inside chat/services/google_cloud_voice.py

# Inside chat/services/google_cloud_voice.py

async def stream_transcribe_async(requests_iterator):
    """
    Initiates and processes a Google Cloud Speech-to-Text streaming recognition.
    """
    # Check if the ASYNC Speech client was successfully initialized
    # Keep this check and print
    if not speech_client_async: # Check the ASYNC client variable
        print("GC_STT: Async Speech client not initialized. Cannot transcribe.")
        # Consider raising an error here or yielding an error signal
        return

    # Keep this print
    print("GC_STT: Calling speech_client_async.streaming_recognize()...")

    # === ADD THIS PRINT just before the try block ===
    print("DEBUG GC_STT: ### Before try block in streaming_recognize ###")

    try:
        # === ADD THIS PRINT before the await call ===
        print("DEBUG GC_STT: ### Before await streaming_recognize ###")
        # This is the call that returns the async iterable
        responses = await speech_client_async.streaming_recognize(requests_iterator)
        # === ADD THIS PRINT immediately after the await call ===
        print("DEBUG GC_STT: ### After await streaming_recognize ###") # <-- DOES EXECUTION REACH HERE?

        # If execution reaches here, the 'responses' variable *should* be an async iterable
        # Keep this print
        print("GC_STT: Awaiting responses from Google...") # <-- This log should appear next if the await completed
        # === ADD THESE PRINTS to inspect the returned object ===
        print(f"DEBUG GC_STT: Type of 'responses' object: {type(responses)}")
        print(f"DEBUG GC_STT: 'responses' object: {responses}")

        # The async for loop will iterate over results from Google
        async for response in responses:
            # === KEEP DEBUG PRINTS INSIDE THE LOOP TOO ===
            print(f"DEBUG GC_STT: Received response object from Google: {response}")
            print(f"DEBUG GC_STT: Response results: {response.results}")

            if not response.results:
                print("DEBUG GC_STT: Response has no results.")
                # Continue the loop, waiting for potential later results
                continue

            # Process the results if they exist
            result = response.results[0]
            if not result.alternatives:
                 print("DEBUG GC_STT: Result has no alternatives.")
                 # Continue the loop
                 continue

            # Extract transcript and finality
            transcript = result.alternatives[0].transcript
            is_final = result.is_final

            # Yield results back to the consumer
            if transcript: # Only yield if there's actual transcript text
                print(f"DEBUG GC_STT: Yielding transcript: '{transcript}' (final: {is_final})")
                yield transcript, is_final
            else:
                 # Handle cases where a result might be final but empty? (Less common for Google STT)
                 print("DEBUG GC_STT: Received empty transcript.")


    except Exception as e:
        # If a standard Python exception happens within the try block, this will log it
        print(f"GC_STT: Error during streaming recognition: {e}") # <-- If an exception happens here, this will log it
        # It might be useful to yield an error signal back to the consumer here
        # yield "", False # Or a specific error format
        raise # Re-raise the exception so the consumer task fails gracefully or handles it

    finally:
        # This block should execute when the try block finishes, an exception occurs, or the generator is closed
        print("GC_STT: stream_transcribe_async generator finished.") # <-- If the generator finishes, this will log it
        
        # --- Text-to-Speech Synthesis Function ---
# This function synthesizes text to speech and returns audio bytes.
# It uses sync_to_async because the TTS client is synchronous.
async def synthesize_text(text):
    """
    Synthesizes text into speech using Google Cloud Text-to-Speech.

    Args:
        text (str): The text to synthesize.

    Returns:
        bytes: The binary audio content (e.g., LINEAR16 or WAV).
               Returns empty bytes b"" on error or no text.
    """
    if not tts_client:
        print("TTS: Client not initialized. Cannot synthesize.")
        return b""

    if not text or not text.strip():
        print("TTS: No text to synthesize.")
        return b""

    print(f"TTS: Synthesizing text...")

    synthesis_input = texttospeech.SynthesisInput(text=text)

    voice = texttospeech.VoiceSelectionParams(
        language_code="en-US",
        ssml_gender=texttospeech.SsmlVoiceGender.NEUTRAL
    )

    audio_config = texttospeech.AudioConfig(
        audio_encoding=texttospeech.AudioEncoding.LINEAR16,
        sample_rate_hertz=16000
    )

    try:
        response = await sync_to_async(tts_client.synthesize_speech)(
            input=synthesis_input,
            voice=voice,
            audio_config=audio_config,
        )
        print(f"TTS: Synthesis successful. Received {len(response.audio_content)} bytes.")
        return response.audio_content

    except Exception as e:
        print(f"TTS: Google Cloud TTS synthesis error: {e}")
        return b""
