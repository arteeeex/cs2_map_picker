const $ = (s) => document.querySelector(s);
const state = {
  players: [], selected: new Set(), names: {}, open: null,
  conservative: false, showAll: false, query: "",
};

// Em Premier solo a maioria dos "colegas" e random de uma partida so.
// Por padrao mostramos quem foi fixado como time, quem esta selecionado,
// e quem tem historico suficiente para o modelo ter o que dizer.
const MIN_GAMES = 3;

function visiblePlayers() {
  const q = state.query.trim().toLowerCase();
  let list = state.players;
  if (q) {
    list = list.filter((p) =>
      (p.name || "").toLowerCase().includes(q) || String(p.steam64).includes(q));
    return list.slice(0, 60);
  }
  if (state.showAll) return list;
  return list.filter((p) =>
    p.is_friend || state.selected.has(String(p.steam64)) || p.games >= MIN_GAMES);
}

const prettyMap = (m) => m.replace(/^de_/, "").replace(/^cs_/, "")
  .replace(/\b\w/, (c) => c.toUpperCase());

function colorFor(p) {
  // vermelho -> amarelo -> verde, ancorado em 50%
  const t = Math.max(0, Math.min(1, (p - 0.35) / 0.35));
  const stops = [[229, 83, 75], [217, 164, 65], [63, 185, 80]];
  const i = t < 0.5 ? 0 : 1;
  const k = t < 0.5 ? t * 2 : (t - 0.5) * 2;
  const c = stops[i].map((v, j) => Math.round(v + (stops[i + 1][j] - v) * k));
  return `rgb(${c.join(",")})`;
}

async function loadState() {
  const r = await fetch("/api/state").then((x) => x.json());
  state.players = r.players || [];
  if (!r.configured) {
    $("#status").textContent = "não configurado";
    $("#ranking").innerHTML = `<div class="warn">
      Falta configurar. Preencha <code>me</code> no <code>config.json</code> com o seu
      Steam64 e importe o histórico — ou rode <code>python mappick.py seed</code>
      para ver o sistema funcionando com dados de exemplo.</div>`;
    renderMates();
    return;
  }
  $("#status").innerHTML =
    `<b>${r.total_matches}</b> partidas · <b>${state.players.length}</b> colegas conhecidos`;
  renderMates();
  rank();
}

function renderMates() {
  const box = $("#mates");
  if (!state.players.length) {
    box.innerHTML = `<span class="empty">nenhum colega no histórico ainda —
      rode <code>python mappick.py sync</code></span>`;
    $("#showall").hidden = true;
    return;
  }
  const list = visiblePlayers();
  box.innerHTML = "";
  if (!list.length) {
    box.innerHTML = `<span class="empty">nenhum colega encontrado</span>`;
  }
  for (const p of list) {
    const id = String(p.steam64);
    const on = state.selected.has(id);
    const el = document.createElement("label");
    el.className = "mate" + (on ? " on" : "") + (p.is_friend ? " fixed" : "");
    el.title = p.is_friend ? "time fixo (botão direito para soltar)"
                           : "botão direito para fixar como time";
    el.innerHTML = `<input type="checkbox" ${on ? "checked" : ""}>
      <span class="n">${p.is_friend ? "★ " : ""}${p.name || id}</span>
      <span class="g">${p.games}j</span>`;

    el.querySelector("input").addEventListener("change", (e) => {
      e.target.checked ? state.selected.add(id) : state.selected.delete(id);
      el.classList.toggle("on", e.target.checked);
      rank();
    });
    el.addEventListener("contextmenu", async (e) => {
      e.preventDefault();
      p.is_friend = p.is_friend ? 0 : 1;
      await fetch("/api/friend", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ steam64: id, is_friend: !!p.is_friend }),
      });
      state.players.sort((a, b) => (b.is_friend - a.is_friend) || (b.games - a.games));
      renderMates();
    });
    box.appendChild(el);
  }

  const hidden = state.players.length - list.length;
  const btn = $("#showall");
  if (state.query.trim()) {
    btn.hidden = true;
  } else if (state.showAll) {
    btn.hidden = false;
    btn.textContent = `mostrar só o time (esconder ${
      state.players.filter((p) => !p.is_friend && p.games < MIN_GAMES).length} avulsos)`;
  } else if (hidden > 0) {
    btn.hidden = false;
    btn.textContent = `mostrar todos (+${hidden} com menos de ${MIN_GAMES} partidas)`;
  } else {
    btn.hidden = true;
  }
}

// Marcar dois colegas em sequencia dispara dois /api/rank quase juntos. Sem
// isto, a resposta do PRIMEIRO pode chegar por ultimo e sobrescrever a do
// lobby atual - a tela fica mostrando o ranking de um time que nao e o marcado.
let rankSeq = 0;

async function rank() {
  const seq = ++rankSeq;
  const mates = [...state.selected].join(",");
  let r;
  try {
    r = await fetch("/api/rank?mates=" + encodeURIComponent(mates)).then((x) => x.json());
  } catch (e) {
    if (seq === rankSeq) $("#ranking").innerHTML =
      `<div class="warn">servidor fora do ar — rode <code>python mappick.py web</code></div>`;
    return;
  }
  if (seq !== rankSeq) return;          // resposta obsoleta: descarta
  if (r.error) {
    $("#ranking").innerHTML = `<div class="warn">${r.error}</div>`;
    return;
  }
  state.names = r.names || {};
  renderRanking(r);
}

