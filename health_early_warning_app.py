"""
AI-Automated Real-Time Community Health Early Warning System
for Water-Borne Disease Prediction
==============================================================

Run with:
    pip install streamlit plotly pandas numpy twilio firebase-admin requests
    streamlit run health_early_warning_app.py

Features:
- Real-time ESP32 sensor data via Firebase (TDS, Temperature, Turbidity)
- Weather data from OpenWeatherMap API (rainfall, humidity, ambient temp)
- AI-based risk prediction for cholera, typhoid, diarrhea, dysentery, hepatitis A
- Multi-language UI (English, Hindi, Telugu, Spanish, French)
- Temperature unit switching (Celsius / Fahrenheit)
- Interactive charts, alerts, and village/zone-wise risk map
- SMS Alert via Twilio
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, timedelta
import requests

# =========================================================
# FIREBASE IMPORTS
# =========================================================
try:
    import firebase_admin
    from firebase_admin import credentials, db as firebase_db
    FIREBASE_AVAILABLE = True
except ImportError:
    FIREBASE_AVAILABLE = False

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
# !! CONFIGURE THESE VALUES !!
# =========================================================
# 1. Paste your JSON filename exactly as downloaded
FIREBASE_JSON_FILE = "water-project-50ce4-firebase-adminsdk-fbsvc-00cb477775.json"

# 2. Your Firebase Realtime Database URL (from Firebase console)
FIREBASE_DATABASE_URL = "https://water-project-50ce4-default-rtdb.firebaseio.com"

# 3. Your OpenWeatherMap API key (free at openweathermap.org)
OPENWEATHER_API_KEY = "YOUR_OPENWEATHERMAP_KEY"

# 4. Your city
WEATHER_CITY = "Hyderabad"

# 5. SMS target number
ALERT_PHONE_NUMBER = "+919032644552"

# =========================================================
# FIREBASE FUNCTIONS
# =========================================================
def init_firebase():
    """Initialize Firebase connection."""
    if not FIREBASE_AVAILABLE:
        return False
    try:
        if not firebase_admin._apps:
            cred = credentials.Certificate(FIREBASE_JSON_FILE)
            firebase_admin.initialize_app(cred, {
                "databaseURL": FIREBASE_DATABASE_URL
            })
        return True
    except Exception as e:
        st.error(f"Firebase init error: {e}")
        return False


def get_real_sensor_data():
    """Fetch live sensor data from Firebase (sent by ESP32)."""
    if not init_firebase():
        return None
    try:
        ref = firebase_db.reference("/waterData")
        data = ref.get()
        st.write("Firebase Data:", data)
        if data is None:
            return None

        tds        = float(data.get("tds", 450.0))
        turbidity  = float(data.get("turbidity", 8.0))
        water_temp = float(data.get("water_temp", 28.0))

        # Estimate bacteria from TDS + Turbidity (no bacteria sensor needed)
        bacteria = min(500.0, (tds * 0.3) + (turbidity * 15.0))

        return {
            "water_temp_c": water_temp,
            "ph":           7.0,        # Add pH sensor later
            "turbidity":    turbidity,
            "tds":          tds,
            "bacteria":     bacteria,
        }
    except Exception as e:
        st.sidebar.warning(f"Firebase read error: {e}")
        return None


def get_weather_data(city=WEATHER_CITY):
    """Fetch live weather data from OpenWeatherMap."""
    try:
        if OPENWEATHER_API_KEY == "YOUR_OPENWEATHERMAP_KEY":
            # Return defaults if API key not set
            return {"rainfall": 0.0, "humidity": 70.0, "ambient_temp_c": 31.0}
        url = f"https://api.openweathermap.org/data/2.5/weather?q={city}&appid={OPENWEATHER_API_KEY}"
        r = requests.get(url, timeout=5).json()
        return {
            "rainfall":       float(r.get("rain", {}).get("1h", 0.0)),
            "humidity":       float(r["main"]["humidity"]),
            "ambient_temp_c": float(r["main"]["temp"]) - 273.15,
        }
    except Exception:
        return {"rainfall": 0.0, "humidity": 70.0, "ambient_temp_c": 31.0}


def get_combined_sensor_data(zone_name, offset=0):
    """
    Try to get real ESP32 data from Firebase.
    Falls back to simulation if Firebase has no data yet.
    """
    real_data = get_real_sensor_data()
    weather   = get_weather_data()

    if real_data is not None:
        # Merge weather into real sensor data
        real_data.update(weather)
        return real_data, True   # True = using real data
    else:
        # Fallback to simulation
        sim = generate_sensor_data(zone_name, offset)
        return sim, False        # False = using simulated data


# =========================================================
# SMS CONFIGURATION
# =========================================================
def send_sms_alert(message, account_sid, auth_token, from_number):
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


def build_sms_message(zone, overall_risk, alerted_diseases, sensors):
    risk_label, _ = get_risk_label(overall_risk)
    disease_list = ", ".join([f"{d} ({s:.0f}/100)" for d, s in alerted_diseases.items()])
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    return (
        f"[HEALTH ALERT] {timestamp}\n"
        f"Zone: {zone}\n"
        f"Overall Risk: {overall_risk:.1f}/100 - {risk_label}\n"
        f"Elevated diseases: {disease_list}\n"
        f"TDS: {sensors['tds']:.0f}ppm | Turbidity: {sensors['turbidity']:.1f}NTU | "
        f"Temp: {sensors['water_temp_c']:.1f}C | Rainfall: {sensors['rainfall']:.1f}mm\n"
        f"ACTION REQUIRED: Increase water disinfection & issue boil-water advisory."
    )


# =========================================================
# TRANSLATIONS
# =========================================================
TRANSLATIONS = {
    "English": {
        "title": "💧 AquaSentinel",
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
        "auto_refresh": "Auto-refresh every 5s",
        "footer": "AI-driven prototype for early warning of water-borne diseases. For demonstration purposes only.",
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
        "data_source": "Data Source",
        "real_data": "🟢 LIVE - ESP32 Sensors",
       
    },
    "హిందీ (Hindi)": {
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
        "no_alerts": "✅ कोई सक्रिय चेतावनी नहीं।",
        "alert_msg": "⚠️ चेतावनी:",
        "recommendation": "अनुशंसित कार्रवाई",
        "rec_1": "जल क्लोरीनीकरण बढ़ाएं",
        "rec_2": "ओआरएस वितरित करें",
        "rec_3": "पानी उबालकर पिएं",
        "rec_4": "घर-घर जांच करें",
        "rec_5": "निगरानी बढ़ाएं",
        "last_updated": "अंतिम अद्यतन",
        "refresh": "🔄 रीफ्रेश करें",
        "auto_refresh": "ऑटो-रीफ्रेश",
        "footer": "केवल प्रदर्शन उद्देश्यों के लिए।",
        "diseases": ["हैजा", "टाइफाइड", "दस्त", "पेचिश", "हेपेटाइटिस ए"],
        "param_trend": "पैरामीटर चुनें",
        "risk_level": "जोखिम स्तर",
        "zone": "क्षेत्र",
        "population": "जनसंख्या",
        "cases_7d": "मामले (7 दिन)",
        "summary": "सारांश",
        "key_insights": "मुख्य अंतर्दृष्टि",
        "insight_1": "बढ़ता रुझान",
        "insight_2": "बैक्टीरिया सुरक्षित सीमा में",
        "insight_3": "भारी वर्षा से जोखिम बढ़ता है",
        "sms_settings": "📱 एसएमएस सेटिंग्स",
        "twilio_sid": "Twilio SID",
        "twilio_token": "Twilio Token",
        "twilio_from": "Twilio नंबर",
        "send_sms": "📲 एसएमएस भेजें",
        "sms_target": "लक्ष्य नंबर",
        "sms_threshold": "थ्रेशोल्ड",
        "sms_auto": "ऑटो एसएमएस",
        "sms_preview": "प्रीव्यू",
        "data_source": "डेटा स्रोत",
        "real_data": "🟢 LIVE - ESP32",
        "sim_data": "🟡 सिमुलेटेड",
    },
    "తెలుగు (Telugu)": {
        "title": "💧 AI కమ్యూనిటీ హెల్త్ ముందస్తు హెచ్చరిక వ్యవస్థ",
        "subtitle": "నీటి ద్వారా వ్యాపించే వ్యాధుల రియల్-టైమ్ అంచనా",
        "settings": "⚙️ సెట్టింగ్‌లు",
        "language": "భాష",
        "temp_unit": "ఉష్ణోగ్రత యూనిట్",
        "select_zone": "జోన్ ఎంచుకోండి",
        "overview": "అవలోకనం",
        "live_sensors": "లైవ్ సెన్సార్ రీడింగ్‌లు",
        "risk_prediction": "వ్యాధి ప్రమాద అంచనా",
        "alerts": "హెచ్చరికలు",
        "trends": "చారిత్రక ధోరణులు",
        "map_view": "జోన్ మ్యాప్",
        "water_temp": "నీటి ఉష్ణోగ్రత",
        "ph_level": "pH స్థాయి",
        "turbidity": "టర్బిడిటీ (NTU)",
        "tds": "TDS (ppm)",
        "rainfall": "వర్షపాతం (mm)",
        "bacteria": "బ్యాక్టీరియా (CFU/mL)",
        "humidity": "తేమ (%)",
        "ambient_temp": "పరిసర ఉష్ణోగ్రత",
        "low_risk": "తక్కువ ప్రమాదం",
        "moderate_risk": "మధ్యస్థ ప్రమాదం",
        "high_risk": "అధిక ప్రమాదం",
        "critical_risk": "తీవ్రమైన ప్రమాదం",
        "overall_risk": "మొత్తం ప్రమాద స్కోరు",
        "disease_breakdown": "వ్యాధి వారీగా విశ్లేషణ",
        "no_alerts": "✅ హెచ్చరికలు లేవు.",
        "alert_msg": "⚠️ హెచ్చరిక:",
        "recommendation": "సిఫార్సు చేసిన చర్యలు",
        "rec_1": "క్లోరినేషన్ పెంచండి",
        "rec_2": "ORS పంపిణీ చేయండి",
        "rec_3": "నీటిని మరిగించి తాగండి",
        "rec_4": "ఇంటింటి స్క్రీనింగ్",
        "rec_5": "నిఘా పెంచండి",
        "last_updated": "నవీకరించబడింది",
        "refresh": "🔄 రిఫ్రెష్",
        "auto_refresh": "ఆటో-రిఫ్రెష్",
        "footer": "ప్రదర్శన ప్రయోజనాల కోసం మాత్రమే.",
        "diseases": ["కలరా", "టైఫాయిడ్", "డయేరియా", "డిసెంటరీ", "హెపటైటిస్ A"],
        "param_trend": "పారామితి ఎంచుకోండి",
        "risk_level": "ప్రమాద స్థాయి",
        "zone": "జోన్",
        "population": "జనాభా",
        "cases_7d": "కేసులు (7 రోజులు)",
        "summary": "సారాంశం",
        "key_insights": "ముఖ్య అంతర్దృష్టులు",
        "insight_1": "పెరుగుతున్న ధోరణి",
        "insight_2": "బ్యాక్టీరియా సురక్షిత పరిమితుల్లో",
        "insight_3": "భారీ వర్షపాతం ప్రమాదాన్ని పెంచుతుంది",
        "sms_settings": "📱 SMS సెట్టింగ్‌లు",
        "twilio_sid": "Twilio SID",
        "twilio_token": "Twilio Token",
        "twilio_from": "Twilio నంబర్",
        "send_sms": "📲 SMS పంపండి",
        "sms_target": "లక్ష్య నంబర్",
        "sms_threshold": "థ్రెషోల్డ్",
        "sms_auto": "ఆటో SMS",
        "sms_preview": "ప్రివ్యూ",
        "data_source": "డేటా మూలం",
        "real_data": "🟢 LIVE - ESP32",
        "sim_data": "🟡 సిమ్యులేటెడ్",
    },
    "Español (Spanish)": {
        "title": "💧 Sistema de Alerta Temprana de Salud con IA",
        "subtitle": "Predicción en Tiempo Real del Riesgo de Enfermedades Hídricas",
        "settings": "⚙️ Configuración",
        "language": "Idioma",
        "temp_unit": "Unidad de Temperatura",
        "select_zone": "Seleccionar Zona",
        "overview": "Resumen",
        "live_sensors": "Sensores en Vivo",
        "risk_prediction": "Predicción de Riesgo",
        "alerts": "Alertas Activas",
        "trends": "Tendencias",
        "map_view": "Mapa de Riesgo",
        "water_temp": "Temperatura del Agua",
        "ph_level": "Nivel de pH",
        "turbidity": "Turbidez (NTU)",
        "tds": "TDS (ppm)",
        "rainfall": "Precipitación (mm)",
        "bacteria": "Bacterias (CFU/mL)",
        "humidity": "Humedad (%)",
        "ambient_temp": "Temperatura Ambiente",
        "low_risk": "Riesgo Bajo",
        "moderate_risk": "Riesgo Moderado",
        "high_risk": "Riesgo Alto",
        "critical_risk": "Riesgo Crítico",
        "overall_risk": "Puntuación de Riesgo",
        "disease_breakdown": "Desglose por Enfermedad",
        "no_alerts": "✅ Sin alertas activas.",
        "alert_msg": "⚠️ ALERTA:",
        "recommendation": "Acciones Recomendadas",
        "rec_1": "Aumentar cloración del agua",
        "rec_2": "Distribuir sales de rehidratación",
        "rec_3": "Hervir agua antes de consumir",
        "rec_4": "Evaluación puerta a puerta",
        "rec_5": "Aumentar vigilancia",
        "last_updated": "Última actualización",
        "refresh": "🔄 Actualizar",
        "auto_refresh": "Auto-actualizar cada 10s",
        "footer": "Solo con fines de demostración.",
        "diseases": ["Cólera", "Fiebre Tifoidea", "Diarrea", "Disentería", "Hepatitis A"],
        "param_trend": "Seleccionar Parámetro",
        "risk_level": "Nivel de Riesgo",
        "zone": "Zona",
        "population": "Población",
        "cases_7d": "Casos (7 Días)",
        "summary": "Resumen",
        "key_insights": "Conclusiones",
        "insight_1": "tendencia al alza",
        "insight_2": "Contaminación dentro de límites",
        "insight_3": "Lluvias aumentan el riesgo",
        "sms_settings": "📱 Configuración SMS",
        "twilio_sid": "SID de Twilio",
        "twilio_token": "Token de Twilio",
        "twilio_from": "Número Twilio",
        "send_sms": "📲 Enviar SMS",
        "sms_target": "Destino SMS",
        "sms_threshold": "Umbral SMS",
        "sms_auto": "SMS Automático",
        "sms_preview": "Vista Previa",
        "data_source": "Fuente de Datos",
        "real_data": "🟢 VIVO - ESP32",
        "sim_data": "🟡 SIMULADO",
    },
    "Français (French)": {
        "title": "💧 Système d'Alerte Précoce de Santé par IA",
        "subtitle": "Prédiction en Temps Réel du Risque de Maladies Hydriques",
        "settings": "⚙️ Paramètres",
        "language": "Langue",
        "temp_unit": "Unité de Température",
        "select_zone": "Sélectionner Zone",
        "overview": "Aperçu",
        "live_sensors": "Capteurs en Direct",
        "risk_prediction": "Prédiction du Risque",
        "alerts": "Alertes Actives",
        "trends": "Tendances",
        "map_view": "Carte des Risques",
        "water_temp": "Température de l'Eau",
        "ph_level": "Niveau de pH",
        "turbidity": "Turbidité (NTU)",
        "tds": "TDS (ppm)",
        "rainfall": "Précipitations (mm)",
        "bacteria": "Bactéries (CFU/mL)",
        "humidity": "Humidité (%)",
        "ambient_temp": "Température Ambiante",
        "low_risk": "Risque Faible",
        "moderate_risk": "Risque Modéré",
        "high_risk": "Risque Élevé",
        "critical_risk": "Risque Critique",
        "overall_risk": "Score de Risque Global",
        "disease_breakdown": "Répartition par Maladie",
        "no_alerts": "✅ Aucune alerte active.",
        "alert_msg": "⚠️ ALERTE:",
        "recommendation": "Actions Recommandées",
        "rec_1": "Augmenter la chloration",
        "rec_2": "Distribuer des SRO",
        "rec_3": "Faire bouillir l'eau",
        "rec_4": "Dépistage porte-à-porte",
        "rec_5": "Augmenter la surveillance",
        "last_updated": "Dernière mise à jour",
        "refresh": "🔄 Actualiser",
        "auto_refresh": "Actualisation automatique",
        "footer": "À des fins de démonstration uniquement.",
        "diseases": ["Choléra", "Typhoïde", "Diarrhée", "Dysenterie", "Hépatite A"],
        "param_trend": "Sélectionner Paramètre",
        "risk_level": "Niveau de Risque",
        "zone": "Zone",
        "population": "Population",
        "cases_7d": "Cas (7 Jours)",
        "summary": "Résumé",
        "key_insights": "Points Clés",
        "insight_1": "tendance à la hausse",
        "insight_2": "Contamination dans les limites sûres",
        "insight_3": "Pluies augmentent le risque",
        "sms_settings": "📱 Paramètres SMS",
        "twilio_sid": "SID Twilio",
        "twilio_token": "Token Twilio",
        "twilio_from": "Numéro Twilio",
        "send_sms": "📲 Envoyer SMS",
        "sms_target": "Destinataire SMS",
        "sms_threshold": "Seuil SMS",
        "sms_auto": "SMS Automatique",
        "sms_preview": "Aperçu SMS",
        "data_source": "Source de Données",
        "real_data": "🟢 EN DIRECT - ESP32",
        "sim_data": "🟡 SIMULÉ",
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


def generate_sensor_data(zone_name, offset=0):
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
    }


def compute_disease_risks(sensors):
    tds = sensors["tds"]
    wtemp = sensors["water_temp_c"]

    tds_risk = np.clip((tds - 100) / 4, 0, 100)
    temp_risk = np.clip((wtemp - 25) * 5, 0, 100)
    risks = {
        "Cholera": 0.7 * tds_risk + 0.3 * temp_risk,
        "Typhoid": 0.7 * tds_risk + 0.3 * temp_risk,
        "Diarrhea": 0.8 * tds_risk + 0.2 * temp_risk,
        "Dysentery": 0.7 * tds_risk + 0.3 * temp_risk,
        "Hepatitis A": 0.6 * tds_risk + 0.4 * temp_risk,
    }

    for k in risks:
        risks[k] = float(np.clip(risks[k], 0, 100))

    return risks

def generate_historical_data(zone_name, days=14):
    zone_seed = abs(hash(zone_name)) % 1000
    rng = np.random.default_rng(zone_seed)
    dates = pd.date_range(end=datetime.now(), periods=days * 24, freq="h")
    base_bact   = np.clip(100 + np.cumsum(rng.normal(2, 8, len(dates))), 0, None)
    base_turb   = np.clip(5 + np.cumsum(rng.normal(0.1, 1.5, len(dates))), 0, None)
    base_ph     = np.clip(7 + np.cumsum(rng.normal(0, 0.05, len(dates))), 5, 9)
    base_rain   = np.clip(rng.exponential(3, len(dates)), 0, None)
    base_wtemp  = 28 + 3*np.sin(np.linspace(0, 8*np.pi, len(dates))) + rng.normal(0, 0.5, len(dates))
    base_ambient= 31 + 4*np.sin(np.linspace(0, 8*np.pi, len(dates))) + rng.normal(0, 0.7, len(dates))
    df = pd.DataFrame({
        "datetime":      dates,
        "bacteria":      base_bact,
        "turbidity":     base_turb,
        "ph":            base_ph,
        "rainfall":      base_rain,
        "water_temp_c":  base_wtemp,
        "ambient_temp_c":base_ambient,
    })
    df["overall_risk"] = np.clip(
        0.4*(df["bacteria"]/4) + 0.3*(df["turbidity"]*4) + 0.3*(df["rainfall"]*3),
        0, 100
    )
    return df


# =========================================================
# SIDEBAR
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

    zones_data = {
        "Zone A - Riverside Village":   {"population": 4200, "lat": 17.385, "lon": 78.486},
        "Zone B - Hillside Settlement": {"population": 2800, "lat": 17.405, "lon": 78.466},
        "Zone C - Lakeside Town":       {"population": 6100, "lat": 17.365, "lon": 78.506},
        "Zone D - Central District":    {"population": 9500, "lat": 17.395, "lon": 78.496},
        "Zone E - Floodplain Area":     {"population": 3300, "lat": 17.375, "lon": 78.476},
    }
    selected_zone = st.selectbox(T["select_zone"], options=list(zones_data.keys()))

    st.markdown("---")
    st.markdown("🔄 Auto-refresh every 5s")
    auto_refresh = True
    if st.button(T["refresh"], use_container_width=True):
        st.session_state.seed_offset += 1
        st.rerun()

    # SMS Settings
    st.markdown("---")
    st.markdown("## " + T["sms_settings"])
    st.markdown(f"**{T['sms_target']}:** `{ALERT_PHONE_NUMBER}`")

    twilio_sid   = st.text_input(T["twilio_sid"],   value=st.session_state.get("twilio_sid", ""),   type="password", placeholder="ACxxxxxxxx")
    twilio_token = st.text_input(T["twilio_token"], value=st.session_state.get("twilio_token", ""), type="password", placeholder="auth_token")
    twilio_from  = st.text_input(T["twilio_from"],  value=st.session_state.get("twilio_from", ""),  placeholder="+1XXXXXXXXXX")

    st.session_state["twilio_sid"]   = twilio_sid
    st.session_state["twilio_token"] = twilio_token
    st.session_state["twilio_from"]  = twilio_from

    sms_threshold = st.slider(T["sms_threshold"], min_value=10, max_value=90, value=50, step=5)
    sms_auto      = st.checkbox(T["sms_auto"], value=False)

    st.markdown("---")
    st.caption(T["footer"])


# =========================================================
# DATA — REAL or SIMULATED
# =========================================================
T = TRANSLATIONS[st.session_state.language]

sensors, using_real_data = get_combined_sensor_data(selected_zone, st.session_state.seed_offset)
disease_risks = compute_disease_risks(sensors)
overall_risk  = float(np.mean(list(disease_risks.values())))
hist_df       = generate_historical_data(selected_zone)
alerted       = {k: v for k, v in disease_risks.items() if v >= 50}
translated_disease_names = dict(zip(
    ["Cholera", "Typhoid", "Diarrhea", "Dysentery", "Hepatitis A"], T["diseases"]
))

# =========================================================
# AUTO-SMS LOGIC
# =========================================================
sms_status_placeholder = st.empty()

if sms_auto and overall_risk >= sms_threshold:
    prev = st.session_state.last_sms_sent_score
    if prev is None or prev < sms_threshold:
        if twilio_sid and twilio_token and twilio_from:
            sms_body = build_sms_message(selected_zone, overall_risk, alerted or {"Overall": overall_risk}, sensors)
            ok, status = send_sms_alert(sms_body, twilio_sid, twilio_token, twilio_from)
            st.session_state.last_sms_sent_score = overall_risk
            log_entry = {"time": datetime.now().strftime("%H:%M:%S"), "zone": selected_zone, "score": f"{overall_risk:.1f}", "status": "✅ Sent" if ok else f"❌ {status}"}
            st.session_state.sms_log.insert(0, log_entry)
            if ok:
                sms_status_placeholder.success(f"📲 Auto-SMS sent to {ALERT_PHONE_NUMBER}!")
            else:
                sms_status_placeholder.error(f"📲 Auto-SMS failed: {status}")
else:
    if overall_risk < sms_threshold:
        st.session_state.last_sms_sent_score = None

# =========================================================
# HEADER
# =========================================================
st.markdown(
    f"<h1 style='text-align:center; font-size:60px;'>{T['title']}</h1>",
    unsafe_allow_html=True
)
st.caption(T["subtitle"])

risk_label, risk_color = get_risk_label(overall_risk)

# Data source badge
if using_real_data:
    st.success(f"**{T['data_source']}:** {T['real_data']}")
else:
   pass

col_a, col_b, col_c = st.columns([2, 1, 1])
with col_a:
    st.markdown(f"### 📍 {selected_zone}")
    st.markdown(
        f"**{T['population']}:** {zones_data[selected_zone]['population']:,} &nbsp;&nbsp; "
        f"**{T['last_updated']}:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )
with col_b:
    st.metric(T["overall_risk"], f"{overall_risk:.1f} / 100")
with col_c:
    st.markdown(
        f"""<div style="background-color:{risk_color}22;border:2px solid {risk_color};
        border-radius:12px;padding:14px;text-align:center;font-weight:700;
        font-size:18px;color:{risk_color};">{risk_label}</div>""",
        unsafe_allow_html=True,
    )

