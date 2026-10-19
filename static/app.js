const TIER_COLORS = {
  IRON: "#5a5a5a",
  BRONZE: "#8c5a3c",
  SILVER: "#9fa8b3",
  GOLD: "#c89b3c",
  PLATINUM: "#3c9e8f",
  EMERALD: "#2f9e57",
  DIAMOND: "#5b8fd9",
  MASTER: "#b354d9",
  GRANDMASTER: "#d94f4f",
  CHALLENGER: "#f0e6d2",
};

const DAY_LABELS = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"];
const MATCHES_PAGE_SIZE = 10;

let championsChart = null;
let rolesChart = null;
let lpChart = null;
let goldChart = null;

let ddragonVersion = "16.15.1";
let currentAccountIndex = null;
let matchesOffset = 0;
let isLoadingMore = false;
let noMoreMatches = false;
let matchesObserver = null;

function championIconUrl(championName) {
  return `https://ddragon.leagueoflegends.com/cdn/${ddragonVersion}/img/champion/${championName}.png`;
}

async function fetchJSON(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Request failed: ${url} (${res.status})`);
  return res.json();
}

function renderTabs(accounts, activeIndex, onSelect) {
  const nav = document.getElementById("account-tabs");
  nav.innerHTML = "";
  accounts.forEach((acc) => {
    const btn = document.createElement("button");
    btn.className = "account-tab" + (acc.index === activeIndex ? " active" : "");
    btn.textContent = acc.label;
    btn.addEventListener("click", () => onSelect(acc.index));
    nav.appendChild(btn);
  });
}

function renderProfile(data) {
  document.getElementById("profile-icon").src = data.profile.profileIconUrl;
  document.getElementById("profile-name").textContent =
    `${data.account.gameName}#${data.account.tagLine}`;
  document.getElementById("profile-level").textContent =
    `Nivel ${data.profile.summonerLevel}`;

  const rankBadge = document.getElementById("rank-badge");
  const rank = data.profile.rank;
  if (rank) {
    rankBadge.textContent = `${rank.tier} ${rank.division} · ${rank.lp} LP`;
    rankBadge.style.borderColor = TIER_COLORS[rank.tier] || "#c89b3c";
    rankBadge.style.color = TIER_COLORS[rank.tier] || "#f0e6d2";
  } else {
    rankBadge.textContent = "Sin clasificar (Solo/Duo)";
    rankBadge.style.borderColor = "#c89b3c";
    rankBadge.style.color = "#f0e6d2";
  }
}

function renderStatCards(stats) {
  document.getElementById("stat-winrate").textContent = `${stats.winrate}%`;
  document.getElementById("stat-record").textContent = `${stats.wins}W / ${stats.losses}L`;
  document.getElementById("stat-kda").textContent =
    `${stats.avgKda.kills} / ${stats.avgKda.deaths} / ${stats.avgKda.assists}`;
  document.getElementById("stat-kda-ratio").textContent = stats.avgKda.ratio;
}

function renderTrend(trend) {
  const container = document.getElementById("trend");
  container.innerHTML = "";
  trend.forEach((result) => {
    const dot = document.createElement("div");
    dot.className = `trend-dot ${result === "W" ? "win" : "loss"}`;
    dot.textContent = result;
    container.appendChild(dot);
  });
}

function renderStreak(streak) {
  const badge = document.getElementById("streak-badge");
  if (!streak || !streak.type || streak.count < 3) {
    badge.classList.add("hidden");
    return;
  }
  badge.classList.remove("hidden");
  if (streak.type === "W") {
    badge.className = "streak-badge win-streak";
    badge.textContent = `🔥 Racha de ${streak.count} victorias`;
  } else {
    badge.className = "streak-badge loss-streak";
    badge.textContent = `⚠️ Racha de ${streak.count} derrotas`;
  }
}

function renderChampionsChart(topChampions) {
  const ctx = document.getElementById("champions-chart");
  const labels = topChampions.map((c) => c.name);
  const games = topChampions.map((c) => c.games);
  const winrates = topChampions.map((c) => c.winrate);

  if (championsChart) championsChart.destroy();
  championsChart = new Chart(ctx, {
    type: "bar",
    data: {
      labels,
      datasets: [{ label: "Partidas", data: games, backgroundColor: "#c89b3c", borderRadius: 4 }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: { afterLabel: (item) => `Winrate: ${winrates[item.dataIndex]}%` },
        },
      },
      scales: {
        x: { ticks: { color: "#8391a4" }, grid: { color: "#1e3a5f" } },
        y: { ticks: { color: "#8391a4", stepSize: 1 }, grid: { color: "#1e3a5f" } },
      },
    },
  });
}

function renderRolesChart(roles) {
  const ctx = document.getElementById("roles-chart");
  const labels = Object.keys(roles);
  const values = Object.values(roles);

  if (rolesChart) rolesChart.destroy();
  rolesChart = new Chart(ctx, {
    type: "doughnut",
    data: {
      labels,
      datasets: [
        {
          data: values,
          backgroundColor: ["#c89b3c", "#5b8fd9", "#2f9e57", "#d94f4f", "#b354d9", "#8391a4"],
          borderColor: "#0f2038",
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { position: "bottom", labels: { color: "#cdd6e0", boxWidth: 10, font: { size: 10 } } } },
    },
  });
}

function renderLpChart(rankHistory) {
  const hint = document.getElementById("lp-chart-hint");
  const ctx = document.getElementById("lp-chart");

  if (rankHistory.length < 2) {
    hint.textContent =
      "Riot no expone historial de LP: graficamos tu progreso desde ahora, partida a partida. Todavía hay pocos puntos.";
  } else {
    hint.textContent = "Progreso desde que empezamos a trackear (no incluye partidas previas a hoy).";
  }

  const labels = rankHistory.map((s) =>
    new Date(s.capturedAt).toLocaleDateString("es-AR", { day: "2-digit", month: "2-digit" })
  );
  const values = rankHistory.map((s) => s.value);

  if (lpChart) lpChart.destroy();
  lpChart = new Chart(ctx, {
    type: "line",
    data: {
      labels,
      datasets: [
        {
          label: "Rank",
          data: values,
          borderColor: "#c89b3c",
          backgroundColor: "rgba(200,155,60,0.15)",
          fill: true,
          tension: 0.25,
          pointRadius: 3,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: (item) => {
              const s = rankHistory[item.dataIndex];
              return `${s.tier} ${s.division} · ${s.lp} LP`;
            },
          },
        },
      },
      scales: {
        x: { ticks: { color: "#8391a4", font: { size: 10 } }, grid: { color: "#1e3a5f" } },
        y: { ticks: { color: "#8391a4", font: { size: 10 } }, grid: { color: "#1e3a5f" } },
      },
    },
  });
}

async function loadMastery(accountIndex) {
  const list = document.getElementById("mastery-list");
  list.innerHTML = '<div class="empty-state">Cargando...</div>';
  const mastery = await fetchJSON(`/api/accounts/${accountIndex}/mastery`);
  if (accountIndex !== currentAccountIndex) return;
  list.innerHTML =
    mastery
      .map(
        (m) => `
        <div class="mastery-card">
          <img src="${m.championIconUrl}" alt="${m.championName}" />
          <div class="mastery-info">
            <span class="mastery-champ">${m.championName}</span>
            <span class="mastery-meta">Nivel ${m.level} · ${m.points.toLocaleString()} pts</span>
          </div>
        </div>
      `
      )
      .join("") || '<div class="empty-state">Sin datos de maestría.</div>';
}

async function loadTeammates(accountIndex) {
  const list = document.getElementById("teammates-list");
  list.innerHTML = '<div class="empty-state">Cargando...</div>';
  const teammates = await fetchJSON(`/api/accounts/${accountIndex}/teammates`);
  if (accountIndex !== currentAccountIndex) return;
  if (teammates.length === 0) {
    list.innerHTML =
      '<div class="empty-state">Todavía no hay suficientes partidas cacheadas para detectar compañeros frecuentes. Se completa a medida que scrolleás la lista de partidas.</div>';
    return;
  }
  list.innerHTML = teammates
    .map(
      (t) => `
        <div class="teammate-row">
          <span class="teammate-name">${t.name}</span>
          <span class="teammate-stats">${t.games} partidas · ${t.winrate}% WR</span>
        </div>
      `
    )
    .join("");
}

