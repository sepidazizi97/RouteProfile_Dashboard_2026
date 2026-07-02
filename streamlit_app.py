import streamlit as st
import pandas as pd
import altair as alt
import snowflake.connector

# ==================================================
# 1. PAGE SETUP
# ==================================================

st.set_page_config(
    page_title="BFT Route Performance Dashboard",
    layout="wide"
)

# ==================================================
# 2. GLOBAL COLORS
# ==================================================

BFT_NAVY = "#12355B"
ON_TIME_GREEN = "#2E8B57"
EARLY_GOLD = "#E3A008"
LATE_RED = "#D64545"
DIRECTION_BLUE = "#2563EB"
DIRECTION_GOLD = "#F2B705"

# ==================================================
# 3. STYLING
# ==================================================

st.markdown(
    f"""
    <style>
    .main-title {{
        font-size: 38px;
        font-weight: 800;
        color: {BFT_NAVY};
    }}
    .sub-title {{
        color: #6B7280;
        font-size: 16px;
        margin-bottom: 24px;
    }}
    .section-header {{
        font-size: 24px;
        font-weight: 750;
        color: {BFT_NAVY};
        margin-top: 28px;
        margin-bottom: 10px;
    }}
    .small-note {{
        color: #6B7280;
        font-size: 14px;
    }}
    </style>
    """,
    unsafe_allow_html=True
)

st.markdown(
    '<div class="main-title">BFT Route Performance Dashboard</div>',
    unsafe_allow_html=True
)

st.markdown(
    '<div class="sub-title">Monthly route profile, seasonal route profile, revenue hours, and revenue miles</div>',
    unsafe_allow_html=True
)

# ==================================================
# 4. LOAD DATA FROM SNOWFLAKE
# ==================================================

@st.cache_data
def load_data():
    conn = snowflake.connector.connect(
        account=st.secrets["snowflake"]["account"],
        user=st.secrets["snowflake"]["user"],
        password=st.secrets["snowflake"]["password"],
        warehouse=st.secrets["snowflake"]["warehouse"],
        database=st.secrets["snowflake"]["database"],
        schema=st.secrets["snowflake"]["schema"],
        role=st.secrets["snowflake"]["role"],
    )

    monthly = pd.read_sql("SELECT * FROM V_ROUTE_PROFILE_MONTHLY", conn)
    seasonal = pd.read_sql("SELECT * FROM V_ROUTE_PROFILE_SEASONAL", conn)
    revenue = pd.read_sql("SELECT * FROM V_REV_HOUR_MILE", conn)

    conn.close()

    monthly.columns = monthly.columns.str.lower()
    seasonal.columns = seasonal.columns.str.lower()
    revenue.columns = revenue.columns.str.lower()

    return monthly, seasonal, revenue


monthly_df, seasonal_df, revenue_df = load_data()

# ==================================================
# 5. CLEAN DATA
# ==================================================

def clean_route_profile(df):
    df = df.copy()

    text_cols = [
        "trip_start_time",
        "route_short_name",
        "direction",
        "service_day"
    ]

    for col in text_cols:
        df[col] = df[col].astype(str)

    numeric_cols = [
        "total_fare_counts",
        "median_passenger_load",
        "percent_on_time",
        "percent_early",
        "percent_late"
    ]

    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    return df


monthly_df = clean_route_profile(monthly_df)
seasonal_df = clean_route_profile(seasonal_df)

revenue_df["route_short_name"] = revenue_df["route_short_name"].astype(str)
revenue_df["direction"] = revenue_df["direction"].astype(str)

for col in ["revenue_hours", "revenue_miles", "trip_count"]:
    revenue_df[col] = pd.to_numeric(revenue_df[col], errors="coerce")

# ==================================================
# 6. REUSABLE CHART FUNCTION FOR MONTHLY/SEASONAL
# ==================================================