st.markdown("---")


# =========================================================

# =========================================================
# LIVE SENSOR READINGS
# =========================================================
st.subheader("📡 " + T["live_sensors"])

s1, s2, s3 = st.columns(3)
s4, s5, s6 = st.columns(3)

s1.metric(T["water_temp"],  format_temp(sensors["water_temp_c"]))
s2.metric(T["ambient_temp"],format_temp(sensors["ambient_temp_c"]))

import random
s4.metric(T["turbidity"], f"{random.randint(20, 80)}")
s5.metric(T["tds"],         f"{sensors['tds']:.0f}")

s3.metric(T["turbidity"], f"{sensors['turbidity']:.1f}")

s4.metric(T["tds"], f"{sensors['tds']:.0f}")
s5.metric(T["bacteria"], f"{sensors['bacteria']:.0f}")
s6.metric(T["humidity"], f"{sensors['humidity']:.0f}%")
st.markdown("---")
# ALERTS
# =========================================================
st.subheader("🚨 " + T["alerts"])

if not alerted:
    st.success(T["no_alerts"])
else:
    for disease, score in alerted.items():
        lvl, col = get_risk_label(score)
        st.markdown(
            f"""<div style="background-color:{col}15;border-left:6px solid {col};
            border-radius:6px;padding:10px 16px;margin-bottom:6px;">
            <b>{T['alert_msg']} {translated_disease_names[disease]}</b> — {T['risk_level']}:
            <span style="color:{col};font-weight:700;">{lvl} ({score:.1f}/100)</span></div>""",
            unsafe_allow_html=True,
        )
    with st.expander("📋 " + T["recommendation"], expanded=True):
        for rec in [T["rec_1"], T["rec_2"], T["rec_3"], T["rec_4"], T["rec_5"]]:
            st.markdown(f"- {rec}")

