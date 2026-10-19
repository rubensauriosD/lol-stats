from datetime import datetime, timezone

QUEUE_RANKED_SOLO_DUO = 420

ROLE_LABELS = {
    "TOP": "Top",
    "JUNGLE": "Jungla",
    "MIDDLE": "Mid",
    "BOTTOM": "ADC",
    "UTILITY": "Support",
}

TIER_ORDER = [
    "IRON", "BRONZE", "SILVER", "GOLD", "PLATINUM", "EMERALD",
    "DIAMOND", "MASTER", "GRANDMASTER", "CHALLENGER",
]
DIVISION_VALUE = {"IV": 0, "III": 1, "II": 2, "I": 3}

# Stat shard (rune) IDs are not in Data Dragon; these are Riot's fixed,
# long-stable IDs (verified against CommunityDragon's perks.json).
STAT_SHARD_NAMES = {
    5001: "Escalado de Vida",
    5002: "Armadura",
    5003: "Resistencia Mágica",
    5005: "Velocidad de Ataque",
    5007: "Templanza de Habilidades",
    5008: "Fuerza Adaptativa",
    5010: "Velocidad de Movimiento",
    5011: "Vida",
    5012: "Escalado de Resistencias",
    5013: "Tenacidad y Resist. a Ralentización",
}


def rank_to_value(tier: str, division: str, lp: int) -> int:
    tier_index = TIER_ORDER.index(tier) if tier in TIER_ORDER else 0
    division_value = DIVISION_VALUE.get(division, 0)
    return tier_index * 400 + division_value * 100 + lp


def _participant_for(match: dict, puuid: str) -> dict:
    return next(p for p in match["info"]["participants"] if p["puuid"] == puuid)


def display_name(participant: dict) -> str:
    game_name = participant.get("riotIdGameName")
    tag_line = participant.get("riotIdTagline")
    if game_name:
        return f"{game_name}#{tag_line}" if tag_line else game_name
    return participant.get("summonerName", "Unknown")


def build_rune_maps(runes_reforged: list) -> dict:
    perks = {}
    styles = {}
    for tree in runes_reforged:
        styles[tree["id"]] = {
            "name": tree["name"],
            "icon": f"https://ddragon.leagueoflegends.com/cdn/img/{tree['icon']}",
        }
        for slot in tree["slots"]:
            for rune in slot["runes"]:
                perks[rune["id"]] = {
                    "name": rune["name"],
                    "icon": f"https://ddragon.leagueoflegends.com/cdn/img/{rune['icon']}",
                }
    return {"perks": perks, "styles": styles}


def _rune_perk_info(perk_id: int, rune_maps: dict) -> dict:
    info = rune_maps["perks"].get(perk_id)
    return {"id": perk_id, "name": info["name"] if info else str(perk_id), "icon": info["icon"] if info else None}


def _rune_style_info(style_id: int, rune_maps: dict) -> dict:
    info = rune_maps["styles"].get(style_id)
    return {"id": style_id, "name": info["name"] if info else str(style_id), "icon": info["icon"] if info else None}


def build_runes_view(participant: dict, rune_maps: dict, full: bool) -> dict | None:
    perks = participant.get("perks")
    if not perks or not perks.get("styles"):
        return None

    primary, secondary = perks["styles"][0], perks["styles"][1]
    primary_style = _rune_style_info(primary["style"], rune_maps)
    secondary_style = _rune_style_info(secondary["style"], rune_maps)

    if not full:
        return {
            "primaryStyle": primary_style,
            "secondaryStyle": secondary_style,
            "keystone": _rune_perk_info(primary["selections"][0]["perk"], rune_maps),
        }

    stat_perks = perks.get("statPerks", {})
    return {
        "primaryStyle": primary_style,
        "primaryRunes": [_rune_perk_info(s["perk"], rune_maps) for s in primary["selections"]],
        "secondaryStyle": secondary_style,
        "secondaryRunes": [_rune_perk_info(s["perk"], rune_maps) for s in secondary["selections"]],
        "statShards": {
            slot: STAT_SHARD_NAMES.get(perk_id, str(perk_id))
            for slot, perk_id in stat_perks.items()
        },
    }


