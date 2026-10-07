"""V1.1 Staging Hardening H2 — Auth/Login/Session Integrity.
Conservative concurrency: 10 / 20 / 50 (NO 100, per H1 capacity limit).
Reuse existing STAGING-E2E (E2E-A/B) + H1 STRESS accounts (stress_0001..0050 exist).
Three-layer evidence: Client (HTTP) / Server (response correctness) / Database (readonly).
Negative auth + refresh rotation. No deployment/code changes. STOP after H2.
Evidence -> /tmp/staging_hardening/h2.json (H1 json preserved separately).
"""
import urllib.request, json, ssl, time, datetime, threading, os

BASE = "https://api-staging.ycqinnan.cn"
CTX = ssl.create_default_context(); CTX.check_hostname = False; CTX.verify_mode = ssl.CERT_NONE
OUTDIR = "/tmp/staging_hardening"
os.makedirs(OUTDIR, exist_ok=True)
EV = {"h2": {}, "meta": {"start": datetime.datetime.now(datetime.timezone.utc).isoformat()}}

def now_iso(): return datetime.datetime.now(datetime.timezone.utc).isoformat()

def call(method, path, body=None, token=None):
    url = BASE + path
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if token: headers["Authorization"] = f"Bearer {token}"
    rec = {"ts": now_iso()}
    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(urllib.request.Request(url, data=data, headers=headers, method=method), timeout=20, context=CTX) as r:
            raw = r.read().decode()
            rec["status"] = r.status
            try: rec["resp"] = json.loads(raw)
            except Exception: rec["resp"] = raw
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        rec["status"] = e.code
        try: rec["resp"] = json.loads(raw)
        except Exception: rec["resp"] = raw
    except Exception as e:
        rec["status"] = None; rec["resp"] = f"ERR {type(e).__name__}: {e}"
    rec["latency_ms"] = round((time.monotonic() - t0) * 1000, 1)
    return rec

# Account pool: E2E-A/B + stress_0001..0050 (verified exist from H1 DB check)
E2E = [
    {"username": "staging_e2e_a_7f3c", "password": "E2Ea!2026xK9"},
    {"username": "staging_e2e_b_7f3c", "password": "E2Eb!2026xK9"},
]
STRESS = [{"username": f"stress_{i:04d}", "password": "Stress!2026xK9"} for i in range(1, 51)]
POOL = E2E + STRESS  # 52 accounts

def auth_flow_one(acc):
    """Login -> /me -> Refresh -> /me(after). Returns layer evidence."""
    out = {"username": acc["username"]}
    lg = call("POST", "/api/v1/auth/login", {
        "identifier": acc["username"], "password": acc["password"],
        "device": {"device_type": "mobile", "device_name": "H2", "device_identifier": f"h2-{acc['username']}"}})
    out["login"] = {"status": lg["status"], "latency_ms": lg["latency_ms"]}
    if lg["status"] != 200:
        out["login"]["resp"] = lg["resp"]
        return out, False
    uid = lg["resp"]["user"]["id"]
    out["login"]["uid"] = uid
    access = lg["resp"]["access_token"]; refresh = lg["resp"]["refresh_token"]
    me = call("GET", "/api/v1/users/me", token=access)
    out["me"] = {"status": me["status"], "latency_ms": me["latency_ms"]}
    # Server-layer: /me uid must match login uid
    if me["status"] == 200:
        out["me"]["uid_match"] = (me["resp"].get("id") == uid)
    else:
        out["me"]["resp"] = me["resp"]
    # Refresh
    rf = call("POST", "/api/v1/auth/refresh", {"refresh_token": refresh})
    out["refresh"] = {"status": rf["status"], "latency_ms": rf["latency_ms"]}
    if rf["status"] == 200:
        new_access = rf["resp"]["access_token"]; new_refresh = rf["resp"]["refresh_token"]
        me2 = call("GET", "/api/v1/users/me", token=new_access)
        out["me_after_refresh"] = {"status": me2["status"]}
        out["refresh"]["rotated"] = (new_refresh != refresh)
        return out, (me["status"] == 200 and out.get("me", {}).get("uid_match") and rf["status"] == 200 and me2["status"] == 200)
    else:
        out["refresh"]["resp"] = rf["resp"]
        return out, False

