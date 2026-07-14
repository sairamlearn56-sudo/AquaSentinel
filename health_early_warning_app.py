"""
AI-Automated Real-Time Community Health Early Warning System
for Water-Borne Disease Prediction
==============================================================

Run with:
    pip install streamlit plotly pandas numpy twilio firebase-admin
    streamlit run health_early_warning_app.py

Features:
- REAL live sensor monitoring from Firebase Realtime Database (ESP32 pushes data)
- Falls back to simulated data automatically if no live ESP32 reading is found,
  clearly labeled so you always know which one you're looking at
- AI-based risk prediction (rule-based + ML-style scoring) for cholera,
  typhoid, diarrhea, dysentery, hepatitis A
- Multi-language UI (English, Hindi, Telugu, Spanish, French)
- Temperature unit switching (Celsius / Fahrenheit)
- Interactive charts, alerts, and village/zone-wise risk map
- SMS Alert via Twilio to registered contact number

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

    (database_url is the ONE extra field you need to add - get it from
    Firebase Console -> Realtime Database -> copy the URL shown at the top)

EXPECTED ESP32 DATA STRUCTURE in Firebase Realtime Database:

    /live_readings/{zone_key}
        water_temp_c: 28.4
        ph: 7.1
        turbidity: 6.2
        tds: 420
        rainfall: 2.1
        bacteria: 145
        humidity: 68
        ambient_temp_c: 30.5
        timestamp: 1752480000   (unix epoch seconds, set by ESP32 or server)

    zone_key options used by this app: zone_a, zone_b, zone_c, zone_d, zone_e
    (see ZONES_DATA below - each zone has a "firebase_key")

    Your ESP32 sketch should push to this path, e.g. for Zone A:
        https://water-project-50ce4-default-rtdb.firebaseio.com/live_readings/zone_a.json
"""

import time
from twilio.rest import Client
import streamlit as st
TWILIO_ACCOUNT_SID = "AC6048fef4548443ba3fb309bbcfaf5a82"
TWILIO_AUTH_TOKEN = "8d401fbc0420807bae0e2bebe3b759f6"
TWILIO_PHONE_NUMBER = "+16056206948"

client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
def send_sms(message):
    try:
        client.messages.create(
            body=message,
            from_=TWILIO_PHONE_NUMBER,
            to=TO_NUMBER
        )
        print("SMS Sent Successfully")
    except Exception as e:
        print("SMS Error:", e)
import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime

