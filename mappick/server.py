"""Servidor local: serve a pagina e a API de ranking. Stdlib pura."""
import json
import os
import urllib.parse
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

from . import store
from .model import MapPicker

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB = os.path.join(ROOT, "web")
CONFIG = os.path.join(ROOT, "config.json")


def load_config():
    with open(CONFIG, encoding="utf-8") as f:
        return json.load(f)


def save_config(cfg):
    with open(CONFIG, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=WEB, **kw)

    def log_message(self, fmt, *args):
        pass  # silencio

    def end_headers(self):
        # servidor local de desenvolvimento: nunca cachear, senao uma edicao no
        # app.js/style.css nao aparece e voce depura um bug que ja foi corrigido
        if not self.path.startswith("/api/"):
            self.send_header("Cache-Control", "no-store, must-revalidate")
        super().end_headers()

    # ---------------------------------------------------------------- utils
    def _json(self, payload, code=200):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        # o coletor roda no navegador, na origem csstats.gg, e entrega aqui
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        # O coletor roda numa pagina HTTPS (csstats.gg) e fala com 127.0.0.1.
        # O Chrome trata isso como Private Network Access e exige este header
        # no preflight, senao o fetch morre com "Failed to fetch".
        self.send_header("Access-Control-Allow-Private-Network", "true")
        self.send_header("Access-Control-Max-Age", "86400")
        self.end_headers()

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        if not n:
            return {}
        try:
            return json.loads(self.rfile.read(n).decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return {}

    # ------------------------------------------------------------------ GET
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if not parsed.path.startswith("/api/"):
            return super().do_GET()
        qs = urllib.parse.parse_qs(parsed.query)
        cfg = load_config()
        me = cfg.get("me") or ""

        if parsed.path == "/api/state":
            conn = store.connect()
            try:
                total = conn.execute("SELECT COUNT(*) c FROM matches").fetchone()["c"]
                players = store.known_players(conn, me)
            finally:
                conn.close()
            return self._json({
                "me": me, "total_matches": total, "players": players,
                "map_pool": cfg.get("map_pool", []),
                "model": cfg.get("model", {}),
                "configured": bool(me) and total > 0,
            })

        if parsed.path == "/api/rank":
            mates = [p for p in (qs.get("mates", [""])[0].split(",")) if p]
            if not me:
                return self._json({"error": "config.json sem 'me' (seu steam64)"}, 400)
            conn = store.connect()
            try:
                matches = store.load_matches(conn, me)
            finally:
                conn.close()
            if not matches:
                return self._json({"error": "sem partidas no banco - rode a coleta ou o seed"}, 400)
            picker = MapPicker(matches, me, cfg)
            res = picker.rank(mates)
            conn = store.connect()
            try:
                names = {str(p["steam64"]): p["name"] for p in store.known_players(conn, None)}
            finally:
                conn.close()
            res["names"] = names
            return self._json(res)

        return self._json({"error": "rota desconhecida"}, 404)

    # ----------------------------------------------------------------- POST
    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        data = self._body()
        cfg = load_config()

        if parsed.path == "/api/ingest":
            # payload entregue pelo coletor que roda no navegador, em csstats.gg
            from .sources import csstats
            per = data.get("per_player") or {}
            names = data.get("names") or {}
            me = str(data.get("me") or cfg.get("me") or "")
            # Guarda sempre o payload cru: a coleta passa pelo Cloudflare e nao
            # vale a pena repetir so porque o 'me' ainda nao estava definido.
            raw_path = os.path.join(ROOT, "data", "raw_csstats.json")
            with open(raw_path, "w", encoding="utf-8") as f:
                json.dump({"per_player": per, "names": names}, f)
            resumo = {k: len(v or []) for k, v in per.items()}
            if not me or me not in per:
                return self._json({
                    "ok": True, "saved_raw": raw_path, "pending_me": True,
                    "message": ("payload salvo; falta definir quem e voce "
                                "(mappick.py setme STEAM64 && mappick.py csstats-build)"),
                    "coletados": resumo, "names": names,
                })
            conn = store.connect()
            try:
                n = csstats.ingest(conn, per, me, names)
                store.backfill_dedupe_keys(conn)
                dup = store.dedupe(conn)
                total = conn.execute("SELECT COUNT(*) c FROM matches").fetchone()["c"]
            finally:
                conn.close()
            msg = (f"{n} partidas gravadas, {dup} duplicatas removidas, "
                   f"{total} no banco")
            print(f"  ingest: {msg}")
            return self._json({"ok": True, "message": msg, "imported": n, "total": total})

        if parsed.path == "/api/friend":
            sid, val = str(data.get("steam64", "")), 1 if data.get("is_friend") else 0
            conn = store.connect()
            try:
                conn.execute("UPDATE players SET is_friend=? WHERE steam64=?", (val, sid))
                conn.commit()
            finally:
                conn.close()
            return self._json({"ok": True})

        if parsed.path == "/api/model":
            model = cfg.setdefault("model", {})
            for k, v in (data or {}).items():
                if k in model and isinstance(v, (int, float)):
                    model[k] = v
            save_config(cfg)
            return self._json({"ok": True, "model": model})

        return self._json({"error": "rota desconhecida"}, 404)


def serve(port=8770, open_browser=True):
    httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{port}/"
    print(f"\n  mappick rodando em {url}\n  Ctrl+C para parar\n")
    if open_browser:
        import threading
        import webbrowser
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("  encerrado.")
    finally:
        httpd.server_close()
