"""Webhook signatures and worker-identifier handling.

Signature scheme for direct integrations (our own, Stripe-style):
    X-SSEW-Signature: t=<unix seconds>,v1=<hex HMAC-SHA256(secret, "<t>." + raw request body)>
The HMAC covers the exact bytes received (not re-serialized JSON), the timestamp blocks replays, and
the comparison runs in constant time. Marketplace platforms such as Procore or Autodesk Build sign
webhooks their own way; each platform adapter must verify that platform's documented scheme.
"""
import hashlib
import hmac
import time


class SignatureError(Exception):
    pass


def sign(secret: str, body: bytes, t: int | None = None) -> str:
    t = int(time.time()) if t is None else t
    mac = hmac.new(secret.encode(), f"{t}.".encode() + body, hashlib.sha256).hexdigest()
    return f"t={t},v1={mac}"


def verify(secret: str, body: bytes, header: str | None, max_skew: int = 300, now: float | None = None) -> int:
    if not header:
        raise SignatureError("missing X-SSEW-Signature header")
    try:
        parts = dict(p.split("=", 1) for p in header.split(","))
        t, given = int(parts["t"]), parts["v1"]
    except (ValueError, KeyError):
        raise SignatureError("malformed signature header")
    now = time.time() if now is None else now
    if abs(now - t) > max_skew:
        raise SignatureError("signature timestamp outside the allowed window")
    expected = hmac.new(secret.encode(), f"{t}.".encode() + body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, given):    # safe for unequal lengths too
        raise SignatureError("signature does not match")
    return t


def roster_counts(roster, pepper: bytes):
    """Turn a gate or badge roster into the counts the model uses, then forget the identifiers.

    Workers are de-duplicated with a keyed hash that exists only in memory for this call. Nothing
    identifying a worker (ID, name or hash) is returned or stored: a salted hash of a badge number is
    still personal information, because anyone holding the salt can re-link it."""
    seen, hours, trades, new, overtime = set(), 0.0, set(), 0, 0
    for w in roster:
        ref = str(w.get("worker_ref", "")).strip()
        if not ref:
            continue
        key = hmac.new(pepper, ref.encode(), hashlib.sha256).digest()
        if key in seen:
            continue
        seen.add(key)
        h = float(w.get("hours", 8) or 0)
        hours += h
        overtime += h > 8
        new += bool(w.get("new_hire"))
        if w.get("trade"):
            trades.add(str(w["trade"]).strip().lower())
    n = len(seen)
    return {"crew": n, "crew_hours": round(hours, 1), "trades": max(len(trades), 1 if n else 0),
            "new_workers_pct": round(100 * new / n, 1) if n else 0.0,
            "overtime_pct": round(100 * overtime / n, 1) if n else 0.0}