# =========================================================
# PAGE CONFIG
# =========================================================
st.set_page_config(
    page_title="Water-Borne Disease Early Warning System",
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
        """
        Initializes the Firebase app exactly once per server process
        (cache_resource persists across reruns/users on this instance).
        Returns (db_module, error_message_or_None).
        """
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
    """
    Attempts to read the latest ESP32 reading from Firebase.

    NOTE: This ESP32 sketch writes ONE shared reading for the whole device
    to /waterData (not per-zone), with fields: tds, turbidity, water_temp.
    So all zones will show the SAME live reading from this single sensor
    unit until you deploy separate ESP32 units per zone with separate paths.
    zone_key is accepted for future multi-zone support but currently ignored.
    """
    if not FIREBASE_AVAILABLE:
        return None, FIREBASE_INIT_ERROR

    try:
        ref = db.reference("/waterData")
        data = ref.get()
        if not data:
            return None, "No data found at /waterData yet (ESP32 may not have pushed anything)."

        # Map the ESP32's actual field names -> the app's internal field names.
        # Sensors not sent by this ESP32 (ph, rainfall, bacteria, humidity,
        # ambient_temp_c) fall back to reasonable defaults so the risk model
        # still runs; add these sensors to the ESP32 sketch to make them live too.
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
ALERT_PHONE_NUMBER = "+919032644552"  # India (+91) + 9032644552


def send_sms_alert(message: str, account_sid: str, auth_token: str, from_number: str) -> tuple[bool, str]:
    """Send an SMS alert using Twilio. Returns (success, status_message)."""
    try:
        from twilio.rest import Client
        client = Client(account_sid, auth_token)
        msg = client.messages.create(
            body=message,
            from_=from_number,
            to=ALERT_PHONE_NUMBER,
        )
        return True, f"SMS sent! SID: {msg.sid}"
    except ImportError:
        return False, "Twilio not installed. Run: pip install twilio"
    except Exception as e:
        return False, f"SMS failed: {str(e)}"


def build_sms_message(zone: str, overall_risk: float, alerted_diseases: dict, sensors: dict) -> str:
    """Build a concise SMS alert message."""
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
# TRANSLATIONS
# =========================================================
TRANSLATIONS = {
    "English": {
        "title": "💧 AI Community Health Early Warning System",
        "subtitle": "Real-Time Water-Borne Disease Risk Prediction",
        "settings": "⚙️ Settings",
        "language": "Language",
        "temp_unit": "Temperature Unit",
        "select_zone": "Select Zone / Village",
        "overview": "Overview",
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
        "no_alerts": "✅ No active alerts. Conditions normal.",
        "alert_msg": "⚠️ ALERT: Elevated risk detected for",
        "recommendation": "Recommended Actions",
        "rec_1": "Increase water chlorination and disinfection frequency",
        "rec_2": "Distribute oral rehydration salts (ORS) to community health centers",
        "rec_3": "Issue public advisory: boil water before consumption",
        "rec_4": "Deploy health workers for door-to-door screening",
        "rec_5": "Increase surveillance and sample testing frequency",
        "last_updated": "Last updated",
        "refresh": "🔄 Refresh Data",
        "auto_refresh": "Auto-refresh every 10s",
        "footer": "AI-driven prototype for early warning of water-borne diseases (cholera, typhoid, diarrhea, dysentery, hepatitis A). For demonstration purposes only.",
        "diseases": ["Cholera", "Typhoid", "Diarrhea", "Dysentery", "Hepatitis A"],
        "param_trend": "Select Parameter for Trend",
        "risk_level": "Risk Level",
        "zone": "Zone",
        "population": "Population",
        "cases_7d": "Cases (Last 7 Days)",
        "summary": "Summary",
        "key_insights": "Key Insights",
        "insight_1": "rising trend detected over the last 24 hours",
        "insight_2": "Bacterial contamination levels are within safe limits",
        "insight_3": "Heavy rainfall increases contamination risk significantly",
        "sms_settings": "📱 SMS Alert Settings",
        "twilio_sid": "Twilio Account SID",
        "twilio_token": "Twilio Auth Token",
        "twilio_from": "Twilio Phone Number (from)",
        "send_sms": "📲 Send SMS Alert Now",
        "sms_target": "Alert SMS Target",
        "sms_threshold": "SMS Alert Threshold (Risk Score)",
        "sms_auto": "Auto-send SMS when risk exceeds threshold",
        "sms_preview": "SMS Preview",
    },
    "हिन्दी (Hindi)": {
        "title": "💧 एआई सामुदायिक स्वास्थ्य पूर्व चेतावनी प्रणाली",
        "subtitle": "जल-जनित रोगों के जोखिम की वास्तविक समय भविष्यवाणी",
        "settings": "⚙️ सेटिंग्स",
        "language": "भाषा",
        "temp_unit": "तापमान इकाई",
        "select_zone": "क्षेत्र / गांव चुनें",
        "overview": "सारांश",
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
        "no_alerts": "✅ कोई सक्रिय चेतावनी नहीं। स्थिति सामान्य है।",
        "alert_msg": "⚠️ चेतावनी: इसके लिए बढ़ा हुआ जोखिम पाया गया",
        "recommendation": "अनुशंसित कार्रवाई",
        "rec_1": "जल क्लोरीनीकरण और कीटाणुशोधन की आवृत्ति बढ़ाएं",
        "rec_2": "सामुदायिक स्वास्थ्य केंद्रों में ओआरएस वितरित करें",
        "rec_3": "सार्वजनिक सलाह जारी करें: पानी उबालकर पिएं",
        "rec_4": "घर-घर जांच के लिए स्वास्थ्य कर्मियों को तैनात करें",
        "rec_5": "निगरानी और नमूना परीक्षण की आवृत्ति बढ़ाएं",
        "last_updated": "अंतिम अद्यतन",
        "refresh": "🔄 डेटा रीफ्रेश करें",
        "auto_refresh": "हर 10 सेकंड में ऑटो-रीफ्रेश करें",
        "footer": "जल-जनित रोगों (हैजा, टाइफाइड, दस्त, पेचिश, हेपेटाइटिस ए) की पूर्व चेतावनी के लिए एआई-संचालित प्रोटोटाइप। केवल प्रदर्शन उद्देश्यों के लिए।",
        "diseases": ["हैजा", "टाइफाइड", "दस्त", "पेचिश", "हेपेटाइटिस ए"],
        "param_trend": "रुझान के लिए पैरामीटर चुनें",
        "risk_level": "जोखिम स्तर",
        "zone": "क्षेत्र",
        "population": "जनसंख्या",
        "cases_7d": "मामले (पिछले 7 दिन)",
        "summary": "सारांश",
        "key_insights": "मुख्य अंतर्दृष्टि",
        "insight_1": "पिछले 24 घंटों में बढ़ता रुझान देखा गया",
        "insight_2": "बैक्टीरिया संदूषण स्तर सुरक्षित सीमा के भीतर है",
        "insight_3": "भारी वर्षा संदूषण जोखिम को काफी बढ़ा देती है",
        "sms_settings": "📱 एसएमएस अलर्ट सेटिंग्स",
        "twilio_sid": "Twilio अकाउंट SID",
        "twilio_token": "Twilio Auth Token",
        "twilio_from": "Twilio फ़ोन नंबर (से)",
        "send_sms": "📲 एसएमएस अलर्ट भेजें",
        "sms_target": "अलर्ट एसएमएस लक्ष्य",
        "sms_threshold": "एसएमएस अलर्ट थ्रेशोल्ड (जोखिम स्कोर)",
        "sms_auto": "थ्रेशोल्ड पार होने पर ऑटो एसएमएस भेजें",
        "sms_preview": "एसएमएस प्रीव्यू",
    },
    "తెలుగు (Telugu)": {
        "title": "💧 AI కమ్యూనిటీ హెల్త్ ముందస్తు హెచ్చరిక వ్యవస్థ",
        "subtitle": "నీటి ద్వారా వ్యాపించే వ్యాధుల రియల్-టైమ్ ప్రమాద అంచనా",
        "settings": "⚙️ సెట్టింగ్‌లు",
        "language": "భాష",
        "temp_unit": "ఉష్ణోగ్రత యూనిట్",
        "select_zone": "జోన్ / గ్రామం ఎంచుకోండి",
        "overview": "అవలోకనం",
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
        "no_alerts": "✅ క్రియాశీల హెచ్చరికలు లేవు. పరిస్థితులు సాధారణం.",
        "alert_msg": "⚠️ హెచ్చరిక: దీనికి పెరిగిన ప్రమాదం గుర్తించబడింది",
        "recommendation": "సిఫార్సు చేసిన చర్యలు",
        "rec_1": "నీటి క్లోరినేషన్ మరియు క్రిమిసంహారక ఫ్రీక్వెన్సీని పెంచండి",
        "rec_2": "కమ్యూనిటీ హెల్త్ సెంటర్లకు ORS ను పంపిణీ చేయండి",
        "rec_3": "ప్రజా సూచన జారీ చేయండి: నీటిని మరిగించి తాగండి",
        "rec_4": "ఇంటింటి స్క్రీనింగ్ కోసం ఆరోగ్య కార్యకర్తలను నియమించండి",
        "rec_5": "నిఘా మరియు నమూనా పరీక్ష ఫ్రీక్వెన్సీని పెంచండి",
        "last_updated": "చివరిగా నవీకరించబడింది",
        "refresh": "🔄 డేటాను రిఫ్రెష్ చేయండి",
        "auto_refresh": "ప్రతి 10 సెకన్లకు ఆటో-రిఫ్రెష్",
        "footer": "నీటి ద్వారా వ్యాపించే వ్యాధుల (కలరా, టైఫాయిడ్, డయేరియా, డిసెంటరీ, హెపటైటిస్ A) ముందస్తు హెచ్చరిక కోసం AI ఆధారిత ప్రోటోటైప్. ప్రదర్శన ప్రయోజనాల కోసం మాత్రమే.",
        "diseases": ["కలరా", "టైఫాయిడ్", "డయేరియా", "డిసెంటరీ", "హెపటైటిస్ A"],
        "param_trend": "ధోరణి కోసం పారామితిని ఎంచుకోండి",
        "risk_level": "ప్రమాద స్థాయి",
        "zone": "జోన్",
        "population": "జనాభా",
        "cases_7d": "కేసులు (గత 7 రోజులు)",
        "summary": "సారాంశం",
        "key_insights": "ముఖ్య అంతర్దృష్టులు",
        "insight_1": "గత 24 గంటల్లో పెరుగుతున్న ధోరణి గుర్తించబడింది",
        "insight_2": "బ్యాక్టీరియా కాలుష్య స్థాయిలు సురక్షిత పరిమితుల్లో ఉన్నాయి",
        "insight_3": "భారీ వర్షపాతం కాలుష్య ప్రమాదాన్ని గణనీయంగా పెంచుతుంది",
        "sms_settings": "📱 SMS హెచ్చరిక సెట్టింగ్‌లు",
        "twilio_sid": "Twilio అకౌంట్ SID",
        "twilio_token": "Twilio Auth Token",
        "twilio_from": "Twilio ఫోన్ నంబర్ (నుండి)",
        "send_sms": "📲 SMS హెచ్చరిక పంపండి",
        "sms_target": "హెచ్చరిక SMS లక్ష్యం",
        "sms_threshold": "SMS హెచ్చరిక థ్రెషోల్డ్ (ప్రమాద స్కోర్)",
        "sms_auto": "థ్రెషోల్డ్ మించినప్పుడు ఆటో SMS పంపండి",
        "sms_preview": "SMS ప్రివ్యూ",
    },
    "Español (Spanish)": {
        "title": "💧 Sistema de Alerta Temprana de Salud Comunitaria con IA",
        "subtitle": "Predicción en Tiempo Real del Riesgo de Enfermedades Hídricas",
        "settings": "⚙️ Configuración",
        "language": "Idioma",
        "temp_unit": "Unidad de Temperatura",
        "select_zone": "Seleccionar Zona / Pueblo",
        "overview": "Resumen",
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
        "no_alerts": "✅ No hay alertas activas. Condiciones normales.",
        "alert_msg": "⚠️ ALERTA: Riesgo elevado detectado para",
        "recommendation": "Acciones Recomendadas",
        "rec_1": "Aumentar la frecuencia de cloración y desinfección del agua",
        "rec_2": "Distribuir sales de rehidratación oral (SRO) a los centros de salud",
        "rec_3": "Emitir aviso público: hervir el agua antes de consumirla",
        "rec_4": "Desplegar trabajadores de salud para evaluación puerta a puerta",
        "rec_5": "Aumentar la vigilancia y la frecuencia de pruebas",
        "last_updated": "Última actualización",
        "refresh": "🔄 Actualizar Datos",
        "auto_refresh": "Actualizar automáticamente cada 10s",
        "footer": "Prototipo basado en IA para alerta temprana de enfermedades transmitidas por el agua (cólera, fiebre tifoidea, diarrea, disentería, hepatitis A). Solo con fines de demostración.",
        "diseases": ["Cólera", "Fiebre Tifoidea", "Diarrea", "Disentería", "Hepatitis A"],
        "param_trend": "Seleccionar Parámetro para Tendencia",
        "risk_level": "Nivel de Riesgo",
        "zone": "Zona",
        "population": "Población",
        "cases_7d": "Casos (Últimos 7 Días)",
        "summary": "Resumen",
        "key_insights": "Conclusiones Clave",
        "insight_1": "tendencia al alza detectada en las últimas 24 horas",
        "insight_2": "Los niveles de contaminación bacteriana están dentro de límites seguros",
        "insight_3": "Las lluvias intensas aumentan significativamente el riesgo de contaminación",
        "sms_settings": "📱 Configuración de Alerta SMS",
        "twilio_sid": "SID de Cuenta Twilio",
        "twilio_token": "Token de Autenticación Twilio",
        "twilio_from": "Número de Teléfono Twilio (desde)",
        "send_sms": "📲 Enviar Alerta SMS Ahora",
        "sms_target": "Destino SMS de Alerta",
        "sms_threshold": "Umbral de Alerta SMS (Puntuación de Riesgo)",
        "sms_auto": "Envío automático de SMS cuando el riesgo supere el umbral",
        "sms_preview": "Vista Previa del SMS",
    },
    "Français (French)": {
        "title": "💧 Système d'Alerte Précoce de Santé Communautaire par IA",
        "subtitle": "Prédiction en Temps Réel du Risque de Maladies Hydriques",
        "settings": "⚙️ Paramètres",
        "language": "Langue",
        "temp_unit": "Unité de Température",
        "select_zone": "Sélectionner Zone / Village",
        "overview": "Aperçu",
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
        "no_alerts": "✅ Aucune alerte active. Conditions normales.",
        "alert_msg": "⚠️ ALERTE : Risque élevé détecté pour",
        "recommendation": "Actions Recommandées",
        "rec_1": "Augmenter la fréquence de chloration et de désinfection de l'eau",
        "rec_2": "Distribuer des sels de réhydratation orale (SRO) aux centres de santé",
        "rec_3": "Émettre un avis public : faire bouillir l'eau avant consommation",
        "rec_4": "Déployer des agents de santé pour le dépistage porte-à-porte",
        "rec_5": "Augmenter la surveillance et la fréquence des tests",
        "last_updated": "Dernière mise à jour",
        "refresh": "🔄 Actualiser les Données",
        "auto_refresh": "Actualisation automatique toutes les 10s",
        "footer": "Prototype basé sur l'IA pour l'alerte précoce des maladies hydriques (choléra, typhoïde, diarrhée, dysenterie, hépatite A). À des fins de démonstration uniquement.",
        "diseases": ["Choléra", "Typhoïde", "Diarrhée", "Dysenterie", "Hépatite A"],
        "param_trend": "Sélectionner un Paramètre pour la Tendance",
        "risk_level": "Niveau de Risque",
        "zone": "Zone",
        "population": "Population",
        "cases_7d": "Cas (7 Derniers Jours)",
        "summary": "Résumé",
        "key_insights": "Points Clés",
        "insight_1": "tendance à la hausse détectée au cours des dernières 24 heures",
        "insight_2": "Les niveaux de contamination bactérienne sont dans les limites sûres",
        "insight_3": "De fortes pluies augmentent considérablement le risque de contamination",
        "sms_settings": "📱 Paramètres d'Alerte SMS",
        "twilio_sid": "SID de Compte Twilio",
        "twilio_token": "Jeton d'Authentification Twilio",
        "twilio_from": "Numéro de Téléphone Twilio (depuis)",
        "send_sms": "📲 Envoyer une Alerte SMS Maintenant",
        "sms_target": "Destinataire SMS d'Alerte",
        "sms_threshold": "Seuil d'Alerte SMS (Score de Risque)",
        "sms_auto": "Envoi SMS automatique si le risque dépasse le seuil",
        "sms_preview": "Aperçu du SMS",
    },
}

# =========================================================
# SESSION STATE INIT
# =========================================================
if "language" not in st.session_state:
    st.session_state.language = "English"
if "temp_unit" not in st.session_state:
    st.session_state.temp_unit = "Celsius (°C)"
if "seed_offset" not in st.session_state:
    st.session_state.seed_offset = 0
if "last_sms_sent_score" not in st.session_state:
    st.session_state.last_sms_sent_score = None
if "sms_log" not in st.session_state:
    st.session_state.sms_log = []

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
        return T["low_risk"], "#2ecc71"
    elif score < 50:
        return T["moderate_risk"], "#f1c40f"
    elif score < 75:
        return T["high_risk"], "#e67e22"
    else:
        return T["critical_risk"], "#e74c3c"


def generate_simulated_sensor_data(zone_name, offset=0):
    """Fallback ONLY - used when no live ESP32 reading is available in Firebase."""
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
    """
    Tries live Firebase/ESP32 data first. Falls back to simulated data
    if unavailable, and reports which source was used + any error.
    """
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
    """
    Reads real logged sensor history from Firebase at /history
    (populated by the ESP32 using http.POST(), which appends a new
    timestamped entry each time instead of overwriting one value).

    Returns a DataFrame sorted by time, or None if no real history
    exists yet (e.g. ESP32 hasn't been updated to log history, or
    hasn't run long enough to build up entries).
    """
    if not FIREBASE_AVAILABLE:
        return None

    try:
        ref = db.reference("/history")
        # order_by_key + limit_to_last keeps this fast even if history is large
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

        # Overall risk per historical row, using the same weighting as compute_disease_risks,
        # so the trend line is consistent with the live risk score elsewhere in the app.
        bact_risk = np.clip(df["bacteria"].fillna(0) / 4, 0, 100)
        turb_risk = np.clip(df["turbidity"].fillna(0) * 4, 0, 100)
        rain_risk = np.clip(df["rainfall"].fillna(0) * 3, 0, 100)
        df["overall_risk"] = np.clip(0.4 * bact_risk + 0.3 * turb_risk + 0.3 * rain_risk, 0, 100)

        return df
    except Exception:
        return None


def generate_historical_data(zone_name, days=14):
    """
    Historical trend data. NOTE: this remains simulated because it requires
    ESP32 + Firebase to have been logging readings over time (e.g. writing
    to /history/{zone_key}/{timestamp} instead of overwriting one node).
    If you want REAL historical trends, have your ESP32 push each reading
    to a new child under /history/{zone_key} instead of overwriting
    /live_readings/{zone_key}, then swap this function to read that path.
    """
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


# =========================================================
# ZONE CONFIG (firebase_key = path used under /live_readings/)
# =========================================================
ZONES_DATA = {
    "Zone A - Riverside Village":   {"population": 4200, "lat": 17.385, "lon": 78.486, "firebase_key": "zone_a"},
    "Zone B - Hillside Settlement": {"population": 2800, "lat": 17.405, "lon": 78.466, "firebase_key": "zone_b"},
    "Zone C - Lakeside Town":       {"population": 6100, "lat": 17.365, "lon": 78.506, "firebase_key": "zone_c"},
    "Zone D - Central District":    {"population": 9500, "lat": 17.395, "lon": 78.496, "firebase_key": "zone_d"},
    "Zone E - Floodplain Area":     {"population": 3300, "lat": 17.375, "lon": 78.476, "firebase_key": "zone_e"},
}


def count_contamination_events(df, column="overall_risk", threshold=50):
    """
    Counts contamination 'events' rather than raw rows above threshold.
    An event = one crossing from below the threshold to at/above it, so a
    sustained 3-hour spike counts as ONE event, not dozens of rows.
    """
    if df is None or column not in df.columns or len(df) < 2:
        return 0
    above = df[column].fillna(0) >= threshold
    crossings = above & ~above.shift(1, fill_value=False)
    return int(crossings.sum())


def summarize_zone_history(zone_name, firebase_key, real_hist_df_available):
    """
    Builds a per-zone historical summary: uses the REAL logged history if
    this zone matches the physical sensor's data (all zones currently share
    one ESP32 until multiple units are deployed), otherwise uses that
    zone's simulated series so every zone still has a sensible summary.
    Returns a dict with event counts and peak risk.
    """
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
# SAFETY & PRECAUTION CONTENT
# (Educational public-health guidance, English-only content;
#  UI chrome around it still respects the selected language.)
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
    "Cholera": {
        "icon": "🦠",
        "symptoms": "Sudden watery diarrhea, vomiting, rapid dehydration.",
        "prevention": "Drink only boiled/treated water; avoid raw or undercooked seafood from affected areas.",
        "seek_help": "Seek medical care immediately if severe watery diarrhea or signs of dehydration (dizziness, dry mouth, reduced urination) appear.",
    },
    "Typhoid": {
        "icon": "🌡️",
        "symptoms": "Prolonged fever, weakness, stomach pain, headache.",
        "prevention": "Practice good hand hygiene; avoid street food/water of unknown source in affected zones.",
        "seek_help": "See a doctor if fever persists beyond 2–3 days, especially alongside stomach pain.",
    },
    "Diarrhea": {
        "icon": "💧",
        "symptoms": "Frequent loose stools, cramping, mild fever.",
        "prevention": "Maintain safe drinking water and food hygiene; wash hands regularly.",
        "seek_help": "Use oral rehydration salts (ORS); seek care if symptoms last more than 2 days or worsen.",
    },
    "Dysentery": {
        "icon": "🩸",
        "symptoms": "Bloody or mucus-mixed diarrhea, abdominal cramps, fever.",
        "prevention": "Avoid contaminated water sources; ensure food is thoroughly cooked and served hot.",
        "seek_help": "Seek medical attention promptly if blood is visible in stool.",
    },
    "Hepatitis A": {
        "icon": "🫀",
        "symptoms": "Fatigue, nausea, abdominal pain, jaundice (yellowing of skin/eyes).",
        "prevention": "Vaccination where available; avoid raw shellfish and untreated water in affected areas.",
        "seek_help": "Consult a doctor if jaundice, dark urine, or persistent fatigue develop.",
    },
}

