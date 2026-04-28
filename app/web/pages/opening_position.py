"""Opening Position detail page.

URL: /opening-position?opening_id=<int>

Shows a static board of the opening position plus:
  - Timeframe + player filters
  - Opening share pie (this opening vs all others)
  - Per-player W/D/L grouped bar
  - Per-player average accuracy horizontal bar
  - Continuation Sankey (3 moves beyond the opening)
  - Frequency-over-time line chart
  - Filterable game table
"""

from __future__ import annotations

from html import escape

import chess
import chess.svg
import pandas as pd
import streamlit as st

from app.services.opening_position_service import OpeningPositionService
from app.services.welcome_service import WelcomeService
from app.web.components.auth import require_auth
from app.web.components.html_embed import render_html_iframe
from app.web.components.charts import (
    opening_frequency_trend,
    opening_player_accuracy_bar,
    opening_share_pie,
    welcome_opening_sankey,
)

require_auth()

_svc = OpeningPositionService()
_wsvc = WelcomeService()

# ── Board colours (Du Bois palette) ──────────────────────────────────────────
_BOARD_COLORS = {
    "square light": "#F2E6D0",
    "square dark": "#1A3A2A",
    "margin": "#1A1A1A",
    "coord": "#D4A843",
}

# ── Table CSS (reuse welcome page style) ─────────────────────────────────────
_TABLE_STYLE = """
<style>
.op-table {
  width: 100%;
  border-collapse: collapse;
  border: 2px solid #1A1A1A;
  font-family: 'DM Mono', monospace;
}
.op-table thead tr { background: #1A3A2A; }
.op-table thead th {
  font-family: 'DM Mono', monospace;
  font-size: 0.65rem;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: #F2E6D0;
  font-weight: 600;
  padding: 0.45rem 0.6rem;
  text-align: left;
  border: none;
}
.op-table tbody tr:nth-child(odd)  { background: #F9F3E8; }
.op-table tbody tr:nth-child(even) { background: #EFE4CC; }
.op-table tbody tr { border-bottom: 1px solid #D4C4A0; }
.op-table td {
  padding: 0.42rem 0.6rem;
  vertical-align: middle;
  white-space: nowrap;
  font-size: 0.8rem;
}
.op-player { font-family: 'EB Garamond', Georgia, serif; font-size: 0.95rem; color: #1A1A1A; }
.op-acc   { font-weight: 700; color: #1A3A2A; }
.op-win   { color: #4A6554; font-weight: 600; }
.op-loss  { color: #B53541; font-weight: 600; }
.op-draw  { color: #4A6E8A; font-weight: 600; }
.op-date  { font-size: 0.68rem; color: #8B3A2A; }
.op-open {
  display: inline-block;
  border: 1.5px solid #1A1A1A;
  color: #1A3A2A;
  font-family: 'DM Mono', monospace;
  font-size: 0.6rem;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  padding: 2px 8px;
  text-decoration: none;
  white-space: nowrap;
}
.op-open:hover { background: #1A1A1A; color: #F2E6D0; text-decoration: none; }
</style>
"""

_ENGINE_CSS = """<style>
.dub { font-family: 'DM Mono', 'Courier New', monospace; color: #1A1A1A; margin-bottom: 1.6rem; }
.dub-head {
  border-top: 3px solid #1A1A1A; border-bottom: 1.5px solid #1A1A1A;
  display: flex; justify-content: space-between; align-items: baseline;
  padding: 5px 0 4px; margin-bottom: 16px;
}
.dub-title { font-family: 'Playfair Display SC', Georgia, serif; font-size: 0.92rem; letter-spacing: 0.07em; color: #1A3A2A; }
.dub-meta { font-size: 0.60rem; letter-spacing: 0.06em; color: #8B3A2A; text-transform: uppercase; }
.dub-row { display: grid; grid-template-columns: 140px 1fr 52px; align-items: center; gap: 0 8px; margin-bottom: 5px; }
.dub-player-lbl { font-size: 0.70rem; letter-spacing: 0.03em; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; color: #1A1A1A; }
.dub-chess { color: #8B3A2A; margin-right: 3px; }
.dub-val { font-size: 0.78rem; font-weight: 700; text-align: right; white-space: nowrap; color: #1A1A1A; }
.dub-stack { height: 26px; display: flex; border: 1.5px solid #1A1A1A; overflow: hidden; }
.dub-seg { display: flex; align-items: center; justify-content: center; font-size: 0.60rem; font-weight: 700; overflow: hidden; white-space: nowrap; color: #F2E6D0; }
.dub-win  { background: #1A3A2A; }
.dub-draw { background: #8B3A2A; }
.dub-loss { background: #B53541; }
</style>"""


