from frontend.map_view import (
    load_villages,
    load_inventory,
    create_flood_map,
)
from streamlit_folium import st_folium

"""Disaster Relief India.  Run with:  python -m streamlit run app.py"""
import hmac
import io
import os
import re
import sqlite3

import numpy as np
import pandas as pd
import requests
import streamlit as st
from PIL import Image, ImageOps

try:
    from streamlit_geolocation import streamlit_geolocation
except Exception:  # the "use my location" button is optional
    streamlit_geolocation = None

st.set_page_config(page_title="Disaster Relief India", page_icon="🌊", layout="centered")
if tuple(int(x) for x in st.__version__.split(".")[:2]) < (1, 37):
    st.error("Your Streamlit is too old. In the terminal run:  python -m pip install --upgrade streamlit")
    st.stop()

DB = "relief.db"
# Relief team logins. Set before running:  TEAM_USERS="asha:long-password,ravi:another-password"
def parse_users(text):
    users = {}
    for pair in text.split(","):
        pair = pair.strip().strip("\"'")
        if ":" in pair:
            name, pw = pair.split(":", 1)
            users[name.strip()] = pw.strip()
    return users or {"admin": "1234"}


TEAM_USERS = parse_users(os.environ.get("TEAM_USERS", ""))
PUBLIC_IMAGES_NEED_VERIFY = True  # photos are public only after the team verifies the report
MAX_IMAGE_BYTES = 10_000_000

ICON = {"need": "🔴", "update": "🟠", "offer": "🟢"}
COLOR = {"need": "#d62728", "update": "#ff7f0e", "offer": "#2ca02c"}
NEED_WEIGHT = {"Food": 0.7, "Medicine": 1.0, "Shelter": 0.8, "Transport": 0.6}
DISASTERS = ["Flood", "Cyclone", "Landslide", "Earthquake", "Fire", "Other"]
STATES = ["Andaman and Nicobar Islands", "Andhra Pradesh", "Arunachal Pradesh", "Assam", "Bihar",
          "Chandigarh", "Chhattisgarh", "Dadra and Nagar Haveli and Daman and Diu", "Delhi", "Goa",
          "Gujarat", "Haryana", "Himachal Pradesh", "Jammu and Kashmir", "Jharkhand", "Karnataka",
          "Kerala", "Ladakh", "Lakshadweep", "Madhya Pradesh", "Maharashtra", "Manipur", "Meghalaya",
          "Mizoram", "Nagaland", "Odisha", "Puducherry", "Punjab", "Rajasthan", "Sikkim", "Tamil Nadu",
          "Telangana", "Tripura", "Uttar Pradesh", "Uttarakhand", "West Bengal"]

