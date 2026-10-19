import json
import mimetypes
import re
import time
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import cache
import insights
import riot_client
import stats
from config import BASE_DIR, load_accounts

STATIC_DIR = BASE_DIR / "static"
DASHBOARD_RE = re.compile(r"^/api/accounts/(\d+)/dashboard$")
MATCHES_LIST_RE = re.compile(r"^/api/accounts/(\d+)/matches$")
MATCH_DETAIL_RE = re.compile(r"^/api/accounts/(\d+)/matches/([\w-]+)$")
TEAMMATES_RE = re.compile(r"^/api/accounts/(\d+)/teammates$")
ACTIVITY_RE = re.compile(r"^/api/accounts/(\d+)/activity$")
MASTERY_RE = re.compile(r"^/api/accounts/(\d+)/mastery$")
LIVE_RE = re.compile(r"^/api/accounts/(\d+)/live$")

_executor = ThreadPoolExecutor(max_workers=8)
_ddragon_version: str | None = None
_rune_maps: dict | None = None
_champion_map: dict[int, str] | None = None


class AccountNotFoundError(Exception):
    pass


def _riot_id_key(account: dict) -> str:
    return f"{account['gameName']}#{account['tagLine']}"


def _get_ddragon_version() -> str:
    global _ddragon_version
    if _ddragon_version is None:
        _ddragon_version = riot_client.get_ddragon_latest_version()
    return _ddragon_version


def _get_rune_maps() -> dict:
    global _rune_maps
    if _rune_maps is None:
        runes_reforged = riot_client.get_ddragon_runes(_get_ddragon_version())
        _rune_maps = stats.build_rune_maps(runes_reforged)
    return _rune_maps


def _get_champion_map() -> dict[int, str]:
    global _champion_map
    if _champion_map is None:
        raw = riot_client.get_ddragon_champions(_get_ddragon_version())
        _champion_map = {int(champ["key"]): name for name, champ in raw["data"].items()}
    return _champion_map


def _champion_icon_url(champion_name: str) -> str:
    return f"https://ddragon.leagueoflegends.com/cdn/{_get_ddragon_version()}/img/champion/{champion_name}.png"


def _resolve_puuid(account: dict) -> str:
    key = _riot_id_key(account)
    cached = cache.get_cached_puuid(key)
    if cached:
        return cached
    data = riot_client.get_account_by_riot_id(account["region"], account["gameName"], account["tagLine"])
    cache.save_puuid(key, data["puuid"])
    return data["puuid"]


def _fetch_ranked_matches(account: dict, puuid: str, start: int, count: int) -> list[dict]:
    match_ids = riot_client.get_match_ids(
        account["region"], puuid, start=start, count=count, queue=stats.QUEUE_RANKED_SOLO_DUO
    )
    cached_ids = cache.get_cached_match_ids(puuid)
    missing = [mid for mid in match_ids if mid not in cached_ids]

    def _fetch_and_save(match_id: str) -> None:
        match = riot_client.get_match(account["region"], match_id)
        cache.save_match(puuid, match_id, match)

    if missing:
        list(_executor.map(_fetch_and_save, missing))

    return [cache.get_match(mid) for mid in match_ids]


def _get_account_or_raise(idx: int) -> dict:
    accounts = load_accounts()
    if idx < 0 or idx >= len(accounts):
        raise AccountNotFoundError(f"Account index {idx} not found")
    return accounts[idx]


def _maybe_save_rank_snapshot(puuid: str, solo_queue: dict | None) -> None:
    if not solo_queue:
        return
    last = cache.get_latest_rank_snapshot(puuid)
    current_total = solo_queue["wins"] + solo_queue["losses"]
    if last is not None and last["wins"] + last["losses"] == current_total:
        return  # no new ranked game finished since last check
    cache.save_rank_snapshot(
        puuid,
        captured_at=int(time.time() * 1000),
        tier=solo_queue["tier"],
        division=solo_queue["rank"],
        lp=solo_queue["leaguePoints"],
        wins=solo_queue["wins"],
        losses=solo_queue["losses"],
    )


def list_accounts() -> list[dict]:
    accounts = load_accounts()
    return [
        {"index": i, "label": a["label"], "gameName": a["gameName"], "tagLine": a["tagLine"]}
        for i, a in enumerate(accounts)
    ]