def _wdl_html(stats_df: "pd.DataFrame") -> str:
    def _seg(cls: str, pct: float, lbl: str) -> str:
        txt = lbl if pct >= 9 else ""
        return f'<div class="dub-seg {cls}" style="flex:{pct:.1f}">{escape(txt)}</div>'

    rows = []
    for _, row in stats_df.iterrows():
        win = float(row["win_pct"])
        draw = float(row["draw_pct"])
        loss = float(row["loss_pct"])
        total = int(row["games"])
        segs = (
            _seg("dub-win", win, f"W {win:.0f}%")
            + _seg("dub-draw", draw, f"D {draw:.0f}%")
            + _seg("dub-loss", loss, f"L {loss:.0f}%")
        )
        rows.append(
            f'<div class="dub-row">'
            f'<div class="dub-player-lbl">{escape(str(row["player"]))}</div>'
            f'<div class="dub-stack">{segs}</div>'
            f'<div class="dub-val" style="font-size:0.65rem;color:#1A1A1A">{total}</div>'
            f'</div>'
        )

    head = (
        '<div class="dub">'
        '<div class="dub-head">'
        '<span class="dub-title">Results by Player</span>'
        '<span class="dub-meta">W / D / L</span>'
        '</div>'
    )
    return head + "".join(rows) + "</div>"


_TIMEFRAMES = {
    "Last 30 days": 30,
    "Last 90 days": 90,
    "Last 6 months": 180,
    "Last year": 365,
    "All time": None,
}

# ── Opening lookup ────────────────────────────────────────────────────────────

opening_id_str = st.query_params.get("opening_id", "")

if not opening_id_str:
    st.title("Opening Position")
    st.info("No opening selected. Search for an opening below.")

    query = st.text_input("Search openings", placeholder="e.g. Italian Game, Sicilian…")
    if query:
        results = _svc.search_openings(query, limit=20)
        if results:
            for r in results:
                col_a, col_b = st.columns([5, 1])
                col_a.markdown(f"**{r['eco']}** {r['name']}")
                if col_b.button("View", key=f"view_{r['id']}"):
                    st.query_params["opening_id"] = str(r["id"])
                    st.rerun()
        else:
            st.warning("No openings found.")
    st.stop()

try:
    opening_id = int(opening_id_str)
except ValueError:
    st.error("Invalid opening_id.")
    st.stop()

opening = _svc.get_opening(opening_id)
if opening is None:
    st.error(f"Opening #{opening_id} not found.")
    st.stop()

# ── Page header ───────────────────────────────────────────────────────────────

st.title(opening["name"])
st.caption(f"{opening['eco']}  ·  {opening['ply_depth']} half-moves  ·  {opening['pgn']}")

# ── Filters ───────────────────────────────────────────────────────────────────

all_members = _wsvc.get_club_member_names()
col_tf, col_pl = st.columns([1, 2])
with col_tf:
    selected_label = st.selectbox(
        "Timeframe",
        options=list(_TIMEFRAMES.keys()),
        index=1,
        label_visibility="collapsed",
        key="op_timeframe",
    )
with col_pl:
    selected_players = st.multiselect(
        "Players",
        options=all_members,
        default=all_members,
        label_visibility="collapsed",
        placeholder="All members",
        key="op_players",
    )

lookback = _TIMEFRAMES[selected_label]
active_players = selected_players if selected_players else all_members

# ── Data load ─────────────────────────────────────────────────────────────────

games_df = _svc.get_games(opening, lookback_days=lookback, players=active_players)

# ── Board + opening share (side by side) ──────────────────────────────────────

board_col, pie_col = st.columns([1, 1])

with board_col:
    st.subheader("Opening Position")
    board = chess.Board(opening["final_fen"])
    svg = chess.svg.board(
        board,
        size=340,
        colors=_BOARD_COLORS,
        coordinates=True,
    )
    board_html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<style>
  body {{ margin: 0; background: transparent; display: flex; justify-content: center; }}
  svg {{ display: block; }}
