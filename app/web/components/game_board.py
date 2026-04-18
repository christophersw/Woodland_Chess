from __future__ import annotations

import io
import json
from uuid import uuid4

import chess
import chess.pgn
import chess.svg
import pandas as pd
import streamlit as st

from app.web.components.html_embed import render_html_iframe


def render_svg_game_viewer(
    pgn: str,
    moves_df: pd.DataFrame,
    size: int = 560,
    orientation: str = "white",
    initial_ply: int | str = "last",
    eval_data: list[dict] | None = None,
) -> None:
    """Full-game SVG viewer with play/pause, scrubber, move list, and best-move arrows.

    ``moves_df`` must have columns: ply, san, fen, arrow_uci (UCI of best move).
    ``eval_data`` — optional list of {"ply": int, "cp_eval": float} dicts.
    When provided, an interactive Plotly.js eval chart is embedded below the
    board and kept in sync: navigating the board highlights the current bar,
    and clicking a bar jumps the board to that ply.
    """
    viewer_id = f"svg-{uuid4().hex}"
    game = chess.pgn.read_game(io.StringIO(pgn))
    if game is None:
        st.warning("Could not parse PGN.")
        return

    flipped = orientation == "black"

    # -- Build SVG frames for each position -----------------------------------
    board = game.board()
    moves_played: list[chess.Move] = list(game.mainline_moves())

    # Build a lookup from ply → arrow_uci
    arrow_map: dict[int, str] = {}
    san_list: list[str] = []
    if not moves_df.empty:
        for _, row in moves_df.iterrows():
            p = int(row["ply"])
            arrow_map[p] = str(row.get("arrow_uci", "") or "")
            san_list.append(str(row.get("san", "")))
    else:
        for move in moves_played:
            san_list.append(board.san(move))
        board = game.board()  # reset

    frames: list[str] = []

    # Frame 0: starting position (no arrows, no lastmove)
    frames.append(
        chess.svg.board(board, size=size, flipped=flipped)
    )

    board = game.board()  # reset
    for ply_i, move in enumerate(moves_played, start=1):
        board.push(move)
        # Best-move arrow for this ply
        arrows: list[chess.svg.Arrow] = []
        uci_str = arrow_map.get(ply_i, "")
        if uci_str and len(uci_str) >= 4:
            try:
                from_sq = chess.parse_square(uci_str[:2])
                to_sq = chess.parse_square(uci_str[2:4])
                arrows.append(chess.svg.Arrow(from_sq, to_sq, color="#3b82f680"))
            except ValueError:
                pass

        frames.append(
            chess.svg.board(
                board,
                size=size,
                lastmove=move,
                arrows=arrows,
                flipped=flipped,
            )
        )

    total_frames = len(frames)  # 0..N where 0=start, 1=after move 1, etc.

    if isinstance(initial_ply, int) and 0 <= initial_ply < total_frames:
        start_ply = initial_ply
    else:
        start_ply = total_frames - 1

    # -- Build move list HTML (numbered moves) --------------------------------
    move_spans: list[str] = []
    for i, san in enumerate(san_list):
        ply = i + 1
        if ply % 2 == 1:
            move_no = (ply + 1) // 2
            move_spans.append(
                f'<span class="move-num">{move_no}.</span>'
            )
        move_spans.append(
            f'<span class="move" data-ply="{ply}" onclick="goTo({ply})">{san}</span>'
        )
    moves_html = " ".join(move_spans)

    # -- Serialize SVG frames as JSON -----------------------------------------
    frames_json = json.dumps(frames)

    html = f"""
    <style>
      #{viewer_id} {{
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
        max-width: 1200px;
      }}
      #{viewer_id} .viewer-grid {{
        display: grid;
        grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
        gap: 14px;
        align-items: start;
      }}
      #{viewer_id} .board-pane,
      #{viewer_id} .analysis-pane {{
        min-width: 0;
      }}
      #{viewer_id} .board-pane {{
        display: flex;
        flex-direction: column;
        gap: 8px;
      }}
      #{viewer_id} .board-wrap {{ text-align: center; }}
      #{viewer_id} .board-wrap svg {{ display: block; margin: 0 auto; }}
      #{viewer_id} .controls {{
        display: flex; align-items: center; gap: 6px;
        padding: 8px 0; justify-content: center;
      }}
      #{viewer_id} .controls button {{
        background: #374151; color: #fff; border: none; border-radius: 4px;
        padding: 5px 10px; cursor: pointer; font-size: 14px; min-width: 32px;
      }}
      #{viewer_id} .controls button:hover {{ background: #4b5563; }}
      #{viewer_id} .controls input[type=range] {{ flex: 1; max-width: 280px; }}
      #{viewer_id} .ply-label {{
        font-size: 13px; color: #9ca3af; min-width: 70px; text-align: center;
      }}
      #{viewer_id} .analysis-pane {{
        display: flex;
        flex-direction: column;
        gap: 8px;
      }}
      #{viewer_id} .analysis-pane > div {{
        width: 100%;
      }}
      #{viewer_id} .move-list {{
        max-height: 220px; overflow-y: auto; padding: 6px 4px;
        font-size: 13px; line-height: 1.8; border: 1px solid #374151;
        border-radius: 6px; margin-top: 0; background: #111827;
      }}
      #{viewer_id} .move-list .move-num {{ color: #6b7280; margin-left: 4px; }}
      #{viewer_id} .move-list .move {{
        cursor: pointer; padding: 1px 4px; border-radius: 3px; color: #d1d5db;
      }}
      #{viewer_id} .move-list .move:hover {{ background: #1f2937; }}
      #{viewer_id} .move-list .move.active {{
        background: #2563eb; color: #fff; font-weight: 600;
      }}
      @media (max-width: 900px) {{
        #{viewer_id} .viewer-grid {{
          grid-template-columns: 1fr;
        }}
        #{viewer_id} .move-list {{
          max-height: 180px;
        }}
      }}
    </style>

    <div id="{viewer_id}">
      <div class="viewer-grid">
        <div class="board-pane">
          <div class="board-wrap" id="{viewer_id}-board"></div>
          <div class="controls">
            <button onclick="goTo(0)" title="Start">&#x23EE;</button>
            <button onclick="goTo(Math.max(0, currentPly-1))" title="Back">&#x25C0;</button>
            <button id="{viewer_id}-playbtn" onclick="togglePlay()" title="Play/Pause">&#x25B6;</button>
            <button onclick="goTo(Math.min({total_frames - 1}, currentPly+1))" title="Forward">&#x25B6;&#xFE0E;</button>
            <button onclick="goTo({total_frames - 1})" title="End">&#x23ED;</button>
            <input type="range" id="{viewer_id}-slider" min="0" max="{total_frames - 1}"
                   value="{start_ply}" oninput="goTo(parseInt(this.value))">
            <span class="ply-label" id="{viewer_id}-label"></span>
          </div>
          <div class="move-list" id="{viewer_id}-moves">{moves_html}</div>
        </div>
        <div class="analysis-pane">
          <div id="{viewer_id}-eval"></div>
        </div>
      </div>
    </div>

    <script>
    (function() {{
      const frames = {frames_json};
      const totalFrames = frames.length;
      let currentPly = {start_ply};
      let playing = false;
      let timer = null;

      const boardEl = document.getElementById('{viewer_id}-board');
      const slider = document.getElementById('{viewer_id}-slider');
      const label = document.getElementById('{viewer_id}-label');
      const playBtn = document.getElementById('{viewer_id}-playbtn');
      const movesEl = document.getElementById('{viewer_id}-moves');
      const allMoveSpans = movesEl.querySelectorAll('.move');

      window.currentPly = currentPly;

      function render() {{
        boardEl.innerHTML = frames[currentPly];
        slider.value = currentPly;
        if (currentPly === 0) {{
          label.textContent = 'Start';
        }} else {{
          const moveNum = Math.ceil(currentPly / 2);
          const side = currentPly % 2 === 1 ? '' : '...';
          label.textContent = moveNum + '.' + side + ' (ply ' + currentPly + ')';
        }}
        // highlight active move in list
        allMoveSpans.forEach(s => s.classList.remove('active'));
        if (currentPly > 0) {{
          const active = movesEl.querySelector('.move[data-ply="' + currentPly + '"]');
          if (active) {{
            active.classList.add('active');
            active.scrollIntoView({{ block: 'nearest' }});
          }}
        }}
        // highlight current ply on eval chart
        if (window._evalChart && typeof window.updateEvalHighlight === 'function') {{
          window.updateEvalHighlight(currentPly);
        }}
      }}

      window.goTo = function(ply) {{
        currentPly = Math.max(0, Math.min(totalFrames - 1, ply));
        window.currentPly = currentPly;
        render();
      }};

      window.togglePlay = function() {{
        if (playing) {{
          clearInterval(timer);
          playing = false;
          playBtn.innerHTML = '\\u25B6';
        }} else {{
          if (currentPly >= totalFrames - 1) currentPly = 0;
          playing = true;
          playBtn.innerHTML = '\\u23F8';
          timer = setInterval(() => {{
            if (currentPly >= totalFrames - 1) {{
              clearInterval(timer);
              playing = false;
              playBtn.innerHTML = '\\u25B6';
              return;
            }}
            currentPly++;
            window.currentPly = currentPly;
            render();
          }}, 800);
        }}
      }};

      render();
    }})();
    </script>
    """

    # -- Optionally embed a linked Plotly.js eval chart -----------------------
    eval_chart_html = ""
    eval_extra_height = 0
    if eval_data:
        eval_json = json.dumps(eval_data)
        eval_count = len(eval_data)
        eval_extra_height = max(340, min(1100, 150 + eval_count * 14))
        eval_chart_html = f"""
    <script src="https://cdn.plot.ly/plotly-2.35.0.min.js"></script>
    <script>
    (function() {{
      const evalData = {eval_json};
      const MATE_CP_BASE = 10000;
      const MATE_THRESHOLD = 9000;
      const DISPLAY_CP_CAP = 1200;

      const points = evalData.map(d => {{
        const ply = Number(d.ply);
        const rawCp = Number(d.cp_eval ?? 0);
        const isMate = Math.abs(rawCp) >= MATE_THRESHOLD;
        const side = rawCp >= 0 ? 'White' : 'Black';

        let mateMoves = null;
        if (isMate) {{
          // If cp is encoded from mate_score (e.g. 9995 => M5), recover distance.
          const recovered = Math.round(MATE_CP_BASE - Math.abs(rawCp));
          if (recovered > 0) {{
            mateMoves = recovered;
          }}
        }}

        const displayCp = isMate
          ? (rawCp >= 0 ? DISPLAY_CP_CAP : -DISPLAY_CP_CAP)
          : Math.max(-DISPLAY_CP_CAP, Math.min(DISPLAY_CP_CAP, rawCp));

        const hoverText = isMate
          ? (mateMoves
              ? `${{side}} mate in ${{mateMoves}}`
              : `${{side}} forced mate`)
          : `${{rawCp >= 0 ? '+' : ''}}${{Math.round(rawCp)}} cp`;

        const textLabel = isMate
          ? (mateMoves
              ? `M${{rawCp >= 0 ? '+' : '-'}}${{mateMoves}}`
              : `M${{rawCp >= 0 ? '+' : '-'}}`)
          : '';

        return {{
          ply,
          rawCp,
          displayCp,
          isMate,
          hoverText,
          textLabel,
        }};
      }});

      const plies = points.map(p => p.ply);
      const evals = points.map(p => p.displayCp);
      const whiteColor = '#f9fafb';
      const blackColor = '#111111';
      const colors = points.map(p => p.rawCp >= 0 ? whiteColor : blackColor);
      const lineColors = points.map(() => '#9ca3af');
      const baseOpacity = evals.map(() => 0.82);

      const trace = {{
        x: evals,
        y: plies,
        type: 'bar',
        orientation: 'h',
        marker: {{
          color: colors.slice(),
          opacity: baseOpacity.slice(),
          line: {{ color: lineColors.slice(), width: 1 }}
        }},
        text: points.map(p => p.textLabel),
        textposition: 'outside',
        customdata: points.map(p => [p.rawCp, p.isMate, p.hoverText]),
        hovertemplate: 'Ply %{{y}}<br>%{{customdata[2]}}<extra></extra>',
      }};
      const layout = {{
        title: 'Engine Evaluation by Ply (White + / Black -)',
        xaxis: {{
          title: 'Centipawns (mate scores capped for display)',
          zeroline: true,
          zerolinecolor: '#9ca3af',
          zerolinewidth: 2,
          range: [-DISPLAY_CP_CAP * 1.1, DISPLAY_CP_CAP * 1.1]
        }},
        yaxis: {{ title: 'Ply', autorange: 'reversed' }},
        margin: {{ l: 50, r: 20, t: 36, b: 40 }},
        bargap: 0.12,
        height: {eval_extra_height - 20},
        paper_bgcolor: 'rgba(0,0,0,0)',
        plot_bgcolor: 'rgba(0,0,0,0)',
        font: {{ color: '#d1d5db' }},
      }};
      const evalDiv = document.getElementById('{viewer_id}-eval');
      Plotly.newPlot(evalDiv, [trace], layout, {{ displaylogo: false, responsive: true }}).then(() => {{
        window._evalChart = evalDiv;
        // click bar → jump board
        evalDiv.on('plotly_click', function(data) {{
          if (data.points && data.points.length > 0) {{
            const ply = data.points[0].y;
            window.goTo(ply);
          }}
        }});
        // initial highlight
        if (typeof window.updateEvalHighlight === 'function') {{
          window.updateEvalHighlight(window.currentPly);
        }}
        // ensure board render and chart highlight are synchronized once chart is ready
        if (typeof window.goTo === 'function') {{
          window.goTo(window.currentPly);
        }}
      }});

      window.updateEvalHighlight = function(ply) {{
        const highlightColor = '#f59e0b';
        const lineColor = plies.map(p => p === ply ? highlightColor : '#9ca3af');
        const opacity = plies.map(p => p === ply ? 1.0 : 0.82);
        const lineWidth = plies.map(p => p === ply ? 3 : 1);
        Plotly.restyle(evalDiv, {{
          'marker.opacity': [opacity],
          'marker.line.width': [lineWidth],
          'marker.line.color': [lineColor]
        }});
      }};
    }})();
    </script>
    """

    html = html + eval_chart_html

    # Height: board + controls + move list + optional eval chart
    render_html_iframe(html, height=size + 280 + eval_extra_height)


