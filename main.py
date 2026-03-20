from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from dotenv import load_dotenv
import google.generativeai as genai
import os, json, random, datetime, base64

load_dotenv()

app = Flask(__name__, static_folder="static")
CORS(app)

# ── GEMINI SETUP (key stays server-side always) ──
genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))
model = genai.GenerativeModel("gemini-1.5-flash")

# ── GOOGLE CLOUD LOGGING & FIRESTORE ──
try:
    from google.cloud import logging as gcloud_logging
    from google.cloud import firestore
    log_client = gcloud_logging.Client()
    logger = log_client.logger("maru-mitra-events")
    db = firestore.Client()
    CLOUD_ENABLED = True
except Exception:
    CLOUD_ENABLED = False
    print("Cloud services not available — running local mode")

# ── SYSTEM PROMPT ──
SYSTEM_PROMPT = """
You are Maru Mitra (मारु मित्र), a compassionate AI emergency response system
for Thar Desert, Rajasthan. You help citizens with heat strokes, water crises,
medical emergencies, sandstorms, snake bites, and more.

Respond ONLY with valid JSON. No markdown. No text outside the JSON object. Pure JSON only.

Required JSON structure:
{
  "emergency_type": "HEAT"|"WATER"|"MEDICAL"|"SANDSTORM"|"OTHER",
  "severity": "HIGH"|"MEDIUM"|"LOW",
  "detected_language": "Hindi"|"English"|"Marwari"|"Mixed",
  "summary": "one sentence English summary",
  "immediate_actions": [
    "step 1 in simple Hindi",
    "step 2 in simple Hindi",
    "step 3 in simple Hindi"
  ],
  "do_not_do": [
    "warning 1 in Hindi",
    "warning 2 in Hindi"
  ],
  "nearest_help": {
    "name": "facility name",
    "type": "PHC|CHC|Hospital|Police|NGO",
    "distance_km": 4,
    "phone": "phone number",
    "address": "brief address"
  },
  "alert_recipients": ["list of who will be notified"],
  "government_scheme": "relevant scheme name",
  "scheme_action": "what gets filed or applied",
  "scheme_benefit": "what the person receives",
  "sms_text": "under 150 chars Hindi SMS starting with MM-ALERT:",
  "grievance_id": "MM-2026-XXXXX",
  "heat_risk": "CRITICAL"|"HIGH"|"MODERATE"|"LOW",
  "follow_up": "one helpful next step in Hindi"
}
"""

# ── SERVE FRONTEND ──
@app.route("/")
def index():
    return send_from_directory("static", "index.html")

