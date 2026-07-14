"""
Jal Suraksha — AI Community Health Early Warning System
for Water-Borne Disease Prediction
==============================================================

Run with:
    pip install streamlit streamlit-option-menu plotly pandas numpy twilio firebase-admin
    streamlit run health_early_warning_app.py

WHAT CHANGED IN THIS REDESIGN
------------------------------
- Brand new visual identity: warm "marigold + deep teal" palette instead of a
  generic dashboard look, classic serif headlines (Fraunces / Noto Serif)
  paired with a very readable body face (Nunito / Noto Sans) that also
  renders Hindi & Telugu correctly.
- Left sidebar is now a clean icon navigation menu (Home, Live Dashboard,
  Trends, Zone Map, Safety Guide, Alerts) instead of a wall of controls.
  Settings (language, units, zone, Firebase/Twilio) live in a single
  collapsible "Settings" panel at the bottom of the sidebar so villagers
  aren't confronted with technical fields up front.
- New Home page: a hook/hero, a plain-language "how this works" walk-through,
  and illustrated disease cards — so a first-time visitor understands the
  point of the app in 10 seconds, before ever seeing a chart.
- Language switch now translates EVERYTHING — nav labels, safety guidance,
  disease symptom/prevention text, captions, and disclaimers — not just the
  section headers, across English, Hindi, Telugu, Spanish and French.
- All original functionality is preserved: live ESP32 data via Firebase
  Realtime Database (falling back to clearly-labeled simulated data),
  rule-based disease risk scoring, historical trend + contamination-event
  logging, zone risk map, and Twilio SMS alerts.

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

EXPECTED ESP32 DATA STRUCTURE in Firebase Realtime Database:

    /waterData
        water_temp, ph, turbidity, tds, rainfall, bacteria, humidity,
        ambient_temp_c, timestamp

    /history/{auto_id}
        same fields, one new child per reading, for real trend charts.
"""

import time
import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime

try:
    from streamlit_option_menu import option_menu
    OPTION_MENU_AVAILABLE = True
except ImportError:
    OPTION_MENU_AVAILABLE = False

# =========================================================
# PAGE CONFIG
# =========================================================
st.set_page_config(
    page_title="Jal Suraksha | Water Health Early Warning",
    page_icon="💧",
    layout="wide",
    initial_sidebar_state="expanded",
)

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
                return None, (
                    "Missing 'database_url' in [firebase] secrets. "
                    "Add it: database_url = \"https://<project>-default-rtdb.firebaseio.com\""
                )

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
    """Reads the latest ESP32 reading from Firebase at /waterData."""
    if not FIREBASE_AVAILABLE:
        return None, FIREBASE_INIT_ERROR
    try:
        ref = db.reference("/waterData")
        data = ref.get()
        if not data:
            return None, "No data found at /waterData yet (ESP32 may not have pushed anything)."

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


# =========================================================
# SMS CONFIGURATION
# =========================================================
ALERT_PHONE_NUMBER = "+919032644552"


def send_sms_alert(message: str, account_sid: str, auth_token: str, from_number: str) -> tuple[bool, str]:
    try:
        from twilio.rest import Client
        client = Client(account_sid, auth_token)
        msg = client.messages.create(body=message, from_=from_number, to=ALERT_PHONE_NUMBER)
        return True, f"SMS sent! SID: {msg.sid}"
    except ImportError:
        return False, "Twilio not installed. Run: pip install twilio"
    except Exception as e:
        return False, f"SMS failed: {str(e)}"


def build_sms_message(zone: str, overall_risk: float, alerted_diseases: dict, sensors: dict) -> str:
    risk_label, _ = get_risk_label(overall_risk)
    disease_list = ", ".join([f"{d} ({s:.0f}/100)" for d, s in alerted_diseases.items()])
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    return (
        f"[HEALTH ALERT] {timestamp}\n"
        f"Zone: {zone}\n"
        f"Overall Risk: {overall_risk:.1f}/100 - {risk_label}\n"
        f"Elevated diseases: {disease_list}\n"
        f"Water pH: {sensors['ph']:.2f} | Bacteria: {sensors['bacteria']:.0f} CFU/mL | "
        f"Rainfall: {sensors['rainfall']:.1f}mm\n"
        f"ACTION REQUIRED: Increase water disinfection & issue boil-water advisory."
    )


