# MaruMitra AI — मारू मित्र

> **Desert Survival Intelligence** — Powered by Google Gemini

MaruMitra AI is a Gemini-powered application designed for desert regions like Rajasthan. It acts as a universal bridge between human intent and complex systems by transforming unstructured inputs (voice, text, messy Hindi/English mix) into structured, life-saving triage analysis.

---

## Features

- 🌵 **Hinglish Understanding** — Reads messy real-world Hindi+English distress calls
- 🎙️ **Voice Input** — Speak your situation (Hindi-first, browser Speech API)
- 🧠 **Gemini-powered Triage** — Structured JSON analysis via Gemini 2.0 Flash
- 🔴 **Risk Level + Urgency** — Immediate / Soon / Safe classification
- 🏜️ **Desert-first context** — Assumes extreme heat, water scarcity, remote access

## Structured Output

For any input, MaruMitra extracts:
1. **User Intent** — What help is actually needed
2. **Situation Type** — heatstroke / dehydration / water shortage / illness / travel risk / other
3. **Key Symptoms / Signals** — Bullet-pointed observations
4. **Risk Level** — Low / Medium / High
5. **Urgency** — Immediate / Soon / Safe

## Running Locally

Requires Python 3.11.

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Run the server
python main.py
```
Open `http://localhost:8080` in your browser.

```
maru-mitra/
├── index.html       ← App frontend + Gemini logic
├── main.py          ← Flask server (10 lines)
├── requirements.txt ← flask==3.0.0
└── Dockerfile       ← Python 3.11 slim container
```

## Tech Stack

- **Frontend**: Single-file HTML/CSS/JS (Vanilla)
- **Backend / Serve**: Python Flask
- **AI Engine**: Google Gemini 1.5 Flash API
- **APIs**: Web Speech API, Open-Meteo API

---

## 🚀 Cloud Run Deployment

If you want to host MaruMitra on [Cloud Run](https://cloud.google.com/run), follow these steps:

### 1. Install Google Cloud CLI
If you don't have it, run this in PowerShell:
```powershell
(New-Object Net.WebClient).DownloadFile("https://dl.google.com/dl/cloudsdk/channels/rapid/GoogleCloudSDKInstaller.exe", "$env:Temp\GoogleCloudSDKInstaller.exe")
& "$env:Temp\GoogleCloudSDKInstaller.exe"
```

### 2. Login & Initialize
```powershell
gcloud auth login
gcloud config set project [YOUR_PROJECT_ID]
```

### 3. Deploy
Run this inside the `maru-mitra` folder:
```powershell
gcloud run deploy maru-mitra --source . --region asia-south1 --allow-unauthenticated
```

---
