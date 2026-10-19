import json
import time
import urllib.error
import urllib.request
from urllib.parse import quote

from config import RIOT_API_KEY

TIMEOUT = 10
MAX_RETRIES = 5

# Riot's API sits behind Cloudflare, which blocks the default
# "Python-urllib/x.y" user agent (WAF error code 1010).
BROWSER_HEADERS = {
    "X-Riot-Token": RIOT_API_KEY,
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    ),
}


def _get(url: str) -> dict | list:
    request = urllib.request.Request(url, headers=BROWSER_HEADERS)
    for _ in range(MAX_RETRIES):
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
                return json.loads(response.read())
        except urllib.error.HTTPError as exc:
            if exc.code == 429:
                retry_after = float(exc.headers.get("Retry-After", "1"))
                time.sleep(retry_after)
                continue
            raise
    raise RuntimeError(f"Rate limited too many times fetching {url}")


def get_account_by_riot_id(region: str, game_name: str, tag_line: str) -> dict:
    url = (
        f"https://{region}.api.riotgames.com/riot/account/v1/accounts/"
        f"by-riot-id/{quote(game_name)}/{quote(tag_line)}"
    )
    return _get(url)


def get_summoner_by_puuid(platform: str, puuid: str) -> dict:
    url = f"https://{platform}.api.riotgames.com/lol/summoner/v4/summoners/by-puuid/{puuid}"
    return _get(url)


def get_league_entries_by_puuid(platform: str, puuid: str) -> list[dict]:
    url = f"https://{platform}.api.riotgames.com/lol/league/v4/entries/by-puuid/{puuid}"
    return _get(url)


def get_match_ids(region: str, puuid: str, start: int, count: int, queue: int | None = None) -> list[str]:
    url = (
        f"https://{region}.api.riotgames.com/lol/match/v5/matches/"
        f"by-puuid/{puuid}/ids?start={start}&count={count}"
    )
    if queue is not None:
        url += f"&queue={queue}"
    return _get(url)


def get_match(region: str, match_id: str) -> dict:
    url = f"https://{region}.api.riotgames.com/lol/match/v5/matches/{match_id}"
    return _get(url)


def get_match_timeline(region: str, match_id: str) -> dict:
    url = f"https://{region}.api.riotgames.com/lol/match/v5/matches/{match_id}/timeline"
    return _get(url)


def get_ddragon_latest_version() -> str:
    request = urllib.request.Request("https://ddragon.leagueoflegends.com/api/versions.json")
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        return json.loads(response.read())[0]


def get_ddragon_runes(version: str) -> list:
    url = f"https://ddragon.leagueoflegends.com/cdn/{version}/data/en_US/runesReforged.json"
    request = urllib.request.Request(url)
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        return json.loads(response.read())


def get_ddragon_champions(version: str) -> dict:
    url = f"https://ddragon.leagueoflegends.com/cdn/{version}/data/en_US/champion.json"
    request = urllib.request.Request(url)
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        return json.loads(response.read())


def get_champion_mastery_top(platform: str, puuid: str, count: int = 5) -> list:
    url = (
        f"https://{platform}.api.riotgames.com/lol/champion-mastery/v4/"
        f"champion-masteries/by-puuid/{puuid}/top?count={count}"
    )
    return _get(url)


def get_active_game(platform: str, puuid: str) -> dict | None:
    url = f"https://{platform}.api.riotgames.com/lol/spectator/v5/active-games/by-summoner/{puuid}"
    request = urllib.request.Request(url, headers=BROWSER_HEADERS)
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise
