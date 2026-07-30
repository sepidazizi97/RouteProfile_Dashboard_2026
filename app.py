import os
import re
from io import BytesIO
from pathlib import Path
from urllib.parse import quote

import requests

import altair as alt
import pandas as pd
import streamlit as st


# ==================================================
# 1. PAGE CONFIGURATION
# ==================================================

st.set_page_config(
    page_title="BFT Spring 2026 Performance Dashboard",
    layout="wide",
)


# ==================================================
# 2. COLOR PALETTE
# ==================================================

BFT_NAVY = "#12355B"
BFT_BLUE = "#2563EB"
BFT_LIGHT_BLUE = "#60A5FA"
BFT_GOLD = "#E3A008"

ON_TIME_GREEN = "#2E8B57"
EARLY_GOLD = "#F6C85F"
LATE_RED = "#D64545"

WEEKDAY_BLUE = "#2563EB"
SATURDAY_GOLD = "#E3A008"
SUNDAY_GREEN = "#2E8B57"

REVENUE_MILES_TEAL = "#0F766E"
REVENUE_HOURS_PURPLE = "#7C3AED"
TRIPS_ORANGE = "#EA580C"

TEXT_GRAY = "#6B7280"
GRID_COLOR = "#E5E7EB"
CARD_BORDER = "#E2E8F0"


# ==================================================
# 3. PAGE STYLING
# ==================================================