# ---------- text: (English, Hindi). To add a language, add its name to LANGS and one more item to each tuple.
LANGS = ["English", "हिन्दी"]
S = {
    "title": ("Disaster Relief India", "आपदा राहत भारत"),
    "emergency": ("In an emergency call 112", "आपातकाल में 112 पर कॉल करें"),
    "tab_report": ("📝 Report", "📝 रिपोर्ट"), "tab_live": ("📍 Live", "📍 लाइव"),
    "tab_wx": ("🌦 Weather", "🌦 मौसम"), "tab_team": ("🧑‍🚒 Relief team", "🧑‍🚒 राहत टीम"),
    "what": ("What do you want to report?", "आप क्या बताना चाहते हैं?"),
    "kind_need": ("I need help", "मुझे मदद चाहिए"), "kind_update": ("Disaster update", "आपदा की स्थिति"),
    "kind_offer": ("Help available", "मदद उपलब्ध है"),
    "dis_Flood": ("Flood", "बाढ़"), "dis_Cyclone": ("Cyclone", "चक्रवात"), "dis_Landslide": ("Landslide", "भूस्खलन"),
    "dis_Earthquake": ("Earthquake", "भूकंप"), "dis_Fire": ("Fire", "आग"), "dis_Other": ("Other", "अन्य"),
    "need_Food": ("Food", "खाना"), "need_Medicine": ("Medicine", "दवा"),
    "need_Shelter": ("Shelter", "आश्रय"), "need_Transport": ("Transport", "वाहन"),
    "disaster": ("Disaster", "आपदा"), "state": ("State", "राज्य"), "choose": ("Choose", "चुनें"),
    "district": ("District", "ज़िला"), "place": ("Village or area", "गाँव या इलाका"),
    "need_q": ("What is needed?", "क्या चाहिए?"), "give_q": ("What can you give?", "आप क्या दे सकते हैं?"),
    "people": ("How many people?", "कितने लोग?"), "people_unit": ("people", "लोग"),
    "serious": ("How serious? (1 = low, 5 = life in danger)", "कितनी गंभीर स्थिति? (1 = कम, 5 = जान को ख़तरा)"),
    "vuln": ("Children, elderly or sick people are here", "बच्चे, बुज़ुर्ग या बीमार लोग हैं"),
    "details": ("Details (e.g. water rising, road closed)", "विवरण (जैसे पानी बढ़ रहा है, रास्ता बंद है)"),
    "photo": ("Photo of the place (optional)", "जगह की फ़ोटो (वैकल्पिक)"),
    "phone": ("Phone (optional, only relief teams see it)", "फ़ोन (वैकल्पिक, सिर्फ़ राहत टीम देखेगी)"),
    "gps_hint": ("📍 At the place now? Tap to share your exact location (press only if you are there)",
                 "📍 अभी उसी जगह पर हैं? सटीक लोकेशन देने के लिए दबाएँ (सिर्फ़ तब दबाएँ जब आप वहीं हों)"),
    "gps_ok": ("✅ Exact location captured", "✅ सटीक लोकेशन मिल गई"),
    "submit": ("Submit", "भेजें"),
    "err_place": ("Please choose the state and enter the place", "राज्य चुनें और जगह लिखें"),
    "big_image": ("Photo is too big (max 10 MB)", "फ़ोटो बहुत बड़ी है (अधिकतम 10 MB)"),
    "bad_image": ("This photo could not be read", "यह फ़ोटो पढ़ी नहीं जा सकी"),
    "saved": ("Thank you, your report is saved", "धन्यवाद, आपकी रिपोर्ट मिल गई"),
    "saved_guess": ("Thank you, your report is saved. Its map position is estimated from the place name.",
                    "धन्यवाद, आपकी रिपोर्ट मिल गई। मैप पर जगह इलाके के नाम से अनुमानित है।"),
    "none_yet": ("No reports yet", "अभी कोई रिपोर्ट नहीं"), "all_states": ("All states", "सभी राज्य"),
    "auto": ("Updates automatically every 30 seconds", "हर 30 सेकंड में अपने आप अपडेट होता है"),
    "m_need": ("Need help", "मदद चाहिए"), "m_update": ("Updates", "स्थिति"),
    "m_offer": ("Help available", "मदद उपलब्ध"), "m_done": ("Helped", "मदद मिली"),
    "verified": ("✅ Verified", "✅ जाँची हुई"), "done": ("Done", "पूरा"),
    # weather
    "wx_place": ("City or district", "शहर या ज़िला"),
    "wx_default": ("Showing the area of the latest report", "ताज़ा रिपोर्ट वाले इलाके का मौसम"),
    "wx_notfound": ("Place not found", "जगह नहीं मिली"),
    "wx_fail": ("Weather is not available right now", "मौसम की जानकारी अभी उपलब्ध नहीं है"),
    "temp": ("Temperature", "तापमान"), "rain_now": ("Rain now", "अभी बारिश"),
    "humid": ("Humidity", "नमी"), "wind": ("Wind", "हवा"),
    "day": ("Day", "दिन"), "sky": ("Sky", "आसमान"), "rain": ("Rain", "बारिश"),
    "wx_heavy": ("Heavy or very heavy rain is forecast on {day}. Stay alert and follow official warnings.",
                 "{day} को भारी या बहुत भारी बारिश का अनुमान है। सतर्क रहें और सरकारी चेतावनी मानें।"),
    "wx_note": ("Weather data: Open-Meteo.com. These are forecasts, not official warnings. Check the India Meteorological Department: mausam.imd.gov.in",
                "मौसम डेटा: Open-Meteo.com। ये अनुमान हैं, सरकारी चेतावनी नहीं। भारतीय मौसम विज्ञान विभाग देखें: mausam.imd.gov.in"),
    "wx_clear": ("Clear sky", "साफ़ आसमान"), "wx_cloudy": ("Cloudy", "बादल"), "wx_fog": ("Fog", "कोहरा"),
    "wx_drizzle": ("Drizzle", "बूँदाबाँदी"), "wx_rain": ("Rain", "बारिश"), "wx_snow": ("Snow", "बर्फ़बारी"),
    "wx_showers": ("Rain showers", "बौछारें"), "wx_storm": ("Thunderstorm", "गरज के साथ बारिश"),
    "r_none": ("No or very light rain", "बारिश नहीं या बहुत हल्की"), "r_light": ("Light", "हल्की"),
    "r_mod": ("Moderate", "मध्यम"), "r_heavy": ("Heavy", "भारी"),
    "r_vheavy": ("Very heavy", "बहुत भारी"), "r_xheavy": ("Extremely heavy", "अत्यंत भारी"),
    # relief team
    "t_name": ("Team member name", "टीम सदस्य का नाम"), "t_pass": ("Password", "पासवर्ड"),
    "t_login": ("Log in", "लॉग इन"), "t_bad": ("Wrong name or password", "नाम या पासवर्ड ग़लत है"),
    "t_hello": ("Logged in as {name}", "{name} के रूप में लॉग इन"), "t_logout": ("Log out", "लॉग आउट"),
    "t_dup": ("Duplicate window (hours)", "दोहराए अनुरोध की सीमा (घंटे)"),
    "t_ttl": ("Request expires after (hours)", "अनुरोध इतने घंटे बाद पुराना"),
    "t_hidden": ("Hidden: {d} duplicate, {o} outdated", "छिपे: {d} दोहराए, {o} पुराने"),
    "t_areas": ("Most urgent areas", "सबसे ज़रूरी इलाके"),
    "t_queue": ("Requests, most urgent first", "अनुरोध, सबसे ज़रूरी पहले"),
    "t_review": ("New reports to review", "जाँच के लिए नई रिपोर्ट"),
    "t_empty": ("Nothing here", "यहाँ कुछ नहीं"),
    "t_requests": ("Requests", "अनुरोध"), "t_top": ("Top priority", "सर्वोच्च प्राथमिकता"),
    "b_verify": ("✅ Verify", "✅ जाँचा"), "b_done": ("✔ Done", "✔ पूरा हुआ"), "b_hide": ("🚫 Hide", "🚫 हटाएँ"),
    "priority": ("Priority", "प्राथमिकता"), "matches": ("Help available nearby", "पास में उपलब्ध मदद"),
}