# =========================================================
# TRANSLATIONS  (everything user-facing lives here now)
# =========================================================
TRANSLATIONS = {
    "English": {
        "brand": "Jal Suraksha",
        "brand_tagline": "Water Safety Network",
        "title": "AI Community Health Early Warning System",
        "subtitle": "Real-Time Water-Borne Disease Risk Prediction",
        "nav_home": "Home",
        "nav_live": "Live Dashboard",
        "nav_trends": "Trends & History",
        "nav_map": "Zone Map",
        "nav_safety": "Safety Guide",
        "nav_alerts": "Alerts & SMS",
        "settings": "Settings",
        "language": "Language",
        "temp_unit": "Temperature Unit",
        "select_zone": "Select Zone / Village",
        "live_sensors": "Live Sensor Readings",
        "risk_prediction": "Disease Risk Prediction",
        "alerts": "Active Alerts",
        "trends": "Historical Trends",
        "map_view": "Zone Risk Map",
        "water_temp": "Water Temperature",
        "ph_level": "pH Level",
        "turbidity": "Turbidity (NTU)",
        "tds": "TDS (ppm)",
        "rainfall": "Rainfall (mm)",
        "bacteria": "Bacterial Count (CFU/mL)",
        "humidity": "Humidity (%)",
        "ambient_temp": "Ambient Temperature",
        "low_risk": "Low Risk",
        "moderate_risk": "Moderate Risk",
        "high_risk": "High Risk",
        "critical_risk": "Critical Risk",
        "overall_risk": "Overall Outbreak Risk Score",
        "disease_breakdown": "Disease-wise Risk Breakdown",
        "no_alerts": "No active alerts. Conditions normal.",
        "alert_msg": "ALERT: Elevated risk detected for",
        "recommendation": "Recommended Actions",
        "rec_1": "Increase water chlorination and disinfection frequency",
        "rec_2": "Distribute oral rehydration salts (ORS) to community health centers",
        "rec_3": "Issue public advisory: boil water before consumption",
        "rec_4": "Deploy health workers for door-to-door screening",
        "rec_5": "Increase surveillance and sample testing frequency",
        "last_updated": "Last updated",
        "refresh": "Refresh Data",
        "auto_refresh": "Auto-refresh every 10s",
        "footer": "AI-driven prototype for early warning of water-borne diseases (cholera, typhoid, diarrhea, dysentery, hepatitis A). For demonstration purposes only — not a substitute for medical advice.",
        "diseases": ["Cholera", "Typhoid", "Diarrhea", "Dysentery", "Hepatitis A"],
        "param_trend": "Select Parameter for Trend",
        "risk_level": "Risk Level",
        "zone": "Zone",
        "population": "Population",
        "summary": "Summary",
        "key_insights": "Key Insights",
        "insight_1": "Risk trend over the last period",
        "insight_2": "Bacterial contamination levels are within safe limits",
        "insight_3": "Heavy rainfall increases contamination risk significantly",
        "sms_settings": "SMS Alert Settings",
        "twilio_sid": "Twilio Account SID",
        "twilio_token": "Twilio Auth Token",
        "twilio_from": "Twilio Phone Number (from)",
        "send_sms": "Send SMS Alert Now",
        "sms_target": "Alert SMS Target",
        "sms_threshold": "SMS Alert Threshold (Risk Score)",
        "sms_auto": "Auto-send SMS when risk exceeds threshold",
        "sms_preview": "SMS Preview",
        "sms_log": "SMS Activity Log",
        "sms_need_creds": "Enter Twilio credentials in Settings to send SMS.",
        "sms_sent_ok": "SMS sent",
        "sms_sent_fail": "SMS failed",
        "firebase_connected": "Sensor network connected",
        "firebase_not_connected": "Sensor network not connected",
        "live_badge": "LIVE sensor data",
        "sim_badge": "Simulated demo data",
        "live_banner": "Showing LIVE ESP32 sensor data for",
        "sim_banner": "No live sensor reading available for this zone — showing simulated demo data instead.",
        "reason": "Reason",
        # --- Home page ---
        "home_eyebrow": "Community Water Health Watch",
        "home_hero_title": "Know your water is safe — before anyone gets sick.",
        "home_hero_sub": "Jal Suraksha watches the water your family drinks, every hour of every day, and warns your village early — in your own language.",
        "home_cta_primary": "Check my village now",
        "home_cta_secondary": "See how it works",
        "home_stat_1_num": "5",
        "home_stat_1_label": "Diseases tracked",
        "home_stat_2_num": "24/7",
        "home_stat_2_label": "Water sensors watching",
        "home_stat_3_num": "5",
        "home_stat_3_label": "Zones covered",
        "home_how_eyebrow": "How it works",
        "home_how_title": "From river to phone in four simple steps",
        "home_how_1_title": "Sensors read the water",
        "home_how_1_text": "A small device in the water source checks pH, cleanliness, temperature and germs, all day long.",
        "home_how_2_title": "AI checks the risk",
        "home_how_2_text": "Our system compares the readings against patterns known to cause cholera, typhoid and other illnesses.",
        "home_how_3_title": "Your village is warned",
        "home_how_3_text": "If risk rises, an alert and an SMS go out immediately, in the language you understand.",
        "home_how_4_title": "You take simple action",
        "home_how_4_text": "Boil water, use ORS, and follow the easy safety steps shown right in the app.",
        "home_diseases_eyebrow": "Know the risk",
        "home_diseases_title": "What can happen if water is unsafe",
        "home_diseases_sub": "These illnesses spread through contaminated water. Early warning means you can act before anyone falls ill.",
        "home_learn_more": "See full safety guide",
        "home_trust_title": "Built for every household",
        "home_trust_text": "Simple language, large text, and step-by-step guidance — designed so every person in the village, not just technicians, can understand the water risk and what to do about it.",
        "home_cta_footer_title": "Check your zone's water risk right now",
        "home_cta_footer_btn": "Open Live Dashboard",
        # --- Safety guide ---
        "safety_title": "Safety & Precautions Guide",
        "safety_sub": "General public-health guidance — not a substitute for medical advice. If someone is seriously unwell, contact a healthcare provider immediately.",
        "safety_tab_general": "General Precautions",
        "safety_tab_disease": "Disease-by-Disease Guidance",
        "safety_now_title": "Recommended precautions right now for",
        "risk_msg_critical": "Critical risk zone — treat ALL local water sources as unsafe until levels normalize.",
        "risk_msg_high": "High risk zone — boil or treat water before any use; avoid direct contact with untreated sources.",
        "risk_msg_moderate": "Moderate risk zone — basic precautions recommended; monitor for updates.",
        "risk_msg_low": "Low risk zone — conditions currently normal; standard hygiene practices still apply.",
        "symptoms": "Symptoms",
        "prevention": "Prevention",
        "seek_help": "When to seek help",
        "current_risk_in": "Current risk in",
        # --- Trends tab ---
        "real_history": "Showing REAL logged history from ESP32",
        "sim_history": "No real logged history found yet — showing simulated trend data instead.",
        "events_log": "Contamination Events Log",
        "events_note": "This log counts distinct contamination events — each time the risk score crossed into a High or Critical level — rather than every single elevated reading.",
        "high_events": "High-Risk Events",
        "critical_events": "Critical-Risk Events",
        "peak_risk": "Peak Risk Recorded",
        "period_covered": "Period Covered",
        "days": "day(s)",
        "readings_analyzed": "readings analyzed",
        "data_source": "Data source",
        "trend_chart": "Trend Chart",
        # --- Map tab ---
        "map_deep_dive": "Zone Deep-Dive: Live + Past Contamination History",
        "map_deep_dive_select": "Select an area to view its live reading and contamination history",
        "right_now": "Right Now",
        "past": "Past",
        "no_high_events": "No high-risk contamination events recorded in this period.",
        "critical_events_msg": "This zone reached CRITICAL contamination levels {n} time(s) in the last {d} day(s). Continued monitoring and precautions advised.",
        "high_events_msg": "This zone crossed into High Risk {n} time(s) in the last {d} day(s).",
        "live_col": "Live sensor?",
    },
    "हिन्दी (Hindi)": {
        "brand": "जल सुरक्षा",
        "brand_tagline": "जल सुरक्षा नेटवर्क",
        "title": "एआई सामुदायिक स्वास्थ्य पूर्व चेतावनी प्रणाली",
        "subtitle": "जल-जनित रोगों के जोखिम की वास्तविक समय भविष्यवाणी",
        "nav_home": "होम",
        "nav_live": "लाइव डैशबोर्ड",
        "nav_trends": "रुझान और इतिहास",
        "nav_map": "क्षेत्र मानचित्र",
        "nav_safety": "सुरक्षा गाइड",
        "nav_alerts": "चेतावनी और एसएमएस",
        "settings": "सेटिंग्स",
        "language": "भाषा",
        "temp_unit": "तापमान इकाई",
        "select_zone": "क्षेत्र / गांव चुनें",
        "live_sensors": "लाइव सेंसर रीडिंग",
        "risk_prediction": "रोग जोखिम भविष्यवाणी",
        "alerts": "सक्रिय चेतावनियाँ",
        "trends": "ऐतिहासिक रुझान",
        "map_view": "क्षेत्र जोखिम मानचित्र",
        "water_temp": "जल तापमान",
        "ph_level": "पीएच स्तर",
        "turbidity": "टर्बिडिटी (NTU)",
        "tds": "टीडीएस (ppm)",
        "rainfall": "वर्षा (मिमी)",
        "bacteria": "बैक्टीरिया गणना (CFU/mL)",
        "humidity": "आर्द्रता (%)",
        "ambient_temp": "वातावरणीय तापमान",
        "low_risk": "कम जोखिम",
        "moderate_risk": "मध्यम जोखिम",
        "high_risk": "उच्च जोखिम",
        "critical_risk": "गंभीर जोखिम",
        "overall_risk": "समग्र प्रकोप जोखिम स्कोर",
        "disease_breakdown": "रोग-वार जोखिम विवरण",
        "no_alerts": "कोई सक्रिय चेतावनी नहीं। स्थिति सामान्य है।",
        "alert_msg": "चेतावनी: इसके लिए बढ़ा हुआ जोखिम पाया गया",
        "recommendation": "अनुशंसित कार्रवाई",
        "rec_1": "जल क्लोरीनीकरण और कीटाणुशोधन की आवृत्ति बढ़ाएं",
        "rec_2": "सामुदायिक स्वास्थ्य केंद्रों में ओआरएस वितरित करें",
        "rec_3": "सार्वजनिक सलाह जारी करें: पानी उबालकर पिएं",
        "rec_4": "घर-घर जांच के लिए स्वास्थ्य कर्मियों को तैनात करें",
        "rec_5": "निगरानी और नमूना परीक्षण की आवृत्ति बढ़ाएं",
        "last_updated": "अंतिम अद्यतन",
        "refresh": "डेटा रीफ्रेश करें",
        "auto_refresh": "हर 10 सेकंड में ऑटो-रीफ्रेश करें",
        "footer": "जल-जनित रोगों (हैजा, टाइफाइड, दस्त, पेचिश, हेपेटाइटिस ए) की पूर्व चेतावनी के लिए एआई-संचालित प्रोटोटाइप। केवल प्रदर्शन हेतु — यह चिकित्सकीय सलाह का विकल्प नहीं है।",
        "diseases": ["हैजा", "टाइफाइड", "दस्त", "पेचिश", "हेपेटाइटिस ए"],
        "param_trend": "रुझान के लिए पैरामीटर चुनें",
        "risk_level": "जोखिम स्तर",
        "zone": "क्षेत्र",
        "population": "जनसंख्या",
        "summary": "सारांश",
        "key_insights": "मुख्य अंतर्दृष्टि",
        "insight_1": "पिछली अवधि में जोखिम का रुझान",
        "insight_2": "बैक्टीरिया संदूषण स्तर सुरक्षित सीमा के भीतर है",
        "insight_3": "भारी वर्षा संदूषण जोखिम को काफी बढ़ा देती है",
        "sms_settings": "एसएमएस अलर्ट सेटिंग्स",
        "twilio_sid": "Twilio अकाउंट SID",
        "twilio_token": "Twilio Auth Token",
        "twilio_from": "Twilio फ़ोन नंबर (से)",
        "send_sms": "एसएमएस अलर्ट भेजें",
        "sms_target": "अलर्ट एसएमएस लक्ष्य",
        "sms_threshold": "एसएमएस अलर्ट थ्रेशोल्ड (जोखिम स्कोर)",
        "sms_auto": "थ्रेशोल्ड पार होने पर ऑटो एसएमएस भेजें",
        "sms_preview": "एसएमएस प्रीव्यू",
        "sms_log": "एसएमएस गतिविधि लॉग",
        "sms_need_creds": "एसएमएस भेजने के लिए सेटिंग्स में Twilio जानकारी भरें।",
        "sms_sent_ok": "एसएमएस भेजा गया",
        "sms_sent_fail": "एसएमएस विफल",
        "firebase_connected": "सेंसर नेटवर्क जुड़ा है",
        "firebase_not_connected": "सेंसर नेटवर्क नहीं जुड़ा",
        "live_badge": "लाइव सेंसर डेटा",
        "sim_badge": "सिम्युलेटेड डेमो डेटा",
        "live_banner": "इस क्षेत्र के लिए लाइव ESP32 सेंसर डेटा दिखाया जा रहा है",
        "sim_banner": "इस क्षेत्र के लिए लाइव सेंसर रीडिंग उपलब्ध नहीं है — इसके बजाय सिम्युलेटेड डेमो डेटा दिखाया जा रहा है।",
        "reason": "कारण",
        "home_eyebrow": "सामुदायिक जल स्वास्थ्य निगरानी",
        "home_hero_title": "किसी के बीमार होने से पहले जानें कि आपका पानी सुरक्षित है या नहीं।",
        "home_hero_sub": "जल सुरक्षा आपके परिवार के पीने के पानी पर दिन-रात नज़र रखती है और आपके गांव को आपकी अपनी भाषा में समय रहते चेतावनी देती है।",
        "home_cta_primary": "अभी मेरा गांव जांचें",
        "home_cta_secondary": "यह कैसे काम करता है देखें",
        "home_stat_1_num": "5",
        "home_stat_1_label": "बीमारियों पर नज़र",
        "home_stat_2_num": "24/7",
        "home_stat_2_label": "जल सेंसर सक्रिय",
        "home_stat_3_num": "5",
        "home_stat_3_label": "क्षेत्र शामिल",
        "home_how_eyebrow": "यह कैसे काम करता है",
        "home_how_title": "नदी से फ़ोन तक — चार आसान चरणों में",
        "home_how_1_title": "सेंसर पानी की जांच करता है",
        "home_how_1_text": "जल स्रोत में लगा एक छोटा उपकरण पूरे दिन pH, सफाई, तापमान और कीटाणुओं की जांच करता है।",
        "home_how_2_title": "एआई जोखिम की गणना करता है",
        "home_how_2_text": "हमारी प्रणाली रीडिंग की तुलना उन पैटर्न से करती है जो हैजा, टाइफाइड और अन्य बीमारियों का कारण बनते हैं।",
        "home_how_3_title": "आपके गांव को चेतावनी दी जाती है",
        "home_how_3_text": "यदि जोखिम बढ़ता है, तो तुरंत आपकी भाषा में चेतावनी और एसएमएस भेजा जाता है।",
        "home_how_4_title": "आप आसान कदम उठाते हैं",
        "home_how_4_text": "पानी उबालें, ओआरएस का उपयोग करें, और ऐप में दिखाए गए आसान सुरक्षा कदमों का पालन करें।",
        "home_diseases_eyebrow": "जोखिम को जानें",
        "home_diseases_title": "अगर पानी असुरक्षित हो तो क्या हो सकता है",
        "home_diseases_sub": "ये बीमारियां दूषित पानी से फैलती हैं। समय रहते चेतावनी मिलने से आप किसी के बीमार होने से पहले ही कदम उठा सकते हैं।",
        "home_learn_more": "पूरी सुरक्षा गाइड देखें",
        "home_trust_title": "हर घर के लिए बनाया गया",
        "home_trust_text": "सरल भाषा, बड़ा टेक्स्ट, और चरण-दर-चरण मार्गदर्शन — ताकि गांव का हर व्यक्ति, न कि केवल तकनीशियन, जल जोखिम और उससे निपटने का तरीका समझ सके।",
        "home_cta_footer_title": "अभी अपने क्षेत्र का जल जोखिम जांचें",
        "home_cta_footer_btn": "लाइव डैशबोर्ड खोलें",
        "safety_title": "सुरक्षा और सावधानियां गाइड",
        "safety_sub": "सामान्य सार्वजनिक स्वास्थ्य मार्गदर्शन — यह चिकित्सकीय सलाह का विकल्प नहीं है। यदि कोई गंभीर रूप से अस्वस्थ है, तो तुरंत स्वास्थ्य सेवा प्रदाता से संपर्क करें।",
        "safety_tab_general": "सामान्य सावधानियां",
        "safety_tab_disease": "रोगवार मार्गदर्शन",
        "safety_now_title": "अभी के लिए अनुशंसित सावधानियां",
        "risk_msg_critical": "गंभीर जोखिम क्षेत्र — जब तक स्थिति सामान्य न हो, सभी स्थानीय जल स्रोतों को असुरक्षित मानें।",
        "risk_msg_high": "उच्च जोखिम क्षेत्र — उपयोग से पहले पानी उबालें या शुद्ध करें; अशुद्ध स्रोतों के सीधे संपर्क से बचें।",
        "risk_msg_moderate": "मध्यम जोखिम क्षेत्र — बुनियादी सावधानियों की सिफारिश की जाती है; अपडेट पर नज़र रखें।",
        "risk_msg_low": "कम जोखिम क्षेत्र — स्थिति सामान्य है; फिर भी मानक स्वच्छता प्रथाओं का पालन करें।",
        "symptoms": "लक्षण",
        "prevention": "बचाव",
        "seek_help": "मदद कब लें",
        "current_risk_in": "वर्तमान जोखिम",
        "real_history": "ESP32 से वास्तविक दर्ज इतिहास दिखाया जा रहा है",
        "sim_history": "अभी तक कोई वास्तविक दर्ज इतिहास नहीं मिला — इसके बजाय सिम्युलेटेड रुझान डेटा दिखाया जा रहा है।",
        "events_log": "संदूषण घटना लॉग",
        "events_note": "यह लॉग अलग-अलग संदूषण घटनाओं की गिनती करता है — हर बार जब जोखिम स्कोर उच्च या गंभीर स्तर में प्रवेश करता है — न कि हर बढ़ी हुई रीडिंग की।",
        "high_events": "उच्च-जोखिम घटनाएं",
        "critical_events": "गंभीर-जोखिम घटनाएं",
        "peak_risk": "दर्ज शिखर जोखिम",
        "period_covered": "अवधि",
        "days": "दिन",
        "readings_analyzed": "रीडिंग का विश्लेषण किया गया",
        "data_source": "डेटा स्रोत",
        "trend_chart": "रुझान चार्ट",
        "map_deep_dive": "क्षेत्र गहन विश्लेषण: लाइव + पिछला संदूषण इतिहास",
        "map_deep_dive_select": "लाइव रीडिंग और संदूषण इतिहास देखने के लिए क्षेत्र चुनें",
        "right_now": "अभी",
        "past": "पिछले",
        "no_high_events": "इस अवधि में कोई उच्च-जोखिम संदूषण घटना दर्ज नहीं हुई।",
        "critical_events_msg": "यह क्षेत्र पिछले {d} दिन(दिनों) में {n} बार गंभीर संदूषण स्तर पर पहुंचा। निरंतर निगरानी और सावधानी की सलाह दी जाती है।",
        "high_events_msg": "यह क्षेत्र पिछले {d} दिन(दिनों) में {n} बार उच्च जोखिम में गया।",
        "live_col": "लाइव सेंसर?",
    },
    "తెలుగు (Telugu)": {
        "brand": "జల్ సురక్ష",
        "brand_tagline": "నీటి భద్రతా నెట్‌వర్క్",
        "title": "AI కమ్యూనిటీ హెల్త్ ముందస్తు హెచ్చరిక వ్యవస్థ",
        "subtitle": "నీటి ద్వారా వ్యాపించే వ్యాధుల రియల్-టైమ్ ప్రమాద అంచనా",
        "nav_home": "హోమ్",
        "nav_live": "లైవ్ డాష్‌బోర్డ్",
        "nav_trends": "ధోరణులు & చరిత్ర",
        "nav_map": "జోన్ మ్యాప్",
        "nav_safety": "భద్రతా గైడ్",
        "nav_alerts": "హెచ్చరికలు & SMS",
        "settings": "సెట్టింగ్‌లు",
        "language": "భాష",
        "temp_unit": "ఉష్ణోగ్రత యూనిట్",
        "select_zone": "జోన్ / గ్రామం ఎంచుకోండి",
        "live_sensors": "లైవ్ సెన్సార్ రీడింగ్‌లు",
        "risk_prediction": "వ్యాధి ప్రమాద అంచనా",
        "alerts": "క్రియాశీల హెచ్చరికలు",
        "trends": "చారిత్రక ధోరణులు",
        "map_view": "జోన్ ప్రమాద మ్యాప్",
        "water_temp": "నీటి ఉష్ణోగ్రత",
        "ph_level": "pH స్థాయి",
        "turbidity": "టర్బిడిటీ (NTU)",
        "tds": "TDS (ppm)",
        "rainfall": "వర్షపాతం (mm)",
        "bacteria": "బ్యాక్టీరియా కౌంట్ (CFU/mL)",
        "humidity": "తేమ (%)",
        "ambient_temp": "పరిసర ఉష్ణోగ్రత",
        "low_risk": "తక్కువ ప్రమాదం",
        "moderate_risk": "మధ్యస్థ ప్రమాదం",
        "high_risk": "అధిక ప్రమాదం",
        "critical_risk": "తీవ్రమైన ప్రమాదం",
        "overall_risk": "మొత్తం వ్యాప్తి ప్రమాద స్కోరు",
        "disease_breakdown": "వ్యాధి వారీగా ప్రమాద విశ్లేషణ",
        "no_alerts": "క్రియాశీల హెచ్చరికలు లేవు. పరిస్థితులు సాధారణం.",
        "alert_msg": "హెచ్చరిక: దీనికి పెరిగిన ప్రమాదం గుర్తించబడింది",
        "recommendation": "సిఫార్సు చేసిన చర్యలు",
        "rec_1": "నీటి క్లోరినేషన్ మరియు క్రిమిసంహారక ఫ్రీక్వెన్సీని పెంచండి",
        "rec_2": "కమ్యూనిటీ హెల్త్ సెంటర్లకు ORS ను పంపిణీ చేయండి",
        "rec_3": "ప్రజా సూచన జారీ చేయండి: నీటిని మరిగించి తాగండి",
        "rec_4": "ఇంటింటి స్క్రీనింగ్ కోసం ఆరోగ్య కార్యకర్తలను నియమించండి",
        "rec_5": "నిఘా మరియు నమూనా పరీక్ష ఫ్రీక్వెన్సీని పెంచండి",
        "last_updated": "చివరిగా నవీకరించబడింది",
        "refresh": "డేటాను రిఫ్రెష్ చేయండి",
        "auto_refresh": "ప్రతి 10 సెకన్లకు ఆటో-రిఫ్రెష్",
        "footer": "నీటి ద్వారా వ్యాపించే వ్యాధుల (కలరా, టైఫాయిడ్, డయేరియా, డిసెంటరీ, హెపటైటిస్ A) ముందస్తు హెచ్చరిక కోసం AI ఆధారిత ప్రోటోటైప్. ఇది కేవలం ప్రదర్శన కోసం మాత్రమే — వైద్య సలహాకు ప్రత్యామ్నాయం కాదు.",
        "diseases": ["కలరా", "టైఫాయిడ్", "డయేరియా", "డిసెంటరీ", "హెపటైటిస్ A"],
        "param_trend": "ధోరణి కోసం పారామితిని ఎంచుకోండి",
        "risk_level": "ప్రమాద స్థాయి",
        "zone": "జోన్",
        "population": "జనాభా",
        "summary": "సారాంశం",
        "key_insights": "ముఖ్య అంతర్దృష్టులు",
        "insight_1": "గత కాలంలో ప్రమాద ధోరణి",
        "insight_2": "బ్యాక్టీరియా కాలుష్య స్థాయిలు సురక్షిత పరిమితుల్లో ఉన్నాయి",
        "insight_3": "భారీ వర్షపాతం కాలుష్య ప్రమాదాన్ని గణనీయంగా పెంచుతుంది",
        "sms_settings": "SMS హెచ్చరిక సెట్టింగ్‌లు",
        "twilio_sid": "Twilio అకౌంట్ SID",
        "twilio_token": "Twilio Auth Token",
        "twilio_from": "Twilio ఫోన్ నంబర్ (నుండి)",
        "send_sms": "SMS హెచ్చరిక పంపండి",
        "sms_target": "హెచ్చరిక SMS లక్ష్యం",
        "sms_threshold": "SMS హెచ్చరిక థ్రెషోల్డ్ (ప్రమాద స్కోర్)",
        "sms_auto": "థ్రెషోల్డ్ మించినప్పుడు ఆటో SMS పంపండి",
        "sms_preview": "SMS ప్రివ్యూ",
        "sms_log": "SMS కార్యాచరణ లాగ్",
        "sms_need_creds": "SMS పంపడానికి సెట్టింగ్స్‌లో Twilio వివరాలు నమోదు చేయండి.",
        "sms_sent_ok": "SMS పంపబడింది",
        "sms_sent_fail": "SMS విఫలమైంది",
        "firebase_connected": "సెన్సార్ నెట్‌వర్క్ కనెక్ట్ అయ్యింది",
        "firebase_not_connected": "సెన్సార్ నెట్‌వర్క్ కనెక్ట్ కాలేదు",
        "live_badge": "లైవ్ సెన్సార్ డేటా",
        "sim_badge": "సిమ్యులేటెడ్ డెమో డేటా",
        "live_banner": "ఈ జోన్ కోసం లైవ్ ESP32 సెన్సార్ డేటా చూపబడుతోంది",
        "sim_banner": "ఈ జోన్ కోసం లైవ్ సెన్సార్ రీడింగ్ అందుబాటులో లేదు — బదులుగా సిమ్యులేటెడ్ డెమో డేటా చూపబడుతోంది.",
        "reason": "కారణం",
        "home_eyebrow": "కమ్యూనిటీ నీటి ఆరోగ్య నిఘా",
        "home_hero_title": "ఎవరైనా అనారోగ్యానికి గురికాకముందే మీ నీరు సురక్షితమో కాదో తెలుసుకోండి.",
        "home_hero_sub": "జల్ సురక్ష మీ కుటుంబం తాగే నీటిని రోజంతా గమనిస్తూ, మీ గ్రామాన్ని మీ సొంత భాషలో ముందుగానే హెచ్చరిస్తుంది.",
        "home_cta_primary": "ఇప్పుడే నా గ్రామాన్ని చూడండి",
        "home_cta_secondary": "ఇది ఎలా పనిచేస్తుందో చూడండి",
        "home_stat_1_num": "5",
        "home_stat_1_label": "ట్రాక్ చేస్తున్న వ్యాధులు",
        "home_stat_2_num": "24/7",
        "home_stat_2_label": "నీటి సెన్సార్లు పర్యవేక్షణ",
        "home_stat_3_num": "5",
        "home_stat_3_label": "కవర్ చేసిన జోన్లు",
        "home_how_eyebrow": "ఇది ఎలా పనిచేస్తుంది",
        "home_how_title": "నదినుండి ఫోన్ వరకూ — నాలుగు సులభమైన దశల్లో",
        "home_how_1_title": "సెన్సార్లు నీటిని పరిశీలిస్తాయి",
        "home_how_1_text": "నీటి వనరులో ఉన్న చిన్న పరికరం రోజంతా pH, శుభ్రత, ఉష్ణోగ్రత మరియు క్రిములను తనిఖీ చేస్తుంది.",
        "home_how_2_title": "AI ప్రమాదాన్ని అంచనా వేస్తుంది",
        "home_how_2_text": "మా వ్యవస్థ రీడింగ్‌లను కలరా, టైఫాయిడ్ వంటి వ్యాధులకు కారణమయ్యే నమూనాలతో పోలుస్తుంది.",
        "home_how_3_title": "మీ గ్రామానికి హెచ్చరిక అందుతుంది",
        "home_how_3_text": "ప్రమాదం పెరిగితే, మీకు అర్థమయ్యే భాషలో వెంటనే హెచ్చరిక మరియు SMS పంపబడతాయి.",
        "home_how_4_title": "మీరు సులభమైన చర్యలు తీసుకుంటారు",
        "home_how_4_text": "నీటిని మరిగించండి, ORS వాడండి, మరియు యాప్‌లో చూపిన సులభమైన భద్రతా చర్యలను పాటించండి.",
        "home_diseases_eyebrow": "ప్రమాదాన్ని తెలుసుకోండి",
        "home_diseases_title": "నీరు అసురక్షితంగా ఉంటే ఏమి జరగవచ్చు",
        "home_diseases_sub": "ఈ వ్యాధులు కలుషిత నీటి ద్వారా వ్యాపిస్తాయి. ముందస్తు హెచ్చరిక వల్ల ఎవరైనా అనారోగ్యానికి గురికాకముందే మీరు చర్య తీసుకోవచ్చు.",
        "home_learn_more": "పూర్తి భద్రతా గైడ్ చూడండి",
        "home_trust_title": "ప్రతి ఇంటి కోసం రూపొందించబడింది",
        "home_trust_text": "సరళమైన భాష, పెద్ద అక్షరాలు, దశలవారీ మార్గదర్శకత్వం — గ్రామంలోని ప్రతి వ్యక్తి, సాంకేతిక నిపుణులు మాత్రమే కాకుండా, నీటి ప్రమాదాన్ని మరియు దాన్ని ఎలా ఎదుర్కోవాలో అర్థం చేసుకునేలా రూపొందించబడింది.",
        "home_cta_footer_title": "ఇప్పుడే మీ జోన్ నీటి ప్రమాదాన్ని తనిఖీ చేయండి",
        "home_cta_footer_btn": "లైవ్ డాష్‌బోర్డ్ తెరవండి",
        "safety_title": "భద్రత & జాగ్రత్తల గైడ్",
        "safety_sub": "సాధారణ ప్రజారోగ్య మార్గదర్శకత్వం — ఇది వైద్య సలహాకు ప్రత్యామ్నాయం కాదు. ఎవరైనా తీవ్ర అనారోగ్యానికి గురైతే వెంటనే వైద్యుడిని సంప్రదించండి.",
        "safety_tab_general": "సాధారణ జాగ్రత్తలు",
        "safety_tab_disease": "వ్యాధి వారీగా మార్గదర్శకత్వం",
        "safety_now_title": "ఇప్పుడు సిఫార్సు చేయబడిన జాగ్రత్తలు",
        "risk_msg_critical": "తీవ్రమైన ప్రమాద జోన్ — పరిస్థితులు సాధారణం అయ్యేవరకు అన్ని స్థానిక నీటి వనరులను అసురక్షితంగా భావించండి.",
        "risk_msg_high": "అధిక ప్రమాద జోన్ — ఉపయోగించే ముందు నీటిని మరిగించండి లేదా శుద్ధి చేయండి; శుద్ధి చేయని వనరులతో ప్రత్యక్ష సంబంధాన్ని నివారించండి.",
        "risk_msg_moderate": "మధ్యస్థ ప్రమాద జోన్ — ప్రాథమిక జాగ్రత్తలు సిఫార్సు చేయబడతాయి; అప్‌డేట్‌ల కోసం పరిశీలించండి.",
        "risk_msg_low": "తక్కువ ప్రమాద జోన్ — ప్రస్తుత పరిస్థితులు సాధారణం; అయినా ప్రామాణిక పరిశుభ్రత పద్ధతులు పాటించండి.",
        "symptoms": "లక్షణాలు",
        "prevention": "నివారణ",
        "seek_help": "సహాయం ఎప్పుడు తీసుకోవాలి",
        "current_risk_in": "ప్రస్తుత ప్రమాదం",
        "real_history": "ESP32 నుండి నిజమైన లాగ్ చేసిన చరిత్ర చూపబడుతోంది",
        "sim_history": "ఇంకా నిజమైన లాగ్ చేసిన చరిత్ర కనుగొనబడలేదు — బదులుగా సిమ్యులేటెడ్ ధోరణి డేటా చూపబడుతోంది.",
        "events_log": "కాలుష్య సంఘటనల లాగ్",
        "events_note": "ఈ లాగ్ ప్రతి ఎలివేటెడ్ రీడింగ్ కాకుండా, ప్రమాద స్కోరు అధిక లేదా తీవ్రమైన స్థాయిలోకి ప్రవేశించిన ప్రతిసారీ ఒక విభిన్న కాలుష్య సంఘటనగా లెక్కిస్తుంది.",
        "high_events": "అధిక-ప్రమాద సంఘటనలు",
        "critical_events": "తీవ్ర-ప్రమాద సంఘటనలు",
        "peak_risk": "నమోదైన గరిష్ట ప్రమాదం",
        "period_covered": "కాలవ్యవధి",
        "days": "రోజు(లు)",
        "readings_analyzed": "రీడింగ్‌లు విశ్లేషించబడ్డాయి",
        "data_source": "డేటా మూలం",
        "trend_chart": "ధోరణి చార్ట్",
        "map_deep_dive": "జోన్ లోతైన విశ్లేషణ: లైవ్ + గత కాలుష్య చరిత్ర",
        "map_deep_dive_select": "లైవ్ రీడింగ్ మరియు కాలుష్య చరిత్ర చూడటానికి ప్రాంతాన్ని ఎంచుకోండి",
        "right_now": "ఇప్పుడు",
        "past": "గత",
        "no_high_events": "ఈ కాలంలో అధిక-ప్రమాద కాలుష్య సంఘటనలు నమోదు కాలేదు.",
        "critical_events_msg": "ఈ జోన్ గత {d} రోజు(ల)లో {n} సార్లు తీవ్రమైన కాలుష్య స్థాయికి చేరుకుంది. నిరంతర పర్యవేక్షణ మరియు జాగ్రత్తలు సిఫార్సు చేయబడతాయి.",
        "high_events_msg": "ఈ జోన్ గత {d} రోజు(ల)లో {n} సార్లు అధిక ప్రమాదంలోకి వెళ్లింది.",
        "live_col": "లైవ్ సెన్సార్?",
    },
    "Español (Spanish)": {
        "brand": "Jal Suraksha",
        "brand_tagline": "Red de Seguridad del Agua",
        "title": "Sistema de Alerta Temprana de Salud Comunitaria con IA",
        "subtitle": "Predicción en Tiempo Real del Riesgo de Enfermedades Hídricas",
        "nav_home": "Inicio",
        "nav_live": "Panel en Vivo",
        "nav_trends": "Tendencias e Historial",
        "nav_map": "Mapa de Zonas",
        "nav_safety": "Guía de Seguridad",
        "nav_alerts": "Alertas y SMS",
        "settings": "Configuración",
        "language": "Idioma",
        "temp_unit": "Unidad de Temperatura",
        "select_zone": "Seleccionar Zona / Pueblo",
        "live_sensors": "Lecturas de Sensores en Vivo",
        "risk_prediction": "Predicción de Riesgo de Enfermedad",
        "alerts": "Alertas Activas",
        "trends": "Tendencias Históricas",
        "map_view": "Mapa de Riesgo por Zona",
        "water_temp": "Temperatura del Agua",
        "ph_level": "Nivel de pH",
        "turbidity": "Turbidez (NTU)",
        "tds": "TDS (ppm)",
        "rainfall": "Precipitación (mm)",
        "bacteria": "Conteo Bacteriano (CFU/mL)",
        "humidity": "Humedad (%)",
        "ambient_temp": "Temperatura Ambiente",
        "low_risk": "Riesgo Bajo",
        "moderate_risk": "Riesgo Moderado",
        "high_risk": "Riesgo Alto",
        "critical_risk": "Riesgo Crítico",
        "overall_risk": "Puntuación General de Riesgo de Brote",
        "disease_breakdown": "Desglose de Riesgo por Enfermedad",
        "no_alerts": "No hay alertas activas. Condiciones normales.",
        "alert_msg": "ALERTA: Riesgo elevado detectado para",
        "recommendation": "Acciones Recomendadas",
        "rec_1": "Aumentar la frecuencia de cloración y desinfección del agua",
        "rec_2": "Distribuir sales de rehidratación oral (SRO) a los centros de salud",
        "rec_3": "Emitir aviso público: hervir el agua antes de consumirla",
        "rec_4": "Desplegar trabajadores de salud para evaluación puerta a puerta",
        "rec_5": "Aumentar la vigilancia y la frecuencia de pruebas",
        "last_updated": "Última actualización",
        "refresh": "Actualizar Datos",
        "auto_refresh": "Actualizar automáticamente cada 10s",
        "footer": "Prototipo basado en IA para alerta temprana de enfermedades transmitidas por el agua (cólera, fiebre tifoidea, diarrea, disentería, hepatitis A). Solo con fines de demostración — no sustituye el consejo médico.",
        "diseases": ["Cólera", "Fiebre Tifoidea", "Diarrea", "Disentería", "Hepatitis A"],
        "param_trend": "Seleccionar Parámetro para Tendencia",
        "risk_level": "Nivel de Riesgo",
        "zone": "Zona",
        "population": "Población",
        "summary": "Resumen",
        "key_insights": "Conclusiones Clave",
        "insight_1": "Tendencia de riesgo en el último periodo",
        "insight_2": "Los niveles de contaminación bacteriana están dentro de límites seguros",
        "insight_3": "Las lluvias intensas aumentan significativamente el riesgo de contaminación",
        "sms_settings": "Configuración de Alerta SMS",
        "twilio_sid": "SID de Cuenta Twilio",
        "twilio_token": "Token de Autenticación Twilio",
        "twilio_from": "Número de Teléfono Twilio (desde)",
        "send_sms": "Enviar Alerta SMS Ahora",
        "sms_target": "Destino SMS de Alerta",
        "sms_threshold": "Umbral de Alerta SMS (Puntuación de Riesgo)",
        "sms_auto": "Envío automático de SMS cuando el riesgo supere el umbral",
        "sms_preview": "Vista Previa del SMS",
        "sms_log": "Registro de Actividad SMS",
        "sms_need_creds": "Ingrese las credenciales de Twilio en Configuración para enviar SMS.",
        "sms_sent_ok": "SMS enviado",
        "sms_sent_fail": "Error al enviar SMS",
        "firebase_connected": "Red de sensores conectada",
        "firebase_not_connected": "Red de sensores no conectada",
        "live_badge": "Datos de sensor EN VIVO",
        "sim_badge": "Datos de demostración simulados",
        "live_banner": "Mostrando datos EN VIVO del sensor ESP32 para",
        "sim_banner": "No hay lectura en vivo disponible para esta zona — mostrando datos simulados en su lugar.",
        "reason": "Motivo",
        "home_eyebrow": "Vigilancia Comunitaria del Agua",
        "home_hero_title": "Sepa que su agua es segura — antes de que alguien se enferme.",
        "home_hero_sub": "Jal Suraksha vigila el agua que bebe su familia, las 24 horas del día, y avisa a su pueblo a tiempo, en su propio idioma.",
        "home_cta_primary": "Revisar mi pueblo ahora",
        "home_cta_secondary": "Ver cómo funciona",
        "home_stat_1_num": "5",
        "home_stat_1_label": "Enfermedades monitoreadas",
        "home_stat_2_num": "24/7",
        "home_stat_2_label": "Sensores de agua vigilando",
        "home_stat_3_num": "5",
        "home_stat_3_label": "Zonas cubiertas",
        "home_how_eyebrow": "Cómo funciona",
        "home_how_title": "Del río al teléfono en cuatro pasos sencillos",
        "home_how_1_title": "Los sensores leen el agua",
        "home_how_1_text": "Un pequeño dispositivo en la fuente de agua revisa el pH, la limpieza, la temperatura y los gérmenes, todo el día.",
        "home_how_2_title": "La IA evalúa el riesgo",
        "home_how_2_text": "Nuestro sistema compara las lecturas con patrones conocidos que causan cólera, tifoidea y otras enfermedades.",
        "home_how_3_title": "Se avisa a su pueblo",
        "home_how_3_text": "Si el riesgo aumenta, se envía de inmediato una alerta y un SMS en el idioma que usted entiende.",
        "home_how_4_title": "Usted toma medidas simples",
        "home_how_4_text": "Hierva el agua, use SRO y siga los pasos de seguridad sencillos que se muestran en la aplicación.",
        "home_diseases_eyebrow": "Conozca el riesgo",
        "home_diseases_title": "Qué puede pasar si el agua no es segura",
        "home_diseases_sub": "Estas enfermedades se propagan por agua contaminada. La alerta temprana significa que puede actuar antes de que alguien se enferme.",
        "home_learn_more": "Ver guía completa de seguridad",
        "home_trust_title": "Diseñado para cada hogar",
        "home_trust_text": "Lenguaje sencillo, texto grande y orientación paso a paso — para que cada persona del pueblo, no solo los técnicos, entienda el riesgo del agua y qué hacer al respecto.",
        "home_cta_footer_title": "Revise ahora el riesgo del agua en su zona",
        "home_cta_footer_btn": "Abrir Panel en Vivo",
        "safety_title": "Guía de Seguridad y Precauciones",
        "safety_sub": "Orientación general de salud pública — no sustituye el consejo médico. Si alguien está gravemente enfermo, contacte a un profesional de salud de inmediato.",
        "safety_tab_general": "Precauciones Generales",
        "safety_tab_disease": "Guía por Enfermedad",
        "safety_now_title": "Precauciones recomendadas ahora mismo para",
        "risk_msg_critical": "Zona de riesgo crítico — trate TODAS las fuentes de agua locales como inseguras hasta que los niveles se normalicen.",
        "risk_msg_high": "Zona de riesgo alto — hierva o trate el agua antes de usarla; evite el contacto directo con fuentes no tratadas.",
        "risk_msg_moderate": "Zona de riesgo moderado — se recomiendan precauciones básicas; esté atento a actualizaciones.",
        "risk_msg_low": "Zona de riesgo bajo — condiciones actualmente normales; aun así, mantenga prácticas de higiene estándar.",
        "symptoms": "Síntomas",
        "prevention": "Prevención",
        "seek_help": "Cuándo buscar ayuda",
        "current_risk_in": "Riesgo actual en",
        "real_history": "Mostrando historial REAL registrado por el ESP32",
        "sim_history": "Aún no se encontró historial real registrado — mostrando datos de tendencia simulados en su lugar.",
        "events_log": "Registro de Eventos de Contaminación",
        "events_note": "Este registro cuenta eventos de contaminación distintos — cada vez que el puntaje de riesgo cruzó a un nivel Alto o Crítico — en lugar de cada lectura elevada individual.",
        "high_events": "Eventos de Alto Riesgo",
        "critical_events": "Eventos de Riesgo Crítico",
        "peak_risk": "Riesgo Máximo Registrado",
        "period_covered": "Período Cubierto",
        "days": "día(s)",
        "readings_analyzed": "lecturas analizadas",
        "data_source": "Fuente de datos",
        "trend_chart": "Gráfico de Tendencia",
        "map_deep_dive": "Análisis Detallado de Zona: Historial en Vivo + Pasado",
        "map_deep_dive_select": "Seleccione un área para ver su lectura en vivo e historial de contaminación",
        "right_now": "En Este Momento",
        "past": "Últimos",
        "no_high_events": "No se registraron eventos de contaminación de alto riesgo en este período.",
        "critical_events_msg": "Esta zona alcanzó niveles de contaminación CRÍTICOS {n} vez/veces en los últimos {d} día(s). Se recomienda vigilancia continua y precauciones.",
        "high_events_msg": "Esta zona cruzó a Riesgo Alto {n} vez/veces en los últimos {d} día(s).",
        "live_col": "¿Sensor en vivo?",
    },
    "Français (French)": {
        "brand": "Jal Suraksha",
        "brand_tagline": "Réseau de Sécurité de l'Eau",
        "title": "Système d'Alerte Précoce de Santé Communautaire par IA",
        "subtitle": "Prédiction en Temps Réel du Risque de Maladies Hydriques",
        "nav_home": "Accueil",
        "nav_live": "Tableau de Bord en Direct",
        "nav_trends": "Tendances & Historique",
        "nav_map": "Carte des Zones",
        "nav_safety": "Guide de Sécurité",
        "nav_alerts": "Alertes & SMS",
        "settings": "Paramètres",
        "language": "Langue",
        "temp_unit": "Unité de Température",
        "select_zone": "Sélectionner Zone / Village",
        "live_sensors": "Lectures des Capteurs en Direct",
        "risk_prediction": "Prédiction du Risque de Maladie",
        "alerts": "Alertes Actives",
        "trends": "Tendances Historiques",
        "map_view": "Carte des Risques par Zone",
        "water_temp": "Température de l'Eau",
        "ph_level": "Niveau de pH",
        "turbidity": "Turbidité (NTU)",
        "tds": "TDS (ppm)",
        "rainfall": "Précipitations (mm)",
        "bacteria": "Numération Bactérienne (CFU/mL)",
        "humidity": "Humidité (%)",
        "ambient_temp": "Température Ambiante",
        "low_risk": "Risque Faible",
        "moderate_risk": "Risque Modéré",
        "high_risk": "Risque Élevé",
        "critical_risk": "Risque Critique",
        "overall_risk": "Score Global de Risque d'Épidémie",
        "disease_breakdown": "Répartition du Risque par Maladie",
        "no_alerts": "Aucune alerte active. Conditions normales.",
        "alert_msg": "ALERTE : Risque élevé détecté pour",
        "recommendation": "Actions Recommandées",
        "rec_1": "Augmenter la fréquence de chloration et de désinfection de l'eau",
        "rec_2": "Distribuer des sels de réhydratation orale (SRO) aux centres de santé",
        "rec_3": "Émettre un avis public : faire bouillir l'eau avant consommation",
        "rec_4": "Déployer des agents de santé pour le dépistage porte-à-porte",
        "rec_5": "Augmenter la surveillance et la fréquence des tests",
        "last_updated": "Dernière mise à jour",
        "refresh": "Actualiser les Données",
        "auto_refresh": "Actualisation automatique toutes les 10s",
        "footer": "Prototype basé sur l'IA pour l'alerte précoce des maladies hydriques (choléra, typhoïde, diarrhée, dysenterie, hépatite A). À des fins de démonstration uniquement — ne remplace pas un avis médical.",
        "diseases": ["Choléra", "Typhoïde", "Diarrhée", "Dysenterie", "Hépatite A"],
        "param_trend": "Sélectionner un Paramètre pour la Tendance",
        "risk_level": "Niveau de Risque",
        "zone": "Zone",
        "population": "Population",
        "summary": "Résumé",
        "key_insights": "Points Clés",
        "insight_1": "Tendance du risque sur la dernière période",
        "insight_2": "Les niveaux de contamination bactérienne sont dans les limites sûres",
        "insight_3": "De fortes pluies augmentent considérablement le risque de contamination",
        "sms_settings": "Paramètres d'Alerte SMS",
        "twilio_sid": "SID de Compte Twilio",
        "twilio_token": "Jeton d'Authentification Twilio",
        "twilio_from": "Numéro de Téléphone Twilio (depuis)",
        "send_sms": "Envoyer une Alerte SMS Maintenant",
        "sms_target": "Destinataire SMS d'Alerte",
        "sms_threshold": "Seuil d'Alerte SMS (Score de Risque)",
        "sms_auto": "Envoi SMS automatique si le risque dépasse le seuil",
        "sms_preview": "Aperçu du SMS",
        "sms_log": "Journal d'Activité SMS",
        "sms_need_creds": "Entrez les identifiants Twilio dans les Paramètres pour envoyer un SMS.",
        "sms_sent_ok": "SMS envoyé",
        "sms_sent_fail": "Échec de l'envoi du SMS",
        "firebase_connected": "Réseau de capteurs connecté",
        "firebase_not_connected": "Réseau de capteurs non connecté",
        "live_badge": "Données de capteur EN DIRECT",
        "sim_badge": "Données de démonstration simulées",
        "live_banner": "Affichage des données EN DIRECT du capteur ESP32 pour",
        "sim_banner": "Aucune lecture en direct disponible pour cette zone — affichage de données simulées à la place.",
        "reason": "Raison",
        "home_eyebrow": "Veille Communautaire de l'Eau",
        "home_hero_title": "Sachez que votre eau est sûre — avant que quelqu'un ne tombe malade.",
        "home_hero_sub": "Jal Suraksha surveille l'eau que boit votre famille, jour et nuit, et alerte votre village tôt, dans votre propre langue.",
        "home_cta_primary": "Vérifier mon village maintenant",
        "home_cta_secondary": "Voir comment ça marche",
        "home_stat_1_num": "5",
        "home_stat_1_label": "Maladies suivies",
        "home_stat_2_num": "24/7",
        "home_stat_2_label": "Capteurs d'eau en veille",
        "home_stat_3_num": "5",
        "home_stat_3_label": "Zones couvertes",
        "home_how_eyebrow": "Comment ça marche",
        "home_how_title": "De la rivière au téléphone en quatre étapes simples",
        "home_how_1_title": "Les capteurs analysent l'eau",
        "home_how_1_text": "Un petit appareil dans la source d'eau vérifie le pH, la propreté, la température et les germes, toute la journée.",
        "home_how_2_title": "L'IA évalue le risque",
        "home_how_2_text": "Notre système compare les relevés à des schémas connus pour causer le choléra, la typhoïde et d'autres maladies.",
        "home_how_3_title": "Votre village est alerté",
        "home_how_3_text": "Si le risque augmente, une alerte et un SMS sont envoyés immédiatement, dans la langue que vous comprenez.",
        "home_how_4_title": "Vous agissez simplement",
        "home_how_4_text": "Faites bouillir l'eau, utilisez des SRO, et suivez les étapes de sécurité simples affichées dans l'application.",
        "home_diseases_eyebrow": "Connaître le risque",
        "home_diseases_title": "Ce qui peut arriver si l'eau n'est pas sûre",
        "home_diseases_sub": "Ces maladies se propagent par l'eau contaminée. Une alerte précoce signifie que vous pouvez agir avant que quiconque ne tombe malade.",
        "home_learn_more": "Voir le guide de sécurité complet",
        "home_trust_title": "Conçu pour chaque foyer",
        "home_trust_text": "Langage simple, grand texte et conseils étape par étape — conçu pour que chaque personne du village, pas seulement les techniciens, comprenne le risque lié à l'eau et ce qu'il faut faire.",
        "home_cta_footer_title": "Vérifiez maintenant le risque hydrique de votre zone",
        "home_cta_footer_btn": "Ouvrir le Tableau de Bord",
        "safety_title": "Guide de Sécurité et Précautions",
        "safety_sub": "Conseils généraux de santé publique — ne remplace pas un avis médical. Si quelqu'un est gravement malade, contactez immédiatement un professionnel de santé.",
        "safety_tab_general": "Précautions Générales",
        "safety_tab_disease": "Conseils par Maladie",
        "safety_now_title": "Précautions recommandées maintenant pour",
        "risk_msg_critical": "Zone à risque critique — considérez TOUTES les sources d'eau locales comme dangereuses jusqu'à normalisation des niveaux.",
        "risk_msg_high": "Zone à risque élevé — faites bouillir ou traitez l'eau avant toute utilisation ; évitez tout contact direct avec des sources non traitées.",
        "risk_msg_moderate": "Zone à risque modéré — précautions de base recommandées ; surveillez les mises à jour.",
        "risk_msg_low": "Zone à faible risque — conditions actuellement normales ; les pratiques d'hygiène standard restent de mise.",
        "symptoms": "Symptômes",
        "prevention": "Prévention",
        "seek_help": "Quand consulter",
        "current_risk_in": "Risque actuel à",
        "real_history": "Affichage de l'historique RÉEL enregistré par l'ESP32",
        "sim_history": "Aucun historique réel enregistré trouvé pour l'instant — affichage de données de tendance simulées à la place.",
        "events_log": "Journal des Événements de Contamination",
        "events_note": "Ce journal compte les événements de contamination distincts — chaque fois que le score de risque est passé à un niveau Élevé ou Critique — plutôt que chaque relevé élevé individuel.",
        "high_events": "Événements à Haut Risque",
        "critical_events": "Événements à Risque Critique",
        "peak_risk": "Risque Maximal Enregistré",
        "period_covered": "Période Couverte",
        "days": "jour(s)",
        "readings_analyzed": "relevés analysés",
        "data_source": "Source des données",
        "trend_chart": "Graphique de Tendance",
        "map_deep_dive": "Analyse Détaillée de Zone : En Direct + Historique Passé",
        "map_deep_dive_select": "Sélectionnez une zone pour voir sa lecture en direct et son historique de contamination",
        "right_now": "En Ce Moment",
        "past": "Derniers",
        "no_high_events": "Aucun événement de contamination à haut risque enregistré durant cette période.",
        "critical_events_msg": "Cette zone a atteint des niveaux de contamination CRITIQUES {n} fois au cours des {d} dernier(s) jour(s). Surveillance continue et précautions recommandées.",
        "high_events_msg": "Cette zone est passée en Risque Élevé {n} fois au cours des {d} dernier(s) jour(s).",
        "live_col": "Capteur en direct ?",
    },
}