st.markdown(
    f"""
    <style>
    .block-container {{
        padding-top: 2rem;
        padding-bottom: 3rem;
    }}

    .main-title {{
        color: {BFT_NAVY};
        font-size: 40px;
        font-weight: 800;
        margin-bottom: 3px;
    }}

    .sub-title {{
        color: {TEXT_GRAY};
        font-size: 16px;
        margin-bottom: 24px;
    }}

    .section-title {{
        color: {BFT_NAVY};
        font-size: 25px;
        font-weight: 750;
        margin-top: 26px;
        margin-bottom: 10px;
    }}

    .section-description {{
        color: {TEXT_GRAY};
        font-size: 14px;
        margin-bottom: 12px;
    }}

    div[data-testid="stMetric"] {{
        background-color: white;
        border: 1px solid {CARD_BORDER};
        border-radius: 14px;
        padding: 15px 18px;
        box-shadow: 0 2px 7px rgba(15, 23, 42, 0.05);
    }}

    div[data-testid="stMetricLabel"] {{
        color: {TEXT_GRAY};
        font-size: 14px;
    }}

    div[data-testid="stMetricValue"] {{
        color: {BFT_NAVY};
    }}
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    '<div class="main-title">BFT Spring 2026 Performance Dashboard</div>',
    unsafe_allow_html=True,
)

st.markdown(
    """
    <div class="sub-title">
    System performance, ridership trends, and detailed Spring 2026 route profiles
    </div>
    """,
    unsafe_allow_html=True,
)


# ==================================================
# 4. LOAD THE LATEST DATA DIRECTLY FROM GITHUB
# ==================================================

GITHUB_OWNER = "sepidazizi97"
GITHUB_REPOSITORY = "RouteProfile_Dashboard_2026"
GITHUB_BRANCH = "main"
GITHUB_RAW_BASE = (
    f"https://raw.githubusercontent.com/{GITHUB_OWNER}/"
    f"{GITHUB_REPOSITORY}/{GITHUB_BRANCH}"
)

SYSTEM_FILE_CANDIDATES = [
    "data/Summary System(1).csv",
    "data/Summary System.csv",
    "data/SYSTEM_SUMMARY_SPRING_2026.csv",
]

TREND_FILE_CANDIDATES = [
    "data/Ridership Trend from 2023 - Jul 20 2026(1).csv",
    "data/Ridership Trend from 2023 - Jul 20 2026.csv",
    "data/RIDERSHIP_TREND_FROM_2023.csv",
]

ROUTE_PROFILE_FILE_CANDIDATES = [
    "data/Route Profile.xlsx",
    "Route Profile.xlsx",
]


def github_raw_url(repository_path: str) -> str:
    """Create a raw GitHub URL while safely encoding spaces and symbols."""
    encoded_path = "/".join(quote(part) for part in repository_path.split("/"))
    return f"{GITHUB_RAW_BASE}/{encoded_path}"


def download_latest_github_file(candidates, refresh_number=0):
    """Download the first existing candidate from the GitHub main branch."""
    errors = []

    for repository_path in candidates:
        url = github_raw_url(repository_path)

        try:
            response = requests.get(
                url,
                timeout=45,
                headers={
                    "Cache-Control": "no-cache, no-store, must-revalidate",
                    "Pragma": "no-cache",
                    "Expires": "0",
                },
                params={"refresh": refresh_number},
            )

            if response.status_code == 200:
                return response.content, repository_path

            errors.append(f"{repository_path}: HTTP {response.status_code}")
        except requests.RequestException as error:
            errors.append(f"{repository_path}: {error}")

    st.error(
        "The latest data could not be downloaded from GitHub. Checked:\n"
        + "\n".join(f"- {item}" for item in errors)
    )
    st.stop()


def standardize_column_names(df):
    """Convert source column names to compact lowercase names."""
    df = df.copy()
    df.columns = (
        df.columns.astype(str)
        .str.strip()
        .str.lower()
        .str.replace(" ", "", regex=False)
        .str.replace("_", "", regex=False)
    )
    return df


@st.cache_data(ttl=60, show_spinner="Downloading the latest GitHub data...")
def load_system_and_trend_data(refresh_number):
    """Load the newest committed CSV files from GitHub."""
    system_bytes, system_source = download_latest_github_file(
        SYSTEM_FILE_CANDIDATES, refresh_number
    )
    trend_bytes, trend_source = download_latest_github_file(
        TREND_FILE_CANDIDATES, refresh_number
    )

    system_df = pd.read_csv(BytesIO(system_bytes))
    trend_df = pd.read_csv(BytesIO(trend_bytes))

    return (
        standardize_column_names(system_df),
        standardize_column_names(trend_df),
        system_source,
        trend_source,
    )


if "github_refresh_number" not in st.session_state:
    st.session_state.github_refresh_number = 0

refresh_col, source_col = st.columns([1, 4])
with refresh_col:
    if st.button("🔄 Refresh GitHub data", use_container_width=True):
        st.session_state.github_refresh_number += 1
        st.cache_data.clear()
        st.rerun()

with source_col:
    st.caption(
        "Data are loaded directly from the latest committed files on the "
        "GitHub main branch. Use Refresh after uploading or replacing a file."
    )

(
    system_df,
    trend_df,
    system_source_path,
    trend_source_path,
) = load_system_and_trend_data(st.session_state.github_refresh_number)


# ==================================================
# 5. DATA-CLEANING FUNCTIONS
# ==================================================

def clean_numeric(series):
    """Convert text-formatted numbers, commas, percentages, and blanks."""
    cleaned = (
        series.astype("string")
        .str.strip()
        .str.replace(",", "", regex=False)
        .str.replace("%", "", regex=False)
        .str.replace("$", "", regex=False)
    )

    cleaned = cleaned.replace(
        {
            "": pd.NA,
            "None": pd.NA,
            "none": pd.NA,
            "NULL": pd.NA,
            "null": pd.NA,
            "NaN": pd.NA,
            "nan": pd.NA,
            "<NA>": pd.NA,
        }
    )

    return pd.to_numeric(cleaned, errors="coerce")


def clean_route_labels(series):
    """Convert values such as 1.0 to 1 while preserving 27X and 123S."""
    return (
        series.astype("string")
        .str.strip()
        .str.replace(r"\.0$", "", regex=True)
    )


def create_route_sort(series):
    """Extract the numeric portion of a route label for route ordering."""
    return pd.to_numeric(
        series.astype("string").str.extract(r"(\d+)")[0],
        errors="coerce",
    )


def prepare_system_summary(df):
    """Clean and prepare the system-summary dataset."""
    df = df.copy()

    if "routes" not in df.columns:
        st.error(
            "The system-summary CSV does not contain a 'Routes' column. "
            f"Available columns: {list(df.columns)}"
        )
        st.stop()

    numeric_columns = [
        "totalavgdailyboardings",
        "totalboarding",
        "totalboradingweekday",
        "totalboardingweekday",
        "totalboardingsaturday",
        "totalboradingsunday",
        "totalboardingsunday",
        "totalaveragedailyweekdayborading",
        "totalaveragedailyweekdayboarding",
        "totalaveragedailysaturdayborading",
        "totalaveragedailysaturdayboarding",
        "totalaveragedailysundayborading",
        "totalaveragedailysundayboarding",
        "avgmedianload",
        "avgearly",
        "avgontime",
        "avglate",
        "totalseasonalrevenuemiles",
        "averagedailyrevenuemilesweekday",
        "averagedailyrevenuemilessaturday",
        "averagedailyrevenuemilessunday",
        "totaltripcount",
        "totalseasonalrevenuehours",
        "averagedailyrevenuehoursweekday",
        "averagedailyrevenuehourssaturday",
        "averagedailyrevenuehourssunday",
        "ridershipperrevhour",
        "weekdayridershipperrevhour",
        "saturdayridershipperrevhour",
        "sundayridershipperrevhour",
    ]

    df["routes"] = clean_route_labels(df["routes"])

    for column in numeric_columns:
        if column in df.columns:
            df[column] = clean_numeric(df[column])

    # Create correctly spelled aliases when the CSV retains earlier typos.
    alias_map = {
        "totalboradingweekday": "totalboardingweekday",
        "totalboradingsunday": "totalboardingsunday",
        "totalaveragedailyweekdayborading": "totalaveragedailyweekdayboarding",
        "totalaveragedailysaturdayborading": "totalaveragedailysaturdayboarding",
        "totalaveragedailysundayborading": "totalaveragedailysundayboarding",
    }

    for old_name, new_name in alias_map.items():
        if new_name not in df.columns and old_name in df.columns:
            df[new_name] = df[old_name]

    # Some system-summary files omit Avg Early. When that happens,
    # calculate it from the remaining OTP components.
    if "avgearly" not in df.columns:
        if "avgontime" in df.columns and "avglate" in df.columns:
            df["avgearly"] = (
                100 - df["avgontime"].fillna(0) - df["avglate"].fillna(0)
            ).clip(lower=0, upper=100)
        else:
            df["avgearly"] = pd.NA

    df["route_sort"] = create_route_sort(df["routes"])

    return (
        df.sort_values(
            by=["route_sort", "routes"],
            na_position="last",
        )
        .reset_index(drop=True)
    )


def prepare_ridership_trend(df):
    """Clean and prepare the monthly ridership-trend dataset."""
    df = df.copy()

    required_columns = ["route", "yearmonth", "totalfarecounts"]
    missing_columns = [
        column for column in required_columns if column not in df.columns
    ]

    if missing_columns:
        st.error(
            "The ridership-trend CSV is missing these columns: "
            f"{missing_columns}. Available columns: {list(df.columns)}"
        )
        st.stop()

    df["route"] = clean_route_labels(df["route"])
    df["yearmonth"] = pd.to_datetime(df["yearmonth"], errors="coerce")
    df["totalfarecounts"] = clean_numeric(df["totalfarecounts"])
    df["route_sort"] = create_route_sort(df["route"])

    # July 2026 is a partial month in the source file, so exclude it from
    # the trend charts, metrics, annual totals, and detail table.
    df = df.loc[
        ~((df["yearmonth"].dt.year == 2026) & (df["yearmonth"].dt.month == 7))
    ].copy()

    return (
        df.dropna(subset=["yearmonth"])
        .sort_values(
            by=["route_sort", "route", "yearmonth"],
            na_position="last",
        )
        .reset_index(drop=True)
    )


system_df = prepare_system_summary(system_df)
trend_df = prepare_ridership_trend(trend_df)

route_sort_order = (
    system_df[["routes", "route_sort"]]
    .dropna(subset=["routes"])
    .drop_duplicates(subset=["routes"])
    .sort_values(by=["route_sort", "routes"], na_position="last")["routes"]
    .astype(str)
    .tolist()
)


# ==================================================
# 6. REUSABLE CHART FORMATTING
# ==================================================

def format_chart(chart):
    return (
        chart.configure_axis(
            labelColor=TEXT_GRAY,
            titleColor=BFT_NAVY,
            gridColor=GRID_COLOR,
            gridOpacity=0.8,
            domain=False,
            tickColor=GRID_COLOR,
        )
        .configure_view(stroke=None)
        .configure_legend(
            labelColor=TEXT_GRAY,
            titleColor=BFT_NAVY,
            orient="top",
        )
        .configure_title(
            color=BFT_NAVY,
            fontSize=17,
            fontWeight=600,
            anchor="start",
        )
    )


def route_axis():
    return alt.X(
        "routes:N",
        title="Route",
        sort=route_sort_order,
        axis=alt.Axis(labelAngle=0, labelOverlap=False),
    )


def section_header(title, description=None):
    st.markdown(
        f'<div class="section-title">{title}</div>',
        unsafe_allow_html=True,
    )
    if description:
        st.markdown(
            f'<div class="section-description">{description}</div>',
            unsafe_allow_html=True,
        )


# ============================================================
# ROUTE PROFILE DATA, HELPERS, AND CHARTS
# ============================================================

# ============================================================
# CONFIGURATION
# ============================================================

APP_FOLDER = Path(__file__).resolve().parent

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


def locate_data_file():
    """Return the latest Route Profile workbook bytes and GitHub path."""
    return download_latest_github_file(
        ROUTE_PROFILE_FILE_CANDIDATES,
        st.session_state.github_refresh_number,
    )


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
    """
    Use the outbound trip start time as the pair display time.

    The workbook stores the outbound trip in Trip 1. Trip 1 is often
    westbound, but it can be another direction depending on the route.
    When Trip 1 is blank, use Trip 2 as a fallback.

    The workbook row order remains authoritative. This is important for
    schedule quirks on Route 1 Weekday/Saturday and Route 123 Sunday, where
    a later clock time can intentionally appear before the following pair.
    """
    outbound_minutes = row.get("trip_1_minutes")
    fallback_minutes = row.get("trip_2_minutes")

    if pd.notna(outbound_minutes):
        return minutes_to_label(outbound_minutes)

    if pd.notna(fallback_minutes):
        return minutes_to_label(fallback_minutes)

    return f"Pair {int(row['pair_number'])}"


def route_section_header(text):
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


@st.cache_data(ttl=60, show_spinner="Downloading the latest Route Profile workbook...")
def load_paired_route_profiles(file_bytes: bytes, refresh_number: int):
    """
    Read every route sheet from Route Profile.xlsx.

    Only columns A:P are read. This is intentional because each sheet uses:
      A:H = Trip 1 information
      I:P = Trip 2 information

    Each spreadsheet row is already a matched trip pair. Blank cells are kept
    as an unmatched side of that pair rather than being dropped or re-paired.
    """

    workbook = pd.ExcelFile(BytesIO(file_bytes))
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

        # Read the worksheet first without forcing A:P. This prevents pandas
        # from crashing when an older or single-direction sheet has fewer than
        # 16 physically populated columns.
        sheet_df = pd.read_excel(
            BytesIO(file_bytes),
            sheet_name=sheet_name,
            dtype=object,
        )

        if sheet_df.empty or sheet_df.shape[1] < 2:
            continue

        # Keep the paired A:P structure. Missing columns are padded with blanks
        # so a one-sided route remains usable rather than being discarded.
        sheet_df = sheet_df.iloc[:, :16].copy()
        while sheet_df.shape[1] < 16:
            sheet_df[f"__blank_{sheet_df.shape[1] + 1}"] = pd.NA

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


ROUTE_PROFILE_BYTES, ROUTE_PROFILE_SOURCE = locate_data_file()

try:
    paired_df, trip_df = load_paired_route_profiles(
        ROUTE_PROFILE_BYTES,
        st.session_state.github_refresh_number,
    )
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

    present_directions = grouped["direction"].dropna().unique().tolist()
    direction_domain = [
        direction
        for direction in DIRECTION_COLORS
        if direction in present_directions
    ]
    direction_domain.extend(
        direction
        for direction in present_directions
        if direction not in direction_domain
    )
    direction_range = [
        DIRECTION_COLORS.get(direction, "#6B7280")
        for direction in direction_domain
    ]

    # Separate-direction charts already name the direction in the heading.
    # Therefore, do not repeat a direction legend when only one direction
    # is present. If this function is ever used with multiple directions,
    # show only the directions that actually exist in the chart data.
    direction_legend = None if len(direction_domain) <= 1 else alt.Legend(title="Direction")

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
                legend=direction_legend,
                scale=alt.Scale(
                    domain=direction_domain,
                    range=direction_range,
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
    average_early = route_trips["percent_early"].mean()
    average_otp = route_trips["percent_on_time"].mean()
    average_late = route_trips["percent_late"].mean()

    m1, m2, m3, m4, m5, m6 = st.columns(6)
    m1.metric("Total Avg. Daily Boardings", f"{total_average_daily_boardings:,.1f}")
    m2.metric("Total Fare Counts", f"{total_fare_counts:,.0f}")
    m3.metric("Avg. Median Load", f"{average_load:.1f}")
    m4.metric("Avg. Early", f"{average_early:.1f}%")
    m5.metric("Avg. On-Time", f"{average_otp:.1f}%")
    m6.metric("Avg. Late", f"{average_late:.1f}%")

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

            route_section_header(f"{service_day} Service")
            st.caption(
                "Each spreadsheet row is one matched pair and workbook row order is preserved. "
                "Pair Display Time uses the outbound Trip 1 start time, with Trip 2 used only "
                "when Trip 1 is blank. A missing bar means no corresponding trip exists."
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

# ==================================================
# 7. DASHBOARD TABS
# ==================================================

tab1, tab2, tab3 = st.tabs(
    [
        "📊 System Performance",
        "📈 Ridership Trend",
        "🚌 Route Profiles",
    ]
)


# ==================================================
# 8. TAB 1 — SPRING 2026 SYSTEM SUMMARY
# ==================================================

with tab1:
    st.markdown("### Spring 2026 System Overview")

    total_boardings = system_df["totalboarding"].sum()
    total_avg_daily_boardings = system_df["totalavgdailyboardings"].sum()
    total_revenue_miles = system_df["totalseasonalrevenuemiles"].sum()
    total_revenue_hours = system_df["totalseasonalrevenuehours"].sum()
    total_trips = system_df["totaltripcount"].sum()

    overall_productivity = (
        total_boardings / total_revenue_hours
        if total_revenue_hours > 0
        else 0
    )

    boardings_weight = system_df["totalboarding"].fillna(0)
    total_weight = boardings_weight.sum()

    weighted_early = (
        (system_df["avgearly"].fillna(0) * boardings_weight).sum()
        / total_weight
        if total_weight > 0
        else 0
    )

    weighted_otp = (
        (system_df["avgontime"].fillna(0) * boardings_weight).sum()
        / total_weight
        if total_weight > 0
        else 0
    )

    weighted_late = (
        (system_df["avglate"].fillna(0) * boardings_weight).sum()
        / total_weight
        if total_weight > 0
        else 0
    )

    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("Total Spring Boardings", f"{total_boardings:,.0f}")
    k2.metric(
        "Total Avg Daily Boardings",
        f"{total_avg_daily_boardings:,.1f}",
    )
    k3.metric("System Early", f"{weighted_early:.1f}%")
    k4.metric("System On-Time", f"{weighted_otp:.1f}%")
    k5.metric("System Late", f"{weighted_late:.1f}%")

    s1, s2, s3, s4 = st.columns(4)
    s1.metric("Seasonal Revenue Miles", f"{total_revenue_miles:,.0f}")
    s2.metric("Seasonal Revenue Hours", f"{total_revenue_hours:,.1f}")
    s3.metric("Total Trips", f"{total_trips:,.0f}")
    s4.metric(
        "Boardings per Revenue Hour",
        f"{overall_productivity:.2f}",
    )

    st.divider()

    section_header(
        "Overall Ridership by Route",
        "Total seasonal boardings and average daily boardings.",
    )

    ridership_col1, ridership_col2 = st.columns(2)

    with ridership_col1:
        total_boarding_chart = (
            alt.Chart(system_df)
            .mark_bar(
                color=BFT_BLUE,
                cornerRadiusTopLeft=4,
                cornerRadiusTopRight=4,
            )
            .encode(
                x=route_axis(),
                y=alt.Y("totalboarding:Q", title="Total Boardings"),
                tooltip=[
                    alt.Tooltip("routes:N", title="Route"),
                    alt.Tooltip(
                        "totalboarding:Q",
                        title="Total Boardings",
                        format=",.0f",
                    ),
                ],
            )
            .properties(height=380, title="Total Spring Boardings")
        )

        st.altair_chart(
            format_chart(total_boarding_chart),
            use_container_width=True,
        )

    with ridership_col2:
        average_daily_chart = (
            alt.Chart(system_df)
            .mark_bar(
                color=BFT_GOLD,
                cornerRadiusTopLeft=4,
                cornerRadiusTopRight=4,
            )
            .encode(
                x=route_axis(),
                y=alt.Y(
                    "totalavgdailyboardings:Q",
                    title="Average Daily Boardings",
                ),
                tooltip=[
                    alt.Tooltip("routes:N", title="Route"),
                    alt.Tooltip(
                        "totalavgdailyboardings:Q",
                        title="Average Daily Boardings",
                        format=",.1f",
                    ),
                ],
            )
            .properties(
                height=380,
                title="Total Average Daily Boardings",
            )
        )

        st.altair_chart(
            format_chart(average_daily_chart),
            use_container_width=True,
        )

    section_header(
        "Total Boardings by Service Day",
        "Seasonal boardings divided between weekday, Saturday, and Sunday service.",
    )

    total_service_boardings = system_df[
        [
            "routes",
            "totalboardingweekday",
            "totalboardingsaturday",
            "totalboardingsunday",
        ]
    ].melt(
        id_vars="routes",
        var_name="service_day",
        value_name="total_boardings",
    )

    total_service_boardings["service_day"] = (
        total_service_boardings["service_day"].replace(
            {
                "totalboardingweekday": "Weekday",
                "totalboardingsaturday": "Saturday",
                "totalboardingsunday": "Sunday",
            }
        )
    )

    total_service_chart = (
        alt.Chart(total_service_boardings)
        .mark_bar(cornerRadiusTopLeft=3, cornerRadiusTopRight=3)
        .encode(
            x=route_axis(),
            xOffset=alt.XOffset(
                "service_day:N",
                sort=["Weekday", "Saturday", "Sunday"],
            ),
            y=alt.Y("total_boardings:Q", title="Total Boardings"),
            color=alt.Color(
                "service_day:N",
                title="Service Day",
                sort=["Weekday", "Saturday", "Sunday"],
                scale=alt.Scale(
                    domain=["Weekday", "Saturday", "Sunday"],
                    range=[
                        WEEKDAY_BLUE,
                        SATURDAY_GOLD,
                        SUNDAY_GREEN,
                    ],
                ),
            ),
            tooltip=[
                alt.Tooltip("routes:N", title="Route"),
                alt.Tooltip("service_day:N", title="Service Day"),
                alt.Tooltip(
                    "total_boardings:Q",
                    title="Total Boardings",
                    format=",.0f",
                ),
            ],
        )
        .properties(
            height=420,
            title="Total Seasonal Boardings by Service Day",
        )
    )

    st.altair_chart(
        format_chart(total_service_chart),
        use_container_width=True,
    )

    section_header(
        "Average Daily Boardings by Service Day",
        "Average daily route ridership for weekday, Saturday, and Sunday service.",
    )

    average_daily_boardings = system_df[
        [
            "routes",
            "totalaveragedailyweekdayboarding",
            "totalaveragedailysaturdayboarding",
            "totalaveragedailysundayboarding",
        ]
    ].melt(
        id_vars="routes",
        var_name="service_day",
        value_name="average_daily_boardings",
    )

    average_daily_boardings["service_day"] = (
        average_daily_boardings["service_day"].replace(
            {
                "totalaveragedailyweekdayboarding": "Weekday",
                "totalaveragedailysaturdayboarding": "Saturday",
                "totalaveragedailysundayboarding": "Sunday",
            }
        )
    )

    average_daily_boardings_chart = (
        alt.Chart(average_daily_boardings)
        .mark_bar(cornerRadiusTopLeft=3, cornerRadiusTopRight=3)
        .encode(
            x=route_axis(),
            xOffset=alt.XOffset(
                "service_day:N",
                sort=["Weekday", "Saturday", "Sunday"],
            ),
            y=alt.Y(
                "average_daily_boardings:Q",
                title="Average Daily Boardings",
            ),
            color=alt.Color(
                "service_day:N",
                title="Service Day",
                sort=["Weekday", "Saturday", "Sunday"],
                scale=alt.Scale(
                    domain=["Weekday", "Saturday", "Sunday"],
                    range=[
                        WEEKDAY_BLUE,
                        SATURDAY_GOLD,
                        SUNDAY_GREEN,
                    ],
                ),
            ),
            tooltip=[
                alt.Tooltip("routes:N", title="Route"),
                alt.Tooltip("service_day:N", title="Service Day"),
                alt.Tooltip(
                    "average_daily_boardings:Q",
                    title="Average Daily Boardings",
                    format=",.1f",
                ),
            ],
        )
        .properties(
            height=420,
            title="Average Daily Boardings by Service Day",
        )
    )

    st.altair_chart(
        format_chart(average_daily_boardings_chart),
        use_container_width=True,
    )

    section_header(
        "Passenger Load",
        "Average median passenger load by route.",
    )

    median_load_chart = (
        alt.Chart(system_df)
        .mark_bar(
            color=BFT_LIGHT_BLUE,
            cornerRadiusTopLeft=4,
            cornerRadiusTopRight=4,
        )
        .encode(
            x=route_axis(),
            y=alt.Y(
                "avgmedianload:Q",
                title="Average Median Passenger Load",
            ),
            tooltip=[
                alt.Tooltip("routes:N", title="Route"),
                alt.Tooltip(
                    "avgmedianload:Q",
                    title="Average Median Load",
                    format=".1f",
                ),
            ],
        )
        .properties(
            height=390,
            title="Average Median Passenger Load by Route",
        )
    )

    st.altair_chart(
        format_chart(median_load_chart),
        use_container_width=True,
    )

    section_header(
        "On-Time Performance",
        "Early, On-Time, and Late percentages are displayed in the same stacked column for each route.",
    )

    performance_data = system_df[
        ["routes", "avgearly", "avgontime", "avglate"]
    ].melt(
        id_vars="routes",
        var_name="performance_type",
        value_name="percentage",
    )

    performance_data["performance_type"] = (
        performance_data["performance_type"].replace(
            {
                "avgearly": "Early",
                "avgontime": "On-Time",
                "avglate": "Late",
            }
        )
    )

    performance_chart = (
        alt.Chart(performance_data)
        .mark_bar(cornerRadiusTopLeft=3, cornerRadiusTopRight=3)
        .encode(
            x=route_axis(),
            y=alt.Y(
                "percentage:Q",
                title="Percentage",
                stack="zero",
                scale=alt.Scale(domain=[0, 100]),
                axis=alt.Axis(labelExpr="datum.value + '%'"),
            ),
            color=alt.Color(
                "performance_type:N",
                title="Performance",
                sort=["Early", "On-Time", "Late"],
                scale=alt.Scale(
                    domain=["Early", "On-Time", "Late"],
                    range=[EARLY_GOLD, ON_TIME_GREEN, LATE_RED],
                ),
            ),
            order=alt.Order("performance_type:N", sort="descending"),
            tooltip=[
                alt.Tooltip("routes:N", title="Route"),
                alt.Tooltip(
                    "performance_type:N",
                    title="Performance",
                ),
                alt.Tooltip(
                    "percentage:Q",
                    title="Percentage",
                    format=".1f",
                ),
            ],
        )
        .properties(
            height=430,
            title="Average Early, On-Time, and Late Performance by Route",
        )
    )

    st.altair_chart(
        format_chart(performance_chart),
        use_container_width=True,
    )

    section_header(
        "Seasonal Service Supply",
        "Seasonal revenue miles, revenue hours, and trip counts are displayed separately because they use different units.",
    )

    supply_col1, supply_col2, supply_col3 = st.columns(3)

    with supply_col1:
        seasonal_miles_chart = (
            alt.Chart(system_df)
            .mark_bar(
                color=REVENUE_MILES_TEAL,
                cornerRadiusTopLeft=4,
                cornerRadiusTopRight=4,
            )
            .encode(
                x=route_axis(),
                y=alt.Y(
                    "totalseasonalrevenuemiles:Q",
                    title="Revenue Miles",
                ),
                tooltip=[
                    alt.Tooltip("routes:N", title="Route"),
                    alt.Tooltip(
                        "totalseasonalrevenuemiles:Q",
                        title="Seasonal Revenue Miles",
                        format=",.0f",
                    ),
                ],
            )
            .properties(height=390, title="Seasonal Revenue Miles")
        )
        st.altair_chart(
            format_chart(seasonal_miles_chart),
            use_container_width=True,
        )

    with supply_col2:
        seasonal_hours_chart = (
            alt.Chart(system_df)
            .mark_bar(
                color=REVENUE_HOURS_PURPLE,
                cornerRadiusTopLeft=4,
                cornerRadiusTopRight=4,
            )
            .encode(
                x=route_axis(),
                y=alt.Y(
                    "totalseasonalrevenuehours:Q",
                    title="Revenue Hours",
                ),
                tooltip=[
                    alt.Tooltip("routes:N", title="Route"),
                    alt.Tooltip(
                        "totalseasonalrevenuehours:Q",
                        title="Seasonal Revenue Hours",
                        format=",.1f",
                    ),
                ],
            )
            .properties(height=390, title="Seasonal Revenue Hours")
        )
        st.altair_chart(
            format_chart(seasonal_hours_chart),
            use_container_width=True,
        )

    with supply_col3:
        total_trips_chart = (
            alt.Chart(system_df)
            .mark_bar(
                color=TRIPS_ORANGE,
                cornerRadiusTopLeft=4,
                cornerRadiusTopRight=4,
            )
            .encode(
                x=route_axis(),
                y=alt.Y("totaltripcount:Q", title="Trip Count"),
                tooltip=[
                    alt.Tooltip("routes:N", title="Route"),
                    alt.Tooltip(
                        "totaltripcount:Q",
                        title="Total Trips",
                        format=",.0f",
                    ),
                ],
            )
            .properties(height=390, title="Total Trip Count")
        )
        st.altair_chart(
            format_chart(total_trips_chart),
            use_container_width=True,
        )

    section_header(
        "Average Daily Revenue Miles",
        "Average daily revenue miles by route and service day.",
    )

    daily_miles_data = system_df[
        [
            "routes",
            "averagedailyrevenuemilesweekday",
            "averagedailyrevenuemilessaturday",
            "averagedailyrevenuemilessunday",
        ]
    ].melt(
        id_vars="routes",
        var_name="service_day",
        value_name="average_daily_revenue_miles",
    )

    daily_miles_data["service_day"] = (
        daily_miles_data["service_day"].replace(
            {
                "averagedailyrevenuemilesweekday": "Weekday",
                "averagedailyrevenuemilessaturday": "Saturday",
                "averagedailyrevenuemilessunday": "Sunday",
            }
        )
    )

    daily_miles_chart = (
        alt.Chart(daily_miles_data)
        .mark_bar(cornerRadiusTopLeft=3, cornerRadiusTopRight=3)
        .encode(
            x=route_axis(),
            xOffset=alt.XOffset(
                "service_day:N",
                sort=["Weekday", "Saturday", "Sunday"],
            ),
            y=alt.Y(
                "average_daily_revenue_miles:Q",
                title="Average Daily Revenue Miles",
            ),
            color=alt.Color(
                "service_day:N",
                title="Service Day",
                sort=["Weekday", "Saturday", "Sunday"],
                scale=alt.Scale(
                    domain=["Weekday", "Saturday", "Sunday"],
                    range=[
                        WEEKDAY_BLUE,
                        SATURDAY_GOLD,
                        SUNDAY_GREEN,
                    ],
                ),
            ),
            tooltip=[
                alt.Tooltip("routes:N", title="Route"),
                alt.Tooltip("service_day:N", title="Service Day"),
                alt.Tooltip(
                    "average_daily_revenue_miles:Q",
                    title="Average Daily Revenue Miles",
                    format=",.1f",
                ),
            ],
        )
        .properties(
            height=420,
            title="Average Daily Revenue Miles by Service Day",
        )
    )

    st.altair_chart(
        format_chart(daily_miles_chart),
        use_container_width=True,
    )

    section_header(
        "Average Daily Revenue Hours",
        "Average daily revenue hours by route and service day.",
    )

    daily_hours_data = system_df[
        [
            "routes",
            "averagedailyrevenuehoursweekday",
            "averagedailyrevenuehourssaturday",
            "averagedailyrevenuehourssunday",
        ]
    ].melt(
        id_vars="routes",
        var_name="service_day",
        value_name="average_daily_revenue_hours",
    )

    daily_hours_data["service_day"] = (
        daily_hours_data["service_day"].replace(
            {
                "averagedailyrevenuehoursweekday": "Weekday",
                "averagedailyrevenuehourssaturday": "Saturday",
                "averagedailyrevenuehourssunday": "Sunday",
            }
        )
    )

    daily_hours_chart = (
        alt.Chart(daily_hours_data)
        .mark_bar(cornerRadiusTopLeft=3, cornerRadiusTopRight=3)
        .encode(
            x=route_axis(),
            xOffset=alt.XOffset(
                "service_day:N",
                sort=["Weekday", "Saturday", "Sunday"],
            ),
            y=alt.Y(
                "average_daily_revenue_hours:Q",
                title="Average Daily Revenue Hours",
            ),
            color=alt.Color(
                "service_day:N",
                title="Service Day",
                sort=["Weekday", "Saturday", "Sunday"],
                scale=alt.Scale(
                    domain=["Weekday", "Saturday", "Sunday"],
                    range=[
                        WEEKDAY_BLUE,
                        SATURDAY_GOLD,
                        SUNDAY_GREEN,
                    ],
                ),
            ),
            tooltip=[
                alt.Tooltip("routes:N", title="Route"),
                alt.Tooltip("service_day:N", title="Service Day"),
                alt.Tooltip(
                    "average_daily_revenue_hours:Q",
                    title="Average Daily Revenue Hours",
                    format=",.1f",
                ),
            ],
        )
        .properties(
            height=420,
            title="Average Daily Revenue Hours by Service Day",
        )
    )

    st.altair_chart(
        format_chart(daily_hours_chart),
        use_container_width=True,
    )

    section_header(
        "Ridership per Revenue Hour",
        "Overall and service-day productivity measures by route.",
    )

    overall_productivity_chart = (
        alt.Chart(system_df)
        .mark_bar(
            color=ON_TIME_GREEN,
            cornerRadiusTopLeft=4,
            cornerRadiusTopRight=4,
        )
        .encode(
            x=route_axis(),
            y=alt.Y(
                "ridershipperrevhour:Q",
                title="Ridership per Revenue Hour",
            ),
            tooltip=[
                alt.Tooltip("routes:N", title="Route"),
                alt.Tooltip(
                    "ridershipperrevhour:Q",
                    title="Overall Ridership per Revenue Hour",
                    format=".2f",
                ),
            ],
        )
        .properties(
            height=390,
            title="Overall Ridership per Revenue Hour",
        )
    )

    st.altair_chart(
        format_chart(overall_productivity_chart),
        use_container_width=True,
    )

    productivity_by_day = system_df[
        [
            "routes",
            "weekdayridershipperrevhour",
            "saturdayridershipperrevhour",
            "sundayridershipperrevhour",
        ]
    ].melt(
        id_vars="routes",
        var_name="service_day",
        value_name="ridership_per_revenue_hour",
    )

    productivity_by_day["service_day"] = (
        productivity_by_day["service_day"].replace(
            {
                "weekdayridershipperrevhour": "Weekday",
                "saturdayridershipperrevhour": "Saturday",
                "sundayridershipperrevhour": "Sunday",
            }
        )
    )

    productivity_day_chart = (
        alt.Chart(productivity_by_day)
        .mark_bar(cornerRadiusTopLeft=3, cornerRadiusTopRight=3)
        .encode(
            x=route_axis(),
            xOffset=alt.XOffset(
                "service_day:N",
                sort=["Weekday", "Saturday", "Sunday"],
            ),
            y=alt.Y(
                "ridership_per_revenue_hour:Q",
                title="Ridership per Revenue Hour",
            ),
            color=alt.Color(
                "service_day:N",
                title="Service Day",
                sort=["Weekday", "Saturday", "Sunday"],
                scale=alt.Scale(
                    domain=["Weekday", "Saturday", "Sunday"],
                    range=[
                        WEEKDAY_BLUE,
                        SATURDAY_GOLD,
                        SUNDAY_GREEN,
                    ],
                ),
            ),
            tooltip=[
                alt.Tooltip("routes:N", title="Route"),
                alt.Tooltip("service_day:N", title="Service Day"),
                alt.Tooltip(
                    "ridership_per_revenue_hour:Q",
                    title="Ridership per Revenue Hour",
                    format=".2f",
                ),
            ],
        )
        .properties(
            height=420,
            title="Ridership per Revenue Hour by Service Day",
        )
    )

    st.altair_chart(
        format_chart(productivity_day_chart),
        use_container_width=True,
    )

    section_header(
        "Complete Spring 2026 System Summary",
        "The table below contains every field from the system-summary CSV.",
    )

    display_columns = {
        "routes": "Route",
        "totalavgdailyboardings": "Total Avg Daily Boardings",
        "totalboarding": "Total Boardings",
        "totalboardingweekday": "Total Boardings – Weekday",
        "totalboardingsaturday": "Total Boardings – Saturday",
        "totalboardingsunday": "Total Boardings – Sunday",
        "totalaveragedailyweekdayboarding": "Avg Daily Boardings – Weekday",
        "totalaveragedailysaturdayboarding": "Avg Daily Boardings – Saturday",
        "totalaveragedailysundayboarding": "Avg Daily Boardings – Sunday",
        "avgmedianload": "Avg Median Load",
        "avgearly": "Avg Early (%)",
        "avgontime": "Avg On-Time (%)",
        "avglate": "Avg Late (%)",
        "totalseasonalrevenuemiles": "Total Seasonal Revenue Miles",
        "averagedailyrevenuemilesweekday": "Avg Daily Revenue Miles – Weekday",
        "averagedailyrevenuemilessaturday": "Avg Daily Revenue Miles – Saturday",
        "averagedailyrevenuemilessunday": "Avg Daily Revenue Miles – Sunday",
        "totaltripcount": "Total Trip Count",
        "totalseasonalrevenuehours": "Total Seasonal Revenue Hours",
        "averagedailyrevenuehoursweekday": "Avg Daily Revenue Hours – Weekday",
        "averagedailyrevenuehourssaturday": "Avg Daily Revenue Hours – Saturday",
        "averagedailyrevenuehourssunday": "Avg Daily Revenue Hours – Sunday",
        "ridershipperrevhour": "Ridership per Revenue Hour",
        "weekdayridershipperrevhour": "Weekday Ridership per Revenue Hour",
        "saturdayridershipperrevhour": "Saturday Ridership per Revenue Hour",
        "sundayridershipperrevhour": "Sunday Ridership per Revenue Hour",
    }

    available_display_columns = {
        key: value
        for key, value in display_columns.items()
        if key in system_df.columns
    }

    complete_summary = system_df[
        list(available_display_columns.keys())
    ].rename(columns=available_display_columns)

    st.dataframe(
        complete_summary,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Route": st.column_config.TextColumn("Route", pinned=True),
            "Avg Early (%)": st.column_config.NumberColumn(
                "Avg Early (%)",
                format="%.1f%%",
            ),
            "Avg On-Time (%)": st.column_config.NumberColumn(
                "Avg On-Time (%)",
                format="%.1f%%",
            ),
            "Avg Late (%)": st.column_config.NumberColumn(
                "Avg Late (%)",
                format="%.1f%%",
            ),
        },
    )


# ==================================================
# 9. TAB 2 — RIDERSHIP TREND SINCE 2023
# ==================================================

with tab2:
    st.markdown("### Ridership Trend")

    route_options = (
        trend_df[["route", "route_sort"]]
        .dropna(subset=["route"])
        .drop_duplicates(subset=["route"])
        .sort_values(
            by=["route_sort", "route"],
            na_position="last",
        )["route"]
        .astype(str)
        .tolist()
    )

    route_filter_options = ["System Total"] + route_options

    selected_route = st.selectbox(
        "Route",
        options=route_filter_options,
        index=0,
        key="ridership_trend_route",
    )

    if selected_route == "System Total":
        chart_data = (
            trend_df.groupby("yearmonth", as_index=False)[
                "totalfarecounts"
            ].sum()
        )
        chart_data["route"] = "System Total"
    else:
        chart_data = trend_df.loc[
            trend_df["route"] == selected_route,
            ["route", "yearmonth", "totalfarecounts"],
        ].copy()

    if chart_data.empty:
        st.warning("No ridership data are available for this selection.")
        st.stop()

    chart_data = chart_data.sort_values("yearmonth").reset_index(drop=True)

    latest_month = chart_data["yearmonth"].max()
    previous_month = latest_month - pd.DateOffset(months=1)

    latest_total = chart_data.loc[
        chart_data["yearmonth"] == latest_month,
        "totalfarecounts",
    ].sum()

    previous_total = chart_data.loc[
        chart_data["yearmonth"] == previous_month,
        "totalfarecounts",
    ].sum()

    monthly_change = (
        ((latest_total - previous_total) / previous_total) * 100
        if previous_total > 0
        else 0
    )

    latest_year = latest_month.year
    latest_year_total = chart_data.loc[
        chart_data["yearmonth"].dt.year == latest_year,
        "totalfarecounts",
    ].sum()

    trend_k1, trend_k2, trend_k3, trend_k4 = st.columns(4)
    trend_k1.metric("Latest Month", latest_month.strftime("%B %Y"))
    trend_k2.metric("Latest Monthly Ridership", f"{latest_total:,.0f}")
    trend_k3.metric(
        "Change from Previous Month",
        f"{monthly_change:+.1f}%",
    )
    trend_k4.metric(
        f"{latest_year} Ridership to Date",
        f"{latest_year_total:,.0f}",
    )

    section_header(
        "Monthly Ridership Trend",
        f"Monthly fare counts for {selected_route}.",
    )

    trend_chart = (
        alt.Chart(chart_data)
        .mark_line(
            color=BFT_BLUE,
            point=alt.OverlayMarkDef(filled=True, size=55),
            strokeWidth=3,
        )
        .encode(
            x=alt.X(
                "yearmonth:T",
                title="Month",
                axis=alt.Axis(format="%b %Y", labelAngle=-45),
            ),
            y=alt.Y(
                "totalfarecounts:Q",
                title="Total Fare Counts",
                scale=alt.Scale(zero=False),
            ),
            tooltip=[
                alt.Tooltip(
                    "yearmonth:T",
                    title="Month",
                    format="%B %Y",
                ),
                alt.Tooltip("route:N", title="Route"),
                alt.Tooltip(
                    "totalfarecounts:Q",
                    title="Fare Counts",
                    format=",.0f",
                ),
            ],
        )
        .properties(
            height=500,
            title=f"Monthly Fare Counts – {selected_route}",
        )
        .interactive()
    )

    st.altair_chart(
        format_chart(trend_chart),
        use_container_width=True,
    )

    annual_ridership = (
        chart_data.assign(year=chart_data["yearmonth"].dt.year)
        .groupby("year", as_index=False)["totalfarecounts"]
        .sum()
    )

    section_header(
        "Annual Ridership",
        "Annual fare-count totals for the selected route.",
    )

    annual_chart = (
        alt.Chart(annual_ridership)
        .mark_bar(
            color=BFT_GOLD,
            cornerRadiusTopLeft=5,
            cornerRadiusTopRight=5,
        )
        .encode(
            x=alt.X("year:O", title="Year"),
            y=alt.Y(
                "totalfarecounts:Q",
                title="Annual Fare Counts",
            ),
            tooltip=[
                alt.Tooltip("year:O", title="Year"),
                alt.Tooltip(
                    "totalfarecounts:Q",
                    title="Annual Fare Counts",
                    format=",.0f",
                ),
            ],
        )
        .properties(
            height=390,
            title=f"Annual Ridership – {selected_route}",
        )
    )

    st.altair_chart(
        format_chart(annual_chart),
        use_container_width=True,
    )

    with st.expander("View ridership trend data"):
        st.dataframe(
            chart_data[
                ["route", "yearmonth", "totalfarecounts"]
            ].rename(
                columns={
                    "route": "Route",
                    "yearmonth": "Month",
                    "totalfarecounts": "Total Fare Counts",
                }
            ),
            use_container_width=True,
            hide_index=True,
            column_config={
                "Month": st.column_config.DateColumn(
                    "Month",
                    format="MMM YYYY",
                ),
                "Total Fare Counts": st.column_config.NumberColumn(
                    "Total Fare Counts",
                    format="%,.0f",
                ),
            },
        )


with tab3:
    st.markdown("### Spring 2026 Route Profiles")
    st.caption(
        "Route performance by service day, direction, and matched trip pair."
    )

    if paired_df.empty or trip_df.empty:
        st.warning("No usable paired route-profile data were found in the workbook.")
    else:
        route_options = sorted(
            paired_df["route_short_name"].dropna().unique().tolist(),
            key=route_sort_key,
        )

        st.caption(
            f"{len(route_options)} route sheets loaded from {ROUTE_PROFILE_SOURCE}. "
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


# ==================================================
# 10. FOOTER
# ==================================================

st.divider()

st.caption(
    f"Latest GitHub sources: {system_source_path}, {trend_source_path}, and "
    f"{ROUTE_PROFILE_SOURCE} • Branch: {GITHUB_BRANCH} • Ben Franklin Transit"
)
