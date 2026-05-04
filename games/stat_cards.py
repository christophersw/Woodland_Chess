"""
Title: stat_cards.py — Du Bois-style engine analysis stat card generators
Description:
    Generates HTML stat card fragments for the game analysis page, covering
    Stockfish accuracy/ACPL/move-quality and Lc0 WDL probability cards.
    Includes rerun-analysis buttons with queue-state awareness.

Changelog:
    2026-05-04 (#16): Added queued param to build_sf_card/build_lc0_card;
                      embedded count labels in quality segments; added _rerun_button;
                      separated build_sf_card/build_lc0_card from build_stat_cards_html
"""

from __future__ import annotations

from html import escape
from typing import Optional

from games.services import GameAnalysisData

_DUB_CSS = """<style>
.dub{font-family:'DM Mono','Courier New',monospace;color:#1A1A1A;margin-bottom:1.6rem;}
.dub-head{border-top:3px solid #1A1A1A;border-bottom:1.5px solid #1A1A1A;display:flex;justify-content:space-between;align-items:baseline;padding:5px 0 4px;margin-bottom:16px;}
.dub-title{font-family:'Playfair Display SC','Cormorant Garamond',Georgia,serif;font-size:.92rem;letter-spacing:.07em;color:#1A3A2A;}
.dub-meta{font-size:.60rem;letter-spacing:.06em;color:#8B3A2A;text-transform:uppercase;}
.dub-row{display:grid;grid-template-columns:140px 1fr 52px;align-items:center;gap:0 8px;margin-bottom:5px;}
.dub-player-lbl{font-size:.70rem;letter-spacing:.03em;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;color:#1A1A1A;}
.dub-chess{color:#8B3A2A;margin-right:3px;}
.dub-val{font-size:.78rem;font-weight:700;text-align:right;white-space:nowrap;color:#1A1A1A;}
.dub-bar{height:28px;background:#F2E6D0;border:1.5px solid #1A1A1A;position:relative;overflow:hidden;}
.dub-bar-fill{position:absolute;left:0;top:0;bottom:0;display:flex;align-items:center;padding-left:6px;}
.dub-bar-lbl{font-size:.65rem;font-weight:700;color:#F2E6D0;white-space:nowrap;overflow:hidden;}
.dub-stack{height:28px;display:flex;border:1.5px solid #1A1A1A;overflow:hidden;}
.dub-seg{display:flex;align-items:center;justify-content:center;font-size:.60rem;font-weight:700;overflow:hidden;white-space:nowrap;color:#F2E6D0;}
.dub-win{background:#1A3A2A;}.dub-draw{background:#8B3A2A;}.dub-loss{background:#B53541;}
.dub-bril{background:#2C6B4A;}.dub-best{background:#4A6E8A;}.dub-great{background:#4A6554;}
.dub-neut{background:#EFE4CC;color:#5A5A5A;}.dub-inac{background:#E07B7B;color:#1A1A1A;}
.dub-mist{background:#CE3A4A;}.dub-blun{background:#B53541;}
.dub-lbl{font-size:.54rem;letter-spacing:.12em;text-transform:uppercase;color:#5A5A5A;margin:10px 0 4px;}
.dub-rule{border:none;border-top:1px solid #D4C4A0;margin:12px 0 10px;}
.dub-legend{display:flex;gap:8px;flex-wrap:wrap;font-size:.57rem;color:#5A5A5A;letter-spacing:.04em;margin-top:5px;}
.dub-swatch{display:inline-block;width:9px;height:9px;border:1px solid #1A1A1A;vertical-align:middle;margin-right:2px;}
.wc-btn{display:inline-block;font-family:'DM Mono',monospace;font-size:.72rem;letter-spacing:.06em;border:1.5px solid #1A1A1A;padding:.3rem .7rem;cursor:pointer;background:transparent;color:#1A1A1A;text-decoration:none;transition:background .15s,color .15s;}
.wc-btn:hover{background:#1A1A1A;color:#F2E6D0;}
.wc-btn:disabled{opacity:.45;cursor:not-allowed;}
.wc-btn-sm{font-size:.65rem;padding:.2rem .5rem;}
.wc-btn-ghost{border-color:#5A5A5A;color:#5A5A5A;}
.wc-btn-ghost:hover{background:#5A5A5A;color:#F2E6D0;}
</style>"""

