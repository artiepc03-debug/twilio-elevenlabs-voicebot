import os
import time
import requests
from flask import Flask, request, Response, send_from_directory
from twilio.twiml.voice_response import VoiceResponse

app = Flask(__name__)

# Read secrets from environment variables (best practice for Render)
ELEVENLABS_API_KEY = os.environ.get("ELEVENLABS_API_KEY", "")
ELEVENLABS_VOICE_ID = os.environ.get("ELEVENLABS_VOICE_ID", "")
PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "")  # e.g. https://your-service.onrender.com

@app.get("/")
def health():
    return "OK"

@app.get("/static/<path:filename>")
def static_files(filename):
    return send_from_directory("static", filename)

@app.post("/voice")
def voice():
    # Basic script for proof-of-integration
    text = (
        "Hello. This is your Eleven Labs voice, delivered through Twilio. "
        "Your integration is working."
    )

    if not ELEVENLABS_API_KEY or not ELEVENLABS_VOICE_ID or not PUBLIC_BASE_URL:
        resp = VoiceResponse()
        resp.say("Configuration error. Missing environment variables.")
        return Response(str(resp), mimetype="text/xml")

    # Generate a unique filename per call to avoid conflicts
    fname = f"tts_{int(time.time())}.mp3"
    local_path = os.path.join("static", fname)

    try:
        generate_elevenlabs_tts(text, local_path)
    except Exception:
        resp = VoiceResponse()
        resp.say("I could not generate speech from Eleven Labs.")
        return Response(str(resp), mimetype="text/xml")

    audio_url = f"{PUBLIC_BASE_URL}/static/{fname}"

    resp = VoiceResponse()
    resp.play(audio_url)
    resp.pause(length=1)
    resp.hangup()
    return Response(str(resp), mimetype="text/xml")


def generate_elevenlabs_tts(text: str, output_file: str) -> None:
    """
    Calls ElevenLabs Text-to-Speech API and writes MP3 bytes to output_file.
    """
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE_ID}"

    headers = {
        "xi-api-key": ELEVENLABS_API_KEY,
        "Content-Type": "application/json",
        "Accept": "audio/mpeg",
    }

    payload = {
        "text": text,
        # model_id may vary by account; this is a common default
        "model_id": "eleven_monolingual_v1",
        "voice_settings": {
            "stability": 0.45,
            "similarity_boost": 0.80
        }
    }

    r = requests.post(url, json=payload, headers=headers, timeout=30)
    r.raise_for_status()

    os.makedirs("static", exist_ok=True)
    with open(output_file, "wb") as f:
        f.write(r.content)
