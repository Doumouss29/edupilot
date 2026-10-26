#!/usr/bin/env python3
"""Controlled read-only load probe for EduPilot. Prefer a staging environment.

Examples:
  python3 scripts/load_probe.py --base-url http://127.0.0.1:8000 --path /login --users 1,5,10,20 --requests-per-user 5
  EDUPILOT_TEST_COOKIE='session=...' python3 scripts/load_probe.py --base-url https://recette.example.org --path /people --users 1,5,10 --requests-per-user 10

Production requires --allow-production explicitly, and is capped at 20 workers.
Only GET is used. No account creation, login attempts, or data writes.
"""
import argparse
import concurrent.futures
import os
import statistics
import time
import urllib.error
import urllib.parse
import urllib.request

def probe(url, cookie, timeout):
    req = urllib.request.Request(url, headers={
        "User-Agent": "EduPilot-authorized-load-probe/1.0",
        "Accept": "text/html,application/json",
        **({"Cookie": cookie} if cookie else {}),
    }, method="GET")
    started = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            response.read()
            return response.status, time.monotonic() - started
    except urllib.error.HTTPError as exc:
        exc.close()
        return exc.code, time.monotonic() - started
    except Exception:
        return 0, time.monotonic() - started

def percentile(data, percent):
    if not data:
        return 0
    values = sorted(data)
    index = max(0, int((len(values) - 1) * percent / 100 + .999999))
    return values[index]

def main():
    parser = argparse.ArgumentParser(description="Read-only stepped concurrency test")
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--path", choices=["/health", "/login", "/people", "/planning", "/courses"], default="/login")
    parser.add_argument("--users", default="1,5,10,20", help="Comma-separated concurrent workers")
    parser.add_argument("--requests-per-user", type=int, default=5)
    parser.add_argument("--timeout", type=float, default=12)
    parser.add_argument("--allow-production", action="store_true", help="Explicitly authorize load on edupilot.ci")
    args = parser.parse_args()
    parsed = urllib.parse.urlsplit(args.base_url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        parser.error("Base URL must be HTTP(S)")
    if parsed.hostname in ("edupilot.ci", "www.edupilot.ci") and not args.allow_production:
        parser.error("Use a staging URL; production requires --allow-production")
    try:
        steps = [int(v.strip()) for v in args.users.split(",")]
    except ValueError:
        parser.error("Invalid --users")
    limit = 20 if args.allow_production else 100
    if not steps or any(v < 1 or v > limit for v in steps) or not 1 <= args.requests_per_user <= 100:
        parser.error(f"Workers must be 1..{limit}; requests-per-user must be 1..100")
    cookie = os.environ.get("EDUPILOT_TEST_COOKIE", "")
    if args.path not in ("/health", "/login") and not cookie:
        parser.error("Authenticated endpoint requires EDUPILOT_TEST_COOKIE of a dedicated test account")
    url = urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, args.path, "", ""))
    print("Endpoint:", url)
    print("Users | Requests | Errors | p50(ms) | p95(ms) | Max(ms) | req/s")
    for users in steps:
        began = time.monotonic()
        with concurrent.futures.ThreadPoolExecutor(max_workers=users) as pool:
            results = list(pool.map(lambda _: probe(url, cookie, args.timeout), range(users * args.requests_per_user)))
        duration = max(time.monotonic() - began, .001)
        times = [elapsed * 1000 for _, elapsed in results]
        failures = sum(code != 200 for code, _ in results)
        print(f"{users:5} | {len(results):8} | {failures:6} | {statistics.median(times):7.0f} | {percentile(times,95):7.0f} | {max(times):7.0f} | {len(results)/duration:5.1f}")
        if failures or percentile(times, 95) > 3000:
            print("STOP: failures or p95 above 3 seconds; investigate before increasing concurrency.")
            break

if __name__ == "__main__":
    main()
