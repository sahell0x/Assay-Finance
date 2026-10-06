"""Dev-only mock of the equity-research API.

Run it when you want to look at the interface but do not want to stand up Postgres,
pgvector, Redis and a worker — which is most of the time while doing frontend work.

    python3 frontend/dev/mock-api.py        # serves on :8000

It is NOT a substitute for the real API: nothing is computed, no analysis actually
runs, and the SSE progress stream is not implemented (so the live pipeline view
cannot be exercised here). Built from one real captured AnalysisDetail (MSFT); the other
companies are derived from it with their own scores, ratings and prices."""
import json, pathlib, re, copy, random
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

HERE = pathlib.Path(__file__).parent
BASE = json.loads((HERE / "sample-analysis.json").read_text())

COMPANIES = [
    ("NVDA", "NVIDIA Corporation", "Technology", "Semiconductors", 218.36, 5.27e12, "BUY",  7.90, "medium",
     {"profitability":9.96,"financial_health":9.55,"growth":8.92,"valuation":3.28,"sentiment":6.10}),
    ("MSFT", "Microsoft Corporation", "Technology", "Software - Infrastructure", 496.20, 3.70e12, "HOLD", 7.00, "high",
     {"profitability":8.80,"financial_health":8.10,"growth":6.40,"valuation":4.60,"sentiment":6.60}),
    ("AAPL", "Apple Inc.", "Technology", "Consumer Electronics", 332.90, 4.90e12, "HOLD", 6.00, "high",
     {"profitability":9.10,"financial_health":6.90,"growth":4.10,"valuation":3.90,"sentiment":6.20}),
    ("JPM",  "JPMorgan Chase & Co.", "Financial Services", "Banks - Diversified", 356.73, 948.3e9, "HOLD", 5.40, "medium",
     {"profitability":6.20,"financial_health":None,"growth":5.30,"valuation":7.10,"sentiment":5.40}),
    ("KO",   "The Coca-Cola Company", "Consumer Defensive", "Beverages", 88.34, 380.1e9, "HOLD", 5.80, "high",
     {"profitability":7.90,"financial_health":5.20,"growth":3.60,"valuation":5.10,"sentiment":6.00}),
    ("PFE",  "Pfizer Inc.", "Healthcare", "Drug Manufacturers - General", 27.56, 157.1e9, "SELL", 4.30, "medium",
     {"profitability":5.40,"financial_health":4.80,"growth":1.10,"valuation":5.80,"sentiment":5.00}),
]
IDS = {c[0]: f"{i+1:08d}-ce46-4f46-bdc7-62d6c7b8fed8" for i, c in enumerate(COMPANIES)}
BY_TICKER = {c[0]: c for c in COMPANIES}

def build(tkr):
    t, name, sector, industry, price, cap, rating, total, conv, dims = BY_TICKER[tkr]
    a = copy.deepcopy(BASE)
    a["id"] = IDS[t]; a["ticker"] = t
    a["public_slug"] = t.lower()
    a["blocks"]["market"] = dict(a["blocks"].get("market") or {},
        name=name, sector=sector, industry=industry, price=price, market_cap=cap, currency="USD")
    sc = a["scorecard"]
    sc["rating"] = rating; sc["total"] = total; sc["conviction"] = conv
    sc["dimension_scores"] = dims
    sc["coverage"] = 1.0 if t != "NVDA" else 0.94
    sc["distance_to_edge"] = round(min(abs(total-7.5), abs(total-5.0)), 3)
    sc["dimensions_unavailable"] = [k for k, v in dims.items() if v is None]
    if sc.get("price_target"):
        sc["price_target"] = dict(sc["price_target"], low=round(price*0.88, 2), high=round(price*1.24, 2))
    if a.get("memo"):
        a["memo"] = dict(a["memo"], ticker=t, recommendation=rating, conviction=conv,
                         price_target_low=round(price*0.88,2), price_target_high=round(price*1.24,2))
    return a

def summary(tkr, i):
    t, name, *_ , rating, total, conv, dims = BY_TICKER[tkr]
    return {"id": IDS[t], "ticker": t, "status": "complete", "rating": rating,
            "conviction": conv, "total_score": total,
            "created_at": f"2026-09-{18-i:02d}T09:41:07Z", "completed_at": f"2026-09-{18-i:02d}T09:42:29Z",
            "cached": i % 3 == 2, "error": None}