def run_concurrency(level):
    accounts = POOL[:level] if level <= len(POOL) else POOL
    results = []
    lock = threading.Lock()
    stop = threading.Event()
    def worker(acc):
        if stop.is_set():
            return
        out, ok = auth_flow_one(acc)
        with lock:
            results.append(out)
    threads = [threading.Thread(target=worker, args=(a,)) for a in accounts]
    t0 = time.monotonic()
    for t in threads: t.start()
    for t in threads: t.join()
    wall = round((time.monotonic() - t0) * 1000, 1)
    ok_count = sum(1 for r in results if r.get("login", {}).get("status") == 200 and r.get("me", {}).get("uid_match") and r.get("refresh", {}).get("status") == 200)
    timeout_count = sum(1 for r in results if r.get("login", {}).get("status") is None)
    s5xx = sum(1 for r in results if isinstance(r.get("login", {}).get("status"), int) and r["login"]["status"] >= 500)
    s4xx = sum(1 for r in results if isinstance(r.get("login", {}).get("status"), int) and 400 <= r["login"]["status"] < 500)
    lats = [r.get("login", {}).get("latency_ms") for r in results if r.get("login", {}).get("latency_ms")]
    lats.sort()
    def pct(p): return lats[int(len(lats)*p)] if lats else None
    summary = {
        "level": level, "total": len(accounts), "ok_full_flow": ok_count,
        "login_200": sum(1 for r in results if r.get("login", {}).get("status") == 200),
        "timeout": timeout_count, "http_4xx": s4xx, "http_5xx": s5xx,
        "wall_ms": wall, "p50_ms": pct(0.5), "p95_ms": pct(0.95), "p99_ms": pct(0.99),
        "max_ms": max(lats) if lats else None, "rps": round(len(accounts)/(wall/1000), 2) if wall else None,
        "ts": now_iso(),
    }
    EV["h2"].setdefault("concurrency", {})[f"c{level}"] = summary
    # STOP condition:大量 timeout
    if timeout_count > level * 0.2:  # >20% timeout
        summary["STOP_TRIGGERED"] = True
        EV["h2"]["stop_at_level"] = level
    return summary

print("=== H2 concurrency 10 ===")
s10 = run_concurrency(10)
print(f"  c10: ok={s10['ok_full_flow']}/{s10['total']} timeout={s10['timeout']} 5xx={s10['http_5xx']} p95={s10['p95_ms']}ms")
if s10.get("STOP_TRIGGERED"):
    print("  STOP TRIGGERED at 10")
else:
    print("=== H2 concurrency 20 ===")
    s20 = run_concurrency(20)
    print(f"  c20: ok={s20['ok_full_flow']}/{s20['total']} timeout={s20['timeout']} 5xx={s20['http_5xx']} p95={s20['p95_ms']}ms")
    if not s20.get("STOP_TRIGGERED"):
        print("=== H2 concurrency 50 ===")
        s50 = run_concurrency(50)
        print(f"  c50: ok={s50['ok_full_flow']}/{s50['total']} timeout={s50['timeout']} 5xx={s50['http_5xx']} p95={s50['p95_ms']}ms")

# Negative auth (real)
print("=== H2 Negative Auth ===")
neg = {}
ua = POOL[0]
lg_wrong = call("POST", "/api/v1/auth/login", {"identifier": ua["username"], "password": "WRONG_PW_xx", "device": {"device_type":"mobile","device_name":"x","device_identifier":"x"}})
neg["wrong_password"] = lg_wrong["status"]
me_notoken = call("GET", "/api/v1/users/me")
neg["no_token"] = me_notoken["status"]
me_bad = call("GET", "/api/v1/users/me", token="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.invalid.invalid")
neg["invalid_token"] = me_bad["status"]
EV["h2"]["negative_auth"] = neg

# Refresh rotation replay (real, on E2E-B)
print("=== H2 Refresh rotation replay ===")
lg = call("POST", "/api/v1/auth/login", {"identifier": "staging_e2e_b_7f3c", "password": "E2Eb!2026xK9", "device": {"device_type":"mobile","device_name":"H2","device_identifier":"h2-rot"}})
if lg["status"] == 200:
    rf1 = call("POST", "/api/v1/auth/refresh", {"refresh_token": lg["resp"]["refresh_token"]})
    if rf1["status"] == 200:
        old = lg["resp"]["refresh_token"]
        new = rf1["resp"]["refresh_token"]
        replay = call("POST", "/api/v1/auth/refresh", {"refresh_token": old})
        EV["h2"]["refresh_rotation"] = {"new_200": True, "old_replay_status": replay["status"]}

EV["meta"]["end"] = now_iso()
with open(f"{OUTDIR}/h2.json", "w", encoding="utf-8") as f:
    json.dump(EV, f, ensure_ascii=False, indent=2)
print(f"\nevidence: {OUTDIR}/h2.json")
print("=== H2 SUMMARY ===")
for k, v in EV["h2"].get("concurrency", {}).items():
    print(f"  {k}: ok={v['ok_full_flow']}/{v['total']} timeout={v['timeout']} 5xx={v['http_5xx']} p95={v['p95_ms']}ms rps={v['rps']}")
print(f"  negative_auth: {neg}")
print(f"  refresh_rotation: {EV['h2'].get('refresh_rotation')}")
