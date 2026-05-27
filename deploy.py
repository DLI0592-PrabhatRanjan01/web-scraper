"""
One-click push & deploy script.
Updates token permissions required: Contents (Read & Write), Actions (Read & Write)

Usage:
    python deploy.py                          # Push all files
    python deploy.py --trigger                # Push and trigger the scraper workflow
    python deploy.py --token YOUR_PAT_TOKEN   # Use a different token
"""
YOUR_PAT_TOKEN = "YOUR_TOKEN_HERE"

import urllib.request
import json
import ssl
import base64
import os
import sys
import time

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

# Default config
DEFAULT_TOKEN = YOUR_PAT_TOKEN
OWNER = "DLI0592-PrabhatRanjan01"
REPO = "web-scraper"
BRANCH = "main"

def get_token():
    """Get token from args or default."""
    for i, arg in enumerate(sys.argv):
        if arg == "--token" and i + 1 < len(sys.argv):
            return sys.argv[i + 1]
    return os.environ.get("GITHUB_TOKEN", DEFAULT_TOKEN)

def api_request(endpoint, method="GET", data=None, token=None):
    """Make GitHub API request."""
    url = f"https://api.github.com{endpoint}" if endpoint.startswith("/") else endpoint
    req = urllib.request.Request(url, method=method)
    req.add_header("Authorization", f"Bearer {token or get_token()}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")

    if data:
        req.add_header("Content-Type", "application/json")
        req = urllib.request.Request(url, data=json.dumps(data).encode(), method=method)
        req.add_header("Authorization", f"Bearer {token or get_token()}")
        req.add_header("Accept", "application/vnd.github+json")
        req.add_header("Content-Type", "application/json")
        req.add_header("X-GitHub-Api-Version", "2022-11-28")

    try:
        resp = urllib.request.urlopen(req, context=ctx)
        return json.loads(resp.read()), resp.status
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        try:
            return json.loads(body), e.code
        except:
            return {"error": body}, e.code

def push_file(filepath, message=None, token=None):
    """Push a file via Contents API."""
    with open(filepath, "rb") as f:
        content = base64.b64encode(f.read()).decode()

    url = f"/repos/{OWNER}/{REPO}/contents/{filepath}"

    # Check existing
    existing, status = api_request(url, token=token)
    sha = existing.get("sha") if status == 200 else None

    payload = {
        "message": message or f"Update {filepath}",
        "content": content,
        "branch": BRANCH
    }
    if sha:
        payload["sha"] = sha

    result, status = api_request(url, method="PUT", data=payload, token=token)

    if status in (200, 201):
        print(f"  [OK] {filepath}")
        return True
    else:
        print(f"  [FAIL] {filepath}: {result.get('message', 'unknown error')}")
        return False

def trigger_workflow(token=None):
    """Trigger the scraper GitHub Actions workflow."""
    url = f"/repos/{OWNER}/{REPO}/actions/workflows/scrape.yml/dispatches"
    payload = {
        "ref": BRANCH,
        "inputs": {
            "url": "https://takeuforward.org/strivers-a2z-dsa-course/strivers-a2z-dsa-course-sheet-2",
            "mode": "--auto"
        }
    }
    result, status = api_request(url, method="POST", data=payload, token=token)
    if status == 204:
        print("\n[TRIGGERED] Scraper workflow started!")
        print(f"  View: https://github.com/{OWNER}/{REPO}/actions")
        return True
    else:
        print(f"\n[FAIL] Could not trigger workflow: {result.get('message', status)}")
        return False

def main():
    token = get_token()
    trigger = "--trigger" in sys.argv

    print(f"{'='*60}")
    print(f"  DEPLOY: https://github.com/{OWNER}/{REPO}")
    print(f"{'='*60}")

    # Verify token access
    print("\n[1] Verifying token access...")
    user_data, status = api_request("/user", token=token)
    if status != 200:
        print(f"  [ERROR] Token invalid or expired")
        sys.exit(1)
    print(f"  Authenticated as: {user_data.get('login')}")

    # Check/create repo
    print("\n[2] Checking repository...")
    repo_data, status = api_request(f"/repos/{OWNER}/{REPO}", token=token)
    if status == 404:
        print("  Repo not found, creating...")
        repo_data, status = api_request("/user/repos", method="POST", data={
            "name": REPO,
            "description": "Dynamic Universal Web Scraper - Works with ANY site",
            "public": True,
            "auto_init": True
        }, token=token)
        if status in (200, 201):
            print(f"  Created: {repo_data.get('html_url')}")
            time.sleep(2)
        else:
            print(f"  [ERROR] Cannot create repo: {repo_data.get('message')}")
            print("  Please create it manually at https://github.com/new")
            sys.exit(1)
    else:
        print(f"  Found: {repo_data.get('html_url')}")

    # Push files
    print("\n[3] Pushing files...")
    os.chdir(os.path.dirname(os.path.abspath(__file__)))

    files = [
        "scraper.py",
        "requirements.txt",
        "README.md",
        ".gitignore",
        ".github/workflows/scrape.yml",
    ]

    success = 0
    for f in files:
        if os.path.exists(f):
            if push_file(f, f"Deploy: {f}", token=token):
                success += 1
        else:
            print(f"  [SKIP] {f} (not found)")

    print(f"\n  Pushed {success}/{len(files)} files")

    # Trigger workflow
    if trigger and success > 0:
        print("\n[4] Triggering scraper workflow...")
        trigger_workflow(token=token)
    elif success > 0:
        print(f"\n[INFO] To trigger the scraper workflow, run:")
        print(f"  python deploy.py --trigger")
        print(f"  OR go to: https://github.com/{OWNER}/{REPO}/actions")

    print(f"\n{'='*60}")
    print(f"  DONE! Repo: https://github.com/{OWNER}/{REPO}")
    print(f"{'='*60}")

if __name__ == "__main__":
    main()