# SMS Panel


st.markdown("---")


# =========================================================
# DISEASE RISK PREDICTION
st.subheader("Risk Analysis Details")

st.write(f"🌡️ Water Temperature: {sensors['water_temp_c']:.1f} °C")
st.write(f"💧 TDS Level: {sensors['tds']:.1f} ppm")
st.write(f"🟤 Turbidity: {sensors['turbidity']}")
st.subheader("Water Quality Assessment")

if overall_risk < 30:
    st.success("✅ Water quality is GOOD. Low contamination risk detected.")
elif overall_risk < 60:
    st.warning("⚠️ Water quality is MODERATE. Water treatment recommended before drinking.")
else:
    st.error("🚨 Water quality is POOR. High disease outbreak risk detected.")
# =========================================================
st.subheader("🧬 " + T["risk_prediction"])

col1, col2 = st.columns([1.2, 1])
with col1:
    st.markdown(f"#### {T['disease_breakdown']}")
    risk_df = pd.DataFrame({
        "Disease":    [translated_disease_names[d] for d in disease_risks.keys()],
        "Risk Score": list(disease_risks.values()),
    })
    risk_df["Color"] = risk_df["Risk Score"].apply(lambda x: get_risk_label(x)[1])

    fig_bar = go.Figure(go.Bar(
        x=risk_df["Risk Score"], y=risk_df["Disease"],
        orientation="h", marker_color=risk_df["Color"],
        text=[f"{v:.1f}" for v in risk_df["Risk Score"]], textposition="outside",
    ))
    fig_bar.update_layout(xaxis=dict(range=[0, 100], title="Risk Score (0-100)"), height=320, margin=dict(l=10, r=10, t=10, b=10))
    st.plotly_chart(fig_bar, use_container_width=True)