lang = st.radio("Language", LANGS, horizontal=True, label_visibility="collapsed")


def t(key):
    v = S[key]
    i = LANGS.index(lang)
    return v[i] if i < len(v) else v[0]


def esc(s):  # stop user text from becoming markdown (links, bold, ...)
    return re.sub(r"([!-/:-@\[-`{-~])", r"\\\1", str(s))


# ---------- database (SQLite, one file)
SCHEMA = """CREATE TABLE IF NOT EXISTS reports(
  id INTEGER PRIMARY KEY AUTOINCREMENT, time TEXT, kind TEXT, disaster TEXT, state TEXT, district TEXT,
  place TEXT, lat REAL, lon REAL, need TEXT, people INTEGER, severity INTEGER, vulnerable INTEGER,
  phone TEXT, details TEXT, image BLOB, status TEXT DEFAULT 'open', verified_by TEXT)"""


def run(sql, args=()):
    con = sqlite3.connect(DB, timeout=10)
    try:
        with con:
            con.execute(sql, args)
    finally:
        con.close()


def query(sql, args=()):
    con = sqlite3.connect(DB, timeout=10)
    try:
        return pd.read_sql_query(sql, con, params=args)
    finally:
        con.close()


@st.cache_resource
def init():
    run(SCHEMA)


def load():
    df = query("""SELECT id, time, kind, disaster, state, district, place, lat, lon, need, people, severity,
                  vulnerable, phone, details, status, verified_by, image IS NOT NULL AS has_image
                  FROM reports ORDER BY time DESC""")
    df["time"] = pd.to_datetime(df["time"], utc=True)
    df["vulnerable"] = df["vulnerable"].astype(bool)
    return df.fillna({"district": "", "need": "", "details": "", "phone": "", "verified_by": ""})


@st.cache_data(ttl=300, max_entries=50, show_spinner=False)
def get_image(report_id):
    return query("SELECT image FROM reports WHERE id = ?", (int(report_id),)).iloc[0, 0]