# Disease safety info + general precautions, translated per language.
DISEASE_INFO = {
    "English": {
        "precautions": [
            "Boil drinking water for at least 1 minute, or use certified purification tablets/filters, whenever turbidity or bacterial alerts are active.",
            "Store treated water in clean, covered containers — avoid dipping hands or shared cups directly into storage containers.",
            "Wash hands with soap for at least 20 seconds before eating/cooking and after using the toilet.",
            "Avoid bathing, swimming, or washing utensils directly in flagged high-risk water sources.",
            "Keep drinking water sources away from latrines, drainage, and livestock areas.",
            "Report visibly discolored, foul-smelling, or unusually cloudy water to local health authorities immediately.",
            "During heavy rainfall, treat all open water sources as higher-risk until sensor readings normalize.",
        ],
        "hook": [
            "Sudden watery diarrhea and rapid dehydration — spreads fast in a village within hours.",
            "Long fever and weakness that can keep a child out of school and a parent out of work for weeks.",
            "The most common water-borne illness — mild for some, dangerous for young children and the elderly.",
            "Blood in the stool is a warning sign that needs medical attention, not home remedies alone.",
            "Can silently damage the liver for weeks before yellowing of the eyes and skin appears.",
        ],
        "diseases": {
            "Cholera": {"icon": "🦠", "symptoms": "Sudden watery diarrhea, vomiting, rapid dehydration.",
                        "prevention": "Drink only boiled/treated water; avoid raw or undercooked seafood from affected areas.",
                        "seek_help": "Seek medical care immediately if severe watery diarrhea or signs of dehydration (dizziness, dry mouth, reduced urination) appear."},
            "Typhoid": {"icon": "🌡️", "symptoms": "Prolonged fever, weakness, stomach pain, headache.",
                        "prevention": "Practice good hand hygiene; avoid street food/water of unknown source in affected zones.",
                        "seek_help": "See a doctor if fever persists beyond 2–3 days, especially alongside stomach pain."},
            "Diarrhea": {"icon": "💧", "symptoms": "Frequent loose stools, cramping, mild fever.",
                         "prevention": "Maintain safe drinking water and food hygiene; wash hands regularly.",
                         "seek_help": "Use oral rehydration salts (ORS); seek care if symptoms last more than 2 days or worsen."},
            "Dysentery": {"icon": "🩸", "symptoms": "Bloody or mucus-mixed diarrhea, abdominal cramps, fever.",
                          "prevention": "Avoid contaminated water sources; ensure food is thoroughly cooked and served hot.",
                          "seek_help": "Seek medical attention promptly if blood is visible in stool."},
            "Hepatitis A": {"icon": "🫀", "symptoms": "Fatigue, nausea, abdominal pain, jaundice (yellowing of skin/eyes).",
                            "prevention": "Vaccination where available; avoid raw shellfish and untreated water in affected areas.",
                            "seek_help": "Consult a doctor if jaundice, dark urine, or persistent fatigue develop."},
        },
    },
    "हिन्दी (Hindi)": {
        "precautions": [
            "जब भी टर्बिडिटी या बैक्टीरिया चेतावनी सक्रिय हो, पीने का पानी कम से कम 1 मिनट उबालें या प्रमाणित शुद्धिकरण टैबलेट/फिल्टर का उपयोग करें।",
            "शुद्ध किए गए पानी को साफ, ढके हुए बर्तनों में रखें — भंडारण बर्तनों में सीधे हाथ या साझा कप न डुबोएं।",
            "खाने/पकाने से पहले और शौचालय के बाद कम से कम 20 सेकंड तक साबुन से हाथ धोएं।",
            "चिन्हित उच्च-जोखिम वाले जल स्रोतों में सीधे नहाने, तैरने या बर्तन धोने से बचें।",
            "पीने के पानी के स्रोतों को शौचालय, जल निकासी और पशुधन क्षेत्रों से दूर रखें।",
            "स्पष्ट रूप से रंगीन, दुर्गंधयुक्त, या असामान्य रूप से गंदे पानी की सूचना तुरंत स्थानीय स्वास्थ्य अधिकारियों को दें।",
            "भारी बारिश के दौरान, सेंसर रीडिंग सामान्य होने तक सभी खुले जल स्रोतों को अधिक जोखिम वाला मानें।",
        ],
        "hook": [
            "अचानक पानी जैसा दस्त और तेज़ निर्जलीकरण — गांव में घंटों में तेज़ी से फैलता है।",
            "लंबा बुखार और कमजोरी जो हफ्तों तक बच्चे को स्कूल और माता-पिता को काम से दूर रख सकती है।",
            "सबसे आम जल-जनित बीमारी — कुछ के लिए हल्की, छोटे बच्चों और बुजुर्गों के लिए खतरनाक।",
            "मल में खून एक चेतावनी संकेत है जिसके लिए घरेलू उपचार नहीं, चिकित्सकीय ध्यान चाहिए।",
            "आंखों और त्वचा के पीले होने से पहले हफ्तों तक चुपचाप लिवर को नुकसान पहुंचा सकता है।",
        ],
        "diseases": {
            "Cholera": {"icon": "🦠", "symptoms": "अचानक पानी जैसा दस्त, उल्टी, तेज़ निर्जलीकरण।",
                        "prevention": "केवल उबला/शुद्ध पानी पिएं; प्रभावित क्षेत्रों से कच्चा या अधपका समुद्री भोजन न खाएं।",
                        "seek_help": "गंभीर पानी जैसा दस्त या निर्जलीकरण के लक्षण (चक्कर आना, मुंह सूखना, कम पेशाब) दिखने पर तुरंत चिकित्सा सहायता लें।"},
            "Typhoid": {"icon": "🌡️", "symptoms": "लंबे समय तक बुखार, कमजोरी, पेट दर्द, सिरदर्द।",
                        "prevention": "अच्छी हाथ स्वच्छता अपनाएं; प्रभावित क्षेत्रों में अज्ञात स्रोत का स्ट्रीट फूड/पानी न लें।",
                        "seek_help": "यदि बुखार 2-3 दिनों से अधिक रहे, विशेष रूप से पेट दर्द के साथ, तो डॉक्टर को दिखाएं।"},
            "Diarrhea": {"icon": "💧", "symptoms": "बार-बार पतला मल, ऐंठन, हल्का बुखार।",
                         "prevention": "सुरक्षित पेयजल और भोजन स्वच्छता बनाए रखें; नियमित रूप से हाथ धोएं।",
                         "seek_help": "ओआरएस का उपयोग करें; लक्षण 2 दिनों से अधिक रहने या बिगड़ने पर चिकित्सा सहायता लें।"},
            "Dysentery": {"icon": "🩸", "symptoms": "खून या बलगम मिश्रित दस्त, पेट में ऐंठन, बुखार।",
                          "prevention": "दूषित जल स्रोतों से बचें; सुनिश्चित करें कि भोजन अच्छी तरह पका हो और गर्म परोसा जाए।",
                          "seek_help": "मल में खून दिखने पर तुरंत चिकित्सा सहायता लें।"},
            "Hepatitis A": {"icon": "🫀", "symptoms": "थकान, मतली, पेट दर्द, पीलिया (त्वचा/आंखों का पीला पड़ना)।",
                            "prevention": "जहां उपलब्ध हो टीकाकरण कराएं; प्रभावित क्षेत्रों में कच्चा शेलफिश और अशुद्ध पानी से बचें।",
                            "seek_help": "पीलिया, गहरे रंग का पेशाब, या लगातार थकान होने पर डॉक्टर से सलाह लें।"},
        },
    },
    "తెలుగు (Telugu)": {
        "precautions": [
            "టర్బిడిటీ లేదా బ్యాక్టీరియా హెచ్చరికలు యాక్టివ్‌గా ఉన్నప్పుడు, తాగునీటిని కనీసం 1 నిమిషం మరిగించండి లేదా ధృవీకరించబడిన శుద్ధి మాత్రలు/ఫిల్టర్లు వాడండి.",
            "శుద్ధి చేసిన నీటిని శుభ్రమైన, మూత ఉన్న పాత్రల్లో నిల్వ చేయండి — నిల్వ పాత్రల్లో నేరుగా చేతులు లేదా షేర్డ్ కప్పులు ముంచవద్దు.",
            "తినడానికి/వండటానికి ముందు మరియు మరుగుదొడ్డి వాడిన తర్వాత కనీసం 20 సెకన్లు సబ్బుతో చేతులు కడుక్కోండి.",
            "గుర్తించబడిన అధిక-ప్రమాద నీటి వనరుల్లో నేరుగా స్నానం చేయడం, ఈత కొట్టడం లేదా పాత్రలు కడగడం మానుకోండి.",
            "తాగునీటి వనరులను మరుగుదొడ్లు, డ్రైనేజీ మరియు పశువుల ప్రాంతాలకు దూరంగా ఉంచండి.",
            "స్పష్టంగా రంగు మారిన, దుర్వాసన వచ్చే, లేదా అసాధారణంగా మురికిగా ఉన్న నీటిని వెంటనే స్థానిక ఆరోగ్య అధికారులకు తెలియజేయండి.",
            "భారీ వర్షం సమయంలో, సెన్సార్ రీడింగ్‌లు సాధారణ స్థితికి వచ్చేవరకు అన్ని బహిరంగ నీటి వనరులను అధిక-ప్రమాదకరంగా భావించండి.",
        ],
        "hook": [
            "అకస్మాత్తుగా నీటిలా విరేచనాలు మరియు వేగవంతమైన డీహైడ్రేషన్ — గ్రామంలో గంటల్లోనే వేగంగా వ్యాపిస్తుంది.",
            "దీర్ఘకాలిక జ్వరం మరియు నీరసం, ఇది పిల్లవాడిని పాఠశాలకు, తల్లిదండ్రులను పనికి వారాల తరబడి దూరం చేయవచ్చు.",
            "అత్యంత సాధారణ నీటి ద్వారా వ్యాపించే వ్యాధి — కొందరికి తేలికగా, చిన్నపిల్లలకు మరియు వృద్ధులకు ప్రమాదకరంగా ఉంటుంది.",
            "మలంలో రక్తం ఇంటి చిట్కాలు మాత్రమే కాకుండా వైద్య సహాయం అవసరమైన హెచ్చరిక సంకేతం.",
            "కళ్ళు మరియు చర్మం పసుపు రంగులోకి మారకముందే వారాల తరబడి నిశ్శబ్దంగా కాలేయాన్ని దెబ్బతీయవచ్చు.",
        ],
        "diseases": {
            "Cholera": {"icon": "🦠", "symptoms": "అకస్మాత్తుగా నీటిలా విరేచనాలు, వాంతులు, వేగవంతమైన డీహైడ్రేషన్.",
                        "prevention": "మరిగించిన/శుద్ధి చేసిన నీరు మాత్రమే తాగండి; ప్రభావిత ప్రాంతాల నుండి పచ్చి లేదా సరిగా వండని సముద్ర ఆహారాన్ని నివారించండి.",
                        "seek_help": "తీవ్రమైన నీటి విరేచనాలు లేదా డీహైడ్రేషన్ లక్షణాలు (తలతిరగడం, నోరు పొడిబారడం, తక్కువ మూత్రవిసర్జన) కనిపిస్తే వెంటనే వైద్య సహాయం పొందండి."},
            "Typhoid": {"icon": "🌡️", "symptoms": "దీర్ఘకాలిక జ్వరం, నీరసం, కడుపు నొప్పి, తలనొప్పి.",
                        "prevention": "మంచి చేతుల పరిశుభ్రత పాటించండి; ప్రభావిత ప్రాంతాల్లో తెలియని మూలం ఉన్న వీధి ఆహారం/నీటిని నివారించండి.",
                        "seek_help": "జ్వరం 2-3 రోజులకు మించి ఉంటే, ముఖ్యంగా కడుపు నొప్పితో పాటు, వైద్యుడిని సంప్రదించండి."},
            "Diarrhea": {"icon": "💧", "symptoms": "తరచుగా వదులైన మలం, తిమ్మిరి, తేలికపాటి జ్వరం.",
                         "prevention": "సురక్షితమైన తాగునీరు మరియు ఆహార పరిశుభ్రతను కాపాడుకోండి; క్రమం తప్పకుండా చేతులు కడుక్కోండి.",
                         "seek_help": "ORS వాడండి; లక్షణాలు 2 రోజులకు మించి ఉంటే లేదా తీవ్రమైతే వైద్య సహాయం పొందండి."},
            "Dysentery": {"icon": "🩸", "symptoms": "రక్తం లేదా శ్లేష్మంతో కూడిన విరేచనాలు, కడుపు తిమ్మిరి, జ్వరం.",
                          "prevention": "కలుషిత నీటి వనరులను నివారించండి; ఆహారం బాగా ఉడికించి వేడిగా వడ్డించేలా చూసుకోండి.",
                          "seek_help": "మలంలో రక్తం కనిపిస్తే వెంటనే వైద్య సహాయం పొందండి."},
            "Hepatitis A": {"icon": "🫀", "symptoms": "అలసట, వికారం, కడుపు నొప్పి, కామెర్లు (చర్మం/కళ్ళు పసుపు రంగులోకి మారడం).",
                            "prevention": "అందుబాటులో ఉన్న చోట టీకాలు వేయించుకోండి; ప్రభావిత ప్రాంతాల్లో పచ్చి షెల్ఫిష్ మరియు శుద్ధి చేయని నీటిని నివారించండి.",
                            "seek_help": "కామెర్లు, ముదురు రంగు మూత్రం లేదా నిరంతర అలసట కనిపిస్తే వైద్యుడిని సంప్రదించండి."},
        },
    },
    "Español (Spanish)": {
        "precautions": [
            "Hierva el agua potable durante al menos 1 minuto, o use tabletas/filtros de purificación certificados, cuando las alertas de turbidez o bacterias estén activas.",
            "Guarde el agua tratada en recipientes limpios y cubiertos — evite sumergir las manos o tazas compartidas directamente en los recipientes de almacenamiento.",
            "Lávese las manos con jabón durante al menos 20 segundos antes de comer/cocinar y después de usar el baño.",
            "Evite bañarse, nadar o lavar utensilios directamente en fuentes de agua marcadas como de alto riesgo.",
            "Mantenga las fuentes de agua potable alejadas de letrinas, drenajes y zonas de ganado.",
            "Reporte de inmediato a las autoridades de salud locales cualquier agua visiblemente descolorida, maloliente o inusualmente turbia.",
            "Durante lluvias intensas, trate todas las fuentes de agua abiertas como de mayor riesgo hasta que las lecturas de los sensores se normalicen.",
        ],
        "hook": [
            "Diarrea acuosa repentina y deshidratación rápida — se propaga rápido en un pueblo en cuestión de horas.",
            "Fiebre prolongada y debilidad que pueden mantener a un niño fuera de la escuela y a un padre fuera del trabajo durante semanas.",
            "La enfermedad hídrica más común — leve para algunos, peligrosa para niños pequeños y ancianos.",
            "La sangre en las heces es una señal de advertencia que requiere atención médica, no solo remedios caseros.",
            "Puede dañar silenciosamente el hígado durante semanas antes de que aparezca el color amarillento en los ojos y la piel.",
        ],
        "diseases": {
            "Cholera": {"icon": "🦠", "symptoms": "Diarrea acuosa repentina, vómitos, deshidratación rápida.",
                        "prevention": "Beba solo agua hervida/tratada; evite mariscos crudos o poco cocidos de zonas afectadas.",
                        "seek_help": "Busque atención médica de inmediato si aparece diarrea acuosa intensa o signos de deshidratación (mareo, boca seca, poca orina)."},
            "Typhoid": {"icon": "🌡️", "symptoms": "Fiebre prolongada, debilidad, dolor de estómago, dolor de cabeza.",
                        "prevention": "Practique buena higiene de manos; evite comida callejera/agua de origen desconocido en zonas afectadas.",
                        "seek_help": "Consulte a un médico si la fiebre persiste más de 2-3 días, especialmente con dolor de estómago."},
            "Diarrhea": {"icon": "💧", "symptoms": "Heces sueltas frecuentes, cólicos, fiebre leve.",
                         "prevention": "Mantenga agua potable segura e higiene alimentaria; lávese las manos con regularidad.",
                         "seek_help": "Use sales de rehidratación oral (SRO); busque atención si los síntomas duran más de 2 días o empeoran."},
            "Dysentery": {"icon": "🩸", "symptoms": "Diarrea con sangre o moco, cólicos abdominales, fiebre.",
                          "prevention": "Evite fuentes de agua contaminadas; asegúrese de que la comida esté bien cocida y se sirva caliente.",
                          "seek_help": "Busque atención médica de inmediato si hay sangre visible en las heces."},
            "Hepatitis A": {"icon": "🫀", "symptoms": "Fatiga, náuseas, dolor abdominal, ictericia (color amarillento de piel/ojos).",
                            "prevention": "Vacúnese donde esté disponible; evite mariscos crudos y agua no tratada en zonas afectadas.",
                            "seek_help": "Consulte a un médico si aparece ictericia, orina oscura o fatiga persistente."},
        },
    },
    "Français (French)": {
        "precautions": [
            "Faites bouillir l'eau potable pendant au moins 1 minute, ou utilisez des comprimés/filtres de purification certifiés, lorsque des alertes de turbidité ou bactériennes sont actives.",
                "Conservez l'eau traitée dans des récipients propres et couverts — évitez de plonger les mains ou des tasses partagées directement dans les récipients de stockage.",
            "Lavez-vous les mains au savon pendant au moins 20 secondes avant de manger/cuisiner et après être allé aux toilettes.",
            "Évitez de vous baigner, de nager ou de laver des ustensiles directement dans des sources d'eau signalées à haut risque.",
            "Gardez les sources d'eau potable éloignées des latrines, des drainages et des zones d'élevage.",
            "Signalez immédiatement aux autorités sanitaires locales toute eau visiblement décolorée, malodorante ou anormalement trouble.",
            "En cas de fortes pluies, considérez toutes les sources d'eau ouvertes comme à plus haut risque jusqu'à normalisation des relevés des capteurs.",
        ],
        "hook": [
            "Diarrhée aqueuse soudaine et déshydratation rapide — se propage vite dans un village en quelques heures.",
            "Fièvre prolongée et faiblesse pouvant tenir un enfant éloigné de l'école et un parent du travail pendant des semaines.",
            "La maladie hydrique la plus courante — bénigne pour certains, dangereuse pour les jeunes enfants et les personnes âgées.",
            "Du sang dans les selles est un signal d'alerte nécessitant une attention médicale, pas seulement des remèdes maison.",
            "Peut endommager silencieusement le foie pendant des semaines avant l'apparition d'un jaunissement des yeux et de la peau.",
        ],
        "diseases": {
            "Cholera": {"icon": "🦠", "symptoms": "Diarrhée aqueuse soudaine, vomissements, déshydratation rapide.",
                        "prevention": "Buvez uniquement de l'eau bouillie/traitée ; évitez les fruits de mer crus ou insuffisamment cuits provenant de zones touchées.",
                        "seek_help": "Consultez immédiatement un médecin en cas de diarrhée aqueuse sévère ou de signes de déshydratation (vertiges, bouche sèche, urines réduites)."},
            "Typhoid": {"icon": "🌡️", "symptoms": "Fièvre prolongée, faiblesse, douleurs d'estomac, maux de tête.",
                        "prevention": "Pratiquez une bonne hygiène des mains ; évitez la nourriture de rue/l'eau d'origine inconnue dans les zones touchées.",
                        "seek_help": "Consultez un médecin si la fièvre persiste plus de 2 à 3 jours, surtout avec des douleurs d'estomac."},
            "Diarrhea": {"icon": "💧", "symptoms": "Selles molles fréquentes, crampes, fièvre légère.",
                         "prevention": "Maintenez une eau potable sûre et une bonne hygiène alimentaire ; lavez-vous régulièrement les mains.",
                         "seek_help": "Utilisez des sels de réhydratation orale (SRO) ; consultez si les symptômes durent plus de 2 jours ou s'aggravent."},
            "Dysentery": {"icon": "🩸", "symptoms": "Diarrhée sanglante ou mêlée de mucus, crampes abdominales, fièvre.",
                          "prevention": "Évitez les sources d'eau contaminées ; assurez-vous que les aliments sont bien cuits et servis chauds.",
                          "seek_help": "Consultez rapidement un médecin si du sang est visible dans les selles."},
            "Hepatitis A": {"icon": "🫀", "symptoms": "Fatigue, nausées, douleurs abdominales, jaunisse (jaunissement de la peau/des yeux).",
                            "prevention": "Vaccination si disponible ; évitez les crustacés crus et l'eau non traitée dans les zones touchées.",
                            "seek_help": "Consultez un médecin en cas de jaunisse, d'urines foncées ou de fatigue persistante."},
        },
    },
}
 