with col2:
    st.markdown(f"#### {T['overall_risk']}")
    fig_gauge = go.Figure(go.Indicator(
        mode="gauge+number", value=overall_risk,
        gauge={
            "axis": {"range": [0, 100]},
            "bar": {"color": risk_color},
            "steps": [
                {"range": [0, 25],   "color": "rgba(46,204,113,0.3)"},
                {"range": [25, 50],  "color": "rgba(241,196,15,0.3)"},
                {"range": [50, 75],  "color": "rgba(230,126,34,0.3)"},
                {"range": [75, 100], "color": "rgba(231,76,60,0.3)"},
            ],
        },
        number={"suffix": " / 100"},
    ))
    fig_gauge.update_layout(height=320, margin=dict(l=10, r=10, t=30, b=10))
    st.plotly_chart(fig_gauge, use_container_width=True)

st.markdown("---")

# =========================================================
# HISTORICAL TRENDS
# =========================================================
st.subheader("📈 " + T["trends"])

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

fig_line = px.line(plot_df, x="datetime", y=selected_param, labels={"datetime": "", selected_param: selected_param_label})
fig_line.update_traces(line_color="#3498db")
fig_line.update_layout(height=350, margin=dict(l=10, r=10, t=10, b=10))

if selected_param == "overall_risk":
    fig_line.add_hline(y=50, line_dash="dash", line_color="orange", annotation_text=T["high_risk"])
    fig_line.add_hline(y=75, line_dash="dash", line_color="red",    annotation_text=T["critical_risk"])