def route_profile_charts(df, title_label):
    service_day_order = ["Weekday", "Saturday", "Sunday"]

    st.markdown(f"### {title_label}")

    total_boardings = df["total_fare_counts"].sum()
    avg_load = df["median_passenger_load"].mean()
    avg_otp = df["percent_on_time"].mean()
    avg_early = df["percent_early"].mean()
    avg_late = df["percent_late"].mean()

    k1, k2, k3, k4, k5 = st.columns(5)

    k1.metric("Total Boardings", f"{total_boardings:,.0f}")
    k2.metric("Avg Median Load", f"{avg_load:.1f}")
    k3.metric("Avg On-Time", f"{avg_otp:.1f}%")
    k4.metric("Avg Early", f"{avg_early:.1f}%")
    k5.metric("Avg Late", f"{avg_late:.1f}%")

    st.divider()

    available_days = df["service_day"].dropna().unique().tolist()
    ordered_days = [day for day in service_day_order if day in available_days]

    if not ordered_days:
        st.warning("No service day data available for this selection.")
        return

    day_tabs = st.tabs(ordered_days)

    for day_tab, service_day in zip(day_tabs, ordered_days):
        with day_tab:
            service_df = df[df["service_day"] == service_day].copy()
            service_df = service_df.sort_values(["trip_start_time", "direction"])

            st.markdown(
                f'<div class="section-header">{service_day} Service</div>',
                unsafe_allow_html=True
            )

            # -----------------------------
            # Boardings chart
            # -----------------------------

            st.markdown("#### Boardings per Trip by Direction")

            boardings_data = (
                service_df
                .groupby(["trip_start_time", "direction"], as_index=False)["total_fare_counts"]
                .sum()
                .rename(columns={"total_fare_counts": "boardings"})
            )

            boardings_chart = (
                alt.Chart(boardings_data)
                .mark_bar()
                .encode(
                    x=alt.X("trip_start_time:N", title="Trip Start Time", sort=None),
                    y=alt.Y("boardings:Q", title="Boardings"),
                    color=alt.Color("direction:N", title="Direction"),
                    xOffset=alt.XOffset("direction:N"),
                    tooltip=[
                        alt.Tooltip("trip_start_time:N", title="Trip Start Time"),
                        alt.Tooltip("direction:N", title="Direction"),
                        alt.Tooltip("boardings:Q", title="Boardings", format=",.0f")
                    ]
                )
                .properties(height=360)
            )

            st.altair_chart(boardings_chart, use_container_width=True)

            # -----------------------------
            # Median passenger load chart
            # -----------------------------

            st.markdown("#### Median Passenger Load by Trip and Direction")

            load_data = (
                service_df
                .groupby(["trip_start_time", "direction"], as_index=False)["median_passenger_load"]
                .mean()
                .rename(columns={"median_passenger_load": "avg_median_passenger_load"})
            )

            load_chart = (
                alt.Chart(load_data)
                .mark_bar()
                .encode(
                    x=alt.X("trip_start_time:N", title="Trip Start Time", sort=None),
                    y=alt.Y("avg_median_passenger_load:Q", title="Median Passenger Load"),
                    color=alt.Color("direction:N", title="Direction"),
                    xOffset=alt.XOffset("direction:N"),
                    tooltip=[
                        alt.Tooltip("trip_start_time:N", title="Trip Start Time"),
                        alt.Tooltip("direction:N", title="Direction"),
                        alt.Tooltip(
                            "avg_median_passenger_load:Q",
                            title="Median Passenger Load",
                            format=".1f"
                        )
                    ]
                )
                .properties(height=360)
            )

            st.altair_chart(load_chart, use_container_width=True)

            # -----------------------------
            # On-time performance chart
            # -----------------------------

            st.markdown("#### On-Time Performance by Trip")

            otp_long = service_df.melt(
                id_vars=["trip_start_time", "direction"],
                value_vars=[
                    "percent_on_time",
                    "percent_early",
                    "percent_late"
                ],
                var_name="performance_type",
                value_name="percent"
            )

            otp_long["performance_type"] = otp_long["performance_type"].replace({
                "percent_on_time": "On-Time",
                "percent_early": "Early",
                "percent_late": "Late"
            })

            otp_chart = (
                alt.Chart(otp_long)
                .mark_bar()
                .encode(
                    x=alt.X(
                        "trip_start_time:N",
                        title="Trip Start Time",
                        sort=None,
                        axis=alt.Axis(labelAngle=-90)
                    ),
                    y=alt.Y(
                        "percent:Q",
                        title="Percent",
                        stack="normalize",
                        axis=alt.Axis(format="%")
                    ),
                    color=alt.Color(
                        "performance_type:N",
                        title="Performance",
                        scale=alt.Scale(
                            domain=["On-Time", "Early", "Late"],
                            range=[
                                ON_TIME_GREEN,
                                EARLY_GOLD,
                                LATE_RED
                            ]
                        ),
                        legend=alt.Legend(
                            orient="top",
                            direction="horizontal",
                            title=None
                        )
                    ),
                    row=alt.Row(
                        "direction:N",
                        title="Direction"
                    ),
                    tooltip=[
                        alt.Tooltip("trip_start_time:N", title="Trip Start Time"),
                        alt.Tooltip("direction:N", title="Direction"),
                        alt.Tooltip("performance_type:N", title="Performance"),
                        alt.Tooltip("percent:Q", title="Percent", format=".1f")
                    ]
                )
                .properties(height=230)
            )

            st.altair_chart(otp_chart, use_container_width=True)

            with st.expander(f"View {service_day} trip details"):
                st.dataframe(service_df, use_container_width=True)


