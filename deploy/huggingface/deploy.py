"""Deploy the public demo to a Hugging Face Docker Space (free CPU tier, no credit card).

    python deploy/huggingface/deploy.py            # create/update the Space and push the code
    python deploy/huggingface/deploy.py --secrets  # also set ANTHROPIC/OPENAI keys from .env as Space secrets

Token: HF_TOKEN env var, or the file ~/.cache/huggingface/token (write access).
Only git-tracked files are pushed (git archive), so .env and samples/ can never be included.
Standard library only.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
API = "https://huggingface.co/api"
SPACE_NAME = "rolelens"
PORT = 7860  # Hugging Face routes Docker Spaces to app_port (default 7860)

SPACE_README = """---
title: RoleLens
emoji: 🔍
colorFrom: green
colorTo: gray
sdk: docker
app_port: {port}
pinned: false
short_description: See your resume through the lens of any role.
---

# RoleLens — public demo

Grounded Q&A with citations and a per-job fit dashboard over a resume and job descriptions.
This demo uses a **fictional** resume and three sample job descriptions (one contains a
prompt-injection attempt). Uploads are disabled and questions are rate-limited.

Source, setup and design notes: https://github.com/anitakapal25/rolelens
"""

# Files the Space doesn't need (and binaries HF would reject without LFS).
EXCLUDE = ["docs", ".github", "frontend/node_modules"]


def token() -> str:
    value = os.environ.get("HF_TOKEN") or ""
    path = Path.home() / ".cache" / "huggingface" / "token"
    if not value and path.exists():
        value = path.read_text().strip()
    if not value:
        sys.exit("No Hugging Face token: set HF_TOKEN or save it to ~/.cache/huggingface/token")
    return value


def call(method: str, url: str, tok: str, body: dict | None = None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as res:
            raw = res.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:300]
        if exc.code == 409:  # already exists
            return {"exists": True}
        sys.exit(f"Hugging Face API {method} {url} failed: {exc.code} {detail}")


def read_env_keys() -> dict[str, str]:
    keys = {}
    for line in (ROOT / ".env").read_text().splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.split("=", 1)
            if k.strip() in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY") and v.strip():
                keys[k.strip()] = v.strip()
    return keys


def build_bundle(dest: Path) -> None:
    archive = subprocess.run(["git", "-C", str(ROOT), "archive", "HEAD"], check=True, capture_output=True).stdout
    subprocess.run(["tar", "-x", "-C", str(dest)], input=archive, check=True)
    for rel in EXCLUDE:
        shutil.rmtree(dest / rel, ignore_errors=True)
    dockerfile = (dest / "Dockerfile.render").read_text().replace("PORT=10000", f"PORT={PORT}").replace(
        "EXPOSE 10000", f"EXPOSE {PORT}")
    (dest / "Dockerfile").write_text(dockerfile)
    (dest / "README.md").write_text(SPACE_README.format(port=PORT))
    for leftover in ("Dockerfile.render", "render.yaml", "docker-compose.yml"):
        (dest / leftover).unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--secrets", action="store_true", help="set the two API keys from .env as Space secrets")
    args = parser.parse_args()

    tok = token()
    user = call("GET", f"{API}/whoami-v2", tok)["name"]
    repo = f"{user}/{SPACE_NAME}"
    created = call("POST", f"{API}/repos/create", tok,
                   {"type": "space", "name": SPACE_NAME, "sdk": "docker", "private": False})
    print(f"Space {repo}: {'already exists' if created.get('exists') else 'created'}")

    if args.secrets:
        for key, value in read_env_keys().items():
            call("POST", f"{API}/spaces/{repo}/secrets", tok, {"key": key, "value": value})
            print(f"  secret set: {key}")

    with tempfile.TemporaryDirectory() as tmp:
        bundle = Path(tmp)
        build_bundle(bundle)
        sha = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"],
                             check=True, capture_output=True, text=True).stdout.strip()
        git = ["git", "-C", str(bundle), "-c", "user.name=RoleLens deploy", "-c", "user.email=deploy@rolelens.invalid"]
        subprocess.run([*git, "init", "-q", "-b", "main"], check=True)
        subprocess.run([*git, "add", "-A"], check=True)
        subprocess.run([*git, "commit", "-q", "-m", f"Deploy {sha} from GitHub"], check=True)
        remote = f"https://user:{tok}@huggingface.co/spaces/{repo}"
        push = subprocess.run([*git, "push", "-q", "--force", remote, "main"], capture_output=True, text=True)
        if push.returncode != 0:
            sys.exit("git push failed: " + push.stderr.replace(tok, "***")[:500])
    print(f"Pushed {sha}. Build logs: https://huggingface.co/spaces/{repo}?logs=build")
    print(f"App URL (after the build): https://{user.lower()}-{SPACE_NAME}.hf.space")


if __name__ == "__main__":
    main()
