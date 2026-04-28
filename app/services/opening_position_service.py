"""Data service for the Opening Position detail page.

Given an OpeningBook.id, provides:
  - Opening metadata (eco, name, pgn, ply depth)
  - Games that passed through the opening position (EPD match)
  - Per-player W/D/L and accuracy stats
  - Opening share vs all openings (for pie chart)
  - Frequency-over-time per player (for trend line)
  - Continuation flow for Sankey (3 more moves deep)
"""

from __future__ import annotations

import io
from collections import defaultdict
from datetime import datetime, timedelta

import chess
import chess.pgn
import pandas as pd
from sqlalchemy import and_, func, select

from app.services.opening_book import lookup_opening
from app.storage.database import get_session, init_db
from app.storage.models import (
    Game,
    GameAnalysis,
    GameParticipant,
    Lc0GameAnalysis,
    OpeningBook,
    Player,
)


def _parse_opening_pgn(pgn_text: str) -> tuple[chess.Board, int]:
    """Play through the opening PGN and return the resulting board and ply depth."""
    board = chess.Board()
    for token in pgn_text.split():
        token = token.rstrip(".")
        if not token or token[0].isdigit():
            continue
        try:
            board.push_san(token)
        except Exception:
            pass
    return board, board.ply()


class OpeningPositionService:
    def __init__(self) -> None:
        init_db()

    # ── Opening metadata ─────────────────────────────────────────────────────

    def get_opening(self, opening_id: int) -> dict | None:
        """Return opening metadata dict or None if not found."""
        with get_session() as session:
            ob = session.get(OpeningBook, opening_id)
            if ob is None:
                return None
            board, ply_depth = _parse_opening_pgn(ob.pgn or "")
            return {
                "id": ob.id,
                "eco": ob.eco,
                "name": ob.name,
                "pgn": ob.pgn or "",
                "epd": ob.epd or "",
                "ply_depth": ply_depth,
                "final_fen": board.fen(),
            }

    def search_openings(self, query: str, limit: int = 30) -> list[dict]:
        """Search openings by name fragment, return list of dicts."""
        with get_session() as session:
            rows = session.execute(
                select(OpeningBook.id, OpeningBook.eco, OpeningBook.name)
                .where(OpeningBook.name.ilike(f"%{query}%"))
                .order_by(OpeningBook.name)
                .limit(limit)
            ).all()
        return [{"id": r.id, "eco": r.eco, "name": r.name} for r in rows]

    # ── Game fetching ────────────────────────────────────────────────────────

    def get_games(
        self,
        opening: dict,
        lookback_days: int | None = 90,
        players: list[str] | None = None,
    ) -> pd.DataFrame:
        """Return all club-player games that passed through the opening position.

        Matches by replaying each game's PGN to ply_depth and comparing EPD.

        Columns: game_id, played_at, club_player, color, result,
                 white_username, black_username, white_accuracy, black_accuracy,
                 white_acpl, black_acpl, player_rating, opponent_rating,
                 result_pgn, pgn
        """
        target_epd = opening["epd"]
        ply_depth = opening["ply_depth"]
        eco = opening["eco"]

        floor_date = (
            datetime.utcnow() - timedelta(days=lookback_days)
            if lookback_days is not None
            else None
        )

        with get_session() as session:
            stmt = (
                select(
                    Game.id.label("game_id"),
                    Game.played_at,
                    Game.white_username,
                    Game.black_username,
                    Game.pgn,
                    Game.result_pgn,
                    GameParticipant.color,
                    GameParticipant.result,
                    GameParticipant.player_rating,
                    GameParticipant.opponent_rating,
                    Player.username.label("club_player"),
                    GameAnalysis.white_accuracy,
                    GameAnalysis.black_accuracy,
                    GameAnalysis.white_acpl,
                    GameAnalysis.black_acpl,
                )
                .join(GameParticipant, GameParticipant.game_id == Game.id)
                .join(Player, Player.id == GameParticipant.player_id)
                .outerjoin(GameAnalysis, GameAnalysis.game_id == Game.id)
                .where(
                    and_(
                        Game.eco_code == eco,
                        Game.pgn.is_not(None),
                        Game.pgn != "",
                    )
                )
                .order_by(Game.played_at.desc())
            )
            if floor_date is not None:
                stmt = stmt.where(Game.played_at >= floor_date)
            if players:
                stmt = stmt.where(
                    func.lower(Player.username).in_([p.lower() for p in players])
                )
            rows = session.execute(stmt).all()

        if not rows:
            return pd.DataFrame()

        # Group by game_id — one row per (game_id, club_player)
        # EPD-filter per unique game_id (only parse PGN once per game)
        seen_game_epd: dict[str, bool] = {}

        def _matches(pgn_text: str, gid: str) -> bool:
            if gid in seen_game_epd:
                return seen_game_epd[gid]
            try:
                game = chess.pgn.read_game(io.StringIO(pgn_text))
                if game is None:
                    seen_game_epd[gid] = False
                    return False
                board = game.board()
                node = game
                for _ in range(ply_depth):
                    if not node.variations:
                        seen_game_epd[gid] = False
                        return False
                    node = node.variations[0]
                    board.push(node.move)
                result = board.ply() == ply_depth and board.epd() == target_epd
            except Exception:
                result = False
            seen_game_epd[gid] = result
            return result

        # Deduplicate (game_id, club_player) and EPD-filter
        seen_keys: set[tuple[str, str]] = set()
        records = []
        for row in rows:
            key = (row.game_id, row.club_player)
            if key in seen_keys:
                continue
            seen_keys.add(key)
            if not _matches(row.pgn, row.game_id):
                continue
            records.append({
                "game_id": row.game_id,
                "played_at": row.played_at,
                "club_player": row.club_player,
                "color": (row.color or "").lower(),
                "result": row.result or "",
                "white_username": row.white_username or "?",
                "black_username": row.black_username or "?",
                "white_accuracy": row.white_accuracy,
                "black_accuracy": row.black_accuracy,
                "white_acpl": row.white_acpl,
                "black_acpl": row.black_acpl,
                "player_rating": row.player_rating,
                "opponent_rating": row.opponent_rating,
                "result_pgn": row.result_pgn or "",
                "pgn": row.pgn or "",
            })

        if not records:
            return pd.DataFrame()

        df = pd.DataFrame(records)
        df["played_at"] = pd.to_datetime(df["played_at"])
        return df

    # ── Per-player stats ─────────────────────────────────────────────────────

    def player_stats(self, games_df: pd.DataFrame) -> pd.DataFrame:
        """Aggregate W/D/L and accuracy per club player.

        Columns: player, games, wins, draws, losses, win_pct, draw_pct,
                 loss_pct, avg_accuracy, avg_acpl, as_white, as_black
        """
        if games_df.empty:
            return pd.DataFrame()

        rows = []
        for player, grp in games_df.groupby("club_player"):
            g = len(grp)
            wins = int((grp["result"] == "Win").sum())
            draws = int((grp["result"] == "Draw").sum())
            losses = int((grp["result"] == "Loss").sum())

            # Accuracy: use the column matching the player's color
            acc_vals = []
            for _, r in grp.iterrows():
                if r["color"] == "white" and r["white_accuracy"] is not None:
                    acc_vals.append(r["white_accuracy"])
                elif r["color"] == "black" and r["black_accuracy"] is not None:
                    acc_vals.append(r["black_accuracy"])

            acpl_vals = []
            for _, r in grp.iterrows():
                if r["color"] == "white" and r["white_acpl"] is not None:
                    acpl_vals.append(r["white_acpl"])
                elif r["color"] == "black" and r["black_acpl"] is not None:
                    acpl_vals.append(r["black_acpl"])

            rows.append({
                "player": player,
                "games": g,
                "wins": wins,
                "draws": draws,
                "losses": losses,
                "win_pct": round(wins / g * 100, 1) if g else 0.0,
                "draw_pct": round(draws / g * 100, 1) if g else 0.0,
                "loss_pct": round(losses / g * 100, 1) if g else 0.0,
                "avg_accuracy": round(sum(acc_vals) / len(acc_vals), 1) if acc_vals else None,
                "avg_acpl": round(sum(acpl_vals) / len(acpl_vals), 1) if acpl_vals else None,
                "as_white": int((grp["color"] == "white").sum()),
                "as_black": int((grp["color"] == "black").sum()),
            })

        return pd.DataFrame(rows).sort_values("games", ascending=False).reset_index(drop=True)

    # ── Opening share (pie) ──────────────────────────────────────────────────

    def opening_share(
        self,
        opening: dict,
        lookback_days: int | None = 90,
        players: list[str] | None = None,
    ) -> pd.DataFrame:
        """Return a 2-row DataFrame for the pie chart:
          this opening vs all other openings, at the same ply depth.

        Columns: slice, games
        """
        eco = opening["eco"]
        floor_date = (
            datetime.utcnow() - timedelta(days=lookback_days)
            if lookback_days is not None
            else None
        )

        with get_session() as session:
            stmt = (
                select(Game.eco_code, func.count().label("n"))
                .join(GameParticipant, GameParticipant.game_id == Game.id)
                .join(Player, Player.id == GameParticipant.player_id)
                .where(Game.pgn.is_not(None), Game.pgn != "")
                .group_by(Game.eco_code)
            )
            if floor_date is not None:
                stmt = stmt.where(Game.played_at >= floor_date)
            if players:
                stmt = stmt.where(
                    func.lower(Player.username).in_([p.lower() for p in players])
                )
            rows = session.execute(stmt).all()

        if not rows:
            return pd.DataFrame(columns=["slice", "games"])

        this_eco = sum(r.n for r in rows if r.eco_code == eco)
        other = sum(r.n for r in rows if r.eco_code != eco)
        return pd.DataFrame([
            {"slice": opening["name"], "games": this_eco},
            {"slice": "All other openings", "games": other},
        ])

    # ── Frequency over time ──────────────────────────────────────────────────

    def frequency_over_time(self, games_df: pd.DataFrame) -> pd.DataFrame:
        """Return per-player monthly game counts for the trend chart.

        Columns: month, player, games
        """
        if games_df.empty:
            return pd.DataFrame(columns=["month", "player", "games"])

        df = games_df.copy()
        df["month"] = df["played_at"].dt.to_period("M").dt.start_time
        grouped = (
            df.groupby(["month", "club_player"], as_index=False)["game_id"]
            .count()
            .rename(columns={"game_id": "games", "club_player": "player"})
            .sort_values(["month", "player"])
        )
        return grouped

    # ── Continuation Sankey ──────────────────────────────────────────────────

    def continuation_flow(
        self,
        games_df: pd.DataFrame,
        opening: dict,
        min_games: int = 2,
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        """Build a 3-level Sankey of continuations beyond the opening position.

        Samples the opening book at opening_ply+2, opening_ply+4, opening_ply+6
        (i.e. 1, 2, and 3 more full moves after the opening).

        Returns (edges_df, node_stats_df) in the same format as
        WelcomeService.get_opening_flow() so welcome_opening_sankey() can render it.
        """
        if games_df.empty:
            return pd.DataFrame(), pd.DataFrame()

        target_epd = opening["epd"]
        ply_depth = opening["ply_depth"]
        opening_name = opening["name"]

        edge_counts: dict[tuple[str, str], int] = defaultdict(int)
        node_data: dict[str, dict] = {}

        # Deduplicate by game_id — one path per game (not per club_player)
        seen_gids: set[str] = set()

        for _, row in games_df.iterrows():
            gid = row["game_id"]
            if gid in seen_gids:
                continue
            seen_gids.add(gid)

            try:
                game = chess.pgn.read_game(io.StringIO(row["pgn"]))
                if game is None:
                    continue
                board = game.board()
                node = game

                # Advance to the opening position
                for _ in range(ply_depth):
                    if not node.variations:
                        break
                    node = node.variations[0]
                    board.push(node.move)

                if board.epd() != target_epd:
                    continue

                # Sample opening names at +2, +4, +6 plies beyond the opening
                continuation_names: list[str] = []
                for i in range(6):
                    if not node.variations:
                        break
                    node = node.variations[0]
                    board.push(node.move)
                    if (i + 1) % 2 == 0:
                        result = lookup_opening(board)
                        if result:
                            _, name = result
                            # Strip opening family prefix for deeper levels
                            if continuation_names and ":" in name:
                                name = name.split(":", 1)[1].strip()
                            if len(name) > 36:
                                name = name[:35] + "…"
                            continuation_names.append(name)
                        else:
                            # Carry forward last known or use opening name
                            continuation_names.append(
                                continuation_names[-1] if continuation_names else opening_name
                            )

                if not continuation_names:
                    continue

                # Deduplicate consecutive identical names
                deduped: list[str] = [continuation_names[0]]
                for nm in continuation_names[1:]:
                    if nm != deduped[-1]:
                        deduped.append(nm)

                # Full path: opening name → continuations
                path = [opening_name] + deduped

            except Exception:
                continue

            # Accumulate stats per node — use the row's result/accuracy
            result_val = row["result"]
            w_acc = row.get("white_accuracy")
            b_acc = row.get("black_accuracy")
            player = row["club_player"]

            for i in range(len(path) - 1):
                edge_counts[(path[i], path[i + 1])] += 1

            for label in path:
                if label not in node_data:
                    node_data[label] = {
                        "games": 0, "wins": 0, "draws": 0, "losses": 0,
                        "white_acc_sum": 0.0, "white_acc_n": 0,
                        "black_acc_sum": 0.0, "black_acc_n": 0,
                        "players": defaultdict(int),
                    }
                nd = node_data[label]
                nd["games"] += 1
                if result_val == "Win":
                    nd["wins"] += 1
                elif result_val == "Draw":
                    nd["draws"] += 1
                else:
                    nd["losses"] += 1
                if w_acc is not None:
                    nd["white_acc_sum"] += w_acc
                    nd["white_acc_n"] += 1
                if b_acc is not None:
                    nd["black_acc_sum"] += b_acc
                    nd["black_acc_n"] += 1
                nd["players"][player] += 1

        if not edge_counts:
            return pd.DataFrame(), pd.DataFrame()

        edges_df = pd.DataFrame(
            [{"source": s, "target": t, "games": c} for (s, t), c in edge_counts.items()]
        )
        edges_df = edges_df[edges_df["games"] >= min_games].reset_index(drop=True)

        node_rows = []
        for label, nd in node_data.items():
            g = nd["games"]
            node_rows.append({
                "node": label,
                "games": g,
                "wins": nd["wins"],
                "draws": nd["draws"],
                "losses": nd["losses"],
                "win_pct": round(nd["wins"] / g * 100, 1) if g else 0.0,
                "draw_pct": round(nd["draws"] / g * 100, 1) if g else 0.0,
                "loss_pct": round(nd["losses"] / g * 100, 1) if g else 0.0,
                "avg_white_accuracy": (
                    round(nd["white_acc_sum"] / nd["white_acc_n"], 1)
                    if nd["white_acc_n"] else None
                ),
                "avg_black_accuracy": (
                    round(nd["black_acc_sum"] / nd["black_acc_n"], 1)
                    if nd["black_acc_n"] else None
                ),
                "players": dict(nd["players"]),
            })

        return edges_df, pd.DataFrame(node_rows)
