import html
import colorsys

import streamlit as st
import geopandas as gpd
import pandas as pd
import plotly.express as px
import folium

from pathlib import Path
from streamlit_folium import st_folium


# 1. PAGE CONFIGURATION
st.set_page_config(
    page_title="Kaduna Geological Web GIS",
    page_icon="🌍",
    layout="wide",
)
st.title("Kaduna Sheet 123 Geological Web GIS")
st.caption("Interactive Geological Database and Spatial Data Dashboard")


# 2. PROJECT PATHS
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR

LAYER_FILES = {
    "Lithologies": DATA_DIR / "Lithologies.geojson",
    "Mining Sites": DATA_DIR / "Mining_Site.geojson",
    "Roads": DATA_DIR / "Roads.geojson",
    "Settlements": DATA_DIR / "Settlements.geojson",
    # Add other exported GeoJSON layers here when ready:
    # "Pegmatites": DATA_DIR / "Pegmatites.geojson",
    # "Rivers and Streams": DATA_DIR / "Rivers_Streams.geojson",
}


# 3. LOAD AND VALIDATE GEOJSON DATA
@st.cache_data(show_spinner="Loading geological data...")
def load_layer(file_path_string: str) -> gpd.GeoDataFrame:
    file_path = Path(file_path_string)
    gdf = gpd.read_file(file_path)

    if gdf.empty:
        raise ValueError(f"No features found in {file_path.name}.")

    if gdf.crs is None:
        raise ValueError(
            f"{file_path.name} has no defined CRS. "
            "Check its CRS in QGIS before displaying it."
        )

    if gdf.crs.to_epsg() != 4326:
        gdf = gdf.to_crs(epsg=4326)

    gdf = gdf.loc[
        gdf.geometry.notna() & ~gdf.geometry.is_empty
    ].copy()

    if gdf.empty:
        raise ValueError(
            f"{file_path.name} contains no usable geometries."
        )

    invalid_count = int((~gdf.geometry.is_valid).sum())
    if invalid_count:
        st.warning(
            f"{file_path.name} contains {invalid_count} invalid geometries. "
            "Review and repair them in QGIS if necessary."
        )

    return gdf


layers = {}
layer_errors = {}

for layer_name, file_path in LAYER_FILES.items():
    if not file_path.exists():
        layer_errors[layer_name] = (
            f"File not found: {file_path}. "
            "Check the filename and ensure it is inside the project folder."
        )
        continue

    try:
        layers[layer_name] = load_layer(str(file_path))
    except Exception as error:
        layer_errors[layer_name] = str(error)

if layer_errors:
    with st.expander("Data loading messages", expanded=True):
        for layer_name, message in layer_errors.items():
            st.error(f"{layer_name}: {message}")

if not layers:
    st.error(
        "No layers could be loaded. Check the GeoJSON filenames, "
        "project folder, and each layer's CRS in QGIS."
    )
    st.stop()


# 4. DASHBOARD METRICS
total_features = sum(len(gdf) for gdf in layers.values())

col1, col2, col3 = st.columns(3)
col1.metric("Loaded Layers", len(layers))
col2.metric("Total Features", f"{total_features:,}")

if "Lithologies" in layers:
    col3.metric("Lithology Features", f"{len(layers['Lithologies']):,}")
else:
    col3.metric("Lithology Features", "Unavailable")

st.divider()


# 5. SIDEBAR LAYER CONTROLS
st.sidebar.header("Map Layer Controls")

visible_layers = {}
for layer_name in layers:
    visible_layers[layer_name] = st.sidebar.checkbox(
        layer_name,
        value=True,
        key=f"show_layer_{layer_name}",
    )


# 6. CREATE A UNIQUE, REPEATABLE COLOUR FOR EACH LITHOLOGY UNIT
lithology_field = None
lithology_color_map = {}

