from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pandas as pd
import streamlit as st

from app.services.opening_analysis_service import OpeningAnalysisService
from app.web.components.auth import get_current_user, require_auth
from app.web.components.charts import opening_wins_losses_bar


require_auth()

service = OpeningAnalysisService()
players = service.list_players()

TIMEFRAME_OPTIONS = {
    "Last Week": 7,
    "Last Month": 30,
    "Last 3 Months": 90,
    "Last 6 Months": 180,
    "Last Year": 365,
    "All": None,
}

st.title("Opening Analysis")

if not players:
    st.warning("No player data available yet. Sync games first to populate opening analytics.")
    st.stop()

user = get_current_user()
email_local = ""
if user and "@" in user.email:
    email_local = user.email.split("@", 1)[0].lower()

player_options = ["All"] + players
default_player_index = 0
if email_local and email_local in players:
    default_player_index = player_options.index(email_local)

col1, col2, col3 = st.columns(3)
with col1:
    selected_player = st.selectbox("Player", player_options, index=default_player_index)
with col2:
    selected_timeframe = st.selectbox("Timeframe", list(TIMEFRAME_OPTIONS.keys()), index=4)
with col3:
    selected_color = st.selectbox("Played As", ["All", "White", "Black"])

timeframe_days = TIMEFRAME_OPTIONS[selected_timeframe]

df = service.club_recent_games()

if timeframe_days is not None:
    cutoff = datetime.now(UTC) - timedelta(days=timeframe_days)
    played = pd.to_datetime(df["played_at"], utc=True, errors="coerce")
    df = df[played >= cutoff].copy()

if selected_player != "All":
    df = df[df["player"] == selected_player.lower()]

if selected_color != "All":
    df = df[df["color"] == selected_color]

if df.empty:
    st.info("No games found for the selected filters.")
    st.stop()

metrics_df = service.opening_metrics_table(df)

st.plotly_chart(
    opening_wins_losses_bar(metrics_df),
    width="stretch",
    config={"displaylogo": False, "plotlyServerURL": ""},
)
