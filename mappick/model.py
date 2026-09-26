"""Modelo objetivo de escolha de mapa.

FORMULA (nenhum passo e manual; tudo sai do historico)
======================================================

1. ALVO CONTINUO  q_i  em [0,1]
   Vitoria/derrota pura e ruidosa demais em amostra pequena, entao cada partida
   vira uma nota continua:
       q_i           = Lo * outcome_i + Lr * round_share_i
       outcome_i     = 1 (W) | 0.5 (D) | 0 (L)
       round_share_i = RW / (RW + RL)
   Assim 13x11 perdido informa diferente de 13x3 perdido.

2. PESO DE CADA PARTIDA  w_i = w_tempo * w_roster
   a) Tempo (meia-vida H):      w_tempo  = 2 ** (-idade_dias / H)
   b) Roster (o ponto central): Jaccard suavizado entre o roster historico R_i
      e o roster alvo T (quem esta no lobby agora), considerando so os colegas
      (eu estou sempre presente):
          J_i      = |R_i inter T| / |R_i uniao T|      (vazio vs vazio = 1)
          w_roster = floor + (1 - floor) * J_i ** gamma
      floor > 0 faz partidas com outro roster ainda informarem a base do mapa.
      E isto que resolve "eu+X", "eu+X+Y", "so eu+Y": cada alvo T produz um
      conjunto de pesos diferente, automaticamente, sem regra escrita a mao.

3. AMOSTRA EFETIVA (Kish)   n_eff = (soma w)**2 / soma (w**2)
   40 partidas velhas com roster errado podem valer n_eff = 5. E isto que
   impede o modelo de confiar em 2 vitorias no Nuke.

4. ESTIMATIVA HIERARQUICA COM ENCOLHIMENTO (empirical Bayes)
       L0 prior  = 0.5
       L1 theta1 = minha base geral (todos os mapas / rosters, com decaimento)
       L2 theta2 = eu no mapa m (todos os rosters)
       L3 theta3 = eu no mapa m com peso de similaridade de roster
   Cada nivel encolhe para o pai com k pseudo-partidas:
       est = (n_eff * S + k * pai) / (n_eff + k)

5. FORMA INDIVIDUAL (KD, ADR, KAST, rating)
   Para cada jogador do lobby, indice composto I_p por partida, normalizado
   contra a PROPRIA linha de base do jogador (z-score) - assim fragger e
   support sao comparaveis. z_{p,m} = quanto o jogador rende acima/abaixo do
   seu normal naquele mapa, encolhido para 0 conforme a amostra.
   Agregacao do time: Z_m = media dos z ponderada pelo n_eff de cada jogador.

6. COMBINACAO FINAL, em logit:
       logit(P_m) = logit(theta3_m) + beta * Z_m
       P_m = sigmoide(...)   -> % esperada de vitoria naquele mapa com o lobby.

7. CONFIANCA: se = sqrt(P(1-P)/n_eff); IC = P +- z*se;
   score conservador P_low = P - z*se serve de desempate.
"""
import math
from datetime import datetime, timezone

EPS = 1e-9


# ---------------------------------------------------------------- utilidades
def _parse_dt(s):
    if isinstance(s, datetime):
        return s if s.tzinfo else s.replace(tzinfo=timezone.utc)
    s = str(s).replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        dt = datetime.strptime(s[:19], "%Y-%m-%dT%H:%M:%S")
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def logit(p):
    p = min(max(p, 1e-6), 1 - 1e-6)
    return math.log(p / (1 - p))


def sigmoid(x):
    if x >= 0:
        return 1 / (1 + math.exp(-x))
    e = math.exp(x)
    return e / (1 + e)


def kish(weights):
    """Tamanho efetivo de amostra: (soma w)**2 / soma(w**2)."""
    s1 = sum(weights)
    s2 = sum(w * w for w in weights)
    return (s1 * s1 / s2) if s2 > EPS else 0.0


