"""V1.1 Staging Backend E2E — Part 3: WebSocket infrastructure-layer verification.
Tests real WS at wss://api-staging.ycqinnan.cn/ws/v1.
- No token -> expect close 4401
- Valid Bearer -> connection.authenticated + connection.ready + ping/pong
- Attempt message.send -> observe whether business broadcast (message.created) occurs
  (current deployment ws.py is infra-only; business events NOT implemented -> record honestly)
"""
import asyncio, json, datetime, websockets

WS_URL = "wss://api-staging.ycqinnan.cn/ws/v1"
EV_PATH = "/tmp/e2e_evidence.json"

def now_iso(): return datetime.datetime.now(datetime.timezone.utc).isoformat()

def load_tokens():
    with open(EV_PATH, encoding="utf-8") as f:
        EV = json.load(f)
    return EV["accounts"]["E2E-A"]["access"], EV["accounts"]["E2E-B"]["access"], EV

async def ws_no_token():
    rec = {"test": "no_token", "timestamp": now_iso()}
    try:
        async with websockets.connect(WS_URL, max_size=2**20, ssl=None) as ws:
            # infra ws.py uses ssl; for wss with default cert, pass ssl=True
            pass
    except Exception as e:
        rec["connect_error"] = f"{type(e).__name__}: {e}"
    # proper: connect with ssl default (verify none via client)
    import ssl
    ctx = ssl.create_default_context(); ctx.check_hostname=False; ctx.verify_mode=ssl.CERT_NONE
    try:
        async with websockets.connect(WS_URL, ssl=ctx) as ws:
            # wait for close (should be 4401 quickly)
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=5)
                rec["early_frame"] = msg
            except asyncio.TimeoutError:
                rec["note"] = "no early frame, waiting close"
            # expect server to close with 4401
            await asyncio.wait_for(ws.wait_closed(), timeout=5)
            rec["close_code"] = ws.close_code
            rec["closed_by_server"] = True
    except Exception as e:
        rec["error"] = f"{type(e).__name__}: {e}"
        rec["close_code"] = getattr(e, "code", None)
    return rec

async def ws_valid(token, label):
    import ssl
    ctx = ssl.create_default_context(); ctx.check_hostname=False; ctx.verify_mode=ssl.CERT_NONE
    rec = {"test": label, "timestamp": now_iso(), "frames": []}
    try:
        async with websockets.connect(WS_URL, ssl=ctx, additional_headers={"Authorization": f"Bearer {token}"}) as ws:
            # collect frames for up to 6s
            end = asyncio.get_event_loop().time() + 6
            authed = False; ready = False
            while asyncio.get_event_loop().time() < end:
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=1.5)
                except asyncio.TimeoutError:
                    break
                try:
                    frame = json.loads(msg)
                except Exception:
                    frame = msg
                rec["frames"].append(frame)
                t = frame.get("type") if isinstance(frame, dict) else None
                if t == "connection.authenticated": authed = True
                if t == "connection.ready": ready = True
                if t == "connection.ping":
                    # reply pong
                    await ws.send(json.dumps({"type": "connection.pong"}))
            rec["authenticated_frame"] = authed
            rec["ready_frame"] = ready
            rec["frame_types"] = sorted({f.get("type") for f in rec["frames"] if isinstance(f, dict)})
            rec["close_code"] = ws.close_code
    except Exception as e:
        rec["error"] = f"{type(e).__name__}: {e}"
        rec["close_code"] = getattr(e, "code", None)
    return rec

async def ws_business_attempt(tokenA, tokenB, conv_id, msg_id_seed):
    """Attempt real A->B message via WS. Observe if message.created broadcasts.
    NOTE: current deployment (ws.py infra-only) does NOT implement business events.
    We record HONESTLY: if no message.created received, mark NOT_IMPLEMENTED (not FAIL)."""
    import ssl
    ctx = ssl.create_default_context(); ctx.check_hostname=False; ctx.verify_mode=ssl.CERT_NONE
    rec = {"test": "business_message_via_ws", "timestamp": now_iso(),
           "assumption": "current ws.py is infra-only (no message.send/create broadcast)",
           "B_frames": [], "A_observed_broadcast": False}
    cmid = f"ws-e2e-{msg_id_seed}"
    try:
        # B connects and listens
        async with websockets.connect(WS_URL, ssl=ctx, additional_headers={"Authorization": f"Bearer {tokenB}"}) as wsB:
            # wait B ready
            await asyncio.sleep(1.0)
            # A connects and sends message.send
            async with websockets.connect(WS_URL, ssl=ctx, additional_headers={"Authorization": f"Bearer {tokenA}"}) as wsA:
                # wait A ready
                await asyncio.sleep(1.0)
                await wsA.send(json.dumps({
                    "type": "message.send",
                    "payload": {"conversation_id": conv_id, "content": "WS hello from A", "client_message_id": cmid}
                }))
                rec["A_sent_message_send"] = True
                # A listen briefly (infra ignores business; may get nothing or error frame)
                try:
                    am = await asyncio.wait_for(wsA.recv(), timeout=3)
                    rec["A_response_to_send"] = json.loads(am) if am.startswith("{") else am
                except asyncio.TimeoutError:
                    rec["A_response_to_send"] = "TIMEOUT_NO_FRAME"
                # B listen for message.created
                end = asyncio.get_event_loop().time() + 4
                while asyncio.get_event_loop().time() < end:
                    try:
                        bm = await asyncio.wait_for(wsB.recv(), timeout=1.5)
                    except asyncio.TimeoutError:
                        break
                    try: bf = json.loads(bm)
                    except Exception: bf = bm
                    rec["B_frames"].append(bf)
                    if isinstance(bf, dict) and bf.get("type") == "message.created":
                        rec["A_observed_broadcast"] = True
                        rec["B_received_message_created"] = bf
    except Exception as e:
        rec["error"] = f"{type(e).__name__}: {e}"
    return rec

async def main():
    tokA, tokB, EV = load_tokens()
    out = {"ws_no_token": await ws_no_token()}
    out["ws_A_valid"] = await ws_valid(tokA, "A_valid_bearer")
    out["ws_B_valid"] = await ws_valid(tokB, "B_valid_bearer")
    cid = EV.get("friend_flow", {}).get("conversation_id")
    out["ws_business"] = await ws_business_attempt(tokA, tokB, cid, int(asyncio.get_event_loop().time()*1000)) if cid else {"skipped": "no conv id"}
    EV["websocket"] = out
    EV["meta"]["part3_ts"] = now_iso()
    with open(EV_PATH, "w", encoding="utf-8") as f:
        json.dump(EV, f, ensure_ascii=False, indent=2)
    print(json.dumps(out, ensure_ascii=False, indent=2))

asyncio.run(main())
