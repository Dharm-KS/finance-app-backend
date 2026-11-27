"""Build the password-protected API docs page.

    DOCS_PASSWORD='...' python3 docs/api_page/build.py

Encrypts content.html (gitignored: it holds the prod client secret) with the password
(PBKDF2-SHA256, 250k iterations -> AES-256-GCM) and writes:
  - app/static/api-docs/index.html  served by the backend at /api-docs (committed; only ciphertext)
  - docs/api_page/artifact.html      the same page for the shared claude.ai link (gitignored)
The browser decrypts with the password; without it the page source shows only scrambled data.
"""
import base64
import json
import os
from pathlib import Path

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

here = Path(__file__).resolve().parent
root = here.parents[1]
password = os.environ["DOCS_PASSWORD"].encode()
iterations = 250_000
salt, iv = os.urandom(16), os.urandom(12)
key = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=iterations).derive(password)
data = AESGCM(key).encrypt(iv, (here / "content.html").read_bytes(), None)
b64 = lambda b: base64.b64encode(b).decode()  # noqa: E731
payload = json.dumps({"salt": b64(salt), "iv": b64(iv), "iter": iterations, "data": b64(data)})
page = (here / "shell.html").read_text().replace("__PAYLOAD__", payload)

# claude.ai artifact: the host adds <html>/<head>/<body> itself
(here / "artifact.html").write_text(page)

# backend: a complete HTML document
head, body = page.split('<div class="wrap">', 1)
doc = ('<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
       '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
       '<meta name="robots" content="noindex">\n'
       f'{head}</head>\n<body>\n<div class="wrap">{body}</body>\n</html>\n')
out = root / "app/static/api-docs/index.html"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(doc)
print("wrote", out.relative_to(root), "and", (here / "artifact.html").relative_to(root))