if "Lithologies" in layers:
    lithology_gdf = layers["Lithologies"]

    accepted_field_names = {
        "lithology",
        "lithologies",
        "rock_type",
        "rocktype",
    }

    lithology_field = next(
        (
            column
            for column in lithology_gdf.columns
            if column != lithology_gdf.geometry.name
            and column.strip().lower() in accepted_field_names
        ),
        None,
    )

    if lithology_field is not None:
        lithology_values = (
            lithology_gdf[lithology_field]
            .fillna("Unclassified")
            .astype(str)
            .str.strip()
            .replace("", "Unclassified")
        )

        lithology_units = sorted(
            lithology_values.unique(),
            key=str.casefold,
        )

        # HSV colour generation gives each category a distinct hue.
        # It also works when the dataset contains more than 15 units.
        number_of_units = max(len(lithology_units), 1)

        for index, unit in enumerate(lithology_units):
            hue = (index / number_of_units + 0.025) % 1.0
            red, green, blue = colorsys.hsv_to_rgb(hue, 0.62, 0.88)
            lithology_color_map[unit] = (
                f"#{round(red * 255):02x}"
                f"{round(green * 255):02x}"
                f"{round(blue * 255):02x}"
            )
    else:
        st.warning(
            "The Lithologies layer was loaded, but no lithology attribute "
            "field was detected. Expected a field such as 'Lithology'."
        )


def get_lithology_colour(feature):
    """Return the colour assigned to the feature's lithology category."""
    if lithology_field is None:
        return "#999999"

    properties = feature.get("properties", {})
    raw_value = properties.get(lithology_field)

    if raw_value is None:
        unit = "Unclassified"
    else:
        unit = str(raw_value).strip() or "Unclassified"

    return lithology_color_map.get(unit, "#999999")


# 7. CREATE INTERACTIVE MAP
all_bounds = gpd.GeoDataFrame(
    geometry=pd.concat(
        [gdf.geometry for gdf in layers.values()],
        ignore_index=True,
    ),
    crs="EPSG:4326",
).total_bounds

minx, miny, maxx, maxy = all_bounds

if not all(pd.notna(value) for value in all_bounds):
    center_lat, center_lon = 10.5, 7.5
else:
    center_lat = (miny + maxy) / 2
    center_lon = (minx + maxx) / 2

m = folium.Map(
    location=[center_lat, center_lon],
    zoom_start=9,
    tiles="OpenStreetMap",
)

layer_styles = {
    "Lithologies": {
        "color": "#d95f02",
        "fillColor": "#fdb863",
        "weight": 1,
        "fillOpacity": 0.65,
    },
    "Mining Sites": {
        "color": "#b30000",
        "fillColor": "#e31a1c",
        "radius": 6,
    },
    "Roads": {
        "color": "#303030",
        "weight": 2,
    },
    "Settlements": {
        "color": "#2166ac",
        "fillColor": "#4393c3",
        "radius": 5,
    },
}

for layer_name, gdf in layers.items():
    if not visible_layers.get(layer_name, False):
        continue

    style = layer_styles.get(layer_name, {})
    attribute_fields = [
        column
        for column in gdf.columns
        if column != gdf.geometry.name
    ][:5]

    tooltip = (
        folium.GeoJsonTooltip(fields=attribute_fields, sticky=True)
        if attribute_fields
        else None
    )

    if layer_name in {"Mining Sites", "Settlements"}:
        folium.GeoJson(
            data=gdf.to_json(),
            name=layer_name,
            marker=folium.CircleMarker(
                radius=style.get("radius", 5),
                color=style.get("color", "#333333"),
                fill=True,
                fill_color=style.get("fillColor", "#777777"),
                fill_opacity=0.9,
            ),
            tooltip=tooltip,
        ).add_to(m)

    elif layer_name == "Lithologies":
        folium.GeoJson(
            data=gdf.to_json(),
            name=layer_name,
            style_function=lambda feature: {
                "color": get_lithology_colour(feature),
                "fillColor": get_lithology_colour(feature),
                "weight": 1,
                "fillOpacity": 0.65,
            },
            tooltip=tooltip,
        ).add_to(m)

    else:
        folium.GeoJson(
            data=gdf.to_json(),
            name=layer_name,
            style_function=lambda feature, current_style=style: {
                key: current_style[key]
                for key in (
                    "color",
                    "fillColor",
                    "weight",
                    "fillOpacity",
                )
                if key in current_style
            },
            tooltip=tooltip,
        ).add_to(m)

folium.LayerControl(collapsed=False).add_to(m)

if all(pd.notna(value) for value in all_bounds):
    if minx != maxx and miny != maxy:
        m.fit_bounds([[miny, minx], [maxy, maxx]])
    else:
        m.location = [center_lat, center_lon]
        m.zoom_start = 12