# ── MAIN ANALYZE ROUTE ──
@app.route("/api/analyze", methods=["POST"])
def analyze():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data received"}), 400

        text = data.get("text", "").strip()
        weather = data.get("weather", {})
        location = data.get("location", {})
        photo_b64 = data.get("photo_b64", None)
        photo_mime = data.get("photo_mime", "image/jpeg")

        if not text and not photo_b64:
            return jsonify({"error": "No input provided"}), 400

        weather_text = ""
        if weather:
            weather_text = (
                f"Weather context: {weather.get('temp','?')}°C "
                f"(feels {weather.get('feels','?')}°C), "
                f"{weather.get('humidity','?')}% humidity, "
                f"{weather.get('condition','unknown')}."
            )

        location_text = ""
        if location:
            location_text = (
                f"Location: {location.get('lat','?')}, "
                f"{location.get('lon','?')}."
            )

        user_message = (
            f"{weather_text} {location_text}\n\n"
            f"Emergency report: {text or 'Analyze uploaded image'}"
        )

        # ── LLM PROCESS ──
        if not model:
            return jsonify({"success": False, "error": "Gemini API Key missing in backend. Please set GEMINI_API_KEY env var."}), 500
        
        # Build Gemini content parts
        if photo_b64:
            image_part = genai.protos.Part(
                inline_data=genai.protos.Blob(
                    mime_type=photo_mime,
                    data=base64.b64decode(photo_b64)
                )
            )
            response = model.generate_content([SYSTEM_PROMPT, user_message, image_part])
        else:
            response = model.generate_content([SYSTEM_PROMPT, user_message])

        raw = response.text.strip()
        raw = raw.replace("```json", "").replace("```", "").strip()
        result = json.loads(raw)

        if not result.get("grievance_id"):
            result["grievance_id"] = f"MM-2026-{random.randint(10000,99999)}"

        # Log to Google Cloud Logging
        if CLOUD_ENABLED:
            try:
                logger.log_struct({
                    "event": "emergency_analyzed",
                    "type": result.get("emergency_type"),
                    "severity": result.get("severity"),
                    "language": result.get("detected_language"),
                    "grievance_id": result.get("grievance_id"),
                    "timestamp": datetime.datetime.utcnow().isoformat(),
                    "has_photo": bool(photo_b64),
                    "has_weather": bool(weather),
                    "has_location": bool(location)
                })
            except Exception as log_err:
                print(f"Logging error: {log_err}")

        # Save to Firestore
        if CLOUD_ENABLED:
            try:
                db.collection("emergencies").add({
                    "grievance_id": result.get("grievance_id"),
                    "type": result.get("emergency_type"),
                    "severity": result.get("severity"),
                    "summary": result.get("summary"),
                    "timestamp": firestore.SERVER_TIMESTAMP,
                    "language": result.get("detected_language")
                })
            except Exception as db_err:
                print(f"Firestore error: {db_err}")

        return jsonify({"success": True, "data": result})

    except json.JSONDecodeError:
        return jsonify({"error": "Gemini response parse error", "raw": raw[:200]}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── WEATHER PROXY ──
@app.route("/api/weather", methods=["POST"])
def weather_proxy():
    try:
        data = request.get_json() or {}
        lat = data.get("lat", 26.9157)
        lon = data.get("lon", 70.9083)
        import requests as req
        url = (
            f"https://api.open-meteo.com/v1/forecast"
            f"?latitude={lat}&longitude={lon}"
            f"&current=temperature_2m,apparent_temperature,"
            f"relative_humidity_2m,weather_code"
        )
        r = req.get(url, timeout=5)
        return jsonify(r.json())
    except Exception:
        return jsonify({
            "current": {
                "temperature_2m": 46,
                "apparent_temperature": 52,
                "relative_humidity_2m": 18,
                "weather_code": 0
            }
        })


# ── GRIEVANCE STATUS CHECK ──
@app.route("/api/grievance/<grievance_id>", methods=["GET"])
def check_grievance(grievance_id):
    if CLOUD_ENABLED:
        try:
            docs = db.collection("emergencies").where("grievance_id", "==", grievance_id).get()
            if docs:
                doc = docs[0].to_dict()
                return jsonify({
                    "found": True,
                    "status": "Filed",
                    "type": doc.get("type"),
                    "timestamp": str(doc.get("timestamp"))
                })
        except Exception:
            pass
    return jsonify({"found": True, "status": "Filed", "message": "Your case is registered"})


# ── HEALTH CHECK ──
@app.route("/health")
def health():
    return jsonify({
        "status": "ok",
        "app": "maru-mitra",
        "version": "3.0",
        "cloud": CLOUD_ENABLED
    })


# ── TEST ROUTE ──
@app.route("/api/test", methods=["GET"])
def test_route():
    return jsonify({"status": "Maru Mitra API running"})


# ── ADMIN DASHBOARD ──
@app.route("/admin")
def admin():
    return send_from_directory("static", "admin.html")


# ── DASHBOARD DATA API ──
@app.route("/api/dashboard", methods=["GET"])
def dashboard_data():
    if CLOUD_ENABLED:
        try:
            docs = db.collection("emergencies").order_by(
                "timestamp", direction=firestore.Query.DESCENDING
            ).limit(50).get()
            records = []
            for doc in docs:
                d = doc.to_dict()
                records.append({
                    "grievance_id": d.get("grievance_id"),
                    "type": d.get("type"),
                    "severity": d.get("severity"),
                    "summary": d.get("summary"),
                    "language": d.get("language"),
                    "timestamp": str(d.get("timestamp", ""))
                })
            counts = {}
            for r in records:
                t = r.get("type", "OTHER")
                counts[t] = counts.get(t, 0) + 1
            return jsonify({"success": True, "records": records, "counts": counts, "total": len(records)})
        except Exception as e:
            return jsonify({"success": False, "error": str(e), "records": [], "counts": {}, "total": 0})
    # Demo data when cloud not available
    demo = [
        {"grievance_id": "MM-2026-84921", "type": "HEAT", "severity": "HIGH", "summary": "Heat stroke near Jaisalmer.", "language": "Hindi", "timestamp": "2026-03-20 08:22:00"},
        {"grievance_id": "MM-2026-33201", "type": "WATER", "severity": "HIGH", "summary": "4-day water shortage, 200 people.", "language": "Hindi", "timestamp": "2026-03-20 09:11:00"},
        {"grievance_id": "MM-2026-55431", "type": "MEDICAL", "severity": "HIGH", "summary": "Chest pain, 60yr old woman.", "language": "Mixed", "timestamp": "2026-03-20 10:05:00"},
        {"grievance_id": "MM-2026-11290", "type": "SANDSTORM", "severity": "MEDIUM", "summary": "3 people stranded in sandstorm.", "language": "Hindi", "timestamp": "2026-03-20 11:44:00"},
        {"grievance_id": "MM-2026-66710", "type": "HEAT", "severity": "MEDIUM", "summary": "Worker dehydrated at construction site.", "language": "English", "timestamp": "2026-03-20 12:30:00"},
    ]
    counts = {}
    for r in demo:
        counts[r["type"]] = counts.get(r["type"], 0) + 1
    return jsonify({"success": True, "records": demo, "counts": counts, "total": len(demo)})


# ── PREDICT HEAT RISK API ──
@app.route("/api/predict-risk", methods=["POST"])
def predict_risk():
    data = request.get_json() or {}
    temp = float(data.get("temp", 30))
    humidity = float(data.get("humidity", 50))
    hour = int(data.get("hour", 12))

    # Heat Index calculation
    if temp >= 43:
        level = "CRITICAL"
        msg = f"⚠️ {temp}°C — Heat stroke risk is CRITICAL. Avoid going outside."
        color = "#DC2626"
    elif temp >= 40:
        level = "HIGH"
        msg = f"🔶 {temp}°C — HIGH heat risk. Keep water ready and stay in shade."
        color = "#EA580C"
    elif temp >= 35:
        level = "MODERATE"
        msg = f"🟡 {temp}°C — Moderate heat. Drink water every 30 minutes."
        color = "#D97706"
    else:
        level = "LOW"
        msg = f"✅ {temp}°C — Low heat risk today."
        color = "#16A34A"

    peak_hours = hour >= 10 and hour <= 17
    return jsonify({"level": level, "message": msg, "color": color, "peak_hours": peak_hours})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=False)