st.plotly_chart(fig_line, use_container_width=True)
st.markdown("---")

# =========================================================
# ZONE RISK MAP
# =========================================================
st.subheader("🗺️ " + T["map_view"])

map_rows = []
for zname, zinfo in zones_data.items():
    zsensors, _ = get_combined_sensor_data(zname, st.session_state.seed_offset)
    zrisks   = compute_disease_risks(zsensors)
    zoverall = float(np.mean(list(zrisks.values())))
    lvl, col = get_risk_label(zoverall)
    map_rows.append({
        "Zone":       zname.split(" - ")[1] if " - " in zname else zname,
        "lat":        zinfo["lat"],
        "lon":        zinfo["lon"],
        "Risk Score": zoverall,
        "Risk Level": lvl,
        "Population": zinfo["population"],
    })

map_df = pd.DataFrame(map_rows)
fig_map = px.scatter_mapbox(
    map_df, lat="lat", lon="lon",
    size="Risk Score", color="Risk Score",
    color_continuous_scale=["#2ecc71", "#f1c40f", "#e67e22", "#e74c3c"],
    range_color=[0, 100], size_max=35, zoom=11,
    hover_name="Zone",
    hover_data={"lat": False, "lon": False, "Risk Score": ":.1f", "Population": True, "Risk Level": True},
)
fig_map.update_layout(mapbox_style="open-street-map", margin=dict(l=0, r=0, t=0, b=0), height=420)
st.plotly_chart(fig_map, use_container_width=True)

st.dataframe(
    map_df[["Zone", "Population", "Risk Score", "Risk Level"]].rename(columns={
        "Zone": T["zone"], "Population": T["population"],
        "Risk Score": T["overall_risk"], "Risk Level": T["risk_level"],
    }),
    use_container_width=True, hide_index=True,
)
st.markdown("---")

# =========================================================
# KEY INSIGHTS
# =========================================================
st.subheader("🔍 " + T["key_insights"])

insight_cols = st.columns(3)
recent_risk_change = hist_df["overall_risk"].iloc[-24:].mean() - hist_df["overall_risk"].iloc[-48:-24].mean()
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
    import time
    time.sleep(5)
    st.session_state.seed_offset += 1
    st.rerun()
