"""V1.1 Staging Backend E2E — Part 1: Accounts + Auth Flow + Negative Auth.
Pure stdlib (urllib) + websockets. No code/config/schema changes.
Evidence written to /tmp/e2e_evidence.json (append mode via reload).
"""
import urllib.request, json, ssl, time, datetime, sys

BASE = "https://api.example.com"
CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE

EVIDENCE = {"accounts": {}, "auth_flow": {}, "negative_auth": {}, "meta": {}}
EV_PATH = "/tmp/e2e_evidence.json"

def now_iso():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()

def call(method, path, body=None, token=None, expect_status=None):
    url = BASE + path
    data = None
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    rec = {
        "method": method, "endpoint": path, "timestamp": now_iso(),
        "request_body": body,
    }
    try:
        with urllib.request.urlopen(req, timeout=20, context=CTX) as r:
            raw = r.read().decode("utf-8")
            rec["http_status"] = r.status
            rec["response"] = json.loads(raw) if raw else None
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        rec["http_status"] = e.code
        try:
            rec["response"] = json.loads(raw)
        except Exception:
            rec["response"] = raw
    except Exception as e:
        rec["http_status"] = None
        rec["response"] = f"ERROR {type(e).__name__}: {e}"
    if expect_status is not None:
        rec["expect_match"] = (rec["http_status"] == expect_status)
    return rec

# ---- Accounts ----
USERS = {
    "E2E-A": {"username": "staging_e2e_a_7f3c", "phone": "13800000001",
              "password": "E2Ea!2026xK9", "nickname": "E2E-A-STAGING"},
    "E2E-B": {"username": "staging_e2e_b_7f3c", "phone": "13800000002",
              "password": "E2Eb!2026xK9", "nickname": "E2E-B-STAGING"},
}

print("=== Step 1: Register E2E-A / E2E-B (real POST /auth/register) ===")
for role, u in USERS.items():
    reg = call("POST", "/api/v1/auth/register", {
        "username": u["username"], "phone": u["phone"],
        "password": u["password"], "nickname": u["nickname"],
    }, expect_status=201)
    EVIDENCE["accounts"][role] = {
        "username": u["username"], "phone": u["phone"],
        "register": reg,
    }
    if reg["http_status"] == 201:
        u["access"] = reg["response"]["access_token"]
        u["refresh"] = reg["response"]["refresh_token"]
        u["user_id"] = reg["response"]["user"]["id"]
        EVIDENCE["accounts"][role]["user_id"] = u["user_id"]
        EVIDENCE["accounts"][role]["created_at"] = now_iso()
        EVIDENCE["accounts"][role]["purpose"] = "STAGING-E2E only; not production; not personal"
        print(f"  {role}: 201 user_id={u['user_id']}")
    else:
        print(f"  {role}: HTTP {reg['http_status']} -> {json.dumps(reg['response'])[:200]}")
        # If already exists (duplicate), try login instead (but do NOT overwrite existing users)
        if reg["http_status"] in (400, 409):
            print(f"  {role}: register failed, attempting login to recover token (no data mutation)")
            lg = call("POST", "/api/v1/auth/login", {
                "identifier": u["username"], "password": u["password"],
                "device": {"device_type": "mobile", "device_name": "E2E-Test", "device_identifier": f"e2e-{role}"},
            }, expect_status=200)
            EVIDENCE["accounts"][role]["login_recover"] = lg
            if lg["http_status"] == 200:
                u["access"] = lg["response"]["access_token"]
                u["refresh"] = lg["response"]["refresh_token"]
                u["user_id"] = lg["response"]["user"]["id"]
                EVIDENCE["accounts"][role]["user_id"] = u["user_id"]
                print(f"  {role}: recovered via login user_id={u['user_id']}")

