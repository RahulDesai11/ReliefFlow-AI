import json
from pathlib import Path

import folium
import streamlit as st
from streamlit_folium import st_folium

# 1. PROJECT PATHS

BASE_DIR = Path(__file__).resolve().parent.parent

VILLAGE_FILES = [
    BASE_DIR / "Data" / "villages.json",
    BASE_DIR / "data" / "villages.json",
]

INVENTORY_FILES = [
    BASE_DIR / "Data" / "Inventory.json",
    BASE_DIR / "data" / "inventory.json",
]


def find_file(paths):
    for path in paths:
        if path.is_file():
            return path
    return None


# 2. LOAD VILLAGE DATA

def load_villages():
    data_file = find_file(VILLAGE_FILES)

    if data_file is None:
        st.error("Village data file was not found.")
        st.write("Expected location:")
        for path in VILLAGE_FILES:
            st.code(str(path))
        st.stop()

    try:
        with data_file.open("r", encoding="utf-8") as file:
            villages = json.load(file)
    except json.JSONDecodeError as error:
        st.error(f"Invalid JSON in villages.json: {error}")
        st.stop()

    if not isinstance(villages, list) or not villages:
        st.error("villages.json must contain a non-empty list.")
        st.stop()

    required_fields = [
        "id",
        "name",
        "latitude",
        "longitude",
        "people_affected",
        "urgency",
    ]

    for index, village in enumerate(villages):
        missing = [
            field for field in required_fields
            if field not in village
        ]

        if missing:
            st.error(
                f"Village entry {index + 1} is missing fields: "
                + ", ".join(missing)
            )
            st.stop()

        try:
            latitude = float(village["latitude"])
            longitude = float(village["longitude"])
            urgency = int(village["urgency"])
            affected = int(village["people_affected"])

            if not -90 <= latitude <= 90:
                raise ValueError("Latitude must be between -90 and 90.")

            if not -180 <= longitude <= 180:
                raise ValueError("Longitude must be between -180 and 180.")

            if not 1 <= urgency <= 5:
                raise ValueError("Urgency must be between 1 and 5.")

            if affected < 0:
                raise ValueError("People affected cannot be negative.")

        except (TypeError, ValueError) as error:
            st.error(f"Invalid data for {village['name']}: {error}")
            st.stop()

    return villages


# 3. LOAD EMERGENCY INVENTORY

def load_inventory():
    inventory_file = find_file(INVENTORY_FILES)

    if inventory_file is None:
        st.error("Inventory.json was not found.")
        st.write("Expected location:")
        for path in INVENTORY_FILES:
            st.code(str(path))
        st.stop()

    try:
        with inventory_file.open("r", encoding="utf-8") as file:
            inventory = json.load(file)
    except json.JSONDecodeError as error:
        st.error(f"Invalid JSON in Inventory.json: {error}")
        st.stop()

    required_items = ["food", "water", "medical_kits"]

    for item in required_items:
        if item not in inventory:
            st.error(f"Inventory.json is missing '{item}'.")
            st.stop()

        if (
                not isinstance(inventory[item], (int, float))
                or isinstance(inventory[item], bool)
                or inventory[item] < 0
        ):
            st.error(f"Inventory quantity for '{item}' must be non-negative.")
            st.stop()

    return inventory


# 4. MAP MARKER COLORS

def urgency_color(urgency):
    if urgency >= 5:
        return "red"
    elif urgency >= 3:
        return "orange"
    return "green"


# ==========================================
# 5. CREATE FLOOD MAP
# ==========================================

def create_flood_map(villages):
    if villages:
        center_lat = sum(
            float(v["latitude"]) for v in villages
        ) / len(villages)

        center_lon = sum(
            float(v["longitude"]) for v in villages
        ) / len(villages)
    else:
        center_lat, center_lon = 21.20, 81.35

    flood_map = folium.Map(
        location=[center_lat, center_lon],
        zoom_start=11,
        tiles="OpenStreetMap",
    )

    for village in villages:
        urgency = int(village["urgency"])

        popup_html = f"""
        <div style="width: 210px">
            <h4>{village['name']}</h4>
            <b>Village ID:</b> {village['id']}<br>
            <b>People affected:</b> {village['people_affected']}<br>
            <b>Urgency:</b> {urgency}/5<br>
            <b>Food needed:</b> {village.get('food_needed', 0)}<br>
            <b>Water needed:</b> {village.get('water_needed', 0)}<br>
            <b>Medical kits needed:</b>
            {village.get('medical_kits_needed', 0)}
        </div>
        """

        folium.Marker(
            location=[
                float(village["latitude"]),
                float(village["longitude"]),
            ],
            tooltip=f"{village['name']} - Urgency {urgency}/5",
            popup=folium.Popup(popup_html, max_width=300),
            icon=folium.Icon(
                color=urgency_color(urgency),
                icon="info-sign",
            ),
        ).add_to(flood_map)

    return flood_map


