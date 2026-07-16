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
        Public-facing route performance dashboard using CSV files stored in this repository.
    </div>
    """,
    unsafe_allow_html=True,
)


# ============================================================
# CONFIGURATION
# ============================================================

DATA_FOLDER = Path(__file__).parent / "data"

DIRECTION_COLORS = {
    "E": "#2563EB",
    "W": "#F2B705",
    "N": "#2563EB",
    "S": "#F2B705",
    "Inbound": "#2563EB",
    "Outbound": "#F2B705",
    "CW": "#2563EB",
    "CCW": "#F2B705",
    "Unknown": "#6B7280",
}

OTP_COLORS = {
    "On-Time": "#2E86AB",
    "Early": "#F6C85F",
    "Late": "#D1495B",
}


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def standardize_column_names(df: pd.DataFrame) -> pd.DataFrame:
    """Convert source column names to lowercase snake_case."""

    cleaned = []

    for column in df.columns:
        value = str(column).strip()
        value = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", value)
        value = re.sub(r"[^A-Za-z0-9]+", "_", value)
        cleaned.append(value.strip("_").lower())

    result = df.copy()
    result.columns = cleaned
    return result


def safe_numeric(series: pd.Series) -> pd.Series:
    """Convert text, percentages, and comma-formatted values to numeric."""

    return pd.to_numeric(
        series.astype(str)
        .str.replace("%", "", regex=False)
        .str.replace(",", "", regex=False)
        .str.strip(),
        errors="coerce",
    )


def normalize_route_name(value) -> str | None:
    """Keep route names such as 1, 26S, and 123S correctly formatted."""

    if pd.isna(value):
        return None

    value = str(value).strip().upper()

    if value.endswith(".0"):
        value = value[:-2]

    return value


def route_sort_key(value):
    """Sort routes naturally: 1, 2, 3, 10, 26, 26S, 123, 123S."""

    value = normalize_route_name(value)

    if value is None:
        return (999999, "")

    match = re.match(r"^(\d+)(.*)$", value)

    if match:
        return int(match.group(1)), match.group(2)

    return 999999, value


def extract_route_from_filename(filename: str) -> str:
    """
    Extract the route from names such as:
      RouteProfile_Spring_Rt 1.csv
      RouteProfile_Spring_Rt_26S.csv
      route_123S.csv
    """

    stem = Path(filename).stem.upper()

    patterns = [
        r"(?:RT|ROUTE)[ _-]*([0-9]+[A-Z]*)",
        r"([0-9]+[A-Z]*)$",
    ]

    for pattern in patterns:
        match = re.search(pattern, stem)

        if match:
            return normalize_route_name(match.group(1))

    return stem


def extract_trip_code(series: pd.Series) -> pd.Series:
    """
    Extract the middle part of the Trip field.

    Example:
      2 - 2W - 08:30 -> 2W
    """

    extracted = series.astype(str).str.extract(
        r"^\s*[^-]+-\s*(.*?)\s*-\s*\d{1,2}:\d{2}\s*$"
    )[0]

    fallback = series.astype(str).str.extract(
        r"([0-9]+[A-Za-z]+[A-Za-z0-9]*)"
    )[0]

    return extracted.fillna(fallback).str.strip()


def format_trip_time(series: pd.Series) -> pd.Series:
    """Extract and standardize trip times as HH:MM."""

    extracted = series.astype(str).str.extract(
        r"(\d{1,2}:\d{2})\s*$"
    )[0]

    parsed = pd.to_datetime(
        extracted,
        format="%H:%M",
        errors="coerce",
    )

    return parsed.dt.strftime("%H:%M").fillna(extracted)


def extract_direction(series: pd.Series) -> pd.Series:
    """
    Extract direction from formats such as:
      1E, 1W0, 2W, 2-W, OB, IB, EB, WB, NB, SB, CW, CCW
    """

    values = (
        series.astype(str)
        .str.strip()
        .str.upper()
        .str.replace(" ", "", regex=False)
    )

    def parse(value: str) -> str:
        if not value or value == "NAN":
            return "Unknown"

        specific = [
            (r"CCW", "CCW"),
            (r"(?<!C)CW", "CW"),
            (r"OUTBOUND", "Outbound"),
            (r"INBOUND", "Inbound"),
            (r"OB", "Outbound"),
            (r"IB", "Inbound"),
            (r"EB", "E"),
            (r"WB", "W"),
            (r"NB", "N"),
            (r"SB", "S"),
        ]

        for pattern, label in specific:
            if re.search(pattern, value):
                return label

        route_direction = re.search(
            r"^\d+[^EWNSOI]*([EWNSOI])",
            value,
        )

        if route_direction:
            return {
                "E": "E",
                "W": "W",
                "N": "N",
                "S": "S",
                "O": "Outbound",
                "I": "Inbound",
            }.get(route_direction.group(1), "Unknown")

        fallback = re.search(r"([EWNSOI])", value)

        if fallback:
            return {
                "E": "E",
                "W": "W",
                "N": "N",
                "S": "S",
                "O": "Outbound",
                "I": "Inbound",
            }.get(fallback.group(1), "Unknown")

        return "Unknown"

    return values.apply(parse)


def clean_route_file(df: pd.DataFrame, route_name: str) -> pd.DataFrame:
    """Prepare one route-profile CSV for the dashboard."""

    df = standardize_column_names(df)

    aliases = {
        "day": "service_day",
        "service_day": "service_day",
        "serviceday": "service_day",

        "trip": "trip",

        "averagedailyboardings": "average_daily_boardings",
        "average_daily_boardings": "average_daily_boardings",

        "medianpassengerload": "median_passenger_load",
        "median_passenger_load": "median_passenger_load",

        "early": "percent_early",
        "percent_early": "percent_early",

        "ontime": "percent_on_time",
        "on_time": "percent_on_time",
        "percent_on_time": "percent_on_time",

        "late": "percent_late",
        "percent_late": "percent_late",

        "totalfarecounts": "total_fare_counts",
        "total_fare_counts": "total_fare_counts",
    }

    df = df.rename(
        columns={
            column: aliases[column]
            for column in df.columns
            if column in aliases
        }
    )

    required = [
        "service_day",
        "trip",
        "average_daily_boardings",
        "median_passenger_load",
        "percent_early",
        "percent_on_time",
        "percent_late",
        "total_fare_counts",
    ]

    missing = [
        column
        for column in required
        if column not in df.columns
    ]

    if missing:
        raise ValueError(
            f"{route_name}: missing columns: {', '.join(missing)}. "
            f"Available columns: {', '.join(df.columns)}"
        )

    df["route_short_name"] = normalize_route_name(route_name)

    df["service_day"] = (
        df["service_day"]
        .astype(str)
        .str.strip()
        .str.title()
        .replace(
            {
                "Weekdays": "Weekday",
                "Sat": "Saturday",
                "Sun": "Sunday",
                "Saturday Service": "Saturday",
                "Sunday Service": "Sunday",
            }
        )
    )

    df["trip"] = df["trip"].astype(str).str.strip()
    df["trip_code"] = extract_trip_code(df["trip"])
    df["direction"] = extract_direction(df["trip_code"])

    unknown = df["direction"].eq("Unknown")

    if unknown.any():
        df.loc[unknown, "direction"] = extract_direction(
            df.loc[unknown, "trip"]
        )

    df["trip_start_time"] = format_trip_time(df["trip"])
    df["trip_datetime"] = pd.to_datetime(
        df["trip_start_time"],
        format="%H:%M",
        errors="coerce",
    )

    numeric_columns = [
        "average_daily_boardings",
        "median_passenger_load",
        "percent_early",
        "percent_on_time",
        "percent_late",
        "total_fare_counts",
    ]

    for column in numeric_columns:
        df[column] = safe_numeric(df[column])

    otp_columns = [
        "percent_early",
        "percent_on_time",
        "percent_late",
    ]

    row_max = df[otp_columns].max(axis=1, skipna=True)
    decimal_rows = row_max.notna() & row_max.le(1.5)

    df.loc[decimal_rows, otp_columns] = (
        df.loc[decimal_rows, otp_columns] * 100
    )

    missing_on_time = (
        df["percent_on_time"].isna()
        & df["percent_early"].notna()
        & df["percent_late"].notna()
    )

    df.loc[missing_on_time, "percent_on_time"] = (
        100
        - df.loc[missing_on_time, "percent_early"]
        - df.loc[missing_on_time, "percent_late"]
    )

    for column in otp_columns:
        df[column] = df[column].clip(0, 100)

    return df.dropna(
        subset=["service_day", "trip_start_time"],
        how="all",
    )


@st.cache_data(ttl=3600)
def load_all_route_files() -> pd.DataFrame:
    """Read and combine every CSV in the repository's data folder."""

    csv_files = sorted(DATA_FOLDER.glob("*.csv"))

    if not csv_files:
        return pd.DataFrame()

    frames = []
    errors = []

    for file_path in csv_files:
        route_name = extract_route_from_filename(file_path.name)

        try:
            raw = pd.read_csv(file_path)
            cleaned = clean_route_file(raw, route_name)
            cleaned["source_file"] = file_path.name
            frames.append(cleaned)
        except Exception as error:
            errors.append(f"{file_path.name}: {error}")

    if errors:
        st.warning(
            "Some files could not be loaded:\n\n"
            + "\n\n".join(f"- {error}" for error in errors)
        )

    if not frames:
        return pd.DataFrame()

    return pd.concat(frames, ignore_index=True)