# =========================================================
# SIDEBAR - SETTINGS
# =========================================================
T = TRANSLATIONS[st.session_state.language]

with st.sidebar:
    st.markdown("## " + T["settings"])

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

    st.markdown("---")

    selected_zone = st.selectbox(T["select_zone"], options=list(ZONES_DATA.keys()))

    st.markdown("---")

    # Firebase / ESP32 connection status indicator
    if FIREBASE_AVAILABLE:
        st.success("🟢 Firebase connected")
    else:
        st.error(f"🔴 Firebase not connected: {FIREBASE_INIT_ERROR}")

    auto_refresh = st.checkbox(T["auto_refresh"], value=False)
    if st.button(T["refresh"], use_container_width=True):
        st.session_state.seed_offset += 1
        st.rerun()

    # ── SMS Settings ──────────────────────────────────────
    st.markdown("---")
    st.markdown("## " + T["sms_settings"])

    st.markdown(f"**{T['sms_target']}:** `{ALERT_PHONE_NUMBER}`")

    st.success("✅ SMS Alerts Enabled")

    sms_threshold = st.slider(T["sms_threshold"], min_value=10, max_value=90, value=50, step=5)
    sms_auto = st.checkbox(T["sms_auto"], value=False)

    st.markdown("---")
    st.caption(T["footer"])