async function loadActivity(accountIndex) {
  const container = document.getElementById("activity-heatmap");
  container.innerHTML = "";
  const activity = await fetchJSON(`/api/accounts/${accountIndex}/activity`);
  if (accountIndex !== currentAccountIndex) return;

  const counts = {};
  let max = 1;
  activity.forEach((a) => {
    counts[`${a.day}-${a.hour}`] = a.count;
    max = Math.max(max, a.count);
  });

  const cells = [];
  for (let day = 0; day < 7; day++) {
    cells.push(`<div class="heatmap-label">${DAY_LABELS[day]}</div>`);
    for (let hour = 0; hour < 24; hour++) {
      const count = counts[`${day}-${hour}`] || 0;
      const intensity = count ? 0.15 + 0.85 * (count / max) : 0.04;
      cells.push(
        `<div class="heatmap-cell" style="--intensity:${intensity}" title="${DAY_LABELS[day]} ${hour}h: ${count} partidas"></div>`
      );
    }
  }
  container.innerHTML = cells.join("");
}

async function checkLiveStatus() {
  if (currentAccountIndex === null) return;
  const banner = document.getElementById("live-banner");
  banner.classList.remove("hidden");
  banner.textContent = "Consultando...";

  const status = await fetchJSON(`/api/accounts/${currentAccountIndex}/live`);
  if (!status.inGame) {
    banner.textContent = "No estás en partida ahora mismo.";
    return;
  }

  const minutes = Math.floor(status.gameLengthSec / 60);
  const yourTeamId = status.participants.find((p) => p.isYou)?.teamId;
  const iconsHTML = status.participants
    .map(
      (p) =>
        `<img class="live-champ ${p.teamId === yourTeamId ? "" : "enemy"}" src="${p.championIconUrl}" title="${p.championName}" />`
    )
    .join("");
  banner.innerHTML = `<strong>¡Estás en partida! (${status.gameMode}, ${minutes} min)</strong> ${iconsHTML}`;
}

function matchRowHTML(match) {
  return `
    <div class="match-stripe ${match.win ? "win" : "loss"}"></div>
    <img class="match-champion-icon" src="${championIconUrl(match.champion)}" alt="${match.champion}" />
    <div class="match-champion">${match.champion}</div>
    <div class="match-role">${match.role} · Visión ${match.visionScore}</div>
    <div class="match-kda">${match.kills}/${match.deaths}/${match.assists}</div>
    <div class="match-cs">${match.cs} CS (${match.csPerMin}/min)</div>
    <div class="match-duration">${match.durationMin} min</div>
  `;
}

function appendMatches(accountIndex, matches) {
  const list = document.getElementById("matches-list");
  matches.forEach((match) => {
    const row = document.createElement("div");
    row.className = "match-row";
    row.innerHTML = matchRowHTML(match);
    row.addEventListener("click", () => openMatchModal(accountIndex, match.matchId));
    list.appendChild(row);
  });
}

async function loadMoreMatches() {
  if (isLoadingMore || noMoreMatches || currentAccountIndex === null) return;
  isLoadingMore = true;

  const accountIndex = currentAccountIndex;
  const matches = await fetchJSON(
    `/api/accounts/${accountIndex}/matches?offset=${matchesOffset}&limit=${MATCHES_PAGE_SIZE}`
  );

  if (accountIndex !== currentAccountIndex) return;

  if (matches.length === 0) {
    noMoreMatches = true;
    document.getElementById("matches-sentinel").textContent = "No hay más partidas Ranked Solo/Duo.";
  } else {
    if (matchesOffset === 0) document.getElementById("matches-list").innerHTML = "";
    appendMatches(accountIndex, matches);
    matchesOffset += matches.length;
    if (matches.length < MATCHES_PAGE_SIZE) {
      noMoreMatches = true;
      document.getElementById("matches-sentinel").textContent = "No hay más partidas Ranked Solo/Duo.";
    }
  }

  isLoadingMore = false;
}

