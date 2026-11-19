"""Throttled dispatcher for lab dataset runs (lab-dataset.yml) on this fork.

Dispatches one workflow run per upstream commit from a queue file, keeping at most
--parallel runs busy, where a run counts as busy while queued, in progress, or within
--cooldown seconds after it completed. Stateless: every pass reads the run list from
GitHub. A queue line `# since: <ISO time>` makes only runs created after that time count
as done, so a queue can repeat commits that already ran.

    python lab/driver.py --repo tarpas/coredis-lab --queue lab/queue.txt          # loop
    python lab/driver.py --repo tarpas/coredis-lab --queue lab/queue.txt --once   # one pass

The scheduled workflow lab-driver.yml (on the default branch) runs one pass every 10
minutes. Auth: GITHUB_TOKEN (needs actions: write). Standard library only.
"""

import argparse
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

API = "https://api.github.com"


def request(method, path, params=None, body=None):
    url = f"{API}{path}" + (f"?{urllib.parse.urlencode(params)}" if params else "")
    req = urllib.request.Request(url, method=method, data=json.dumps(body).encode() if body else None)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    if token := os.environ.get("GITHUB_TOKEN"):
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=60) as r:
        data = r.read()
    return json.loads(data) if data else None


def parse_ts(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def read_queue(path):
    shas, since = [], None
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line.startswith("# since:"):
                since = parse_ts(line.split(":", 1)[1].strip())
            elif line and not line.startswith("#"):
                shas.append(line.split()[0])
    return shas, since


def list_runs(repo, workflow, created_after):
    runs, page = [], 1
    while True:
        batch = request("GET", f"/repos/{repo}/actions/workflows/{workflow}/runs", {
            "per_page": 100, "page": page,
            "created": ">=" + created_after.strftime("%Y-%m-%dT%H:%M:%SZ"),
        })["workflow_runs"]
        runs += batch
        if len(batch) < 100:
            return runs
        page += 1


def state(runs, since, cooldown):
    now = datetime.now(timezone.utc)
    started, busy = set(), 0
    for run in runs:  # every run of the workflow occupies a slot, however started
        title = run.get("display_title", "")
        if title.startswith("lab ") and (since is None or parse_ts(run["created_at"]) >= since):
            started.add(title[4:])
        if run["status"] != "completed" or (now - parse_ts(run["updated_at"])).total_seconds() < cooldown:
            busy += 1
    return started, busy


def one_pass(args):
    shas, since = read_queue(args.queue)
    window = datetime.now(timezone.utc) - timedelta(days=2)
    runs = list_runs(args.repo, args.workflow, min(since, window) if since else datetime(2020, 1, 1, tzinfo=timezone.utc))
    started, busy = state(runs, since, args.cooldown)
    pending = [s for s in shas if s not in started]
    stamp = datetime.now().strftime("%H:%M:%S")
    print(f"{stamp} started {len(shas) - len(pending)}/{len(shas)}, busy {busy}", flush=True)
    while pending and busy < args.parallel:
        sha = pending.pop(0)
        print(f"{stamp} dispatch {sha}", flush=True)
        if not args.dry_run:
            request("POST", f"/repos/{args.repo}/actions/workflows/{args.workflow}/dispatches",
                    body={"ref": args.ref, "inputs": {"sha": sha}})
        busy += 1
    return not pending and busy == 0


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--repo", required=True, help="owner/name of the fork")
    p.add_argument("--queue", required=True, help="file, one upstream sha per line")
    p.add_argument("--workflow", default="lab-dataset.yml")
    p.add_argument("--ref", default="lab/dataset")
    p.add_argument("--parallel", type=int, default=2)
    p.add_argument("--cooldown", type=int, default=600, help="seconds after a run ends")
    p.add_argument("--poll", type=int, default=60)
    p.add_argument("--once", action="store_true", help="one pass, then exit")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args(argv)
    while True:
        if one_pass(args):
            print("queue done")
            return 0
        if args.once:
            return 0
        time.sleep(args.poll)


if __name__ == "__main__":
    sys.exit(main())
