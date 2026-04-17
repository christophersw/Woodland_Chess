from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pandas as pd
import streamlit as st

from app.services.opening_analysis_service import OpeningAnalysisService, OpeningMetricsFilters
from app.web.components.auth import get_current_user, require_auth
from app.web.components.charts import (
    opening_bubble,
    opening_flow_sankey,
    opening_frequency_bar,
    opening_timeline_heatmap,
    opening_wdl_stacked,
    player_fingerprint_radar,
)


require_auth()

service = OpeningAnalysisService()
players = service.list_players()

TIMEFRAME_OPTIONS = [
    ("1m", 30),
    ("3m", 90),
    ("6m", 180),
    ("12m", 365),
    ("All", None),
]


def _apply_timeframe(df, timeframe_days: int | None):
    if df.empty or timeframe_days is None:
        return df

    cutoff = datetime.now(UTC) - timedelta(days=timeframe_days)
    played = pd.to_datetime(df["played_at"], utc=True, errors="coerce")
    return df[played >= cutoff].copy()


def _timeline_bucket_for_timeframe(timeframe_days: int | None) -> str | None:
    if timeframe_days is None:
        return None
    if timeframe_days <= 45:
        return "D"
    if timeframe_days <= 240:
        return "W"
    return "M"


def _selected_opening_from_chart_event(event) -> str | None:
    if not event:
        return None

    if isinstance(event, dict):
        selection = event.get("selection")
    else:
        selection = getattr(event, "selection", None)

    if not selection:
        return None

    if isinstance(selection, dict):
        points = selection.get("points") or []
    else:
        points = getattr(selection, "points", None) or []

    if not points:
        return None

    point = points[0]
    if not isinstance(point, dict):
        return None

    opening = point.get("y") or point.get("label") or point.get("text")
    if not opening:
        custom = point.get("customdata")
        if isinstance(custom, (list, tuple)) and custom:
            opening = custom[0]
        elif isinstance(custom, str):
            opening = custom

    opening_text = str(opening or "").strip()
    return opening_text or None


def _navigate_to_opening_search(selected_opening: str, source_key: str) -> None:
    if not selected_opening:
        return

    last_clicked_opening = st.session_state.get("last_clicked_opening")
    last_clicked_source = st.session_state.get("last_clicked_opening_source")
    if selected_opening == last_clicked_opening and source_key == last_clicked_source:
        return

    st.session_state["last_clicked_opening"] = selected_opening
    st.session_state["last_clicked_opening_source"] = source_key
    st.session_state["pending_opening_search"] = selected_opening
    st.switch_page("app/web/pages/game_search.py")

st.title("Opening Analysis")
st.caption("Opening analytics across games in the selected timeframe (safety cap: 999).")

timeframe_labels = [label for label, _ in TIMEFRAME_OPTIONS]
selected_timeframe = st.selectbox("Timeframe", timeframe_labels, index=timeframe_labels.index("6m"))
timeframe_days = dict(TIMEFRAME_OPTIONS)[selected_timeframe]

if not players:
    st.warning("No player data available yet. Sync games first to populate opening analytics.")
    st.stop()

club_df = service.club_recent_games()
club_df = _apply_timeframe(club_df, timeframe_days)
if club_df.empty:
    st.info("No games found in the selected timeframe.")
    st.stop()

user = get_current_user()
email_local = ""
if user and "@" in user.email:
    email_local = user.email.split("@", 1)[0].lower()

default_player = players[0]
if email_local and email_local in players:
    default_player = email_local

club_col1, club_col2, club_col3 = st.columns(3)
club_col1.metric("Club Participant-Games", len(club_df))
club_col2.metric("Unique Openings", club_df["opening_label"].nunique())
club_col3.metric("Tracked Members", club_df["player"].nunique())

st.markdown("## Club Data")
club_filters_left, club_filters_right = st.columns([2, 1])
with club_filters_left:
    table_player = st.selectbox("Filter table by player", ["All"] + players, index=0)
with club_filters_right:
    table_color = st.selectbox("Filter table by color", ["All", "White", "Black"], index=0)

metrics_filters = OpeningMetricsFilters(
    player=None if table_player == "All" else table_player,
    color=None if table_color == "All" else table_color,
)
club_df_filtered = club_df.copy()
if metrics_filters.player:
    club_df_filtered = club_df_filtered[club_df_filtered["player"] == metrics_filters.player.lower()]
if metrics_filters.color:
    club_df_filtered = club_df_filtered[club_df_filtered["color"] == metrics_filters.color]

club_metrics_df = service.opening_metrics_table(club_df_filtered)