# =========================================================
# DATA FETCH (live ESP32 via Firebase, with simulated fallback)
# =========================================================
zone_info = ZONES_DATA[selected_zone]
sensors, is_live, fetch_error = get_sensor_data(
    selected_zone, zone_info["firebase_key"], st.session_state.seed_offset
)
disease_risks = compute_disease_risks(sensors)
overall_risk = float(np.mean(list(disease_risks.values())))
if overall_risk >= 70:
    send_sms(
        f"🚨 Aqua Sentinel AI Alert!\n"
        f"Overall Risk: {overall_risk:.1f}/100\n"
        f"Water quality is UNSAFE.\n"
        f"Please inspect the water source immediately."
    )
hist_df = generate_historical_data(selected_zone)
alerted = {k: v for k, v in disease_risks.items() if v >= 50}
translated_disease_names = dict(zip(
    ["Cholera", "Typhoid", "Diarrhea", "Dysentery", "Hepatitis A"], T["diseases"]
))

# =========================================================
# LIVE DATA STATUS BANNER
# =========================================================
if is_live:
    ts_display = ""
    if sensors.get("timestamp"):
        try:
            ts_display = f" (ESP32 timestamp: {datetime.fromtimestamp(sensors['timestamp']).strftime('%Y-%m-%d %H:%M:%S')})"
        except Exception:
            pass
    st.success(f"🟢 Showing LIVE ESP32 sensor data for {selected_zone}{ts_display}")