def shrink(sample_mean, n_eff, prior, k):
    """Encolhimento bayesiano com k pseudo-partidas de prior."""
    if n_eff <= EPS:
        return prior
    return (n_eff * sample_mean + k * prior) / (n_eff + k)


def wmean(pairs):
    """pairs: iteravel de (valor, peso)."""
    num = den = 0.0
    for v, w in pairs:
        if v is None or w is None:
            continue
        num += v * w
        den += w
    return (num / den) if den > EPS else None


# ------------------------------------------------------------------- modelo
class MapPicker:
    def __init__(self, matches, me, config):
        self.me = str(me)
        self.cfg = config["model"]
        self.perf_w = config.get("perf_weights", {})
        self.map_pool = config.get("map_pool") or []
        self.map_resets = {k: _parse_dt(v) for k, v in (config.get("map_resets") or {}).items()}
        self.now = datetime.now(timezone.utc)
        self.matches = self._prepare(matches)
        self._player_baselines = {}

    # -- preparo -----------------------------------------------------------
    def _prepare(self, matches):
        out = self._raw_rows(matches)
        # CALIBRACAO: q e uma nota, nao uma probabilidade. Reescalamos q para a
        # escala de vitoria usando as proprias medias empiricas de q nas
        # vitorias (Q1) e nas derrotas (Q0):  q' = (q - Q0) / (Q1 - Q0).
        # Assim E[q'] = P(vitoria) e o prior 0.5 do encolhimento fica correto,
        # enquanto a margem de rounds continua separando 13x3 de 13x11.
        wins = [(r["q"], r["w_time"]) for r in out if r["outcome"] == 1.0]
        loss = [(r["q"], r["w_time"]) for r in out if r["outcome"] == 0.0]
        q1 = wmean(wins)
        q0 = wmean(loss)
        if q1 is None or q0 is None or (q1 - q0) < 0.05:
            q1, q0 = 1.0, 0.0  # sem amostra dos dois lados: nao recalibra
        self.calib = (q0, q1)
        for r in out:
            r["q"] = min(max((r["q"] - q0) / (q1 - q0), -0.2), 1.2)
        return out

    def _raw_rows(self, matches):
        out = []
        max_age = self.cfg.get("max_age_days", 540)
        for m in matches:
            dt = _parse_dt(m["played_at"])
            age = (self.now - dt).total_seconds() / 86400.0
            if age < 0:
                age = 0.0
            if max_age and age > max_age:
                continue
            reset = self.map_resets.get(m["map"])
            if reset and dt < reset:
                continue  # mapa reformulado: historico anterior nao vale
            rw, rl = int(m["rounds_won"]), int(m["rounds_lost"])
            total = rw + rl
            res = (m.get("result") or "").upper()
            outcome = 1.0 if res == "W" else (0.0 if res == "L" else 0.5)
            round_share = (rw / total) if total > 0 else outcome
            q = (self.cfg["outcome_weight"] * outcome +
                 self.cfg["round_share_weight"] * round_share)
            mates = {str(p) for p in m["roster"]} - {self.me}
            out.append({**m, "dt": dt, "age": age, "q": q, "outcome": outcome,
                        "round_share": round_share, "mates": mates,
                        "w_time": 2 ** (-age / self.cfg["half_life_days"])})
        return out

    # -- pesos -------------------------------------------------------------
    def _roster_weight(self, mates, target):
        floor = self.cfg["roster_floor"]
        gamma = self.cfg["roster_sharpness"]
        if not mates and not target:
            j = 1.0
        else:
            union = mates | target
            j = (len(mates & target) / len(union)) if union else 1.0
        return floor + (1.0 - floor) * (j ** gamma)

    # -- linha de base de performance de cada jogador ----------------------
    def _perf_index(self, ps):
        """Indice composto bruto de uma partida, com os campos disponiveis."""
        parts, wsum = 0.0, 0.0
        w = self.perf_w
        k, d = ps.get("kills"), ps.get("deaths")
        if k is not None and d is not None:
            kd = k / max(d, 1)
            parts += w.get("kd", 0) * min(kd, 3.0) / 3.0
            wsum += w.get("kd", 0)
        if ps.get("adr") is not None:
            parts += w.get("adr", 0) * min(ps["adr"], 150.0) / 150.0
            wsum += w.get("adr", 0)
        if ps.get("kast") is not None:
            kast = ps["kast"] / 100.0 if ps["kast"] > 1.5 else ps["kast"]
            parts += w.get("kast", 0) * min(kast, 1.0)
            wsum += w.get("kast", 0)
        if ps.get("rating") is not None:
            parts += w.get("rating", 0) * min(ps["rating"], 2.0) / 2.0
            wsum += w.get("rating", 0)
        return (parts / wsum) if wsum > EPS else None

    def _baseline(self, steam64):
        """(media, desvio) do indice do jogador em TODOS os mapas, com decaimento."""
        if steam64 in self._player_baselines:
            return self._player_baselines[steam64]
        vals = []
        for m in self.matches:
            ps = m["players"].get(steam64)
            if not ps:
                continue
            idx = self._perf_index(ps)
            if idx is not None:
                vals.append((idx, m["w_time"]))
        mu = wmean(vals)
        if mu is None:
            res = (None, None)
        else:
            den = sum(w for _, w in vals)
            var = sum(w * (v - mu) ** 2 for v, w in vals) / den if den > EPS else 0.0
            res = (mu, max(math.sqrt(var), 0.02))
        self._player_baselines[steam64] = res
        return res

    def _form_z(self, steam64, map_name):
        """z-score do jogador NAQUELE mapa vs a propria media, encolhido por amostra."""
        mu, sd = self._baseline(steam64)
        if mu is None:
            return 0.0, 0.0
        vals = []
        for m in self.matches:
            if m["map"] != map_name:
                continue
            ps = m["players"].get(steam64)
            if not ps:
                continue
            idx = self._perf_index(ps)
            if idx is not None:
                vals.append((idx, m["w_time"]))
        if not vals:
            return 0.0, 0.0
        mm = wmean(vals)
        n_eff = kish([w for _, w in vals])
        z = (mm - mu) / sd
        k = self.cfg.get("form_shrink", 6)
        return z * (n_eff / (n_eff + k)), n_eff

    # -- niveis hierarquicos -----------------------------------------------
    def _level_global(self):
        ws = [m["w_time"] for m in self.matches]
        if not ws:
            return 0.5, 0.0
        s = wmean([(m["q"], m["w_time"]) for m in self.matches]) or 0.5
        n = kish(ws)
        return shrink(s, n, 0.5, self.cfg["shrink_global"]), n

    def _level_map(self, map_name, theta_global):
        sel = [m for m in self.matches if m["map"] == map_name]
        if not sel:
            return theta_global, 0.0
        s = wmean([(m["q"], m["w_time"]) for m in sel]) or theta_global
        n = kish([m["w_time"] for m in sel])
        return shrink(s, n, theta_global, self.cfg["shrink_map"]), n

    def _level_roster(self, map_name, target, theta_map):
        sel = [m for m in self.matches if m["map"] == map_name]
        if not sel:
            return theta_map, 0.0, []
        scored = [(m, m["w_time"] * self._roster_weight(m["mates"], target)) for m in sel]
        s = wmean([(m["q"], w) for m, w in scored]) or theta_map
        n = kish([w for _, w in scored])
        return shrink(s, n, theta_map, self.cfg["shrink_roster"]), n, scored

    # -- pool de mapas ------------------------------------------------------
    def _active_maps(self):
        """Quais mapas entram no ranking.

        `map_pool: "auto"` (padrao) deriva o pool ativo do proprio historico:
        mapas efetivamente jogados na janela recente, no modo competitivo. Isso
        evita duas coisas chatas - listar mapa que saiu do pool (Cache, Vertigo)
        e precisar editar o config toda vez que a Valve mexe na rotacao.
        Uma lista explicita em `map_pool` passa a valer como FILTRO.
        """
        modes_ok = {"premier", "competitive", "comp", None, ""}
        if isinstance(self.map_pool, list) and self.map_pool:
            allowed = set(self.map_pool)
            seen = [m["map"] for m in self.matches]
            return [mp for mp in dict.fromkeys(list(self.map_pool) + seen) if mp in allowed]

        window = self.cfg.get("pool_window_days", 120)
        recent, fallback = {}, {}
        for m in self.matches:
            mode = (m.get("mode") or "").lower()
            if mode and mode not in modes_ok:
                continue  # wingman, casual, deathmatch nao entram
            fallback[m["map"]] = fallback.get(m["map"], 0) + 1
            if m["age"] <= window:
                recent[m["map"]] = recent.get(m["map"], 0) + 1
        pool = recent or fallback
        return sorted(pool, key=lambda mp: -pool[mp])

    # -- API principal ------------------------------------------------------
    def rank(self, target_mates):
        target = {str(p) for p in target_mates} - {self.me}
        lobby = sorted(target | {self.me})
        theta_g, n_g = self._level_global()

        maps = self._active_maps()
        results = []
        for mp in maps:
            theta_m, n_m = self._level_map(mp, theta_g)
            theta_r, n_r, _scored = self._level_roster(mp, target, theta_m)

            zs = []
            for p in lobby:
                z, n = self._form_z(p, mp)
                zs.append((p, z, n))
            den = sum(n for _, _, n in zs)
            Z = (sum(z * n for _, z, n in zs) / den) if den > EPS else 0.0

            p_win = sigmoid(logit(theta_r) + self.cfg["form_beta"] * Z)

            # amostra bruta com o roster exato (so para exibir, nao entra na conta)
            exact = [m for m in self.matches if m["map"] == mp and m["mates"] == target]
            w_ex = sum(1 for m in exact if m["outcome"] == 1.0)
            l_ex = sum(1 for m in exact if m["outcome"] == 0.0)

            zc = self.cfg.get("confidence_z", 1.645)
            se = math.sqrt(max(p_win * (1 - p_win), 1e-6) / n_r) if n_r > EPS else 0.5
            results.append({
                "map": mp,
                "p_win": p_win,
                "p_low": max(0.0, p_win - zc * se),
                "p_high": min(1.0, p_win + zc * se),
                "n_eff": n_r,
                "n_eff_map": n_m,
                "games_total": len([m for m in self.matches if m["map"] == mp]),
                "exact_w": w_ex, "exact_l": l_ex, "exact_n": len(exact),
                "confidence": self._confidence_label(n_r),
                "breakdown": {
                    "base_global": theta_g,
                    "map_level": theta_m,
                    "roster_level": theta_r,
                    "form_Z": Z,
                    "form_delta_pp": (p_win - theta_r) * 100,
                },
                "drivers": sorted(
                    [{"steam64": p, "z": z, "n_eff": n} for p, z, n in zs if n > 0.5],
                    key=lambda d: -abs(d["z"]))[:5],
            })

        results.sort(key=lambda r: (-r["p_win"], -r["n_eff"]))
        for i, r in enumerate(results, 1):
            r["rank"] = i
        return {
            "lobby": lobby, "me": self.me,
            "global_baseline": theta_g, "n_eff_global": n_g,
            "total_matches": len(self.matches),
            "generated_at": self.now.isoformat(),
            "maps": results,
        }

    @staticmethod
    def _confidence_label(n_eff):
        if n_eff < 3:
            return "sem dados"
        if n_eff < 8:
            return "baixa"
        if n_eff < 20:
            return "media"
        return "alta"
