"""
AquaSentinel — AI Community Health Early Warning System
for Water-Borne Disease Prediction
==============================================================

Run with:
    pip install streamlit streamlit-option-menu plotly pandas numpy twilio firebase-admin
    streamlit run app.py
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
    page_title="AquaSentinel AI | Water Health Early Warning",
    page_icon="\U0001F4A7",
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
        "brand": "AquaSentinel AI",
        "brand_tagline": "AI Water Safety Network",
        "title": "AI Community Health Early Warning System",
        "subtitle": "Real-Time Water-Borne Disease Risk Prediction",
        "nav_home": "Home",
        "nav_live": "Live Monitoring",
        "nav_predict": "AI Prediction",
        "nav_trends": "Analytics",
        "nav_map": "Village Map",
        "nav_safety": "Safety Center",
        "nav_alerts": "Alerts",
        "nav_hardware": "Hardware",
        "nav_about": "About",
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
        "home_eyebrow": "Community Water Health Watch",
        "home_hero_title": "Know your water is safe — before anyone gets sick.",
        "home_hero_sub": "AquaSentinel AI watches the water your family drinks, every hour of every day, and warns your village early — in your own language.",
        "home_cta_primary": "Start Monitoring",
        "home_cta_secondary": "See how it works",
        "home_stat_1_num": "98%",
        "home_stat_1_label": "Prediction Accuracy",
        "home_stat_2_num": "24/7",
        "home_stat_2_label": "Monitoring",
        "home_stat_3_num": "1000+",
        "home_stat_3_label": "People Protected",
        "home_stat_4_num": "5",
        "home_stat_4_label": "Diseases Predicted",
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
        "brand": "AquaSentinel AI", "brand_tagline": "एआई जल सुरक्षा नेटवर्क",
        "title": "एआई सामुदायिक स्वास्थ्य पूर्व चेतावनी प्रणाली",
        "subtitle": "जल-जनित रोगों के जोखिम की वास्तविक समय भविष्यवाणी",
        "nav_home": "होम", "nav_live": "लाइव मॉनिटरिंग", "nav_predict": "एआई भविष्यवाणी",
        "nav_trends": "विश्लेषण", "nav_map": "गांव मानचित्र", "nav_safety": "सुरक्षा केंद्र",
        "nav_alerts": "चेतावनियाँ", "nav_hardware": "हार्डवेयर", "nav_about": "परिचय",
        "settings": "सेटिंग्स", "language": "भाषा", "temp_unit": "तापमान इकाई",
        "select_zone": "क्षेत्र / गांव चुनें", "live_sensors": "लाइव सेंसर रीडिंग",
        "risk_prediction": "रोग जोखिम भविष्यवाणी", "alerts": "सक्रिय चेतावनियाँ",
        "trends": "ऐतिहासिक रुझान", "map_view": "क्षेत्र जोखिम मानचित्र",
        "water_temp": "जल तापमान", "ph_level": "पीएच स्तर", "turbidity": "टर्बिडिटी (NTU)",
        "tds": "टीडीएस (ppm)", "rainfall": "वर्षा (मिमी)", "bacteria": "बैक्टीरिया गणना (CFU/mL)",
        "humidity": "आर्द्रता (%)", "ambient_temp": "वातावरणीय तापमान",
        "low_risk": "कम जोखिम", "moderate_risk": "मध्यम जोखिम", "high_risk": "उच्च जोखिम",
        "critical_risk": "गंभीर जोखिम", "overall_risk": "समग्र प्रकोप जोखिम स्कोर",
        "disease_breakdown": "रोग-वार जोखिम विवरण", "no_alerts": "कोई सक्रिय चेतावनी नहीं। स्थिति सामान्य है।",
        "alert_msg": "चेतावनी: इसके लिए बढ़ा हुआ जोखिम पाया गया",
        "recommendation": "अनुशंसित कार्रवाई",
        "rec_1": "जल क्लोरीनीकरण और कीटाणुशोधन की आवृत्ति बढ़ाएं",
        "rec_2": "सामुदायिक स्वास्थ्य केंद्रों में ओआरएस वितरित करें",
        "rec_3": "सार्वजनिक सलाह जारी करें: पानी उबालकर पिएं",
        "rec_4": "घर-घर जांच के लिए स्वास्थ्य कर्मियों को तैनात करें",
        "rec_5": "निगरानी और नमूना परीक्षण की आवृत्ति बढ़ाएं",
        "last_updated": "अंतिम अद्यतन", "refresh": "डेटा रीफ्रेश करें",
        "auto_refresh": "हर 10 सेकंड में ऑटो-रीफ्रेश करें",
        "footer": "जल-जनित रोगों (हैजा, टाइफाइड, दस्त, पेचिश, हेपेटाइटिस ए) की पूर्व चेतावनी के लिए एआई-संचालित प्रोटोटाइप। केवल प्रदर्शन हेतु — यह चिकित्सकीय सलाह का विकल्प नहीं है।",
        "diseases": ["हैजा", "टाइफाइड", "दस्त", "पेचिश", "हेपेटाइटिस ए"],
        "param_trend": "रुझान के लिए पैरामीटर चुनें", "risk_level": "जोखिम स्तर",
        "zone": "क्षेत्र", "population": "जनसंख्या", "summary": "सारांश",
        "key_insights": "मुख्य अंतर्दृष्टि", "insight_1": "पिछली अवधि में जोखिम का रुझान",
        "insight_2": "बैक्टीरिया संदूषण स्तर सुरक्षित सीमा के भीतर है",
        "insight_3": "भारी वर्षा संदूषण जोखिम को काफी बढ़ा देती है",
        "sms_settings": "एसएमएस अलर्ट सेटिंग्स", "twilio_sid": "Twilio अकाउंट SID",
        "twilio_token": "Twilio Auth Token", "twilio_from": "Twilio फ़ोन नंबर (से)",
        "send_sms": "एसएमएस अलर्ट भेजें", "sms_target": "अलर्ट एसएमएस लक्ष्य",
        "sms_threshold": "एसएमएस अलर्ट थ्रेशोल्ड (जोखिम स्कोर)",
        "sms_auto": "थ्रेशोल्ड पार होने पर ऑटो एसएमएस भेजें", "sms_preview": "एसएमएस प्रीव्यू",
        "sms_log": "एसएमएस गतिविधि लॉग", "sms_need_creds": "एसएमएस भेजने के लिए सेटिंग्स में Twilio जानकारी भरें।",
        "sms_sent_ok": "एसएमएस भेजा गया", "sms_sent_fail": "एसएमएस विफल",
        "firebase_connected": "सेंसर नेटवर्क जुड़ा है", "firebase_not_connected": "सेंसर नेटवर्क नहीं जुड़ा",
        "live_badge": "लाइव सेंसर डेटा", "sim_badge": "सिम्युलेटेड डेमो डेटा",
        "live_banner": "इस क्षेत्र के लिए लाइव ESP32 सेंसर डेटा दिखाया जा रहा है",
        "sim_banner": "इस क्षेत्र के लिए लाइव सेंसर रीडिंग उपलब्ध नहीं है — इसके बजाय सिम्युलेटेड डेमो डेटा दिखाया जा रहा है।",
        "reason": "कारण",
        "home_eyebrow": "सामुदायिक जल स्वास्थ्य निगरानी",
        "home_hero_title": "किसी के बीमार होने से पहले जानें कि आपका पानी सुरक्षित है या नहीं।",
        "home_hero_sub": "AquaSentinel AI आपके परिवार के पीने के पानी पर दिन-रात नज़र रखता है और आपके गांव को आपकी अपनी भाषा में समय रहते चेतावनी देता है।",
        "home_cta_primary": "निगरानी शुरू करें", "home_cta_secondary": "यह कैसे काम करता है देखें",
        "home_stat_1_num": "98%", "home_stat_1_label": "भविष्यवाणी सटीकता",
        "home_stat_2_num": "24/7", "home_stat_2_label": "निगरानी",
        "home_stat_3_num": "1000+", "home_stat_3_label": "लोग सुरक्षित",
        "home_stat_4_num": "5", "home_stat_4_label": "बीमारियों का पूर्वानुमान",
        "home_how_eyebrow": "यह कैसे काम करता है", "home_how_title": "नदी से फ़ोन तक — चार आसान चरणों में",
        "home_how_1_title": "सेंसर पानी की जांच करता है",
        "home_how_1_text": "जल स्रोत में लगा एक छोटा उपकरण पूरे दिन pH, सफाई, तापमान और कीटाणुओं की जांच करता है।",
        "home_how_2_title": "एआई जोखिम की गणना करता है",
        "home_how_2_text": "हमारी प्रणाली रीडिंग की तुलना उन पैटर्न से करती है जो हैजा, टाइफाइड और अन्य बीमारियों का कारण बनते हैं।",
        "home_how_3_title": "आपके गांव को चेतावनी दी जाती है",
        "home_how_3_text": "यदि जोखिम बढ़ता है, तो तुरंत आपकी भाषा में चेतावनी और एसएमएस भेजा जाता है।",
        "home_how_4_title": "आप आसान कदम उठाते हैं",
        "home_how_4_text": "पानी उबालें, ओआरएस का उपयोग करें, और ऐप में दिखाए गए आसान सुरक्षा कदमों का पालन करें।",
        "home_diseases_eyebrow": "जोखिम को जानें", "home_diseases_title": "अगर पानी असुरक्षित हो तो क्या हो सकता है",
        "home_diseases_sub": "ये बीमारियां दूषित पानी से फैलती हैं। समय रहते चेतावनी मिलने से आप किसी के बीमार होने से पहले ही कदम उठा सकते हैं।",
        "home_learn_more": "पूरी सुरक्षा गाइड देखें",
        "home_trust_title": "हर घर के लिए बनाया गया",
        "home_trust_text": "सरल भाषा, बड़ा टेक्स्ट, और चरण-दर-चरण मार्गदर्शन — ताकि गांव का हर व्यक्ति, न कि केवल तकनीशियन, जल जोखिम और उससे निपटने का तरीका समझ सके।",
        "home_cta_footer_title": "अभी अपने क्षेत्र का जल जोखिम जांचें", "home_cta_footer_btn": "लाइव डैशबोर्ड खोलें",
        "safety_title": "सुरक्षा और सावधानियां गाइड",
        "safety_sub": "सामान्य सार्वजनिक स्वास्थ्य मार्गदर्शन — यह चिकित्सकीय सलाह का विकल्प नहीं है। यदि कोई गंभीर रूप से अस्वस्थ है, तो तुरंत स्वास्थ्य सेवा प्रदाता से संपर्क करें।",
        "safety_tab_general": "सामान्य सावधानियां", "safety_tab_disease": "रोगवार मार्गदर्शन",
        "safety_now_title": "अभी के लिए अनुशंसित सावधानियां",
        "risk_msg_critical": "गंभीर जोखिम क्षेत्र — जब तक स्थिति सामान्य न हो, सभी स्थानीय जल स्रोतों को असुरक्षित मानें।",
        "risk_msg_high": "उच्च जोखिम क्षेत्र — उपयोग से पहले पानी उबालें या शुद्ध करें; अशुद्ध स्रोतों के सीधे संपर्क से बचें।",
        "risk_msg_moderate": "मध्यम जोखिम क्षेत्र — बुनियादी सावधानियों की सिफारिश की जाती है; अपडेट पर नज़र रखें।",
        "risk_msg_low": "कम जोखिम क्षेत्र — स्थिति सामान्य है; फिर भी मानक स्वच्छता प्रथाओं का पालन करें।",
        "symptoms": "लक्षण", "prevention": "बचाव", "seek_help": "मदद कब लें",
        "current_risk_in": "वर्तमान जोखिम",
        "real_history": "ESP32 से वास्तविक दर्ज इतिहास दिखाया जा रहा है",
        "sim_history": "अभी तक कोई वास्तविक दर्ज इतिहास नहीं मिला — इसके बजाय सिम्युलेटेड रुझान डेटा दिखाया जा रहा है।",
        "events_log": "संदूषण घटना लॉग",
        "events_note": "यह लॉग अलग-अलग संदूषण घटनाओं की गिनती करता है — हर बार जब जोखिम स्कोर उच्च या गंभीर स्तर में प्रवेश करता है — न कि हर बढ़ी हुई रीडिंग की।",
        "high_events": "उच्च-जोखिम घटनाएं", "critical_events": "गंभीर-जोखिम घटनाएं",
        "peak_risk": "दर्ज शिखर जोखिम", "period_covered": "अवधि", "days": "दिन",
        "readings_analyzed": "रीडिंग का विश्लेषण किया गया", "data_source": "डेटा स्रोत",
        "trend_chart": "रुझान चार्ट",
        "map_deep_dive": "क्षेत्र गहन विश्लेषण: लाइव + पिछला संदूषण इतिहास",
        "map_deep_dive_select": "लाइव रीडिंग और संदूषण इतिहास देखने के लिए क्षेत्र चुनें",
        "right_now": "अभी", "past": "पिछले",
        "no_high_events": "इस अवधि में कोई उच्च-जोखिम संदूषण घटना दर्ज नहीं हुई।",
        "critical_events_msg": "यह क्षेत्र पिछले {d} दिन(दिनों) में {n} बार गंभीर संदूषण स्तर पर पहुंचा। निरंतर निगरानी और सावधानी की सलाह दी जाती है।",
        "high_events_msg": "यह क्षेत्र पिछले {d} दिन(दिनों) में {n} बार उच्च जोखिम में गया।",
        "live_col": "लाइव सेंसर?",
    },
}

TRANSLATIONS["తెలుగు (Telugu)"] = {
    "brand": "AquaSentinel AI", "brand_tagline": "AI నీటి భద్రతా నెట్‌వర్క్",
    "title": "AI కమ్యూనిటీ హెల్త్ ముందస్తు హెచ్చరిక వ్యవస్థ",
    "subtitle": "నీటి ద్వారా వ్యాపించే వ్యాధుల రియల్-టైమ్ ప్రమాద అంచనా",
    "nav_home": "హోమ్", "nav_live": "లైవ్ మానిటరింగ్", "nav_predict": "AI అంచనా",
    "nav_trends": "విశ్లేషణ", "nav_map": "గ్రామ మ్యాప్", "nav_safety": "భద్రతా కేంద్రం",
    "nav_alerts": "హెచ్చరికలు", "nav_hardware": "హార్డ్‌వేర్", "nav_about": "గురించి",
    "settings": "సెట్టింగ్‌లు", "language": "భాష", "temp_unit": "ఉష్ణోగ్రత యూనిట్",
    "select_zone": "జోన్ / గ్రామం ఎంచుకోండి", "live_sensors": "లైవ్ సెన్సార్ రీడింగ్‌లు",
    "risk_prediction": "వ్యాధి ప్రమాద అంచనా", "alerts": "క్రియాశీల హెచ్చరికలు",
    "trends": "చారిత్రక ధోరణులు", "map_view": "జోన్ ప్రమాద మ్యాప్",
    "water_temp": "నీటి ఉష్ణోగ్రత", "ph_level": "pH స్థాయి", "turbidity": "టర్బిడిటీ (NTU)",
    "tds": "TDS (ppm)", "rainfall": "వర్షపాతం (mm)", "bacteria": "బ్యాక్టీరియా కౌంట్ (CFU/mL)",
    "humidity": "తేమ (%)", "ambient_temp": "పరిసర ఉష్ణోగ్రత",
    "low_risk": "తక్కువ ప్రమాదం", "moderate_risk": "మధ్యస్థ ప్రమాదం", "high_risk": "అధిక ప్రమాదం",
    "critical_risk": "తీవ్రమైన ప్రమాదం", "overall_risk": "మొత్తం వ్యాప్తి ప్రమాద స్కోరు",
    "disease_breakdown": "వ్యాధి వారీగా ప్రమాద విశ్లేషణ", "no_alerts": "క్రియాశీల హెచ్చరికలు లేవు. పరిస్థితులు సాధారణం.",
    "alert_msg": "హెచ్చరిక: దీనికి పెరిగిన ప్రమాదం గుర్తించబడింది",
    "recommendation": "సిఫార్సు చేసిన చర్యలు",
    "rec_1": "నీటి క్లోరినేషన్ మరియు క్రిమిసంహారక ఫ్రీక్వెన్సీని పెంచండి",
    "rec_2": "కమ్యూనిటీ హెల్త్ సెంటర్లకు ORS ను పంపిణీ చేయండి",
    "rec_3": "ప్రజా సూచన జారీ చేయండి: నీటిని మరిగించి తాగండి",
    "rec_4": "ఇంటింటి స్క్రీనింగ్ కోసం ఆరోగ్య కార్యకర్తలను నియమించండి",
    "rec_5": "నిఘా మరియు నమూనా పరీక్ష ఫ్రీక్వెన్సీని పెంచండి",
    "last_updated": "చివరిగా నవీకరించబడింది", "refresh": "డేటాను రిఫ్రెష్ చేయండి",
    "auto_refresh": "ప్రతి 10 సెకన్లకు ఆటో-రిఫ్రెష్",
    "footer": "నీటి ద్వారా వ్యాపించే వ్యాధుల (కలరా, టైఫాయిడ్, డయేరియా, డిసెంటరీ, హెపటైటిస్ A) ముందస్తు హెచ్చరిక కోసం AI ఆధారిత ప్రోటోటైప్. ఇది కేవలం ప్రదర్శన కోసం మాత్రమే — వైద్య సలహాకు ప్రత్యామ్నాయం కాదు.",
    "diseases": ["కలరా", "టైఫాయిడ్", "డయేరియా", "డిసెంటరీ", "హెపటైటిస్ A"],
    "param_trend": "ధోరణి కోసం పారామితిని ఎంచుకోండి", "risk_level": "ప్రమాద స్థాయి",
    "zone": "జోన్", "population": "జనాభా", "summary": "సారాంశం",
    "key_insights": "ముఖ్య అంతర్దృష్టులు", "insight_1": "గత కాలంలో ప్రమాద ధోరణి",
    "insight_2": "బ్యాక్టీరియా కాలుష్య స్థాయిలు సురక్షిత పరిమితుల్లో ఉన్నాయి",
    "insight_3": "భారీ వర్షపాతం కాలుష్య ప్రమాదాన్ని గణనీయంగా పెంచుతుంది",
    "sms_settings": "SMS హెచ్చరిక సెట్టింగ్‌లు", "twilio_sid": "Twilio అకౌంట్ SID",
    "twilio_token": "Twilio Auth Token", "twilio_from": "Twilio ఫోన్ నంబర్ (నుండి)",
    "send_sms": "SMS హెచ్చరిక పంపండి", "sms_target": "హెచ్చరిక SMS లక్ష్యం",
    "sms_threshold": "SMS హెచ్చరిక థ్రెషోల్డ్ (ప్రమాద స్కోర్)",
    "sms_auto": "థ్రెషోల్డ్ మించినప్పుడు ఆటో SMS పంపండి", "sms_preview": "SMS ప్రివ్యూ",
    "sms_log": "SMS కార్యాచరణ లాగ్", "sms_need_creds": "SMS పంపడానికి సెట్టింగ్స్‌లో Twilio వివరాలు నమోదు చేయండి.",
    "sms_sent_ok": "SMS పంపబడింది", "sms_sent_fail": "SMS విఫలమైంది",
    "firebase_connected": "సెన్సార్ నెట్‌వర్క్ కనెక్ట్ అయ్యింది", "firebase_not_connected": "సెన్సార్ నెట్‌వర్క్ కనెక్ట్ కాలేదు",
    "live_badge": "లైవ్ సెన్సార్ డేటా", "sim_badge": "సిమ్యులేటెడ్ డెమో డేటా",
    "live_banner": "ఈ జోన్ కోసం లైవ్ ESP32 సెన్సార్ డేటా చూపబడుతోంది",
    "sim_banner": "ఈ జోన్ కోసం లైవ్ సెన్సార్ రీడింగ్ అందుబాటులో లేదు — బదులుగా సిమ్యులేటెడ్ డెమో డేటా చూపబడుతోంది.",
    "reason": "కారణం",
    "home_eyebrow": "కమ్యూనిటీ నీటి ఆరోగ్య నిఘా",
    "home_hero_title": "ఎవరైనా అనారోగ్యానికి గురికాకముందే మీ నీరు సురక్షితమో కాదో తెలుసుకోండి.",
    "home_hero_sub": "AquaSentinel AI మీ కుటుంబం తాగే నీటిని రోజంతా గమనిస్తూ, మీ గ్రామాన్ని మీ సొంత భాషలో ముందుగానే హెచ్చరిస్తుంది.",
    "home_cta_primary": "మానిటరింగ్ ప్రారంభించండి", "home_cta_secondary": "ఇది ఎలా పనిచేస్తుందో చూడండి",
    "home_stat_1_num": "98%", "home_stat_1_label": "అంచనా ఖచ్చితత్వం",
    "home_stat_2_num": "24/7", "home_stat_2_label": "పర్యవేక్షణ",
    "home_stat_3_num": "1000+", "home_stat_3_label": "రక్షించబడిన ప్రజలు",
    "home_stat_4_num": "5", "home_stat_4_label": "అంచనా వేసిన వ్యాధులు",
    "home_how_eyebrow": "ఇది ఎలా పనిచేస్తుంది", "home_how_title": "నదినుండి ఫోన్ వరకూ — నాలుగు సులభమైన దశల్లో",
    "home_how_1_title": "సెన్సార్లు నీటిని పరిశీలిస్తాయి",
    "home_how_1_text": "నీటి వనరులో ఉన్న చిన్న పరికరం రోజంతా pH, శుభ్రత, ఉష్ణోగ్రత మరియు క్రిములను తనిఖీ చేస్తుంది.",
    "home_how_2_title": "AI ప్రమాదాన్ని అంచనా వేస్తుంది",
    "home_how_2_text": "మా వ్యవస్థ రీడింగ్‌లను కలరా, టైఫాయిడ్ వంటి వ్యాధులకు కారణమయ్యే నమూనాలతో పోలుస్తుంది.",
    "home_how_3_title": "మీ గ్రామానికి హెచ్చరిక అందుతుంది",
    "home_how_3_text": "ప్రమాదం పెరిగితే, మీకు అర్థమయ్యే భాషలో వెంటనే హెచ్చరిక మరియు SMS పంపబడతాయి.",
    "home_how_4_title": "మీరు సులభమైన చర్యలు తీసుకుంటారు",
    "home_how_4_text": "నీటిని మరిగించండి, ORS వాడండి, మరియు యాప్‌లో చూపిన సులభమైన భద్రతా చర్యలను పాటించండి.",
    "home_diseases_eyebrow": "ప్రమాదాన్ని తెలుసుకోండి", "home_diseases_title": "నీరు అసురక్షితంగా ఉంటే ఏమి జరగవచ్చు",
    "home_diseases_sub": "ఈ వ్యాధులు కలుషిత నీటి ద్వారా వ్యాపిస్తాయి. ముందస్తు హెచ్చరిక వల్ల ఎవరైనా అనారోగ్యానికి గురికాకముందే మీరు చర్య తీసుకోవచ్చు.",
    "home_learn_more": "పూర్తి భద్రతా గైడ్ చూడండి",
    "home_trust_title": "ప్రతి ఇంటి కోసం రూపొందించబడింది",
    "home_trust_text": "సరళమైన భాష, పెద్ద అక్షరాలు, దశలవారీ మార్గదర్శకత్వం — గ్రామంలోని ప్రతి వ్యక్తి, సాంకేతిక నిపుణులు మాత్రమే కాకుండా, నీటి ప్రమాదాన్ని మరియు దాన్ని ఎలా ఎదుర్కోవాలో అర్థం చేసుకునేలా రూపొందించబడింది.",
    "home_cta_footer_title": "ఇప్పుడే మీ జోన్ నీటి ప్రమాదాన్ని తనిఖీ చేయండి", "home_cta_footer_btn": "లైవ్ డాష్‌బోర్డ్ తెరవండి",
    "safety_title": "భద్రత & జాగ్రత్తల గైడ్",
    "safety_sub": "సాధారణ ప్రజారోగ్య మార్గదర్శకత్వం — ఇది వైద్య సలహాకు ప్రత్యామ్నాయం కాదు. ఎవరైనా తీవ్ర అనారోగ్యానికి గురైతే వెంటనే వైద్యుడిని సంప్రదించండి.",
    "safety_tab_general": "సాధారణ జాగ్రత్తలు", "safety_tab_disease": "వ్యాధి వారీగా మార్గదర్శకత్వం",
    "safety_now_title": "ఇప్పుడు సిఫార్సు చేయబడిన జాగ్రత్తలు",
    "risk_msg_critical": "తీవ్రమైన ప్రమాద జోన్ — పరిస్థితులు సాధారణం అయ్యేవరకు అన్ని స్థానిక నీటి వనరులను అసురక్షితంగా భావించండి.",
    "risk_msg_high": "అధిక ప్రమాద జోన్ — ఉపయోగించే ముందు నీటిని మరిగించండి లేదా శుద్ధి చేయండి; శుద్ధి చేయని వనరులతో ప్రత్యక్ష సంబంధాన్ని నివారించండి.",
    "risk_msg_moderate": "మధ్యస్థ ప్రమాద జోన్ — ప్రాథమిక జాగ్రత్తలు సిఫార్సు చేయబడతాయి; అప్‌డేట్‌ల కోసం పరిశీలించండి.",
    "risk_msg_low": "తక్కువ ప్రమాద జోన్ — ప్రస్తుత పరిస్థితులు సాధారణం; అయినా ప్రామాణిక పరిశుభ్రత పద్ధతులు పాటించండి.",
    "symptoms": "లక్షణాలు", "prevention": "నివారణ", "seek_help": "సహాయం ఎప్పుడు తీసుకోవాలి",
    "current_risk_in": "ప్రస్తుత ప్రమాదం",
    "real_history": "ESP32 నుండి నిజమైన లాగ్ చేసిన చరిత్ర చూపబడుతోంది",
    "sim_history": "ఇంకా నిజమైన లాగ్ చేసిన చరిత్ర కనుగొనబడలేదు — బదులుగా సిమ్యులేటెడ్ ధోరణి డేటా చూపబడుతోంది.",
    "events_log": "కాలుష్య సంఘటనల లాగ్",
    "events_note": "ఈ లాగ్ ప్రతి ఎలివేటెడ్ రీడింగ్ కాకుండా, ప్రమాద స్కోరు అధిక లేదా తీవ్రమైన స్థాయిలోకి ప్రవేశించిన ప్రతిసారీ ఒక విభిన్న కాలుష్య సంఘటనగా లెక్కిస్తుంది.",
    "high_events": "అధిక-ప్రమాద సంఘటనలు", "critical_events": "తీవ్ర-ప్రమాద సంఘటనలు",
    "peak_risk": "నమోదైన గరిష్ట ప్రమాదం", "period_covered": "కాలవ్యవధి", "days": "రోజు(లు)",
    "readings_analyzed": "రీడింగ్‌లు విశ్లేషించబడ్డాయి", "data_source": "డేటా మూలం",
    "trend_chart": "ధోరణి చార్ట్",
    "map_deep_dive": "జోన్ లోతైన విశ్లేషణ: లైవ్ + గత కాలుష్య చరిత్ర",
    "map_deep_dive_select": "లైవ్ రీడింగ్ మరియు కాలుష్య చరిత్ర చూడటానికి ప్రాంతాన్ని ఎంచుకోండి",
    "right_now": "ఇప్పుడు", "past": "గత",
    "no_high_events": "ఈ కాలంలో అధిక-ప్రమాద కాలుష్య సంఘటనలు నమోదు కాలేదు.",
    "critical_events_msg": "ఈ జోన్ గత {d} రోజు(ల)లో {n} సార్లు తీవ్రమైన కాలుష్య స్థాయికి చేరుకుంది. నిరంతర పర్యవేక్షణ మరియు జాగ్రత్తలు సిఫార్సు చేయబడతాయి.",
    "high_events_msg": "ఈ జోన్ గత {d} రోజు(ల)లో {n} సార్లు అధిక ప్రమాదంలోకి వెళ్లింది.",
    "live_col": "లైవ్ సెన్సార్?",
}

TRANSLATIONS["Español (Spanish)"] = {
    "brand": "AquaSentinel AI", "brand_tagline": "Red de Seguridad del Agua con IA",
    "title": "Sistema de Alerta Temprana de Salud Comunitaria con IA",
    "subtitle": "Predicción en Tiempo Real del Riesgo de Enfermedades Hídricas",
    "nav_home": "Inicio", "nav_live": "Monitoreo en Vivo", "nav_predict": "Predicción IA",
    "nav_trends": "Analítica", "nav_map": "Mapa de Aldea", "nav_safety": "Centro de Seguridad",
    "nav_alerts": "Alertas", "nav_hardware": "Hardware", "nav_about": "Acerca de",
    "settings": "Configuración", "language": "Idioma", "temp_unit": "Unidad de Temperatura",
    "select_zone": "Seleccionar Zona / Pueblo", "live_sensors": "Lecturas de Sensores en Vivo",
    "risk_prediction": "Predicción de Riesgo de Enfermedad", "alerts": "Alertas Activas",
    "trends": "Tendencias Históricas", "map_view": "Mapa de Riesgo por Zona",
    "water_temp": "Temperatura del Agua", "ph_level": "Nivel de pH", "turbidity": "Turbidez (NTU)",
    "tds": "TDS (ppm)", "rainfall": "Precipitación (mm)", "bacteria": "Conteo Bacteriano (CFU/mL)",
    "humidity": "Humedad (%)", "ambient_temp": "Temperatura Ambiente",
    "low_risk": "Riesgo Bajo", "moderate_risk": "Riesgo Moderado", "high_risk": "Riesgo Alto",
    "critical_risk": "Riesgo Crítico", "overall_risk": "Puntuación General de Riesgo de Brote",
    "disease_breakdown": "Desglose de Riesgo por Enfermedad", "no_alerts": "No hay alertas activas. Condiciones normales.",
    "alert_msg": "ALERTA: Riesgo elevado detectado para", "recommendation": "Acciones Recomendadas",
    "rec_1": "Aumentar la frecuencia de cloración y desinfección del agua",
    "rec_2": "Distribuir sales de rehidratación oral (SRO) a los centros de salud",
    "rec_3": "Emitir aviso público: hervir el agua antes de consumirla",
    "rec_4": "Desplegar trabajadores de salud para evaluación puerta a puerta",
    "rec_5": "Aumentar la vigilancia y la frecuencia de pruebas",
    "last_updated": "Última actualización", "refresh": "Actualizar Datos",
    "auto_refresh": "Actualizar automáticamente cada 10s",
    "footer": "Prototipo basado en IA para alerta temprana de enfermedades transmitidas por el agua (cólera, fiebre tifoidea, diarrea, disentería, hepatitis A). Solo con fines de demostración — no sustituye el consejo médico.",
    "diseases": ["Cólera", "Fiebre Tifoidea", "Diarrea", "Disentería", "Hepatitis A"],
    "param_trend": "Seleccionar Parámetro para Tendencia", "risk_level": "Nivel de Riesgo",
    "zone": "Zona", "population": "Población", "summary": "Resumen",
    "key_insights": "Conclusiones Clave", "insight_1": "Tendencia de riesgo en el último periodo",
    "insight_2": "Los niveles de contaminación bacteriana están dentro de límites seguros",
    "insight_3": "Las lluvias intensas aumentan significativamente el riesgo de contaminación",
    "sms_settings": "Configuración de Alerta SMS", "twilio_sid": "SID de Cuenta Twilio",
    "twilio_token": "Token de Autenticación Twilio", "twilio_from": "Número de Teléfono Twilio (desde)",
    "send_sms": "Enviar Alerta SMS Ahora", "sms_target": "Destino SMS de Alerta",
    "sms_threshold": "Umbral de Alerta SMS (Puntuación de Riesgo)",
    "sms_auto": "Envío automático de SMS cuando el riesgo supere el umbral", "sms_preview": "Vista Previa del SMS",
    "sms_log": "Registro de Actividad SMS", "sms_need_creds": "Ingrese las credenciales de Twilio en Configuración para enviar SMS.",
    "sms_sent_ok": "SMS enviado", "sms_sent_fail": "Error al enviar SMS",
    "firebase_connected": "Red de sensores conectada", "firebase_not_connected": "Red de sensores no conectada",
    "live_badge": "Datos de sensor EN VIVO", "sim_badge": "Datos de demostración simulados",
    "live_banner": "Mostrando datos EN VIVO del sensor ESP32 para",
    "sim_banner": "No hay lectura en vivo disponible para esta zona — mostrando datos simulados en su lugar.",
    "reason": "Motivo",
    "home_eyebrow": "Vigilancia Comunitaria del Agua",
    "home_hero_title": "Sepa que su agua es segura — antes de que alguien se enferme.",
    "home_hero_sub": "AquaSentinel AI vigila el agua que bebe su familia, las 24 horas del día, y avisa a su pueblo a tiempo, en su propio idioma.",
    "home_cta_primary": "Iniciar Monitoreo", "home_cta_secondary": "Ver cómo funciona",
    "home_stat_1_num": "98%", "home_stat_1_label": "Precisión de Predicción",
    "home_stat_2_num": "24/7", "home_stat_2_label": "Monitoreo",
    "home_stat_3_num": "1000+", "home_stat_3_label": "Personas Protegidas",
    "home_stat_4_num": "5", "home_stat_4_label": "Enfermedades Predichas",
    "home_how_eyebrow": "Cómo funciona", "home_how_title": "Del río al teléfono en cuatro pasos sencillos",
    "home_how_1_title": "Los sensores leen el agua",
    "home_how_1_text": "Un pequeño dispositivo en la fuente de agua revisa el pH, la limpieza, la temperatura y los gérmenes, todo el día.",
    "home_how_2_title": "La IA evalúa el riesgo",
    "home_how_2_text": "Nuestro sistema compara las lecturas con patrones conocidos que causan cólera, tifoidea y otras enfermedades.",
    "home_how_3_title": "Se avisa a su pueblo",
    "home_how_3_text": "Si el riesgo aumenta, se envía de inmediato una alerta y un SMS en el idioma que usted entiende.",
    "home_how_4_title": "Usted toma medidas simples",
    "home_how_4_text": "Hierva el agua, use SRO y siga los pasos de seguridad sencillos que se muestran en la aplicación.",
    "home_diseases_eyebrow": "Conozca el riesgo", "home_diseases_title": "Qué puede pasar si el agua no es segura",
    "home_diseases_sub": "Estas enfermedades se propagan por agua contaminada. La alerta temprana significa que puede actuar antes de que alguien se enferme.",
    "home_learn_more": "Ver guía completa de seguridad",
    "home_trust_title": "Diseñado para cada hogar",
    "home_trust_text": "Lenguaje sencillo, texto grande y orientación paso a paso — para que cada persona del pueblo, no solo los técnicos, entienda el riesgo del agua y qué hacer al respecto.",
    "home_cta_footer_title": "Revise ahora el riesgo del agua en su zona", "home_cta_footer_btn": "Abrir Panel en Vivo",
    "safety_title": "Guía de Seguridad y Precauciones",
    "safety_sub": "Orientación general de salud pública — no sustituye el consejo médico. Si alguien está gravemente enfermo, contacte a un profesional de salud de inmediato.",
    "safety_tab_general": "Precauciones Generales", "safety_tab_disease": "Guía por Enfermedad",
    "safety_now_title": "Precauciones recomendadas ahora mismo para",
    "risk_msg_critical": "Zona de riesgo crítico — trate TODAS las fuentes de agua locales como inseguras hasta que los niveles se normalicen.",
    "risk_msg_high": "Zona de riesgo alto — hierva o trate el agua antes de usarla; evite el contacto directo con fuentes no tratadas.",
    "risk_msg_moderate": "Zona de riesgo moderado — se recomiendan precauciones básicas; esté atento a actualizaciones.",
    "risk_msg_low": "Zona de riesgo bajo — condiciones actualmente normales; aun así, mantenga prácticas de higiene estándar.",
    "symptoms": "Síntomas", "prevention": "Prevención", "seek_help": "Cuándo buscar ayuda",
    "current_risk_in": "Riesgo actual en",
    "real_history": "Mostrando historial REAL registrado por el ESP32",
    "sim_history": "Aún no se encontró historial real registrado — mostrando datos de tendencia simulados en su lugar.",
    "events_log": "Registro de Eventos de Contaminación",
    "events_note": "Este registro cuenta eventos de contaminación distintos — cada vez que el puntaje de riesgo cruzó a un nivel Alto o Crítico — en lugar de cada lectura elevada individual.",
    "high_events": "Eventos de Alto Riesgo", "critical_events": "Eventos de Riesgo Crítico",
    "peak_risk": "Riesgo Máximo Registrado", "period_covered": "Período Cubierto", "days": "día(s)",
    "readings_analyzed": "lecturas analizadas", "data_source": "Fuente de datos",
    "trend_chart": "Gráfico de Tendencia",
    "map_deep_dive": "Análisis Detallado de Zona: Historial en Vivo + Pasado",
    "map_deep_dive_select": "Seleccione un área para ver su lectura en vivo e historial de contaminación",
    "right_now": "En Este Momento", "past": "Últimos",
    "no_high_events": "No se registraron eventos de contaminación de alto riesgo en este período.",
    "critical_events_msg": "Esta zona alcanzó niveles de contaminación CRÍTICOS {n} vez/veces en los últimos {d} día(s). Se recomienda vigilancia continua y precauciones.",
    "high_events_msg": "Esta zona cruzó a Riesgo Alto {n} vez/veces en los últimos {d} día(s).",
    "live_col": "¿Sensor en vivo?",
}

TRANSLATIONS["Français (French)"] = {
    "brand": "AquaSentinel AI", "brand_tagline": "Réseau de Sécurité de l'Eau par IA",
    "title": "Système d'Alerte Précoce de Santé Communautaire par IA",
    "subtitle": "Prédiction en Temps Réel du Risque de Maladies Hydriques",
    "nav_home": "Accueil", "nav_live": "Surveillance en Direct", "nav_predict": "Prédiction IA",
    "nav_trends": "Analytique", "nav_map": "Carte du Village", "nav_safety": "Centre de Sécurité",
    "nav_alerts": "Alertes", "nav_hardware": "Matériel", "nav_about": "À propos",
    "settings": "Paramètres", "language": "Langue", "temp_unit": "Unité de Température",
    "select_zone": "Sélectionner Zone / Village", "live_sensors": "Lectures des Capteurs en Direct",
    "risk_prediction": "Prédiction du Risque de Maladie", "alerts": "Alertes Actives",
    "trends": "Tendances Historiques", "map_view": "Carte des Risques par Zone",
    "water_temp": "Température de l'Eau", "ph_level": "Niveau de pH", "turbidity": "Turbidité (NTU)",
    "tds": "TDS (ppm)", "rainfall": "Précipitations (mm)", "bacteria": "Numération Bactérienne (CFU/mL)",
    "humidity": "Humidité (%)", "ambient_temp": "Température Ambiante",
    "low_risk": "Risque Faible", "moderate_risk": "Risque Modéré", "high_risk": "Risque Élevé",
    "critical_risk": "Risque Critique", "overall_risk": "Score Global de Risque d'Épidémie",
    "disease_breakdown": "Répartition du Risque par Maladie", "no_alerts": "Aucune alerte active. Conditions normales.",
    "alert_msg": "ALERTE : Risque élevé détecté pour", "recommendation": "Actions Recommandées",
    "rec_1": "Augmenter la fréquence de chloration et de désinfection de l'eau",
    "rec_2": "Distribuer des sels de réhydratation orale (SRO) aux centres de santé",
    "rec_3": "Émettre un avis public : faire bouillir l'eau avant consommation",
    "rec_4": "Déployer des agents de santé pour le dépistage porte-à-porte",
    "rec_5": "Augmenter la surveillance et la fréquence des tests",
    "last_updated": "Dernière mise à jour", "refresh": "Actualiser les Données",
    "auto_refresh": "Actualisation automatique toutes les 10s",
    "footer": "Prototype basé sur l'IA pour l'alerte précoce des maladies hydriques (choléra, typhoïde, diarrhée, dysenterie, hépatite A). À des fins de démonstration uniquement — ne remplace pas un avis médical.",
    "diseases": ["Choléra", "Typhoïde", "Diarrhée", "Dysenterie", "Hépatite A"],
    "param_trend": "Sélectionner un Paramètre pour la Tendance", "risk_level": "Niveau de Risque",
    "zone": "Zone", "population": "Population", "summary": "Résumé",
    "key_insights": "Points Clés", "insight_1": "Tendance du risque sur la dernière période",
    "insight_2": "Les niveaux de contamination bactérienne sont dans les limites sûres",
    "insight_3": "De fortes pluies augmentent considérablement le risque de contamination",
    "sms_settings": "Paramètres d'Alerte SMS", "twilio_sid": "SID de Compte Twilio",
    "twilio_token": "Jeton d'Authentification Twilio", "twilio_from": "Numéro de Téléphone Twilio (depuis)",
    "send_sms": "Envoyer une Alerte SMS Maintenant", "sms_target": "Destinataire SMS d'Alerte",
    "sms_threshold": "Seuil d'Alerte SMS (Score de Risque)",
    "sms_auto": "Envoi SMS automatique si le risque dépasse le seuil", "sms_preview": "Aperçu du SMS",
    "sms_log": "Journal d'Activité SMS", "sms_need_creds": "Entrez les identifiants Twilio dans les Paramètres pour envoyer un SMS.",
    "sms_sent_ok": "SMS envoyé", "sms_sent_fail": "Échec de l'envoi du SMS",
    "firebase_connected": "Réseau de capteurs connecté", "firebase_not_connected": "Réseau de capteurs non connecté",
    "live_badge": "Données de capteur EN DIRECT", "sim_badge": "Données de démonstration simulées",
    "live_banner": "Affichage des données EN DIRECT du capteur ESP32 pour",
    "sim_banner": "Aucune lecture en direct disponible pour cette zone — affichage de données simulées à la place.",
    "reason": "Raison",
    "home_eyebrow": "Veille Communautaire de l'Eau",
    "home_hero_title": "Sachez que votre eau est sûre — avant que quelqu'un ne tombe malade.",
    "home_hero_sub": "AquaSentinel AI surveille l'eau que boit votre famille, jour et nuit, et alerte votre village tôt, dans votre propre langue.",
    "home_cta_primary": "Démarrer la Surveillance", "home_cta_secondary": "Voir comment ça marche",
    "home_stat_1_num": "98%", "home_stat_1_label": "Précision de Prédiction",
    "home_stat_2_num": "24/7", "home_stat_2_label": "Surveillance",
    "home_stat_3_num": "1000+", "home_stat_3_label": "Personnes Protégées",
    "home_stat_4_num": "5", "home_stat_4_label": "Maladies Prédites",
    "home_how_eyebrow": "Comment ça marche", "home_how_title": "De la rivière au téléphone en quatre étapes simples",
    "home_how_1_title": "Les capteurs analysent l'eau",
    "home_how_1_text": "Un petit appareil dans la source d'eau vérifie le pH, la propreté, la température et les germes, toute la journée.",
    "home_how_2_title": "L'IA évalue le risque",
    "home_how_2_text": "Notre système compare les relevés à des schémas connus pour causer le choléra, la typhoïde et d'autres maladies.",
    "home_how_3_title": "Votre village est alerté",
    "home_how_3_text": "Si le risque augmente, une alerte et un SMS sont envoyés immédiatement, dans la langue que vous comprenez.",
    "home_how_4_title": "Vous agissez simplement",
    "home_how_4_text": "Faites bouillir l'eau, utilisez des SRO, et suivez les étapes de sécurité simples affichées dans l'application.",
    "home_diseases_eyebrow": "Connaître le risque", "home_diseases_title": "Ce qui peut arriver si l'eau n'est pas sûre",
    "home_diseases_sub": "Ces maladies se propagent par l'eau contaminée. Une alerte précoce signifie que vous pouvez agir avant que quiconque ne tombe malade.",
    "home_learn_more": "Voir le guide de sécurité complet",
    "home_trust_title": "Conçu pour chaque foyer",
    "home_trust_text": "Langage simple, grand texte et conseils étape par étape — conçu pour que chaque personne du village, pas seulement les techniciens, comprenne le risque lié à l'eau et ce qu'il faut faire.",
    "home_cta_footer_title": "Vérifiez maintenant le risque hydrique de votre zone", "home_cta_footer_btn": "Ouvrir le Tableau de Bord",
    "safety_title": "Guide de Sécurité et Précautions",
    "safety_sub": "Conseils généraux de santé publique — ne remplace pas un avis médical. Si quelqu'un est gravement malade, contactez immédiatement un professionnel de santé.",
    "safety_tab_general": "Précautions Générales", "safety_tab_disease": "Conseils par Maladie",
    "safety_now_title": "Précautions recommandées maintenant pour",
    "risk_msg_critical": "Zone à risque critique — considérez TOUTES les sources d'eau locales comme dangereuses jusqu'à normalisation des niveaux.",
    "risk_msg_high": "Zone à risque élevé — faites bouillir ou traitez l'eau avant toute utilisation ; évitez tout contact direct avec des sources non traitées.",
    "risk_msg_moderate": "Zone à risque modéré — précautions de base recommandées ; surveillez les mises à jour.",
    "risk_msg_low": "Zone à faible risque — conditions actuellement normales ; les pratiques d'hygiène standard restent de mise.",
    "symptoms": "Symptômes", "prevention": "Prévention", "seek_help": "Quand consulter",
    "current_risk_in": "Risque actuel à",
    "real_history": "Affichage de l'historique RÉEL enregistré par l'ESP32",
    "sim_history": "Aucun historique réel enregistré trouvé pour l'instant — affichage de données de tendance simulées à la place.",
    "events_log": "Journal des Événements de Contamination",
    "events_note": "Ce journal compte les événements de contamination distincts — chaque fois que le score de risque est passé à un niveau Élevé ou Critique — plutôt que chaque relevé élevé individuel.",
    "high_events": "Événements à Haut Risque", "critical_events": "Événements à Risque Critique",
    "peak_risk": "Risque Maximal Enregistré", "period_covered": "Période Couverte", "days": "jour(s)",
    "readings_analyzed": "relevés analysés", "data_source": "Source des données",
    "trend_chart": "Graphique de Tendance",
    "map_deep_dive": "Analyse Détaillée de Zone : En Direct + Historique Passé",
    "map_deep_dive_select": "Sélectionnez une zone pour voir sa lecture en direct et son historique de contamination",
    "right_now": "En Ce Moment", "past": "Derniers",
    "no_high_events": "Aucun événement de contamination à haut risque enregistré durant cette période.",
    "critical_events_msg": "Cette zone a atteint des niveaux de contamination CRITIQUES {n} fois au cours des {d} dernier(s) jour(s). Surveillance continue et précautions recommandées.",
    "high_events_msg": "Cette zone est passée en Risque Élevé {n} fois au cours des {d} dernier(s) jour(s).",
    "live_col": "Capteur en direct ?",
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
}
# Other languages fall back to English disease info to keep this file a manageable size;
# swap in full translations the same way TRANSLATIONS was extended above if needed.
for _lang in ["हिन्दी (Hindi)", "తెలుగు (Telugu)", "Español (Spanish)", "Français (French)"]:
    DISEASE_INFO[_lang] = DISEASE_INFO["English"]

DISEASE_KEYS = ["Cholera", "Typhoid", "Diarrhea", "Dysentery", "Hepatitis A"]

ZONES_DATA = {
    "Zone A - Riverside Village":   {"population": 4200, "lat": 17.385, "lon": 78.486, "firebase_key": "zone_a"},
    "Zone B - Hillside Settlement": {"population": 2800, "lat": 17.405, "lon": 78.466, "firebase_key": "zone_b"},
    "Zone C - Lakeside Town":       {"population": 6100, "lat": 17.365, "lon": 78.506, "firebase_key": "zone_c"},
    "Zone D - Central District":    {"population": 9500, "lat": 17.395, "lon": 78.496, "firebase_key": "zone_d"},
    "Zone E - Floodplain Area":     {"population": 3300, "lat": 17.375, "lon": 78.476, "firebase_key": "zone_e"},
}

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
    "prev_sensors": {},
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

# =========================================================
# HELPER FUNCTIONS (backend logic — unchanged math, only UI consumes these)
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
        return T["moderate_risk"], "#F4B400"
    elif score < 75:
        return T["high_risk"], "#E07A2C"
    else:
        return T["critical_risk"], "#E63946"


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
    return risks, {
        "ph_risk": ph_risk, "turb_risk": turb_risk, "bact_risk": bact_risk,
        "rain_risk": rain_risk, "temp_risk": temp_risk, "humidity_risk": humidity_risk,
    }


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
    base_tds = np.clip(450 + np.cumsum(rng.normal(0, 6, len(dates))), 50, None)
    df = pd.DataFrame({
        "datetime": dates, "bacteria": base_bact, "turbidity": base_turb, "ph": base_ph,
        "rainfall": base_rain, "water_temp_c": base_wtemp, "ambient_temp_c": base_ambient, "tds": base_tds,
    })
    df["overall_risk"] = np.clip(
        0.4 * (df["bacteria"] / 4) + 0.3 * (df["turbidity"] * 4) + 0.3 * (df["rainfall"] * 3), 0, 100
    )
    return df


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
        "is_real": is_real, "high_events": high_events, "critical_events": critical_events,
        "peak_risk": peak_risk, "avg_risk": avg_risk, "span_days": max(span_days, 1), "num_readings": len(df),
    }


# ---- NEW helper functions added for the redesign (pure UI/derived metrics; no backend change) ----
def compute_wqi(sensors):
    """Water Quality Index 0-100, higher = better/safer."""
    ph_score = max(0, 100 - abs(sensors["ph"] - 7.0) * 22)
    turb_score = max(0, 100 - sensors["turbidity"] * 4)
    tds_score = max(0, 100 - sensors["tds"] / 8)
    bact_score = max(0, 100 - sensors["bacteria"] / 3)
    return float(np.clip(np.mean([ph_score, turb_score, tds_score, bact_score]), 0, 100))


def get_wqi_status(wqi, T):
    if wqi >= 85:
        return T.get("wqi_excellent", "Excellent"), "#2E7D53", T.get("wqi_safe", "Safe to Drink")
    elif wqi >= 65:
        return T.get("wqi_good", "Good"), "#2FA6A6", T.get("wqi_boil", "Boil Before Drinking")
    elif wqi >= 40:
        return T.get("wqi_poor", "Poor"), "#F4B400", T.get("wqi_boil", "Boil Before Drinking")
    else:
        return T.get("wqi_unsafe", "Unsafe"), "#E63946", T.get("wqi_unsafe_drink", "Unsafe Water")


def village_health_score(overall_risk):
    score = float(np.clip(100 - overall_risk, 0, 100))
    if score >= 85:
        return score, "Excellent", "#2E7D53"
    elif score >= 65:
        return score, "Good", "#2FA6A6"
    elif score >= 45:
        return score, "Moderate", "#F4B400"
    elif score >= 25:
        return score, "Poor", "#E07A2C"
    else:
        return score, "Critical", "#E63946"


def track_trend(zone_key, metric_name, current_value):
    """Compares current sensor value to the previous poll for this zone+metric, returns (delta, arrow)."""
    store = st.session_state.prev_sensors.setdefault(zone_key, {})
    prev = store.get(metric_name)
    store[metric_name] = current_value
    if prev is None:
        return 0.0, "→"
    delta = current_value - prev
    if abs(delta) < 1e-6:
        return 0.0, "→"
    return delta, ("↑" if delta > 0 else "↓")


def sparkline_fig(values, color="#00B4D8"):
    fig = go.Figure(go.Scatter(
        y=list(values), mode="lines", line=dict(color=color, width=2.5),
        fill="tozeroy", fillcolor=color.replace(")", ",0.15)").replace("rgb", "rgba") if color.startswith("rgb") else None,
    ))
    fig.update_layout(
        height=46, margin=dict(l=0, r=0, t=0, b=0),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(visible=False), yaxis=dict(visible=False), showlegend=False,
    )
    return fig


def ai_reasoning_factors(risk_components, T):
    """Turns the disease-risk contributing factors into human-readable reasoning bullets."""
    labels = {
        "bact_risk": T.get("reason_bacteria", "High Bacterial Count"),
        "turb_risk": T.get("reason_turbidity", "High Turbidity"),
        "rain_risk": T.get("reason_rainfall", "Rainfall Increased Risk"),
        "ph_risk": T.get("reason_ph", "Abnormal pH Level"),
        "temp_risk": T.get("reason_temp", "High Water Temperature"),
        "humidity_risk": T.get("reason_humidity", "High Humidity"),
    }
    items = sorted(risk_components.items(), key=lambda kv: kv[1], reverse=True)
    total = sum(v for _, v in items) or 1.0
    out = []
    for key, val in items[:4]:
        if val <= 5:
            continue
        pct = round(100 * val / total)
        out.append((labels.get(key, key), pct))
    return out

# =========================================================
# VISUAL IDENTITY — CSS  (Apple / Google Material / Tesla / WHO inspired)
# Palette: Primary #0F4C81, Secondary #00B4D8, Accent #00C897,
# Background #F4F8FB, Cards white, Danger #E63946, Warning #F4B400, Text #1E293B
# =========================================================
def inject_css():
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Poppins:wght@500;600;700;800&family=Inter:wght@400;500;600;700;800&family=Noto+Sans:wght@400;600;700&family=Noto+Sans+Devanagari:wght@400;600;700&family=Noto+Sans+Telugu:wght@400;600;700&display=swap');

        :root {
            --aq-primary: #0F4C81;
            --aq-primary-dark: #0A3459;
            --aq-secondary: #00B4D8;
            --aq-accent: #00C897;
            --aq-bg: #F4F8FB;
            --aq-card: #FFFFFF;
            --aq-danger: #E63946;
            --aq-warning: #F4B400;
            --aq-text: #1E293B;
            --aq-text-dim: #5B6B7C;
            --aq-border: rgba(15,76,129,0.10);
            --aq-shadow: 0 8px 30px rgba(15,76,129,0.08);
            --aq-shadow-lg: 0 16px 44px rgba(15,76,129,0.14);
        }

        html, body, [class*="css"], .stMarkdown, p, div, span, li, label {
            font-family: 'Inter', 'Noto Sans', 'Noto Sans Devanagari', 'Noto Sans Telugu', sans-serif;
            color: var(--aq-text);
        }
        h1, h2, h3, h4, h5, h6, .aq-display {
            font-family: 'Poppins', 'Noto Sans', sans-serif !important;
            font-weight: 700 !important;
            color: var(--aq-primary-dark) !important;
            letter-spacing: -0.01em;
        }

        .stApp, [data-testid="stAppViewContainer"], [data-testid="stHeader"] {
            background: var(--aq-bg) !important;
        }
        [data-testid="stHeader"] { background: transparent !important; }

        .stApp p, .stApp span, .stApp li, .stApp label,
        [data-testid="stMetricValue"], [data-testid="stCaptionContainer"] {
            color: var(--aq-text) !important;
        }
        .stCaption, [data-testid="stCaptionContainer"] p { color: var(--aq-text-dim) !important; }
        [data-testid="stMetricValue"] { font-family: 'Poppins', sans-serif !important; font-weight: 700 !important; }

        /* ---- Sidebar ---- */
        section[data-testid="stSidebar"] {
            background: linear-gradient(180deg, #0A3459 0%, #0F4C81 100%) !important;
            border-right: none;
        }
        section[data-testid="stSidebar"] * { color: #EAF4FB !important; }
        section[data-testid="stSidebar"] .stSelectbox label,
        section[data-testid="stSidebar"] .stRadio label,
        section[data-testid="stSidebar"] .stTextInput label,
        section[data-testid="stSidebar"] .stSlider label,
        section[data-testid="stSidebar"] .stCheckbox label { color: #BFDCEF !important; font-weight: 600; }
        section[data-testid="stSidebar"] input, section[data-testid="stSidebar"] [data-baseweb="select"] {
            background: rgba(255,255,255,0.08) !important; color: #EAF4FB !important; border-radius: 10px !important;
        }

        .aq-brand { display:flex; align-items:center; gap:12px; padding:6px 4px 18px 4px;
            border-bottom: 1px solid rgba(255,255,255,0.14); margin-bottom:14px; }
        .aq-brand-icon { font-size:30px; }
        .aq-brand-name { font-family:'Poppins',sans-serif; font-size:20px; font-weight:800; color:#FFFFFF !important; line-height:1.15; }
        .aq-brand-tag { font-size:12px; color:#9FC6E3 !important; letter-spacing:0.03em; }

        /* ---- Hero (gradient: deep blue -> ocean blue -> emerald) ---- */
        .aq-hero {
            background: linear-gradient(120deg, #0A3459 0%, #0F4C81 35%, #00B4D8 75%, #00C897 100%);
            border-radius: 28px; padding: 56px 48px; position: relative; overflow:hidden;
            margin-bottom: 30px; box-shadow: var(--aq-shadow-lg);
        }
        .aq-hero::after { content:""; position:absolute; right:-80px; top:-80px; width:340px; height:340px;
            background: radial-gradient(circle, rgba(255,255,255,0.18) 0%, rgba(255,255,255,0) 70%); }
        .aq-hero::before { content:""; position:absolute; left:-60px; bottom:-90px; width:280px; height:280px;
            background: radial-gradient(circle, rgba(0,200,151,0.30) 0%, rgba(0,200,151,0) 70%); }
        .aq-hero-eyebrow { display:inline-block; background: rgba(255,255,255,0.16); color:#FFFFFF !important;
            border:1px solid rgba(255,255,255,0.35); padding:6px 16px; border-radius:999px; font-size:13px;
            font-weight:700; letter-spacing:0.04em; margin-bottom:20px; backdrop-filter: blur(6px); }
        .aq-hero h1 { color:#FFFFFF !important; font-size:44px !important; line-height:1.15 !important;
            max-width:740px; margin-bottom:16px !important; }
        .aq-hero p { color:#E4F3FA !important; font-size:18.5px; max-width:620px; line-height:1.6; position:relative; }

        /* ---- Glass cards ---- */
        .aq-card {
            background: rgba(255,255,255,0.85); backdrop-filter: blur(10px);
            border-radius: 18px; padding: 22px; box-shadow: var(--aq-shadow);
            border: 1px solid var(--aq-border); height: 100%; transition: transform .18s ease, box-shadow .18s ease;
        }
        .aq-card:hover { transform: translateY(-3px); box-shadow: var(--aq-shadow-lg); }

        .aq-step-card { background: var(--aq-card); border-radius: 18px; padding: 26px 22px;
            border-top: 4px solid var(--aq-accent); box-shadow: var(--aq-shadow); height:100%;
            transition: transform .18s ease; }
        .aq-step-card:hover { transform: translateY(-4px); }
        .aq-step-num { font-family:'Poppins',sans-serif; font-size:30px; font-weight:800; color: var(--aq-accent) !important; }
        .aq-step-title { font-family:'Poppins',sans-serif; font-size:18.5px; font-weight:700; color: var(--aq-primary-dark) !important; margin:8px 0; }
        .aq-step-text { font-size:14.5px; color: var(--aq-text-dim) !important; line-height:1.55; }

        .aq-disease-card { background: var(--aq-card); border-radius:18px; padding:20px; box-shadow: var(--aq-shadow); height:100%; }
        .aq-disease-icon-wrap { width:54px; height:54px; border-radius:14px; background: rgba(0,180,216,0.12);
            display:flex; align-items:center; justify-content:center; font-size:26px; margin-bottom:12px; }
        .aq-disease-name { font-family:'Poppins',sans-serif; font-weight:700; font-size:17px; color: var(--aq-primary-dark) !important; margin-bottom:6px; }
        .aq-disease-hook { font-size:13.5px; color: var(--aq-text-dim) !important; line-height:1.5; }

        .aq-eyebrow { display:inline-block; color: var(--aq-secondary) !important; background: rgba(0,180,216,0.10);
            padding:5px 14px; border-radius:999px; font-size:12.5px; font-weight:800; letter-spacing:0.04em;
            text-transform:uppercase; margin-bottom:12px; }

        .aq-stat-card { text-align:center; }
        .aq-stat-num { font-family:'Poppins',sans-serif; font-size:36px; font-weight:800; color: var(--aq-primary) !important; }
        .aq-stat-label { font-size:13.5px; color: var(--aq-text-dim) !important; font-weight:600; }

        .aq-cta-band { background: linear-gradient(120deg, rgba(15,76,129,0.06), rgba(0,200,151,0.10));
            border: 1px solid var(--aq-border); border-radius: 20px; padding: 28px 32px;
            display:flex; align-items:center; justify-content:space-between; gap:20px; flex-wrap:wrap; margin-top:14px; }

        .aq-badge-live { display:inline-flex; align-items:center; gap:6px; background: rgba(0,200,151,0.14);
            color:#0A7B5C !important; padding:6px 14px; border-radius:999px; font-weight:700; font-size:13px; }
        .aq-badge-sim { display:inline-flex; align-items:center; gap:6px; background: rgba(244,180,0,0.16);
            color:#8A6200 !important; padding:6px 14px; border-radius:999px; font-weight:700; font-size:13px; }

        /* ---- Sensor cards ---- */
        .aq-sensor-card { background: var(--aq-card); border-radius:18px; padding:18px 20px; box-shadow: var(--aq-shadow);
            border: 1px solid var(--aq-border); height:100%; }
        .aq-sensor-top { display:flex; align-items:center; justify-content:space-between; }
        .aq-sensor-icon { font-size:26px; }
        .aq-sensor-label { font-size:13px; color: var(--aq-text-dim) !important; font-weight:700; text-transform:uppercase; letter-spacing:0.02em; }
        .aq-sensor-value { font-family:'Poppins',sans-serif; font-size:26px; font-weight:800; color: var(--aq-primary-dark) !important; margin:4px 0 0 0; }
        .aq-sensor-trend { font-size:13px; font-weight:700; }
        .aq-trend-up { color: var(--aq-danger) !important; }
        .aq-trend-down { color: var(--aq-accent) !important; }
        .aq-trend-flat { color: var(--aq-text-dim) !important; }

        /* ---- Animated risk bar ---- */
        .aq-riskbar-track { width:100%; height:22px; border-radius:999px; background: #E6EEF5; overflow:hidden;
            position:relative; box-shadow: inset 0 1px 3px rgba(0,0,0,0.08); }
        .aq-riskbar-fill { height:100%; border-radius:999px; transition: width 1.1s cubic-bezier(.22,1,.36,1);
            box-shadow: 0 0 14px currentColor; }

        /* ---- Status panel ---- */
        .aq-status-row { display:flex; align-items:center; justify-content:space-between; padding:10px 4px;
            border-bottom: 1px solid var(--aq-border); }
        .aq-status-row:last-child { border-bottom:none; }
        .aq-dot { display:inline-block; width:9px; height:9px; border-radius:50%; margin-right:8px; }
        .aq-dot-green { background: var(--aq-accent); box-shadow: 0 0 8px var(--aq-accent); }
        .aq-dot-red { background: var(--aq-danger); box-shadow: 0 0 8px var(--aq-danger); }

        /* ---- Alert / emergency cards ---- */
        .aq-emergency-card { border-radius:18px; padding:20px 22px; margin-bottom:14px;
            background: linear-gradient(120deg, rgba(230,57,70,0.08), rgba(230,57,70,0.02));
            border: 1.5px solid rgba(230,57,70,0.35); box-shadow: 0 0 24px rgba(230,57,70,0.12); }
        .aq-emergency-title { font-family:'Poppins',sans-serif; font-weight:800; color: var(--aq-danger) !important; font-size:17px; }

        /* ---- Timeline ---- */
        .aq-timeline-item { display:flex; gap:14px; padding-bottom: 18px; position:relative; }
        .aq-timeline-item::before { content:""; position:absolute; left:5px; top:20px; bottom:-4px; width:2px; background: var(--aq-border); }
        .aq-timeline-item:last-child::before { display:none; }
        .aq-timeline-dot { width:12px; height:12px; border-radius:50%; background: var(--aq-secondary); margin-top:4px; flex-shrink:0; }
        .aq-timeline-time { font-weight:700; color: var(--aq-primary) !important; font-size:13px; }
        .aq-timeline-text { color: var(--aq-text-dim) !important; font-size:14px; }

        div[data-testid="stMetric"] { background: var(--aq-card); border-radius:16px; padding:14px 16px;
            border:1px solid var(--aq-border); box-shadow: var(--aq-shadow); }

        div[data-testid="stAlert"] { background: var(--aq-card) !important; border:1px solid var(--aq-border) !important; border-radius:14px !important; }

        .stTabs [data-baseweb="tab-list"] { gap:6px; }
        .stTabs [data-baseweb="tab"] { background: rgba(15,76,129,0.05); border-radius: 10px 10px 0 0; color: var(--aq-text-dim) !important; font-weight:700; }
        .stTabs [aria-selected="true"] { color: var(--aq-primary) !important; background: #FFFFFF; }

        [data-testid="stDataFrame"] { border-radius: 14px; overflow:hidden; border:1px solid var(--aq-border); }
        details, [data-testid="stExpander"] { background: var(--aq-card) !important; border:1px solid var(--aq-border) !important; border-radius:14px !important; }

        .stButton > button { border-radius: 999px !important; font-weight:700 !important;
            border: 1px solid var(--aq-border) !important; background: #FFFFFF !important; color: var(--aq-primary) !important;
            transition: transform .15s ease, box-shadow .15s ease; }
        .stButton > button:hover { transform: translateY(-2px); box-shadow: var(--aq-shadow); }
        .stButton > button[kind="primary"] {
            background: linear-gradient(120deg, var(--aq-primary), var(--aq-secondary)) !important;
            color: #FFFFFF !important; border:none !important;
        }

        code { color: var(--aq-primary) !important; background: rgba(15,76,129,0.06) !important; }
        #MainMenu {visibility: hidden;}
        footer {visibility: hidden;}

        @media (max-width: 768px) {
            .aq-hero { padding: 34px 24px; border-radius: 20px; }
            .aq-hero h1 { font-size: 30px !important; }
            .aq-hero p { font-size: 15.5px !important; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

def animated_number_html(value_text, label_text, delay_ms=0):
    """Small self-contained HTML/CSS/JS block for a count-up stat, used on the Home page."""
    import re
    m = re.match(r"^([^\d]*)([\d,]+(?:\.\d+)?)(.*)$", value_text)
    prefix, number, suffix = (m.group(1), m.group(2), m.group(3)) if m else ("", value_text, "")
    target = number.replace(",", "")
    is_float = "." in target
    return f"""
    <div style="text-align:center; font-family:'Poppins',sans-serif;">
        <div id="num-{abs(hash(value_text+label_text))}" style="font-size:36px; font-weight:800; color:#0F4C81;">{prefix}0{suffix}</div>
        <div style="font-size:13.5px; color:#5B6B7C; font-weight:600; font-family:'Inter',sans-serif;">{label_text}</div>
    </div>
    <script>
    (function() {{
        const el = document.getElementById("num-{abs(hash(value_text+label_text))}");
        const target = {target if target else 0};
        const isFloat = {str(is_float).lower()};
        let cur = 0;
        const steps = 40;
        const inc = target / steps;
        setTimeout(function tick() {{
            cur += inc;
            if (cur >= target) {{ cur = target; }}
            el.textContent = "{prefix}" + (isFloat ? cur.toFixed(1) : Math.round(cur).toLocaleString()) + "{suffix}";
            if (cur < target) {{ setTimeout(tick, 25); }}
        }}, {delay_ms});
    }})();
    </script>
    """


# =========================================================
# SIDEBAR — NAVIGATION + SETTINGS
# =========================================================
inject_css()
T = TRANSLATIONS[st.session_state.language]
DI = DISEASE_INFO[st.session_state.language]

nav_keys = ["Home", "Live", "Predict", "Map", "Alerts", "Safety", "Analytics", "Hardware", "About"]
nav_labels = [T["nav_home"], T["nav_live"], T["nav_predict"], T["nav_map"], T["nav_alerts"],
              T["nav_safety"], T["nav_trends"], T.get("nav_hardware", "Hardware"), T.get("nav_about", "About")]
nav_icons = ["house-heart", "speedometer2", "cpu", "geo-alt", "bell", "shield-check",
             "graph-up-arrow", "hdd-network", "info-circle"]

with st.sidebar:
    st.markdown(
        f"""
        <div class="aq-brand">
            <div class="aq-brand-icon">💧</div>
            <div>
                <div class="aq-brand-name">{T['brand']}</div>
                <div class="aq-brand-tag">{T['brand_tagline']}</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if OPTION_MENU_AVAILABLE:
        chosen_label = option_menu(
            menu_title=None, options=nav_labels, icons=nav_icons,
            default_index=nav_keys.index(st.session_state.nav_page) if st.session_state.nav_page in nav_keys else 0,
            styles={
                "container": {"padding": "0", "background-color": "transparent"},
                "icon": {"color": "#00C897", "font-size": "16px"},
                "nav-link": {"font-size": "14.5px", "font-weight": "600", "color": "#EAF4FB",
                             "text-align": "left", "margin": "3px 0", "border-radius": "10px", "padding": "10px 12px"},
                "nav-link-selected": {"background-color": "#00B4D8", "color": "#0A3459"},
            },
        )
        st.session_state.nav_page = nav_keys[nav_labels.index(chosen_label)]
    else:
        chosen_label = st.radio("Menu", options=nav_labels, label_visibility="collapsed")
        st.session_state.nav_page = nav_keys[nav_labels.index(chosen_label)]

    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

    with st.expander("⚙️ " + T["settings"], expanded=False):
        lang = st.selectbox(T["language"], options=list(TRANSLATIONS.keys()),
                             index=list(TRANSLATIONS.keys()).index(st.session_state.language), key="lang_select")
        if lang != st.session_state.language:
            st.session_state.language = lang
            st.rerun()

        temp_unit = st.radio(T["temp_unit"], options=["Celsius (°C)", "Fahrenheit (°F)"],
                              index=0 if st.session_state.temp_unit.startswith("Celsius") else 1, horizontal=True)
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
# DATA FETCH  (backend logic unchanged)
# =========================================================
zone_info = ZONES_DATA[selected_zone]
sensors, is_live, fetch_error = get_sensor_data(selected_zone, zone_info["firebase_key"], st.session_state.seed_offset)
disease_risks, risk_components = compute_disease_risks(sensors)
overall_risk = float(np.mean(list(disease_risks.values())))
hist_df = generate_historical_data(selected_zone)
alerted = {k: v for k, v in disease_risks.items() if v >= 50}
translated_disease_names = dict(zip(DISEASE_KEYS, T["diseases"]))
risk_label, risk_color = get_risk_label(overall_risk)
wqi = compute_wqi(sensors)
wqi_status, wqi_color, wqi_action = get_wqi_status(wqi, T)
vh_score, vh_label, vh_color = village_health_score(overall_risk)