def compress(f):  # shrink for slow networks; re-saving also removes hidden photo metadata
    img = ImageOps.exif_transpose(Image.open(f)).convert("RGB")
    img.thumbnail((1000, 1000))
    out = io.BytesIO()
    img.save(out, "JPEG", quality=80)
    return out.getvalue()


def act(report_id, what):  # team buttons
    if what == "verify":
        run("UPDATE reports SET verified_by = ? WHERE id = ?", (st.session_state.team_user, int(report_id)))
    else:
        run("UPDATE reports SET status = ? WHERE id = ?", ("fulfilled" if what == "done" else "hidden", int(report_id)))


def ist(ts):
    return (ts + pd.Timedelta("5h30min")).strftime("%d %b, %I:%M %p")


# ---------- location + weather (Open-Meteo: free, no key, non-commercial use)
@st.cache_data(ttl=86400, show_spinner=False)
def geocode(name, state=""):  # raises on network errors so failures are not cached
    r = requests.get("https://geocoding-api.open-meteo.com/v1/search",
                     params={"name": name, "count": 10, "countryCode": "IN"}, timeout=8)
    r.raise_for_status()
    results = r.json().get("results") or []
    if state:
        results = [x for x in results if state.lower() in (x.get("admin1") or "").lower()]
    return results[0] if results else None


def place_to_xy(place, district, state):
    for name in (place, district):
        if name:
            try:
                g = geocode(name, state)
            except Exception:
                return None, None
            if g:
                return g["latitude"], g["longitude"]
    return None, None


@st.cache_data(ttl=600, show_spinner=False)
def weather(lat, lon):
    r = requests.get("https://api.open-meteo.com/v1/forecast", timeout=8, params={
        "latitude": lat, "longitude": lon, "timezone": "Asia/Kolkata", "forecast_days": 4,
        "current": "temperature_2m,relative_humidity_2m,precipitation,weather_code,wind_speed_10m",
        "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_sum"})
    r.raise_for_status()
    return r.json()


def sky(code):
    for limit, key in [(0, "clear"), (3, "cloudy"), (48, "fog"), (57, "drizzle"), (67, "rain"),
                       (77, "snow"), (82, "showers"), (86, "snow")]:
        if code <= limit:
            return t("wx_" + key)
    return t("wx_storm")


def rain_level(mm):  # India Meteorological Department 24-hour rainfall classes
    for limit, key in [(2.4, "r_none"), (15.5, "r_light"), (64.4, "r_mod"), (115.5, "r_heavy"), (204.4, "r_vheavy")]:
        if mm <= limit:
            return t(key)
    return t("r_xheavy")


# ---------- one report card (public feed and team view)
def card(r, team=False, note=""):
    with st.container(border=True):
        tag = f" · {t('verified')}" if r.verified_by else ""
        st.markdown(f"**{ICON[r.kind]} {esc(r.place)}, {esc(r.district)} {esc(r.state)}**{tag}")
        line = f"{t('dis_' + r.disaster)} · {ist(r.time)} IST"
        if r.kind != "update":
            line += f" · {t('need_' + r.need)} · {r.people} {t('people_unit')}"
        if r.status == "fulfilled":
            line += f" · ✔ {t('done')}"
        st.caption(line)
        if r.details:
            st.markdown(esc(r.details))
        if r.has_image and (team or r.verified_by or not PUBLIC_IMAGES_NEED_VERIFY):
            st.image(get_image(r.id))
        if team:
            if note:
                st.markdown(note)
            if r.phone:
                st.markdown(f"📞 {esc(r.phone)}")
            b = st.columns(3)
            b[0].button(t("b_verify"), key=f"v{r.id}", on_click=act, args=(r.id, "verify"))
            b[1].button(t("b_done"), key=f"d{r.id}", on_click=act, args=(r.id, "done"))
            b[2].button(t("b_hide"), key=f"h{r.id}", on_click=act, args=(r.id, "hide"))