def get_dashboard(idx: int, count: int) -> dict:
    account = _get_account_or_raise(idx)

    ddragon_version = _get_ddragon_version()
    puuid = _resolve_puuid(account)

    summoner = riot_client.get_summoner_by_puuid(account["platform"], puuid)
    league_entries = riot_client.get_league_entries_by_puuid(account["platform"], puuid)
    matches = _fetch_ranked_matches(account, puuid, start=0, count=count)

    solo_queue = next((e for e in league_entries if e["queueType"] == "RANKED_SOLO_5x5"), None)
    _maybe_save_rank_snapshot(puuid, solo_queue)

    rank_history = [
        {**snap, "value": stats.rank_to_value(snap["tier"], snap["division"], snap["lp"])}
        for snap in cache.get_rank_history(puuid)
    ]

    return {
        "account": {"label": account["label"], "gameName": account["gameName"], "tagLine": account["tagLine"]},
        "profile": {
            "summonerLevel": summoner["summonerLevel"],
            "profileIconUrl": (
                f"https://ddragon.leagueoflegends.com/cdn/{ddragon_version}/img/"
                f"profileicon/{summoner['profileIconId']}.png"
            ),
            "rank": (
                {
                    "tier": solo_queue["tier"],
                    "division": solo_queue["rank"],
                    "lp": solo_queue["leaguePoints"],
                    "wins": solo_queue["wins"],
                    "losses": solo_queue["losses"],
                }
                if solo_queue
                else None
            ),
        },
        "ddragonVersion": ddragon_version,
        "stats": stats.compute_dashboard_stats(matches, puuid),
        "rankHistory": rank_history,
    }


def get_matches_page(idx: int, offset: int, limit: int) -> list[dict]:
    account = _get_account_or_raise(idx)
    puuid = _resolve_puuid(account)
    matches = _fetch_ranked_matches(account, puuid, start=offset, count=limit)
    return [stats.summarize_match(m, puuid) for m in matches]


def _compute_champion_baseline(puuid: str, champion_name: str, exclude_match_id: str) -> dict | None:
    matches = cache.get_all_cached_matches(puuid, stats.QUEUE_RANKED_SOLO_DUO)
    samples = []
    for match in matches:
        if match["metadata"]["matchId"] == exclude_match_id:
            continue
        p = next((pp for pp in match["info"]["participants"] if pp["puuid"] == puuid), None)
        if p is None or p["championName"] != champion_name:
            continue
        duration_min = match["info"]["gameDuration"] / 60
        samples.append(
            {
                "kda": (p["kills"] + p["assists"]) / max(p["deaths"], 1),
                "damage": p["totalDamageDealtToChampions"],
                "gold": p["goldEarned"],
                "csPerMin": (p["totalMinionsKilled"] + p["neutralMinionsKilled"]) / duration_min if duration_min else 0,
            }
        )

    if not samples:
        return None

    n = len(samples)
    return {
        "gamesSampled": n,
        "avgKda": round(sum(s["kda"] for s in samples) / n, 2),
        "avgDamage": round(sum(s["damage"] for s in samples) / n),
        "avgGold": round(sum(s["gold"] for s in samples) / n),
        "avgCsPerMin": round(sum(s["csPerMin"] for s in samples) / n, 1),
    }


def get_match_detail(idx: int, match_id: str) -> dict:
    account = _get_account_or_raise(idx)
    puuid = _resolve_puuid(account)

    match = cache.get_match(match_id)
    if match is None:
        match = riot_client.get_match(account["region"], match_id)
        cache.save_match(puuid, match_id, match)

    timeline = cache.get_timeline(match_id)
    if timeline is None:
        timeline = riot_client.get_match_timeline(account["region"], match_id)
        cache.save_timeline(match_id, timeline)

    detail = stats.compute_match_detail(match, puuid, _get_rune_maps())
    detail["goldDiffTimeline"] = stats.compute_gold_diff_timeline(match, timeline, puuid)
    detail["analysis"]["gameMvp"] = insights.compute_game_mvp(match)
    detail["analysis"]["improvementTips"] = insights.compute_improvement_tips(match, puuid)

    you = next(p for p in match["info"]["participants"] if p["puuid"] == puuid)
    baseline = _compute_champion_baseline(puuid, you["championName"], exclude_match_id=match_id)
    if baseline:
        detail["analysis"]["vsYourAverage"] = baseline

    return detail