function resetMatchesList() {
  matchesOffset = 0;
  noMoreMatches = false;
  isLoadingMore = false;
  document.getElementById("matches-list").innerHTML = '<div class="empty-state">Cargando partidas...</div>';
  document.getElementById("matches-sentinel").textContent = "Cargando más partidas...";
}

function setupInfiniteScroll() {
  if (matchesObserver) return;
  const sentinel = document.getElementById("matches-sentinel");
  matchesObserver = new IntersectionObserver(
    (entries) => {
      if (entries[0].isIntersecting) loadMoreMatches();
    },
    { rootMargin: "200px" }
  );
  matchesObserver.observe(sentinel);
}

function analysisStatHTML(value, label) {
  return `<div class="analysis-stat"><span class="value">${value}%</span><span class="label">${label}</span></div>`;
}

function runesBasicIconsHTML(runes) {
  if (!runes) return "";
  return `
    <img class="rune-icon" src="${runes.primaryStyle.icon}" title="${runes.primaryStyle.name}" />
    <img class="rune-icon" src="${runes.secondaryStyle.icon}" title="${runes.secondaryStyle.name}" />
  `;
}

function yourRunesFullHTML(runes) {
  if (!runes || !runes.primaryRunes) return "";
  const primaryRunesHTML = runes.primaryRunes
    .map((r) => `<img class="rune-icon" src="${r.icon}" title="${r.name}" />`)
    .join("");
  const secondaryRunesHTML = runes.secondaryRunes
    .map((r) => `<img class="rune-icon" src="${r.icon}" title="${r.name}" />`)
    .join("");
  return `
    <div class="your-runes-box">
      <h3>Tus runas</h3>
      <div class="rune-tree-row">
        <img class="rune-icon-lg" src="${runes.primaryStyle.icon}" title="${runes.primaryStyle.name}" />
        <span class="tree-name">${runes.primaryStyle.name}</span>
        ${primaryRunesHTML}
      </div>
      <div class="rune-tree-row">
        <img class="rune-icon-lg" src="${runes.secondaryStyle.icon}" title="${runes.secondaryStyle.name}" />
        <span class="tree-name">${runes.secondaryStyle.name}</span>
        ${secondaryRunesHTML}
      </div>
      <div class="stat-shards-row">
        <span>Ofensiva: ${runes.statShards.offense}</span>
        <span>Flex: ${runes.statShards.flex}</span>
        <span>Defensa: ${runes.statShards.defense}</span>
      </div>
    </div>
  `;
}

function teamTableHTML(team) {
  const rows = team.participants
    .map(
      (p) => `
        <tr class="${p.isYou ? "is-you" : ""}">
          <td><img class="match-champion-icon" style="width:20px;height:20px" src="${championIconUrl(p.championName)}" alt="${p.championName}" /></td>
          <td>${p.name}</td>
          <td>${p.role}</td>
          <td>${p.kills}/${p.deaths}/${p.assists}</td>
          <td>${p.cs}</td>
          <td>${p.goldEarned.toLocaleString()}</td>
          <td>${p.damageDealt.toLocaleString()}</td>
          <td>${p.visionScore}</td>
          <td class="runes-basic">${runesBasicIconsHTML(p.runes)}</td>
        </tr>
      `
    )
    .join("");

  const obj = team.objectives;
  const objText = Object.entries(obj)
    .map(([name, kills]) => `${name}: ${kills}`)
    .join(" · ");

  return `
    <div class="team-header ${team.win ? "team-win" : "team-loss"}">
      <span>${team.win ? "Equipo ganador" : "Equipo perdedor"}</span>
      <span>${team.totalKills} kills · ${team.totalGold.toLocaleString()} oro</span>
    </div>
    <div class="objectives">${objText}</div>
    <table class="team-table">
      <thead>
        <tr><th></th><th>Jugador</th><th>Rol</th><th>KDA</th><th>CS</th><th>Oro</th><th>Daño</th><th>Visión</th><th>Runas</th></tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>
  `;
}

function vsAverageHTML(detail, youParticipant) {
  const avg = detail.analysis.vsYourAverage;
  if (!avg) {
    return '<p class="lp-chart-hint">Todavía no hay suficientes partidas cacheadas con este campeón para comparar contra tu propio promedio.</p>';
  }
  const csPerMin = (youParticipant.cs / detail.durationMin).toFixed(1);
  const yourKda = ((youParticipant.kills + youParticipant.assists) / Math.max(youParticipant.deaths, 1)).toFixed(2);
  return `
    <div class="vs-average-box">
      <div><span class="value">${yourKda}</span>KDA (vs ${avg.avgKda} tuyo, ${avg.gamesSampled} partidas)</div>
      <div><span class="value">${youParticipant.damageDealt.toLocaleString()}</span>Daño (vs ${avg.avgDamage.toLocaleString()})</div>
      <div><span class="value">${youParticipant.goldEarned.toLocaleString()}</span>Oro (vs ${avg.avgGold.toLocaleString()})</div>
      <div><span class="value">${csPerMin}</span>CS/min (vs ${avg.avgCsPerMin})</div>
    </div>
  `;
}

function renderGoldChart(goldDiffTimeline) {
  const ctx = document.getElementById("gold-diff-chart");
  const labels = goldDiffTimeline.map((p) => `${p.minute}m`);
  const values = goldDiffTimeline.map((p) => p.diff);

  if (goldChart) goldChart.destroy();
  goldChart = new Chart(ctx, {
    type: "line",
    data: {
      labels,
      datasets: [
        {
          label: "Diferencia de oro (vos - rival)",
          data: values,
          borderColor: values[values.length - 1] >= 0 ? "#2f9e57" : "#c74e4e",
          backgroundColor: "rgba(200,155,60,0.1)",
          fill: true,
          tension: 0.2,
          pointRadius: 0,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        x: { ticks: { color: "#8391a4" }, grid: { color: "#1e3a5f" } },
        y: { ticks: { color: "#8391a4" }, grid: { color: "#1e3a5f" } },
      },
    },
  });
}

function showModal() {
  document.getElementById("modal").classList.remove("hidden");
}

function closeModal() {
  document.getElementById("modal").classList.add("hidden");
}

async function openMatchModal(accountIndex, matchId) {
  const content = document.getElementById("modal-content");
  content.innerHTML = '<div class="empty-state">Cargando partida...</div>';
  showModal();

  const detail = await fetchJSON(`/api/accounts/${accountIndex}/matches/${matchId}`);
  const yourTeam = detail.teams.find((t) => t.participants.some((p) => p.isYou));
  const enemyTeam = detail.teams.find((t) => t !== yourTeam);
  const you = yourTeam.participants.find((p) => p.isYou);
  const mvp = detail.analysis.gameMvp;

  content.innerHTML = `
    <div class="modal-header">
      <h2>${detail.win ? "Victoria" : "Derrota"} · ${detail.durationMin} min</h2>
    </div>
    <div class="modal-summary">${detail.analysis.summary} · ${new Date(detail.date).toLocaleString("es-AR")}</div>
    <div class="mvp-badge">🏆 MVP de la partida: ${mvp.championName} (${mvp.name})</div>
    <div class="analysis-row">
      ${analysisStatHTML(detail.analysis.killParticipation, "Participación en kills")}
      ${analysisStatHTML(detail.analysis.damageShare, "% daño del equipo")}
      ${analysisStatHTML(detail.analysis.goldShare, "% oro del equipo")}
    </div>
    ${vsAverageHTML(detail, you)}
    <ul class="tips-list">${detail.analysis.improvementTips.map((t) => `<li>${t}</li>`).join("")}</ul>
    ${yourRunesFullHTML(you.runes)}
    ${teamTableHTML(yourTeam)}
    ${teamTableHTML(enemyTeam)}
    <div class="gold-chart-box">
      <h3>Diferencia de oro durante la partida</h3>
      <div class="chart-canvas-wrap"><canvas id="gold-diff-chart"></canvas></div>
    </div>
  `;

  renderGoldChart(detail.goldDiffTimeline);
}

function compareTableHTML(dashboards) {
  const rows = [
    ["Rango", (d) => (d.profile.rank ? `${d.profile.rank.tier} ${d.profile.rank.division} (${d.profile.rank.lp} LP)` : "Sin clasificar")],
    ["Winrate", (d) => `${d.stats.winrate}%`],
    ["Récord", (d) => `${d.stats.wins}W / ${d.stats.losses}L`],
    ["KDA promedio", (d) => `${d.stats.avgKda.kills}/${d.stats.avgKda.deaths}/${d.stats.avgKda.assists}`],
    ["Ratio K+A/D", (d) => d.stats.avgKda.ratio],
  ];
  const bodyRows = rows
    .map(
      ([label, fn]) =>
        `<tr><td>${label}</td>${dashboards.map((d) => `<td class="highlight">${fn(d)}</td>`).join("")}</tr>`
    )
    .join("");

  const champSets = dashboards.map((d) => new Set(d.stats.topChampions.map((c) => c.name)));
  const shared = [...champSets[0]].filter((name) => champSets.every((s) => s.has(name)));
  const sharedHTML = shared.length
    ? `<h3 style="font-size:13px;color:var(--gold-light);margin:16px 0 8px;">Campeones en común</h3><p>${shared.join(", ")}</p>`
    : `<p class="lp-chart-hint" style="margin-top:16px;">No hay campeones en el top de ambas cuentas todavía.</p>`;

  return `
    <div class="modal-header"><h2>Comparativa entre cuentas</h2></div>
    <table class="compare-table">
      <thead><tr><th>Métrica</th>${dashboards.map((d) => `<th>${d.account.label}</th>`).join("")}</tr></thead>
      <tbody>${bodyRows}</tbody>
    </table>
    ${sharedHTML}
  `;
}

async function openCompareModal() {
  const content = document.getElementById("modal-content");
  content.innerHTML = '<div class="empty-state">Cargando comparativa...</div>';
  showModal();

  const accounts = await fetchJSON("/api/accounts");
  const dashboards = await Promise.all(accounts.map((a) => fetchJSON(`/api/accounts/${a.index}/dashboard`)));
  content.innerHTML = compareTableHTML(dashboards);
}

async function loadDashboard(index) {
  const app = document.getElementById("app");
  app.classList.remove("loaded");

  currentAccountIndex = index;
  document.getElementById("live-banner").classList.add("hidden");

  const data = await fetchJSON(`/api/accounts/${index}/dashboard`);
  if (index !== currentAccountIndex) return;
  ddragonVersion = data.ddragonVersion;

  renderProfile(data);
  renderStatCards(data.stats);
  renderTrend(data.stats.trend);
  renderStreak(data.stats.streak);
  renderChampionsChart(data.stats.topChampions);
  renderRolesChart(data.stats.roles);
  renderLpChart(data.rankHistory);

  loadMastery(index);
  loadTeammates(index);
  loadActivity(index);

  resetMatchesList();
  setupInfiniteScroll();
  await loadMoreMatches();

  requestAnimationFrame(() => app.classList.add("loaded"));
}

async function init() {
  const accounts = await fetchJSON("/api/accounts");
  let activeIndex = accounts[0].index;

  const selectAccount = (index) => {
    activeIndex = index;
    renderTabs(accounts, activeIndex, selectAccount);
    loadDashboard(index);
  };

  renderTabs(accounts, activeIndex, selectAccount);

  document.getElementById("modal-close").addEventListener("click", closeModal);
  document.getElementById("modal").addEventListener("click", (e) => {
    if (e.target.id === "modal") closeModal();
  });
  document.getElementById("live-btn").addEventListener("click", checkLiveStatus);
  document.getElementById("compare-btn").addEventListener("click", openCompareModal);
  document.getElementById("refresh-btn").addEventListener("click", async () => {
    const btn = document.getElementById("refresh-btn");
    btn.disabled = true;
    btn.textContent = "Actualizando...";
    await loadDashboard(currentAccountIndex);
    btn.disabled = false;
    btn.textContent = "↻ Actualizar";
  });

  await loadDashboard(activeIndex);
}

init().catch((err) => {
  console.error(err);
  document.getElementById("app").innerHTML =
    `<div class="empty-state">Error cargando datos: ${err.message}</div>`;
});