</style></head>
<body>{svg}</body></html>"""
    render_html_iframe(board_html, height=360)

with pie_col:
    st.subheader("Club Share")
    share_df = _svc.opening_share(opening, lookback_days=lookback, players=active_players)
    if share_df.empty or share_df["games"].sum() == 0:
        st.info("No game data available for this period.")
    else:
        fig_pie = opening_share_pie(share_df, opening["name"])
        st.plotly_chart(fig_pie, width='stretch', config={"displaylogo": False})

st.divider()

if games_df.empty:
    st.info(f"No games found with this opening in the selected period.")
    st.stop()

total_games = games_df["game_id"].nunique()
st.caption(
    f"**{total_games}** club games played through this opening "
    f"in the {selected_label.lower()}."
)

# ── Per-player stats ──────────────────────────────────────────────────────────

stats_df = _svc.player_stats(games_df)

wdl_col, acc_col = st.columns(2)

with wdl_col:
    if stats_df.empty:
        st.info("No player stats available.")
    else:
        st.html(_ENGINE_CSS + _wdl_html(stats_df))

with acc_col:
    fig_acc = opening_player_accuracy_bar(stats_df, opening["name"])
    st.plotly_chart(fig_acc, width='stretch', config={"displaylogo": False})

# ── Player stats summary cards ────────────────────────────────────────────────

if not stats_df.empty:
    card_cols = st.columns(len(stats_df))
    for col, (_, row) in zip(card_cols, stats_df.iterrows()):
        with col:
            st.markdown(
                f"<div style='font-family:\"DM Mono\",monospace;font-size:0.7rem;"
                f"letter-spacing:0.08em;text-transform:uppercase;color:#8B3A2A'>"
                f"{escape(row['player'])}</div>"
                f"<div style='font-family:\"EB Garamond\",Georgia,serif;font-size:1.5rem;"
                f"font-weight:600;color:#1A1A1A'>{int(row['games'])} games</div>"
                f"<div style='font-size:0.75rem;color:#4A6554'>W {row['wins']} "
                f"· D {row['draws']} · L {row['losses']}</div>"
                f"<div style='font-size:0.75rem;color:#5A5A5A'>"
                f"{'♙' if row['as_white'] >= row['as_black'] else '♟'} "
                f"White {row['as_white']} · Black {row['as_black']}</div>",
                unsafe_allow_html=True,
            )

st.divider()

# ── Continuation Sankey ───────────────────────────────────────────────────────

st.subheader("Popular Continuations")
st.caption(
    f"Most common lines played 3 moves beyond the {opening['name']} position. "
    "Click a node to see stats."
)

_cont_edges, _cont_nodes = _svc.continuation_flow(games_df, opening, min_games=2)

if _cont_edges.empty:
    st.info("Not enough games to build a continuation chart (need ≥ 2 games per line).")
else:
    _cont_title = f"Continuations from {opening['name']}  ·  {selected_label}"
    _selected_cont = st.session_state.get("_cont_selected_node")

    _cont_labels: list[str] = list(dict.fromkeys(
        _cont_edges["source"].tolist() + _cont_edges["target"].tolist()
    ))
    _cont_fig = welcome_opening_sankey(
        _cont_edges,
        _cont_nodes,
        selected_node=_selected_cont,
        title=_cont_title,
    )
    _cont_event = st.plotly_chart(
        _cont_fig,
        width='stretch',
        on_select="rerun",
        key="cont_sankey",
    )

    _cont_clicked: str | None = None
    if _cont_event and _cont_event.selection:
        pts = _cont_event.selection.get("points", [])
        if pts:
            pt = pts[0]
            _cont_clicked = (
                pt.get("label")
                or (pt.get("customdata")[0] if isinstance(pt.get("customdata"), list) and pt.get("customdata") else None)
                or pt.get("customdata")
            )
            if _cont_clicked is None:
                idx = pt.get("point_number")
                if idx is not None and 0 <= idx < len(_cont_labels):
                    _cont_clicked = _cont_labels[idx]

    if _cont_clicked and _cont_clicked != _selected_cont:
        st.session_state["_cont_selected_node"] = _cont_clicked
        st.rerun()
    elif _cont_clicked and _cont_clicked == _selected_cont:
        st.session_state.pop("_cont_selected_node", None)
        st.rerun()

    if _selected_cont and not _cont_nodes.empty:
        _ns_row = _cont_nodes[_cont_nodes["node"] == _selected_cont]
        if not _ns_row.empty:
            _ns = _ns_row.iloc[0]
            st.markdown(f"**{_selected_cont}** — {int(_ns['games'])} games")
            _c1, _c2, _c3, _c4 = st.columns(4)
            _c1.metric("Wins", f"{int(_ns['wins'])}  ({_ns['win_pct']:.0f}%)")
            _c2.metric("Draws", f"{int(_ns['draws'])}  ({_ns['draw_pct']:.0f}%)")
            _c3.metric("Losses", f"{int(_ns['losses'])}  ({_ns['loss_pct']:.0f}%)")
            _wa = _ns.get("avg_white_accuracy")
            _ba = _ns.get("avg_black_accuracy")
            if _wa is not None and _ba is not None:
                _c4.metric("Avg Accuracy", f"W {_wa:.0f}% / B {_ba:.0f}%")
            if st.button("Clear selection", key="clear_cont"):
                st.session_state.pop("_cont_selected_node", None)
                st.rerun()

st.divider()

# ── Frequency over time ───────────────────────────────────────────────────────

st.subheader("How Often is This Opening Played?")
freq_df = _svc.frequency_over_time(games_df)
if not freq_df.empty:
    fig_freq = opening_frequency_trend(freq_df, opening["name"])
    st.plotly_chart(fig_freq, width='stretch', config={"displaylogo": False})
else:
    st.info("Not enough data for a trend chart.")

st.divider()

# ── Game table ────────────────────────────────────────────────────────────────

st.subheader("Games")

# Filters above the table
tcol1, tcol2, tcol3 = st.columns(3)
with tcol1:
    _tbl_player = st.selectbox(
        "Filter by player",
        options=["All"] + sorted(games_df["club_player"].unique().tolist()),
        index=0,
        key="tbl_player",
    )
with tcol2:
    _tbl_color = st.selectbox(
        "Color",
        options=["All", "White", "Black"],
        index=0,
        key="tbl_color",
    )
with tcol3:
    _tbl_result = st.selectbox(
        "Result",
        options=["All", "Win", "Draw", "Loss"],
        index=0,
        key="tbl_result",
    )

# Apply table filters to a deduplicated game view
_tbl_df = games_df.copy()
if _tbl_player != "All":
    _tbl_df = _tbl_df[_tbl_df["club_player"] == _tbl_player]
if _tbl_color != "All":
    _tbl_df = _tbl_df[_tbl_df["color"] == _tbl_color.lower()]
if _tbl_result != "All":
    _tbl_df = _tbl_df[_tbl_df["result"] == _tbl_result]

_tbl_df = _tbl_df.sort_values("played_at", ascending=False)

if _tbl_df.empty:
    st.info("No games match the selected filters.")
else:
    def _fmt_acc(v: float | None) -> str:
        return f"{v:.1f}%" if v is not None else "—"

    def _result_class(r: str) -> str:
        return {"Win": "op-win", "Loss": "op-loss", "Draw": "op-draw"}.get(r, "")

    _rows_html = []
    for _, row in _tbl_df.iterrows():
        date_str = row["played_at"].strftime("%d %b %Y") if hasattr(row["played_at"], "strftime") else str(row["played_at"])[:10]
        color_sym = "♙" if row["color"] == "white" else "♟"
        opponent = row["black_username"] if row["color"] == "white" else row["white_username"]
        p_acc = _fmt_acc(
            row["white_accuracy"] if row["color"] == "white" else row["black_accuracy"]
        )
        p_acpl = f"{row['white_acpl']:.1f}" if row["color"] == "white" and row["white_acpl"] is not None else (
            f"{row['black_acpl']:.1f}" if row["color"] == "black" and row["black_acpl"] is not None else "—"
        )
        link = escape(f"/game-analysis?game_id={row['game_id']}")
        result_cls = _result_class(row["result"])
        _rows_html.append(
            f"<tr>"
            f'<td class="op-date">{escape(date_str)}</td>'
            f'<td class="op-player">{escape(row["club_player"])}</td>'
            f'<td>{color_sym}</td>'
            f'<td class="op-player">{escape(str(opponent))}</td>'
            f'<td class="{result_cls}">{escape(row["result"])}</td>'
            f'<td class="op-acc">{escape(p_acc)}</td>'
            f'<td class="op-acc">{escape(p_acpl)}</td>'
            f'<td><a class="op-open" href="{link}" target="_blank">Open</a></td>'
            f"</tr>"
        )

    st.html(
        _TABLE_STYLE
        + f"""<table class="op-table">
          <thead><tr>
            <th>Date</th><th>Player</th><th></th><th>Opponent</th>
            <th>Result</th><th>Accuracy</th><th>ACPL</th><th></th>
          </tr></thead>
          <tbody>{"".join(_rows_html)}</tbody>
        </table>"""
    )
    st.caption(f"{len(_tbl_df)} games shown.")