# ============================================================
# CHART HELPERS
# ============================================================

def temporal_bar_chart(
    data: pd.DataFrame,
    value_column: str,
    y_title: str,
    tooltip_title: str,
    height: int = 330,
):
    """Create a bar chart positioned by actual scheduled time."""

    return (
        alt.Chart(data)
        .mark_bar(
            size=8,
            cornerRadiusTopLeft=2,
            cornerRadiusTopRight=2,
        )
        .encode(
            x=alt.X(
                "trip_datetime:T",
                title="Actual Trip Start Time",
                axis=alt.Axis(
                    format="%H:%M",
                    labelAngle=-45,
                    tickCount=24,
                    labelOverlap=True,
                ),
                scale=alt.Scale(nice=False),
            ),
            y=alt.Y(
                f"{value_column}:Q",
                title=y_title,
            ),
            tooltip=[
                alt.Tooltip(
                    "trip_start_time:N",
                    title="Trip Start Time",
                ),
                alt.Tooltip(
                    "trip_code:N",
                    title="Trip",
                ),
                alt.Tooltip(
                    "direction:N",
                    title="Direction",
                ),
                alt.Tooltip(
                    f"{value_column}:Q",
                    title=tooltip_title,
                    format=",.1f",
                ),
            ],
        )
        .properties(
            width=1250,
            height=height,
        )
    )


