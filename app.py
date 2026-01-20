import os
import time
import requests
import smtplib
from email.message import EmailMessage
from flask import Flask, Response, send_from_directory, request
from twilio.twiml.voice_response import VoiceResponse
from openai import OpenAI

app = Flask(__name__)

# =========================
# ENVIRONMENT VARIABLES
# =========================
ELEVENLABS_API_KEY = os.environ.get("ELEVENLABS_API_KEY")
ELEVENLABS_VOICE_ID = os.environ.get("ELEVENLABS_VOICE_ID")
PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL")

EMAIL_HOST = os.environ.get("EMAIL_HOST")
EMAIL_PORT = int(os.environ.get("EMAIL_PORT", "587"))
EMAIL_USER = os.environ.get("EMAIL_USER")
EMAIL_PASS = os.environ.get("EMAIL_PASS")
EMAIL_TO = "artie_swinton@ncwp.uscourts.gov"

client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

# =========================
# BASIC ROUTES
# =========================
@app.route("/")
def health():
    return "OK"

@app.route("/static/<path:filename>")
def static_files(filename):
    return send_from_directory("static", filename)

# =========================
# HELPER FUNCTIONS
# =========================
def elevenlabs_voice(text):
    filename = f"el_{int(time.time())}.mp3"
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

def yes_no(text):
    t = text.lower()
    if "yes" in t:
        return "Yes"
    if "no" in t:
        return "No"
    return None

def ai_answer(user_text):
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a professional probation and reentry assistance AI. "
                    "Respond clearly, respectfully, and supportively. "
                    "Do not provide legal advice. Encourage compliance and stability."
                )
            },
            {"role": "user", "content": user_text}
        ],
        temperature=0.3,
        max_tokens=120
    )
    return response.choices[0].message.content.strip()

def interrupt_acknowledge_yesno(user_text):
    yn = yes_no(user_text)

    if yn:
        return yn, None

    ai_reply = ai_answer(user_text)
    acknowledge = f"{ai_reply} Thank you for asking. Let’s continue."
    return "Acknowledge", acknowledge

def interrupt_acknowledge_text(user_text):
    if len(user_text.strip()) >= 3:
        return user_text, None

    ai_reply = ai_answer(user_text)
    acknowledge = f"{ai_reply} Thank you. Let’s continue."
    return "Acknowledge", acknowledge

def send_summary(data):
    msg = EmailMessage()
    msg["Subject"] = "AI Voicebot – Supervision Intake Summary"
    msg["From"] = EMAIL_USER
    msg["To"] = EMAIL_TO

    msg.set_content(f"""
AI VOICEBOT SUMMARY

Caller: {data.get("caller")}

Under Supervision: Yes
Officer: {data.get("officer")}
Recent Release (30 days): {data.get("recent_release")}
Urgent Needs: {data.get("urgent")}
Urgent Details: {data.get("urgent_details")}

Client Request:
{data.get("assistance")}
""")

    with smtplib.SMTP(EMAIL_HOST, EMAIL_PORT) as server:
        server.starttls()
        server.login(EMAIL_USER, EMAIL_PASS)
        server.send_message(msg)

# =========================
# CALL FLOW
# =========================
@app.route("/voice", methods=["POST", "GET"])
def step_1():
    resp = VoiceResponse()
    audio = elevenlabs_voice(
        "Hello. Are you currently on probation or supervised release? Please say yes or no."
    )
    gather = resp.gather(
        input="speech",
        action="/step-2",
        method="POST",
        speechTimeout="auto"
    )
    gather.play(audio)
    return Response(str(resp), mimetype="text/xml")

@app.route("/step-2", methods=["POST"])
def step_2():
    resp = VoiceResponse()
    user_text = request.form.get("SpeechResult", "")

    result, message = interrupt_acknowledge_yesno(user_text)

    if result == "No":
        resp.say("This system is for supervised clients only. Goodbye.")
        resp.hangup()
        return Response(str(resp), mimetype="text/xml")

    if result == "Acknowledge":
        resp.say(message)

    audio = elevenlabs_voice(
        "Who is your supervising officer? Please say their name."
    )
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
    resp = VoiceResponse()
    officer, message = interrupt_acknowledge_text(
        request.form.get("SpeechResult", "")
    )

    if officer == "Acknowledge":
        resp.say(message)

    audio = elevenlabs_voice(
        "Have you been released from custody within the past thirty days? Please say yes or no."
    )
    gather = resp.gather(
        input="speech",
        action=f"/step-4?officer={officer}",
        method="POST",
        speechTimeout="auto"
    )
    gather.play(audio)
    return Response(str(resp), mimetype="text/xml")

@app.route("/step-4", methods=["POST"])
def step_4():
    resp = VoiceResponse()
    officer = request.args.get("officer")
    user_text = request.form.get("SpeechResult", "")

    result, message = interrupt_acknowledge_yesno(user_text)

    if result == "Acknowledge":
        resp.say(message)

    audio = elevenlabs_voice(
        "Do you have any urgent needs right now such as housing, food, medication, or transportation? Please say yes or no."
    )
    gather = resp.gather(
        input="speech",
        action=f"/step-5?officer={officer}&recent_release={result}",
        method="POST",
        speechTimeout="auto"
    )
    gather.play(audio)
    return Response(str(resp), mimetype="text/xml")

@app.route("/step-5", methods=["POST"])
def step_5():
    resp = VoiceResponse()
    officer = request.args.get("officer")
    recent_release = request.args.get("recent_release")
    user_text = request.form.get("SpeechResult", "")

    result, message = interrupt_acknowledge_yesno(user_text)

    if result == "Acknowledge":
        resp.say(message)

    if result == "Yes":
        audio = elevenlabs_voice("Please briefly describe your urgent need.")
        gather = resp.gather(
            input="speech",
            action=f"/finish?officer={officer}&recent_release={recent_release}&urgent=Yes",
            method="POST",
            speechTimeout="auto"
        )
        gather.play(audio)
        return Response(str(resp), mimetype="text/xml")

    resp.redirect(
        f"/finish?officer={officer}&recent_release={recent_release}&urgent=No",
        method="POST"
    )
    return Response(str(resp), mimetype="text/xml")

@app.route("/finish", methods=["POST"])
def finish():
    resp = VoiceResponse()
    assistance = request.form.get("SpeechResult", "")

    ai_reply = ai_answer(assistance)

    send_summary({
        "caller": request.form.get("From"),
        "officer": request.args.get("officer"),
        "recent_release": request.args.get("recent_release"),
        "urgent": request.args.get("urgent"),
        "urgent_details": assistance,
        "assistance": assistance
    })

    resp.say(ai_reply)
    resp.say("Thank you. Your information has been sent. Goodbye.")
    resp.hangup()
    return Response(str(resp), mimetype="text/xml")