# 6. MAIN DASHBOARD

def main():
    st.set_page_config(
        page_title="ReliefFlow AI",
        page_icon="🌊",
        layout="wide",
    )

    st.title("🌊 ReliefFlow AI")
    st.subheader("Emergency Supply Planning Dashboard")

    st.write(
        "Monitor simulated flood-affected villages, "
        "adjust urgency, and review available relief supplies."
    )

    st.warning(
        "Hackathon demo: village locations, affected populations, "
        "and inventory quantities are simulated, not live disaster data."
    )

    # Load data
    villages = load_villages()
    inventory = load_inventory()

    # Sidebar: interactive scenario controls

    st.sidebar.title("⚙️ Scenario Controls")

    if "village_urgencies" not in st.session_state:
        st.session_state.village_urgencies = {
            village["id"]: int(village["urgency"])
            for village in villages
        }

    village_options = {
        village["id"]: village["name"]
        for village in villages
    }

    selected_id = st.sidebar.selectbox(
        "Select a village",
        options=list(village_options.keys()),
        format_func=lambda village_id: village_options[village_id],
    )

    new_urgency = st.sidebar.slider(
        "Set urgency level",
        min_value=1,
        max_value=5,
        value=st.session_state.village_urgencies[selected_id],
        key=f"urgency_{selected_id}",
        help="1 = lower urgency; 5 = highest urgency.",
    )

    st.session_state.village_urgencies[selected_id] = new_urgency

    st.sidebar.markdown("### Map Legend")
    st.sidebar.markdown("🔴 **Red:** Urgency 5")
    st.sidebar.markdown("🟠 **Orange:** Urgency 3–4")
    st.sidebar.markdown("🟢 **Green:** Urgency 1–2")

    if st.sidebar.button("Reset all urgency levels"):
        for village in villages:
            st.session_state.village_urgencies[village["id"]] = int(
                village["urgency"]
            )

            slider_key = f"urgency_{village['id']}"
            if slider_key in st.session_state:
                del st.session_state[slider_key]

        st.rerun()

    # Create a display copy. Original JSON is not modified.
    display_villages = []

    for village in villages:
        updated_village = village.copy()
        updated_village["urgency"] = (
            st.session_state.village_urgencies[village["id"]]
        )
        display_villages.append(updated_village)

    # Dashboard summary metrics
    total_affected = sum(
        int(village["people_affected"])
        for village in display_villages
    )

    high_urgency = sum(
        int(village["urgency"]) >= 4
        for village in display_villages
    )

    st.markdown("### 📊 Situation Overview")

    metric1, metric2, metric3 = st.columns(3)

    metric1.metric(
        "Affected People",
        f"{total_affected:,}",
    )

    metric2.metric(
        "Villages Monitored",
        len(display_villages),
    )

    metric3.metric(
        "High-Urgency Villages",
        high_urgency,
    )
    # Emergency inventory cards
    st.markdown("### 📦 Available Emergency Supplies")

    food_col, water_col, medical_col = st.columns(3)

    food_col.metric(
        "Food Available",
        f"{inventory['food']:,}",
    )

    water_col.metric(
        "Water Available",
        f"{inventory['water']:,}",
    )

    medical_col.metric(
        "Medical Kits Available",
        f"{inventory['medical_kits']:,}",
    )

    st.caption(
        "Inventory numbers are simulated demo quantities, "
        "not verified real-world stock.")

    # Map
    st.markdown("### 🗺️ Flood-Affected Villages")

    st_folium(
        create_flood_map(display_villages),
        width=None,
        height=500,
        key="reliefflow_flood_map",
    )

    st.markdown("### 🏘️ Village Demand Details")

    village_rows = []

    for village in display_villages:
        village_rows.append({
            "Village ID": village["id"],
            "Village": village["name"],
            "People Affected": village["people_affected"],
            "Urgency": village["urgency"],
            "Food Needed": village.get("food_needed", 0),
            "Water Needed": village.get("water_needed", 0),
            "Medical Kits Needed": village.get(
                "medical_kits_needed", 0
            ),
        })

    st.dataframe(
        village_rows,
        use_container_width=True,
        hide_index=True,
    )

    st.info(
        "Changing urgency updates this dashboard's simulated scenario only. "
        "It does not yet save changes to JSON or send them to the allocation API."
    )


if __name__ == "__main__":
    main()