def render_pgn_viewer(
    pgn: str,
    size: int = 560,
    orientation: str = "white",
    board_theme: str = "blue",
    initial_ply: int | str = "last",
) -> None:
    viewer_id = f"lpv-{uuid4().hex}"
    safe_pgn = json.dumps(pgn)
    safe_orientation = "black" if orientation == "black" else "white"
    safe_theme = board_theme if board_theme in {"blue", "green", "brown"} else "blue"
    safe_initial_ply: int | str
    if isinstance(initial_ply, int) and initial_ply >= 0:
        safe_initial_ply = initial_ply
    else:
        safe_initial_ply = "last"

    initial_ply_js = json.dumps(safe_initial_ply)

    # Uses the official lichess-org/pgn-viewer package for move tree, controls,
    # and board playback UI.
    html_payload = f"""
        <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@lichess-org/pgn-viewer@2.6.0/dist/lichess-pgn-viewer.css" />

        <style>
            #{viewer_id} {{ width: min({size + 180}px, 100%); }}
            #{viewer_id} .lpv__board {{ width: {size}px; max-width: 100%; }}

            #{viewer_id}.theme-blue cg-board square.light {{ background: #d8e3ef; }}
            #{viewer_id}.theme-blue cg-board square.dark {{ background: #7b96b2; }}

            #{viewer_id}.theme-green cg-board square.light {{ background: #e2eadf; }}
            #{viewer_id}.theme-green cg-board square.dark {{ background: #6f8f5f; }}

            #{viewer_id}.theme-brown cg-board square.light {{ background: #f0d9b5; }}
            #{viewer_id}.theme-brown cg-board square.dark {{ background: #b58863; }}
        </style>

        <div id="{viewer_id}" class="theme-{safe_theme}"></div>

        <script nomodule>
            document.getElementById('{viewer_id}').innerHTML = '<p>Modern chess viewer requires module-enabled browser support.</p>';
        </script>

        <script type="module">
            import LichessPgnViewer from 'https://cdn.jsdelivr.net/npm/@lichess-org/pgn-viewer@2.6.0/+esm';

            const target = document.getElementById('{viewer_id}');
            const pgn = {safe_pgn};

            LichessPgnViewer(target, {{
                pgn,
                orientation: '{safe_orientation}',
                showClocks: false,
                showMoves: 'auto',
                scrollToMove: true,
                initialPly: {initial_ply_js},
            }});
        </script>
        """

    render_html_iframe(html_payload, height=size + 220)
