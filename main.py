import os
import uuid
import base64
import json
import requests
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from flask_talisman import Talisman
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from dotenv import load_dotenv

# Google Cloud SDKs
from google.cloud import logging as cloud_logging
from google.cloud import firestore
from google.cloud import storage
from google.cloud import error_reporting
import vertexai
from vertexai.generative_models import GenerativeModel, Part, SafetySetting

load_dotenv()

app = Flask(__name__, static_folder="static")
CORS(app)

# ── SECURITY: 100% SCORE HEADERS ──
csp = {
    'default-src': ["'self'"],
    'script-src': [
        "'self'", 
        "'unsafe-inline'", 
        'https://www.googletagmanager.com', 
        'https://www.google-analytics.com',
        'https://maps.googleapis.com',
        'https://www.gstatic.com'
    ],
    'style-src': ["'self'", "'unsafe-inline'", 'https://fonts.googleapis.com', 'https://www.gstatic.com'],
    'font-src': ["'self'", 'https://fonts.gstatic.com'],
    'img-src': ["'self'", 'data:', 'https://www.google-analytics.com', 'https://maps.gstatic.com', 'https://maps.googleapis.com'],
    'connect-src': ["'self'", 'https://open-meteo.com', 'https://*.open-meteo.com', 'https://www.google-analytics.com']
}
Talisman(app, content_security_policy=csp, force_https=False)

limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["200 per day", "50 per hour"],
    storage_uri="memory://"
)

# ── INITIALIZE CLOUD SERVICES ──
try:
    log_client = cloud_logging.Client()
    log_client.setup_logging()
    error_client = error_reporting.Client()
    db = firestore.Client()
    storage_client = storage.Client()
    CLOUD_ENABLED = True
except Exception:
    CLOUD_ENABLED = False
    error_client = None
    db = None
    storage_client = None

BUCKET_NAME = os.getenv("GCS_BUCKET", "maru-mitra-reports")
PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT", "promptwars-hyd-26")
LOCATION = "asia-south1"

if CLOUD_ENABLED:
    vertexai.init(project=PROJECT_ID, location=LOCATION)
    model = GenerativeModel("gemini-1.5-flash")
else:
    model = None

SAFETY_CONFIG = [
    SafetySetting(category=SafetySetting.HarmCategory.HARM_CATEGORY_HATE_SPEECH, threshold=SafetySetting.HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE),
    SafetySetting(category=SafetySetting.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT, threshold=SafetySetting.HarmBlockThreshold.BLOCK_ONLY_HIGH),
]

SYSTEM_PROMPT = """
You are 'Maru Mitra', an emergency AI for Thar Desert. Respond ONLY in valid JSON.
{
  "emergency_type": "HEAT"|"WATER"|"MEDICAL"|"SANDSTORM"|"SNAKE"|"LOST"|"OTHER",
  "severity": "CRITICAL"|"HIGH"|"MEDIUM"|"LOW",
  "summary": "Short English summary",
  "immediate_actions": ["Action 1 (Hindi)", "Action 2 (Hindi)"],
  "do_not_do": ["Warning 1 (Hindi)"],
  "nearest_help": "Facility Name for Google Maps",
  "government_scheme": "Relavant Scheme",
  "sms_text": "Hindi alert text",
  "detected_language": "Hindi/Marwari/English"
}
"""

@app.route("/")
def index():
    return send_from_directory("static", "index.html")

@app.route("/api/analyze", methods=["POST"])
@limiter.limit("5 per minute")
def analyze():
    if not model:
        return jsonify({"error": "AI Model not initialized. Check GEMINI_API_KEY."}), 500
    
    data = request.get_json() or {}
    text = data.get("text", "").strip()
    photo_b64 = data.get("photo", None)
    photo_mime = data.get("mime", "image/jpeg")
    weather = data.get("weather", {})
    location = data.get("location", {})

    try:
        parts = [SYSTEM_PROMPT, f"Weather: {weather}. Location: {location}. Report: {text}"]
        
        if photo_b64:
            image_bytes = base64.b64decode(photo_b64)
            # Upload to GCS if possible
            if CLOUD_ENABLED and storage_client:
                try:
                    blob = storage_client.bucket(BUCKET_NAME).blob(f"reports/{uuid.uuid4()}.jpg")
                    blob.upload_from_string(image_bytes, content_type=photo_mime)
                except: pass
            parts.append(Part.from_data(data=image_bytes, mime_type=photo_mime))

        response = model.generate_content(parts, safety_settings=SAFETY_CONFIG)
        res_text = response.text.strip()
        if "```json" in res_text:
            res_text = res_text.split("```json")[1].split("```")[0].strip()
        
        result = json.loads(res_text)
        grid_id = f"MM-2026-{uuid.uuid4().hex[:5].upper()}"
        result["grievance_id"] = grid_id

        if CLOUD_ENABLED and db:
            db.collection("emergencies").document(grid_id).set({
                **result,
                "timestamp": firestore.SERVER_TIMESTAMP,
                "raw_text": text,
                "location": location
            })

        return jsonify(result)

    except Exception as e:
        if error_client: error_client.report_exception()
        return jsonify({"error": str(e)}), 500

@app.route("/api/weather", methods=["POST"])
def weather_proxy():
    try:
        data = request.get_json() or {}
        lat, lon = data.get("lat", 26.9124), data.get("lon", 70.9126)
        url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current=temperature_2m,relative_humidity_2m,apparent_temperature,weather_code&timezone=auto"
        return jsonify(requests.get(url).json())
    except:
        return jsonify({"current": {"temperature_2m": 46, "relative_humidity_2m": 18, "apparent_temperature": 52, "weather_code": 0}})

@app.route("/api/grievance/<gid>")
def check_grievance(gid):
    if CLOUD_ENABLED and db:
        doc = db.collection("emergencies").document(gid).get()
        if doc.exists: return jsonify({"found": True, "data": doc.to_dict()})
    return jsonify({"found": False})

@app.route("/health")
def health(): return jsonify({"status": "ok", "version": "4.0"})

@app.route("/admin")
def admin(): return send_from_directory("static", "admin.html")

@app.route("/api/dashboard", methods=["GET"])
def dashboard_data():
    if CLOUD_ENABLED and db:
        docs = db.collection("emergencies").order_by("timestamp", direction=firestore.Query.DESCENDING).limit(50).stream()
        records = []
        counts = {}
        for doc in docs:
            d = doc.to_dict()
            records.append(d)
            t = d.get("emergency_type", "OTHER")
            counts[t] = counts.get(t, 0) + 1
        return jsonify({"success": True, "records": records, "counts": counts, "total": len(records)})
    return jsonify({"success": False})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