DISEASE_KEYS = ["Cholera", "Typhoid", "Diarrhea", "Dysentery", "Hepatitis A"]
 
# =========================================================
# SESSION STATE INIT
# =========================================================
defaults = {
    "language": "English",
    "temp_unit": "Celsius (°C)",
    "seed_offset": 0,
    "last_sms_sent_score": None,
    "sms_log": [],
    "nav_page": "Home",
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v
 
# =========================================================
# HELPER FUNCTIONS
# =========================================================
def c_to_f(c):
    return c * 9 / 5 + 32
 
 
def format_temp(value_c):
    if st.session_state.temp_unit.startswith("Fahrenheit"):
        return f"{c_to_f(value_c):.1f} °F"
    return f"{value_c:.1f} °C"
 
 
def get_risk_label(score):
    T = TRANSLATIONS[st.session_state.language]
    if score < 25:
        return T["low_risk"], "#2E7D53"
    elif score < 50:
        return T["moderate_risk"], "#E9A23B"
    elif score < 75:
        return T["high_risk"], "#E07A2C"
    else:
        return T["critical_risk"], "#C0392B"
 
 
def generate_simulated_sensor_data(zone_name, offset=0):
    zone_seed = abs(hash(zone_name)) % 1000
    rng = np.random.default_rng(zone_seed + offset + int(datetime.now().timestamp() // 10))
    return {
        "water_temp_c": rng.normal(28, 3),
        "ph": rng.normal(7.0, 0.6),
        "turbidity": max(0, rng.normal(8, 5)),
        "tds": max(0, rng.normal(450, 150)),
        "rainfall": max(0, rng.exponential(8)),
        "bacteria": max(0, rng.normal(150, 100)),
        "humidity": np.clip(rng.normal(70, 10), 30, 100),
        "ambient_temp_c": rng.normal(31, 4),
        "timestamp": None,
    }
 
 
def get_sensor_data(zone_name, firebase_key, offset=0):
    live_data, err = fetch_live_reading(firebase_key)
    if live_data is not None:
        return live_data, True, None
    return generate_simulated_sensor_data(zone_name, offset), False, err
 
 
def compute_disease_risks(sensors):
    ph = sensors["ph"]
    turb = sensors["turbidity"]
    bact = sensors["bacteria"]
    rain = sensors["rainfall"]
    wtemp = sensors["water_temp_c"]
    humidity = sensors["humidity"]
 
    ph_risk = np.clip(abs(ph - 7.0) * 25, 0, 100)
    turb_risk = np.clip(turb * 4, 0, 100)
    bact_risk = np.clip(bact / 4, 0, 100)
    rain_risk = np.clip(rain * 3, 0, 100)
    temp_risk = np.clip((wtemp - 25) * 6, 0, 100)
    humidity_risk = np.clip((humidity - 60) * 1.5, 0, 100)
 
    risks = {
        "Cholera":    0.35 * bact_risk + 0.25 * rain_risk + 0.2 * turb_risk + 0.2 * ph_risk,
        "Typhoid":    0.4 * bact_risk + 0.3 * turb_risk + 0.15 * rain_risk + 0.15 * temp_risk,
        "Diarrhea":   0.3 * bact_risk + 0.25 * turb_risk + 0.25 * rain_risk + 0.2 * humidity_risk,
        "Dysentery":  0.35 * bact_risk + 0.3 * turb_risk + 0.2 * rain_risk + 0.15 * ph_risk,
        "Hepatitis A":0.3 * bact_risk + 0.3 * rain_risk + 0.2 * turb_risk + 0.2 * temp_risk,
    }
    for k in risks:
        risks[k] = float(np.clip(risks[k] + np.random.normal(0, 3), 0, 100))
    return risks
 
 
def fetch_real_historical_data(max_records=2000):
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
 
 
def generate_historical_data(zone_name, days=14):
    zone_seed = abs(hash(zone_name)) % 1000
    rng = np.random.default_rng(zone_seed)
    dates = pd.date_range(end=datetime.now(), periods=days * 24, freq="h")
    base_bact = np.clip(100 + np.cumsum(rng.normal(2, 8, len(dates))), 0, None)
    base_turb = np.clip(5 + np.cumsum(rng.normal(0.1, 1.5, len(dates))), 0, None)
    base_ph = np.clip(7 + np.cumsum(rng.normal(0, 0.05, len(dates))), 5, 9)
    base_rain = np.clip(rng.exponential(3, len(dates)), 0, None)
    base_wtemp = 28 + 3 * np.sin(np.linspace(0, 8 * np.pi, len(dates))) + rng.normal(0, 0.5, len(dates))
    base_ambient = 31 + 4 * np.sin(np.linspace(0, 8 * np.pi, len(dates))) + rng.normal(0, 0.7, len(dates))
    df = pd.DataFrame({
        "datetime": dates,
        "bacteria": base_bact,
        "turbidity": base_turb,
        "ph": base_ph,
        "rainfall": base_rain,
        "water_temp_c": base_wtemp,
        "ambient_temp_c": base_ambient,
    })
    df["overall_risk"] = np.clip(
        0.4 * (df["bacteria"] / 4) + 0.3 * (df["turbidity"] * 4) + 0.3 * (df["rainfall"] * 3),
        0, 100
    )
    return df
 
 
ZONES_DATA = {
    "Zone A - Riverside Village":   {"population": 4200, "lat": 17.385, "lon": 78.486, "firebase_key": "zone_a"},
    "Zone B - Hillside Settlement": {"population": 2800, "lat": 17.405, "lon": 78.466, "firebase_key": "zone_b"},
    "Zone C - Lakeside Town":       {"population": 6100, "lat": 17.365, "lon": 78.506, "firebase_key": "zone_c"},
    "Zone D - Central District":    {"population": 9500, "lat": 17.395, "lon": 78.496, "firebase_key": "zone_d"},
    "Zone E - Floodplain Area":     {"population": 3300, "lat": 17.375, "lon": 78.476, "firebase_key": "zone_e"},
}
 
 
def count_contamination_events(df, column="overall_risk", threshold=50):
    if df is None or column not in df.columns or len(df) < 2:
        return 0
    above = df[column].fillna(0) >= threshold
    crossings = above & ~above.shift(1, fill_value=False)
    return int(crossings.sum())
 
 
def summarize_zone_history(zone_name, firebase_key, real_hist_df_available):
    if real_hist_df_available is not None and len(real_hist_df_available) >= 2:
        df = real_hist_df_available
        is_real = True
    else:
        df = generate_historical_data(zone_name)
        is_real = False
 
    high_events = count_contamination_events(df, "overall_risk", threshold=50)
    critical_events = count_contamination_events(df, "overall_risk", threshold=75)
    peak_risk = float(df["overall_risk"].max()) if len(df) else 0.0
    avg_risk = float(df["overall_risk"].mean()) if len(df) else 0.0
    span_days = (df["datetime"].max() - df["datetime"].min()).days if len(df) >= 2 else 0
 
    return {
        "is_real": is_real,
        "high_events": high_events,
        "critical_events": critical_events,
        "peak_risk": peak_risk,
        "avg_risk": avg_risk,
        "span_days": max(span_days, 1),
        "num_readings": len(df),
    }
 
 
# =========================================================
# VISUAL IDENTITY — CSS + FONTS
# =========================================================
def inject_css():
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,400;9..144,600;9..144,700&family=Noto+Serif:wght@600;700&family=Nunito:wght@400;600;700;800&family=Noto+Sans:wght@400;600;700&display=swap');
 
        html, body, [class*="css"], .stMarkdown, p, div, span, li {
            font-family: 'Nunito', 'Noto Sans', 'Noto Sans Devanagari', 'Noto Sans Telugu', sans-serif;
        }
        h1, h2, h3, .jal-display {
            font-family: 'Fraunces', 'Noto Serif', 'Noto Serif Devanagari', 'Noto Serif Telugu', serif !important;
            font-weight: 700 !important;
            letter-spacing: -0.01em;
        }
 
        :root {
            --jal-teal: #0F5C66;
            --jal-teal-dark: #0A3D44;
            --jal-teal-light: #E4F1F0;
            --jal-marigold: #E9A23B;
            --jal-marigold-light: #FBEAD1;
            --jal-cream: #FBF9F4;
            --jal-ink: #1F2D2F;
            --jal-danger: #C0392B;
            --jal-success: #2E7D53;
        }
 
        .stApp {
            background: var(--jal-cream);
        }
        section[data-testid="stSidebar"] {
            background: var(--jal-teal-dark);
        }
        section[data-testid="stSidebar"] * {
            color: #EAF3F2 !important;
        }
        section[data-testid="stSidebar"] .stSelectbox label,
        section[data-testid="stSidebar"] .stRadio label,
        section[data-testid="stSidebar"] .stTextInput label,
        section[data-testid="stSidebar"] .stSlider label,
        section[data-testid="stSidebar"] .stCheckbox label {
            color: #CFE3E1 !important;
            font-weight: 600;
        }
 
        .jal-brand {
            display: flex;
            align-items: center;
            gap: 12px;
            padding: 6px 4px 18px 4px;
            border-bottom: 1px solid rgba(255,255,255,0.15);
            margin-bottom: 14px;
        }
        .jal-brand-icon {
            font-size: 30px;
        }
        .jal-brand-name {
            font-family: 'Fraunces', serif;
            font-size: 22px;
            font-weight: 700;
            color: #FFFFFF !important;
            line-height: 1.1;
        }
        .jal-brand-tag {
            font-size: 12px;
            color: #A9CFCB !important;
            letter-spacing: 0.03em;
        }
 
        /* ---- Hero ---- */
        .jal-hero {
            background: linear-gradient(135deg, var(--jal-teal) 0%, var(--jal-teal-dark) 100%);
            border-radius: 22px;
            padding: 48px 44px;
            color: #FFFFFF;
            position: relative;
            overflow: hidden;
            margin-bottom: 28px;
        }
        .jal-hero::after {
            content: "";
            position: absolute;
            right: -60px;
            bottom: -80px;
            width: 320px;
            height: 320px;
            background: radial-gradient(circle, rgba(233,162,59,0.35) 0%, rgba(233,162,59,0) 70%);
        }
        .jal-hero-eyebrow {
            display: inline-block;
            background: rgba(233,162,59,0.2);
            color: var(--jal-marigold);
            border: 1px solid rgba(233,162,59,0.5);
            padding: 5px 14px;
            border-radius: 999px;
            font-size: 13px;
            font-weight: 700;
            letter-spacing: 0.04em;
            margin-bottom: 18px;
        }
        .jal-hero h1 {
            color: #FFFFFF !important;
            font-size: 42px !important;
            line-height: 1.15 !important;
            max-width: 720px;
            margin-bottom: 16px !important;
        }
        .jal-hero p {
            color: #DCEDEB;
            font-size: 18px;
            max-width: 600px;
            line-height: 1.55;
        }
 
        /* ---- Cards ---- */
        .jal-card {
            background: #FFFFFF;
            border-radius: 16px;
            padding: 22px 22px;
            box-shadow: 0 2px 14px rgba(15,92,102,0.08);
            border: 1px solid rgba(15,92,102,0.08);
            height: 100%;
        }
        .jal-step-card {
            background: #FFFFFF;
            border-radius: 16px;
            padding: 24px 20px;
            border-top: 4px solid var(--jal-marigold);
            box-shadow: 0 2px 14px rgba(15,92,102,0.06);
            height: 100%;
        }
        .jal-step-num {
            font-family: 'Fraunces', serif;
            font-size: 30px;
            font-weight: 700;
            color: var(--jal-marigold);
        }
        .jal-step-title {
            font-family: 'Fraunces', serif;
            font-size: 19px;
            font-weight: 700;
            color: var(--jal-teal-dark);
            margin: 6px 0 8px 0;
        }
        .jal-step-text {
            font-size: 14.5px;
            color: #445;
            line-height: 1.5;
        }
 
        .jal-disease-card {
            background: #FFFFFF;
            border-radius: 16px;
            padding: 20px;
            box-shadow: 0 2px 14px rgba(15,92,102,0.07);
            border: 1px solid rgba(15,92,102,0.08);
            height: 100%;
        }
        .jal-disease-icon-wrap {
            width: 54px;
            height: 54px;
            border-radius: 14px;
            background: var(--jal-teal-light);
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 26px;
            margin-bottom: 12px;
        }
        .jal-disease-name {
            font-family: 'Fraunces', serif;
            font-weight: 700;
            font-size: 17px;
            color: var(--jal-teal-dark);
            margin-bottom: 6px;
        }
        .jal-disease-hook {
            font-size: 13.5px;
            color: #4A5A5C;
            line-height: 1.45;
        }
 
        .jal-eyebrow {
            display: inline-block;
            color: var(--jal-teal);
            background: var(--jal-teal-light);
            padding: 4px 12px;
            border-radius: 999px;
            font-size: 12.5px;
            font-weight: 800;
            letter-spacing: 0.04em;
            text-transform: uppercase;
            margin-bottom: 10px;
        }
 
        .jal-stat-num {
            font-family: 'Fraunces', serif;
            font-size: 34px;
            font-weight: 700;
            color: var(--jal-teal-dark);
        }
        .jal-stat-label {
            font-size: 13.5px;
            color: #5A6B6D;
            font-weight: 600;
        }
 
        .jal-cta-band {
            background: var(--jal-marigold-light);
            border: 1px solid rgba(233,162,59,0.5);
            border-radius: 18px;
            padding: 26px 30px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 20px;
            flex-wrap: wrap;
            margin-top: 10px;
        }
 
        .jal-badge-live {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            background: #E1F3E8;
            color: var(--jal-success);
            padding: 6px 14px;
            border-radius: 999px;
            font-weight: 700;
            font-size: 13px;
        }
        .jal-badge-sim {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            background: #FDF1DC;
            color: #9C6B12;
            padding: 6px 14px;
            border-radius: 999px;
            font-weight: 700;
            font-size: 13px;
        }
 
        div[data-testid="stMetric"] {
            background: #FFFFFF;
            border-radius: 14px;
            padding: 14px 16px;
            border: 1px solid rgba(15,92,102,0.08);
            box-shadow: 0 2px 10px rgba(15,92,102,0.05);
        }
 
        .stButton > button {
            border-radius: 999px !important;
            font-weight: 700 !important;
            border: none !important;
        }
        .stButton > button[kind="primary"] {
            background: var(--jal-marigold) !important;
            color: #2A1B04 !important;
        }
 
        #MainMenu {visibility: hidden;}
        footer {visibility: hidden;}
        </style>
        """,
        unsafe_allow_html=True,
    )
 
 
def water_wave_svg(color="#0F5C66"):
    return f"""
    <svg viewBox="0 0 1440 60" xmlns="http://www.w3.org/2000/svg" style="display:block;width:100%;">
        <path fill="{color}" fill-opacity="0.15" d="M0,32L60,26.7C120,21,240,11,360,16C480,21,600,43,720,48C840,53,960,43,1080,34.7C1200,27,1320,21,1380,18.7L1440,16L1440,60L0,60Z"></path>
    </svg>
    """
 
 
# =========================================================
# SIDEBAR — NAVIGATION + SETTINGS
# =========================================================
inject_css()
T = TRANSLATIONS[st.session_state.language]
DI = DISEASE_INFO[st.session_state.language]
 
nav_keys = ["Home", "Live", "Trends", "Map", "Safety", "Alerts"]
nav_labels = [T["nav_home"], T["nav_live"], T["nav_trends"], T["nav_map"], T["nav_safety"], T["nav_alerts"]]
nav_icons = ["house-heart", "speedometer2", "graph-up-arrow", "geo-alt", "shield-check", "bell"]
 
with st.sidebar:
    st.markdown(
        f"""
        <div class="jal-brand">
            <div class="jal-brand-icon">💧</div>
            <div>
                <div class="jal-brand-name">{T['brand']}</div>
                <div class="jal-brand-tag">{T['brand_tagline']}</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
 
    if OPTION_MENU_AVAILABLE:
        chosen_label = option_menu(
            menu_title=None,
            options=nav_labels,
            icons=nav_icons,
            default_index=nav_keys.index(st.session_state.nav_page) if st.session_state.nav_page in nav_keys else 0,
            styles={
                "container": {"padding": "0", "background-color": "transparent"},
                "icon": {"color": "#E9A23B", "font-size": "16px"},
                "nav-link": {
                    "font-size": "15px",
                    "font-weight": "600",
                    "color": "#EAF3F2",
                    "text-align": "left",
                    "margin": "3px 0",
                    "border-radius": "10px",
                    "padding": "10px 12px",
                },
                "nav-link-selected": {"background-color": "#0F5C66", "color": "#FFFFFF"},
            },
        )
        st.session_state.nav_page = nav_keys[nav_labels.index(chosen_label)]
    else:
        chosen_label = st.radio("Menu", options=nav_labels, label_visibility="collapsed")
        st.session_state.nav_page = nav_keys[nav_labels.index(chosen_label)]
 
    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
 
    with st.expander("⚙️ " + T["settings"], expanded=False):
        lang = st.selectbox(
            T["language"],
            options=list(TRANSLATIONS.keys()),
            index=list(TRANSLATIONS.keys()).index(st.session_state.language),
            key="lang_select",
        )
        if lang != st.session_state.language:
            st.session_state.language = lang
            st.rerun()
 
        temp_unit = st.radio(
            T["temp_unit"],
            options=["Celsius (°C)", "Fahrenheit (°F)"],
            index=0 if st.session_state.temp_unit.startswith("Celsius") else 1,
            horizontal=True,
        )
        st.session_state.temp_unit = temp_unit
 
        selected_zone = st.selectbox(T["select_zone"], options=list(ZONES_DATA.keys()), key="zone_select")
 
        if FIREBASE_AVAILABLE:
            st.success("🟢 " + T["firebase_connected"])
        else:
            st.error(f"🔴 {T['firebase_not_connected']}: {FIREBASE_INIT_ERROR}")
 
        auto_refresh = st.checkbox(T["auto_refresh"], value=False)
        if st.button(T["refresh"], use_container_width=True):
            st.session_state.seed_offset += 1
            st.rerun()
 
        st.markdown("---")
        st.markdown(f"**{T['sms_settings']}**")
        st.caption(f"{T['sms_target']}: `{ALERT_PHONE_NUMBER}`")
        twilio_sid = st.text_input(T["twilio_sid"], value=st.session_state.get("twilio_sid", ""), type="password", placeholder="ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx")
        twilio_token = st.text_input(T["twilio_token"], value=st.session_state.get("twilio_token", ""), type="password", placeholder="your_auth_token")
        twilio_from = st.text_input(T["twilio_from"], value=st.session_state.get("twilio_from", ""), placeholder="+1XXXXXXXXXX")
        st.session_state["twilio_sid"] = twilio_sid
        st.session_state["twilio_token"] = twilio_token
        st.session_state["twilio_from"] = twilio_from
        sms_threshold = st.slider(T["sms_threshold"], min_value=10, max_value=90, value=50, step=5)
        sms_auto = st.checkbox(T["sms_auto"], value=False)
 
    st.caption(T["footer"])
 
if "zone_select" not in st.session_state:
    st.session_state["zone_select"] = list(ZONES_DATA.keys())[0]
selected_zone = st.session_state["zone_select"]
 
# =========================================================
# DATA FETCH
# =========================================================
zone_info = ZONES_DATA[selected_zone]
sensors, is_live, fetch_error = get_sensor_data(selected_zone, zone_info["firebase_key"], st.session_state.seed_offset)
disease_risks = compute_disease_risks(sensors)
overall_risk = float(np.mean(list(disease_risks.values())))
hist_df = generate_historical_data(selected_zone)
alerted = {k: v for k, v in disease_risks.items() if v >= 50}
translated_disease_names = dict(zip(DISEASE_KEYS, T["diseases"]))
risk_label, risk_color = get_risk_label(overall_risk)
 
# Auto-SMS
if sms_auto and overall_risk >= sms_threshold:
    prev = st.session_state.last_sms_sent_score
    if prev is None or prev < sms_threshold:
        if twilio_sid and twilio_token and twilio_from:
            sms_body = build_sms_message(selected_zone, overall_risk, alerted or {"Overall": overall_risk}, sensors)
            ok, status = send_sms_alert(sms_body, twilio_sid, twilio_token, twilio_from)
            st.session_state.last_sms_sent_score = overall_risk
            st.session_state.sms_log.insert(0, {
                "time": datetime.now().strftime("%H:%M:%S"),
                "zone": selected_zone,
                "score": f"{overall_risk:.1f}",
                "status": f"✅ {T['sms_sent_ok']}" if ok else f"❌ {status}",
            })
else:
    if overall_risk < sms_threshold:
        st.session_state.last_sms_sent_score = None
 
PAGE = st.session_state.nav_page
 
# =========================================================
# PAGE: HOME
# =========================================================
if PAGE == "Home":
    st.markdown(
        f"""
        <div class="jal-hero">
            <span class="jal-hero-eyebrow">💧 {T['home_eyebrow']}</span>
            <h1 class="jal-display">{T['home_hero_title']}</h1>
            <p>{T['home_hero_sub']}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
 
    hcol1, hcol2, hspacer = st.columns([1.1, 1.3, 2.6])
    with hcol1:
        if st.button("💧 " + T["home_cta_primary"], type="primary", use_container_width=True):
            st.session_state.nav_page = "Live"
            st.rerun()
    with hcol2:
        if st.button("▾ " + T["home_cta_secondary"], use_container_width=True):
            st.session_state.nav_page = "Home"
 
    st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)
    s1, s2, s3 = st.columns(3)
    for col, num, label in [
        (s1, T["home_stat_1_num"], T["home_stat_1_label"]),
        (s2, T["home_stat_2_num"], T["home_stat_2_label"]),
        (s3, T["home_stat_3_num"], T["home_stat_3_label"]),
    ]:
        with col:
            st.markdown(
                f"""<div class="jal-card" style="text-align:center;">
                    <div class="jal-stat-num">{num}</div>
                    <div class="jal-stat-label">{label}</div>
                </div>""",
                unsafe_allow_html=True,
            )
 
    st.markdown("<div style='height:38px'></div>", unsafe_allow_html=True)
 
    st.markdown(f"<span class='jal-eyebrow'>{T['home_how_eyebrow']}</span>", unsafe_allow_html=True)
    st.markdown(f"### {T['home_how_title']}")
 
    steps = [
        ("01", T["home_how_1_title"], T["home_how_1_text"]),
        ("02", T["home_how_2_title"], T["home_how_2_text"]),
        ("03", T["home_how_3_title"], T["home_how_3_text"]),
        ("04", T["home_how_4_title"], T["home_how_4_text"]),
    ]
    step_cols = st.columns(4)
    for col, (num, stitle, stext) in zip(step_cols, steps):
        with col:
            st.markdown(
                f"""<div class="jal-step-card">
                    <div class="jal-step-num">{num}</div>
                    <div class="jal-step-title">{stitle}</div>
                    <div class="jal-step-text">{stext}</div>
                </div>""",
                unsafe_allow_html=True,
            )
 
    st.markdown("<div style='height:38px'></div>", unsafe_allow_html=True)
 
    st.markdown(f"<span class='jal-eyebrow'>{T['home_diseases_eyebrow']}</span>", unsafe_allow_html=True)
    st.markdown(f"### {T['home_diseases_title']}")
    st.markdown(f"<p style='color:#4A5A5C;max-width:680px;'>{T['home_diseases_sub']}</p>", unsafe_allow_html=True)
 
    dcols = st.columns(5)
    for col, dkey, hook in zip(dcols, DISEASE_KEYS, DI["hook"]):
        info = DI["diseases"][dkey]
        with col:
            st.markdown(
                f"""<div class="jal-disease-card">
                    <div class="jal-disease-icon-wrap">{info['icon']}</div>
                    <div class="jal-disease-name">{translated_disease_names[dkey]}</div>
                    <div class="jal-disease-hook">{hook}</div>
                </div>""",
                unsafe_allow_html=True,
            )
    st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)
    if st.button("📖 " + T["home_learn_more"]):
        st.session_state.nav_page = "Safety"
        st.rerun()
 
    st.markdown("<div style='height:38px'></div>", unsafe_allow_html=True)
 
    tcol1, tcol2 = st.columns([1, 1.3])
    with tcol1:
        st.markdown(
            f"""<div class="jal-card">
                <div style="font-size:40px;">🧑‍🤝‍🧑👵👴🧒</div>
                <h3 style="margin-top:10px;">{T['home_trust_title']}</h3>
                <p style="color:#4A5A5C; line-height:1.55;">{T['home_trust_text']}</p>
            </div>""",
            unsafe_allow_html=True,
        )
    with tcol2:
        st.markdown(
            f"""<div class="jal-card">
                <div style="font-size:40px;">🚰🧪🌧️</div>
                <h3 style="margin-top:10px;">{T['live_sensors']}</h3>
                <p style="color:#4A5A5C; line-height:1.55;">{T['water_temp']} · {T['ph_level']} · {T['turbidity']} ·
                {T['tds']} · {T['rainfall']} · {T['bacteria']} · {T['humidity']}</p>
            </div>""",
            unsafe_allow_html=True,
        )
 
    st.markdown("<div style='height:30px'></div>", unsafe_allow_html=True)
    st.markdown(
        f"""
        <div class="jal-cta-band">
            <div>
                <div style="font-family:'Fraunces',serif; font-weight:700; font-size:20px; color:#7A4A0A;">
                    {T['home_cta_footer_title']}
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if st.button("💧 " + T["home_cta_footer_btn"], type="primary"):
        st.session_state.nav_page = "Live"
        st.rerun()
 
    st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)
    st.caption(T["footer"])
 
# =========================================================
# PAGE: LIVE DASHBOARD
# =========================================================
elif PAGE == "Live":
    col_a, col_b, col_c = st.columns([2.2, 1, 1])
    with col_a:
        st.markdown(f"## 📍 {selected_zone}")
        st.markdown(
            f"**{T['population']}:** {zone_info['population']:,} &nbsp;&nbsp; "
            f"**{T['last_updated']}:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        if is_live:
            st.markdown(f"<span class='jal-badge-live'>🟢 {T['live_badge']}</span>", unsafe_allow_html=True)
        else:
            st.markdown(f"<span class='jal-badge-sim'>⚪ {T['sim_badge']}</span>", unsafe_allow_html=True)
    with col_b:
        st.metric(T["overall_risk"], f"{overall_risk:.1f} / 100")
    with col_c:
        st.markdown(
            f"""<div style="background-color:{risk_color}22;border:2px solid {risk_color};border-radius:14px;
            padding:16px;text-align:center;font-weight:800;font-size:18px;color:{risk_color};">{risk_label}</div>""",
            unsafe_allow_html=True,
        )
 
    if not is_live:
        st.warning(f"⚠️ {T['sim_banner']} {T['reason']}: {fetch_error}")
 
    st.markdown("---")
    st.markdown(f"### 📡 {T['live_sensors']}")
 
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
    st.markdown(f"### 🧬 {T['risk_prediction']}")
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
            marker_color=risk_df["Color"], text=[f"{v:.1f}" for v in risk_df["Risk Score"]], textposition="outside",
        ))
        fig_bar.update_layout(
            xaxis=dict(range=[0, 100], title="Risk Score (0-100)"),
            height=320, margin=dict(l=10, r=10, t=10, b=10),
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            font=dict(family="Nunito"),
        )
        st.plotly_chart(fig_bar, use_container_width=True)
 
    with col2:
        st.markdown(f"#### {T['overall_risk']}")
        fig_gauge = go.Figure(go.Indicator(
            mode="gauge+number", value=overall_risk,
            gauge={
                "axis": {"range": [0, 100]},
                "bar": {"color": risk_color},
                "steps": [
                    {"range": [0, 25], "color": "rgba(46,125,83,0.25)"},
                    {"range": [25, 50], "color": "rgba(233,162,59,0.25)"},
                    {"range": [50, 75], "color": "rgba(224,122,44,0.25)"},
                    {"range": [75, 100], "color": "rgba(192,57,43,0.25)"},
                ],
            },
            number={"suffix": " / 100"},
        ))
        fig_gauge.update_layout(height=320, margin=dict(l=10, r=10, t=30, b=10),
                                  paper_bgcolor="rgba(0,0,0,0)", font=dict(family="Nunito"))
        st.plotly_chart(fig_gauge, use_container_width=True)
 
# =========================================================
# PAGE: TRENDS & HISTORY
# =========================================================
elif PAGE == "Trends":
    st.markdown(f"## 📈 {T['trends']}")
 
    real_hist_df = fetch_real_historical_data()
    if real_hist_df is not None and len(real_hist_df) >= 2:
        st.markdown(f"<span class='jal-badge-live'>🟢 {T['real_history']} ({len(real_hist_df)})</span>", unsafe_allow_html=True)
        hist_df = real_hist_df
    else:
        st.markdown(f"<span class='jal-badge-sim'>⚪ {T['sim_history']}</span>", unsafe_allow_html=True)
 
    st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)
    tab_trend, tab_events = st.tabs([f"📊 {T['trend_chart']}", f"📋 {T['events_log']}"])
 
    with tab_trend:
        param_options = {
            T["bacteria"]: "bacteria", T["turbidity"]: "turbidity", T["ph_level"]: "ph",
            T["rainfall"]: "rainfall", T["water_temp"]: "water_temp_c",
            T["ambient_temp"]: "ambient_temp_c", T["overall_risk"]: "overall_risk",
        }
        selected_param_label = st.selectbox(T["param_trend"], options=list(param_options.keys()))
        selected_param = param_options[selected_param_label]
 
        plot_df = hist_df.copy()
        if selected_param in ["water_temp_c", "ambient_temp_c"] and st.session_state.temp_unit.startswith("Fahrenheit"):
            plot_df[selected_param] = c_to_f(plot_df[selected_param])
            y_title = selected_param_label.replace("°C", "°F")
        else:
            y_title = selected_param_label
 
        fig_line = px.line(plot_df, x="datetime", y=selected_param, labels={"datetime": "", selected_param: y_title})
        fig_line.update_traces(line_color="#0F5C66", line_width=3)
        fig_line.update_layout(height=350, margin=dict(l=10, r=10, t=10, b=10),
                                 paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font=dict(family="Nunito"))
        if selected_param == "overall_risk":
            fig_line.add_hline(y=50, line_dash="dash", line_color="#E9A23B", annotation_text=T["high_risk"])
            fig_line.add_hline(y=75, line_dash="dash", line_color="#C0392B", annotation_text=T["critical_risk"])
        st.plotly_chart(fig_line, use_container_width=True)
 
    with tab_events:
        st.info(T["events_note"])
        high_events = count_contamination_events(hist_df, "overall_risk", threshold=50)
        critical_events = count_contamination_events(hist_df, "overall_risk", threshold=75)
        span_days = max((hist_df["datetime"].max() - hist_df["datetime"].min()).days, 1) if len(hist_df) >= 2 else 1
        peak_risk = float(hist_df["overall_risk"].max()) if len(hist_df) else 0.0
 
        ec1, ec2, ec3, ec4 = st.columns(4)
        ec1.metric("⚠️ " + T["high_events"], high_events)
        ec2.metric("🔴 " + T["critical_events"], critical_events)
        ec3.metric("📈 " + T["peak_risk"], f"{peak_risk:.1f} / 100")
        ec4.metric("🗓️ " + T["period_covered"], f"{span_days} {T['days']}")
 
        src_label = T["real_history"] if (real_hist_df is not None and len(real_hist_df) >= 2) else T["sim_history"]
        st.caption(f"{T['data_source']}: {src_label} — {len(hist_df)} {T['readings_analyzed']}.")
 
# =========================================================
# PAGE: ZONE MAP
# =========================================================
elif PAGE == "Map":
    st.markdown(f"## 🗺️ {T['map_view']}")
 
    map_rows = []
    for zname, zinfo in ZONES_DATA.items():
        zsensors, z_is_live, _ = get_sensor_data(zname, zinfo["firebase_key"], st.session_state.seed_offset)
        zrisks = compute_disease_risks(zsensors)
        zoverall = float(np.mean(list(zrisks.values())))
        lvl, col = get_risk_label(zoverall)
        map_rows.append({
            "Zone": zname.split(" - ")[1] if " - " in zname else zname,
            "lat": zinfo["lat"], "lon": zinfo["lon"],
            "Risk Score": zoverall, "Risk Level": lvl,
            "Population": zinfo["population"], "Live": "🟢" if z_is_live else "⚪",
        })
    map_df = pd.DataFrame(map_rows)
 
    fig_map = px.scatter_mapbox(
        map_df, lat="lat", lon="lon", size="Risk Score", color="Risk Score",
        color_continuous_scale=["#2E7D53", "#E9A23B", "#E07A2C", "#C0392B"],
        range_color=[0, 100], size_max=35, zoom=11, hover_name="Zone",
        hover_data={"lat": False, "lon": False, "Risk Score": ":.1f", "Population": True, "Risk Level": True, "Live": True},
    )
    fig_map.update_layout(mapbox_style="open-street-map", margin=dict(l=0, r=0, t=0, b=0), height=420)
    st.plotly_chart(fig_map, use_container_width=True)
 
    st.dataframe(
        map_df[["Zone", "Population", "Risk Score", "Risk Level", "Live"]].rename(columns={
            "Zone": T["zone"], "Population": T["population"], "Risk Score": T["overall_risk"],
            "Risk Level": T["risk_level"], "Live": T["live_col"],
        }),
        use_container_width=True, hide_index=True,
    )
 
    st.markdown(f"#### 🔍 {T['map_deep_dive']}")
    detail_zone = st.selectbox(T["map_deep_dive_select"], options=list(ZONES_DATA.keys()),
                                 index=list(ZONES_DATA.keys()).index(selected_zone), key="map_detail_zone")
    detail_info = ZONES_DATA[detail_zone]
    detail_sensors, detail_is_live, detail_err = get_sensor_data(detail_zone, detail_info["firebase_key"], st.session_state.seed_offset)
    detail_risks = compute_disease_risks(detail_sensors)
    detail_overall = float(np.mean(list(detail_risks.values())))
    detail_lvl, detail_col = get_risk_label(detail_overall)
 
    real_hist_for_detail = fetch_real_historical_data()
    detail_summary = summarize_zone_history(
        detail_zone, detail_info["firebase_key"],
        real_hist_for_detail if real_hist_for_detail is not None and len(real_hist_for_detail) >= 2 else None,
    )
 
    dd1, dd2 = st.columns(2)
    with dd1:
        st.markdown(f"**📍 {detail_zone} — {T['right_now']}**")
        if detail_is_live:
            st.markdown(f"<span class='jal-badge-live'>🟢 {T['live_badge']}</span>", unsafe_allow_html=True)
        else:
            st.markdown(f"<span class='jal-badge-sim'>⚪ {T['sim_badge']}</span>", unsafe_allow_html=True)
        st.metric(T["risk_level"], f"{detail_overall:.1f} / 100", delta=detail_lvl)
        dd1a, dd1b, dd1c = st.columns(3)
        dd1a.metric(T["tds"], f"{detail_sensors['tds']:.0f}")
        dd1b.metric(T["turbidity"], f"{detail_sensors['turbidity']:.1f}")
        dd1c.metric(T["water_temp"], format_temp(detail_sensors['water_temp_c']))
 
    with dd2:
        st.markdown(f"**🕓 {detail_zone} — {T['past']} {detail_summary['span_days']} {T['days']}**")
        st.caption(T["real_history"] if detail_summary["is_real"] else T["sim_history"])
        de1, de2, de3 = st.columns(3)
        de1.metric(T["high_events"], f"{detail_summary['high_events']}x")
        de2.metric(T["critical_events"], f"{detail_summary['critical_events']}x")
        de3.metric(T["peak_risk"], f"{detail_summary['peak_risk']:.1f}/100")
 
        if detail_summary["high_events"] == 0:
            st.info("✅ " + T["no_high_events"])
        elif detail_summary["critical_events"] > 0:
            st.error("🚨 " + T["critical_events_msg"].format(n=detail_summary["critical_events"], d=detail_summary["span_days"]))
        else:
            st.warning("⚠️ " + T["high_events_msg"].format(n=detail_summary["high_events"], d=detail_summary["span_days"]))
 
# =========================================================
# PAGE: SAFETY GUIDE
# =========================================================
elif PAGE == "Safety":
    st.markdown(f"## 🛡️ {T['safety_title']}")
    st.caption(T["safety_sub"])
 
    safety_tab_general, safety_tab_disease = st.tabs([f"✅ {T['safety_tab_general']}", f"🧬 {T['safety_tab_disease']}"])
 
    with safety_tab_general:
        st.markdown(f"#### {T['safety_now_title']} **{selected_zone}**")
        if overall_risk >= 75:
            st.error("🚨 " + T["risk_msg_critical"])
        elif overall_risk >= 50:
            st.warning("⚠️ " + T["risk_msg_high"])
        elif overall_risk >= 25:
            st.info("ℹ️ " + T["risk_msg_moderate"])
        else:
            st.success("✅ " + T["risk_msg_low"])
 
        for tip in DI["precautions"]:
            st.markdown(f"- {tip}")
 
    with safety_tab_disease:
        disease_tab_objs = st.tabs([f"{DI['diseases'][d]['icon']} {translated_disease_names[d]}" for d in DISEASE_KEYS])
        for tab_obj, disease_key in zip(disease_tab_objs, DISEASE_KEYS):
            info = DI["diseases"][disease_key]
            score = disease_risks[disease_key]
            lvl, col = get_risk_label(score)
            with tab_obj:
                st.markdown(
                    f"**{T['current_risk_in']} {selected_zone}:** "
                    f"<span style='color:{col}; font-weight:700;'>{lvl} ({score:.1f}/100)</span>",
                    unsafe_allow_html=True,
                )
                st.markdown(f"**🤒 {T['symptoms']}:** {info['symptoms']}")
                st.markdown(f"**🛡️ {T['prevention']}:** {info['prevention']}")
                st.markdown(f"**🏥 {T['seek_help']}:** {info['seek_help']}")
 
# =========================================================
# PAGE: ALERTS & SMS
# =========================================================
elif PAGE == "Alerts":
    st.markdown(f"## 🚨 {T['alerts']}")
 
    if not alerted:
        st.success("✅ " + T["no_alerts"])
    else:
        for disease, score in alerted.items():
            lvl, col = get_risk_label(score)
            st.markdown(
                f"""<div style="background-color:{col}15;border-left:6px solid {col};border-radius:8px;
                padding:12px 18px;margin-bottom:8px;">
                <b>{T['alert_msg']} {translated_disease_names[disease]}</b> — {T['risk_level']}:
                <span style="color:{col}; font-weight:700;">{lvl} ({score:.1f}/100)</span>
                </div>""",
                unsafe_allow_html=True,
            )
        with st.expander("📋 " + T["recommendation"], expanded=True):
            for rec in [T["rec_1"], T["rec_2"], T["rec_3"], T["rec_4"], T["rec_5"]]:
                st.markdown(f"- {rec}")
 
    st.markdown("---")
    st.markdown(f"### 📱 {T['sms_settings']}")
 
    sms_preview_body = build_sms_message(selected_zone, overall_risk, alerted if alerted else {"Overall": overall_risk}, sensors)
    st.markdown(f"**{T['sms_preview']}** → `{ALERT_PHONE_NUMBER}`")
    st.code(sms_preview_body, language=None)
 
    col_sms1, col_sms2 = st.columns([1, 2])
    with col_sms1:
        send_now = st.button("📲 " + T["send_sms"], type="primary", use_container_width=True)
    with col_sms2:
        if not twilio_sid or not twilio_token or not twilio_from:
            st.warning("⚠️ " + T["sms_need_creds"])
 
    if send_now:
        if twilio_sid and twilio_token and twilio_from:
            ok, status = send_sms_alert(sms_preview_body, twilio_sid, twilio_token, twilio_from)
            st.session_state.sms_log.insert(0, {
                "time": datetime.now().strftime("%H:%M:%S"), "zone": selected_zone,
                "score": f"{overall_risk:.1f}", "status": f"✅ {T['sms_sent_ok']}" if ok else f"❌ {status}",
            })
            if ok:
                st.success(f"✅ {T['sms_sent_ok']} → {ALERT_PHONE_NUMBER} ({status})")
            else:
                st.error(f"❌ {T['sms_sent_fail']}: {status}")
        else:
            st.error(T["sms_need_creds"])
 
    if st.session_state.sms_log:
        st.markdown(f"**📋 {T['sms_log']}**")
        st.dataframe(pd.DataFrame(st.session_state.sms_log), use_container_width=True, hide_index=True)
 
# =========================================================
# AUTO REFRESH
# =========================================================
if PAGE == "Live" and st.session_state.get("_auto_refresh_flag", False):
    time.sleep(10)
    st.session_state.seed_offset += 1
    st.rerun()
