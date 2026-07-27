import re
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st


# ============================================================
# PAGE CONFIGURATION
# ============================================================

st.set_page_config(
    page_title="BFT Spring Route Profiles",
    page_icon="🚌",
    layout="wide",
)


# ============================================================
# PAGE STYLING
# ============================================================

st.markdown(
    """
    <style>
        .main-title {
            font-size: 38px;
            font-weight: 800;
            color: #12355B;
            margin-bottom: 2px;
        }
        .sub-title {
            color: #6B7280;
            font-size: 16px;
            margin-bottom: 22px;
        }
        .section-header {
            font-size: 23px;
            font-weight: 750;
            color: #12355B;
            margin-top: 24px;
            margin-bottom: 8px;
        }
        div[data-testid="stMetric"] {
            background-color: #F8FAFC;
            border: 1px solid #E5E7EB;
            padding: 14px;
            border-radius: 10px;
        }
        button[data-baseweb="tab"] {
            font-size: 15px;
            font-weight: 650;
        }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    '<div class="main-title">BFT Spring 2026 Route Profiles</div>',
    unsafe_allow_html=True,
)

st.markdown(
    """
    <div class="sub-title">
        Spring route performance by route, service day, direction, and paired trip.
    </div>
    """,
    unsafe_allow_html=True,
)


# ============================================================
# CONFIGURATION
# ============================================================

APP_FOLDER = Path(__file__).resolve().parent
DATA_FILE_CANDIDATES = [
    APP_FOLDER / "data" / "Route Profile.xlsx",
    APP_FOLDER / "Route Profile.xlsx",
]

DIRECTION_COLORS = {
    "E": "#2563EB",
    "W": "#F2B705",
    "N": "#2563EB",
    "S": "#F2B705",
    "Inbound": "#F2B705",
    "Outbound": "#2563EB",
    "CW": "#2563EB",
    "CCW": "#F2B705",
    "Trip 1": "#F2B705",
    "Trip 2": "#2563EB",
    "Unknown": "#6B7280",
}

OTP_COLORS = {
    "On-Time": "#2E86AB",
    "Early": "#F6C85F",
    "Late": "#D1495B",
}

SERVICE_DAY_ORDER = ["Weekday", "Saturday", "Sunday"]


# ============================================================
# GENERAL HELPERS
# ============================================================


def locate_data_file() -> Path:
    for candidate in DATA_FILE_CANDIDATES:
        if candidate.exists():
            return candidate

    st.error(
        "Route Profile.xlsx was not found. Place it either beside this app.py "
        "file or inside a data folder."
    )
    st.stop()


def normalize_route_name(value):
    if pd.isna(value):
        return None

    value = str(value).strip()
    value = re.sub(r"^Route\s+", "", value, flags=re.IGNORECASE)

    if value.endswith(".0"):
        value = value[:-2]

    return value.upper()


def route_sort_key(value):
    value = normalize_route_name(value)

    if value is None:
        return (999999, "")

    match = re.match(r"^(\d+)(.*)$", value)
    if match:
        return (int(match.group(1)), match.group(2))

    return (999999, value)


def safe_numeric(series):
    return pd.to_numeric(
        series.astype("string")
        .str.replace("%", "", regex=False)
        .str.replace(",", "", regex=False)
        .str.strip(),
        errors="coerce",
    )


def clean_service_day(series):
    return (
        series.astype("string")
        .str.strip()
        .str.title()
        .replace(
            {
                "Weekdays": "Weekday",
                "Saturday Service": "Saturday",
                "Sunday Service": "Sunday",
                "Sat": "Saturday",
                "Sun": "Sunday",
                "<Na>": pd.NA,
                "Nan": pd.NA,
                "None": pd.NA,
                "": pd.NA,
            }
        )
    )


def extract_trip_time(series):
    extracted = series.astype("string").str.extract(r"(\d{1,2}:\d{2})\s*$")[0]
    parsed = pd.to_datetime(extracted, format="%H:%M", errors="coerce")
    return parsed.dt.strftime("%H:%M").fillna(extracted)


def extract_trip_code(series):
    return (
        series.astype("string")
        .str.extract(r"^\s*[^-]+-\s*(.*?)\s*-\s*\d{1,2}:\d{2}\s*$")[0]
        .str.strip()
    )


def extract_direction(trip_series):
    values = (
        trip_series.astype("string")
        .str.upper()
        .str.replace(" ", "", regex=False)
        .fillna("")
    )

    def parse(value):
        if not value:
            return "Unknown"

        checks = [
            (r"CCW", "CCW"),
            (r"(?<!C)CW", "CW"),
            (r"OUTBOUND|\bOB\b", "Outbound"),
            (r"INBOUND|\bIB\b", "Inbound"),
            (r"EB", "E"),
            (r"WB", "W"),
            (r"NB", "N"),
            (r"SB", "S"),
        ]

        for pattern, label in checks:
            if re.search(pattern, value):
                return label

        trip_code_match = re.search(r"-([A-Z0-9]+)-", value)
        candidate = trip_code_match.group(1) if trip_code_match else value

        route_direction = re.search(r"\d+[^EWNSOI]*([EWNSOI])", candidate)
        if route_direction:
            return {
                "E": "E",
                "W": "W",
                "N": "N",
                "S": "S",
                "O": "Outbound",
                "I": "Inbound",
            }[route_direction.group(1)]

        return "Unknown"

    return values.apply(parse)


def minutes_from_time(series):
    parsed = pd.to_datetime(series, format="%H:%M", errors="coerce")
    return parsed.dt.hour * 60 + parsed.dt.minute


def minutes_to_label(value):
    if pd.isna(value):
        return ""

    value = int(round(value))
    return f"{value // 60:02d}:{value % 60:02d}"


def paired_time_label(row):
    times = [row.get("trip_1_minutes"), row.get("trip_2_minutes")]
    valid_times = [value for value in times if pd.notna(value)]

    if not valid_times:
        return f"Pair {int(row['pair_number'])}"

    return minutes_to_label(sum(valid_times) / len(valid_times))


def section_header(text):
    st.markdown(
        f'<div class="section-header">{text}</div>',
        unsafe_allow_html=True,
    )


def chart_style(chart):
    return (
        chart.configure_axis(
            labelColor="#4B5563",
            titleColor="#12355B",
            gridColor="#E5E7EB",
            domain=False,
        )
        .configure_legend(
            labelColor="#4B5563",
            titleColor="#12355B",
            orient="top",
        )
        .configure_view(stroke=None)
    )


# ============================================================
# LOAD AND PREPARE THE PAIRED WORKBOOK
# ============================================================


@st.cache_data(ttl=3600)
def load_paired_route_profiles(file_path: str):
    """
    Read every route sheet from Route Profile.xlsx.

    Only columns A:P are read. This is intentional because each sheet uses:
      A:H = Trip 1 information
      I:P = Trip 2 information

    Each spreadsheet row is already a matched trip pair. Blank cells are kept
    as an unmatched side of that pair rather than being dropped or re-paired.
    """

    workbook = pd.ExcelFile(file_path)
    paired_frames = []

    expected_columns = [
        "day1",
        "trip1",
        "average_daily_boardings1",
        "median_passenger_load1",
        "early1",
        "on_time1",
        "late1",
        "total_fare_counts1",
        "day2",
        "trip2",
        "average_daily_boardings2",
        "median_passenger_load2",
        "early2",
        "on_time2",
        "late2",
        "total_fare_counts2",
    ]

    for sheet_name in workbook.sheet_names:
        route_name = normalize_route_name(sheet_name)

        sheet_df = pd.read_excel(
            file_path,
            sheet_name=sheet_name,
            usecols="A:P",
            dtype=object,
        )

        # Use position rather than original spelling so small Excel-header
        # differences do not break the dashboard.
        if sheet_df.shape[1] < 16:
            continue

        sheet_df = sheet_df.iloc[:, :16].copy()
        sheet_df.columns = expected_columns

        # Remove rows where neither side contains a trip.
        sheet_df = sheet_df[
            sheet_df["trip1"].notna() | sheet_df["trip2"].notna()
        ].copy()

        if sheet_df.empty:
            continue

        sheet_df["route_short_name"] = route_name
        sheet_df["source_sheet"] = sheet_name
        sheet_df["pair_number"] = range(1, len(sheet_df) + 1)

        for side in (1, 2):
            sheet_df[f"day{side}"] = clean_service_day(sheet_df[f"day{side}"])
            sheet_df[f"trip{side}"] = (
                sheet_df[f"trip{side}"].astype("string").str.strip()
            )

            numeric_fields = [
                f"average_daily_boardings{side}",
                f"median_passenger_load{side}",
                f"early{side}",
                f"on_time{side}",
                f"late{side}",
                f"total_fare_counts{side}",
            ]

            for field in numeric_fields:
                sheet_df[field] = safe_numeric(sheet_df[field])

            otp_fields = [
                f"early{side}",
                f"on_time{side}",
                f"late{side}",
            ]

            row_max = sheet_df[otp_fields].max(axis=1, skipna=True)
            decimal_rows = row_max.notna() & (row_max <= 1.5)
            sheet_df.loc[decimal_rows, otp_fields] = (
                sheet_df.loc[decimal_rows, otp_fields] * 100
            )

            missing_on_time = (
                sheet_df[f"on_time{side}"].isna()
                & sheet_df[f"early{side}"].notna()
                & sheet_df[f"late{side}"].notna()
            )

            sheet_df.loc[missing_on_time, f"on_time{side}"] = (
                100
                - sheet_df.loc[missing_on_time, f"early{side}"]
                - sheet_df.loc[missing_on_time, f"late{side}"]
            )

            for field in otp_fields:
                sheet_df[field] = sheet_df[field].clip(0, 100)

            sheet_df[f"trip_{side}_start_time"] = extract_trip_time(
                sheet_df[f"trip{side}"]
            )
            sheet_df[f"trip_{side}_minutes"] = minutes_from_time(
                sheet_df[f"trip_{side}_start_time"]
            )
            sheet_df[f"trip_{side}_code"] = extract_trip_code(
                sheet_df[f"trip{side}"]
            )
            sheet_df[f"direction{side}"] = extract_direction(
                sheet_df[f"trip{side}"]
            )

        # Use whichever service-day cell is present. When both are populated,
        # they should represent the same service day.
        sheet_df["service_day"] = sheet_df["day1"].combine_first(sheet_df["day2"])

        sheet_df["pair_time"] = sheet_df.apply(paired_time_label, axis=1)
        sheet_df["pair_key"] = (
            sheet_df["service_day"].astype("string").fillna("Unknown")
            + " | "
            + sheet_df["pair_number"].astype(str).str.zfill(3)
            + " | "
            + sheet_df["pair_time"].astype(str)
        )

        paired_frames.append(sheet_df)

    if not paired_frames:
        return pd.DataFrame(), pd.DataFrame()

    paired_df = pd.concat(paired_frames, ignore_index=True)

    # Convert the paired wide format into a long trip table for charts that
    # show each direction separately. pair_number remains attached to every
    # trip, so combined charts can place Trip 1 and Trip 2 side by side.
    long_frames = []

    for side in (1, 2):
        side_df = paired_df[
            [
                "route_short_name",
                "source_sheet",
                "service_day",
                "pair_number",
                "pair_time",
                "pair_key",
                f"trip{side}",
                f"trip_{side}_code",
                f"trip_{side}_start_time",
                f"trip_{side}_minutes",
                f"direction{side}",
                f"average_daily_boardings{side}",
                f"median_passenger_load{side}",
                f"early{side}",
                f"on_time{side}",
                f"late{side}",
                f"total_fare_counts{side}",
            ]
        ].copy()

        side_df.columns = [
            "route_short_name",
            "source_sheet",
            "service_day",
            "pair_number",
            "pair_time",
            "pair_key",
            "trip",
            "trip_code",
            "trip_start_time",
            "trip_minutes",
            "direction",
            "average_daily_boardings",
            "median_passenger_load",
            "percent_early",
            "percent_on_time",
            "percent_late",
            "total_fare_counts",
        ]

        side_df["pair_side"] = f"Trip {side}"
        side_df = side_df[side_df["trip"].notna()].copy()
        long_frames.append(side_df)

    long_df = pd.concat(long_frames, ignore_index=True)

    return paired_df, long_df


DATA_FILE = locate_data_file()

try:
    paired_df, trip_df = load_paired_route_profiles(str(DATA_FILE))
except Exception as error:
    st.error("The paired Route Profile workbook could not be loaded.")
    st.exception(error)
    st.stop()


# ============================================================
# CHART FUNCTIONS
# ============================================================


def paired_bar_chart(data, value_column, y_title, tooltip_title):
    if data.empty:
        return None

    pair_order = (
        data[["pair_key", "pair_number"]]
        .drop_duplicates()
        .sort_values("pair_number")["pair_key"]
        .tolist()
    )

    directions = data["direction"].dropna().unique().tolist()
    color_domain = [direction for direction in DIRECTION_COLORS if direction in directions]
    color_domain.extend(
        direction for direction in directions if direction not in color_domain
    )
    color_range = [DIRECTION_COLORS.get(direction, "#6B7280") for direction in color_domain]

    chart = (
        alt.Chart(data)
        .mark_bar(cornerRadiusTopLeft=2, cornerRadiusTopRight=2)
        .encode(
            x=alt.X(
                "pair_key:N",
                title="Matched Trip Pair",
                sort=pair_order,
                axis=alt.Axis(
                    labelExpr="split(datum.label, ' | ')[2]",
                    labelAngle=-45,
                    labelOverlap=False,
                    labelLimit=90,
                ),
                scale=alt.Scale(paddingInner=0.2, paddingOuter=0.1),
            ),
            xOffset=alt.XOffset(
                "pair_side:N",
                sort=["Trip 1", "Trip 2"],
            ),
            y=alt.Y(f"{value_column}:Q", title=y_title),
            color=alt.Color(
                "direction:N",
                title="Direction",
                scale=alt.Scale(domain=color_domain, range=color_range),
            ),
            tooltip=[
                alt.Tooltip("pair_number:Q", title="Matched Pair", format=".0f"),
                alt.Tooltip("pair_side:N", title="Table Side"),
                alt.Tooltip("direction:N", title="Direction"),
                alt.Tooltip("trip_start_time:N", title="Actual Trip Start Time"),
                alt.Tooltip("trip_code:N", title="Trip"),
                alt.Tooltip(f"{value_column}:Q", title=tooltip_title, format=",.1f"),
            ],
        )
        .properties(height=390)
    )

    return chart_style(chart)


def actual_time_bar_chart(data, value_column, y_title, tooltip_title, aggregation="sum"):
    if data.empty:
        return None

    grouped = (
        data.groupby(
            ["trip_start_time", "trip_minutes", "trip_code", "direction"],
            as_index=False,
            dropna=False,
        )[value_column]
        .agg(aggregation)
        .sort_values(["trip_minutes", "trip_start_time", "trip_code"])
    )

    grouped["trip_datetime"] = pd.to_datetime(
        grouped["trip_start_time"], format="%H:%M", errors="coerce"
    )
    grouped = grouped.dropna(subset=["trip_datetime"])

    chart = (
        alt.Chart(grouped)
        .mark_bar(size=8, cornerRadiusTopLeft=2, cornerRadiusTopRight=2)
        .encode(
            x=alt.X(
                "trip_datetime:T",
                title="Actual Trip Start Time",
                axis=alt.Axis(format="%H:%M", labelAngle=-45, tickCount=24),
                scale=alt.Scale(nice=False),
            ),
            y=alt.Y(f"{value_column}:Q", title=y_title),
            color=alt.Color(
                "direction:N",
                title="Direction",
                scale=alt.Scale(
                    domain=list(DIRECTION_COLORS.keys()),
                    range=list(DIRECTION_COLORS.values()),
                ),
            ),
            tooltip=[
                alt.Tooltip("trip_start_time:N", title="Trip Start Time"),
                alt.Tooltip("trip_code:N", title="Trip"),
                alt.Tooltip("direction:N", title="Direction"),
                alt.Tooltip(f"{value_column}:Q", title=tooltip_title, format=",.1f"),
            ],
        )
        .properties(height=330)
    )

    return chart_style(chart)


def otp_chart(data):
    if data.empty:
        return None

    trip_order = (
        data[["trip_start_time", "trip_minutes"]]
        .drop_duplicates()
        .sort_values(["trip_minutes", "trip_start_time"])["trip_start_time"]
        .tolist()
    )

    otp_data = (
        data.groupby(
            ["trip_start_time", "trip_code", "direction"],
            as_index=False,
            dropna=False,
        )
        .agg(
            percent_on_time=("percent_on_time", "mean"),
            percent_early=("percent_early", "mean"),
            percent_late=("percent_late", "mean"),
        )
    )

    otp_long = otp_data.melt(
        id_vars=["trip_start_time", "trip_code", "direction"],
        value_vars=["percent_on_time", "percent_early", "percent_late"],
        var_name="performance_type",
        value_name="percent",
    ).dropna(subset=["percent"])

    otp_long["performance_type"] = otp_long["performance_type"].replace(
        {
            "percent_on_time": "On-Time",
            "percent_early": "Early",
            "percent_late": "Late",
        }
    )

    otp_long["performance_order"] = otp_long["performance_type"].map(
        {"Early": 1, "On-Time": 2, "Late": 3}
    )

    chart = (
        alt.Chart(otp_long)
        .mark_bar(cornerRadiusTopLeft=1, cornerRadiusTopRight=1)
        .encode(
            x=alt.X(
                "trip_start_time:N",
                title="Trip Start Time",
                sort=trip_order,
                axis=alt.Axis(labelAngle=-45, labelOverlap=False, labelLimit=90),
                scale=alt.Scale(paddingInner=0.18, paddingOuter=0.10),
            ),
            y=alt.Y(
                "percent:Q",
                title="Percent",
                stack="zero",
                scale=alt.Scale(domain=[0, 100]),
            ),
            color=alt.Color(
                "performance_type:N",
                title="Performance Type",
                sort=["On-Time", "Early", "Late"],
                scale=alt.Scale(
                    domain=["On-Time", "Early", "Late"],
                    range=[
                        OTP_COLORS["On-Time"],
                        OTP_COLORS["Early"],
                        OTP_COLORS["Late"],
                    ],
                ),
            ),
            order=alt.Order("performance_order:Q"),
            tooltip=[
                alt.Tooltip("trip_start_time:N", title="Trip Start Time"),
                alt.Tooltip("trip_code:N", title="Trip"),
                alt.Tooltip("direction:N", title="Direction"),
                alt.Tooltip("performance_type:N", title="Performance Type"),
                alt.Tooltip("percent:Q", title="Percent", format=".1f"),
            ],
        )
        .properties(height=300)
    )

    return chart_style(chart)


# ============================================================
# ROUTE PROFILE DISPLAY
# ============================================================


def create_route_profile(route_pairs, route_trips, route_name):
    if route_pairs.empty or route_trips.empty:
        st.warning(f"No Spring 2026 data are available for Route {route_name}.")
        return

    st.markdown(f"## Route {route_name}")

    total_average_daily_boardings = route_trips["average_daily_boardings"].sum()
    total_fare_counts = route_trips["total_fare_counts"].sum()
    average_load = route_trips["median_passenger_load"].mean()
    average_otp = route_trips["percent_on_time"].mean()
    average_late = route_trips["percent_late"].mean()

    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Total Avg. Daily Boardings", f"{total_average_daily_boardings:,.1f}")
    m2.metric("Total Fare Counts", f"{total_fare_counts:,.0f}")
    m3.metric("Avg. Median Load", f"{average_load:.1f}")
    m4.metric("Avg. On-Time", f"{average_otp:.1f}%")
    m5.metric("Avg. Late", f"{average_late:.1f}%")

    st.divider()

    available_days = route_pairs["service_day"].dropna().unique().tolist()
    ordered_days = [day for day in SERVICE_DAY_ORDER if day in available_days]
    ordered_days.extend(sorted(day for day in available_days if day not in ordered_days))

    if not ordered_days:
        st.warning("No service-day categories were found for this route.")
        return

    day_tabs = st.tabs(ordered_days)

    for day_tab, service_day in zip(day_tabs, ordered_days):
        with day_tab:
            day_pairs = route_pairs[route_pairs["service_day"] == service_day].copy()
            day_trips = route_trips[route_trips["service_day"] == service_day].copy()

            section_header(f"{service_day} Service")
            st.caption(
                "Each spreadsheet row is one matched pair. Trip 1 and Trip 2 are "
                "shown beside each other. A missing bar means that the opposite "
                "trip cell was blank and no corresponding trip exists."
            )

            # ------------------------------------------------
            # COMBINED-DIRECTION CHARTS USING THE EXISTING PAIRS
            # ------------------------------------------------

            st.markdown("#### Both Directions — Average Daily Boardings per Trip")
            combined_boardings = paired_bar_chart(
                day_trips,
                "average_daily_boardings",
                "Average Daily Boardings",
                "Average Daily Boardings",
            )
            if combined_boardings is not None:
                st.altair_chart(combined_boardings, use_container_width=True)

            st.markdown("#### Both Directions — Median Passenger Load per Trip")
            combined_load = paired_bar_chart(
                day_trips,
                "median_passenger_load",
                "Median Passenger Load",
                "Median Passenger Load",
            )
            if combined_load is not None:
                st.altair_chart(combined_load, use_container_width=True)

            # ------------------------------------------------
            # SEPARATE-DIRECTION BOARDING CHARTS
            # ------------------------------------------------

            st.markdown("#### Boardings per Trip by Direction")
            directions = sorted(day_trips["direction"].dropna().unique().tolist())

            for direction in directions:
                direction_df = day_trips[day_trips["direction"] == direction].copy()
                st.markdown(f"##### Direction {direction}")

                b1, b2 = st.columns(2)
                b1.metric(
                    "Total Boardings",
                    f"{direction_df['total_fare_counts'].sum():,.0f}",
                )
                b2.metric(
                    "Total Average Daily Boardings",
                    f"{direction_df['average_daily_boardings'].sum():,.1f}",
                )

                st.markdown("###### Total Boardings per Trip")
                total_chart = actual_time_bar_chart(
                    direction_df,
                    "total_fare_counts",
                    "Total Boardings",
                    "Total Boardings",
                    aggregation="sum",
                )
                if total_chart is not None:
                    st.altair_chart(total_chart, use_container_width=True)

                st.markdown("###### Average Daily Boardings per Trip")
                avg_chart = actual_time_bar_chart(
                    direction_df,
                    "average_daily_boardings",
                    "Average Daily Boardings",
                    "Average Daily Boardings",
                    aggregation="sum",
                )
                if avg_chart is not None:
                    st.altair_chart(avg_chart, use_container_width=True)

            # ------------------------------------------------
            # SEPARATE-DIRECTION LOAD CHARTS
            # ------------------------------------------------

            st.markdown("#### Median Passenger Load per Trip by Direction")

            for direction in directions:
                direction_df = day_trips[day_trips["direction"] == direction].copy()
                st.markdown(f"##### Direction {direction}")
                st.metric(
                    "Average Median Passenger Load",
                    f"{direction_df['median_passenger_load'].mean():.1f}",
                )

                load_chart = actual_time_bar_chart(
                    direction_df,
                    "median_passenger_load",
                    "Median Passenger Load",
                    "Median Passenger Load",
                    aggregation="mean",
                )
                if load_chart is not None:
                    st.altair_chart(load_chart, use_container_width=True)

            # ------------------------------------------------
            # ON-TIME PERFORMANCE
            # ------------------------------------------------

            st.markdown("#### On-Time Performance per Trip")

            for direction in directions:
                direction_df = day_trips[day_trips["direction"] == direction].copy()
                st.markdown(f"##### Direction {direction}")

                direction_otp = otp_chart(direction_df)
                if direction_otp is None:
                    st.warning(f"No OTP data were found for Direction {direction}.")
                else:
                    st.altair_chart(direction_otp, use_container_width=True)

            # ------------------------------------------------
            # PAIRED DETAIL TABLE
            # ------------------------------------------------

            with st.expander(
                f"View Route {route_name} {service_day} matched trip details"
            ):
                detail_columns = [
                    "pair_number",
                    "pair_time",
                    "trip1",
                    "direction1",
                    "average_daily_boardings1",
                    "median_passenger_load1",
                    "early1",
                    "on_time1",
                    "late1",
                    "total_fare_counts1",
                    "trip2",
                    "direction2",
                    "average_daily_boardings2",
                    "median_passenger_load2",
                    "early2",
                    "on_time2",
                    "late2",
                    "total_fare_counts2",
                ]

                detail_df = day_pairs[detail_columns].rename(
                    columns={
                        "pair_number": "Matched Pair",
                        "pair_time": "Pair Display Time",
                        "trip1": "Trip 1",
                        "direction1": "Direction 1",
                        "average_daily_boardings1": "Average Daily Boardings 1",
                        "median_passenger_load1": "Median Passenger Load 1",
                        "early1": "% Early 1",
                        "on_time1": "% On-Time 1",
                        "late1": "% Late 1",
                        "total_fare_counts1": "Total Fare Counts 1",
                        "trip2": "Trip 2",
                        "direction2": "Direction 2",
                        "average_daily_boardings2": "Average Daily Boardings 2",
                        "median_passenger_load2": "Median Passenger Load 2",
                        "early2": "% Early 2",
                        "on_time2": "% On-Time 2",
                        "late2": "% Late 2",
                        "total_fare_counts2": "Total Fare Counts 2",
                    }
                )

                st.dataframe(detail_df, use_container_width=True, hide_index=True)


# ============================================================
# ROUTE TABS
# ============================================================

if paired_df.empty or trip_df.empty:
    st.warning("No usable paired route-profile data were found in the workbook.")
else:
    route_options = sorted(
        paired_df["route_short_name"].dropna().unique().tolist(),
        key=route_sort_key,
    )

    st.caption(
        f"{len(route_options)} route sheets loaded from {DATA_FILE.name}. "
        "Trip matching comes directly from the spreadsheet rows."
    )

    route_tabs = st.tabs([f"Route {route}" for route in route_options])

    for route_tab, route_name in zip(route_tabs, route_options):
        with route_tab:
            route_pairs = paired_df[
                paired_df["route_short_name"] == route_name
            ].copy()
            route_trips = trip_df[
                trip_df["route_short_name"] == route_name
            ].copy()

            create_route_profile(route_pairs, route_trips, route_name)
