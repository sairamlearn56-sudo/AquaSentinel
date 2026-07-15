"""
AI Community Health Early Warning System — Water-Borne Disease Risk Prediction
================================================================================

Run with:
    pip install streamlit plotly pandas numpy twilio firebase-admin
    streamlit run health_early_warning_app.py

WHAT'S NEW IN THIS REDESIGN:
- Full visual redesign: classic serif headings + clean sans body font,
  card-based layout, hover + safe/danger pulse animations
- Sidebar rebuilt as a simple navigation menu (Home / Alerts / Live Data /
  History / Map / Safety / Settings) instead of cramped top tabs
- New Home landing page with a hero section, "why this matters" cards,
  and a "how it works" walkthrough
- Live Data & Risk page now shows a big ANIMATED SAFE state (green, calm)
  when risk is low, and only reveals disease-by-disease AI predictions +
  precautions when risk is actually elevated (animated red danger state)
- Twilio credentials no longer hardcoded in source — read from Streamlit
  Secrets (recommended) with a safe fallback to sidebar input

REQUIRED Streamlit secrets (Settings -> Secrets on Streamlit Cloud):

    [firebase]
    type = "service_account"
    project_id = "water-project-50ce4"
    private_key_id = "..."
    private_key = \"\"\"-----BEGIN PRIVATE KEY-----
    ...
    -----END PRIVATE KEY-----
    \"\"\"
    client_email = "firebase-adminsdk-fbsvc@water-project-50ce4.iam.gserviceaccount.com"
    client_id = "..."
    auth_uri = "https://accounts.google.com/o/oauth2/auth"
    token_uri = "https://oauth2.googleapis.com/token"
    auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"
    client_x509_cert_url = "..."
    universe_domain = "googleapis.com"
    database_url = "https://water-project-50ce4-default-rtdb.firebaseio.com"

    [twilio]
    account_sid = "ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
    auth_token = "your_auth_token"
    from_number = "+1XXXXXXXXXX"

    (Never hardcode these in the .py file — Secrets keeps them out of GitHub.)

EXPECTED ESP32 DATA:
    Live reading  -> /waterData          {tds, turbidity, water_temp, timestamp}
    History log   -> /history/{auto-id}  {tds, turbidity, water_temp, timestamp}
"""

import time
import streamlit as st
from auth import login, logout
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime

# =========================================================
# PAGE CONFIG
# =========================================================
st.set_page_config(
    page_title="AquaSentinel — Community Water Health Monitor",
    page_icon="💧",
    layout="wide",
    initial_sidebar_state="expanded",
)
if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False

if not st.session_state["logged_in"]:
    login()
    st.stop()

logout()
# =========================================================
# STYLING — classic serif headings, clean body font, cards, animations
# =========================================================
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Merriweather:wght@700;900&family=Nunito:wght@400;600;700;800&display=swap');

html, body, [class*="css"] { font-family: 'Nunito', -apple-system, sans-serif !important; }
h1, h2, h3 { font-family: 'Merriweather', Georgia, serif !important; letter-spacing: -0.3px; }
h1 { font-size: 2.2rem !important; }
h2 { font-size: 1.55rem !important; }
h3 { font-size: 1.2rem !important; }

section[data-testid="stSidebar"] {
    background-color: #10151c;
    border-right: 1px solid #232b36;
}
section[data-testid="stSidebar"] .stRadio label { font-size: 1.05rem !important; padding: 5px 0; }
section[data-testid="stSidebar"] h2, section[data-testid="stSidebar"] h3 { font-family:'Nunito', sans-serif !important; }

.stButton > button, .stDownloadButton > button {
    border-radius: 10px !important;
    font-weight: 700 !important;
}

div[data-testid="stMetric"] {
    background: rgba(255,255,255,0.03);
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 12px;
    padding: 10px 14px;
}

.classic-card {
    background: rgba(255,255,255,0.03);
    border: 1px solid rgba(255,255,255,0.09);
    border-radius: 16px;
    padding: 22px 26px;
    margin-bottom: 16px;
    transition: transform 0.2s ease, box-shadow 0.2s ease;
}
.classic-card:hover { transform: translateY(-3px); box-shadow: 0 10px 24px rgba(0,0,0,0.25); }

.hero-wrap { padding: 10px 0 6px 0; }
.hero-title { font-family:'Merriweather', serif; font-size: 2.6rem; font-weight: 900; line-height: 1.15; margin-bottom: 8px; }
.hero-sub { font-size: 1.15rem; opacity: 0.85; margin-bottom: 22px; max-width: 720px; }

.step-num {
    display:inline-flex; align-items:center; justify-content:center;
    width:36px; height:36px; border-radius:50%;
    background:#3498db; color:white; font-weight:800;
    margin-right:12px; flex-shrink:0;
}