def showcase(limit):
    out = []
    for t, name, sector, industry, price, cap, rating, total, conv, dims in COMPANIES[:limit]:
        a = build(t)
        out.append({"id": IDS[t], "ticker": t, "name": name, "sector": sector, "rating": rating,
                    "conviction": conv, "total_score": total, "dimension_scores": dims,
                    "price": price, "currency": "USD", "market_cap": cap,
                    "thesis": (a.get("memo") or {}).get("thesis"),
                    "completed_at": "2026-09-18T09:42:29Z"})
    return out


def scenario_setup(tkr):
    """Real solver output for NVDA, computed against the project's own scoring.py."""
    t, name, sector, industry, price, cap, rating, total, conv, dims = BY_TICKER[tkr]
    a = build(tkr)
    lev = lambda n,l,d,u,v,lo,hi,st,hib=True: {"name":n,"label":l,"dimension":d,"unit":u,
        "value":v,"min":lo,"max":hi,"step":st,"higher_is_better":hib}
    path = lambda n,l,d,u,f,to,dl,ef,rb,rt,hib=True: {"lever":n,"label":l,"dimension":d,"unit":u,
        "from":f,"to":to,"delta":dl,"effort":ef,"reachable":rb,"resulting_total":rt,
        "higher_is_better":hib}
    return {
      "ticker": t,
      "baseline": {"total": total, "rating": rating, "conviction": conv,
                   "distance_to_edge": round(min(abs(total-7.5), abs(total-5.0)), 3),
                   "dimension_scores": dims,
                   "weights_applied": {"profitability":.25,"financial_health":.20,
                                       "growth":.25,"valuation":.20,"sentiment":.10},
                   "price_target": a["scorecard"].get("price_target")},
      "thresholds": {"buy": 7.5, "hold": 5.0},
      "target_rating": "HOLD" if rating == "BUY" else "BUY",
      "levers": [
        lev("rev_yoy","Revenue growth, year on year","growth","pct",0.4030,-0.15,0.35,0.005),
        lev("roic","Return on invested capital","profitability","pct",0.8240,0.0,0.32,0.005),
        lev("operating_margin","Operating margin","profitability","pct",0.6521,-0.05,0.40,0.005),
        lev("price","Share price","valuation","currency",price,price*0.35,price*2.0,0.5,False),
        lev("growth_acceleration","Growth acceleration","growth","pct",-0.20,-0.12,0.12,0.005),
      ],
      "paths": [
        path("rev_yoy","Revenue growth, year on year","growth","pct",0.4030,-0.0170,-0.4200,0.62,True,7.49),
        path("roic","Return on invested capital","profitability","pct",0.8240,0.0340,-0.7900,0.78,True,7.49),
        path("operating_margin","Operating margin","profitability","pct",0.6521,-0.0379,-0.6900,0.81,True,7.49),
        path("price","Share price","valuation","currency",price,None,None,None,False,None,False),
        path("growth_acceleration","Growth acceleration","growth","pct",-0.20,None,None,None,False,None),
      ],
    }

USAGE = {"scope": "anon", "used": 1, "limit": 3, "remaining": 2, "exhausted": False,
         "authenticated": False,
         "budget": {"spent_usd": 2.41, "cap_usd": 3.0, "exhausted": False, "remaining_usd": 0.59},
         "signup_benefits": ["25 analyses a month", "History that follows you across devices",
                             "A watchlist that re-scores automatically"]}

