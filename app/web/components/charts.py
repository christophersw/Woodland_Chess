import io

import chess.pgn
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go


def elo_trend_chart(df: pd.DataFrame, selected_player: str):
    fig = px.line(
        df,
        x="date",
        y="rating",
        color="player",
        title="ELO Trend (Daily Games)",
        markers=False,
    )
    fig.update_traces(opacity=0.35)
    fig.for_each_trace(
        lambda trace: trace.update(opacity=1.0, line=dict(width=3))
        if trace.name == selected_player
        else None
    )
    fig.update_layout(legend_title="Player", margin=dict(l=20, r=20, t=56, b=20))
    return fig


def opening_pie_chart(df: pd.DataFrame):
    fig = px.pie(
        df,
        names="opening",
        values="games",
        title="Recent Openings Distribution (Depth = 5 Ply)",
    )
    fig.update_traces(textposition="inside", textinfo="percent+label")
    return fig


def eval_timeline_chart(df: pd.DataFrame, selected_ply: int | None = None):
    fig = px.bar(df, x="ply", y="cp_eval", title="Engine Evaluation by Ply")

    if selected_ply is not None:
        colors = ["#4c78a8" if int(p) != selected_ply else "#e45756" for p in df["ply"].tolist()]
        fig.update_traces(marker_color=colors)

    fig.add_hline(y=0, line_dash="dot")
    fig.update_layout(yaxis_title="Centipawns", xaxis_title="Ply", clickmode="event+select")
    return fig


def opening_starburst_chart(df: pd.DataFrame, depth: int = 5):
    """Build a sunburst from opening ply data, with lichess opening labels on large segments."""
    if df.empty:
        return None

    depth = max(1, min(depth, 20))
    denorm_cols = [f"opening_ply_{i}" for i in range(1, depth + 1)]
    has_denorm = all(col in df.columns for col in denorm_cols)
    has_lichess = "lichess_opening" in df.columns

    # Collect per-game move sequences and lichess opening names.
    game_data: list[tuple[list[str], str]] = []
    for _, row in df.iterrows():
        plies: list[str] = []
        if has_denorm:
            for col in denorm_cols:
                val = row.get(col)
                if val is None:
                    break
                t = str(val).strip()
                if not t:
                    break
                plies.append(t)

        if not plies and "pgn" in df.columns:
            pgn = str(row.get("pgn") or "").strip()
            if pgn:
                game = chess.pgn.read_game(io.StringIO(pgn))
                if game is not None:
                    board = game.board()
                    for i, move in enumerate(game.mainline_moves(), 1):
                        plies.append(board.san(move))
                        board.push(move)
                        if i >= depth:
                            break

        if not plies:
            continue

        lichess = str(row.get("lichess_opening") or "").strip() if has_lichess else ""
        game_data.append((plies, lichess))

    if not game_data:
        return None

    # Build hierarchy nodes.
    nodes: dict[str, dict] = {}
    for plies, lichess in game_data:
        for d in range(1, min(len(plies), depth) + 1):
            nid = "/".join(plies[:d])
            pid = "/".join(plies[:d - 1]) if d > 1 else ""
            if nid not in nodes:
                nodes[nid] = {
                    "label": plies[d - 1],
                    "parent": pid,
                    "value": 0,
                    "lichess_names": [],
                }
            nodes[nid]["value"] += 1
            if lichess:
                nodes[nid]["lichess_names"].append(lichess)

    total = sum(n["value"] for n in nodes.values() if n["parent"] == "")

    ids, labels_arr, parents_arr, values_arr = [], [], [], []
    texts, hovertexts, customdata_arr = [], [], []

    for nid in sorted(nodes):
        n = nodes[nid]
        ids.append(nid)
        labels_arr.append(n["label"])
        parents_arr.append(n["parent"])
        values_arr.append(n["value"])

        # Dominant lichess opening name for this node.
        lnames = n["lichess_names"]
        if lnames:
            mode = pd.Series(lnames).mode()
            name = str(mode.iloc[0]) if not mode.empty else ""
        else:
            name = ""

        pct = n["value"] / total * 100 if total else 0
        # Show lichess name on segments >= 3% of total.
        if name and pct >= 3:
            short = name.split(" ", 1)[1] if " " in name else name
            texts.append(short)
        else:
            texts.append("")
        hovertexts.append(name or "")
        customdata_arr.append(name or "")

    fig = go.Figure(go.Sunburst(
        ids=ids,
        labels=labels_arr,
        parents=parents_arr,
        values=values_arr,
        text=texts,
        hovertext=hovertexts,
        customdata=customdata_arr,
        branchvalues="total",
        textinfo="label+text+percent parent",
        hovertemplate="<b>%{label}</b><br>Games: %{value}<br>%{hovertext}<extra></extra>",
        insidetextorientation="auto",
    ))
    fig.update_layout(
        title=f"Opening Star-burst (First {depth} Plies)",
        margin=dict(l=10, r=10, t=56, b=10),
    )
    return fig


def opening_frequency_bar(df: pd.DataFrame):
    if df.empty:
        return go.Figure()

    top = df.sort_values("games", ascending=False).head(15)
    fig = px.bar(
        top,
        x="games",
        y="opening_label",
        orientation="h",
        title="Opening Frequency",
        labels={"opening_label": "Opening", "games": "Games"},
    )
    fig.update_layout(yaxis=dict(categoryorder="total ascending"), margin=dict(l=10, r=10, t=56, b=10))
    return fig