_QUALITY_INLINE_LEGEND = (
    '<div class="dub-legend">'
    '<span><span class="dub-swatch" style="background:#2C6B4A"></span>!! Brilliant</span>'
    '<span><span class="dub-swatch" style="background:#4A6E8A"></span>B Best</span>'
    '<span><span class="dub-swatch" style="background:#4A6554"></span>Gr Great</span>'
    '<span><span class="dub-swatch" style="background:#EFE4CC"></span>Good</span>'
    '<span><span class="dub-swatch" style="background:#E07B7B"></span>?! Inaccuracy</span>'
    '<span><span class="dub-swatch" style="background:#CE3A4A"></span>? Mistake</span>'
    '<span><span class="dub-swatch" style="background:#B53541"></span>?? Blunder</span>'
    "</div>"
)


def _acc_color(pct: float) -> str:
    """
    Return a hex color code appropriate for an accuracy percentage.

    Params:
        pct (float): Accuracy percentage 0–100.

    Returns:
        Hex color string.
    """
    if pct >= 90:
        return "#1A3A2A"
    if pct >= 80:
        return "#4A6554"
    if pct >= 70:
        return "#D4A843"
    return "#B53541"


def _bar_row(sym: str, name: str, pct: float, val_str: str, fill: str | None = None) -> str:
    """
    Generate HTML for a single stat bar row with player label, filled bar, and value.

    Params:
        sym (str): Chess piece symbol (♙ or ♟).
        name (str): Player name.
        pct (float): Bar fill percentage 0–100.
        val_str (str): Display value string shown in the right column.
        fill (str | None): Custom hex color for the bar fill; defaults to accuracy color.

    Returns:
        HTML string for the row.
    """
    color = fill or _acc_color(pct)
    w = min(max(pct, 0), 100)
    inner_lbl = f'<span class="dub-bar-lbl">{escape(val_str)}</span>' if w > 15 else ""
    return (
        f'<div class="dub-row">'
        f'<div class="dub-player-lbl"><span class="dub-chess">{sym}</span>{escape(name)}</div>'
        f'<div class="dub-bar"><div class="dub-bar-fill" style="width:{w:.1f}%;background:{color}">{inner_lbl}</div></div>'
        f'<div class="dub-val">{escape(val_str)}</div>'
        f"</div>"
    )


def _wdl_row(sym: str, name: str, win: float, draw: float, loss: float) -> str:
    """
    Generate HTML for a Win/Draw/Loss probability stacked bar row.

    Params:
        sym (str): Chess piece symbol.
        name (str): Player name.
        win (float): Win probability 0–100.
        draw (float): Draw probability 0–100.
        loss (float): Loss probability 0–100.

    Returns:
        HTML string for the row.
    """
    def _seg(cls: str, pct: float, lbl: str) -> str:
        """Build a single WDL segment."""
        txt = lbl if pct >= 9 else ""
        return f'<div class="dub-seg {cls}" style="flex:{pct:.1f}">{escape(txt)}</div>'

    segs = (
        _seg("dub-win", win, f"W {win:.0f}%")
        + _seg("dub-draw", draw, f"D {draw:.0f}%")
        + _seg("dub-loss", loss, f"L {loss:.0f}%")
    )
    return (
        f'<div class="dub-row">'
        f'<div class="dub-player-lbl"><span class="dub-chess">{sym}</span>{escape(name)}</div>'
        f'<div class="dub-stack">{segs}</div>'
        f'<div class="dub-val" style="font-size:.58rem;color:#5A5A5A">WDL</div>'
        f"</div>"
    )


def _quality_row(
    sym: str, name: str,
    brilliant: int, best: int, great: int,
    inaccuracy: int, mistake: int, blunder: int,
    total: int,
) -> str:
    """
    Generate HTML for a move quality classification stacked bar row.

    Each segment shows a short label (e.g., "!! 2") when wide enough.

    Params:
        sym (str): Chess piece symbol.
        name (str): Player name.
        brilliant (int): Count of brilliant moves.
        best (int): Count of best moves.
        great (int): Count of great moves.
        inaccuracy (int): Count of inaccuracies.
        mistake (int): Count of mistakes.
        blunder (int): Count of blunders.
        total (int): Total moves for this side.

    Returns:
        HTML string for the row.
    """
    classified = brilliant + best + great + inaccuracy + mistake + blunder
    neutral = max(0, total - classified)

    def _seg(cls: str, n: int, short_lbl: str) -> str:
        """Build a single quality classification segment."""
        if n == 0 or total == 0:
            return ""
        pct = n / total * 100
        txt = f"{short_lbl} {n}" if pct >= 6 else ""
        return f'<div class="dub-seg {cls}" style="flex:{pct:.2f}">{escape(txt)}</div>'

    neu_seg = ""
    if neutral > 0 and total > 0:
        pct = neutral / total * 100
        neu_seg = f'<div class="dub-seg dub-neut" style="flex:{pct:.2f}"></div>'

    segs = (
        _seg("dub-bril", brilliant, "!!")
        + _seg("dub-best", best, "B")
        + _seg("dub-great", great, "Gr")
        + neu_seg
        + _seg("dub-inac", inaccuracy, "?!")
        + _seg("dub-mist", mistake, "?")
        + _seg("dub-blun", blunder, "??")
    )
    return (
        f'<div class="dub-row">'
        f'<div class="dub-player-lbl"><span class="dub-chess">{sym}</span>{escape(name)}</div>'
        f'<div class="dub-stack">{segs}</div>'
        f'<div class="dub-val" style="font-size:.60rem;color:#5A5A5A">{total}</div>'
        f"</div>"
    )


def _rerun_button(engine: str, queued: bool) -> str:
    """
    Generate an HTML rerun-analysis button for an engine card.

    When queued=True the button is disabled. Otherwise it opens the confirmation
    modal via window.openQueueModal().

    Params:
        engine (str): Engine identifier — "stockfish" or "lc0".
        queued (bool): Whether this engine already has an active job.

    Returns:
        HTML button string.
    """
    label = "Stockfish" if engine == "stockfish" else "Lc0"
    btn_id = f"queue-btn-{engine}"
    if queued:
        return (
            f'<button id="{btn_id}" class="wc-btn wc-btn-sm" disabled '
            f'style="margin-top:10px">Already Queued</button>'
        )
    return (
        f'<button id="{btn_id}" class="wc-btn wc-btn-sm" '
        f'onclick="window.openQueueModal(\'{engine}\')" '
        f'style="margin-top:10px">Re-run {label}</button>'
    )


def build_sf_card(data: GameAnalysisData, queued: bool = False) -> str:
    """
    Generate Stockfish analysis stat card HTML.

    Params:
        data (GameAnalysisData): Assembled game analysis data.
        queued (bool): Whether a Stockfish job is currently active in the queue.

    Returns:
        HTML string for the card, or empty string if no SF data.
    """
    if not data.has_sf:
        return ""

    meta_parts = []
    if data.engine_depth:
        meta_parts.append(f"depth {data.engine_depth}")
    meta = " · ".join(meta_parts)

    acc_section = ""
    if data.white_accuracy is not None or data.black_accuracy is not None:
        acc_section = '<div class="dub-lbl">Accuracy</div>'
        if data.white_accuracy is not None:
            acc_section += _bar_row("♙", data.white, data.white_accuracy, f"{data.white_accuracy:.1f}%")
        if data.black_accuracy is not None:
            acc_section += _bar_row("♟", data.black, data.black_accuracy, f"{data.black_accuracy:.1f}%")

    acpl_section = ""
    if data.white_acpl is not None or data.black_acpl is not None:
        acpl_section = '<hr class="dub-rule"><div class="dub-lbl">Avg Centipawn Loss</div>'
        max_acpl = max(v for v in [data.white_acpl, data.black_acpl] if v is not None)
        if data.white_acpl is not None:
            pct = max(0.0, min(100.0, 100 - data.white_acpl / max(max_acpl, 1) * 100)) if max_acpl else 50.0
            acpl_section += _bar_row("♙", data.white, pct, f"{data.white_acpl:.1f}", fill="#D4A843")
        if data.black_acpl is not None:
            pct = max(0.0, min(100.0, 100 - data.black_acpl / max(max_acpl, 1) * 100)) if max_acpl else 50.0
            acpl_section += _bar_row("♟", data.black, pct, f"{data.black_acpl:.1f}", fill="#D4A843")

    quality_section = ""
    if data.moves:
        w_moves = [m for m in data.moves if m.ply % 2 == 1]
        b_moves = [m for m in data.moves if m.ply % 2 == 0]
        if any(m.classification for m in data.moves):
            def _cnt(moves_list, cls):
                return sum(1 for m in moves_list if m.classification == cls)

            quality_section = '<hr class="dub-rule"><div class="dub-lbl">Move Quality</div>'
            for sym, name, side_moves, blun, mist, inac in [
                ("♙", data.white, w_moves, data.white_blunders, data.white_mistakes, data.white_inaccuracies),
                ("♟", data.black, b_moves, data.black_blunders, data.black_mistakes, data.black_inaccuracies),
            ]:
                bril = _cnt(side_moves, "brilliant")
                best = _cnt(side_moves, "best")
                great = _cnt(side_moves, "great")
                inaccuracy = inac if inac is not None else _cnt(side_moves, "inaccuracy")
                mistake = mist if mist is not None else _cnt(side_moves, "mistake")
                blunder = blun if blun is not None else _cnt(side_moves, "blunder")
                total = len(side_moves)
                if total:
                    quality_section += _quality_row(sym, name, bril, best, great, inaccuracy, mistake, blunder, total)
            quality_section += _QUALITY_INLINE_LEGEND

    return (
        f'<div class="dub">'
        f'<div class="dub-head">'
        f'<span class="dub-title">Stockfish Analysis</span>'
        f'<span class="dub-meta">{escape(meta)}</span>'
        f"</div>"
        + acc_section + acpl_section + quality_section
        + _rerun_button("stockfish", queued)
        + "</div>"
    )


