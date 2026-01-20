import os
import time
import requests
import smtplib
from email.message import EmailMessage
from flask import Flask, Response, send_from_directory, request
from twilio.twiml.voice_response import VoiceResponse

app = Flask(__name__)

# ---- ENV ----
ELEVENLABS_API_KEY = os.environ.get("ELEVENLABS_API_KEY")
ELEVENLABS_VOICE_ID = os.environ.get("ELEVENLABS_VOICE_ID")
PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL")

EMAIL_HOST = os.environ.get("EMAIL_HOST")
EMAIL_PORT = int(os.environ.get("EMAIL_PORT", "587"))
EMAIL_USER = os.environ.get("EMAIL_USER")
EMAIL_PASS = os.environ.get("EMAIL_PASS")
EMAIL_TO = "artie_swinton@ncwp.uscourts.gov"

# ---- BASIC ROUTES ----
@app.route("/")
def health():
    return "OK"

@app.route("/static/<path:filename>")
def static_files(filename):
    return send_from_directory("static", filename)

# ---- HELPERS ----
def generate_voice(text):
    filename = f"audio_{int(time.time())}.mp3"
    filepath = f"static/{filename}"

    url = f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE_ID}"
    headers = {
        "xi-api-key": ELEVENLABS_API_KEY,
        "Content-Type": "application/json",
        "Accept": "audio/mpeg"
    }
    payload = {"text": text}

    r = requests.post(url, json=payload, headers=headers, timeout=30)
    r.raise_for_status()

    os.makedirs("static", exist_ok=True)
    with open(filepath, "wb") as f:
        f.write(r.content)

    return f"{PUBLIC_BASE_URL}/{filepath}"

def yes_no(value):
    value = value.lower()
    if "yes" in value:
        return "Yes"
    if "no" in value:
        return "No"
    return "Unclear"

def send_summary(data):
    msg = EmailMessage()
    msg["Subject"] = "AI Voicebot – Supervision Intake Summary"
    msg["From"] = EMAIL_USER
    msg["To"] = EMAIL_TO

    body = f"""
AI VOICEBOT INTAKE SUMMARY

Caller Phone: {data.get("caller")}

Under Supervision: {data.get("supervision")}
Supervising Officer: {data.get("officer")}

Recent Release (last 30 days): {data.get("recent_release")}

Urgent Needs: {data.get("urgent_needs")}
Urgent Need Details: {data.get("urgent_details")}

Compliance Difficulty: {data.get("compliance_issue")}
Compliance Details: {data.get("compliance_details")}

Requested Assistance:
{data.get("assistance")}

Well-being Support Requested: {data.get("support_needed")}
Contact Number: {data.get("contact")}
"""

    msg.set_content(body)

    with smtplib.SMTP(EMAIL_HOST, EMAIL_PORT) as server:
        server.starttls()
        server.login(EMAIL_USER, EMAIL_PASS)
        server.send_message(msg)

# ---- FLOW ----

@app.route("/voice", methods=["POST", "GET"])
def step_1():
    resp = VoiceResponse()
    audio = generate_voice(
        "Are you currently on probation or supervised release? Please say yes or no."
    )

    gather = resp.gather(
        input="speech",
        action="/step-2",
        method="POST",
        speechTimeout="auto"
    )
    gather.play(audio)

    resp.say("No response received. Goodbye.")
    return Response(str(resp), mimetype="text/xml")

@app.route("/step-2", methods=["POST"])
def step_2():
    supervision = yes_no(request.form.get("SpeechResult", ""))

    if supervision != "Yes":
        resp = VoiceResponse()
        resp.say("This system is for supervised clients only. Goodbye.")
        resp.hangup()
        return Response(str(resp), mimetype="text/xml")

    resp = VoiceResponse()
    audio = generate_voice("Who is your supervising officer? Please say their name.")
    gather = resp.gather(
        input="speech",
        action="/step-3",
        method="POST",
        speechTimeout="auto"
    )
    gather.play(audio)

    return Response(str(resp), mimetype="text/xml")

@app.route("/step-3", methods=["POST"])
def step_3():
    officer = request.form.get("SpeechResult", "Unknown")

    resp = VoiceResponse()
    audio = generate_voice(
        "Have you been released from custody within the past thirty days? Please say yes or no."
    )
    gather = resp.gather(
        input="speech",
        action="/step-4",
        method="POST",
        speechTimeout="auto"
    )
    gather.play(audio)

    resp.redirect(f"/step-4?officer={officer}", method="POST")
    return Response(str(resp), mimetype="text/xml")

@app.route("/step-4", methods=["POST"])
def step_4():
    officer = request.args.get("officer", "Unknown")
    recent_release = yes_no(request.form.get("SpeechResult", ""))

    resp = VoiceResponse()
    audio = generate_voice(
        "Do you have any urgent needs right now such as housing, food, medication, or transportation? Please say yes or no."
    )
    gather = resp.gather(
        input="speech",
        action="/step-5",
        method="POST",
        speechTimeout="auto"
    )
    gather.play(audio)

    resp.redirect(
        f"/step-5?officer={officer}&recent_release={recent_release}",
        method="POST"
    )
    return Response(str(resp), mimetype="text/xml")

@app.route("/step-5", methods=["POST"])
def step_5():
    officer = request.args.get("officer")
    recent_release = request.args.get("recent_release")
    urgent_needs = yes_no(request.form.get("SpeechResult", ""))

    resp = VoiceResponse()

    if urgent_needs == "Yes":
        audio = generate_voice("Please briefly describe your urgent need.")
        gather = resp.gather(
            input="speech",
            action="/step-6",
            method="POST",
            speechTimeout="auto"
        )
        gather.play(audio)
        return Response(str(resp), mimetype="text/xml")

    resp.redirect(
        f"/step-6?officer={officer}&recent_release={recent_release}&urgent_needs=No",
        method="POST"
    )
    return Response(str(resp), mimetype="text/xml")

@app.route("/step-6", methods=["POST"])
def step_6():
    data = {
        "caller": request.form.get("From"),
        "officer": request.args.get("officer"),
        "recent_release": request.args.get("recent_release"),
        "urgent_needs": request.args.get("urgent_needs", "Yes"),
        "urgent_details": request.form.get("SpeechResult", "None"),
        "supervision": "Yes"
    }

    resp = VoiceResponse()
    audio = generate_voice("How can I assist you today? Please explain.")
    gather = resp.gather(
        input="speech",
        action="/finish",
        method="POST",
        speechTimeout="auto"
    )
    gather.play(audio)

    resp.redirect("/finish", method="POST")
    return Response(str(resp), mimetype="text/xml")

@app.route("/finish", methods=["POST"])
def finish():
    data = {
        "caller": request.form.get("From"),
        "officer": request.args.get("officer"),
        "recent_release": request.args.get("recent_release"),
        "urgent_needs": request.args.get("urgent_needs"),
        "urgent_details": request.args.get("urgent_details"),
        "assistance": request.form.get("SpeechResult"),
        "support_needed": "Not assessed",
        "contact": request.form.get("From"),
        "supervision": "Yes"
    }

    send_summary(data)

    resp = VoiceResponse()
    resp.say(
        "Thank you. Your information has been sent for review. Someone will follow up with you soon."
    )
    resp.hangup()
    return Response(str(resp), mimetype="text/xml")
