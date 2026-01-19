import os
import time
import requests
from flask import Flask, Response, send_from_directory, request
from twilio.twiml.voice_response import VoiceResponse

app = Flask(__name__)

ELEVENLABS_API_KEY = os.environ.get("ELEVENLABS_API_KEY")
ELEVENLABS_VOICE_ID = os.environ.get("ELEVENLABS_VOICE_ID")
PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL")

@app.route("/", methods=["GET"])
def health():
    return "OK"

@app.route("/static/<path:filename>")
def static_files(filename):
    return send_from_directory("static", filename)

@app.route("/voice", methods=["POST", "GET"])
def voice():
    resp = VoiceResponse()

    question = "Please say your first and last name after the tone."

    filename = f"q_{int(time.time())}.mp3"
    filepath = f"static/{filename}"
    generate_voice(question, filepath)

    gather = resp.gather(
        input="speech",
        action="/process-name",
        method="POST",
        speechTimeout="auto"
    )

    gather.play(f"{PUBLIC_BASE_URL}/{filepath}")

    resp.say("We did not receive your response. Goodbye.")
    return Response(str(resp), mimetype="text/xml")

@app.route("/process-name", methods=["POST"])
def process_name():
    resp = VoiceResponse()

    name = request.form.get("SpeechResult", "")

    if not name:
        resp.say("I did not hear your name. Please try again later.")
        return Response(str(resp), mimetype="text/xml")

    reply = f"Thank you {name}. Your response has been recorded."

    filename = f"r_{int(time.time())}.mp3"
    filepath = f"static/{filename}"
    generate_voice(reply, filepath)

    resp.play(f"{PUBLIC_BASE_URL}/{filepath}")
    resp.hangup()

    return Response(str(resp), mimetype="text/xml")


def generate_voice(text, output_file):
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE_ID}"

    headers = {
        "xi-api-key": ELEVENLABS_API_KEY,
        "Content-Type": "application/json",
        "Accept": "audio/mpeg"
    }

    payload = {
        "text": text,
        "model_id": "eleven_multilingual_v2"
    }

    r = requests.post(url, json=payload, headers=headers, timeout=30)
    r.raise_for_status()

    os.makedirs("static", exist_ok=True)
    with open(output_file, "wb") as f:
        f.write(r.content)