def build_lc0_card(data: GameAnalysisData, queued: bool = False) -> str:
    """
    Generate Lc0 neural network analysis stat card HTML.

    Params:
        data (GameAnalysisData): Assembled game analysis data.
        queued (bool): Whether an Lc0 job is currently active in the queue.

    Returns:
        HTML string for the card, or empty string if no Lc0 data.
    """
    if not data.has_lc0:
        return ""
    if data.lc0_white_win_prob is None and data.lc0_black_win_prob is None:
        return ""

    meta_parts = []
    if data.lc0_network_name:
        meta_parts.append(data.lc0_network_name)
    if data.lc0_engine_nodes:
        meta_parts.append(f"{data.lc0_engine_nodes:,} nodes/move")
    meta = " · ".join(meta_parts)

    wdl_section = '<div class="dub-lbl">Win / Draw / Loss — average over game</div>'
    if data.lc0_white_win_prob is not None:
        wdl_section += _wdl_row(
            "♙", data.white,
            data.lc0_white_win_prob,
            data.lc0_white_draw_prob or 0.0,
            data.lc0_white_loss_prob or 0.0,
        )
    if data.lc0_black_win_prob is not None:
        wdl_section += _wdl_row(
            "♟", data.black,
            data.lc0_black_win_prob,
            data.lc0_black_draw_prob or 0.0,
            data.lc0_black_loss_prob or 0.0,
        )

    errors_section = ""
    lc0_errors = [
        data.lc0_white_inaccuracies, data.lc0_white_mistakes, data.lc0_white_blunders,
        data.lc0_black_inaccuracies, data.lc0_black_mistakes, data.lc0_black_blunders,
    ]
    if any(v is not None for v in lc0_errors):
        errors_section = '<hr class="dub-rule"><div class="dub-lbl">Move Errors</div>'

        def _count_span(n: Optional[int], lbl: str, cls: str) -> str:
            """Format a single error count span."""
            if n is None:
                return ""
            return f'<span style="font-size:.70rem;font-weight:700;color:{cls}">{n}</span><span style="font-size:.54rem;letter-spacing:.05em;color:#5A5A5A;margin-left:2px;margin-right:8px">{lbl}</span>'

        for sym, name, inac, mist, blun in [
            ("♙", data.white, data.lc0_white_inaccuracies, data.lc0_white_mistakes, data.lc0_white_blunders),
            ("♟", data.black, data.lc0_black_inaccuracies, data.lc0_black_mistakes, data.lc0_black_blunders),
        ]:
            counts = (
                _count_span(inac, "inaccuracy", "#E07B7B")
                + _count_span(mist, "mistake", "#CE3A4A")
                + _count_span(blun, "blunder", "#B53541")
            )
            errors_section += (
                f'<div class="dub-row">'
                f'<div class="dub-player-lbl"><span class="dub-chess">{sym}</span>{escape(name)}</div>'
                f'<div style="grid-column:2/4;display:flex;align-items:baseline;flex-wrap:wrap">{counts}</div>'
                f"</div>"
            )

    return (
        f'<div class="dub">'
        f'<div class="dub-head">'
        f'<span class="dub-title">Lc0 Neural Network</span>'
        f'<span class="dub-meta">{escape(meta)}</span>'
        f"</div>"
        + wdl_section + errors_section
        + _rerun_button("lc0", queued)
        + "</div>"
    )


def build_stat_cards_html(data: GameAnalysisData, sf_queued: bool = False, lc0_queued: bool = False) -> str:
    """
    Return the full Du Bois stat cards HTML block (CSS + SF card + Lc0 card).

    Params:
        data (GameAnalysisData): Assembled game analysis data.
        sf_queued (bool): Whether a Stockfish job is currently active.
        lc0_queued (bool): Whether an Lc0 job is currently active.

    Returns:
        Complete HTML block with inline CSS and both engine cards.
    """
    cards = build_sf_card(data, queued=sf_queued) + build_lc0_card(data, queued=lc0_queued)
    if not cards:
        return '<p class="font-mono text-sm text-slate">No engine analysis available yet.</p>'
    return _DUB_CSS + cards