# 8. DISPLAY INTERACTIVE MAP
st.subheader("Interactive Geological Map")
st.caption(
    "Click anywhere on the map to obtain the geographic coordinates "
    "of that location."
)

map_output = st_folium(
    m,
    width=None,
    height=600,
    use_container_width=True,
    returned_objects=[
        "last_clicked",
        "last_object_clicked",
    ],
)


# 9. GEOLOGICAL LEGEND - DIRECTLY BELOW THE MAP
if lithology_color_map:
    st.subheader("Geological Map Legend")
    st.caption(
        "Each colour represents a different lithological unit shown on the map."
    )

    legend_columns = st.columns(3)

    for index, (unit, colour) in enumerate(lithology_color_map.items()):
        safe_unit = html.escape(str(unit))
        column = legend_columns[index % len(legend_columns)]

        column.markdown(
            f""" <div style=" display: flex; align-items: center; gap: 9px; min-height: 32px; margin-bottom: 8px; "> <span style=" display: inline-block; width: 19px; height: 19px; min-width: 19px; background-color: {colour}; border: 1px solid #333333; border-radius: 3px; "></span> <span style="font-size: 14px;">{safe_unit}</span> </div> """,
            unsafe_allow_html=True,
        )

st.divider()


# 10. DISPLAY COORDINATES OF THE CLICKED LOCATION
clicked_point = map_output.get("last_clicked") if map_output else None

if clicked_point:
    latitude = clicked_point.get("lat")
    longitude = clicked_point.get("lng")

    if latitude is not None and longitude is not None:
        st.success("Location Coordinates")

        col1, col2 = st.columns(2)
        col1.metric("Latitude", f"{latitude:.6f}°")
        col2.metric("Longitude", f"{longitude:.6f}°")

        st.code(
            f"Latitude: {latitude:.6f}\n"
            f"Longitude: {longitude:.6f}"
        )

        st.caption("Coordinate Reference System: WGS 84 (EPSG:4326)")

    clicked_object = map_output.get("last_object_clicked")

    if clicked_object:
        st.subheader("Feature Information")
        st.json(clicked_object)
    else:
        st.info(
            "Coordinates received. Click directly on a mapped "
            "feature to try to retrieve its attributes."
        )


# 11. FEATURE COUNTS
st.subheader("Feature Summary")

summary_df = pd.DataFrame(
    [
        {
            "Layer": name,
            "Feature Count": len(gdf),
            "Geometry Type": ", ".join(
                sorted(gdf.geom_type.dropna().unique())
            ) or "Unknown",
        }
        for name, gdf in layers.items()
    ]
)

st.dataframe(
    summary_df,
    use_container_width=True,
    hide_index=True,
)


# 12. LITHOLOGY DISTRIBUTION
if "Lithologies" in layers and lithology_field is not None:
    lithologies = layers["Lithologies"]
    st.subheader("Lithology Distribution")

    lithology_counts = (
        lithologies[lithology_field]
        .fillna("Unclassified")
        .astype(str)
        .str.strip()
        .replace("", "Unclassified")
        .value_counts()
        .rename_axis("Lithology")
        .reset_index(name="Feature Count")
    )

    fig = px.bar(
        lithology_counts,
        x="Lithology",
        y="Feature Count",
        title="Number of Mapped Features by Lithology",
        labels={
            "Lithology": "Lithology Type",
            "Feature Count": "Number of Features",
        },
    )
    fig.update_layout(xaxis_tickangle=-30)

    st.plotly_chart(fig, use_container_width=True)
    st.dataframe(
        lithology_counts,
        use_container_width=True,
        hide_index=True,
    )


# 13. DATA INFORMATION
with st.expander("Layer Attribute Information"):
    for layer_name, gdf in layers.items():
        st.markdown(f"*{layer_name}*")

        fields = [
            column
            for column in gdf.columns
            if column != gdf.geometry.name
        ]
        st.write("Fields:", fields)

        st.dataframe(
            gdf.drop(columns=gdf.geometry.name).head(10),
            use_container_width=True,
            hide_index=True,
        )

st.divider()
st.caption(
    "Prototype Web GIS | Source data, licensing, and positional accuracy "
    "should be verified before authoritative use."
)
