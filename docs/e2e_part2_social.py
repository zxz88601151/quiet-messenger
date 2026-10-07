"""V1.1 Staging Backend E2E — Part 2: User Search + Friend + Conversation + Message REST.
Loads tokens from /tmp/e2e_evidence.json. Pure stdlib + websockets. No mutations to code/config.
"""
import urllib.request, json, ssl, time, datetime

BASE = "https://api.example.com"
CTX = ssl.create_default_context(); CTX.check_hostname = False; CTX.verify_mode = ssl.CERT_NONE
EV_PATH = "/tmp/e2e_evidence.json"

def now_iso(): return datetime.datetime.now(datetime.timezone.utc).isoformat()
def call(method, path, body=None, token=None, expect_status=None):
    url = BASE + path
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if token: headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    rec = {"method": method, "endpoint": path, "timestamp": now_iso(), "request_body": body}
    try:
        with urllib.request.urlopen(req, timeout=20, context=CTX) as r:
            raw = r.read().decode()
            rec["http_status"] = r.status
            rec["response"] = json.loads(raw) if raw else None
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        rec["http_status"] = e.code
        try: rec["response"] = json.loads(raw)
        except Exception: rec["response"] = raw
    except Exception as e:
        rec["http_status"] = None; rec["response"] = f"ERROR {type(e).__name__}: {e}"
    if expect_status is not None: rec["expect_match"] = (rec["http_status"] == expect_status)
    return rec

with open(EV_PATH, encoding="utf-8") as f:
    EV = json.load(f)

A = EV["accounts"]["E2E-A"]; B = EV["accounts"]["E2E-B"]
# Re-login to get fresh tokens (refresh tokens rotated in part1; use login)
def fresh_token(role, acc):
    u = acc
    lg = call("POST", "/api/v1/auth/login", {
        "identifier": u["username"], "password": ("E2Ea!2026xK9" if role=="A" else "E2Eb!2026xK9"),
        "device": {"device_type": "mobile", "device_name": "E2E-Test", "device_identifier": f"e2e-{role}"},
    }, expect_status=200)
    return lg["response"]["access_token"], lg["response"]["refresh_token"]
tokA, refA = fresh_token("A", A)
tokB, refB = fresh_token("B", B)
EV["accounts"]["E2E-A"]["access"] = tokA; EV["accounts"]["E2E-A"]["refresh"] = refA
EV["accounts"]["E2E-B"]["access"] = tokB; EV["accounts"]["E2E-B"]["refresh"] = refB

EV.setdefault("user_search", {}); EV.setdefault("friend_flow", {})
EV.setdefault("negative_friend", {}); EV.setdefault("conversation", {})
EV.setdefault("message_rest", {})

print("=== Step 4: User Search (E2E-A searches E2E-B) ===")
srch = call("GET", f"/api/v1/users/search?q={B['username']}", token=tokA, expect_status=200)
EV["user_search"]["search_B_by_A"] = srch
if srch["http_status"] == 200:
    items = srch["response"]
    print(f"  found {len(items)} user(s)")
    for it in items:
        keys = set(it.keys())
        allowed = {"id", "username", "nickname", "avatar"}
        leak = keys - allowed
        print(f"  id={it.get('id')} username={it.get('username')} nickname={it.get('nickname')} avatar={it.get('avatar')}")
        print(f"  sensitive_field_leak={sorted(leak) if leak else 'NONE'}")
        EV["user_search"]["field_leak_check"] = sorted(leak) if leak else "NONE"
        # capture B id for friend flow
        EV["user_search"]["found_B_id"] = it.get("id")

print("=== Step 5/8: Friend Request A->B, Accept by B ===")
fr = call("POST", "/api/v1/friends/requests", {"target_username_or_phone": B["username"]}, token=tokA, expect_status=201)
EV["friend_flow"]["A_send_request"] = fr
req_id = None
if fr["http_status"] == 201:
    req_id = fr["response"].get("id")
    print(f"  request created id={req_id} status={fr['response'].get('status')}")
elif fr["http_status"] == 200:
    # already exists / already friend
    req_id = fr["response"].get("id")
    print(f"  request 200 (exists/already) id={req_id}")
# list incoming for B
inc = call("GET", "/api/v1/friends/requests?type=incoming", token=tokB, expect_status=200)
EV["friend_flow"]["B_incoming"] = inc
if req_id is None and inc["http_status"] == 200:
    for r in inc["response"]:
        if r.get("requester", {}).get("id") == A["user_id"] or r.get("from_user", {}).get("id") == A["user_id"]:
            req_id = r.get("id"); break
