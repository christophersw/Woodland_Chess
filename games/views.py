"""Views for rendering game analysis pages."""

from django.shortcuts import render, get_object_or_404, redirect
from django.http import Http404

from games.models import Game
from games.services import get_game_analysis
from games.board_builder import build_board_viewer_html
from games.stat_cards import build_stat_cards_html


def game_analysis(request, slug):
    """Render interactive game analysis page with board viewer and stat cards."""
    game = get_object_or_404(Game, slug=slug)
    data = get_game_analysis(slug)

    if data is None or not data.moves:
        return render(request, "games/analysis.html", {
            "game": game,
            "no_data": True,
        })

    orientation = request.GET.get("orientation", "white")
    if orientation not in ("white", "black"):
        orientation = "white"

    board_html = build_board_viewer_html(data, size=480, orientation=orientation)
    stat_cards_html = build_stat_cards_html(data)

    details_parts = []
    if data.date:
        details_parts.append(data.date)
    if data.time_control:
        details_parts.append(data.time_control)

    opening_label = data.lichess_opening or data.opening_name or ""
    if data.eco_code and data.opening_name:
        opening_label = f"{data.eco_code} · {data.opening_name}"
    elif data.eco_code:
        opening_label = data.eco_code

    return render(request, "games/analysis.html", {
        "game": game,
        "data": data,
        "board_html": board_html,
        "stat_cards_html": stat_cards_html,
        "details": " · ".join(details_parts),
        "opening_label": opening_label,
        "chesscom_url": data.url,
        "flip_url": request.path + "?orientation=" + ("black" if orientation == "white" else "white"),
        "orientation": orientation,
        "no_data": False,
    })