@st.fragment(run_every="30s")
def live():
    df = load()
    df = df[df["status"] != "hidden"]
    if df.empty:
        st.info(t("none_yet"))
        return
    all_states = t("all_states")
    pick = st.selectbox(t("state"), [all_states] + sorted(df["state"].unique()))
    view = df if pick == all_states else df[df["state"] == pick]
    open_ = view[view["status"] == "open"]

    c = st.columns(4)
    c[0].metric(t("m_need"), int((open_["kind"] == "need").sum()))
    c[1].metric(t("m_update"), int((open_["kind"] == "update").sum()))
    c[2].metric(t("m_offer"), int((open_["kind"] == "offer").sum()))
    c[3].metric(t("m_done"), int(((view["kind"] == "need") & (view["status"] == "fulfilled")).sum()))

    pts = open_.dropna(subset=["lat", "lon"])
    if len(pts):
        st.map(pts.assign(color=pts["kind"].map(COLOR)), latitude="lat", longitude="lon", color="color")
    st.caption(t("auto"))
    for r in open_.head(20).itertuples():
        card(r)


def team():
    if "team_user" not in st.session_state:
        name = st.text_input(t("t_name"))
        pw = st.text_input(t("t_pass"), type="password")
        if st.button(t("t_login")):
            if name in TEAM_USERS and hmac.compare_digest(pw.encode(), TEAM_USERS[name].encode()):
                st.session_state.team_user = name
                st.rerun()
            else:
                st.error(t("t_bad"))
        return
    st.caption(t("t_hello").format(name=st.session_state.team_user))
    st.button(t("t_logout"), on_click=lambda: st.session_state.pop("team_user"))

    df = load()
    df = df[df["status"] != "hidden"]
    offers = df[(df["kind"] == "offer") & (df["status"] == "open")]
    n = df[(df["kind"] == "need") & (df["status"] == "open")].sort_values("time").copy()

    if n.empty:
        st.info(t("t_empty"))
    else:
        a, b = st.columns(2)
        dup_h = a.slider(t("t_dup"), 1, 24, 6)
        ttl_h = b.slider(t("t_ttl"), 6, 96, 48)
        n["age_h"] = (pd.Timestamp.now(tz="UTC") - n["time"]).dt.total_seconds() / 3600

        # duplicate = a newer request with the same phone (or same row if no phone), place and need
        key = n["phone"].where(n["phone"] != "", n["time"].astype(str)) + n["place"].str.lower().str.strip() + n["need"]
        gap = (n.groupby(key)["time"].shift(-1) - n["time"]).dt.total_seconds() / 3600
        dup, old = gap <= dup_h, n["age_h"] > ttl_h
        n = n[~dup & ~old].copy()
        st.caption(t("t_hidden").format(d=int(dup.sum()), o=int((old & ~dup).sum())))

        n["priority"] = (100 * (0.35 * (n["severity"] - 1) / 4
                                + 0.25 * (np.log1p(n["people"]) / np.log1p(150)).clip(upper=1)
                                + 0.15 * n["vulnerable"]
                                + 0.15 * (n["age_h"] / ttl_h).clip(upper=1)
                                + 0.10 * n["need"].map(NEED_WEIGHT))).round()
        n = n.sort_values("priority", ascending=False)

        if len(n):
            st.subheader(t("t_areas"))
            areas = n.groupby(["state", "district"]).agg(r=("kind", "size"), p=("people", "sum"), top=("priority", "max"))
            st.dataframe(areas.sort_values("top", ascending=False).reset_index().rename(
                columns={"state": t("state"), "district": t("district"), "r": t("t_requests"),
                         "p": t("people_unit"), "top": t("t_top")}), hide_index=True)
            st.subheader(t("t_queue"))
            for r in n.head(15).itertuples():
                m = offers[(offers["need"] == r.need) & (offers["state"] == r.state)
                           & (offers["district"].str.lower() == r.district.lower())]
                note = f"⭐ {t('priority')}: **{r.priority:.0f}**"
                if len(m):
                    note += f"  \n🤝 {t('matches')}: " + ", ".join(f"{esc(o.place)} {esc(o.phone)}" for o in m.itertuples())
                card(r, team=True, note=note)

    st.subheader(t("t_review"))
    review = df[(df["kind"] != "need") & (df["status"] == "open") & (df["verified_by"] == "")]
    if review.empty:
        st.info(t("t_empty"))
    for r in review.head(15).itertuples():
        card(r, team=True)


# ---------- page
init()
st.title("🌊 " + t("title"))
st.caption("☎️ " + t("emergency"))

tab_report, tab_live, tab_wx, tab_team, tab_allocate = st.tabs(
    [
        t("tab_report"),
        t("tab_live"),
        t("tab_wx"),
        t("tab_team"),
        "🤖 AI Allocation",
    ]
)


