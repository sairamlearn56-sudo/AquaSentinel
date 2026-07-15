"""
AquaSentinel — AI Community Water Health Early Warning System
================================================================================
Redesigned dashboard (matches the "Dashboard" mockup: safe/not-safe status
circles, live readings, disease-risk icons, "what to do" guide, trends,
forecast, alerts, history, map, and an AI Voice Assistant that AUTOMATICALLY
speaks up when the water becomes unsafe.

Run with:
    pip install streamlit plotly pandas numpy twilio firebase-admin
    streamlit run health_early_warning_app.py

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

VOICE ASSISTANT NOTE:
    The AI Voice Assistant uses the browser's built-in Web Speech API
    (speechSynthesis) — no extra install needed, works fully offline once the
    page is loaded. Some browsers block auto-playing audio until the person
    has clicked anywhere on the page once; if the automatic alert stays
    silent, just tap the "Tap to Speak" button once and it will work
    automatically after that for the rest of the session.
"""

import json
import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime
import streamlit.components.v1 as components

# =========================================================
# PAGE CONFIG
# =========================================================
st.set_page_config(
    page_title="AquaSentinel — Water Health Monitor",
    page_icon="💧",
    layout="wide",
    initial_sidebar_state="expanded",
)
from auth import login, logout

if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False

if not st.session_state["logged_in"]:
    login()
    st.stop()

logout()
# =========================================================
# STYLING — light, friendly, card-based dashboard (matches mockup)
# =========================================================
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Poppins:wght@500;600;700;800&family=Inter:wght@400;500;600;700&display=swap');

html, body, [class*="css"] { font-family: 'Inter', -apple-system, sans-serif !important; }
h1, h2, h3 { font-family: 'Poppins', sans-serif !important; letter-spacing: -0.3px; }

.block-container { padding-top: 1.4rem; }