def summarize_match(match: dict, puuid: str) -> dict:
    p = _participant_for(match, puuid)
    duration_min = match["info"]["gameDuration"] / 60
    cs = p["totalMinionsKilled"] + p["neutralMinionsKilled"]
    role = p.get("teamPosition") or "UNKNOWN"

    return {
        "matchId": match["metadata"]["matchId"],
        "champion": p["championName"],
        "win": p["win"],
        "kills": p["kills"],
        "deaths": p["deaths"],
        "assists": p["assists"],
        "role": ROLE_LABELS.get(role, "Otro"),
        "cs": cs,
        "csPerMin": round(cs / duration_min, 1) if duration_min else 0,
        "visionScore": p.get("visionScore", 0),
        "durationMin": round(duration_min),
        "queueId": match["info"]["queueId"],
        "date": datetime.fromtimestamp(match["info"]["gameCreation"] / 1000, tz=timezone.utc).isoformat(),
    }


def compute_dashboard_stats(matches: list[dict], puuid: str) -> dict:
    # matches are expected newest-first
    participants = [_participant_for(m, puuid) for m in matches]

    games = len(participants)
    wins = sum(1 for p in participants if p["win"])

    champ_agg: dict[str, dict] = {}
    role_agg: dict[str, int] = {}
    kills = deaths = assists = 0
    trend = []

    for p in participants:
        champ_agg.setdefault(p["championName"], {"games": 0, "wins": 0})
        champ_agg[p["championName"]]["games"] += 1
        champ_agg[p["championName"]]["wins"] += int(p["win"])

        role = p.get("teamPosition") or "UNKNOWN"
        role_agg[role] = role_agg.get(role, 0) + 1

        kills += p["kills"]
        deaths += p["deaths"]
        assists += p["assists"]
        trend.append("W" if p["win"] else "L")

    top_champions = sorted(
        (
            {
                "name": name,
                "games": data["games"],
                "wins": data["wins"],
                "winrate": round(100 * data["wins"] / data["games"], 1),
            }
            for name, data in champ_agg.items()
        ),
        key=lambda c: c["games"],
        reverse=True,
    )[:8]

    roles = {ROLE_LABELS.get(role, "Otro"): count for role, count in role_agg.items()}
    chronological_trend = list(reversed(trend))

    return {
        "games": games,
        "wins": wins,
        "losses": games - wins,
        "winrate": round(100 * wins / games, 1) if games else 0,
        "avgKda": {
            "kills": round(kills / games, 1) if games else 0,
            "deaths": round(deaths / games, 1) if games else 0,
            "assists": round(assists / games, 1) if games else 0,
            "ratio": round((kills + assists) / max(deaths, 1), 2) if games else 0,
        },
        "topChampions": top_champions,
        "roles": roles,
        "recent": [summarize_match(m, puuid) for m in matches],
        "trend": chronological_trend,  # chronological order for sparkline
        "streak": _compute_streak(chronological_trend),
    }


def _compute_streak(chronological_trend: list[str]) -> dict:
    if not chronological_trend:
        return {"type": None, "count": 0}
    last = chronological_trend[-1]
    count = 0
    for result in reversed(chronological_trend):
        if result != last:
            break
        count += 1
    return {"type": last, "count": count}


