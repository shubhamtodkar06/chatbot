# chat/services/google_cloud_voice.py
import os
import asyncio
# No need to import json here, handled in consumer
from google.cloud import speech # Used for RecognitionConfig and StreamingRecognitionConfig
from google.cloud import texttospeech # TTS client is typically synchronous
from google.oauth2 import service_account
from django.conf import settings
from asgiref.sync import sync_to_async

# Import the async client
from google.cloud.speech_v1 import SpeechAsyncClient

KEY_FILE_NAME = 'big-buttress-457415-v1-2a505cf38889.json' # Your credentials file name

# --- UNIQUE PRINT STATEMENT TO VERIFY FILE LOADING ---
print("--- Loading chat/services/google_cloud_voice.py (Version 5 - Refactored Client Init) ---")
# -----------------------------------------------------------------------

# Determine the credentials file path
KEY_FILE_PATH = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
if not KEY_FILE_PATH:
    KEY_FILE_PATH = os.path.join(settings.BASE_DIR, KEY_FILE_NAME)
    if not os.path.exists(KEY_FILE_PATH):
        print(f"WARNING: GOOGLE_APPLICATION_CREDENTIALS env var not set AND fallback file not found at: {KEY_FILE_PATH}")
        print("Please set the GOOGLE_APPLICATION_CREDENTIALS env var or ensure the key file is in the project base directory.")
        KEY_FILE_PATH = None
    else:
        print(f"GOOGLE_APPLICATION_CREDENTIALS env var not set, attempting to load from fallback file: {KEY_FILE_PATH}")
else:
    if not os.path.exists(KEY_FILE_PATH):
        print(f"ERROR: Google Cloud credentials file specified by GOOGLE_APPLICATION_CREDENTIALS not found at: {KEY_FILE_PATH}")
        print("Please check the path set in the environment variable.")
        KEY_FILE_PATH = None
    else:
        print(f"Loading Google Cloud credentials from GOOGLE_APPLICATION_CREDENTIALS env var: {KEY_FILE_PATH}")


# --- Refactored Client Initialization ---
# We will now initialize clients within async functions or on demand
_speech_client_async_instance = None
_tts_client_instance = None
_credentials_instance = None # Cache credentials


async def _get_credentials():
    """Asynchronously load and return credentials, caching the result."""
    global _credentials_instance
    if _credentials_instance:
        return _credentials_instance

    if not KEY_FILE_PATH or not os.path.exists(KEY_FILE_PATH):
        print("_get_credentials: Credentials file path is not valid.")
        return None

    try:
        # service_account.Credentials.from_service_account_file is synchronous
        # Use sync_to_async to run it in a thread pool
        _credentials_instance = await sync_to_async(service_account.Credentials.from_service_account_file)(KEY_FILE_PATH)
        print("_get_credentials: Credentials loaded successfully.")
        return _credentials_instance
    except Exception as e:
        print(f"ERROR: Failed to load Google Cloud credentials: {e}")
        _credentials_instance = None # Ensure it's None on failure
        return None


async def get_speech_client_async():
    """Asynchronously get or create the SpeechAsyncClient instance."""
    global _speech_client_async_instance
    if _speech_client_async_instance:
        # print("get_speech_client_async: Returning cached client instance.") # Keep noisy logs commented
        return _speech_client_async_instance

    print("get_speech_client_async: Initializing new SpeechAsyncClient...")
    credentials = await _get_credentials()
    if not credentials:
        print("get_speech_client_async: Failed to get credentials.")
        return None

    try:
        # Initialize the async client within an async function
        _speech_client_async_instance = SpeechAsyncClient(credentials=credentials)
        print("get_speech_client_async: Speech ASYNC Client initialized successfully.")
        return _speech_client_async_instance
    except Exception as e:
        print(f"ERROR: Failed to initialize SpeechAsyncClient: {e}")
        _speech_client_async_instance = None # Ensure it's None on failure
        return None


async def get_tts_client():
    """Asynchronously get or create the synchronous TextToSpeechClient instance."""
    global _tts_client_instance
    if _tts_client_instance:
        # print("get_tts_client: Returning cached client instance.") # Keep noisy logs commented
        return _tts_client_instance

    print("get_tts_client: Initializing new TextToSpeechClient...")
    credentials = await _get_credentials()
    if not credentials:
        print("get_tts_client: Failed to get credentials.")
        return None

    try:
        # Initialize the synchronous client within an async function
        # The TTS synthesis call itself will use sync_to_async
        _tts_client_instance = texttospeech.TextToSpeechClient(credentials=credentials)
        print("get_tts_client: Text-to-Speech Client initialized successfully.")
        return _tts_client_instance
    except Exception as e:
        print(f"ERROR: Failed to initialize TextToSpeechClient: {e}")
        _tts_client_instance = None # Ensure it's None on failure
        return None