with tab_report:
    kind = st.radio(t("what"), list(ICON), format_func=lambda k: f"{ICON[k]} {t('kind_' + k)}")
    gps = None
    if streamlit_geolocation:
        slot = st.empty()
        try:  # if this extra button cannot load, the rest of the site still works
            with slot.container():
                st.caption(t("gps_hint"))
                g = streamlit_geolocation()
        except Exception:
            slot.empty()
            g = None
        if g and g.get("latitude") is not None:
            gps = (g["latitude"], g["longitude"])
            st.success(t("gps_ok"))

    with st.form("report"):
        disaster = st.selectbox(t("disaster"), DISASTERS, format_func=lambda k: t("dis_" + k))
        state = st.selectbox(t("state"), STATES, index=None, placeholder=t("choose"))
        district = st.text_input(t("district"))
        place = st.text_input(t("place"))
        need, people, severity, vulnerable = "", 0, 1, False
        if kind != "update":
            need = st.selectbox(t("need_q") if kind == "need" else t("give_q"), list(NEED_WEIGHT),
                                format_func=lambda k: t("need_" + k))
            people = st.number_input(t("people"), 1, 100000, 10)
        if kind == "need":
            severity = st.slider(t("serious"), 1, 5, 3)
            vulnerable = st.checkbox(t("vuln"))
        details = st.text_area(t("details"))
        photo = st.file_uploader(t("photo"), type=["jpg", "jpeg", "png"])
        phone = st.text_input(t("phone"))
        sent = st.form_submit_button(t("submit"), type="primary")

    if sent:
        if not state or not place.strip():
            st.error(t("err_place"))
        elif photo and photo.size > MAX_IMAGE_BYTES:
            st.error(t("big_image"))
        else:
            try:
                img = compress(photo) if photo else None
            except Exception:
                img = False
            if img is False:
                st.error(t("bad_image"))
            else:
                lat, lon = gps or (None, None)
                guessed = lat is None
                if guessed:
                    lat, lon = place_to_xy(place.strip(), district.strip(), state)
                run("""INSERT INTO reports(time, kind, disaster, state, district, place, lat, lon, need, people,
                       severity, vulnerable, phone, details, image) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%d %H:%M:%S"), kind, disaster, state, district.strip(), place.strip(),
                     lat, lon, need, int(people), int(severity), int(vulnerable), phone.strip(), details.strip(), img))
                st.success(t("saved_guess") if guessed and lat is not None else t("saved"))

with tab_live:
    live()

with tab_wx:
    name = lat = lon = None
    q = st.text_input(t("wx_place"), placeholder="Patna, Guwahati, Kochi, Bhubaneswar")
    try:
        if q.strip():
            g = geocode(q.strip())
            if g:
                name, lat, lon = f"{g['name']}, {g.get('admin1', '')}", g["latitude"], g["longitude"]
            else:
                st.info(t("wx_notfound"))
        else:
            known = load()
            known = known[(known["status"] != "hidden")].dropna(subset=["lat", "lon"])
            if len(known):
                r = known.iloc[0]
                name, lat, lon = f"{r['place']}, {r['state']}", r["lat"], r["lon"]
                st.caption(t("wx_default"))
        if lat is not None:
            w = weather(round(float(lat), 2), round(float(lon), 2))
            cur, d = w["current"], w["daily"]
            st.subheader(name)
            c = st.columns(4)
            c[0].metric(t("temp"), f"{cur['temperature_2m']:.0f} °C")
            c[1].metric(t("rain_now"), f"{cur['precipitation']} mm")
            c[2].metric(t("humid"), f"{cur['relative_humidity_2m']}%")
            c[3].metric(t("wind"), f"{cur['wind_speed_10m']:.0f} km/h")
            st.write(sky(cur["weather_code"]))
            for day, mm in zip(d["time"][:3], d["precipitation_sum"][:3]):
                if (mm or 0) >= 64.5:
                    st.warning(t("wx_heavy").format(day=pd.Timestamp(day).strftime("%a %d %b")))
                    break
            st.dataframe(pd.DataFrame([
                {t("day"): pd.Timestamp(day).strftime("%a %d %b"), t("sky"): sky(code),
                 t("rain"): f"{(mm or 0):.0f} mm · {rain_level(mm or 0)}", t("temp"): f"{lo:.0f}–{hi:.0f} °C"}
                for day, code, mm, lo, hi in zip(d["time"], d["weather_code"], d["precipitation_sum"],
                                                  d["temperature_2m_min"], d["temperature_2m_max"])]), hide_index=True)
            st.caption(t("wx_note"))
    except Exception:
        st.warning(t("wx_fail"))

with tab_team:
    team()


# ---------- AI Resource Allocation

with tab_allocate:
    st.header("🤖 AI Resource Allocation")
    st.caption(
        "Explore flood-affected villages and optimize food and water distribution."
    )

    # Load Person 3's sample scenario
    try:
        villages = load_villages()
        inventory = load_inventory()
    except Exception as error:
        st.error(f"Could not load scenario data: {error}")
        st.stop()

    # Let the user adjust each village's urgency
    st.subheader("🚨 Village Urgency Controls")
    display_villages = []

    for village in villages:
        village_copy = village.copy()
        village_id = village["id"]
        slider_key = f"rf_urgency_{village_id}"

        if slider_key not in st.session_state:
            st.session_state[slider_key] = int(village["urgency"])

        village_copy["urgency"] = st.slider(
            f"{village['name']} — urgency (1 = low, 5 = critical)",
            min_value=1,
            max_value=5,
            key=slider_key,
        )
        display_villages.append(village_copy)

    # Display Person 3's map using the current urgency values
    st.subheader("🗺️ Flood-Affected Villages")
    st_folium(
        create_flood_map(display_villages),
        width=None,
        height=450,
        key="reliefflow_integrated_map",
    )

    # Show available stock
    st.subheader("📦 Available Inventory")
    food_col, water_col, medical_col = st.columns(3)
    food_col.metric("Food", f"{inventory['food']:,}")
    water_col.metric("Water", f"{inventory['water']:,}")
    medical_col.metric("Medical kits", f"{inventory['medical_kits']:,}")

    st.caption(
        "These are simulated demonstration quantities, not live stock reports."
    )

    # Optimize using the latest urgency selections
    if st.button("Run AI Allocation", type="primary"):
        payload = {
            "locations": display_villages,
            "inventory": {
                "food": inventory["food"],
                "water": inventory["water"],
            },
        }

        try:
            response = requests.post(
                "http://127.0.0.1:8000/allocate",
                json=payload,
                timeout=15,
            )
            response.raise_for_status()
            result = response.json()
            st.session_state["reliefflow_allocation"] = result
            st.session_state["reliefflow_used_urgencies"] = {
                village["id"]: village["urgency"]
                for village in display_villages
            }
        except requests.RequestException as error:
            st.error(f"Allocation request failed: {error}")

    result = st.session_state.get("reliefflow_allocation")

    if result:
        used_urgencies = st.session_state.get(
            "reliefflow_used_urgencies", {}
        )

        # Warn if sliders have changed since the last calculation
        if any(
            used_urgencies.get(village["id"]) != village["urgency"]
            for village in display_villages
        ):
            st.info("Urgency changed. Run AI Allocation again to refresh results.")

        allocations = result.get("allocations", [])
        remaining = result.get("remaining_inventory", {})

        st.subheader("📊 Allocation Summary")
        food_sent = sum(
            row["food_allocated"] for row in allocations
        )
        water_sent = sum(
            row["water_allocated"] for row in allocations
        )

        c1, c2 = st.columns(2)
        c1.metric("Food allocated", f"{food_sent:,}")
        c2.metric("Water allocated", f"{water_sent:,}")

        c1, c2 = st.columns(2)
        c1.metric(
            "Food unmet",
            f"{sum(row['food_unmet'] for row in allocations):,}",
        )
        c2.metric(
            "Water unmet",
            f"{sum(row['water_unmet'] for row in allocations):,}",
        )

        st.subheader("🏘️ Village-wise Allocation")
        if allocations:
            st.dataframe(
                pd.DataFrame(allocations),
                use_container_width=True,
                hide_index=True,
            )

        st.subheader("📦 Remaining Inventory")
        c1, c2 = st.columns(2)
        c1.metric("Food remaining", f"{remaining.get('food', 0):,}")
        c2.metric("Water remaining", f"{remaining.get('water', 0):,}")

        st.caption(
            "The current optimizer allocates food and water only. "
            "Medical kits are displayed but are not yet optimized."
        )