def opening_wdl_stacked(metrics_df: pd.DataFrame):
    if metrics_df.empty:
        return go.Figure()

    top = metrics_df.sort_values("games", ascending=False).head(12).copy()
    melted = top.melt(
        id_vars=["opening_label", "games"],
        value_vars=["wins", "draws", "losses"],
        var_name="outcome",
        value_name="count",
    )
    fig = px.bar(
        melted,
        x="opening_label",
        y="count",
        color="outcome",
        title="Win / Draw / Loss by Opening",
        labels={"opening_label": "Opening", "count": "Games", "outcome": "Outcome"},
        color_discrete_map={"wins": "#1f77b4", "draws": "#9e9e9e", "losses": "#d62728"},
    )
    fig.update_layout(barmode="stack", xaxis_tickangle=-35, margin=dict(l=10, r=10, t=56, b=10))
    return fig


def opening_bubble(metrics_df: pd.DataFrame):
    if metrics_df.empty:
        return go.Figure()

    fig = px.scatter(
        metrics_df,
        x="games",
        y="win_pct",
        size="games",
        color="wins",
        hover_name="opening_label",
        custom_data=["opening_label"],
        hover_data={"wins": True, "draw_pct": True, "loss_pct": True, "avg_game_length": True, "avg_move10_cp": True},
        title="Opening Bubble Map (Frequency vs Win Rate)",
        labels={"games": "Frequency", "win_pct": "Win %", "wins": "Total Wins", "opening_label": "Opening"},
        size_max=45,
        color_continuous_scale="Viridis",
    )
    fig.update_layout(showlegend=False, margin=dict(l=10, r=10, t=56, b=10))
    return fig


def opening_timeline_heatmap(timeline_df: pd.DataFrame, title: str):
    if timeline_df.empty:
        return go.Figure()

    time_col = "time_bucket" if "time_bucket" in timeline_df.columns else "week_start"
    bucket_label = "Week"
    if "bucket_label" in timeline_df.columns and not timeline_df["bucket_label"].empty:
        bucket_label = str(timeline_df["bucket_label"].iloc[0])

    pivot = timeline_df.pivot_table(
        index="opening_label",
        columns=time_col,
        values="games",
        aggfunc="sum",
        fill_value=0,
    )

    xvals = [d.strftime("%Y-%m-%d") for d in pivot.columns]
    yvals = pivot.index.tolist()
    fig = go.Figure(
        data=go.Heatmap(
            z=pivot.values,
            x=xvals,
            y=yvals,
            colorscale="Blues",
            colorbar_title="Games",
            hovertemplate=f"Opening: %{{y}}<br>{bucket_label}: %{{x}}<br>Games: %{{z}}<extra></extra>",
        )
    )
    fig.update_layout(
        title=title,
        xaxis_title=bucket_label,
        yaxis_title="Opening",
        margin=dict(l=10, r=10, t=56, b=10),
    )
    return fig


def player_fingerprint_radar(df: pd.DataFrame):
    if df.empty:
        return go.Figure()

    theta = df["family"].tolist()
    r = df["share_pct"].tolist()
    fig = go.Figure(
        data=go.Scatterpolar(
            r=r,
            theta=theta,
            fill="toself",
            name="Opening Fingerprint",
            line=dict(color="#2a6f97", width=3),
            marker=dict(size=8),
        )
    )
    fig.update_layout(
        title="Player Opening Fingerprint",
        polar=dict(radialaxis=dict(visible=True, range=[0, 100])),
        showlegend=False,
        margin=dict(l=10, r=10, t=56, b=10),
    )
    return fig


def opening_flow_sankey(flow_df: pd.DataFrame):
    if flow_df.empty:
        return go.Figure()

    labels = list(dict.fromkeys(flow_df["source"].tolist() + flow_df["target"].tolist()))
    idx_map = {label: i for i, label in enumerate(labels)}

    fig = go.Figure(
        data=[
            go.Sankey(
                node=dict(label=labels, pad=18, thickness=16),
                link=dict(
                    source=[idx_map[s] for s in flow_df["source"]],
                    target=[idx_map[t] for t in flow_df["target"]],
                    value=flow_df["games"].tolist(),
                ),
            )
        ]
    )
    fig.update_layout(title="Opening-to-Opening Flow", margin=dict(l=10, r=10, t=56, b=10))
    return fig


def opening_wins_losses_bar(metrics_df: pd.DataFrame, top_n: int = 15) -> go.Figure:
    if metrics_df.empty:
        return go.Figure()

    top = metrics_df.sort_values("games", ascending=False).head(top_n).copy()

    def _truncate(label: str, max_len: int = 30) -> str:
        return label if len(label) <= max_len else label[:max_len - 1] + "…"

    x_labels = [_truncate(str(lbl)) for lbl in top["opening_label"]]

    fig = go.Figure()

    fig.add_trace(go.Bar(
        name="Wins",
        x=x_labels,
        y=top["wins"],
        marker_color="#2ca02c",
        text=top["wins"],
        textposition="outside",
        textfont=dict(size=11),
        hovertemplate="<b>%{x}</b><br>Wins: %{y}<extra></extra>",
    ))

    fig.add_trace(go.Bar(
        name="Losses",
        x=x_labels,
        y=-top["losses"],
        marker_color="#d62728",
        text=top["losses"],
        textposition="outside",
        textfont=dict(size=11),
        hovertemplate="<b>%{x}</b><br>Losses: %{text}<extra></extra>",
    ))

    fig.update_layout(
        title="Most Common Openings — Wins vs Losses",
        barmode="relative",
        xaxis=dict(
            title="Opening",
            tickangle=-50,
            tickfont=dict(size=11),
        ),
        yaxis=dict(
            title="Games",
            zeroline=True,
            zerolinewidth=2,
            zerolinecolor="#333",
        ),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(l=10, r=10, t=70, b=180),
    )

    return fig
