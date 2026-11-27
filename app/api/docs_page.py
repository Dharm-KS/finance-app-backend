"""Password-protected API docs page (/api-docs).

The page content is encrypted with the team password (see docs/api_page/build.py) and normally
decrypted in the browser. Browsers only offer that crypto on HTTPS or localhost, so on a plain-HTTP
server the page posts the password here instead and the server decrypts the same ciphertext.
Failed attempts are rate limited per client IP.
"""

import base64
import json
import re
import time
from collections import defaultdict, deque
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from fastapi import APIRouter, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

PAGE = Path(__file__).resolve().parents[1] / "static" / "api-docs" / "index.html"
MAX_FAILURES = 10
WINDOW_SECONDS = 15 * 60

router = APIRouter(include_in_schema=False)
_failures: dict[str, deque[float]] = defaultdict(deque)


class UnlockIn(BaseModel):
    password: str = Field(min_length=1, max_length=200)


def _payload() -> dict:
    match = re.search(r"const PAYLOAD = (\{.*?\});", PAGE.read_text())
    if not match:
        raise RuntimeError("API docs page has no encrypted payload; run docs/api_page/build.py")
    return json.loads(match.group(1))


def _decrypt(password: str) -> str | None:
    p = _payload()
    key = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=base64.b64decode(p["salt"]),
                     iterations=p["iter"]).derive(password.encode())
    try:
        return AESGCM(key).decrypt(base64.b64decode(p["iv"]), base64.b64decode(p["data"]), None).decode()
    except InvalidTag:
        return None


def _recent_failures(ip: str) -> deque[float]:
    q, now = _failures[ip], time.monotonic()
    while q and now - q[0] > WINDOW_SECONDS:
        q.popleft()
    return q


@router.get("/api-docs")
@router.get("/api-docs/")
async def api_docs_page():
    return FileResponse(PAGE, media_type="text/html", headers={"Cache-Control": "no-cache"})


@router.post("/api-docs/unlock")
async def unlock(payload: UnlockIn, request: Request):
    ip = request.client.host if request.client else "unknown"
    failures = _recent_failures(ip)
    if len(failures) >= MAX_FAILURES:
        return JSONResponse({"success": False, "message": "Too many wrong attempts. Try again in 15 minutes."},
                            status_code=429, headers={"Cache-Control": "no-store"})
    html = await run_in_threadpool(_decrypt, payload.password)
    if html is None:
        failures.append(time.monotonic())
        return JSONResponse({"success": False, "message": "Wrong password"}, status_code=401,
                            headers={"Cache-Control": "no-store"})
    failures.clear()
    return JSONResponse({"success": True, "data": {"html": html}}, headers={"Cache-Control": "no-store"})