# accept by B
if req_id:
    acc = call("POST", f"/api/v1/friends/requests/{req_id}/accept", {}, token=tokB, expect_status=200)
    EV["friend_flow"]["B_accept"] = acc
    if acc["http_status"] == 200:
        print(f"  accept 200 friendship={ 'friendship' in acc['response'] } conversation={'conversation' in acc['response']}")
        EV["friend_flow"]["conversation_id"] = acc["response"].get("conversation", {}).get("id")
        EV["friend_flow"]["friendship_id"] = acc["response"].get("friendship", {}).get("id")
    # verify both sides list each other
    fa = call("GET", "/api/v1/friends", token=tokA, expect_status=200)
    fb = call("GET", "/api/v1/friends", token=tokB, expect_status=200)
    EV["friend_flow"]["A_friends_list"] = fa; EV["friend_flow"]["B_friends_list"] = fb
    print(f"  A friends={len(fa['response']) if fa['http_status']==200 else fa['http_status']}, B friends={len(fb['response']) if fb['http_status']==200 else fb['http_status']}")

print("=== Step 6: Negative Friend Cases (Contract-only) ===")
# self-add
nf_self = call("POST", "/api/v1/friends/requests", {"target_username_or_phone": A["username"]}, token=tokA)
EV["negative_friend"]["self_add"] = nf_self
# non-existent user
nf_none = call("POST", "/api/v1/friends/requests", {"target_username_or_phone": "staging_e2e_nonexistent_zzz"}, token=tokA)
EV["negative_friend"]["nonexistent_user"] = nf_none
# duplicate request (already friends now)
nf_dup = call("POST", "/api/v1/friends/requests", {"target_username_or_phone": B["username"]}, token=tokA)
EV["negative_friend"]["duplicate_after_friend"] = nf_dup
# non-recipient cannot accept (A tries to accept own outgoing -> use a fresh request from B to A then A accepts? simpler: A cannot accept B's request that doesn't exist)
nf_nonrecip = call("POST", "/api/v1/friends/requests/00000000-0000-0000-0000-000000000000/accept", {}, token=tokA)
EV["negative_friend"]["accept_nonexistent"] = nf_nonrecip
print(f"  self_add={nf_self['http_status']} nonexistent={nf_none['http_status']} dup={nf_dup['http_status']} accept_missing={nf_nonrecip['http_status']}")

print("=== Step 7/9: Conversation verify (A side) ===")
cid = EV["friend_flow"].get("conversation_id")
if cid:
    gc = call("GET", f"/api/v1/conversations/{cid}", token=tokA, expect_status=200)
    EV["conversation"]["A_get_conv"] = gc
    if gc["http_status"] == 200:
        conv = gc["response"]
        parts = conv.get("participants") or [conv.get("peer")]
        print(f"  conversation {cid}: peer={conv.get('peer',{}).get('username') if conv.get('peer') else None}")
        # B can access too?
        gcB = call("GET", f"/api/v1/conversations/{cid}", token=tokB, expect_status=200)
        EV["conversation"]["B_get_conv"] = gcB
        print(f"  B access conv HTTP {gcB['http_status']}")
    # list conversations for A
    lc = call("GET", "/api/v1/conversations", token=tokA, expect_status=200)
    EV["conversation"]["A_list"] = lc

print("=== Step 10: Message REST (A sends, B reads) ===")
if cid:
    cmid = f"e2e-{int(time.time()*1000)}"
    sm = call("POST", f"/api/v1/conversations/{cid}/messages", {"content": "Hello from E2E-A (staging backend e2e)", "client_message_id": cmid}, token=tokA, expect_status=201)
    EV["message_rest"]["A_send"] = sm
    msg_id = None
    if sm["http_status"] == 201:
        msg_id = sm["response"].get("id")
        print(f"  A send 201 msg_id={msg_id} sender={sm['response'].get('sender_id')} conv={sm['response'].get('conversation_id')} state={sm['response'].get('state')}")
        # B reads messages
        rd = call("GET", f"/api/v1/conversations/{cid}/messages?limit=20", token=tokB, expect_status=200)
        EV["message_rest"]["B_read"] = rd
        if rd["http_status"] == 200:
            items = rd["response"].get("items", [])
            found = [m for m in items if m.get("id") == msg_id]
            print(f"  B read {len(items)} msg(s); target present={bool(found)}")
            if found:
                m = found[0]
                EV["message_rest"]["consistency_fields"] = {
                    "id_match": m.get("id") == msg_id,
                    "sender": m.get("sender_id"), "conversation": m.get("conversation_id"),
                    "content": m.get("content"), "created_at": m.get("created_at"), "state": m.get("state"),
                }
                print(f"  consistency: {EV['message_rest']['consistency_fields']}")
    # idempotency: same client_message_id again
    sm2 = call("POST", f"/api/v1/conversations/{cid}/messages", {"content": "dup", "client_message_id": cmid}, token=tokA)
    EV["message_rest"]["A_send_idempotent"] = sm2
    print(f"  idempotent re-send HTTP {sm2['http_status']} (expect 200 with same msg)")

EV["meta"]["part2_ts"] = now_iso()
with open(EV_PATH, "w", encoding="utf-8") as f:
    json.dump(EV, f, ensure_ascii=False, indent=2)
print(f"\n=== Evidence updated {EV_PATH} ===")