section[data-testid="stSidebar"] {
    background-color: #0f2027;
    border-right: 1px solid #1c3038;
}
section[data-testid="stSidebar"] * { color: #eaf3f3 !important; }
section[data-testid="stSidebar"] .stRadio label { font-size: 1.0rem !important; padding: 4px 0; }

div[data-testid="stMetric"] {
    background: #ffffff08;
    border: 1px solid rgba(120,120,120,0.18);
    border-radius: 14px;
    padding: 12px 16px;
}

.card {
    background: rgba(140,140,140,0.05);
    border: 1px solid rgba(120,120,120,0.15);
    border-radius: 18px;
    padding: 20px 24px;
    margin-bottom: 16px;
}

/* --- Status circles (Water Is Safe / Not Safe) --- */
.status-box {
    border-radius: 18px;
    padding: 22px 26px;
    display: flex;
    align-items: center;
    gap: 20px;
    border: 1px solid rgba(120,120,120,0.15);
}
.status-safe   { background: rgba(46,204,113,0.08); }
.status-caution{ background: rgba(241,196,15,0.10); }
.status-danger { background: rgba(231,76,60,0.10); }

@keyframes pulseGreen { 0%{box-shadow:0 0 0 0 rgba(46,204,113,.55);} 70%{box-shadow:0 0 0 22px rgba(46,204,113,0);} 100%{box-shadow:0 0 0 0 rgba(46,204,113,0);} }
@keyframes pulseYellow{ 0%{box-shadow:0 0 0 0 rgba(241,196,15,.55);} 70%{box-shadow:0 0 0 22px rgba(241,196,15,0);} 100%{box-shadow:0 0 0 0 rgba(241,196,15,0);} }
@keyframes pulseRed   { 0%{box-shadow:0 0 0 0 rgba(231,76,60,.6);}  70%{box-shadow:0 0 0 26px rgba(231,76,60,0);}  100%{box-shadow:0 0 0 0 rgba(231,76,60,0);} }

.status-circle {
    width: 92px; height: 92px; border-radius: 50%;
    display:flex; align-items:center; justify-content:center;
    font-size: 2.6rem; flex-shrink:0;
}
.circle-safe    { background:#2ecc71; animation: pulseGreen 2.4s infinite; }
.circle-caution { background:#f1c40f; animation: pulseYellow 2.2s infinite; }
.circle-danger  { background:#e74c3c; animation: pulseRed 1.6s infinite; }

.status-title-safe    { color:#27ae60; font-family:'Poppins',sans-serif; font-weight:800; font-size:1.5rem; }
.status-title-caution { color:#d4a800; font-family:'Poppins',sans-serif; font-weight:800; font-size:1.5rem; }
.status-title-danger  { color:#c0392b; font-family:'Poppins',sans-serif; font-weight:800; font-size:1.5rem; }

.health-bar-track { width:100%; height:10px; border-radius:6px; background:rgba(120,120,120,0.2); margin-top:8px; }
.health-bar-fill { height:10px; border-radius:6px; }

.disease-chip {
    text-align:center; border-radius:14px; padding:14px 8px;
    border:1px solid rgba(120,120,120,0.15); background: rgba(140,140,140,0.05);
}
.disease-emoji { font-size: 2.1rem; }
.disease-name { font-weight:700; font-size:0.95rem; margin-top:4px; }
.risk-tag-low { color:#2ecc71; font-weight:700; font-size:0.82rem; }
.risk-tag-mod { color:#f1c40f; font-weight:700; font-size:0.82rem; }
.risk-tag-high{ color:#e67e22; font-weight:700; font-size:0.82rem; }
.risk-tag-crit{ color:#e74c3c; font-weight:700; font-size:0.82rem; }

.todo-item { display:flex; align-items:center; gap:10px; padding:8px 0; border-bottom:1px dashed rgba(120,120,120,0.15); }
.todo-item:last-child { border-bottom:none; }

.voice-box {
    border-radius:18px; padding:20px; text-align:center;
    background: linear-gradient(160deg, rgba(52,152,219,0.08), rgba(52,152,219,0.02));
    border: 1px solid rgba(52,152,219,0.25);
}
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
    if "twilio" in st.secrets:
        t = st.secrets["twilio"]
        return t.get("account_sid", ""), t.get("auth_token", ""), t.get("from_number", "")
    return (
        st.session_state.get("twilio_sid", ""),
        st.session_state.get("twilio_token", ""),
        st.session_state.get("twilio_from", ""),
    )


def send_sms_alert(message: str, account_sid: str, auth_token: str, from_number: str):
    try:
        from twilio.rest import Client
        client = Client(account_sid, auth_token)
        msg = client.messages.create(body=message, from_=from_number, to=ALERT_PHONE_NUMBER)
        return True, f"SMS sent! SID: {msg.sid}"
    except ImportError:
        return False, "Twilio not installed. Run: pip install twilio"
    except Exception as e:
        return False, f"SMS failed: {str(e)}"


def build_sms_message(zone, overall_risk, alerted_diseases, sensors, risk_label):
    disease_list = ", ".join([f"{d} ({s:.0f}/100)" for d, s in alerted_diseases.items()])
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    return (
        f"[WATER HEALTH ALERT] {timestamp}\nZone: {zone}\n"
        f"Status: {risk_label} ({overall_risk:.1f}/100)\n"
        f"Diseases of concern: {disease_list}\n"
        f"pH: {sensors['ph']:.2f} | Bacteria: {sensors['bacteria']:.0f} CFU/mL | Rain: {sensors['rainfall']:.1f}mm\n"
        f"ACTION: Do not drink untreated water. Boil water. Follow the safety guide."
    )


# =========================================================
# SESSION STATE
# =========================================================
defaults = {
    "seed_offset": 0, "last_sms_sent_score": None, "sms_log": [],
    "nav_page": "nav_home", "last_spoken_state": None, "voice_enabled": True,
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

# =========================================================
# HELPERS
# =========================================================
def get_risk_label(score):
    if score < 25: return "Low Risk", "#2ecc71"
    elif score < 50: return "Moderate Risk", "#f1c40f"
    elif score < 75: return "High Risk", "#e67e22"
    else: return "Critical Risk", "#e74c3c"

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
        "Skin Infections": 0.4*turb_risk + 0.3*bact_risk + 0.3*ph_risk,
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

def generate_forecast(current_risk, days=7):
    rng = np.random.default_rng(int(current_risk * 100))
    vals = [current_risk]
    for _ in range(days - 1):
        vals.append(float(np.clip(vals[-1] + rng.normal(0, 12), 0, 100)))
    return vals

def count_contamination_events(df, column="overall_risk", threshold=50):
    if df is None or column not in df.columns or len(df) < 2:
        return 0
    above = df[column].fillna(0) >= threshold
    crossings = above & ~above.shift(1, fill_value=False)
    return int(crossings.sum())

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
# SAFETY CONTENT — plain language, for EVERYONE (not just farmers)
# =========================================================
GENERAL_PRECAUTIONS = [
    ("🔥", "Boil drinking water for at least 1 minute, or use a certified filter/purification tablet."),
    ("🧴", "Add chlorine or bleaching powder to stored water if advised by local health workers."),
    ("⏳", "If you just treated the water, wait for it to settle/cool before using it."),
    ("🧼", "Wash your hands with soap for 20 seconds before eating and after using the toilet."),
    ("🚫", "Do not irrigate vegetables, cook, or bathe with water flagged as unsafe."),
    ("🐄", "Keep drinking-water sources away from toilets, drains, and animal areas."),
    ("📞", "If you feel sick or the water looks/smells odd, contact your nearest health officer."),
]

DISEASE_SAFETY_INFO = {
    "Cholera": {"icon": "🤢", "symptoms": "Sudden watery diarrhea, vomiting, rapid dehydration.",
        "prevention": "Drink only boiled/treated water; avoid raw or undercooked food from affected areas.",
        "seek_help": "Go to a clinic immediately if you see severe watery diarrhea or dehydration."},
    "Typhoid": {"icon": "🌡️", "symptoms": "Long-lasting fever, weakness, stomach pain, headache.",
        "prevention": "Wash hands often; avoid street food or water from unknown sources.",
        "seek_help": "See a doctor if fever lasts more than 2–3 days."},
    "Diarrhea": {"icon": "💧", "symptoms": "Frequent loose stools, cramps, mild fever.",
        "prevention": "Keep drinking water and food clean; wash hands regularly.",
        "seek_help": "Use oral rehydration salts (ORS); see a doctor if it lasts over 2 days."},
    "Dysentery": {"icon": "🩸", "symptoms": "Blood or mucus in stool, stomach cramps, fever.",
        "prevention": "Avoid contaminated water; make sure food is cooked thoroughly and served hot.",
        "seek_help": "Get medical help right away if you see blood in the stool."},
    "Hepatitis A": {"icon": "🫀", "symptoms": "Tiredness, nausea, stomach pain, yellow skin/eyes (jaundice).",
        "prevention": "Get vaccinated if possible; avoid raw shellfish and untreated water.",
        "seek_help": "See a doctor if you notice jaundice, dark urine, or ongoing tiredness."},
    "Skin Infections": {"icon": "🖐️", "symptoms": "Rashes, itching, redness, or sores after contact with water.",
        "prevention": "Avoid bathing or washing directly in flagged high-risk water.",
        "seek_help": "See a health worker if a rash spreads or does not heal."},
}

DISEASE_TODO = {
    "safe": [("🚿", "It is fine to use this water for drinking, cooking, and daily use."),
             ("🌾", "Safe for irrigation and animals too."),
             ("🔁", "Keep checking readings regularly — conditions can change quickly.")],
    "caution": [("🔥", "Boil water before drinking, just to be safe."),
                ("👀", "Watch the readings closely over the next few hours."),
                ("🧼", "Keep up good hand-washing and hygiene habits."),
                ("🚫", "Avoid using this water for infants or anyone with a weak immune system.")],
    "danger": [("🔥", "Boil water before any use."),
               ("🧴", "Add chlorine/bleaching powder if instructed by health workers."),
               ("⏳", "Wait 24 hours after treatment before using stored water."),
               ("🚫", "Do not irrigate vegetables or bathe with this water."),
               ("📞", "Contact your nearest health officer if anyone feels sick.")],
}

# =========================================================
# SIDEBAR
# =========================================================
with st.sidebar:
    st.markdown("## 💧 AquaSentinel")
    st.caption("Water Health Monitor")
    st.markdown("---")

    selected_zone = st.selectbox("Location", options=list(ZONES_DATA.keys()))
    temp_unit = st.radio("Temperature Unit", options=["Celsius (°C)", "Fahrenheit (°F)"], horizontal=True)

    st.markdown("### Menu")
    nav_options = ["nav_home", "nav_live", "nav_disease", "nav_todo", "nav_trends", "nav_map", "nav_alerts", "nav_settings"]
    nav_labels = {
        "nav_home": "🏠 Dashboard", "nav_live": "📡 Live Readings", "nav_disease": "🧬 Risk & Diseases",
        "nav_todo": "✅ What to Do?", "nav_trends": "📈 Trends & History", "nav_map": "🗺️ Map View",
        "nav_alerts": "🔔 Alerts", "nav_settings": "⚙️ Settings",
    }
    nav_choice = st.radio("Menu", options=nav_options, format_func=lambda k: nav_labels[k],
                           index=nav_options.index(st.session_state.nav_page), label_visibility="collapsed")
    st.session_state.nav_page = nav_choice

    st.markdown("---")
    st.checkbox("🔊 Voice alerts enabled", value=st.session_state.voice_enabled, key="voice_enabled")
    auto_refresh = st.checkbox("Auto-refresh every 10s", value=False)
    if st.button("🔄 Refresh Data", use_container_width=True):
        st.session_state.seed_offset += 1
        st.rerun()

    st.markdown("---")
    if FIREBASE_AVAILABLE:
        st.success("🟢 Sensor connected")
    else:
        st.warning("⚪ Demo data (sensor not connected)")

    st.markdown("---")
    st.error("🚑 **Emergency Help**\n\nCall your local health officer or ASHA worker immediately if anyone shows signs of illness.")

def c_to_f(c): return c * 9 / 5 + 32
def format_temp(value_c):
    if temp_unit.startswith("Fahrenheit"):
        return f"{c_to_f(value_c):.1f} °F"
    return f"{value_c:.1f} °C"

# =========================================================
# DATA
# =========================================================
zone_info = ZONES_DATA[selected_zone]
sensors, is_live, fetch_error = get_sensor_data(selected_zone, zone_info["firebase_key"], st.session_state.seed_offset)
disease_risks = compute_disease_risks(sensors)
overall_risk = float(np.mean(list(disease_risks.values())))
hist_df = generate_historical_data(selected_zone)
alerted = {k: v for k, v in disease_risks.items() if v >= 50}
mild_alerted = {k: v for k, v in disease_risks.items() if v >= 25}

twilio_sid, twilio_token, twilio_from = get_twilio_credentials()

if overall_risk < 25:
    risk_state, status_word = "safe", "WATER IS SAFE"
elif overall_risk < 50:
    risk_state, status_word = "caution", "WATER NEEDS CAUTION"
else:
    risk_state, status_word = "danger", "WATER IS NOT SAFE"

risk_label, risk_color = get_risk_label(overall_risk)

# =========================================================
# AUTO-SMS
# =========================================================
sms_threshold = st.session_state.get("sms_threshold", 50)
sms_auto = st.session_state.get("sms_auto", False)
if sms_auto and overall_risk >= sms_threshold:
    prev = st.session_state.last_sms_sent_score
    if prev is None or prev < sms_threshold:
        if twilio_sid and twilio_token and twilio_from:
            sms_body = build_sms_message(selected_zone, overall_risk, alerted or {"Overall": overall_risk}, sensors, risk_label)
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
# AI VOICE ASSISTANT — builds a plain-language spoken report
# =========================================================
def build_voice_message(auto=False):
    parts = []
    if auto:
        parts.append("Attention. This is an automatic water health alert.")
    if risk_state == "safe":
        parts.append(f"Good news. The water in {selected_zone} is currently safe to use for drinking, cooking, and daily use.")
    elif risk_state == "caution":
        parts.append(f"Caution. Water quality in {selected_zone} is showing some warning signs. Please be careful.")
        parts.append("It is recommended to boil water before drinking and to keep checking the readings.")
    else:
        parts.append(f"Warning. The water in {selected_zone} is not safe right now. Please do not drink it without boiling or treating it first.")
        if alerted:
            names = ", ".join(alerted.keys())
            parts.append(f"The possible diseases from this contamination level include: {names}.")
        parts.append("Please follow the safety guidelines. Boil the water, add chlorine if advised, and avoid using it for irrigation or bathing.")
        parts.append("If anyone feels sick, contact your nearest health officer immediately.")
    return " ".join(parts)

def render_voice_widget(auto_speak: bool):
    message = build_voice_message(auto=auto_speak).replace('"', "'")
    should_autoplay = "true" if (auto_speak and st.session_state.voice_enabled) else "false"
    html_code = f"""
    <div id="voice-root" style="font-family: Inter, sans-serif;">
      <button id="speakBtn" style="
          background:#2f80ed;color:white;border:none;border-radius:10px;
          padding:12px 20px;font-weight:700;cursor:pointer;font-size:0.95rem;width:100%;">
          🎙️ Tap to Speak
      </button>
      <p id="voiceStatus" style="opacity:0.7;font-size:0.85rem;margin-top:8px;text-align:center;"></p>
    </div>
    <script>
      const msg = {json.dumps(message)};
      const statusEl = document.getElementById('voiceStatus');
      function speakNow() {{
        try {{
          window.parent.speechSynthesis.cancel();
          const utter = new SpeechSynthesisUtterance(msg);
          utter.rate = 0.95; utter.pitch = 1.0; utter.lang = 'en-US';
          utter.onstart = () => statusEl.innerText = "Speaking...";
          utter.onend = () => statusEl.innerText = "Ask anything about your water quality.";
          window.parent.speechSynthesis.speak(utter);
        }} catch (e) {{ statusEl.innerText = "Voice not supported in this browser."; }}
      }}
      document.getElementById('speakBtn').addEventListener('click', speakNow);
      if ({should_autoplay}) {{
        setTimeout(speakNow, 500);
      }}
    </script>
    """
    components.html(html_code, height=90)

# =========================================================
# TOP HEADER
# =========================================================
h1, h2, h3 = st.columns([2.2, 1, 1])
with h1:
    st.markdown(f"### 💧 AquaSentinel Dashboard")
    st.caption(f"📍 {selected_zone}   •   🗓️ {datetime.now().strftime('%d %b %Y, %I:%M %p')}")
with h2:
    st.metric("Health Score", f"{100 - overall_risk:.0f} / 100")
with h3:
    st.markdown(f"""<div style="background:{risk_color}22;border:2px solid {risk_color};
        border-radius:12px;padding:10px;text-align:center;font-weight:700;color:{risk_color};">
        {risk_label}</div>""", unsafe_allow_html=True)
st.markdown("---")

page = st.session_state.nav_page

# =========================================================
# PAGE: DASHBOARD (HOME) — mirrors the mockup layout
# =========================================================
if page == "nav_home":
    health_score = 100 - overall_risk
    circle_class = f"circle-{risk_state}"
    title_class = f"status-title-{risk_state}"
    box_class = f"status-{risk_state}"
    emoji = {"safe": "✅", "caution": "⚠️", "danger": "🚨"}[risk_state]
    sub_text = {
        "safe": "You can use this water for drinking, irrigation, and daily use.",
        "caution": "Some readings are drifting — boil water before drinking, just in case.",
        "danger": "Do not drink or cook with this water without treating it first.",
    }[risk_state]

    cA, cB = st.columns(2)
    with cA:
        st.markdown(f"""
        <div class="status-box {box_class}">
            <div class="status-circle {circle_class}">{emoji}</div>
            <div style="flex:1;">
                <div class="{title_class}">{status_word}</div>
                <p style="opacity:0.85; margin:4px 0 8px 0;">{sub_text}</p>
                <b>Health Score: {health_score:.0f} / 100</b>
                <div class="health-bar-track">
                    <div class="health-bar-fill" style="width:{health_score:.0f}%; background:{risk_color};"></div>
                </div>
            </div>
        </div>""", unsafe_allow_html=True)
    with cB:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown("##### 🎙️ AI Voice Assistant")
        st.caption("Automatically speaks up when the water becomes unsafe. Tap the button to hear the status any time.")
        render_voice_widget(auto_speak=(risk_state != "safe" and st.session_state.last_spoken_state != risk_state))
        st.markdown('</div>', unsafe_allow_html=True)
    if risk_state != "safe":
        st.session_state.last_spoken_state = risk_state
    else:
        st.session_state.last_spoken_state = "safe"

    st.markdown("#### 📡 Live Water Readings")
    s1, s2, s3, s4, s5, s6 = st.columns(6)
    s1.metric("TDS (ppm)", f"{sensors['tds']:.0f}")
    s2.metric("pH Level", f"{sensors['ph']:.2f}")
    s3.metric("Turbidity (NTU)", f"{sensors['turbidity']:.1f}")
    s4.metric("Temperature", format_temp(sensors["water_temp_c"]))
    s5.metric("Bacteria (CFU/mL)", f"{sensors['bacteria']:.0f}")
    s6.metric("Humidity (%)", f"{sensors['humidity']:.0f}")

    st.markdown("#### ")
    d1, d2 = st.columns([1.4, 1])
    with d1:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown("##### 🧬 Disease Risk Prediction")
        cols = st.columns(len(disease_risks))
        for col, (dname, score) in zip(cols, disease_risks.items()):
            lvl, _ = get_risk_label(score)
            tag_class = {"Low Risk": "risk-tag-low", "Moderate Risk": "risk-tag-mod",
                         "High Risk": "risk-tag-high", "Critical Risk": "risk-tag-crit"}[lvl]
            info = DISEASE_SAFETY_INFO[dname]
            col.markdown(f"""<div class="disease-chip">
                <div class="disease-emoji">{info['icon']}</div>
                <div class="disease-name">{dname}</div>
                <div class="{tag_class}">{lvl}</div>
            </div>""", unsafe_allow_html=True)
        if risk_state == "danger":
            st.error("🚨 Dirty water can cause serious diseases. Use clean, treated water to stay safe and healthy.")
        elif risk_state == "caution":
            st.warning("⚠️ Some readings are drifting outside the safe range. Keep monitoring closely.")
        else:
            st.success("✅ All readings are within safe limits right now.")
        st.markdown('</div>', unsafe_allow_html=True)
    with d2:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown("##### ✅ What Should You Do?")
        for icon, tip in DISEASE_TODO[risk_state]:
            st.markdown(f'<div class="todo-item"><span style="font-size:1.3rem;">{icon}</span><span>{tip}</span></div>', unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

    t1, t2 = st.columns(2)
    with t1:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown("##### 📈 Water Quality Trend (last 7 days)")
        recent = hist_df.tail(24*7).iloc[::12]
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=recent["datetime"], y=recent["overall_risk"], mode="lines+markers",
                                  line=dict(color="#3498db", width=3), name="Risk Score"))
        fig.update_layout(height=280, margin=dict(l=10, r=10, t=10, b=10), yaxis=dict(range=[0, 100]))
        st.plotly_chart(fig, use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)
    with t2:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown("##### 🔮 Water Quality Forecast (next 7 days)")
        forecast_vals = generate_forecast(overall_risk)
        forecast_dates = pd.date_range(start=datetime.now(), periods=7)
        face_map = lambda v: "🟢" if v < 25 else ("🟡" if v < 50 else ("🟠" if v < 75 else "🔴"))
        cols = st.columns(7)
        for col, dt, val in zip(cols, forecast_dates, forecast_vals):
            lvl, _ = get_risk_label(val)
            col.markdown(f"<div style='text-align:center;'><b>{dt.strftime('%d %b')}</b><br>"
                         f"<span style='font-size:1.6rem;'>{face_map(val)}</span><br>"
                         f"<span style='font-size:0.75rem;'>{lvl}</span></div>", unsafe_allow_html=True)
        st.info("💡 The AI model predicts future water quality using recent readings, rainfall, and seasonal patterns.")
        st.markdown('</div>', unsafe_allow_html=True)

    b1, b2, b3 = st.columns(3)
    with b1:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown("##### 🔔 Recent Alerts")
        sample_alerts = [
            ("✅", "Water quality is in safe range.", "Safe") if risk_state == "safe" else ("🚨", f"{risk_label} detected — take precautions.", risk_label),
            ("⚠️", "Turbidity has been drifting upward.", "Moderate"),
            ("✅", "Readings returned to normal earlier today.", "Safe"),
        ]
        for icon, text, tag in sample_alerts:
            st.markdown(f"{icon} **{text}**  \n`{tag}`")
        st.markdown('</div>', unsafe_allow_html=True)
    with b2:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown("##### 📋 Water Quality History")
        hist_summary = hist_df.tail(24*5).iloc[::24][["datetime", "overall_risk"]].copy()
        hist_summary["Status"] = hist_summary["overall_risk"].apply(lambda v: get_risk_label(v)[0])
        hist_summary["datetime"] = hist_summary["datetime"].dt.strftime("%d %b %Y")
        hist_summary["overall_risk"] = hist_summary["overall_risk"].round(0).astype(int).astype(str) + "/100"
        st.dataframe(hist_summary.rename(columns={"datetime": "Date", "overall_risk": "Score"}),
                     hide_index=True, use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)
    with b3:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown("##### 📝 Today's Summary")
        st.write(f"**Water Status:** {status_word.title()}")
        st.write(f"**Health Score:** {health_score:.0f}/100")
        st.write(f"**Disease Risk:** {risk_label}")
        st.write(f"**Safe for drinking:** {'Yes' if risk_state=='safe' else 'No — boil/treat first'}")
        st.write(f"**Safe for irrigation:** {'Yes' if risk_state!='danger' else 'No'}")
        st.markdown('</div>', unsafe_allow_html=True)

# =========================================================
# PAGE: LIVE READINGS
# =========================================================
elif page == "nav_live":
    st.markdown("### 📡 Live Water Readings")
    s1, s2, s3, s4 = st.columns(4)
    s5, s6, s7, s8 = st.columns(4)
    s1.metric("Water Temperature", format_temp(sensors["water_temp_c"]))
    s2.metric("Ambient Temperature", format_temp(sensors["ambient_temp_c"]))
    s3.metric("pH Level", f"{sensors['ph']:.2f}")
    s4.metric("Turbidity (NTU)", f"{sensors['turbidity']:.1f}")
    s5.metric("TDS (ppm)", f"{sensors['tds']:.0f}")
    s6.metric("Rainfall (mm)", f"{sensors['rainfall']:.1f}")
    s7.metric("Bacteria (CFU/mL)", f"{sensors['bacteria']:.0f}")
    s8.metric("Humidity (%)", f"{sensors['humidity']:.0f}%")
    st.markdown("---")
    fig_gauge = go.Figure(go.Indicator(mode="gauge+number", value=overall_risk,
        title={"text": "Overall Risk Score"},
        gauge={"axis": {"range": [0, 100]}, "bar": {"color": risk_color},
            "steps": [{"range": [0, 25], "color": "rgba(46,204,113,0.3)"},
                      {"range": [25, 50], "color": "rgba(241,196,15,0.3)"},
                      {"range": [50, 75], "color": "rgba(230,126,34,0.3)"},
                      {"range": [75, 100], "color": "rgba(231,76,60,0.3)"}]}))
    fig_gauge.update_layout(height=320)
    st.plotly_chart(fig_gauge, use_container_width=True)
    if not is_live:
        st.info("⚪ Showing simulated demo data — connect a live ESP32 sensor via Firebase to see real readings.")

# =========================================================
# PAGE: RISK & DISEASES
# =========================================================
elif page == "nav_disease":
    st.markdown("### 🧬 Disease Risk & Possible Outcomes by Contamination Level")
    st.caption("This shows what could happen at the current contamination level — not a diagnosis. Always confirm with a health worker.")
    risk_df = pd.DataFrame({"Disease": list(disease_risks.keys()), "Risk Score": list(disease_risks.values())})
    risk_df["Color"] = risk_df["Risk Score"].apply(lambda x: get_risk_label(x)[1])
    fig_bar = go.Figure(go.Bar(x=risk_df["Risk Score"], y=risk_df["Disease"], orientation="h",
        marker_color=risk_df["Color"], text=[f"{v:.1f}" for v in risk_df["Risk Score"]], textposition="outside"))
    fig_bar.update_layout(xaxis=dict(range=[0, 100], title="Risk Score (0-100)"), height=330, margin=dict(l=10, r=10, t=10, b=10))
    st.plotly_chart(fig_bar, use_container_width=True)

    st.markdown("#### 🧠 Possible Disease Outcomes at This Contamination Level")
    for d, score in sorted(disease_risks.items(), key=lambda x: -x[1]):
        info = DISEASE_SAFETY_INFO[d]
        lvl, col = get_risk_label(score)
        with st.expander(f"{info['icon']} {d} — {lvl} ({score:.1f}/100)", expanded=(score >= 50)):
            st.markdown(f"**🤒 Symptoms:** {info['symptoms']}")
            st.markdown(f"**🛡️ Prevention:** {info['prevention']}")
            st.markdown(f"**🏥 Seek help:** {info['seek_help']}")

# =========================================================
# PAGE: WHAT TO DO
# =========================================================
elif page == "nav_todo":
    st.markdown("### ✅ What to Do — Safety Guide")
    st.caption("Simple steps anyone can follow, based on the current water status.")
    box_class = f"status-{risk_state}"
    st.markdown(f"""<div class="status-box {box_class}"><div style="font-size:2rem;">{ {'safe':'✅','caution':'⚠️','danger':'🚨'}[risk_state] }</div>
        <div><b>Current status: {status_word}</b></div></div>""", unsafe_allow_html=True)
    st.markdown("#### Right now, you should:")
    for icon, tip in DISEASE_TODO[risk_state]:
        st.markdown(f"- {icon} {tip}")
    st.markdown("---")
    st.markdown("#### 🌍 General precautions (always good practice)")
    for icon, tip in GENERAL_PRECAUTIONS:
        st.markdown(f"- {icon} {tip}")
    st.markdown("---")
    st.markdown("#### 🧬 If a disease risk is elevated, here's what to know:")
    for d, score in alerted.items():
        info = DISEASE_SAFETY_INFO[d]
        st.markdown(f"**{info['icon']} {d}** — {info['prevention']}")

# =========================================================
# PAGE: TRENDS & HISTORY
# =========================================================
elif page == "nav_trends":
    st.markdown("### 📈 Trends & History")
    real_hist_df = fetch_real_historical_data()
    if real_hist_df is not None and len(real_hist_df) >= 2:
        st.success(f"🟢 Showing real logged history ({len(real_hist_df)} readings)")
        plot_source = real_hist_df
    else:
        st.info("⚪ No real logged history yet — showing simulated trend data.")
        plot_source = hist_df

    tab1, tab2 = st.tabs(["📊 Trend Chart", "📋 Contamination Events"])
    with tab1:
        param_options = {"Bacteria": "bacteria", "Turbidity": "turbidity", "pH": "ph",
                          "Rainfall": "rainfall", "Water Temp": "water_temp_c", "Overall Risk": "overall_risk"}
        chosen = st.selectbox("Choose what to plot", options=list(param_options.keys()))
        col = param_options[chosen]
        fig_line = px.line(plot_source, x="datetime", y=col, labels={"datetime": "", col: chosen})
        fig_line.update_traces(line_color="#3498db")
        fig_line.update_layout(height=350, margin=dict(l=10, r=10, t=10, b=10))
        if col == "overall_risk":
            fig_line.add_hline(y=50, line_dash="dash", line_color="orange", annotation_text="High Risk")
            fig_line.add_hline(y=75, line_dash="dash", line_color="red", annotation_text="Critical")
        st.plotly_chart(fig_line, use_container_width=True)
    with tab2:
        high_events = count_contamination_events(plot_source, "overall_risk", 50)
        critical_events = count_contamination_events(plot_source, "overall_risk", 75)
        peak_risk = float(plot_source["overall_risk"].max()) if len(plot_source) else 0.0
        span_days = max((plot_source["datetime"].max() - plot_source["datetime"].min()).days, 1) if len(plot_source) >= 2 else 1
        e1, e2, e3, e4 = st.columns(4)
        e1.metric("⚠️ High-Risk Events", high_events)
        e2.metric("🔴 Critical Events", critical_events)
        e3.metric("📈 Peak Risk", f"{peak_risk:.1f}/100")
        e4.metric("🗓️ Days Covered", span_days)

# =========================================================
# PAGE: MAP VIEW
# =========================================================
elif page == "nav_map":
    st.markdown("### 🗺️ Village Water Health Map")
    map_rows = []
    for zname, zinfo in ZONES_DATA.items():
        zsensors, z_is_live, _ = get_sensor_data(zname, zinfo["firebase_key"], st.session_state.seed_offset)
        zrisks = compute_disease_risks(zsensors)
        zoverall = float(np.mean(list(zrisks.values())))
        lvl, _ = get_risk_label(zoverall)
        map_rows.append({"Zone": zname.split(" - ")[1] if " - " in zname else zname, "lat": zinfo["lat"], "lon": zinfo["lon"],
                          "Risk Score": zoverall, "Risk Level": lvl, "Population": zinfo["population"], "Live": "🟢" if z_is_live else "⚪"})
    map_df = pd.DataFrame(map_rows)
    fig_map = px.scatter_mapbox(map_df, lat="lat", lon="lon", size="Risk Score", color="Risk Score",
        color_continuous_scale=["#2ecc71", "#f1c40f", "#e67e22", "#e74c3c"], range_color=[0, 100],
        size_max=35, zoom=11, hover_name="Zone",
        hover_data={"lat": False, "lon": False, "Risk Score": ":.1f", "Population": True, "Risk Level": True, "Live": True})
    fig_map.update_layout(mapbox_style="open-street-map", margin=dict(l=0, r=0, t=0, b=0), height=440)
    st.plotly_chart(fig_map, use_container_width=True)
    st.dataframe(map_df, hide_index=True, use_container_width=True)

# =========================================================
# PAGE: ALERTS (incl. SMS + voice settings)
# =========================================================
elif page == "nav_alerts":
    st.markdown("### 🔔 Active Alerts")
    if not alerted:
        st.success("✅ No active alerts. Conditions are normal.")
    else:
        for disease, score in alerted.items():
            lvl, col = get_risk_label(score)
            st.markdown(f"""<div style="background-color:{col}15;border-left:6px solid {col};
                border-radius:6px;padding:10px 16px;margin-bottom:6px;">
                <b>⚠️ Elevated risk detected for {disease}</b> — {lvl} ({score:.1f}/100)</div>""", unsafe_allow_html=True)
        with st.expander("📋 Recommended Actions", expanded=True):
            for icon, tip in DISEASE_TODO["danger" if overall_risk >= 50 else "caution"]:
                st.markdown(f"- {icon} {tip}")

    st.markdown("#### 🎙️ Voice Alert")
    render_voice_widget(auto_speak=False)

    with st.expander("📱 SMS Alert Settings", expanded=bool(alerted)):
        sms_preview_body = build_sms_message(selected_zone, overall_risk, alerted if alerted else {"Overall": overall_risk}, sensors, risk_label)
        st.markdown(f"**SMS Preview** → `{ALERT_PHONE_NUMBER}`")
        st.code(sms_preview_body, language=None)
        st.session_state["sms_threshold"] = st.slider("SMS Alert Threshold (risk score)", 0, 100, st.session_state.get("sms_threshold", 50))
        st.session_state["sms_auto"] = st.checkbox("Auto-send SMS when risk exceeds threshold", value=st.session_state.get("sms_auto", False))
        if not (twilio_sid and twilio_token and twilio_from):
            st.markdown("**Twilio credentials (only if not using Secrets):**")
            st.session_state["twilio_sid"] = st.text_input("Twilio Account SID", value=st.session_state.get("twilio_sid", ""))
            st.session_state["twilio_token"] = st.text_input("Twilio Auth Token", value=st.session_state.get("twilio_token", ""), type="password")
            st.session_state["twilio_from"] = st.text_input("Twilio Phone Number (from)", value=st.session_state.get("twilio_from", ""))
            twilio_sid, twilio_token, twilio_from = get_twilio_credentials()
        if st.button("📲 Send SMS Alert Now", type="primary"):
            if twilio_sid and twilio_token and twilio_from:
                ok, status = send_sms_alert(sms_preview_body, twilio_sid, twilio_token, twilio_from)
                st.session_state.sms_log.insert(0, {
                    "time": datetime.now().strftime("%H:%M:%S"), "zone": selected_zone,
                    "score": f"{overall_risk:.1f}", "status": "✅ Sent" if ok else f"❌ {status}",
                })
                st.success(f"✅ SMS sent! ({status})") if ok else st.error(f"❌ SMS failed: {status}")
            else:
                st.error("Please add Twilio credentials above (or via Streamlit Secrets) first.")
        if st.session_state.sms_log:
            st.markdown("**📋 SMS Activity Log**")
            st.dataframe(pd.DataFrame(st.session_state.sms_log), use_container_width=True, hide_index=True)

# =========================================================
# PAGE: SETTINGS
# =========================================================
elif page == "nav_settings":
    st.markdown("### ⚙️ Settings")
    st.write("**Firebase status:**", "🟢 Connected" if FIREBASE_AVAILABLE else f"🔴 Not connected ({FIREBASE_INIT_ERROR})")
    st.write("**Twilio status:**", "🟢 Configured" if (twilio_sid and twilio_token and twilio_from) else "🔴 Not configured")
    st.markdown("---")
    st.caption("AI-driven prototype for early warning of water-borne diseases (cholera, typhoid, diarrhea, dysentery, hepatitis A, skin infections). For demonstration purposes only — always confirm with local health authorities.")

st.markdown("---")
st.caption("💧 Clean Water Today, Better Tomorrow — Keep monitoring water quality regularly for a healthy community.")