class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _send(self, obj, code=200):
        b = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "http://localhost:3111")
        self.send_header("Access-Control-Allow-Credentials", "true")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers(); self.wfile.write(b)
    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "http://localhost:3111")
        self.send_header("Access-Control-Allow-Credentials", "true")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,DELETE,PATCH,OPTIONS")
        self.end_headers()
    def do_POST(self):
        p = urlparse(self.path).path
        if p.endswith("/share"): return self._send({"slug": "msft", "url": "/m/msft"})
        if "/scenario" in p:
            mm = re.match(r"^/analyses/([^/]+)/scenario$", p)
            tk = next((t for t, i in IDS.items() if mm and i == mm.group(1)), "NVDA")
            a = build(tk); sc = dict(a["scorecard"])
            sc.update(overridden=["rev_yoy"], price_scenario=None,
                      baseline={"total": sc["total"], "rating": sc["rating"],
                                "conviction": sc["conviction"]})
            sc["total"] = round(sc["total"] - 0.42, 3); sc["rating"] = "HOLD"
            return self._send(sc)
        if p == "/analyses":     return self._send({"id": IDS["NVDA"], "status": "complete",
                                     "ticker": "NVDA", "cached": True, "cached_at": "2026-09-18T09:42:29Z",
                                     "stream_url": "", "poll_url": "", "budget": USAGE["budget"], "quota": USAGE}, 202)
        return self._send({"detail": "not found"}, 404)
    def do_DELETE(self): self._send({}, 204)
    def do_GET(self):
        u = urlparse(self.path); p = u.path; q = parse_qs(u.query)
        if p == "/healthz":  return self._send({"status": "ok"})
        if p == "/usage":    return self._send(USAGE)
        if p == "/meta/pipeline":
            return self._send({"pipeline": BASE.get("pipeline") or [],
                               "weights": {"profitability":.25,"financial_health":.20,"growth":.25,
                                           "valuation":.20,"sentiment":.10},
                               "thresholds": {"buy": 7.5, "hold": 5.0},
                               "budget": USAGE["budget"]})
        if p == "/public/showcase": return self._send(showcase(int(q.get("limit", [6])[0])))
        if p == "/public/sample/memo": return self._send(build("NVDA"))
        if p.startswith("/public/"):
            t = p.rsplit("/", 1)[-1].upper()
            return self._send(build(t) if t in BY_TICKER else build("NVDA"))
        if p == "/analyses":
            lim = int(q.get("limit", [20])[0])
            return self._send([summary(c[0], i) for i, c in enumerate(COMPANIES)][:lim])
        if p == "/watchlist":
            return self._send([{"ticker": c[0], "added_at": "2026-09-10T00:00:00Z", "name": c[1],
                                "rating": c[6], "total_score": c[7], "analysis_id": IDS[c[0]],
                                "last_run": "2026-09-18T09:42:29Z"} for c in COMPANIES[:4]])
        if p == "/compare":
            ts = [t.strip().upper() for t in q.get("tickers", [""])[0].split(",") if t.strip()]
            cols, missing = [], []
            for t in ts:
                if t not in BY_TICKER: missing.append(t); continue
                c = BY_TICKER[t]; a = build(t)
                cols.append({"ticker": t, "available": True, "analysis_id": IDS[t],
                             "completed_at": "2026-09-18T09:42:29Z", "rating": c[6],
                             "conviction": c[8], "total": c[7], "dimension_scores": c[9],
                             "price_target": a["scorecard"].get("price_target"),
                             "thesis": (a.get("memo") or {}).get("thesis"),
                             "key_risks": (a.get("memo") or {}).get("key_risks", [])[:3]})
            return self._send({"columns": cols, "missing": missing,
                               "dimensions": ["profitability","financial_health","growth","valuation","sentiment"]})
        if p == "/tickers/search":
            s = q.get("q", [""])[0].upper()
            return self._send([{"ticker": c[0], "name": c[1], "exchange": "NASDAQ", "sector": c[2]}
                               for c in COMPANIES if s in c[0] or s.lower() in c[1].lower()][:8])
        m = re.match(r"^/tickers/([^/]+)/history$", p)
        if m:
            random.seed(m.group(1))
            return self._send([{"analysis_id": IDS.get(m.group(1).upper(), IDS["NVDA"]),
                                "date": f"2026-0{k+3}-01", "total": round(random.uniform(4.2, 8.4), 2),
                                "rating": "BUY", "dimension_scores": None} for k in range(6)])
        m = re.match(r"^/analyses/([^/]+)$", p)
        if m:
            for t, i in IDS.items():
                if i == m.group(1): return self._send(build(t))
            return self._send(build("NVDA"))
        m = re.match(r"^/analyses/([^/]+)/scenario$", p)
        if m:
            for t, i in IDS.items():
                if i == m.group(1): return self._send(scenario_setup(t))
            return self._send(scenario_setup("NVDA"))
        if p in ("/users/me", "/auth/me"): return self._send({"detail": "Unauthorized"}, 401)
        return self._send({"detail": "not found"}, 404)

ThreadingHTTPServer(("127.0.0.1", 8000), H).serve_forever()