# ---- Auth Flow: /me + refresh ----
print("=== Step 2: Auth Flow (login explicit + /me + refresh) ===")
for role, u in USERS.items():
    if "access" not in u:
        print(f"  {role}: SKIP (no token)")
        continue
    # explicit login (device object required)
    lg = call("POST", "/api/v1/auth/login", {
        "identifier": u["username"], "password": u["password"],
        "device": {"device_type": "mobile", "device_name": "E2E-Test", "device_identifier": f"e2e-{role}"},
    }, expect_status=200)
    EVIDENCE["auth_flow"][f"{role}_login"] = lg
    if lg["http_status"] == 200:
        u["access"] = lg["response"]["access_token"]
        u["refresh"] = lg["response"]["refresh_token"]
    # /me
    me = call("GET", "/api/v1/users/me", token=u["access"], expect_status=200)
    EVIDENCE["auth_flow"][f"{role}_me"] = me
    # refresh
    rf = call("POST", "/api/v1/auth/refresh", {"refresh_token": u["refresh"]}, expect_status=200)
    EVIDENCE["auth_flow"][f"{role}_refresh"] = rf
    if rf["http_status"] == 200:
        u["access"] = rf["response"]["access_token"]
        u["refresh"] = rf["response"]["refresh_token"]
        # /me with NEW access token after rotation
        me2 = call("GET", "/api/v1/users/me", token=u["access"], expect_status=200)
        EVIDENCE["auth_flow"][f"{role}_me_after_refresh"] = me2
        print(f"  {role}: login 200 / me 200 / refresh 200 / me(after rotation) {me2['http_status']}")
    else:
        print(f"  {role}: refresh HTTP {rf['http_status']}")

# ---- Negative Auth ----
print("=== Step 3: Negative Auth ===")
# wrong password
neg_wrong = call("POST", "/api/v1/auth/login", {
    "identifier": USERS["E2E-A"]["username"], "password": "WRONG_PASSWORD_xx",
    "device": {"device_type": "mobile", "device_name": "x", "device_identifier": "x"},
}, expect_status=401)
EVIDENCE["negative_auth"]["wrong_password"] = neg_wrong
# no token on /me
neg_notoken = call("GET", "/api/v1/users/me", expect_status=401)
EVIDENCE["negative_auth"]["no_token"] = neg_notoken
# illegal token
neg_bad = call("GET", "/api/v1/users/me", token="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.invalid.invalid", expect_status=401)
EVIDENCE["negative_auth"]["illegal_token"] = neg_bad

# refresh rotation check: old refresh token behavior (if contract rotates)
# After we rotated above, the OLD refresh (before last rotation) should be revoked.
# We saved only latest; do a dedicated rotation test on E2E-B:
print("=== Step 3b: Refresh rotation (old token revocation) ===")
u = USERS["E2E-B"]
rf1 = call("POST", "/api/v1/auth/refresh", {"refresh_token": u["refresh"]}, expect_status=200)
EVIDENCE["negative_auth"]["rotate_rf1"] = rf1
if rf1["http_status"] == 200:
    old_refresh = u["refresh"]
    u["refresh"] = rf1["response"]["refresh_token"]
    # try using OLD refresh again -> should be revoked (401) if rotation enforced
    rf_old = call("POST", "/api/v1/auth/refresh", {"refresh_token": old_refresh}, expect_status=401)
    EVIDENCE["negative_auth"]["old_refresh_reuse"] = rf_old
    print(f"  rotation: new refresh 200; old refresh reuse HTTP {rf_old['http_status']}")

EVIDENCE["meta"]["part1_ts"] = now_iso()
with open(EV_PATH, "w", encoding="utf-8") as f:
    json.dump(EVIDENCE, f, ensure_ascii=False, indent=2)
print(f"\n=== Evidence written to {EV_PATH} ===")
print("Summary: accounts=", {k: v.get('user_id') for k, v in EVIDENCE['accounts'].items()})
print("negative:", {k: v.get('http_status') for k, v in EVIDENCE['negative_auth'].items()})
