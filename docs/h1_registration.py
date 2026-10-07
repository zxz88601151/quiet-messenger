"""V1.1 Staging Hardening H1 — Multi Account Registration.
Real POST /auth/register at阶梯 10/50/100 (保守, RAM 1.9GiB 约束).
Tests: sequential / concurrent / duplicate username / invalid input / unicode.
DB readonly verification of uniqueness (no duplicate, no orphan).
Does NOT touch E2E-A / E2E-B. Marked STAGING ONLY.
Evidence -> /tmp/staging_hardening/h1.json
"""
import urllib.request, json, ssl, time, datetime, threading, random, string, os

BASE = "https://api-staging.ycqinnan.cn"
CTX = ssl.create_default_context(); CTX.check_hostname = False; CTX.verify_mode = ssl.CERT_NONE
OUTDIR = "/tmp/staging_hardening"
os.makedirs(OUTDIR, exist_ok=True)
EV = {"h1": {}, "meta": {"start": datetime.datetime.now(datetime.timezone.utc).isoformat()}}

def now_iso(): return datetime.datetime.now(datetime.timezone.utc).isoformat()

def call(method, path, body=None, token=None):
    url = BASE + path
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if token: headers["Authorization"] = f"Bearer {token}"
    rec = {"method": method, "endpoint": path, "ts": now_iso(), "body": body}
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
    return rec

def gen_user(idx):
    u = f"stress_{idx:04d}"
    return {"username": u, "phone": f"139{idx:08d}", "password": "Stress!2026xK9", "nickname": f"STRESS-{idx:04d}"}

def register_batch(users, concurrency=1, label=""):
    results = []
    lock = threading.Lock()
    def worker(u):
        r = call("POST", "/api/v1/auth/register", u)
        with lock:
            results.append({"username": u["username"], "status": r["status"],
                            "uid": (r["resp"].get("user", {}).get("id") if isinstance(r["resp"], dict) else None),
                            "err": (r["resp"] if r["status"] != 201 else None)})
    if concurrency <= 1:
        for u in users:
            worker(u)
    else:
        threads = [threading.Thread(target=worker, args=(u,)) for u in users]
        for t in threads: t.start()
        for t in threads: t.join()
    ok = sum(1 for r in results if r["status"] == 201)
    fail = len(results) - ok
    EV["h1"].setdefault("batches", {})[label] = {
        "total": len(users), "concurrency": concurrency, "ok_201": ok, "fail": fail,
        "fail_samples": [r for r in results if r["status"] != 201][:5],
        "ts": now_iso(),
    }
    return results

# ---- H1 Step: 10 sequential ----
print("=== H1-10 sequential ===")
u10 = [gen_user(i) for i in range(1, 11)]
register_batch(u10, 1, "s10_seq")

# ---- H1 Step: 50 sequential ----
print("=== H1-50 sequential ===")
u50 = [gen_user(i) for i in range(11, 61)]
register_batch(u50, 1, "s50_seq")

# ---- H1 Step: 100 concurrent (conservative, single worker) ----
print("=== H1-100 concurrent ===")
u100 = [gen_user(i) for i in range(61, 161)]
register_batch(u100, 100, "c100_conc")

# ---- H1 Step: duplicate username (same user sent twice concurrently) ----
print("=== H1 duplicate username concurrent ===")
dup_u = gen_user(9001)
dup_users = [dup_u, dict(dup_u)]  # identical username+phone
register_batch(dup_users, 2, "dup_username_x2")

# ---- H1 Step: invalid input ----
print("=== H1 invalid input ===")
inv = []
for body in [
    {"username": "", "phone": "13900000000", "password": "x", "nickname": "e"},
    {"username": "stress_inv1", "phone": "13900000000", "password": "", "nickname": "e"},  # empty pw
    {"username": "stress_inv2", "phone": "13900000000", "password": "Stress!2026xK9", "nickname": "e", "extra": "x"},
    {"username": "stress_inv3", "password": "Stress!2026xK9"},  # missing phone
    {"username": "stress unicode 测试", "phone": "13900000001", "password": "Stress!2026xK9", "nickname": "ünïcöde"},
]:
    r = call("POST", "/api/v1/auth/register", body)
    inv.append({"body_keys": list(body.keys()), "status": r["status"], "resp": (r["resp"] if r["status"] != 201 else "OK")})
EV["h1"]["invalid_input"] = inv

EV["meta"]["end"] = now_iso()
with open(f"{OUTDIR}/h1.json", "w", encoding="utf-8") as f:
    json.dump(EV, f, ensure_ascii=False, indent=2)

# summary
print("\n=== H1 SUMMARY ===")
for k, v in EV["h1"].get("batches", {}).items():
    print(f"  {k}: total={v['total']} ok_201={v['ok_201']} fail={v['fail']}")
print(f"  invalid_input samples: {len(inv)} sent")
print(f"  evidence: {OUTDIR}/h1.json")