@keyframes pulseGreen {
  0%   { box-shadow: 0 0 0 0 rgba(46,204,113,0.55); }
  70%  { box-shadow: 0 0 0 28px rgba(46,204,113,0); }
  100% { box-shadow: 0 0 0 0 rgba(46,204,113,0); }
}
@keyframes pulseRed {
  0%   { box-shadow: 0 0 0 0 rgba(231,76,60,0.6); }
  70%  { box-shadow: 0 0 0 32px rgba(231,76,60,0); }
  100% { box-shadow: 0 0 0 0 rgba(231,76,60,0); }
}
@keyframes pulseYellow {
  0%   { box-shadow: 0 0 0 0 rgba(241,196,15,0.55); }
  70%  { box-shadow: 0 0 0 24px rgba(241,196,15,0); }
  100% { box-shadow: 0 0 0 0 rgba(241,196,15,0); }
}
.safe-card {
    animation: pulseGreen 2.2s infinite;
    background: rgba(46,204,113,0.07);
    border: 2px solid #2ecc71;
    border-radius: 22px;
    padding: 36px 24px;
    text-align: center;
    margin: 10px 0 24px 0;
}
.caution-card {
    animation: pulseYellow 2s infinite;
    background: rgba(241,196,15,0.08);
    border: 2px solid #f1c40f;
    border-radius: 22px;
    padding: 30px 24px;
    text-align: center;
    margin: 10px 0 24px 0;
}
.danger-card {
    animation: pulseRed 1.5s infinite;
    background: rgba(231,76,60,0.10);
    border: 2px solid #e74c3c;
    border-radius: 22px;
    padding: 30px 24px;
    text-align: center;
    margin: 10px 0 24px 0;
}
.big-emoji { font-size: 3.4rem; margin-bottom: 6px; }
.safe-title { font-family:'Merriweather', serif; font-size: 1.7rem; font-weight:900; color:#2ecc71; }
.caution-title { font-family:'Merriweather', serif; font-size: 1.7rem; font-weight:900; color:#f1c40f; }
.danger-title { font-family:'Merriweather', serif; font-size: 1.7rem; font-weight:900; color:#e74c3c; }
</style>
""", unsafe_allow_html=True)

# =========================================================
# FIREBASE SETUP (real ESP32 live data source)
# =========================================================
FIREBASE_AVAILABLE = False
FIREBASE_INIT_ERROR = None

try:
    import firebase_admin
    from firebase_admin import credentials, db

    @st.cache_resource(show_spinner=False)
    def init_firebase():
        try:
            if "firebase" not in st.secrets:
                return None, "No [firebase] section found in Streamlit secrets."
            cred_dict = dict(st.secrets["firebase"])
            database_url = cred_dict.pop("database_url", None)
            if not database_url:
                return None, "Missing 'database_url' in [firebase] secrets."
            if not firebase_admin._apps:
                cred = credentials.Certificate(cred_dict)
                firebase_admin.initialize_app(cred, {"databaseURL": database_url})
            return db, None
        except Exception as e:
            return None, str(e)

    _db_module, FIREBASE_INIT_ERROR = init_firebase()
    FIREBASE_AVAILABLE = _db_module is not None
except ImportError:
    FIREBASE_INIT_ERROR = "firebase-admin not installed. Run: pip install firebase-admin"


def fetch_live_reading(zone_key: str):
    """Reads the latest ESP32 reading from /waterData (shared across zones for now)."""
    if not FIREBASE_AVAILABLE:
        return None, FIREBASE_INIT_ERROR
    try:
        ref = db.reference("/waterData")
        data = ref.get()
        if not data:
            return None, "No data found at /waterData yet."
        reading = {
            "water_temp_c": float(data.get("water_temp", 28.0)),
            "ph": float(data.get("ph", 7.0)),
            "turbidity": float(data.get("turbidity", 5.0)),
            "tds": float(data.get("tds", 450.0)),
            "rainfall": float(data.get("rainfall", 0.0)),
            "bacteria": float(data.get("bacteria", 150.0)),
            "humidity": float(data.get("humidity", 70.0)),
            "ambient_temp_c": float(data.get("ambient_temp_c", 31.0)),
            "timestamp": data.get("timestamp"),
        }
        return reading, None
    except Exception as e:
        return None, str(e)


def fetch_real_historical_data(max_records=2000):
    """Reads real logged sensor history from Firebase at /history (POSTed by ESP32)."""
    if not FIREBASE_AVAILABLE:
        return None
    try:
        ref = db.reference("/history")
        data = ref.order_by_key().limit_to_last(max_records).get()
        if not data:
            return None
        rows = []
        for key, entry in data.items():
            if not isinstance(entry, dict):
                continue
            ts = entry.get("timestamp")
            if ts is None:
                continue
            rows.append({
                "datetime": pd.to_datetime(ts, unit="s"),
                "bacteria": float(entry.get("bacteria", np.nan)),
                "turbidity": float(entry.get("turbidity", np.nan)),
                "ph": float(entry.get("ph", np.nan)),
                "rainfall": float(entry.get("rainfall", np.nan)),
                "water_temp_c": float(entry.get("water_temp", entry.get("water_temp_c", np.nan))),
                "ambient_temp_c": float(entry.get("ambient_temp_c", np.nan)),
                "tds": float(entry.get("tds", np.nan)),
            })
        if not rows:
            return None
        df = pd.DataFrame(rows).sort_values("datetime").reset_index(drop=True)
        bact_risk = np.clip(df["bacteria"].fillna(0) / 4, 0, 100)
        turb_risk = np.clip(df["turbidity"].fillna(0) * 4, 0, 100)
        rain_risk = np.clip(df["rainfall"].fillna(0) * 3, 0, 100)
        df["overall_risk"] = np.clip(0.4 * bact_risk + 0.3 * turb_risk + 0.3 * rain_risk, 0, 100)
        return df
    except Exception:
        return None


# =========================================================
# SMS (Twilio) — credentials come from Secrets, NEVER hardcoded
# =========================================================
ALERT_PHONE_NUMBER = "+919032644552"


def get_twilio_credentials():
    """Reads Twilio credentials from Streamlit secrets if present."""
    if "twilio" in st.secrets:
        t = st.secrets["twilio"]
        return t.get("account_sid", ""), t.get("auth_token", ""), t.get("from_number", "")
    return (
        st.session_state.get("twilio_sid", ""),
        st.session_state.get("twilio_token", ""),
        st.session_state.get("twilio_from", ""),
    )


def send_sms_alert(message: str, account_sid: str, auth_token: str, from_number: str):
    """Send an SMS alert using Twilio. Returns (success, status_message)."""
    try:
        from twilio.rest import Client
        client = Client(account_sid, auth_token)
        msg = client.messages.create(body=message, from_=from_number, to=ALERT_PHONE_NUMBER)
        return True, f"SMS sent! SID: {msg.sid}"
    except ImportError:
        return False, "Twilio not installed. Run: pip install twilio"
    except Exception as e:
        return False, f"SMS failed: {str(e)}"


def build_sms_message(zone, overall_risk, alerted_diseases, sensors):
    risk_label, _ = get_risk_label(overall_risk)
    disease_list = ", ".join([f"{d} ({s:.0f}/100)" for d, s in alerted_diseases.items()])
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    return (
        f"[HEALTH ALERT] {timestamp}\nZone: {zone}\n"
        f"Overall Risk: {overall_risk:.1f}/100 - {risk_label}\n"
        f"Elevated diseases: {disease_list}\n"
        f"Water pH: {sensors['ph']:.2f} | Bacteria: {sensors['bacteria']:.0f} CFU/mL | "
        f"Rainfall: {sensors['rainfall']:.1f}mm\n"
        f"ACTION REQUIRED: Increase water disinfection & issue boil-water advisory."
    )


# =========================================================
# TRANSLATIONS
# =========================================================
TRANSLATIONS = {
    "English": {
        "nav_home": "🏠 Home", "nav_alerts": "🚨 Alerts & SMS", "nav_live": "📡 Live Data & Risk",
        "nav_trends": "📈 History & Events", "nav_map": "🗺️ Zone Map", "nav_safety": "🛡️ Safety Guide",
        "nav_insights": "🔍 Key Insights", "nav_settings": "⚙️ Settings",
        "title": "AquaSentinel — AI Community Health Early Warning System",
        "subtitle": "Real-Time Water-Borne Disease Risk Prediction",
        "hero_tag": "Clean water, caught before it becomes a crisis.",
        "hero_sub": "AquaSentinel watches your village's water quality every second — using live IoT sensors and AI — so outbreaks of cholera, typhoid, and other water-borne diseases can be stopped before they start.",
        "hero_cta": "View Live Data →",
        "why_title": "Why this matters",
        "why_1_title": "Water-borne disease spreads fast",
        "why_1_body": "Contaminated water can silently sicken an entire village within days — often before anyone notices anything is wrong.",
        "why_2_title": "Early warning saves lives",
        "why_2_body": "Detecting contamination hours or days earlier gives health workers time to act before people get sick.",
        "why_3_title": "Built for every community",
        "why_3_body": "Simple language, clear color-coded alerts, and SMS notifications — designed to be understood by everyone, not just engineers.",
        "how_title": "How it works",
        "how_1": "Sensors placed in local water sources continuously measure temperature, turbidity, TDS and more.",
        "how_2": "Readings travel over WiFi to a secure cloud database in real time.",
        "how_3": "AI analyzes the readings and predicts outbreak risk for 5 major water-borne diseases.",
        "how_4": "If risk is high, the system alerts health workers instantly by SMS — and shows villagers simple safety steps.",
        "language": "Language", "temp_unit": "Temperature Unit", "select_zone": "Select Zone / Village",
        "live_sensors": "Live Sensor Readings", "risk_prediction": "Disease Risk Prediction",
        "alerts": "Active Alerts", "trends": "Historical Trends", "map_view": "Zone Risk Map",
        "water_temp": "Water Temperature", "ph_level": "pH Level", "turbidity": "Turbidity (NTU)",
        "tds": "TDS (ppm)", "rainfall": "Rainfall (mm)", "bacteria": "Bacterial Count (CFU/mL)",
        "humidity": "Humidity (%)", "ambient_temp": "Ambient Temperature",
        "low_risk": "Low Risk", "moderate_risk": "Moderate Risk", "high_risk": "High Risk", "critical_risk": "Critical Risk",
        "overall_risk": "Overall Outbreak Risk Score", "disease_breakdown": "Disease-wise Risk Breakdown",
        "no_alerts": "✅ No active alerts. Conditions normal.", "alert_msg": "⚠️ ALERT: Elevated risk detected for",
        "recommendation": "Recommended Actions",
        "rec_1": "Increase water chlorination and disinfection frequency",
        "rec_2": "Distribute oral rehydration salts (ORS) to community health centers",
        "rec_3": "Issue public advisory: boil water before consumption",
        "rec_4": "Deploy health workers for door-to-door screening",
        "rec_5": "Increase surveillance and sample testing frequency",
        "last_updated": "Last updated", "refresh": "🔄 Refresh Data", "auto_refresh": "Auto-refresh every 10s",
        "footer": "AI-driven prototype for early warning of water-borne diseases (cholera, typhoid, diarrhea, dysentery, hepatitis A). For demonstration purposes only.",
        "diseases": ["Cholera", "Typhoid", "Diarrhea", "Dysentery", "Hepatitis A"],
        "param_trend": "Select Parameter for Trend", "risk_level": "Risk Level", "zone": "Zone", "population": "Population",
        "key_insights": "Key Insights",
        "insight_1": "rising trend detected over the last 24 hours",
        "insight_2": "Bacterial contamination levels are within safe limits",
        "insight_3": "Heavy rainfall increases contamination risk significantly",
        "sms_settings": "📱 SMS Alert Settings", "twilio_sid": "Twilio Account SID", "twilio_token": "Twilio Auth Token",
        "twilio_from": "Twilio Phone Number (from)", "send_sms": "📲 Send SMS Alert Now",
        "sms_target": "Alert SMS Target", "sms_threshold": "SMS Alert Threshold (Risk Score)",
        "sms_auto": "Auto-send SMS when risk exceeds threshold", "sms_preview": "SMS Preview",
        "safe_title": "Water Quality is Safe", "safe_body": "All monitored readings are within safe limits right now. No unusual disease risk detected.",
        "caution_title": "Moderate Risk — Stay Alert", "danger_title": "High Risk Detected — Take Precautions",
    },
    "हिन्दी (Hindi)": {
        "nav_home": "🏠 होम", "nav_alerts": "🚨 अलर्ट व SMS", "nav_live": "📡 लाइव डेटा व जोखिम",
        "nav_trends": "📈 इतिहास व घटनाएं", "nav_map": "🗺️ क्षेत्र मानचित्र", "nav_safety": "🛡️ सुरक्षा गाइड",
        "nav_insights": "🔍 मुख्य जानकारी", "nav_settings": "⚙️ सेटिंग्स",
        "title": "एक्वासेंटिनल — एआई सामुदायिक स्वास्थ्य पूर्व चेतावनी प्रणाली",
        "subtitle": "जल-जनित रोगों के जोखिम की वास्तविक समय भविष्यवाणी",
        "hero_tag": "साफ पानी, संकट बनने से पहले ही पकड़ा गया।",
        "hero_sub": "एक्वासेंटिनल आपके गांव के पानी की गुणवत्ता को हर सेकंड लाइव सेंसर और एआई से जांचता है — ताकि हैजा, टाइफाइड जैसी बीमारियां फैलने से पहले ही रोकी जा सकें।",
        "hero_cta": "लाइव डेटा देखें →",
        "why_title": "यह क्यों ज़रूरी है",
        "why_1_title": "जल-जनित रोग तेज़ी से फैलते हैं",
        "why_1_body": "दूषित पानी कुछ ही दिनों में पूरे गांव को बीमार कर सकता है — अक्सर किसी को पता चलने से पहले।",
        "why_2_title": "जल्दी चेतावनी जान बचाती है",
        "why_2_body": "घंटों या दिनों पहले संदूषण का पता चलने से स्वास्थ्य कर्मियों को कार्रवाई का समय मिलता है।",
        "why_3_title": "हर समुदाय के लिए बनाया गया",
        "why_3_body": "सरल भाषा, स्पष्ट रंग-कोडित चेतावनियां, और SMS सूचनाएं — सभी के लिए समझने योग्य।",
        "how_title": "यह कैसे काम करता है",
        "how_1": "स्थानीय जल स्रोतों में लगे सेंसर लगातार तापमान, टर्बिडिटी, TDS आदि मापते हैं।",
        "how_2": "रीडिंग वास्तविक समय में वाईफाई के माध्यम से सुरक्षित क्लाउड डेटाबेस तक जाती हैं।",
        "how_3": "एआई रीडिंग का विश्लेषण करता है और 5 प्रमुख जल-जनित रोगों के प्रकोप जोखिम की भविष्यवाणी करता है।",
        "how_4": "अगर जोखिम अधिक है, तो सिस्टम तुरंत SMS द्वारा स्वास्थ्य कर्मियों को सूचित करता है।",
        "language": "भाषा", "temp_unit": "तापमान इकाई", "select_zone": "क्षेत्र / गांव चुनें",
        "live_sensors": "लाइव सेंसर रीडिंग", "risk_prediction": "रोग जोखिम भविष्यवाणी",
        "alerts": "सक्रिय चेतावनियाँ", "trends": "ऐतिहासिक रुझान", "map_view": "क्षेत्र जोखिम मानचित्र",
        "water_temp": "जल तापमान", "ph_level": "पीएच स्तर", "turbidity": "टर्बिडिटी (NTU)",
        "tds": "टीडीएस (ppm)", "rainfall": "वर्षा (मिमी)", "bacteria": "बैक्टीरिया गणना (CFU/mL)",
        "humidity": "आर्द्रता (%)", "ambient_temp": "वातावरणीय तापमान",
        "low_risk": "कम जोखिम", "moderate_risk": "मध्यम जोखिम", "high_risk": "उच्च जोखिम", "critical_risk": "गंभीर जोखिम",
        "overall_risk": "समग्र प्रकोप जोखिम स्कोर", "disease_breakdown": "रोग-वार जोखिम विवरण",
        "no_alerts": "✅ कोई सक्रिय चेतावनी नहीं। स्थिति सामान्य है।", "alert_msg": "⚠️ चेतावनी: इसके लिए बढ़ा हुआ जोखिम पाया गया",
        "recommendation": "अनुशंसित कार्रवाई",
        "rec_1": "जल क्लोरीनीकरण और कीटाणुशोधन की आवृत्ति बढ़ाएं",
        "rec_2": "सामुदायिक स्वास्थ्य केंद्रों में ओआरएस वितरित करें",
        "rec_3": "सार्वजनिक सलाह जारी करें: पानी उबालकर पिएं",
        "rec_4": "घर-घर जांच के लिए स्वास्थ्य कर्मियों को तैनात करें",
        "rec_5": "निगरानी और नमूना परीक्षण की आवृत्ति बढ़ाएं",
        "last_updated": "अंतिम अद्यतन", "refresh": "🔄 डेटा रीफ्रेश करें", "auto_refresh": "हर 10 सेकंड में ऑटो-रीफ्रेश करें",
        "footer": "जल-जनित रोगों की पूर्व चेतावनी के लिए एआई-संचालित प्रोटोटाइप। केवल प्रदर्शन उद्देश्यों के लिए।",
        "diseases": ["हैजा", "टाइफाइड", "दस्त", "पेचिश", "हेपेटाइटिस ए"],
        "param_trend": "रुझान के लिए पैरामीटर चुनें", "risk_level": "जोखिम स्तर", "zone": "क्षेत्र", "population": "जनसंख्या",
        "key_insights": "मुख्य अंतर्दृष्टि",
        "insight_1": "पिछले 24 घंटों में बढ़ता रुझान देखा गया",
        "insight_2": "बैक्टीरिया संदूषण स्तर सुरक्षित सीमा के भीतर है",
        "insight_3": "भारी वर्षा संदूषण जोखिम को काफी बढ़ा देती है",
        "sms_settings": "📱 एसएमएस अलर्ट सेटिंग्स", "twilio_sid": "Twilio अकाउंट SID", "twilio_token": "Twilio Auth Token",
        "twilio_from": "Twilio फ़ोन नंबर (से)", "send_sms": "📲 एसएमएस अलर्ट भेजें",
        "sms_target": "अलर्ट एसएमएस लक्ष्य", "sms_threshold": "एसएमएस अलर्ट थ्रेशोल्ड (जोखिम स्कोर)",
        "sms_auto": "थ्रेशोल्ड पार होने पर ऑटो एसएमएस भेजें", "sms_preview": "एसएमएस प्रीव्यू",
        "safe_title": "पानी की गुणवत्ता सुरक्षित है", "safe_body": "सभी निगरानी की गई रीडिंग अभी सुरक्षित सीमा में हैं। कोई असामान्य रोग जोखिम नहीं पाया गया।",
        "caution_title": "मध्यम जोखिम — सतर्क रहें", "danger_title": "उच्च जोखिम — सावधानी बरतें",
    },
    "తెలుగు (Telugu)": {
        "nav_home": "🏠 హోమ్", "nav_alerts": "🚨 హెచ్చరికలు & SMS", "nav_live": "📡 లైవ్ డేటా & ప్రమాదం",
        "nav_trends": "📈 చరిత్ర & సంఘటనలు", "nav_map": "🗺️ జోన్ మ్యాప్", "nav_safety": "🛡️ భద్రతా గైడ్",
        "nav_insights": "🔍 ముఖ్య అంతర్దృష్టులు", "nav_settings": "⚙️ సెట్టింగ్‌లు",
        "title": "అక్వాసెంటినల్ — AI కమ్యూనిటీ హెల్త్ ముందస్తు హెచ్చరిక వ్యవస్థ",
        "subtitle": "నీటి ద్వారా వ్యాపించే వ్యాధుల రియల్-టైమ్ ప్రమాద అంచనా",
        "hero_tag": "శుభ్రమైన నీరు — సంక్షోభంగా మారకముందే గుర్తించబడుతుంది.",
        "hero_sub": "అక్వాసెంటినల్ మీ గ్రామం నీటి నాణ్యతను ప్రతి సెకనూ లైవ్ సెన్సార్లు మరియు AI తో పరిశీలిస్తుంది — కలరా, టైఫాయిడ్ వంటి వ్యాధులు వ్యాప్తి చెందకముందే ఆపడానికి.",
        "hero_cta": "లైవ్ డేటా చూడండి →",
        "why_title": "ఇది ఎందుకు ముఖ్యం",
        "why_1_title": "నీటి ద్వారా వ్యాపించే వ్యాధులు వేగంగా వ్యాపిస్తాయి",
        "why_1_body": "కలుషిత నీరు కొన్ని రోజుల్లోనే మొత్తం గ్రామాన్ని అనారోగ్యానికి గురిచేయవచ్చు — తరచుగా ఎవరూ గమనించకముందే.",
        "why_2_title": "ముందస్తు హెచ్చరిక ప్రాణాలను కాపాడుతుంది",
        "why_2_body": "గంటలు లేదా రోజుల ముందు కాలుష్యాన్ని గుర్తించడం ఆరోగ్య కార్యకర్తలకు చర్య తీసుకోవడానికి సమయం ఇస్తుంది.",
        "why_3_title": "ప్రతి సమాజం కోసం రూపొందించబడింది",
        "why_3_body": "సరళమైన భాష, స్పష్టమైన రంగు-కోడెడ్ హెచ్చరికలు, మరియు SMS నోటిఫికేషన్‌లు — అందరికీ అర్థమయ్యేలా.",
        "how_title": "ఇది ఎలా పనిచేస్తుంది",
        "how_1": "స్థానిక నీటి వనరులలో ఉంచిన సెన్సార్లు నిరంతరం ఉష్ణోగ్రత, టర్బిడిటీ, TDS మొదలైనవి కొలుస్తాయి.",
        "how_2": "రీడింగ్‌లు వైఫై ద్వారా రియల్ టైమ్‌లో సురక్షిత క్లౌడ్ డేటాబేస్‌కు వెళ్తాయి.",
        "how_3": "AI రీడింగ్‌లను విశ్లేషించి 5 ప్రధాన నీటి ద్వారా వ్యాపించే వ్యాధుల ప్రమాదాన్ని అంచనా వేస్తుంది.",
        "how_4": "ప్రమాదం ఎక్కువగా ఉంటే, సిస్టమ్ వెంటనే SMS ద్వారా ఆరోగ్య కార్యకర్తలను హెచ్చరిస్తుంది.",
        "language": "భాష", "temp_unit": "ఉష్ణోగ్రత యూనిట్", "select_zone": "జోన్ / గ్రామం ఎంచుకోండి",
        "live_sensors": "లైవ్ సెన్సార్ రీడింగ్‌లు", "risk_prediction": "వ్యాధి ప్రమాద అంచనా",
        "alerts": "క్రియాశీల హెచ్చరికలు", "trends": "చారిత్రక ధోరణులు", "map_view": "జోన్ ప్రమాద మ్యాప్",
        "water_temp": "నీటి ఉష్ణోగ్రత", "ph_level": "pH స్థాయి", "turbidity": "టర్బిడిటీ (NTU)",
        "tds": "TDS (ppm)", "rainfall": "వర్షపాతం (mm)", "bacteria": "బ్యాక్టీరియా కౌంట్ (CFU/mL)",
        "humidity": "తేమ (%)", "ambient_temp": "పరిసర ఉష్ణోగ్రత",
        "low_risk": "తక్కువ ప్రమాదం", "moderate_risk": "మధ్యస్థ ప్రమాదం", "high_risk": "అధిక ప్రమాదం", "critical_risk": "తీవ్రమైన ప్రమాదం",
        "overall_risk": "మొత్తం వ్యాప్తి ప్రమాద స్కోరు", "disease_breakdown": "వ్యాధి వారీగా ప్రమాద విశ్లేషణ",
        "no_alerts": "✅ క్రియాశీల హెచ్చరికలు లేవు. పరిస్థితులు సాధారణం.", "alert_msg": "⚠️ హెచ్చరిక: దీనికి పెరిగిన ప్రమాదం గుర్తించబడింది",
        "recommendation": "సిఫార్సు చేసిన చర్యలు",
        "rec_1": "నీటి క్లోరినేషన్ మరియు క్రిమిసంహారక ఫ్రీక్వెన్సీని పెంచండి",
        "rec_2": "కమ్యూనిటీ హెల్త్ సెంటర్లకు ORS ను పంపిణీ చేయండి",
        "rec_3": "ప్రజా సూచన జారీ చేయండి: నీటిని మరిగించి తాగండి",
        "rec_4": "ఇంటింటి స్క్రీనింగ్ కోసం ఆరోగ్య కార్యకర్తలను నియమించండి",
        "rec_5": "నిఘా మరియు నమూనా పరీక్ష ఫ్రీక్వెన్సీని పెంచండి",
        "last_updated": "చివరిగా నవీకరించబడింది", "refresh": "🔄 డేటాను రిఫ్రెష్ చేయండి", "auto_refresh": "ప్రతి 10 సెకన్లకు ఆటో-రిఫ్రెష్",
        "footer": "నీటి ద్వారా వ్యాపించే వ్యాధుల ముందస్తు హెచ్చరిక కోసం AI ఆధారిత ప్రోటోటైప్. ప్రదర్శన ప్రయోజనాల కోసం మాత్రమే.",
        "diseases": ["కలరా", "టైఫాయిడ్", "డయేరియా", "డిసెంటరీ", "హెపటైటిస్ A"],
        "param_trend": "ధోరణి కోసం పారామితిని ఎంచుకోండి", "risk_level": "ప్రమాద స్థాయి", "zone": "జోన్", "population": "జనాభా",
        "key_insights": "ముఖ్య అంతర్దృష్టులు",
        "insight_1": "గత 24 గంటల్లో పెరుగుతున్న ధోరణి గుర్తించబడింది",
        "insight_2": "బ్యాక్టీరియా కాలుష్య స్థాయిలు సురక్షిత పరిమితుల్లో ఉన్నాయి",
        "insight_3": "భారీ వర్షపాతం కాలుష్య ప్రమాదాన్ని గణనీయంగా పెంచుతుంది",
        "sms_settings": "📱 SMS హెచ్చరిక సెట్టింగ్‌లు", "twilio_sid": "Twilio అకౌంట్ SID", "twilio_token": "Twilio Auth Token",
        "twilio_from": "Twilio ఫోన్ నంబర్ (నుండి)", "send_sms": "📲 SMS హెచ్చరిక పంపండి",
        "sms_target": "హెచ్చరిక SMS లక్ష్యం", "sms_threshold": "SMS హెచ్చరిక థ్రెషోల్డ్ (ప్రమాద స్కోర్)",
        "sms_auto": "థ్రెషోల్డ్ మించినప్పుడు ఆటో SMS పంపండి", "sms_preview": "SMS ప్రివ్యూ",
        "safe_title": "నీటి నాణ్యత సురక్షితం", "safe_body": "ప్రస్తుతం అన్ని పరిశీలించిన రీడింగ్‌లు సురక్షిత పరిమితుల్లో ఉన్నాయి. అసాధారణ వ్యాధి ప్రమాదం గుర్తించబడలేదు.",
        "caution_title": "మధ్యస్థ ప్రమాదం — అప్రమత్తంగా ఉండండి", "danger_title": "అధిక ప్రమాదం గుర్తించబడింది — జాగ్రత్తలు తీసుకోండి",
    },
    "Español (Spanish)": {
        "nav_home": "🏠 Inicio", "nav_alerts": "🚨 Alertas y SMS", "nav_live": "📡 Datos en Vivo y Riesgo",
        "nav_trends": "📈 Historial y Eventos", "nav_map": "🗺️ Mapa de Zonas", "nav_safety": "🛡️ Guía de Seguridad",
        "nav_insights": "🔍 Puntos Clave", "nav_settings": "⚙️ Configuración",
        "title": "AquaSentinel — Sistema de Alerta Temprana de Salud Comunitaria con IA",
        "subtitle": "Predicción en Tiempo Real del Riesgo de Enfermedades Hídricas",
        "hero_tag": "Agua limpia, detectada antes de convertirse en una crisis.",
        "hero_sub": "AquaSentinel vigila la calidad del agua de tu pueblo cada segundo — con sensores IoT en vivo e IA — para detener brotes de cólera, tifoidea y otras enfermedades hídricas antes de que comiencen.",
        "hero_cta": "Ver Datos en Vivo →",
        "why_title": "Por qué esto importa",
        "why_1_title": "Las enfermedades hídricas se propagan rápido",
        "why_1_body": "El agua contaminada puede enfermar silenciosamente a todo un pueblo en días — a menudo antes de que nadie note algo mal.",
        "why_2_title": "La alerta temprana salva vidas",
        "why_2_body": "Detectar la contaminación horas o días antes da tiempo a los trabajadores de salud para actuar antes de que la gente enferme.",
        "why_3_title": "Diseñado para cada comunidad",
        "why_3_body": "Lenguaje simple, alertas codificadas por color y notificaciones SMS — pensado para que todos lo entiendan.",
        "how_title": "Cómo funciona",
        "how_1": "Sensores en fuentes de agua locales miden continuamente temperatura, turbidez, TDS y más.",
        "how_2": "Las lecturas viajan por WiFi a una base de datos segura en la nube en tiempo real.",
        "how_3": "La IA analiza las lecturas y predice el riesgo de brote para 5 enfermedades hídricas principales.",
        "how_4": "Si el riesgo es alto, el sistema alerta al instante a los trabajadores de salud por SMS.",
        "language": "Idioma", "temp_unit": "Unidad de Temperatura", "select_zone": "Seleccionar Zona / Pueblo",
        "live_sensors": "Lecturas de Sensores en Vivo", "risk_prediction": "Predicción de Riesgo de Enfermedad",
        "alerts": "Alertas Activas", "trends": "Tendencias Históricas", "map_view": "Mapa de Riesgo por Zona",
        "water_temp": "Temperatura del Agua", "ph_level": "Nivel de pH", "turbidity": "Turbidez (NTU)",
        "tds": "TDS (ppm)", "rainfall": "Precipitación (mm)", "bacteria": "Conteo Bacteriano (CFU/mL)",
        "humidity": "Humedad (%)", "ambient_temp": "Temperatura Ambiente",
        "low_risk": "Riesgo Bajo", "moderate_risk": "Riesgo Moderado", "high_risk": "Riesgo Alto", "critical_risk": "Riesgo Crítico",
        "overall_risk": "Puntuación General de Riesgo de Brote", "disease_breakdown": "Desglose de Riesgo por Enfermedad",
        "no_alerts": "✅ No hay alertas activas. Condiciones normales.", "alert_msg": "⚠️ ALERTA: Riesgo elevado detectado para",
        "recommendation": "Acciones Recomendadas",
        "rec_1": "Aumentar la frecuencia de cloración y desinfección del agua",
        "rec_2": "Distribuir sales de rehidratación oral (SRO) a los centros de salud",
        "rec_3": "Emitir aviso público: hervir el agua antes de consumirla",
        "rec_4": "Desplegar trabajadores de salud para evaluación puerta a puerta",
        "rec_5": "Aumentar la vigilancia y la frecuencia de pruebas",
        "last_updated": "Última actualización", "refresh": "🔄 Actualizar Datos", "auto_refresh": "Actualizar automáticamente cada 10s",
        "footer": "Prototipo basado en IA para alerta temprana de enfermedades hídricas. Solo con fines de demostración.",
        "diseases": ["Cólera", "Fiebre Tifoidea", "Diarrea", "Disentería", "Hepatitis A"],
        "param_trend": "Seleccionar Parámetro para Tendencia", "risk_level": "Nivel de Riesgo", "zone": "Zona", "population": "Población",
        "key_insights": "Conclusiones Clave",
        "insight_1": "tendencia al alza detectada en las últimas 24 horas",
        "insight_2": "Los niveles de contaminación bacteriana están dentro de límites seguros",
        "insight_3": "Las lluvias intensas aumentan significativamente el riesgo de contaminación",
        "sms_settings": "📱 Configuración de Alerta SMS", "twilio_sid": "SID de Cuenta Twilio", "twilio_token": "Token de Autenticación Twilio",
        "twilio_from": "Número de Teléfono Twilio (desde)", "send_sms": "📲 Enviar Alerta SMS Ahora",
        "sms_target": "Destino SMS de Alerta", "sms_threshold": "Umbral de Alerta SMS (Puntuación de Riesgo)",
        "sms_auto": "Envío automático de SMS cuando el riesgo supere el umbral", "sms_preview": "Vista Previa del SMS",
        "safe_title": "La Calidad del Agua es Segura", "safe_body": "Todas las lecturas monitoreadas están dentro de límites seguros ahora mismo. No se detectó riesgo inusual de enfermedad.",
        "caution_title": "Riesgo Moderado — Mantente Alerta", "danger_title": "Riesgo Alto Detectado — Toma Precauciones",
    },
    "Français (French)": {
        "nav_home": "🏠 Accueil", "nav_alerts": "🚨 Alertes et SMS", "nav_live": "📡 Données en Direct et Risque",
        "nav_trends": "📈 Historique et Événements", "nav_map": "🗺️ Carte des Zones", "nav_safety": "🛡️ Guide de Sécurité",
        "nav_insights": "🔍 Points Clés", "nav_settings": "⚙️ Paramètres",
        "title": "AquaSentinel — Système d'Alerte Précoce de Santé Communautaire par IA",
        "subtitle": "Prédiction en Temps Réel du Risque de Maladies Hydriques",
        "hero_tag": "Une eau propre, surveillée avant qu'elle ne devienne une crise.",
        "hero_sub": "AquaSentinel surveille la qualité de l'eau de votre village chaque seconde — grâce à des capteurs IoT en direct et à l'IA — pour arrêter les épidémies de choléra, de typhoïde et d'autres maladies hydriques avant qu'elles ne commencent.",
        "hero_cta": "Voir les Données en Direct →",
        "why_title": "Pourquoi c'est important",
        "why_1_title": "Les maladies hydriques se propagent vite",
        "why_1_body": "Une eau contaminée peut rendre tout un village malade en quelques jours — souvent avant que quiconque ne remarque un problème.",
        "why_2_title": "L'alerte précoce sauve des vies",
        "why_2_body": "Détecter la contamination des heures ou des jours plus tôt donne aux agents de santé le temps d'agir.",
        "why_3_title": "Conçu pour chaque communauté",
        "why_3_body": "Langage simple, alertes codées par couleur et notifications SMS — pensé pour être compris par tous.",
        "how_title": "Comment ça marche",
        "how_1": "Des capteurs placés dans les sources d'eau locales mesurent en continu la température, la turbidité, le TDS et plus encore.",
        "how_2": "Les lectures voyagent par WiFi vers une base de données cloud sécurisée en temps réel.",
        "how_3": "L'IA analyse les lectures et prédit le risque d'épidémie pour 5 maladies hydriques majeures.",
        "how_4": "Si le risque est élevé, le système alerte instantanément les agents de santé par SMS.",
        "language": "Langue", "temp_unit": "Unité de Température", "select_zone": "Sélectionner Zone / Village",
        "live_sensors": "Lectures des Capteurs en Direct", "risk_prediction": "Prédiction du Risque de Maladie",
        "alerts": "Alertes Actives", "trends": "Tendances Historiques", "map_view": "Carte des Risques par Zone",
        "water_temp": "Température de l'Eau", "ph_level": "Niveau de pH", "turbidity": "Turbidité (NTU)",
        "tds": "TDS (ppm)", "rainfall": "Précipitations (mm)", "bacteria": "Numération Bactérienne (CFU/mL)",
        "humidity": "Humidité (%)", "ambient_temp": "Température Ambiante",
        "low_risk": "Risque Faible", "moderate_risk": "Risque Modéré", "high_risk": "Risque Élevé", "critical_risk": "Risque Critique",
        "overall_risk": "Score Global de Risque d'Épidémie", "disease_breakdown": "Répartition du Risque par Maladie",
        "no_alerts": "✅ Aucune alerte active. Conditions normales.", "alert_msg": "⚠️ ALERTE : Risque élevé détecté pour",
        "recommendation": "Actions Recommandées",
        "rec_1": "Augmenter la fréquence de chloration et de désinfection de l'eau",
        "rec_2": "Distribuer des sels de réhydratation orale (SRO) aux centres de santé",
        "rec_3": "Émettre un avis public : faire bouillir l'eau avant consommation",
        "rec_4": "Déployer des agents de santé pour le dépistage porte-à-porte",
        "rec_5": "Augmenter la surveillance et la fréquence des tests",
        "last_updated": "Dernière mise à jour", "refresh": "🔄 Actualiser les Données", "auto_refresh": "Actualisation automatique toutes les 10s",
        "footer": "Prototype basé sur l'IA pour l'alerte précoce des maladies hydriques. À des fins de démonstration uniquement.",
        "diseases": ["Choléra", "Typhoïde", "Diarrhée", "Dysenterie", "Hépatite A"],
        "param_trend": "Sélectionner un Paramètre pour la Tendance", "risk_level": "Niveau de Risque", "zone": "Zone", "population": "Population",
        "key_insights": "Points Clés",
        "insight_1": "tendance à la hausse détectée au cours des dernières 24 heures",
        "insight_2": "Les niveaux de contamination bactérienne sont dans les limites sûres",
        "insight_3": "De fortes pluies augmentent considérablement le risque de contamination",
        "sms_settings": "📱 Paramètres d'Alerte SMS", "twilio_sid": "SID de Compte Twilio", "twilio_token": "Jeton d'Authentification Twilio",
        "twilio_from": "Numéro de Téléphone Twilio (depuis)", "send_sms": "📲 Envoyer une Alerte SMS Maintenant",
        "sms_target": "Destinataire SMS d'Alerte", "sms_threshold": "Seuil d'Alerte SMS (Score de Risque)",
        "sms_auto": "Envoi SMS automatique si le risque dépasse le seuil", "sms_preview": "Aperçu du SMS",
        "safe_title": "La Qualité de l'Eau est Sûre", "safe_body": "Toutes les lectures surveillées sont actuellement dans les limites sûres. Aucun risque de maladie inhabituel détecté.",
        "caution_title": "Risque Modéré — Restez Vigilant", "danger_title": "Risque Élevé Détecté — Prenez des Précautions",
    },
}

# =========================================================
# SESSION STATE INIT
# =========================================================
if "language" not in st.session_state: st.session_state.language = "English"
if "temp_unit" not in st.session_state: st.session_state.temp_unit = "Celsius (°C)"
if "seed_offset" not in st.session_state: st.session_state.seed_offset = 0
if "last_sms_sent_score" not in st.session_state: st.session_state.last_sms_sent_score = None
if "sms_log" not in st.session_state: st.session_state.sms_log = []
if "nav_page" not in st.session_state: st.session_state.nav_page = "nav_home"

# =========================================================
# HELPERS
# =========================================================
def c_to_f(c): return c * 9 / 5 + 32

def format_temp(value_c):
    if st.session_state.temp_unit.startswith("Fahrenheit"):
        return f"{c_to_f(value_c):.1f} °F"
    return f"{value_c:.1f} °C"

def get_risk_label(score):
    T = TRANSLATIONS[st.session_state.language]
    if score < 25: return T["low_risk"], "#2ecc71"
    elif score < 50: return T["moderate_risk"], "#f1c40f"
    elif score < 75: return T["high_risk"], "#e67e22"
    else: return T["critical_risk"], "#e74c3c"

def generate_simulated_sensor_data(zone_name, offset=0):
    zone_seed = abs(hash(zone_name)) % 1000
    rng = np.random.default_rng(zone_seed + offset + int(datetime.now().timestamp() // 10))
    return {
        "water_temp_c": rng.normal(28, 3), "ph": rng.normal(7.0, 0.6),
        "turbidity": max(0, rng.normal(8, 5)), "tds": max(0, rng.normal(450, 150)),
        "rainfall": max(0, rng.exponential(8)), "bacteria": max(0, rng.normal(150, 100)),
        "humidity": np.clip(rng.normal(70, 10), 30, 100), "ambient_temp_c": rng.normal(31, 4),
        "timestamp": None,
    }

def get_sensor_data(zone_name, firebase_key, offset=0):
    live_data, err = fetch_live_reading(firebase_key)
    if live_data is not None:
        return live_data, True, None
    return generate_simulated_sensor_data(zone_name, offset), False, err

def compute_disease_risks(sensors):
    ph, turb, bact = sensors["ph"], sensors["turbidity"], sensors["bacteria"]
    rain, wtemp, humidity = sensors["rainfall"], sensors["water_temp_c"], sensors["humidity"]
    ph_risk = np.clip(abs(ph - 7.0) * 25, 0, 100)
    turb_risk = np.clip(turb * 4, 0, 100)
    bact_risk = np.clip(bact / 4, 0, 100)
    rain_risk = np.clip(rain * 3, 0, 100)
    temp_risk = np.clip((wtemp - 25) * 6, 0, 100)
    humidity_risk = np.clip((humidity - 60) * 1.5, 0, 100)
    risks = {
        "Cholera":    0.35*bact_risk + 0.25*rain_risk + 0.2*turb_risk + 0.2*ph_risk,
        "Typhoid":    0.4*bact_risk + 0.3*turb_risk + 0.15*rain_risk + 0.15*temp_risk,
        "Diarrhea":   0.3*bact_risk + 0.25*turb_risk + 0.25*rain_risk + 0.2*humidity_risk,
        "Dysentery":  0.35*bact_risk + 0.3*turb_risk + 0.2*rain_risk + 0.15*ph_risk,
        "Hepatitis A":0.3*bact_risk + 0.3*rain_risk + 0.2*turb_risk + 0.2*temp_risk,
    }
    for k in risks:
        risks[k] = float(np.clip(risks[k] + np.random.normal(0, 3), 0, 100))
    return risks

def generate_historical_data(zone_name, days=14):
    zone_seed = abs(hash(zone_name)) % 1000
    rng = np.random.default_rng(zone_seed)
    dates = pd.date_range(end=datetime.now(), periods=days * 24, freq="h")
    base_bact = np.clip(100 + np.cumsum(rng.normal(2, 8, len(dates))), 0, None)
    base_turb = np.clip(5 + np.cumsum(rng.normal(0.1, 1.5, len(dates))), 0, None)
    base_ph = np.clip(7 + np.cumsum(rng.normal(0, 0.05, len(dates))), 5, 9)
    base_rain = np.clip(rng.exponential(3, len(dates)), 0, None)
    base_wtemp = 28 + 3*np.sin(np.linspace(0, 8*np.pi, len(dates))) + rng.normal(0, 0.5, len(dates))
    base_ambient = 31 + 4*np.sin(np.linspace(0, 8*np.pi, len(dates))) + rng.normal(0, 0.7, len(dates))
    df = pd.DataFrame({
        "datetime": dates, "bacteria": base_bact, "turbidity": base_turb, "ph": base_ph,
        "rainfall": base_rain, "water_temp_c": base_wtemp, "ambient_temp_c": base_ambient,
    })
    df["overall_risk"] = np.clip(0.4*(df["bacteria"]/4) + 0.3*(df["turbidity"]*4) + 0.3*(df["rainfall"]*3), 0, 100)
    return df

def count_contamination_events(df, column="overall_risk", threshold=50):
    if df is None or column not in df.columns or len(df) < 2:
        return 0
    above = df[column].fillna(0) >= threshold
    crossings = above & ~above.shift(1, fill_value=False)
    return int(crossings.sum())

def summarize_zone_history(zone_name, firebase_key, real_hist_df_available):
    if real_hist_df_available is not None and len(real_hist_df_available) >= 2:
        df, is_real = real_hist_df_available, True
    else:
        df, is_real = generate_historical_data(zone_name), False
    return {
        "is_real": is_real,
        "high_events": count_contamination_events(df, "overall_risk", 50),
        "critical_events": count_contamination_events(df, "overall_risk", 75),
        "peak_risk": float(df["overall_risk"].max()) if len(df) else 0.0,
        "span_days": max((df["datetime"].max() - df["datetime"].min()).days if len(df) >= 2 else 0, 1),
        "num_readings": len(df),
    }

# =========================================================
# ZONE CONFIG
# =========================================================
ZONES_DATA = {
    "Zone A - Riverside Village":   {"population": 4200, "lat": 17.385, "lon": 78.486, "firebase_key": "zone_a"},
    "Zone B - Hillside Settlement": {"population": 2800, "lat": 17.405, "lon": 78.466, "firebase_key": "zone_b"},
    "Zone C - Lakeside Town":       {"population": 6100, "lat": 17.365, "lon": 78.506, "firebase_key": "zone_c"},
    "Zone D - Central District":    {"population": 9500, "lat": 17.395, "lon": 78.496, "firebase_key": "zone_d"},
    "Zone E - Floodplain Area":     {"population": 3300, "lat": 17.375, "lon": 78.476, "firebase_key": "zone_e"},
}

# =========================================================
# SAFETY & PRECAUTION CONTENT (English; UI chrome respects language)
# =========================================================
GENERAL_PRECAUTIONS = [
    "Boil drinking water for at least 1 minute, or use certified purification tablets/filters, whenever turbidity or bacterial alerts are active.",
    "Store treated water in clean, covered containers — avoid dipping hands or shared cups directly into storage containers.",
    "Wash hands with soap for at least 20 seconds before eating/cooking and after using the toilet.",
    "Avoid bathing, swimming, or washing utensils directly in flagged high-risk water sources.",
    "Keep drinking water sources away from latrines, drainage, and livestock areas.",
    "Report visibly discolored, foul-smelling, or unusually cloudy water to local health authorities immediately.",
    "During heavy rainfall, treat all open water sources as higher-risk until sensor readings normalize.",
]

DISEASE_SAFETY_INFO = {
    "Cholera": {"icon": "🦠", "symptoms": "Sudden watery diarrhea, vomiting, rapid dehydration.",
        "prevention": "Drink only boiled/treated water; avoid raw or undercooked seafood from affected areas.",
        "seek_help": "Seek medical care immediately if severe watery diarrhea or dehydration signs appear."},
    "Typhoid": {"icon": "🌡️", "symptoms": "Prolonged fever, weakness, stomach pain, headache.",
        "prevention": "Practice good hand hygiene; avoid street food/water of unknown source.",
        "seek_help": "See a doctor if fever persists beyond 2–3 days, especially with stomach pain."},
    "Diarrhea": {"icon": "💧", "symptoms": "Frequent loose stools, cramping, mild fever.",
        "prevention": "Maintain safe drinking water and food hygiene; wash hands regularly.",
        "seek_help": "Use oral rehydration salts (ORS); seek care if symptoms last more than 2 days."},
    "Dysentery": {"icon": "🩸", "symptoms": "Bloody or mucus-mixed diarrhea, abdominal cramps, fever.",
        "prevention": "Avoid contaminated water sources; ensure food is thoroughly cooked and served hot.",
        "seek_help": "Seek medical attention promptly if blood is visible in stool."},
    "Hepatitis A": {"icon": "🫀", "symptoms": "Fatigue, nausea, abdominal pain, jaundice (yellowing of skin/eyes).",
        "prevention": "Vaccination where available; avoid raw shellfish and untreated water.",
        "seek_help": "Consult a doctor if jaundice, dark urine, or persistent fatigue develop."},
}

T = TRANSLATIONS[st.session_state.language]

# =========================================================
# SIDEBAR — brand + quick controls + nav menu
# =========================================================
with st.sidebar:
    st.markdown("## 💧 AquaSentinel")
    st.caption("Community Water Health Monitor")
    st.markdown("---")

    lang = st.selectbox(T["language"], options=list(TRANSLATIONS.keys()),
                         index=list(TRANSLATIONS.keys()).index(st.session_state.language), key="lang_select")
    if lang != st.session_state.language:
        st.session_state.language = lang
        st.rerun()

    selected_zone = st.selectbox(T["select_zone"], options=list(ZONES_DATA.keys()))

    temp_unit = st.radio(T["temp_unit"], options=["Celsius (°C)", "Fahrenheit (°F)"],
                          index=0 if st.session_state.temp_unit.startswith("Celsius") else 1, horizontal=True)
    st.session_state.temp_unit = temp_unit

    st.markdown("---")
    st.markdown("### Menu")
    nav_options = ["nav_home", "nav_alerts", "nav_live", "nav_trends", "nav_map", "nav_safety", "nav_insights", "nav_settings"]
    nav_choice = st.radio(
        "Menu", options=nav_options, format_func=lambda k: T[k],
        index=nav_options.index(st.session_state.nav_page), label_visibility="collapsed",
    )
    st.session_state.nav_page = nav_choice

    st.markdown("---")
    if FIREBASE_AVAILABLE:
        st.success("🟢 Firebase connected")
    else:
        st.error(f"🔴 Firebase not connected")

    auto_refresh = st.checkbox(T["auto_refresh"], value=False)
    if st.button(T["refresh"], use_container_width=True):
        st.session_state.seed_offset += 1
        st.rerun()

# =========================================================
# DATA FETCH
# =========================================================
zone_info = ZONES_DATA[selected_zone]
sensors, is_live, fetch_error = get_sensor_data(selected_zone, zone_info["firebase_key"], st.session_state.seed_offset)
disease_risks = compute_disease_risks(sensors)
overall_risk = float(np.mean(list(disease_risks.values())))
hist_df = generate_historical_data(selected_zone)
alerted = {k: v for k, v in disease_risks.items() if v >= 50}
mild_alerted = {k: v for k, v in disease_risks.items() if v >= 25}
translated_disease_names = dict(zip(["Cholera", "Typhoid", "Diarrhea", "Dysentery", "Hepatitis A"], T["diseases"]))

twilio_sid, twilio_token, twilio_from = get_twilio_credentials()

# risk state used across pages: safe / caution / danger
if overall_risk < 25:
    risk_state = "safe"
elif overall_risk < 50:
    risk_state = "caution"
else:
    risk_state = "danger"

# =========================================================
# AUTO-SMS (fires once per threshold crossing)
# =========================================================
sms_threshold = st.session_state.get("sms_threshold", 50)
sms_auto = st.session_state.get("sms_auto", False)
if sms_auto and overall_risk >= sms_threshold:
    prev = st.session_state.last_sms_sent_score
    if prev is None or prev < sms_threshold:
        if twilio_sid and twilio_token and twilio_from:
            sms_body = build_sms_message(selected_zone, overall_risk, alerted or {"Overall": overall_risk}, sensors)
            ok, status = send_sms_alert(sms_body, twilio_sid, twilio_token, twilio_from)
            st.session_state.last_sms_sent_score = overall_risk
            st.session_state.sms_log.insert(0, {
                "time": datetime.now().strftime("%H:%M:%S"), "zone": selected_zone,
                "score": f"{overall_risk:.1f}", "status": "✅ Sent" if ok else f"❌ {status}",
            })
else:
    if overall_risk < sms_threshold:
        st.session_state.last_sms_sent_score = None

# =========================================================
# TOP HEADER (always visible)
# =========================================================
risk_label, risk_color = get_risk_label(overall_risk)
hc1, hc2, hc3 = st.columns([2, 1, 1])
with hc1:
    st.markdown(f"### 💧 {T['title']}")
    st.caption(T["subtitle"])
with hc2:
    st.metric(T["overall_risk"], f"{overall_risk:.1f} / 100")
with hc3:
    st.markdown(f"""<div style="background-color:{risk_color}22;border:2px solid {risk_color};
        border-radius:12px;padding:12px;text-align:center;font-weight:700;font-size:16px;color:{risk_color};">
        {risk_label}</div>""", unsafe_allow_html=True)
st.markdown("---")

page = st.session_state.nav_page

# =========================================================
# PAGE: HOME
# =========================================================
if page == "nav_home":
    st.markdown(f"""
    <div class="hero-wrap">
        <div class="hero-title">💧 {T['hero_tag']}</div>
        <div class="hero-sub">{T['hero_sub']}</div>
    </div>
    """, unsafe_allow_html=True)

    if st.button(T["hero_cta"], type="primary"):
        st.session_state.nav_page = "nav_live"
        st.rerun()

    st.markdown("### " + T["why_title"])
    wc1, wc2, wc3 = st.columns(3)
    why_cards = [
        ("🦠", T["why_1_title"], T["why_1_body"]),
        ("⏱️", T["why_2_title"], T["why_2_body"]),
        ("🏘️", T["why_3_title"], T["why_3_body"]),
    ]
    for col, (icon, title, body) in zip([wc1, wc2, wc3], why_cards):
        with col:
            st.markdown(f"""<div class="classic-card">
                <div style="font-size:2.2rem;">{icon}</div>
                <h3>{title}</h3>
                <p style="opacity:0.85;">{body}</p>
            </div>""", unsafe_allow_html=True)

    st.markdown("### " + T["how_title"])
    steps = [T["how_1"], T["how_2"], T["how_3"], T["how_4"]]
    for i, step in enumerate(steps, start=1):
        st.markdown(f"""<div class="classic-card" style="display:flex; align-items:center;">
            <span class="step-num">{i}</span><span>{step}</span>
        </div>""", unsafe_allow_html=True)

    st.markdown("### 📊 Right Now")
    qc1, qc2, qc3, qc4 = st.columns(4)
    qc1.metric(T["zone"], selected_zone.split(" - ")[1] if " - " in selected_zone else selected_zone)
    qc2.metric(T["population"], f"{zone_info['population']:,}")
    qc3.metric(T["overall_risk"], f"{overall_risk:.1f}/100")
    qc4.metric("Status", "🟢 Live" if is_live else "⚪ Demo")

# =========================================================
# PAGE: ALERTS & SMS
# =========================================================
elif page == "nav_alerts":
    st.subheader("🚨 " + T["alerts"])
    if not alerted:
        st.success(T["no_alerts"])
    else:
        for disease, score in alerted.items():
            lvl, col = get_risk_label(score)
            st.markdown(f"""<div style="background-color:{col}15;border-left:6px solid {col};
                border-radius:6px;padding:10px 16px;margin-bottom:6px;">
                <b>{T['alert_msg']} {translated_disease_names[disease]}</b> — {T['risk_level']}:
                <span style="color:{col};font-weight:700;">{lvl} ({score:.1f}/100)</span></div>""",
                unsafe_allow_html=True)
        with st.expander("📋 " + T["recommendation"], expanded=True):
            for rec in [T["rec_1"], T["rec_2"], T["rec_3"], T["rec_4"], T["rec_5"]]:
                st.markdown(f"- {rec}")

    with st.expander("📱 " + T["sms_settings"], expanded=bool(alerted)):
        sms_preview_body = build_sms_message(selected_zone, overall_risk, alerted if alerted else {"Overall": overall_risk}, sensors)
        st.markdown(f"**{T['sms_preview']}** → `{ALERT_PHONE_NUMBER}`")
        st.code(sms_preview_body, language=None)
        col_sms1, col_sms2 = st.columns([1, 2])
        with col_sms1:
            send_now = st.button(T["send_sms"], type="primary", use_container_width=True)
        with col_sms2:
            if not (twilio_sid and twilio_token and twilio_from):
                st.warning("⚠️ Add Twilio credentials in ⚙️ Settings to send SMS.")
        if send_now:
            if twilio_sid and twilio_token and twilio_from:
                ok, status = send_sms_alert(sms_preview_body, twilio_sid, twilio_token, twilio_from)
                st.session_state.sms_log.insert(0, {
                    "time": datetime.now().strftime("%H:%M:%S"), "zone": selected_zone,
                    "score": f"{overall_risk:.1f}", "status": "✅ Sent" if ok else f"❌ {status}",
                })
                st.success(f"✅ SMS sent! ({status})") if ok else st.error(f"❌ SMS failed: {status}")
            else:
                st.error("Please add Twilio credentials in ⚙️ Settings first.")
        if st.session_state.sms_log:
            st.markdown("**📋 SMS Activity Log**")
            st.dataframe(pd.DataFrame(st.session_state.sms_log), use_container_width=True, hide_index=True)

# =========================================================
# PAGE: LIVE DATA & RISK  (animated safe / caution / danger states)
# =========================================================
elif page == "nav_live":
    st.subheader("📡 " + T["live_sensors"])
    s1, s2, s3, s4 = st.columns(4)
    s5, s6, s7, s8 = st.columns(4)
    s1.metric(T["water_temp"], format_temp(sensors["water_temp_c"]))
    s2.metric(T["ambient_temp"], format_temp(sensors["ambient_temp_c"]))
    s3.metric(T["ph_level"], f"{sensors['ph']:.2f}")
    s4.metric(T["turbidity"], f"{sensors['turbidity']:.1f}")
    s5.metric(T["tds"], f"{sensors['tds']:.0f}")
    s6.metric(T["rainfall"], f"{sensors['rainfall']:.1f}")
    s7.metric(T["bacteria"], f"{sensors['bacteria']:.0f}")
    s8.metric(T["humidity"], f"{sensors['humidity']:.0f}%")
    st.markdown("---")

    st.subheader("🧬 " + T["risk_prediction"])

    if risk_state == "safe":
        st.markdown(f"""<div class="safe-card">
            <div class="big-emoji">✅</div>
            <div class="safe-title">{T['safe_title']}</div>
            <p style="opacity:0.85; max-width:520px; margin:10px auto 0 auto;">{T['safe_body']}</p>
        </div>""", unsafe_allow_html=True)

    elif risk_state == "caution":
        st.markdown(f"""<div class="caution-card">
            <div class="big-emoji">⚠️</div>
            <div class="caution-title">{T['caution_title']}</div>
            <p style="opacity:0.85; max-width:560px; margin:10px auto 0 auto;">
            Some readings are drifting outside normal range. No confirmed high disease risk yet — keep monitoring.</p>
        </div>""", unsafe_allow_html=True)
        if mild_alerted:
            st.markdown("**Diseases showing early elevated signal:**")
            for d, score in mild_alerted.items():
                st.markdown(f"- {DISEASE_SAFETY_INFO[d]['icon']} **{translated_disease_names[d]}** — {score:.1f}/100")

    else:  # danger
        st.markdown(f"""<div class="danger-card">
            <div class="big-emoji">🚨</div>
            <div class="danger-title">{T['danger_title']}</div>
            <p style="opacity:0.9; max-width:560px; margin:10px auto 0 auto;">
            The AI model has detected elevated outbreak risk. Review the diseases below and follow the precautions immediately.</p>
        </div>""", unsafe_allow_html=True)

        st.markdown("#### 🧠 AI Prediction & Precautions")
        for d, score in sorted(alerted.items(), key=lambda x: -x[1]):
            info = DISEASE_SAFETY_INFO[d]
            lvl, col = get_risk_label(score)
            with st.container():
                st.markdown(f"""<div class="classic-card" style="border-left:6px solid {col};">
                    <h3>{info['icon']} {translated_disease_names[d]} — <span style="color:{col};">{lvl} ({score:.1f}/100)</span></h3>
                    <p><b>🤒 Symptoms:</b> {info['symptoms']}</p>
                    <p><b>🛡️ Prevention:</b> {info['prevention']}</p>
                    <p><b>🏥 Seek help:</b> {info['seek_help']}</p>
                </div>""", unsafe_allow_html=True)

    st.markdown("---")
    col1, col2 = st.columns([1.2, 1])
    with col1:
        st.markdown(f"#### {T['disease_breakdown']}")
        risk_df = pd.DataFrame({
            "Disease": [translated_disease_names[d] for d in disease_risks.keys()],
            "Risk Score": list(disease_risks.values()),
        })
        risk_df["Color"] = risk_df["Risk Score"].apply(lambda x: get_risk_label(x)[1])
        fig_bar = go.Figure(go.Bar(
            x=risk_df["Risk Score"], y=risk_df["Disease"], orientation="h",
            marker_color=risk_df["Color"], text=[f"{v:.1f}" for v in risk_df["Risk Score"]], textposition="outside"))
        fig_bar.update_layout(xaxis=dict(range=[0, 100], title="Risk Score (0-100)"), height=300, margin=dict(l=10, r=10, t=10, b=10))
        st.plotly_chart(fig_bar, use_container_width=True)
    with col2:
        st.markdown(f"#### {T['overall_risk']}")
        fig_gauge = go.Figure(go.Indicator(mode="gauge+number", value=overall_risk,
            gauge={"axis": {"range": [0, 100]}, "bar": {"color": risk_color},
                "steps": [{"range": [0, 25], "color": "rgba(46,204,113,0.3)"},
                          {"range": [25, 50], "color": "rgba(241,196,15,0.3)"},
                          {"range": [50, 75], "color": "rgba(230,126,34,0.3)"},
                          {"range": [75, 100], "color": "rgba(231,76,60,0.3)"}]},
            number={"suffix": " / 100"}))
        fig_gauge.update_layout(height=300, margin=dict(l=10, r=10, t=30, b=10))
        st.plotly_chart(fig_gauge, use_container_width=True)

# =========================================================
# PAGE: HISTORY & EVENTS
# =========================================================
elif page == "nav_trends":
    st.subheader("📈 " + T["trends"])
    real_hist_df = fetch_real_historical_data()
    if real_hist_df is not None and len(real_hist_df) >= 2:
        st.success(f"🟢 Showing REAL logged history from ESP32 ({len(real_hist_df)} readings)")
        hist_df = real_hist_df
    else:
        st.warning("⚠️ No real logged history yet — showing SIMULATED trend data instead.")

    tab_trend, tab_events = st.tabs(["📊 Trend Chart", "📋 Contamination Events Log"])
    with tab_trend:
        param_options = {T["bacteria"]: "bacteria", T["turbidity"]: "turbidity", T["ph_level"]: "ph",
                          T["rainfall"]: "rainfall", T["water_temp"]: "water_temp_c",
                          T["ambient_temp"]: "ambient_temp_c", T["overall_risk"]: "overall_risk"}
        selected_param_label = st.selectbox(T["param_trend"], options=list(param_options.keys()))
        selected_param = param_options[selected_param_label]
        plot_df = hist_df.copy()
        if selected_param in ["water_temp_c", "ambient_temp_c"] and st.session_state.temp_unit.startswith("Fahrenheit"):
            plot_df[selected_param] = c_to_f(plot_df[selected_param])
            y_title = selected_param_label.replace("°C", "°F")
        else:
            y_title = selected_param_label
        fig_line = px.line(plot_df, x="datetime", y=selected_param, labels={"datetime": "", selected_param: y_title})
        fig_line.update_traces(line_color="#3498db")
        fig_line.update_layout(height=350, margin=dict(l=10, r=10, t=10, b=10))
        if selected_param == "overall_risk":
            fig_line.add_hline(y=50, line_dash="dash", line_color="orange", annotation_text=T["high_risk"])
            fig_line.add_hline(y=75, line_dash="dash", line_color="red", annotation_text=T["critical_risk"])
        st.plotly_chart(fig_line, use_container_width=True)
    with tab_events:
        st.markdown("Counts **distinct contamination events** (crossings into High/Critical), not every elevated reading.")
        high_events = count_contamination_events(hist_df, "overall_risk", 50)
        critical_events = count_contamination_events(hist_df, "overall_risk", 75)
        span_days = max((hist_df["datetime"].max() - hist_df["datetime"].min()).days, 1) if len(hist_df) >= 2 else 1
        peak_risk = float(hist_df["overall_risk"].max()) if len(hist_df) else 0.0
        ec1, ec2, ec3, ec4 = st.columns(4)
        ec1.metric("⚠️ High-Risk Events", high_events)
        ec2.metric("🔴 Critical-Risk Events", critical_events)
        ec3.metric("📈 Peak Risk Recorded", f"{peak_risk:.1f} / 100")
        ec4.metric("🗓️ Period Covered", f"{span_days} day(s)")

# =========================================================
# PAGE: ZONE MAP
# =========================================================
elif page == "nav_map":
    st.subheader("🗺️ " + T["map_view"])
    map_rows = []
    for zname, zinfo in ZONES_DATA.items():
        zsensors, z_is_live, _ = get_sensor_data(zname, zinfo["firebase_key"], st.session_state.seed_offset)
        zrisks = compute_disease_risks(zsensors)
        zoverall = float(np.mean(list(zrisks.values())))
        lvl, col = get_risk_label(zoverall)
        map_rows.append({"Zone": zname.split(" - ")[1] if " - " in zname else zname, "lat": zinfo["lat"], "lon": zinfo["lon"],
                          "Risk Score": zoverall, "Risk Level": lvl, "Population": zinfo["population"], "Live": "🟢" if z_is_live else "⚪"})
    map_df = pd.DataFrame(map_rows)
    fig_map = px.scatter_mapbox(map_df, lat="lat", lon="lon", size="Risk Score", color="Risk Score",
        color_continuous_scale=["#2ecc71", "#f1c40f", "#e67e22", "#e74c3c"], range_color=[0, 100],
        size_max=35, zoom=11, hover_name="Zone",
        hover_data={"lat": False, "lon": False, "Risk Score": ":.1f", "Population": True, "Risk Level": True, "Live": True})
    fig_map.update_layout(mapbox_style="open-street-map", margin=dict(l=0, r=0, t=0, b=0), height=420)
    st.plotly_chart(fig_map, use_container_width=True)
    st.dataframe(map_df.rename(columns={"Zone": T["zone"], "Population": T["population"],
        "Risk Score": T["overall_risk"], "Risk Level": T["risk_level"], "Live": "Live ESP32?"}),
        use_container_width=True, hide_index=True)

    st.markdown("#### 🔍 Zone Deep-Dive")
    detail_zone = st.selectbox("Select an area", options=list(ZONES_DATA.keys()),
                                index=list(ZONES_DATA.keys()).index(selected_zone), key="map_detail_zone")
    detail_info = ZONES_DATA[detail_zone]
    detail_sensors, detail_is_live, _ = get_sensor_data(detail_zone, detail_info["firebase_key"], st.session_state.seed_offset)
    detail_risks = compute_disease_risks(detail_sensors)
    detail_overall = float(np.mean(list(detail_risks.values())))
    real_hist_for_summary = fetch_real_historical_data()
    detail_summary = summarize_zone_history(detail_zone, detail_info["firebase_key"],
        real_hist_for_summary if real_hist_for_summary is not None and len(real_hist_for_summary) >= 2 else None)
    dd1, dd2 = st.columns(2)
    with dd1:
        st.markdown(f"**📍 {detail_zone} — Now**")
        st.success("🟢 Live") if detail_is_live else st.warning("⚪ Simulated")
        st.metric("Risk", f"{detail_overall:.1f}/100")
    with dd2:
        st.markdown(f"**🕓 Past {detail_summary['span_days']} Day(s)**")
        de1, de2 = st.columns(2)
        de1.metric("High-Risk Events", f"{detail_summary['high_events']}x")
        de2.metric("Critical Events", f"{detail_summary['critical_events']}x")

# =========================================================
# PAGE: SAFETY GUIDE
# =========================================================
elif page == "nav_safety":
    st.subheader("🛡️ Safety & Precautions Guide")
    st.caption("General public-health guidance — not a substitute for medical advice.")
    safety_tab_general, safety_tab_disease = st.tabs(["✅ General Precautions", "🧬 Disease-Specific Guidance"])
    with safety_tab_general:
        for tip in GENERAL_PRECAUTIONS:
            st.markdown(f"- {tip}")
    with safety_tab_disease:
        disease_tabs = st.tabs([f"{DISEASE_SAFETY_INFO[d]['icon']} {translated_disease_names[d]}" for d in disease_risks.keys()])
        for tab_obj, d in zip(disease_tabs, disease_risks.keys()):
            info = DISEASE_SAFETY_INFO[d]
            with tab_obj:
                st.markdown(f"**🤒 Symptoms:** {info['symptoms']}")
                st.markdown(f"**🛡️ Prevention:** {info['prevention']}")
                st.markdown(f"**🏥 Seek help:** {info['seek_help']}")

# =========================================================
# PAGE: KEY INSIGHTS
# =========================================================
elif page == "nav_insights":
    st.subheader("🔍 " + T["key_insights"])
    insight_cols = st.columns(3)
    if len(hist_df) >= 48:
        recent_risk_change = hist_df["overall_risk"].iloc[-24:].mean() - hist_df["overall_risk"].iloc[-48:-24].mean()
    else:
        recent_risk_change = 0.0
    with insight_cols[0]:
        st.info(f"{'📈' if recent_risk_change > 0 else '📉'} {T['insight_1']} ({recent_risk_change:+.1f} pts)")
    with insight_cols[1]:
        st.success(f"🦠 {T['insight_2']}") if sensors["bacteria"] < 200 else st.warning(f"🦠 {T['bacteria']}: {sensors['bacteria']:.0f}")
    with insight_cols[2]:
        st.warning(f"🌧️ {T['insight_3']}") if sensors["rainfall"] > 10 else st.info(f"🌧️ {T['rainfall']}: {sensors['rainfall']:.1f}mm")
    st.markdown("---")
    st.caption(T["footer"])

# =========================================================
# PAGE: SETTINGS (SMS credentials + thresholds — kept out of the sidebar)
# =========================================================
elif page == "nav_settings":
    st.subheader("⚙️ Settings")
    st.markdown("#### " + T["sms_settings"])
    st.markdown(f"**{T['sms_target']}:** `{ALERT_PHONE_NUMBER}`")

    if "twilio" in st.secrets:
        st.success("✅ Twilio credentials loaded from Streamlit Secrets (recommended).")
    else:
        st.info("No Twilio secrets found — enter credentials below for this session only (not saved).")
        st.session_state["twilio_sid"] = st.text_input(T["twilio_sid"], value=st.session_state.get("twilio_sid", ""), type="password")
        st.session_state["twilio_token"] = st.text_input(T["twilio_token"], value=st.session_state.get("twilio_token", ""), type="password")
        st.session_state["twilio_from"] = st.text_input(T["twilio_from"], value=st.session_state.get("twilio_from", ""))

    st.session_state["sms_threshold"] = st.slider(T["sms_threshold"], min_value=10, max_value=90,
                                                    value=st.session_state.get("sms_threshold", 50), step=5)
    st.session_state["sms_auto"] = st.checkbox(T["sms_auto"], value=st.session_state.get("sms_auto", False))
    st.markdown("---")
    st.caption(T["footer"])

# =========================================================
# AUTO REFRESH
# =========================================================
if auto_refresh:
    time.sleep(10)
    st.session_state.seed_offset += 1
    st.rerun()