else:
    st.warning(
        f"⚠️ No live ESP32 reading available for {selected_zone} — showing SIMULATED demo data instead. "
        f"Reason: {fetch_error}"
    )

# =========================================================
# AUTO-SMS LOGIC (fires once per threshold crossing)
# =========================================================
sms_status_placeholder = st.empty()

if sms_auto and overall_risk >= sms_threshold:
    prev = st.session_state.last_sms_sent_score
    if prev is None or prev < sms_threshold:
        if True:
            sms_body = build_sms_message(selected_zone, overall_risk, alerted or {"Overall": overall_risk}, sensors)
           ok, status = send_sms_alert(
    sms_body,
    TWILIO_ACCOUNT_SID,
    TWILIO_AUTH_TOKEN,
    TWILIO_PHONE_NUMBER
)
            st.session_state.last_sms_sent_score = overall_risk
            log_entry = {
                "time": datetime.now().strftime("%H:%M:%S"),
                "zone": selected_zone,
                "score": f"{overall_risk:.1f}",
                "status": "✅ Sent" if ok else f"❌ {status}",
            }
            st.session_state.sms_log.insert(0, log_entry)
            if ok:
                sms_status_placeholder.success(f"📲 Auto-SMS sent to {ALERT_PHONE_NUMBER}! ({status})")
            else:
                sms_status_placeholder.error(f"📲 Auto-SMS failed: {status}")
else:
    if overall_risk < sms_threshold:
        st.session_state.last_sms_sent_score = None

# =========================================================
# HEADER
# =========================================================
st.title(T["title"])
st.caption(T["subtitle"])

risk_label, risk_color = get_risk_label(overall_risk)