def _team_participant_view(p: dict, is_you: bool, rune_maps: dict) -> dict:
    return {
        "puuid": p["puuid"],
        "isYou": is_you,
        "name": display_name(p),
        "championName": p["championName"],
        "role": ROLE_LABELS.get(p.get("teamPosition") or "UNKNOWN", "Otro"),
        "win": p["win"],
        "kills": p["kills"],
        "deaths": p["deaths"],
        "assists": p["assists"],
        "cs": p["totalMinionsKilled"] + p["neutralMinionsKilled"],
        "goldEarned": p["goldEarned"],
        "damageDealt": p["totalDamageDealtToChampions"],
        "damageTaken": p["totalDamageTaken"],
        "visionScore": p.get("visionScore", 0),
        "runes": build_runes_view(p, rune_maps, full=is_you),
    }


def _objectives_view(team: dict) -> dict:
    objectives = team["objectives"]
    return {
        obj_name: objectives[obj_name]["kills"]
        for obj_name in ("baron", "dragon", "tower", "inhibitor", "riftHerald")
        if obj_name in objectives
    }


def compute_match_detail(match: dict, puuid: str, rune_maps: dict) -> dict:
    info = match["info"]
    you = _participant_for(match, puuid)
    your_team_id = you["teamId"]

    teams = []
    for team in info["teams"]:
        team_participants = [p for p in info["participants"] if p["teamId"] == team["teamId"]]
        total_gold = sum(p["goldEarned"] for p in team_participants)
        total_damage = sum(p["totalDamageDealtToChampions"] for p in team_participants)
        total_kills = sum(p["kills"] for p in team_participants)

        teams.append(
            {
                "teamId": team["teamId"],
                "win": team["win"],
                "objectives": _objectives_view(team),
                "totalGold": total_gold,
                "totalDamage": total_damage,
                "totalKills": total_kills,
                "participants": [
                    _team_participant_view(p, is_you=p["puuid"] == puuid, rune_maps=rune_maps)
                    for p in team_participants
                ],
            }
        )

    your_team = next(t for t in teams if t["teamId"] == your_team_id)
    enemy_team = next(t for t in teams if t["teamId"] != your_team_id)

    kill_participation = (you["kills"] + you["assists"]) / max(your_team["totalKills"], 1)
    damage_share = you["totalDamageDealtToChampions"] / max(your_team["totalDamage"], 1)
    gold_share = you["goldEarned"] / max(your_team["totalGold"], 1)

    summary_parts = ["Victoria" if you["win"] else "Derrota"]
    if damage_share >= 0.30:
        summary_parts.append("mayor daño de tu equipo")
    elif damage_share < 0.12:
        summary_parts.append("daño bajo respecto al equipo")
    if kill_participation >= 0.7:
        summary_parts.append("alta participación en kills")
    elif kill_participation < 0.3:
        summary_parts.append("baja participación en kills")

    return {
        "matchId": match["metadata"]["matchId"],
        "queueId": info["queueId"],
        "durationMin": round(info["gameDuration"] / 60),
        "date": datetime.fromtimestamp(info["gameCreation"] / 1000, tz=timezone.utc).isoformat(),
        "win": you["win"],
        "yourPuuid": puuid,
        "teams": teams,
        "analysis": {
            "killParticipation": round(100 * kill_participation, 1),
            "damageShare": round(100 * damage_share, 1),
            "goldShare": round(100 * gold_share, 1),
            "summary": ", ".join(summary_parts),
        },
    }


def compute_gold_diff_timeline(match: dict, timeline: dict, puuid: str) -> list[dict]:
    participants = match["info"]["participants"]
    your_team_id = next(p["teamId"] for p in participants if p["puuid"] == puuid)
    enemy_team_id = 200 if your_team_id == 100 else 100
    pid_to_team = {p["participantId"]: p["teamId"] for p in participants}

    points = []
    for frame in timeline["info"]["frames"]:
        minute = round(frame["timestamp"] / 60000)
        team_gold = {100: 0, 200: 0}
        for pid_str, pframe in frame["participantFrames"].items():
            team_gold[pid_to_team[int(pid_str)]] += pframe["totalGold"]
        points.append({"minute": minute, "diff": team_gold[your_team_id] - team_gold[enemy_team_id]})
    return points