function renderRanking(r) {
  const box = $("#ranking");
  box.innerHTML = "";
  const maps = [...r.maps];
  if (state.conservative) {
    maps.sort((a, b) => b.p_low - a.p_low);
    maps.forEach((m, i) => (m.rank = i + 1));
  }

  for (const m of maps) {
    const row = document.createElement("div");
    const isOpen = state.open === m.map;
    row.className = "row" + (isOpen ? " open" : "");
    const pct = (m.p_win * 100).toFixed(1);
    const conf = { alta: "c-alta", media: "c-media", baixa: "c-baixa" }[m.confidence] || "c-nenhum";
    const ciL = m.p_low * 100, ciW = (m.p_high - m.p_low) * 100;

    row.innerHTML = `
      <div class="pos">${m.rank}</div>
      <div class="map">${prettyMap(m.map)}</div>
      <div class="bar">
        <div class="fill" style="width:${pct}%;background:${colorFor(m.p_win)};opacity:.85"></div>
        <div class="ci" style="left:${ciL}%;width:${ciW}%"></div>
        <div class="mid"></div>
      </div>
      <div class="pct" style="color:${colorFor(m.p_win)}">${pct}%</div>
      <div class="meta">
        <span class="conf ${conf}">${m.confidence}</span>
        <span class="n">n_ef ${m.n_eff.toFixed(1)} · ${m.games_total}j</span>
      </div>`;

    if (isOpen) row.appendChild(detailEl(m, r));
    row.addEventListener("click", (e) => {
      if (e.target.closest(".detail")) return;
      state.open = isOpen ? null : m.map;
      renderRanking(r);
    });
    box.appendChild(row);
  }
}

function detailEl(m, r) {
  const d = document.createElement("div");
  d.className = "detail";
  const b = m.breakdown;
  const pp = (x) => (x * 100).toFixed(1) + "%";

  const drivers = m.drivers.length
    ? m.drivers.map((x) => {
        const nm = state.names[x.steam64] || x.steam64.slice(-5);
        const cls = x.z >= 0 ? "pos-z" : "neg-z";
        return `<div class="kv ${cls}"><span>${nm}</span><b>${x.z >= 0 ? "+" : ""}${x.z.toFixed(2)}σ</b></div>`;
      }).join("")
    : `<div class="kv"><span>sem dados de performance</span></div>`;

  d.innerHTML = `
    <div>
      <h4>como chegou nesse número</h4>
      <div class="kv"><span>sua base geral</span><b>${pp(b.base_global)}</b></div>
      <div class="kv"><span>+ esse mapa</span><b>${pp(b.map_level)}</b></div>
      <div class="kv"><span>+ esse time</span><b>${pp(b.roster_level)}</b></div>
      <div class="kv"><span>+ forma no mapa</span><b>${b.form_delta_pp >= 0 ? "+" : ""}${b.form_delta_pp.toFixed(1)} pp</b></div>
      <div class="kv"><span>= previsão</span><b>${pp(m.p_win)}</b></div>
    </div>
    <div>
      <h4>quem puxa o mapa (KD/ADR/KAST)</h4>
      ${drivers}
    </div>
    <div>
      <h4>amostra</h4>
      <div class="kv"><span>intervalo 90%</span><b>${pp(m.p_low)} – ${pp(m.p_high)}</b></div>
      <div class="kv"><span>amostra efetiva</span><b>${m.n_eff.toFixed(1)}</b></div>
      <div class="kv"><span>partidas no mapa</span><b>${m.games_total}</b></div>
      <div class="kv"><span>com esse time exato</span><b>${m.exact_w}V ${m.exact_l}D</b></div>
    </div>
    <div>
      <h4>leitura</h4>
      <div class="note">${reading(m)}</div>
    </div>`;
  return d;
}

function reading(m) {
  const parts = [];
  if (m.confidence === "sem dados")
    parts.push("Quase sem histórico com esse time aqui — o número é praticamente a sua média geral.");
  else if (m.confidence === "baixa")
    parts.push("Amostra fina. O intervalo é largo, trate como palpite.");
  else if (m.confidence === "alta")
    parts.push("Amostra sólida para esse time.");
  else parts.push("Amostra razoável.");

  const diff = (m.breakdown.roster_level - m.breakdown.map_level) * 100;
  if (Math.abs(diff) >= 2.5)
    parts.push(`Esse time específico rende <b>${diff > 0 ? "+" : ""}${diff.toFixed(1)} pp</b> aqui em relação ao seu mapa médio.`);
  if (Math.abs(m.breakdown.form_delta_pp) >= 1.5)
    parts.push(`As estatísticas individuais ${m.breakdown.form_delta_pp > 0 ? "ajudam" : "atrapalham"} (${m.breakdown.form_delta_pp.toFixed(1)} pp).`);
  return parts.join(" ");
}

$("#clear").addEventListener("click", () => { state.selected.clear(); renderMates(); rank(); });
$("#conservative").addEventListener("change", (e) => { state.conservative = e.target.checked; rank(); });
$("#showall").addEventListener("click", () => { state.showAll = !state.showAll; renderMates(); });
$("#search").addEventListener("input", (e) => { state.query = e.target.value; renderMates(); });
loadState();