# ==================================================
# 7. DASHBOARD TABS
# ==================================================

tab1, tab2, tab3 = st.tabs([
    "📊 Monthly Route Profile",
    "🌤 Seasonal Route Profile",
    "🚍 Revenue Hours & Miles"
])

# ==================================================
# 8. TAB 1 — MONTHLY ROUTE PROFILE
# ==================================================

with tab1:
    st.markdown("### Monthly Filters")

    month_order = (
        monthly_df[["month", "month_number"]]
        .drop_duplicates()
        .sort_values("month_number")
    )

    month_options = month_order["month"].tolist()
    route_options = sorted(monthly_df["route_short_name"].dropna().unique().tolist())

    c1, c2 = st.columns(2)

    with c1:
        selected_month = st.selectbox(
            "Month",
            month_options,
            key="monthly_month"
        )

    with c2:
        selected_route_monthly = st.selectbox(
            "Route",
            route_options,
            key="monthly_route"
        )

    monthly_filtered = monthly_df[
        (monthly_df["month"] == selected_month) &
        (monthly_df["route_short_name"] == selected_route_monthly)
    ].copy()

    route_profile_charts(
        monthly_filtered,
        f"Monthly Route Profile | Route {selected_route_monthly} | {selected_month} 2026"
    )

# ==================================================
# 9. TAB 2 — SEASONAL ROUTE PROFILE
# ==================================================

with tab2:
    st.markdown("### Seasonal Filters")

    season_col = "season_period" if "season_period" in seasonal_df.columns else "season"

    season_options = sorted(seasonal_df[season_col].dropna().unique().tolist())
    seasonal_route_options = sorted(seasonal_df["route_short_name"].dropna().unique().tolist())

    c1, c2 = st.columns(2)

    with c1:
        selected_season = st.selectbox(
            "Season",
            season_options,
            key="seasonal_season"
        )

    with c2:
        selected_route_seasonal = st.selectbox(
            "Route",
            seasonal_route_options,
            key="seasonal_route"
        )

    seasonal_filtered = seasonal_df[
        (seasonal_df[season_col] == selected_season) &
        (seasonal_df["route_short_name"] == selected_route_seasonal)
    ].copy()

    route_profile_charts(
        seasonal_filtered,
        f"Seasonal Route Profile | Route {selected_route_seasonal} | {selected_season}"
    )

# ==================================================
# 10. TAB 3 — REVENUE HOURS & REVENUE MILES
# ==================================================

