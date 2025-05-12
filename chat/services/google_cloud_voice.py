# chat/services/google_cloud_voice.py
import os
import asyncio
from google.cloud import texttospeech
from google.oauth2 import service_account
from django.conf import settings
from asgiref.sync import sync_to_async

KEY_FILE_NAME = 'big-buttress-457415-v1-2a505cf38889.json'

print("--- Loading chat/services/google_cloud_voice.py (Version 6 - TTS Only, MP3 Output - Less Comments) ---")

# Determine the credentials file path
KEY_FILE_PATH = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
if not KEY_FILE_PATH:
    base_dir_path = getattr(settings, 'BASE_DIR', None)
    if base_dir_path:
        KEY_FILE_PATH = os.path.join(base_dir_path, KEY_FILE_NAME)
    else:
        KEY_FILE_PATH = KEY_FILE_NAME

    if not os.path.exists(KEY_FILE_PATH):
        print(f"WARNING: Credentials file not found: {KEY_FILE_PATH}")
        KEY_FILE_PATH = None
    else:
        print(f"Loading credentials from fallback: {KEY_FILE_PATH}")
else:
    if not os.path.exists(KEY_FILE_PATH):
        print(f"ERROR: Credentials file specified by GOOGLE_APPLICATION_CREDENTIALS not found: {KEY_FILE_PATH}")
        KEY_FILE_PATH = None
    else:
        print(f"Loading credentials from GOOGLE_APPLICATION_CREDENTIALS: {KEY_FILE_PATH}")

_tts_client_instance = None
_credentials_instance = None

async def _get_credentials():
    """Asynchronously load and return credentials, caching the result."""
    global _credentials_instance
    if _credentials_instance:
        return _credentials_instance

    if not KEY_FILE_PATH or not os.path.exists(KEY_FILE_PATH):
        print("_get_credentials: Credentials file path is not valid.")
        return None

    try:
        _credentials_instance = await sync_to_async(service_account.Credentials.from_service_account_file)(KEY_FILE_PATH)
        print("_get_credentials: Credentials loaded successfully.")
        return _credentials_instance
    except Exception as e:
        print(f"ERROR: Failed to load Google Cloud credentials: {e}")
        _credentials_instance = None
        return None

async def get_tts_client():
    """Asynchronously get or create the synchronous TextToSpeechClient instance."""
    global _tts_client_instance
    if _tts_client_instance:
        return _tts_client_instance

    print("get_tts_client: Initializing new TextToSpeechClient...")
    credentials = await _get_credentials()
    if not credentials:
        print("get_tts_client: Failed to get credentials.")
        return None

    try:
        _tts_client_instance = texttospeech.TextToSpeechClient(credentials=credentials)
        print("get_tts_client: Text-to-Speech Client initialized successfully.")
        return _tts_client_instance
    except Exception as e:
        print(f"ERROR: Failed to initialize TextToSpeechClient: {e}")
        _tts_client_instance = None
        return None

async def synthesize_text(text):
    """
    Synthesizes text into speech using Google Cloud Text-to-Speech.

    Args:
        text (str): The text to synthesize.

    Returns:
        tuple: A tuple containing:
            - bytes: The binary audio content (MP3).
            - str: The MIME type of the audio ('audio/mpeg').
            Returns (b"", "") on error or no text.
    """
    tts_client = await get_tts_client()

    if not tts_client:
        print("TTS: Client not available. Cannot synthesize.")
        return b"", ""

    if not text or not text.strip():
        print("TTS: No text to synthesize.")
        return b"", ""

    print(f"TTS: Synthesizing text...")

    synthesis_input = texttospeech.SynthesisInput(text=text)

    voice = texttospeech.VoiceSelectionParams(
        language_code="en-US",
        ssml_gender=texttospeech.SsmlVoiceGender.NEUTRAL
    )

    audio_encoding = texttospeech.AudioEncoding.MP3
    audio_config = texttospeech.AudioConfig(
        audio_encoding=audio_encoding,
    )

    try:
        response = await sync_to_async(tts_client.synthesize_speech)(
            input=synthesis_input,
            voice=voice,
            audio_config=audio_config,
        )
        print(f"TTS: Synthesis successful. Received {len(response.audio_content)} bytes.")

        mime_type = "audio/mpeg"

        return response.audio_content, mime_type

    except Exception as e:
        print(f"TTS: Google Cloud TTS synthesis error: {e}")
        return b"", ""