col_a, col_b, col_c = st.columns([2, 1, 1])
with col_a:
    st.markdown(f"### 📍 {selected_zone}")
    st.markdown(
        f"**{T['population']}:** {zone_info['population']:,} &nbsp;&nbsp; "
        f"**{T['last_updated']}:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )
with col_b:
    st.metric(T["overall_risk"], f"{overall_risk:.1f} / 100")
with col_c:
    st.markdown(
        f"""
        <div style="
            background-color:{risk_color}22;
            border:2px solid {risk_color};
            border-radius:12px;
            padding:14px;
            text-align:center;
            font-weight:700;
            font-size:18px;
            color:{risk_color};
        ">
        {risk_label}
        </div>
        """,
        unsafe_allow_html=True,
    )

st.markdown("---")

tab_overview, tab_live, tab_trends, tab_map, tab_safety, tab_insights = st.tabs([
    "🚨 Alerts & SMS",
    "📡 Live Data & Risk",
    "📈 History & Events",
    "🗺️ Zone Map",
    "🛡️ Safety Guide",
    "🔍 Key Insights",
])

with tab_overview:
    # =========================================================
    # ALERTS + SMS PANEL
    # =========================================================
    st.subheader("🚨 " + T["alerts"])

    if not alerted:
        st.success(T["no_alerts"])
    else:
        for disease, score in alerted.items():
            lvl, col = get_risk_label(score)
            st.markdown(
                f"""
                <div style="
                    background-color:{col}15;
                    border-left:6px solid {col};
                    border-radius:6px;
                    padding:10px 16px;
                    margin-bottom:6px;
                ">
                <b>{T['alert_msg']} {translated_disease_names[disease]}</b> — {T['risk_level']}:
                <span style="color:{col}; font-weight:700;">{lvl} ({score:.1f}/100)</span>
                </div>
                """,
                unsafe_allow_html=True,
            )

        with st.expander("📋 " + T["recommendation"], expanded=True):
            for rec in [T["rec_1"], T["rec_2"], T["rec_3"], T["rec_4"], T["rec_5"]]:
                st.markdown(f"- {rec}")

    # ── SMS Send Panel ─────────────────────────────────────────────────────────────
    with st.expander("📱 " + T["sms_settings"], expanded=bool(alerted)):

        sms_preview_body = build_sms_message(
            selected_zone, overall_risk,
            alerted if alerted else {"Overall": overall_risk},
            sensors
        )
        st.markdown(f"**{T['sms_preview']}** → `{ALERT_PHONE_NUMBER}`")
        st.code(sms_preview_body, language=None)

        col_sms1, col_sms2 = st.columns([1, 2])
        with col_sms1:
            send_now = st.button(T["send_sms"], type="primary", use_container_width=True)

        with col_sms2:
            if not twilio_sid or not twilio_token or not twilio_from:
                st.warning("⚠️ Enter Twilio credentials in the sidebar to send SMS.")

        if send_now:
            if True:
                ok, status = send_sms_alert(sms_preview_body, twilio_sid, twilio_token, twilio_from)
                log_entry = {
                    "time": datetime.now().strftime("%H:%M:%S"),
                    "zone": selected_zone,
                    "score": f"{overall_risk:.1f}",
                    "status": "✅ Sent" if ok else f"❌ {status}",
                }
                st.session_state.sms_log.insert(0, log_entry)
                if ok:
                    st.success(f"✅ SMS sent to {ALERT_PHONE_NUMBER}! ({status})")
                else:
                    st.error(f"❌ SMS failed: {status}")
            else:
                st.error("Please fill in all Twilio credentials in the sidebar first.")

        if st.session_state.sms_log:
            st.markdown("**📋 SMS Activity Log**")
            log_df = pd.DataFrame(st.session_state.sms_log)
            st.dataframe(log_df, use_container_width=True, hide_index=True)

    st.markdown("---")


with tab_live:
    # =========================================================
    # LIVE SENSOR READINGS
    # =========================================================
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

    # =========================================================
    # DISEASE RISK PREDICTION
    # =========================================================
    st.subheader("🧬 " + T["risk_prediction"])

    col1, col2 = st.columns([1.2, 1])

    with col1:
        st.markdown(f"#### {T['disease_breakdown']}")
        risk_df = pd.DataFrame({
            "Disease": [translated_disease_names[d] for d in disease_risks.keys()],
            "Risk Score": list(disease_risks.values()),
        })
        risk_df["Color"] = risk_df["Risk Score"].apply(lambda x: get_risk_label(x)[1])

        fig_bar = go.Figure(go.Bar(
            x=risk_df["Risk Score"],
            y=risk_df["Disease"],
            orientation="h",
            marker_color=risk_df["Color"],
            text=[f"{v:.1f}" for v in risk_df["Risk Score"]],
            textposition="outside",
        ))
        fig_bar.update_layout(
            xaxis=dict(range=[0, 100], title="Risk Score (0-100)"),
            height=320,
            margin=dict(l=10, r=10, t=10, b=10),
        )
        st.plotly_chart(fig_bar, use_container_width=True)

    with col2:
        st.markdown(f"#### {T['overall_risk']}")
        fig_gauge = go.Figure(go.Indicator(
            mode="gauge+number",
            value=overall_risk,
            gauge={
                "axis": {"range": [0, 100]},
                "bar": {"color": risk_color},
                "steps": [
                    {"range": [0, 25],  "color": "rgba(46,204,113,0.3)"},
                    {"range": [25, 50], "color": "rgba(241,196,15,0.3)"},
                    {"range": [50, 75], "color": "rgba(230,126,34,0.3)"},
                    {"range": [75, 100],"color": "rgba(231,76,60,0.3)"},
                ],
            },
            number={"suffix": " / 100"},
        ))
        fig_gauge.update_layout(height=320, margin=dict(l=10, r=10, t=30, b=10))
        st.plotly_chart(fig_gauge, use_container_width=True)

    st.markdown("---")


with tab_trends:
    # =========================================================
    # HISTORICAL TRENDS
    # =========================================================
    st.subheader("📈 " + T["trends"])

    real_hist_df = fetch_real_historical_data()

    if real_hist_df is not None and len(real_hist_df) >= 2:
        st.success(f"🟢 Showing REAL logged history from ESP32 ({len(real_hist_df)} readings)")
        hist_df = real_hist_df
    else:
        st.warning(
            "⚠️ No real logged history found at /history yet — showing SIMULATED trend data instead. "
            "Update your ESP32 to POST readings to /history (see notes) to make this live."
        )
        # hist_df already holds the simulated fallback generated earlier

    tab_trend, tab_events = st.tabs(["📊 Trend Chart", "📋 Contamination Events Log"])

    with tab_trend:
        param_options = {
            T["bacteria"]:     "bacteria",
            T["turbidity"]:    "turbidity",
            T["ph_level"]:     "ph",
            T["rainfall"]:     "rainfall",
            T["water_temp"]:   "water_temp_c",
            T["ambient_temp"]: "ambient_temp_c",
            T["overall_risk"]: "overall_risk",
        }

        selected_param_label = st.selectbox(T["param_trend"], options=list(param_options.keys()))
        selected_param = param_options[selected_param_label]

        plot_df = hist_df.copy()
        if selected_param in ["water_temp_c", "ambient_temp_c"] and st.session_state.temp_unit.startswith("Fahrenheit"):
            plot_df[selected_param] = c_to_f(plot_df[selected_param])
            y_title = selected_param_label.replace("°C", "°F")
        else:
            y_title = selected_param_label

        fig_line = px.line(
            plot_df, x="datetime", y=selected_param,
            labels={"datetime": "", selected_param: y_title},
        )
        fig_line.update_traces(line_color="#3498db")
        fig_line.update_layout(height=350, margin=dict(l=10, r=10, t=10, b=10))

        if selected_param == "overall_risk":
            fig_line.add_hline(y=50, line_dash="dash", line_color="orange", annotation_text=T["high_risk"])
            fig_line.add_hline(y=75, line_dash="dash", line_color="red", annotation_text=T["critical_risk"])

        st.plotly_chart(fig_line, use_container_width=True)

    with tab_events:
        st.markdown(
            "This log counts **distinct contamination events** — each time the risk score "
            "crossed *into* a High or Critical level — rather than every single elevated reading, "
            "so a single multi-hour spike counts once, not dozens of times."
        )

        high_events = count_contamination_events(hist_df, "overall_risk", threshold=50)
        critical_events = count_contamination_events(hist_df, "overall_risk", threshold=75)
        span_days = max((hist_df["datetime"].max() - hist_df["datetime"].min()).days, 1) if len(hist_df) >= 2 else 1
        peak_risk = float(hist_df["overall_risk"].max()) if len(hist_df) else 0.0

        ec1, ec2, ec3, ec4 = st.columns(4)
        ec1.metric("⚠️ High-Risk Events", high_events)
        ec2.metric("🔴 Critical-Risk Events", critical_events)
        ec3.metric("📈 Peak Risk Recorded", f"{peak_risk:.1f} / 100")
        ec4.metric("🗓️ Period Covered", f"{span_days} day(s)")

        st.caption(
            f"Data source: {'real ESP32 logged history' if (real_hist_df is not None and len(real_hist_df) >= 2) else 'simulated demo data'} "
            f"— {len(hist_df)} readings analyzed."
        )

    st.markdown("---")


with tab_map:
    # =========================================================
    # ZONE RISK MAP
    # =========================================================
    st.subheader("🗺️ " + T["map_view"])

    map_rows = []
    for zname, zinfo in ZONES_DATA.items():
        zsensors, z_is_live, _ = get_sensor_data(zname, zinfo["firebase_key"], st.session_state.seed_offset)
        zrisks = compute_disease_risks(zsensors)
        zoverall = float(np.mean(list(zrisks.values())))
        lvl, col = get_risk_label(zoverall)
        map_rows.append({
            "Zone": zname.split(" - ")[1] if " - " in zname else zname,
            "Full Zone": zname,
            "lat": zinfo["lat"],
            "lon": zinfo["lon"],
            "Risk Score": zoverall,
            "Risk Level": lvl,
            "Population": zinfo["population"],
            "Live": "🟢" if z_is_live else "⚪",
        })

    map_df = pd.DataFrame(map_rows)

    fig_map = px.scatter_mapbox(
        map_df, lat="lat", lon="lon",
        size="Risk Score", color="Risk Score",
        color_continuous_scale=["#2ecc71", "#f1c40f", "#e67e22", "#e74c3c"],
        range_color=[0, 100],
        size_max=35,
        zoom=11,
        hover_name="Zone",
        hover_data={"lat": False, "lon": False, "Risk Score": ":.1f", "Population": True, "Risk Level": True, "Live": True},
    )
    fig_map.update_layout(mapbox_style="open-street-map", margin=dict(l=0, r=0, t=0, b=0), height=420)
    st.plotly_chart(fig_map, use_container_width=True)

    st.dataframe(
        map_df[["Zone", "Population", "Risk Score", "Risk Level", "Live"]].rename(columns={
            "Zone": T["zone"],
            "Population": T["population"],
            "Risk Score": T["overall_risk"],
            "Risk Level": T["risk_level"],
            "Live": "Live ESP32?",
        }),
        use_container_width=True,
        hide_index=True,
    )

    st.markdown("#### 🔍 Zone Deep-Dive: Live + Past Contamination History")
    detail_zone = st.selectbox(
        "Select an area to view its live reading and contamination history",
        options=list(ZONES_DATA.keys()),
        index=list(ZONES_DATA.keys()).index(selected_zone),
        key="map_detail_zone",
    )
    detail_info = ZONES_DATA[detail_zone]
    detail_sensors, detail_is_live, detail_err = get_sensor_data(
        detail_zone, detail_info["firebase_key"], st.session_state.seed_offset
    )
    detail_risks = compute_disease_risks(detail_sensors)
    detail_overall = float(np.mean(list(detail_risks.values())))
    detail_lvl, detail_col = get_risk_label(detail_overall)
    detail_summary = summarize_zone_history(
        detail_zone, detail_info["firebase_key"],
        real_hist_df if real_hist_df is not None and len(real_hist_df) >= 2 else None,
    )

    with st.container():
        dd1, dd2 = st.columns([1, 1])

        with dd1:
            st.markdown(f"**📍 {detail_zone} — Right Now**")
            if detail_is_live:
                st.success("🟢 Live ESP32 reading")
            else:
                st.warning("⚪ Simulated reading (no live ESP32 data for this path yet)")
            st.metric("Current Risk Level", f"{detail_overall:.1f} / 100", delta=detail_lvl)
            dd1a, dd1b, dd1c = st.columns(3)
            dd1a.metric("TDS", f"{detail_sensors['tds']:.0f}")
            dd1b.metric("Turbidity", f"{detail_sensors['turbidity']:.1f}")
            dd1c.metric("Water Temp", format_temp(detail_sensors['water_temp_c']))

        with dd2:
            st.markdown(f"**🕓 {detail_zone} — Past {detail_summary['span_days']} Day(s)**")
            st.caption(
                "🟢 Based on real logged ESP32 history" if detail_summary["is_real"]
                else "⚪ Based on simulated demo history (connect ESP32 history logging for real data)"
            )
            de1, de2, de3 = st.columns(3)
            de1.metric("Contaminated (High Risk)", f"{detail_summary['high_events']}x")
            de2.metric("Critical Events", f"{detail_summary['critical_events']}x")
            de3.metric("Peak Risk", f"{detail_summary['peak_risk']:.1f}/100")

            if detail_summary["high_events"] == 0:
                st.info("✅ No high-risk contamination events recorded in this period.")
            elif detail_summary["critical_events"] > 0:
                st.error(
                    f"🚨 This zone reached CRITICAL contamination levels {detail_summary['critical_events']} time(s) "
                    f"in the last {detail_summary['span_days']} day(s). Continued monitoring and precautions advised."
                )
            else:
                st.warning(
                    f"⚠️ This zone crossed into High Risk {detail_summary['high_events']} time(s) "
                    f"in the last {detail_summary['span_days']} day(s)."
                )

    st.markdown("---")


with tab_safety:
    # =========================================================
    # SAFETY & PRECAUTIONS
    # =========================================================
    st.subheader("🛡️ Safety & Precautions Guide")
    st.caption(
        "General public-health guidance — not a substitute for medical advice. "
        "If you or someone nearby is seriously unwell, contact a healthcare provider immediately."
    )

    safety_tab_general, safety_tab_disease = st.tabs(["✅ General Precautions", "🧬 Disease-Specific Guidance"])

    with safety_tab_general:
        st.markdown(f"#### Recommended precautions right now for **{selected_zone}**")
        if overall_risk >= 75:
            st.error("🚨 **Critical risk zone** — treat ALL local water sources as unsafe until levels normalize.")
        elif overall_risk >= 50:
            st.warning("⚠️ **High risk zone** — boil or treat water before any use; avoid direct contact with untreated sources.")
        elif overall_risk >= 25:
            st.info("ℹ️ **Moderate risk zone** — basic precautions recommended; monitor for updates.")
        else:
            st.success("✅ **Low risk zone** — conditions currently normal; standard hygiene practices still apply.")

        for tip in GENERAL_PRECAUTIONS:
            st.markdown(f"- {tip}")

    with safety_tab_disease:
        st.markdown("Symptoms, prevention, and when to seek medical help for each monitored disease:")
        disease_tab_objs = st.tabs([f"{DISEASE_SAFETY_INFO[d]['icon']} {translated_disease_names[d]}" for d in disease_risks.keys()])

        for tab_obj, disease_key in zip(disease_tab_objs, disease_risks.keys()):
            info = DISEASE_SAFETY_INFO[disease_key]
            score = disease_risks[disease_key]
            lvl, col = get_risk_label(score)
            with tab_obj:
                st.markdown(
                    f"**Current risk in {selected_zone}:** "
                    f"<span style='color:{col}; font-weight:700;'>{lvl} ({score:.1f}/100)</span>",
                    unsafe_allow_html=True,
                )
                st.markdown(f"**🤒 Symptoms:** {info['symptoms']}")
                st.markdown(f"**🛡️ Prevention:** {info['prevention']}")
                st.markdown(f"**🏥 When to seek help:** {info['seek_help']}")

    st.markdown("---")


with tab_insights:
    # =========================================================
    # KEY INSIGHTS / SUMMARY
    # =========================================================
    st.subheader("🔍 " + T["key_insights"])

    insight_cols = st.columns(3)
    if len(hist_df) >= 48:
        recent_risk_change = hist_df["overall_risk"].iloc[-24:].mean() - hist_df["overall_risk"].iloc[-48:-24].mean()
    elif len(hist_df) >= 4:
        half = len(hist_df) // 2
        recent_risk_change = hist_df["overall_risk"].iloc[half:].mean() - hist_df["overall_risk"].iloc[:half].mean()
    else:
        recent_risk_change = 0.0
    trend_icon = "📈" if recent_risk_change > 0 else "📉"

    with insight_cols[0]:
        st.info(f"{trend_icon} **{T['overall_risk']}**: {T['insight_1']} ({recent_risk_change:+.1f} pts)")

    with insight_cols[1]:
        if sensors["bacteria"] < 200:
            st.success(f"🦠 {T['insight_2']}")
        else:
            st.warning(f"🦠 **{T['bacteria']}**: {sensors['bacteria']:.0f} CFU/mL")

    with insight_cols[2]:
        if sensors["rainfall"] > 10:
            st.warning(f"🌧️ {T['insight_3']}")
        else:
            st.info(f"🌧️ {T['rainfall']}: {sensors['rainfall']:.1f} mm")

    st.markdown("---")
    st.caption(T["footer"])


# =========================================================
# AUTO REFRESH
# =========================================================
if auto_refresh:
    time.sleep(10)
    st.session_state.seed_offset += 1
    st.rerun()
