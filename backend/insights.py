from datetime import datetime
from zoneinfo import ZoneInfo

from stats import display_name

LOCAL_TZ = ZoneInfo("America/Argentina/Buenos_Aires")


def _mvp_score(match: dict, participant: dict) -> float:
    duration_min = match["info"]["gameDuration"] / 60
    cs = participant["totalMinionsKilled"] + participant["neutralMinionsKilled"]
    kda = (participant["kills"] + participant["assists"]) / max(participant["deaths"], 1)
    return (
        kda * 2
        + participant["totalDamageDealtToChampions"] / 1000
        + participant["goldEarned"] / 500
        + participant.get("visionScore", 0) * 0.5
        + (cs / duration_min if duration_min else 0)
    )


def compute_game_mvp(match: dict) -> dict:
    participants = match["info"]["participants"]
    best = max(participants, key=lambda p: _mvp_score(match, p))
    return {
        "name": display_name(best),
        "championName": best["championName"],
        "teamId": best["teamId"],
        "win": best["win"],
    }


def compute_improvement_tips(match: dict, puuid: str) -> list[str]:
    participants = match["info"]["participants"]
    you = next(p for p in participants if p["puuid"] == puuid)
    your_team = [p for p in participants if p["teamId"] == you["teamId"]]
    duration_min = match["info"]["gameDuration"] / 60

    tips = []

    team_avg_vision = sum(p.get("visionScore", 0) for p in your_team) / len(your_team)
    if you.get("visionScore", 0) < team_avg_vision * 0.6:
        tips.append("Tu visión estuvo por debajo del promedio de tu equipo — sumá más wards/control wards.")

    if you["deaths"] >= 7:
        tips.append(f"Moriste {you['deaths']} veces — cuidado con el posicionamiento en peleas.")

    team_kills = sum(p["kills"] for p in your_team)
    kill_participation = (you["kills"] + you["assists"]) / max(team_kills, 1)
    if kill_participation < 0.4:
        tips.append("Baja participación en peleas grupales (menos del 40% de las kills de tu equipo).")

    cs_per_min = (you["totalMinionsKilled"] + you["neutralMinionsKilled"]) / duration_min if duration_min else 0
    if you.get("teamPosition") in ("TOP", "MIDDLE", "BOTTOM", "JUNGLE") and cs_per_min < 5.5:
        tips.append(f"CS/min bajo ({cs_per_min:.1f}) para tu rol — priorizá el farmeo entre peleas.")

    if not tips:
        tips.append("Buen balance general en esta partida, sin puntos débiles claros.")

    return tips[:3]


def compute_frequent_teammates(matches: list[dict], puuid: str, top_n: int = 5) -> list[dict]:
    agg: dict[str, dict] = {}

    for match in matches:
        participants = match["info"]["participants"]
        you = next(p for p in participants if p["puuid"] == puuid)
        teammates = [p for p in participants if p["teamId"] == you["teamId"] and p["puuid"] != puuid]

        for mate in teammates:
            entry = agg.setdefault(mate["puuid"], {"name": display_name(mate), "games": 0, "wins": 0})
            entry["games"] += 1
            entry["wins"] += int(you["win"])

    ranked = sorted(agg.values(), key=lambda a: a["games"], reverse=True)
    return [
        {**a, "winrate": round(100 * a["wins"] / a["games"], 1)}
        for a in ranked
        if a["games"] >= 2
    ][:top_n]


def compute_activity_heatmap(matches: list[dict]) -> list[dict]:
    grid: dict[tuple[int, int], int] = {}

    for match in matches:
        dt = datetime.fromtimestamp(match["info"]["gameCreation"] / 1000, tz=LOCAL_TZ)
        key = (dt.weekday(), dt.hour)  # Monday=0 .. Sunday=6
        grid[key] = grid.get(key, 0) + 1

    return [{"day": day, "hour": hour, "count": count} for (day, hour), count in grid.items()]