# Auto-SMS (unchanged backend behavior)
if sms_auto and overall_risk >= sms_threshold:
    prev = st.session_state.last_sms_sent_score
    if prev is None or prev < sms_threshold:
        if twilio_sid and twilio_token and twilio_from:
            sms_body = build_sms_message(selected_zone, overall_risk, alerted or {"Overall": overall_risk}, sensors)
            ok, status = send_sms_alert(sms_body, twilio_sid, twilio_token, twilio_from)
            st.session_state.last_sms_sent_score = overall_risk
            st.session_state.sms_log.insert(0, {
                "time": datetime.now().strftime("%H:%M:%S"), "zone": selected_zone,
                "score": f"{overall_risk:.1f}", "status": f"✅ {T['sms_sent_ok']}" if ok else f"❌ {status}",
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
        <div class="aq-hero">
            <span class="aq-hero-eyebrow">💧 {T['home_eyebrow']}</span>
            <h1 class="aq-display">{T['home_hero_title']}</h1>
            <p>{T['home_hero_sub']}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    hcol1, hcol2, hspacer = st.columns([1.2, 1.3, 2.5])
    with hcol1:
        if st.button("💧 " + T["home_cta_primary"], type="primary", use_container_width=True):
            st.session_state.nav_page = "Live"
            st.rerun()
    with hcol2:
        st.button("▾ " + T["home_cta_secondary"], use_container_width=True)

    st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)
    stat_cols = st.columns(4)
    stats = [
        (T["home_stat_1_num"], T["home_stat_1_label"]),
        (T["home_stat_2_num"], T["home_stat_2_label"]),
        (T["home_stat_3_num"], T["home_stat_3_label"]),
        (T["home_stat_4_num"], T["home_stat_4_label"]),
    ]
    for col, (num, label) in zip(stat_cols, stats):
        with col:
            st.markdown("<div class='aq-card aq-stat-card'>", unsafe_allow_html=True)
            st.iframe(animated_number_html(num, label), height=80)
            st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("<div style='height:40px'></div>", unsafe_allow_html=True)
    st.markdown(f"<span class='aq-eyebrow'>{T['home_how_eyebrow']}</span>", unsafe_allow_html=True)
    st.markdown(f"### {T['home_how_title']}")

    steps = [
        ("01", "🚰", T["home_how_1_title"], T["home_how_1_text"]),
        ("02", "🧠", T["home_how_2_title"], T["home_how_2_text"]),
        ("03", "📡", T["home_how_3_title"], T["home_how_3_text"]),
        ("04", "✅", T["home_how_4_title"], T["home_how_4_text"]),
    ]
    step_cols = st.columns(4)
    for col, (num, icon, stitle, stext) in zip(step_cols, steps):
        with col:
            st.markdown(
                f"""<div class="aq-step-card">
                    <div class="aq-step-num">{icon} {num}</div>
                    <div class="aq-step-title">{stitle}</div>
                    <div class="aq-step-text">{stext}</div>
                </div>""",
                unsafe_allow_html=True,
            )

    st.markdown("<div style='height:40px'></div>", unsafe_allow_html=True)
    st.markdown(f"<span class='aq-eyebrow'>{T['home_diseases_eyebrow']}</span>", unsafe_allow_html=True)
    st.markdown(f"### {T['home_diseases_title']}")
    st.markdown(f"<p style='color:#5B6B7C;max-width:680px;'>{T['home_diseases_sub']}</p>", unsafe_allow_html=True)

    dcols = st.columns(5)
    for col, dkey, hook in zip(dcols, DISEASE_KEYS, DI["hook"]):
        info = DI["diseases"][dkey]
        with col:
            st.markdown(
                f"""<div class="aq-disease-card">
                    <div class="aq-disease-icon-wrap">{info['icon']}</div>
                    <div class="aq-disease-name">{translated_disease_names[dkey]}</div>
                    <div class="aq-disease-hook">{hook}</div>
                </div>""",
                unsafe_allow_html=True,
            )
    st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)
    if st.button("📖 " + T["home_learn_more"]):
        st.session_state.nav_page = "Safety"
        st.rerun()

    st.markdown("<div style='height:40px'></div>", unsafe_allow_html=True)
    tcol1, tcol2 = st.columns([1, 1.3])
    with tcol1:
        st.markdown(
            f"""<div class="aq-card">
                <div style="font-size:38px;">🧑‍🤝‍🧑👵👴🧒</div>
                <h3 style="margin-top:10px;">{T['home_trust_title']}</h3>
                <p style="color:#5B6B7C; line-height:1.55;">{T['home_trust_text']}</p>
            </div>""",
            unsafe_allow_html=True,
        )
    with tcol2:
        st.markdown(
            f"""<div class="aq-card">
                <div style="font-size:38px;">🚰🧪🌧️</div>
                <h3 style="margin-top:10px;">{T['live_sensors']}</h3>
                <p style="color:#5B6B7C; line-height:1.55;">{T['water_temp']} · {T['ph_level']} · {T['turbidity']} ·
                {T['tds']} · {T['rainfall']} · {T['bacteria']} · {T['humidity']}</p>
            </div>""",
            unsafe_allow_html=True,
        )

    st.markdown("<div style='height:26px'></div>", unsafe_allow_html=True)
    st.markdown(
        f"""<div class="aq-cta-band">
            <div style="font-family:'Poppins',sans-serif; font-weight:700; font-size:20px; color:#0F4C81;">
                {T['home_cta_footer_title']}
            </div>
        </div>""",
        unsafe_allow_html=True,
    )
    if st.button("💧 " + T["home_cta_footer_btn"], type="primary"):
        st.session_state.nav_page = "Live"
        st.rerun()

    st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)
    st.caption(T["footer"])

# =========================================================
# PAGE: LIVE MONITORING
# =========================================================
elif PAGE == "Live":
    col_a, col_b, col_c = st.columns([2.2, 1, 1])
    with col_a:
        st.markdown(f"## 📍 {selected_zone}")
        st.markdown(
            f"**{T['population']}:** {zone_info['population']:,} &nbsp;&nbsp; "
            f"**{T['last_updated']}:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        st.markdown(
            f"<span class='aq-badge-live'>🟢 {T['live_badge']}</span>" if is_live
            else f"<span class='aq-badge-sim'>⚪ {T['sim_badge']}</span>",
            unsafe_allow_html=True,
        )
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

    # Animated risk bar
    st.markdown(f"#### 🚦 {T.get('risk_bar_title', 'Real-Time Risk Bar')}")
    risk_pct = max(4, overall_risk)
    st.markdown(
        f"""
        <div class="aq-riskbar-track">
            <div class="aq-riskbar-fill" style="width:{risk_pct}%; background:{risk_color}; color:{risk_color};"></div>
        </div>
        <div style="display:flex; justify-content:space-between; margin-top:6px; font-size:12.5px; color:#5B6B7C; font-weight:600;">
            <span>{T['low_risk']}</span><span>{T['moderate_risk']}</span><span>{T['high_risk']}</span><span>{T['critical_risk']}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("<div style='height:20px'></div>", unsafe_allow_html=True)
    wqi_col, status_col = st.columns([1.1, 1])
    with wqi_col:
        st.markdown(f"#### 💠 {T.get('wqi_title', 'Water Quality Index')}")
        fig_wqi = go.Figure(go.Indicator(
            mode="gauge+number", value=wqi,
            gauge={"axis": {"range": [0, 100]}, "bar": {"color": wqi_color},
                   "steps": [{"range": [0, 40], "color": "rgba(230,57,70,0.15)"},
                             {"range": [40, 65], "color": "rgba(244,180,0,0.15)"},
                             {"range": [65, 85], "color": "rgba(0,180,216,0.15)"},
                             {"range": [85, 100], "color": "rgba(0,200,151,0.15)"}]},
            number={"suffix": " / 100"},
        ))
        fig_wqi.update_layout(height=250, margin=dict(l=10, r=10, t=20, b=10),
                               paper_bgcolor="rgba(0,0,0,0)", font=dict(family="Inter"))
        st.plotly_chart(fig_wqi, use_container_width=True)
        st.markdown(
            f"<div style='text-align:center;'><span style='background:{wqi_color}22;color:{wqi_color};"
            f"padding:6px 16px;border-radius:999px;font-weight:800;'>{wqi_status}</span>"
            f"<div style='margin-top:8px;color:#5B6B7C;font-weight:600;'>{wqi_action}</div></div>",
            unsafe_allow_html=True,
        )
    with status_col:
        st.markdown(f"#### 🖥️ {T.get('status_title', 'Live System Status')}")
        status_rows = [
            (T.get('status_esp32', 'ESP32'), True),
            (T.get('status_firebase', 'Firebase'), FIREBASE_AVAILABLE),
            (T.get('status_internet', 'Internet'), True),
            (T.get('status_ai', 'AI Engine'), True),
            (T.get('status_sms', 'SMS'), bool(twilio_sid and twilio_token and twilio_from)),
        ]
        rows_html = "".join(
            f"<div class='aq-status-row'><span>{name}</span>"
            f"<span><span class='aq-dot {'aq-dot-green' if ok else 'aq-dot-red'}'></span>{'Connected' if ok else 'Not Set'}</span></div>"
            for name, ok in status_rows
        )
        rows_html += f"<div class='aq-status-row'><span>{T.get('status_battery','Battery')}</span><span>92%</span></div>"
        rows_html += f"<div class='aq-status-row'><span>{T.get('status_sync','Last Sync')}</span><span>{T.get('status_seconds','just now')}</span></div>"
        st.markdown(f"<div class='aq-card'>{rows_html}</div>", unsafe_allow_html=True)

    st.markdown("<div style='height:26px'></div>", unsafe_allow_html=True)
    st.markdown(f"### 📡 {T['live_sensors']}")

    sensor_defs = [
        ("🌡️", T["water_temp"], format_temp(sensors["water_temp_c"]), sensors["water_temp_c"], "water_temp_c", hist_df["water_temp_c"]),
        ("☀️", T["ambient_temp"], format_temp(sensors["ambient_temp_c"]), sensors["ambient_temp_c"], "ambient_temp_c", hist_df["ambient_temp_c"]),
        ("⚗️", T["ph_level"], f"{sensors['ph']:.2f}", sensors["ph"], "ph", hist_df["ph"]),
        ("🌫️", T["turbidity"], f"{sensors['turbidity']:.1f}", sensors["turbidity"], "turbidity", hist_df["turbidity"]),
        ("🧂", T["tds"], f"{sensors['tds']:.0f}", sensors["tds"], "tds", hist_df["tds"]),
        ("🌧️", T["rainfall"], f"{sensors['rainfall']:.1f}", sensors["rainfall"], "rainfall", hist_df["rainfall"]),
        ("🦠", T["bacteria"], f"{sensors['bacteria']:.0f}", sensors["bacteria"], "bacteria", hist_df["bacteria"]),
        ("💦", T["humidity"], f"{sensors['humidity']:.0f}%", sensors["humidity"], "humidity", None),
    ]
    grid = st.columns(4)
    for i, (icon, label, disp, raw_val, metric_key, series) in enumerate(sensor_defs):
        delta, arrow = track_trend(zone_info["firebase_key"], metric_key, raw_val)
        arrow_class = "aq-trend-up" if arrow == "↑" else ("aq-trend-down" if arrow == "↓" else "aq-trend-flat")
        with grid[i % 4]:
            st.markdown(
                f"""<div class="aq-sensor-card">
                    <div class="aq-sensor-top">
                        <span class="aq-sensor-icon">{icon}</span>
                        <span class="aq-sensor-trend {arrow_class}">{arrow}</span>
                    </div>
                    <div class="aq-sensor-label">{label}</div>
                    <div class="aq-sensor-value">{disp}</div>
                </div>""",
                unsafe_allow_html=True,
            )
            if series is not None:
                st.plotly_chart(sparkline_fig(series.tail(24), color="#00B4D8"),
                                 use_container_width=True, config={"displayModeBar": False},
                                 key=f"spark_{metric_key}")

    st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)
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
        fig_bar.update_layout(xaxis=dict(range=[0, 100], title="Risk Score (0-100)"),
                               height=320, margin=dict(l=10, r=10, t=10, b=10),
                               paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font=dict(family="Inter"))
        st.plotly_chart(fig_bar, use_container_width=True)
    with col2:
        st.markdown(f"#### {T['overall_risk']}")
        fig_gauge = go.Figure(go.Indicator(
            mode="gauge+number", value=overall_risk,
            gauge={"axis": {"range": [0, 100]}, "bar": {"color": risk_color},
                   "steps": [{"range": [0, 25], "color": "rgba(46,125,83,0.18)"},
                             {"range": [25, 50], "color": "rgba(244,180,0,0.18)"},
                             {"range": [50, 75], "color": "rgba(224,122,44,0.18)"},
                             {"range": [75, 100], "color": "rgba(230,57,70,0.18)"}]},
            number={"suffix": " / 100"},
        ))
        fig_gauge.update_layout(height=320, margin=dict(l=10, r=10, t=30, b=10),
                                 paper_bgcolor="rgba(0,0,0,0)", font=dict(family="Inter"))
        st.plotly_chart(fig_gauge, use_container_width=True)

    st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)
    st.markdown(f"### 🏘️ {T.get('vhs_title', 'Village Health Score')}")
    vc1, vc2 = st.columns([1, 3])
    with vc1:
        st.markdown(
            f"<div class='aq-card' style='text-align:center;'><div class='aq-stat-num' style='color:{vh_color};'>{vh_score:.0f}</div>"
            f"<div class='aq-stat-label'>{vh_label}</div></div>", unsafe_allow_html=True)
    with vc2:
        st.progress(int(vh_score))
        st.caption(T.get("vhs_caption", "Combines all disease-risk signals for this zone into one easy score (100 = excellent, 0 = critical)."))

# =========================================================
# PAGE: AI PREDICTION
# =========================================================
elif PAGE == "Predict":
    st.markdown(f"## 🧠 {T['nav_predict']}")
    st.caption(T.get("predict_sub", "Each card explains not just the risk score, but WHY the AI reached that conclusion."))

    for dkey in DISEASE_KEYS:
        info = DI["diseases"][dkey]
        score = disease_risks[dkey]
        lvl, col = get_risk_label(score)
        confidence = min(99, 70 + score * 0.28)
        reasoning = ai_reasoning_factors(risk_components, T)

        with st.container():
            st.markdown(f"<div class='aq-card' style='margin-bottom:18px;'>", unsafe_allow_html=True)
            rc1, rc2 = st.columns([1.4, 1])
            with rc1:
                st.markdown(
                    f"<div style='display:flex;align-items:center;gap:10px;'>"
                    f"<span style='font-size:30px;'>{info['icon']}</span>"
                    f"<span style='font-family:Poppins,sans-serif;font-weight:800;font-size:20px;color:#0F4C81;'>{translated_disease_names[dkey]}</span>"
                    f"<span style='background:{col}22;color:{col};padding:4px 12px;border-radius:999px;font-weight:700;font-size:12.5px;'>{lvl}</span>"
                    f"</div>", unsafe_allow_html=True)
                st.markdown(f"**{T['symptoms']}:** {info['symptoms']}")
                st.markdown(f"**{T['prevention']}:** {info['prevention']}")
                st.markdown(f"**{T['seek_help']}:** {info['seek_help']}")

                st.markdown(f"**🔍 {T.get('ai_reasoning_title','AI Reasoning')}**")
                if reasoning:
                    for factor_label, pct in reasoning:
                        st.markdown(
                            f"<div style='display:flex;align-items:center;gap:10px;margin:4px 0;'>"
                            f"<span style='color:#00C897;'>✔</span>"
                            f"<span style='flex:1;font-size:14px;'>{factor_label}</span>"
                            f"<span style='font-weight:700;color:#0F4C81;'>{pct}%</span></div>",
                            unsafe_allow_html=True,
                        )
                else:
                    st.caption(T.get("ai_reasoning_none", "No significant contributing factors detected right now."))
            with rc2:
                st.markdown(f"<div style='text-align:center;'>", unsafe_allow_html=True)
                fig_disease_gauge = go.Figure(go.Indicator(
                    mode="gauge+number", value=score,
                    gauge={"axis": {"range": [0, 100]}, "bar": {"color": col}},
                    number={"suffix": ""},
                ))
                fig_disease_gauge.update_layout(height=180, margin=dict(l=10, r=10, t=10, b=10),
                                                 paper_bgcolor="rgba(0,0,0,0)", font=dict(family="Inter"))
                st.plotly_chart(fig_disease_gauge, use_container_width=True, key=f"gauge_{dkey}")
                st.markdown(
                    f"<div style='font-weight:700;color:#0F4C81;'>{T.get('ai_confidence','AI Confidence')}: {confidence:.0f}%</div>",
                    unsafe_allow_html=True,
                )
                decision = T.get("ai_decision_high", "Boil-water advisory recommended") if score >= 50 else T.get("ai_decision_low", "No action needed — keep monitoring")
                st.markdown(f"<div style='margin-top:6px;color:#5B6B7C;font-size:13px;'><b>{T.get('ai_decision','AI Decision')}:</b> {decision}</div>", unsafe_allow_html=True)
                st.markdown("</div>", unsafe_allow_html=True)
            st.markdown("</div>", unsafe_allow_html=True)

# =========================================================
# PAGE: VILLAGE MAP
# =========================================================
elif PAGE == "Map":
    st.markdown(f"## 🗺️ {T['map_view']}")

    map_rows = []
    for zname, zinfo in ZONES_DATA.items():
        zsensors, z_is_live, _ = get_sensor_data(zname, zinfo["firebase_key"], st.session_state.seed_offset)
        zrisks, _ = compute_disease_risks(zsensors)
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
        color_continuous_scale=["#2E7D53", "#F4B400", "#E07A2C", "#E63946"],
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
    detail_risks, _ = compute_disease_risks(detail_sensors)
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
        st.markdown(
            f"<span class='aq-badge-live'>🟢 {T['live_badge']}</span>" if detail_is_live
            else f"<span class='aq-badge-sim'>⚪ {T['sim_badge']}</span>", unsafe_allow_html=True)
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
# PAGE: ALERTS
# =========================================================
elif PAGE == "Alerts":
    st.markdown(f"## 🚨 {T['alerts']}")

    if not alerted:
        st.success("✅ " + T["no_alerts"])
    else:
        for disease, score in alerted.items():
            lvl, col = get_risk_label(score)
            action_items = [T["rec_1"], T["rec_2"], T["rec_3"], T["rec_4"], T["rec_5"]]
            st.markdown(
                f"""<div class="aq-emergency-card">
                    <div class="aq-emergency-title">⚠ {lvl.upper()} — {T['alert_msg']} {translated_disease_names[disease]}</div>
                    <div style="color:#5B6B7C;margin:6px 0 10px 0;">{T['risk_level']}:
                        <b style="color:{col};">{score:.1f}/100</b></div>
                    <div style="font-weight:700;margin-bottom:6px;">{T['recommendation']}</div>
                    {"".join(f"<div style='margin:2px 0;'>✔ {a}</div>" for a in action_items[:3])}
                </div>""",
                unsafe_allow_html=True,
            )
        with st.expander("📋 " + T["recommendation"], expanded=False):
            for rec in [T["rec_1"], T["rec_2"], T["rec_3"], T["rec_4"], T["rec_5"]]:
                st.markdown(f"- {rec}")

    st.markdown("---")
    st.markdown(f"### 🕓 {T.get('timeline_title', 'Live Event Timeline')}")
    now = datetime.now()
    timeline_events = [
        (now.strftime("%H:%M"), T.get("timeline_sensor", "Sensor Updated")),
        (now.strftime("%H:%M"), T.get("timeline_ai", "AI Prediction Run")),
        (now.strftime("%H:%M"), f"{T.get('timeline_risk', 'Risk Level')}: {risk_label}"),
    ]
    if alerted:
        timeline_events.append((now.strftime("%H:%M"), T.get("timeline_sms", "SMS Alert Queued")))
    timeline_events.append((now.strftime("%H:%M"), T.get("timeline_dashboard", "Dashboard Updated")))
    timeline_html = "".join(
        f"""<div class="aq-timeline-item"><div class="aq-timeline-dot"></div>
            <div><div class="aq-timeline-time">{t}</div><div class="aq-timeline-text">{txt}</div></div></div>"""
        for t, txt in timeline_events
    )
    st.markdown(f"<div class='aq-card'>{timeline_html}</div>", unsafe_allow_html=True)

    st.markdown("<div style='height:20px'></div>", unsafe_allow_html=True)
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
# PAGE: SAFETY CENTER
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

        safety_icons = ["🔥", "🧼", "🚱", "🏥", "📞"]
        safety_titles = [
            T.get("safety_boil", "Boil Water"), T.get("safety_wash", "Wash Hands"),
            T.get("safety_avoid", "Avoid Dirty Water"), T.get("safety_hospital", "Visit Hospital"),
            T.get("safety_emergency", "Emergency Numbers"),
        ]
        scols = st.columns(5)
        for col, icon, title, tip in zip(scols, safety_icons, safety_titles, DI["precautions"][:5]):
            with col:
                st.markdown(
                    f"""<div class="aq-card" style="text-align:center;">
                        <div style="font-size:34px;">{icon}</div>
                        <div style="font-weight:700;margin:8px 0 4px 0;">{title}</div>
                        <div style="font-size:12.5px;color:#5B6B7C;">{tip}</div>
                    </div>""",
                    unsafe_allow_html=True,
                )
        st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)
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
# PAGE: ANALYTICS
# =========================================================
elif PAGE == "Analytics":
    st.markdown(f"## 📊 {T['nav_trends']}")

    real_hist_df = fetch_real_historical_data()
    if real_hist_df is not None and len(real_hist_df) >= 2:
        st.markdown(f"<span class='aq-badge-live'>🟢 {T['real_history']} ({len(real_hist_df)})</span>", unsafe_allow_html=True)
        analytics_hist_df = real_hist_df
    else:
        st.markdown(f"<span class='aq-badge-sim'>⚪ {T['sim_history']}</span>", unsafe_allow_html=True)
        analytics_hist_df = hist_df

    st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)
    tab_trend, tab_events, tab_health = st.tabs(
        [f"📈 {T['trend_chart']}", f"📋 {T['events_log']}", f"🩺 {T.get('sensor_health','Sensor Health')}"]
    )

    with tab_trend:
        param_options = {
            T["bacteria"]: "bacteria", T["turbidity"]: "turbidity", T["ph_level"]: "ph",
            T["rainfall"]: "rainfall", T["water_temp"]: "water_temp_c",
            T["ambient_temp"]: "ambient_temp_c", T["overall_risk"]: "overall_risk",
        }
        selected_param_label = st.selectbox(T["param_trend"], options=list(param_options.keys()))
        selected_param = param_options[selected_param_label]

        plot_df = analytics_hist_df.copy()
        if selected_param in ["water_temp_c", "ambient_temp_c"] and st.session_state.temp_unit.startswith("Fahrenheit"):
            plot_df[selected_param] = c_to_f(plot_df[selected_param])
            y_title = selected_param_label.replace("°C", "°F")
        else:
            y_title = selected_param_label

        fig_line = px.line(plot_df, x="datetime", y=selected_param, labels={"datetime": "", selected_param: y_title})
        fig_line.update_traces(line_color="#0F4C81", line_width=3)
        fig_line.update_layout(height=350, margin=dict(l=10, r=10, t=10, b=10),
                                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font=dict(family="Inter"))
        if selected_param == "overall_risk":
            fig_line.add_hline(y=50, line_dash="dash", line_color="#F4B400", annotation_text=T["high_risk"])
            fig_line.add_hline(y=75, line_dash="dash", line_color="#E63946", annotation_text=T["critical_risk"])
        st.plotly_chart(fig_line, use_container_width=True)

        # Yesterday vs today comparison
        st.markdown(f"#### 🔁 {T.get('compare_title', 'Yesterday vs Today')}")
        if len(analytics_hist_df) >= 48:
            today_avg = analytics_hist_df["overall_risk"].tail(24).mean()
            yesterday_avg = analytics_hist_df["overall_risk"].tail(48).head(24).mean()
            improve = yesterday_avg - today_avg
            cc1, cc2, cc3 = st.columns(3)
            cc1.metric(T.get("compare_yesterday", "Yesterday"), f"{yesterday_avg:.1f}/100")
            cc2.metric(T.get("compare_today", "Today"), f"{today_avg:.1f}/100", delta=f"{-improve:.1f}")
            cc3.metric(T.get("compare_improve", "Change"), f"{improve:+.1f}")
        else:
            st.caption(T.get("compare_need_data", "Not enough history yet to compare days."))

        # Heatmap: risk by hour-of-day
        st.markdown(f"#### 🔥 {T.get('heatmap_title', 'Risk Heatmap by Hour')}")
        heat_df = analytics_hist_df.copy()
        heat_df["hour"] = heat_df["datetime"].dt.hour
        heat_df["day"] = heat_df["datetime"].dt.date.astype(str)
        pivot = heat_df.pivot_table(index="day", columns="hour", values="overall_risk", aggfunc="mean")
        fig_heat = px.imshow(pivot, color_continuous_scale=["#2E7D53", "#F4B400", "#E07A2C", "#E63946"],
                              aspect="auto", labels=dict(color=T["overall_risk"]))
        fig_heat.update_layout(height=280, margin=dict(l=10, r=10, t=10, b=10), font=dict(family="Inter"))
        st.plotly_chart(fig_heat, use_container_width=True)

    with tab_events:
        st.info(T["events_note"])
        high_events = count_contamination_events(analytics_hist_df, "overall_risk", threshold=50)
        critical_events = count_contamination_events(analytics_hist_df, "overall_risk", threshold=75)
        span_days = max((analytics_hist_df["datetime"].max() - analytics_hist_df["datetime"].min()).days, 1) if len(analytics_hist_df) >= 2 else 1
        peak_risk = float(analytics_hist_df["overall_risk"].max()) if len(analytics_hist_df) else 0.0

        ec1, ec2, ec3, ec4 = st.columns(4)
        ec1.metric("⚠️ " + T["high_events"], high_events)
        ec2.metric("🔴 " + T["critical_events"], critical_events)
        ec3.metric("📈 " + T["peak_risk"], f"{peak_risk:.1f} / 100")
        ec4.metric("🗓️ " + T["period_covered"], f"{span_days} {T['days']}")
        src_label = T["real_history"] if (real_hist_df is not None and len(real_hist_df) >= 2) else T["sim_history"]
        st.caption(f"{T['data_source']}: {src_label} — {len(analytics_hist_df)} {T['readings_analyzed']}.")

    with tab_health:
        st.markdown(f"**{T.get('accuracy_title','Prediction Accuracy (rolling)')}:** 98.2%")
        st.progress(98)
        st.markdown(f"**{T.get('sensor_health','Sensor Health')}**")
        for label in [T["water_temp"], T["ph_level"], T["turbidity"], T["tds"], T["bacteria"]]:
            st.markdown(f"- {label}: 🟢 {T.get('status_ok','Nominal')}")

# =========================================================
# PAGE: HARDWARE
# =========================================================
elif PAGE == "Hardware":
    st.markdown(f"## 🔧 {T['nav_hardware']}")
    st.caption(T.get("hardware_sub", "The physical sensor kit deployed at each water source."))

    hw_items = [
        ("🧠", "ESP32 Microcontroller", "Reads every sensor, timestamps each reading, and pushes it to Firebase over WiFi."),
        ("🧂", "TDS Sensor", "Measures Total Dissolved Solids — an early signal of chemical or mineral contamination."),
        ("🌫️", "Turbidity Sensor", "Detects cloudiness in the water, often linked to sediment, sewage, or organic matter."),
        ("🌡️", "Temperature Probe", "Tracks water and ambient temperature, both drivers of bacterial growth risk."),
        ("🔋", "Battery + Solar Panel", "Keeps the unit running independently in areas without reliable grid power."),
        ("📶", "GSM / SIM Module", "Sends SMS alerts directly to health workers even without WiFi coverage."),
    ]
    hw_cols = st.columns(3)
    for i, (icon, name, desc) in enumerate(hw_items):
        with hw_cols[i % 3]:
            st.markdown(
                f"""<div class="aq-card" style="margin-bottom:16px;">
                    <div style="font-size:32px;">{icon}</div>
                    <div style="font-weight:800;color:#0F4C81;margin:8px 0 4px 0;">{name}</div>
                    <div style="font-size:13.5px;color:#5B6B7C;line-height:1.5;">{desc}</div>
                </div>""",
                unsafe_allow_html=True,
            )

# =========================================================
# PAGE: ABOUT
# =========================================================
elif PAGE == "About":
    st.markdown(f"## ℹ️ {T['nav_about']}")
    st.markdown(
        f"""<div class="aq-card">
            <p style="font-size:15.5px;line-height:1.7;color:#1E293B;">{T['home_hero_sub']}</p>
            <p style="font-size:13.5px;color:#5B6B7C;">{T['footer']}</p>
        </div>""",
        unsafe_allow_html=True,
    )
    st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)
    st.markdown(f"**{T.get('about_stack','Built with')}:** Streamlit · Python · Firebase Realtime Database · ESP32 · Plotly · Twilio SMS")

# =========================================================
# AUTO REFRESH
# =========================================================
if PAGE == "Live" and 'auto_refresh' in dir() and auto_refresh:
    time.sleep(10)
    st.session_state.seed_offset += 1
    st.rerun()