def otp_chart_for_direction(
    direction_df: pd.DataFrame,
):
    """Create a categorical OTP chart for one direction."""

    direction_df = direction_df.sort_values(
        [
            "trip_datetime",
            "trip_start_time",
            "trip_code",
        ]
    )

    trip_order = (
        direction_df[
            ["trip_start_time", "trip_datetime"]
        ]
        .drop_duplicates()
        .sort_values(
            ["trip_datetime", "trip_start_time"]
        )
        ["trip_start_time"]
        .tolist()
    )

    otp_data = (
        direction_df
        .groupby(
            [
                "trip_start_time",
                "trip_code",
                "direction",
            ],
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
        id_vars=[
            "trip_start_time",
            "trip_code",
            "direction",
        ],
        value_vars=[
            "percent_on_time",
            "percent_early",
            "percent_late",
        ],
        var_name="performance_type",
        value_name="percent",
    ).dropna(subset=["percent"])

    otp_long["performance_type"] = (
        otp_long["performance_type"]
        .replace(
            {
                "percent_on_time": "On-Time",
                "percent_early": "Early",
                "percent_late": "Late",
            }
        )
    )

    otp_long["performance_order"] = (
        otp_long["performance_type"]
        .map(
            {
                "Early": 1,
                "On-Time": 2,
                "Late": 3,
            }
        )
    )

    return (
        alt.Chart(otp_long)
        .mark_bar(
            cornerRadiusTopLeft=1,
            cornerRadiusTopRight=1,
        )
        .encode(
            x=alt.X(
                "trip_start_time:N",
                title="Trip Start Time",
                sort=trip_order,
                axis=alt.Axis(
                    labelAngle=-45,
                    labelOverlap=False,
                    labelLimit=90,
                ),
                scale=alt.Scale(
                    paddingInner=0.18,
                    paddingOuter=0.10,
                ),
            ),
            y=alt.Y(
                "percent:Q",
                title="Percent",
                stack="zero",
                scale=alt.Scale(domain=[0, 100]),
                axis=alt.Axis(
                    values=[0, 20, 40, 60, 80, 100]
                ),
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
                alt.Tooltip(
                    "trip_start_time:N",
                    title="Trip Start Time",
                ),
                alt.Tooltip(
                    "trip_code:N",
                    title="Trip",
                ),
                alt.Tooltip(
                    "direction:N",
                    title="Direction",
                ),
                alt.Tooltip(
                    "performance_type:N",
                    title="Performance Type",
                ),
                alt.Tooltip(
                    "percent:Q",
                    title="Percent",
                    format=".1f",
                ),
            ],
        )
        .properties(
            width=1250,
            height=300,
        )
    )


# ============================================================
# ROUTE PROFILE DISPLAY
# ============================================================

def display_route_profile(
    route_df: pd.DataFrame,
    route_name: str,
):
    """Display all dashboard sections for one route."""

    st.markdown(f"## Route {route_name}")

    total_boardings = route_df["total_fare_counts"].sum()
    total_daily_average = (
        route_df["average_daily_boardings"].sum()
    )
    average_load = route_df["median_passenger_load"].mean()
    average_otp = route_df["percent_on_time"].mean()
    average_late = route_df["percent_late"].mean()

    m1, m2, m3, m4, m5 = st.columns(5)

    m1.metric(
        "Total Boardings",
        f"{total_boardings:,.0f}",
    )

    m2.metric(
        "Total Average Daily Boardings",
        f"{total_daily_average:,.1f}",
    )

    m3.metric(
        "Avg. Median Load",
        f"{average_load:.1f}",
    )

    m4.metric(
        "Avg. On-Time",
        f"{average_otp:.1f}%",
    )

    m5.metric(
        "Avg. Late",
        f"{average_late:.1f}%",
    )

    st.divider()

    preferred_days = [
        "Weekday",
        "Saturday",
        "Sunday",
    ]

    available_days = (
        route_df["service_day"]
        .dropna()
        .unique()
        .tolist()
    )

    ordered_days = [
        day
        for day in preferred_days
        if day in available_days
    ]

    ordered_days.extend(
        sorted(
            day
            for day in available_days
            if day not in preferred_days
        )
    )

    if not ordered_days:
        st.warning(
            "No service-day categories were found for this route."
        )
        return

    day_tabs = st.tabs(ordered_days)

    for day_tab, service_day in zip(
        day_tabs,
        ordered_days,
    ):
        with day_tab:
            service_df = route_df[
                route_df["service_day"] == service_day
            ].copy()

            service_df = service_df.dropna(
                subset=["trip_datetime"]
            )

            st.markdown(
                f'<div class="section-header">{service_day} Service</div>',
                unsafe_allow_html=True,
            )

            directions = sorted(
                service_df["direction"]
                .dropna()
                .unique()
                .tolist()
            )

            if not directions:
                st.warning(
                    f"No direction information is available for {service_day}."
                )
                continue

            # ------------------------------------------------
            # BOARDINGS
            # ------------------------------------------------

            st.markdown("### Boardings")

            for direction in directions:
                direction_df = service_df[
                    service_df["direction"] == direction
                ].copy()

                st.markdown(f"#### Direction {direction}")

                direction_total = (
                    direction_df["total_fare_counts"].sum()
                )

                direction_daily_average = (
                    direction_df[
                        "average_daily_boardings"
                    ].sum()
                )

                c1, c2 = st.columns(2)

                c1.metric(
                    "Total Boardings",
                    f"{direction_total:,.0f}",
                )

                c2.metric(
                    "Total Average Daily Boardings",
                    f"{direction_daily_average:,.1f}",
                )

                total_data = (
                    direction_df
                    .groupby(
                        [
                            "trip_datetime",
                            "trip_start_time",
                            "trip_code",
                            "direction",
                        ],
                        as_index=False,
                        dropna=False,
                    )
                    ["total_fare_counts"]
                    .sum()
                )

                st.markdown(
                    "##### Total Boardings per Trip"
                )

                st.altair_chart(
                    temporal_bar_chart(
                        total_data,
                        "total_fare_counts",
                        "Total Boardings",
                        "Total Boardings",
                    ),
                    use_container_width=True,
                )

                daily_data = (
                    direction_df
                    .groupby(
                        [
                            "trip_datetime",
                            "trip_start_time",
                            "trip_code",
                            "direction",
                        ],
                        as_index=False,
                        dropna=False,
                    )
                    ["average_daily_boardings"]
                    .sum()
                )

                st.markdown(
                    "##### Average Daily Boardings per Trip"
                )

                st.altair_chart(
                    temporal_bar_chart(
                        daily_data,
                        "average_daily_boardings",
                        "Average Daily Boardings",
                        "Average Daily Boardings",
                    ),
                    use_container_width=True,
                )

            # ------------------------------------------------
            # MEDIAN PASSENGER LOAD
            # ------------------------------------------------

            st.markdown("### Median Passenger Load")

            for direction in directions:
                direction_df = service_df[
                    service_df["direction"] == direction
                ].copy()

                st.markdown(f"#### Direction {direction}")

                average_direction_load = (
                    direction_df[
                        "median_passenger_load"
                    ].mean()
                )

                st.metric(
                    "Average Median Passenger Load",
                    f"{average_direction_load:.1f}",
                )

                load_data = (
                    direction_df
                    .groupby(
                        [
                            "trip_datetime",
                            "trip_start_time",
                            "trip_code",
                            "direction",
                        ],
                        as_index=False,
                        dropna=False,
                    )
                    ["median_passenger_load"]
                    .mean()
                )

                st.altair_chart(
                    temporal_bar_chart(
                        load_data,
                        "median_passenger_load",
                        "Median Passenger Load",
                        "Median Passenger Load",
                        height=350,
                    ),
                    use_container_width=True,
                )

            # ------------------------------------------------
            # ON-TIME PERFORMANCE
            # ------------------------------------------------

            st.markdown("### On-Time Performance")

            for direction in directions:
                direction_df = service_df[
                    service_df["direction"] == direction
                ].copy()

                valid_otp = direction_df.dropna(
                    subset=[
                        "percent_on_time",
                        "percent_early",
                        "percent_late",
                    ],
                    how="all",
                )

                st.markdown(f"#### Direction {direction}")

                if valid_otp.empty:
                    st.warning(
                        "No valid on-time-performance values "
                        "are available for this direction."
                    )
                    continue

                st.altair_chart(
                    otp_chart_for_direction(valid_otp),
                    use_container_width=True,
                )

            # ------------------------------------------------
            # DETAIL TABLE
            # ------------------------------------------------

            with st.expander(
                f"View Route {route_name} {service_day} trip details"
            ):
                detail_columns = [
                    "service_day",
                    "route_short_name",
                    "direction",
                    "trip_code",
                    "trip_start_time",
                    "total_fare_counts",
                    "average_daily_boardings",
                    "median_passenger_load",
                    "percent_early",
                    "percent_on_time",
                    "percent_late",
                ]

                detail_df = service_df[
                    detail_columns
                ].copy()

                detail_df = detail_df.rename(
                    columns={
                        "service_day": "Service Day",
                        "route_short_name": "Route",
                        "direction": "Direction",
                        "trip_code": "Trip Code",
                        "trip_start_time": "Trip Start Time",
                        "total_fare_counts": "Total Boardings",
                        "average_daily_boardings": "Average Daily Boardings",
                        "median_passenger_load": "Median Passenger Load",
                        "percent_early": "% Early",
                        "percent_on_time": "% On-Time",
                        "percent_late": "% Late",
                    }
                )

                st.dataframe(
                    detail_df,
                    use_container_width=True,
                    hide_index=True,
                )


# ============================================================
# APP
# ============================================================

spring_df = load_all_route_files()

if spring_df.empty:
    st.error(
        "No route CSV files were found. Add your files to the "
        "`data` folder in the GitHub repository."
    )

    st.code(
        """
data/
├── RouteProfile_Spring_Rt 1.csv
├── RouteProfile_Spring_Rt 2.csv
├── RouteProfile_Spring_Rt 3.csv
└── ...
        """.strip()
    )

    st.stop()

route_options = sorted(
    spring_df["route_short_name"]
    .dropna()
    .unique()
    .tolist(),
    key=route_sort_key,
)

st.caption(
    f"{len(route_options)} route files loaded from the repository."
)

route_tabs = st.tabs(
    [f"Route {route}" for route in route_options]
)

for route_tab, route_name in zip(
    route_tabs,
    route_options,
):
    with route_tab:
        route_df = spring_df[
            spring_df["route_short_name"] == route_name
        ].copy()

        display_route_profile(
            route_df,
            route_name,
        )