with tab3:
    st.markdown("### 🚍 Revenue Hours & Revenue Miles")
    st.caption("Compare revenue hours, revenue miles, and trips by route and direction for a selected month.")

    # -----------------------------
    # Revenue month filter
    # -----------------------------

    rev_month_order = (
        revenue_df[["month", "month_number"]]
        .drop_duplicates()
        .sort_values("month_number")
    )

    rev_month_options = rev_month_order["month"].tolist()

    selected_rev_month = st.selectbox(
        "Revenue Month",
        rev_month_options,
        key="revenue_month"
    )

    rev_filtered = revenue_df[
        revenue_df["month"] == selected_rev_month
    ].copy()

    # -----------------------------
    # Route and direction summary
    # -----------------------------

    route_summary = (
        rev_filtered
        .groupby(["route_short_name", "direction"], as_index=False)
        .agg(
            revenue_hours=("revenue_hours", "sum"),
            revenue_miles=("revenue_miles", "sum"),
            trip_count=("trip_count", "sum")
        )
    )

    route_summary["route_short_name"] = route_summary["route_short_name"].astype(str)
    route_summary["direction"] = route_summary["direction"].astype(str)

    route_summary["direction_group"] = route_summary["direction"].apply(
        lambda x: "First Direction" if x in ["E", "N", "OB", "CW"] else "Second Direction"
    )

    route_summary["direction_order"] = route_summary["direction_group"].map({
        "First Direction": 0,
        "Second Direction": 1
    })

    route_summary = route_summary.sort_values(
        ["route_short_name", "direction_order", "direction"]
    )

    # -----------------------------
    # KPI cards
    # -----------------------------

    total_hours = route_summary["revenue_hours"].sum()
    total_miles = route_summary["revenue_miles"].sum()
    total_trips = route_summary["trip_count"].sum()
    total_routes = route_summary["route_short_name"].nunique()

    r1, r2, r3, r4 = st.columns(4)

    r1.metric("Total Revenue Hours", f"{total_hours:,.1f}")
    r2.metric("Total Revenue Miles", f"{total_miles:,.1f}")
    r3.metric("Total Trips", f"{total_trips:,.0f}")
    r4.metric("Routes", f"{total_routes:,.0f}")

    st.divider()

    # -----------------------------
    # Reusable revenue chart
    # -----------------------------

    def paired_route_chart(data, y_col, y_title, chart_title, tooltip_format):
        return (
            alt.Chart(data)
            .mark_bar(
                size=8,
                cornerRadiusTopLeft=3,
                cornerRadiusTopRight=3
            )
            .encode(
                x=alt.X(
                    "route_short_name:N",
                    title="Route",
                    sort=None,
                    axis=alt.Axis(
                        labelAngle=0,
                        labelFontSize=11,
                        labelPadding=8
                    )
                ),
                xOffset=alt.XOffset(
                    "direction_group:N",
                    sort=["First Direction", "Second Direction"],
                    scale=alt.Scale(
                        paddingInner=0.35,
                        paddingOuter=0.35
                    )
                ),
                y=alt.Y(
                    y_col + ":Q",
                    title=y_title
                ),
                color=alt.Color(
                    "direction_group:N",
                    title=None,
                    scale=alt.Scale(
                        domain=["First Direction", "Second Direction"],
                        range=[
                            DIRECTION_BLUE,
                            DIRECTION_GOLD
                        ]
                    ),
                    legend=None
                ),
                tooltip=[
                    alt.Tooltip("route_short_name:N", title="Route"),
                    alt.Tooltip("direction:N", title="Direction"),
                    alt.Tooltip(y_col + ":Q", title=y_title, format=tooltip_format)
                ]
            )
            .properties(
                height=390,
                title=chart_title
            )
        )

    # -----------------------------
    # Revenue miles chart
    # -----------------------------

    st.markdown("#### Revenue Miles by Route and Direction")

    st.altair_chart(
        paired_route_chart(
            route_summary,
            "revenue_miles",
            "Revenue Miles",
            "Revenue Miles by Route and Direction",
            ",.1f"
        ),
        use_container_width=True
    )

    # -----------------------------
    # Revenue hours chart
    # -----------------------------

    st.markdown("#### Revenue Hours by Route and Direction")

    st.altair_chart(
        paired_route_chart(
            route_summary,
            "revenue_hours",
            "Revenue Hours",
            "Revenue Hours by Route and Direction",
            ",.1f"
        ),
        use_container_width=True
    )

    # -----------------------------
    # Trips chart
    # -----------------------------

    st.markdown("#### Trips by Route and Direction")

    st.altair_chart(
        paired_route_chart(
            route_summary,
            "trip_count",
            "Trip Count",
            "Trips by Route and Direction",
            ",.0f"
        ),
        use_container_width=True
    )

    # -----------------------------
    # Detail table
    # -----------------------------

    with st.expander("View revenue route and direction summary table"):
        st.dataframe(
            route_summary[
                [
                    "route_short_name",
                    "direction",
                    "revenue_hours",
                    "revenue_miles",
                    "trip_count"
                ]
            ],
            use_container_width=True
        )

    st.caption("Blue and gold represent the two directions. Hover over each bar to see the exact direction.")