c1, c2 = st.columns(2)
with c1:
    st.caption("Tip: click a bar to open matching games in Game Search.")
    frequency_fig = opening_frequency_bar(club_metrics_df)
    frequency_event = st.plotly_chart(
        frequency_fig,
        width="stretch",
        config={"displaylogo": False, "plotlyServerURL": ""},
        on_select="rerun",
        key="club_opening_frequency_chart",
    )
    selected_opening = _selected_opening_from_chart_event(frequency_event)
    _navigate_to_opening_search(selected_opening or "", source_key="club_frequency")
with c2:
    st.plotly_chart(
        opening_wdl_stacked(club_metrics_df),
        width="stretch",
        config={"displaylogo": False, "plotlyServerURL": ""},
    )

bubble_fig = opening_bubble(club_metrics_df)
bubble_event = st.plotly_chart(
    bubble_fig,
    width="stretch",
    config={"displaylogo": False, "plotlyServerURL": ""},
    on_select="rerun",
    key="club_opening_bubble_chart",
)
bubble_selected_opening = _selected_opening_from_chart_event(bubble_event)
_navigate_to_opening_search(bubble_selected_opening or "", source_key="club_bubble")

st.subheader("Sortable Metrics Table")
if club_metrics_df.empty:
    st.info("No openings match the selected filters.")
else:
    table_df = club_metrics_df.rename(
        columns={
            "opening_label": "Opening",
            "games": "Games",
            "wins": "Wins",
            "draws": "Draws",
            "losses": "Losses",
            "win_pct": "Win %",
            "draw_pct": "Draw %",
            "loss_pct": "Loss %",
            "avg_game_length": "Avg Game Length (plies)",
            "avg_move10_cp": "Avg Engine Score @ Move 10",
        }
    )
    st.dataframe(
        table_df,
        width="stretch",
        hide_index=True,
        column_config={
            "Win %": st.column_config.NumberColumn(format="%.1f"),
            "Draw %": st.column_config.NumberColumn(format="%.1f"),
            "Loss %": st.column_config.NumberColumn(format="%.1f"),
            "Avg Game Length (plies)": st.column_config.NumberColumn(format="%.1f"),
            "Avg Engine Score @ Move 10": st.column_config.NumberColumn(format="%.1f"),
        },
    )

club_timeline_df = service.opening_timeline(
    club_df_filtered,
    top_n=20,
    bucket=_timeline_bucket_for_timeframe(timeframe_days),
)
heatmap_player_label = table_player if table_player != "All" else "All"
heatmap_color_label = table_color if table_color != "All" else "All"
st.caption(
    f"Heatmap filters - timeframe: {selected_timeframe}, player: {heatmap_player_label}, color: {heatmap_color_label}."
)
club_heatmap_fig = opening_timeline_heatmap(
    club_timeline_df,
    title=f"Top 20 Openings Timeline (Club, {selected_timeframe}, {heatmap_player_label}, {heatmap_color_label})",
)
club_heatmap_event = st.plotly_chart(
    club_heatmap_fig,
    width="stretch",
    config={"displaylogo": False, "plotlyServerURL": ""},
    on_select="rerun",
    key="club_opening_timeline_heatmap",
)
heatmap_selected_opening = _selected_opening_from_chart_event(club_heatmap_event)
_navigate_to_opening_search(heatmap_selected_opening or "", source_key="club_heatmap")

st.markdown("## Member View")
selected_player = st.selectbox(
    "Member",
    players,
    index=players.index(default_player) if default_player in players else 0,
)

player_df = service.player_recent_games(selected_player)
player_df = _apply_timeframe(player_df, timeframe_days)
if player_df.empty:
    st.info("No games found for this member in the selected timeframe.")
    st.stop()

member_col1, member_col2, member_col3 = st.columns(3)
member_col1.metric("Games", len(player_df))
member_col2.metric("Openings", player_df["opening_label"].nunique())
member_col3.metric("Win %", f"{(player_df['result'].eq('Win').mean() * 100):.1f}")

fingerprint_df = service.opening_family_fingerprint(player_df)
player_timeline_df = service.opening_timeline(
    player_df,
    top_n=20,
    bucket=_timeline_bucket_for_timeframe(timeframe_days),
)
flow_df = service.opening_flow(player_df)

left, right = st.columns(2)
with left:
    st.plotly_chart(
        player_fingerprint_radar(fingerprint_df),
        width="stretch",
        config={"displaylogo": False, "plotlyServerURL": ""},
    )
with right:
    st.plotly_chart(
        opening_timeline_heatmap(player_timeline_df, title=f"Top 20 Openings Timeline ({selected_player})"),
        width="stretch",
        config={"displaylogo": False, "plotlyServerURL": ""},
    )

st.plotly_chart(
    opening_flow_sankey(flow_df),
    width="stretch",
    config={"displaylogo": False, "plotlyServerURL": ""},
)