def get_teammates(idx: int) -> list[dict]:
    account = _get_account_or_raise(idx)
    puuid = _resolve_puuid(account)
    matches = cache.get_all_cached_matches(puuid, stats.QUEUE_RANKED_SOLO_DUO)
    return insights.compute_frequent_teammates(matches, puuid)


def get_activity(idx: int) -> list[dict]:
    account = _get_account_or_raise(idx)
    puuid = _resolve_puuid(account)
    matches = cache.get_all_cached_matches(puuid, stats.QUEUE_RANKED_SOLO_DUO)
    return insights.compute_activity_heatmap(matches)


def get_mastery(idx: int) -> list[dict]:
    account = _get_account_or_raise(idx)
    puuid = _resolve_puuid(account)
    champion_map = _get_champion_map()
    top = riot_client.get_champion_mastery_top(account["platform"], puuid, count=5)
    return [
        {
            "championName": champion_map.get(m["championId"], f"Champion{m['championId']}"),
            "championIconUrl": _champion_icon_url(champion_map.get(m["championId"], "")),
            "level": m["championLevel"],
            "points": m["championPoints"],
        }
        for m in top
    ]


def get_live_status(idx: int) -> dict:
    account = _get_account_or_raise(idx)
    puuid = _resolve_puuid(account)
    game = riot_client.get_active_game(account["platform"], puuid)
    if game is None:
        return {"inGame": False}

    champion_map = _get_champion_map()
    participants = [
        {
            "championName": champion_map.get(p["championId"], f"Champion{p['championId']}"),
            "championIconUrl": _champion_icon_url(champion_map.get(p["championId"], "")),
            "teamId": p["teamId"],
            "isYou": p["puuid"] == puuid,
        }
        for p in game["participants"]
    ]
    return {
        "inGame": True,
        "gameMode": game.get("gameMode"),
        "gameLengthSec": game.get("gameLength"),
        "participants": participants,
    }


class Handler(BaseHTTPRequestHandler):
    def _send_json(self, payload: object, status: int = 200) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _serve_static(self, path: str) -> None:
        if path == "/":
            path = "/index.html"
        file_path = (STATIC_DIR / path.lstrip("/")).resolve()
        if not file_path.is_relative_to(STATIC_DIR) or not file_path.is_file():
            self.send_error(404)
            return
        content_type, _ = mimetypes.guess_type(str(file_path))
        data = file_path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type or "application/octet-stream")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        try:
            if path == "/api/accounts":
                self._send_json(list_accounts())
                return

            match = DASHBOARD_RE.match(path)
            if match:
                idx = int(match.group(1))
                count = int(query.get("count", ["20"])[0])
                self._send_json(get_dashboard(idx, count))
                return

            match = MATCHES_LIST_RE.match(path)
            if match:
                idx = int(match.group(1))
                offset = int(query.get("offset", ["0"])[0])
                limit = int(query.get("limit", ["10"])[0])
                self._send_json(get_matches_page(idx, offset, limit))
                return

            match = MATCH_DETAIL_RE.match(path)
            if match:
                idx = int(match.group(1))
                match_id = match.group(2)
                self._send_json(get_match_detail(idx, match_id))
                return

            match = TEAMMATES_RE.match(path)
            if match:
                self._send_json(get_teammates(int(match.group(1))))
                return

            match = ACTIVITY_RE.match(path)
            if match:
                self._send_json(get_activity(int(match.group(1))))
                return

            match = MASTERY_RE.match(path)
            if match:
                self._send_json(get_mastery(int(match.group(1))))
                return

            match = LIVE_RE.match(path)
            if match:
                self._send_json(get_live_status(int(match.group(1))))
                return

            self._serve_static(path)
        except AccountNotFoundError as exc:
            self._send_json({"error": str(exc)}, status=404)
        except Exception as exc:  # boundary for this single-user local app
            self._send_json({"error": str(exc)}, status=500)

    def log_message(self, format: str, *args) -> None:
        print(f"{self.address_string()} - {format % args}")


def run(port: int = 8000) -> None:
    server = ThreadingHTTPServer(("localhost", port), Handler)
    print(f"LoL Stats Tracker running at http://localhost:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()


if __name__ == "__main__":
    run()