# --- Speech-to-Text Streaming Function ---
# This function is an async generator that takes an async iterator of requests
# (created by the consumer) and yields back the transcription results from Google.
async def stream_transcribe_async(requests_iterator):
    """
    Initiates and processes a Google Cloud Speech-to-Text streaming recognition.
    """
    # Get the async Speech client instance
    speech_client_async = await get_speech_client_async() # <-- Get client here

    # Check if the ASYNC Speech client was successfully initialized
    if not speech_client_async:
        print("GC_STT: Async Speech client not available. Cannot transcribe.") # Keep this log
        # We cannot proceed without the client, so we simply return
        return # Exit the generator

    print("GC_STT: Calling speech_client_async.streaming_recognize()...") # Keep this print

    # === ADD THIS PRINT just before the try block ===
    print("DEBUG GC_STT: ### Before try block in streaming_recognize ###") # Keep this print

    try:
        # === ADD THIS PRINT before the await call ===
        print("DEBUG GC_STT: ### Before await streaming_recognize ###") # Keep this print
        # This is the call that returns the async iterable
        responses = await speech_client_async.streaming_recognize(requests_iterator)
        # === ADD THIS PRINT immediately after the await call ===
        print("DEBUG GC_STT: ### After await streaming_recognize ###") # Keep this print

        # If execution reaches here, the 'responses' variable *should* be an async iterable
        print("GC_STT: Awaiting responses from Google...") # Keep this print
        # === ADD THESE PRINTS to inspect the returned object ===
        print(f"DEBUG GC_STT: Type of 'responses' object: {type(responses)}") # Keep this print
        # print(f"DEBUG GC_STT: 'responses' object: {responses}") # Keep noisy logs commented

        # The async for loop will iterate over results from Google
        async for response in responses:
            # === KEEP DEBUG PRINTS INSIDE THE LOOP TOO ===
            # print(f"DEBUG GC_STT: Received response object from Google: {response}") # Keep noisy logs commented
            # print(f"DEBUG GC_STT: Response results: {response.results}") # Keep noisy logs commented

            if not response.results:
                print("DEBUG GC_STT: Response has no results.") # Keep this print
                # Continue the loop, waiting for potential later results
                continue

            # Process the results if they exist
            result = response.results[0]
            if not result.alternatives:
                 print("DEBUG GC_STT: Result has no alternatives.") # Keep this print
                 # Continue the loop
                 continue

            # Extract transcript and finality
            transcript = result.alternatives[0].transcript
            is_final = result.is_final

            # Yield results back to the consumer
            if transcript: # Only yield if there's actual transcript text
                 print(f"DEBUG GC_STT: Yielding transcript: '{transcript}' (final: {is_final})") # Keep this print
                 yield transcript, is_final
            else:
                 # Handle cases where a result might be final but empty? (Less common for Google STT)
                 print("DEBUG GC_STT: Received empty transcript.") # Keep this print


    except Exception as e:
        # If a standard Python exception happens within the try block, this will log it
        print(f"GC_STT: Error during streaming recognition: {e}") # Keep this log
        # It might be useful to yield an error signal back to the consumer here
        # yield "", False # Or a specific error format
        raise # Re-raise the exception so the consumer task fails gracefully or handles it

    finally:
        # This block should execute when the try block finishes, an exception occurs, or the generator is closed
        print("GC_STT: stream_transcribe_async generator finished.") # Keep this log


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
    # Get the synchronous TTS client instance
    tts_client = await get_tts_client() # <-- Get client here

    if not tts_client:
        print("TTS: Client not available. Cannot synthesize.") # Keep this log
        return b""

    if not text or not text.strip():
        print("TTS: No text to synthesize.") # Keep this log
        return b""

    print(f"TTS: Synthesizing text...") # Keep this log

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
        # Use sync_to_async to run the synchronous TTS client method
        response = await sync_to_async(tts_client.synthesize_speech)(
            input=synthesis_input,
            voice=voice,
            audio_config=audio_config,
        )
        print(f"TTS: Synthesis successful. Received {len(response.audio_content)} bytes.") # Keep this log
        return response.audio_content

    except Exception as e:
        print(f"TTS: Google Cloud TTS synthesis error: {e}") # Keep this log
        return b""

