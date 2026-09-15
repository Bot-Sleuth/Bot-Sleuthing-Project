"""Generate a seven-day Cloud Run schedule and optionally queue it with Ubuntu at."""

import argparse
from collections import Counter
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import random
import re
import shlex
import shutil
import subprocess
import sys


PROJECT = "psychbot-499512"
START_DELAY_MINUTES = 5
OUTPUT_DIRECTORY = Path(__file__).resolve().parent

TARGETS = [
    ("us-central1", "bot-sleuthing-job"),
    ("us-east1", "bot-sleuthing-project"),
    ("us-east4", "bot-sleuthing-project"),
    ("us-east5", "bot-sleuthing-project"),
    ("us-south1", "bot-sleuthing-project"),
    ("us-west1", "bot-sleuthing-project"),
]


def parse_arguments():
    """Read the single optional enqueue flag."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--enqueue", action="store_true", help="Actually submit the triggers to at")
    return parser.parse_args()


def validate_environment(targets, project):
    """Check local tools, atd, and cloud jobs before submitting anything."""
    gcloud = shutil.which("gcloud")
    at = shutil.which("at")
    if not gcloud or not at:
        raise RuntimeError("Install gcloud and at before using --enqueue")
    active = subprocess.run(["systemctl", "is-active", "--quiet", "atd"], check=False)
    if active.returncode:
        raise RuntimeError("atd is not active. Run sudo systemctl enable --now atd")
    for region, job in targets:
        subprocess.run([gcloud, "run", "jobs", "describe", job,
                        "--region", region, "--project", project,
                        "--format=value(name)"], check=True, stdout=subprocess.DEVNULL)
    return gcloud, at


def generate_schedule(targets, start, project, rng=None):
    """Pick 275 random minutes across seven days with balanced region counts."""
    rng = rng if rng is not None else random.Random()
    targets = list(targets)
    rng.shuffle(targets)
    assignments = [target for index, target in enumerate(targets)
                   for _ in range(45 if index == 5 else 46)]
    rng.shuffle(assignments)
    runs = []
    for index, (region, job) in enumerate(assignments):
        # Disjoint windows distribute requests throughout the 10,080-minute week.
        minute = rng.randrange(index * 10080 // 275, (index + 1) * 10080 // 275)
        scheduled = start + timedelta(minutes=minute)
        runs.append({"time_utc": scheduled.isoformat(), "region": region,
                     "job": job, "at_id": None})
    return {"project": project, "start_utc": start.isoformat(),
            "end_utc": (start + timedelta(days=7)).isoformat(),
            "status": "preview", "runs": runs}


def save_manifest(manifest, output):
    """Replace the manifest atomically so progress survives interruption."""
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(json.dumps(manifest, indent=2) + "\n")
    temporary.replace(output)


def build_trigger_command(run, project, gcloud, log):
    """Build a shell-quoted cloud execution request with per-trigger logging."""
    command = shlex.join([gcloud, "run", "jobs", "execute", run["job"],
                          "--region", run["region"], "--project", project,
                          "--async", "--quiet"])
    return f"{command} >> {shlex.quote(str(log))} 2>&1\n"


def submit_trigger(run, command, at):
    """Queue one request in UTC and return its at queue ID."""
    scheduled = datetime.fromisoformat(run["time_utc"])
    if scheduled <= datetime.now(timezone.utc):
        raise RuntimeError("A scheduled time has passed; increase START_DELAY_MINUTES before scheduling again")
    result = subprocess.run([at, "-t", scheduled.strftime("%Y%m%d%H%M")],
                            input=command, text=True, capture_output=True,
                            env={**os.environ, "TZ": "UTC", "LC_ALL": "C"})
    match = re.search(r"job\s+(\d+)\s+at", result.stderr + result.stdout)
    if result.returncode or not match:
        raise RuntimeError(f"at submission failed or returned an unrecognized ID: {result.stderr}")
    return int(match.group(1))


def enqueue_schedule(manifest, output, gcloud, at):
    """Queue requests while recording IDs and preserving partial progress."""
    manifest["status"] = "queuing"
    save_manifest(manifest, output)
    try:
        for index, run in enumerate(manifest["runs"]):
            log = output.parent / f"{output.stem}-run-{index + 1:03d}.log"
            command = build_trigger_command(run, manifest["project"], gcloud, log)
            run["at_id"] = submit_trigger(run, command, at)
            save_manifest(manifest, output)
    except (Exception, KeyboardInterrupt):
        manifest["status"] = "partial; inspect atq before retrying"
        save_manifest(manifest, output)
        print(f"Stopped. Existing triggers remain queued; IDs are saved in {output}.", file=sys.stderr)
        raise
    manifest["status"] = "queued"
    save_manifest(manifest, output)
    print("Queued all 275 triggers. Use atq to inspect them; atrm ID to cancel one.")


def main():
    args = parse_arguments()

    output = OUTPUT_DIRECTORY / ("weekly-queued.json" if args.enqueue else "weekly-preview.json")
    if args.enqueue and output.exists():
        raise RuntimeError(f"Schedule already exists: {output}. Inspect its IDs and atq before archiving it to schedule another week.")
    if args.enqueue:
        gcloud, at = validate_environment(TARGETS, PROJECT)
    # Start the delay after cloud validation, which may take some time.
    start = (datetime.now(timezone.utc) + timedelta(minutes=START_DELAY_MINUTES)).replace(second=0, microsecond=0)
    manifest = generate_schedule(TARGETS, start, PROJECT)
    save_manifest(manifest, output)
    print("Regional totals:", dict(Counter(run["region"] for run in manifest["runs"])))
    print(f"Schedule: {output}")
    if args.enqueue:
        enqueue_schedule(manifest, output, gcloud, at)
    else:
        print("Preview only. Run again with --enqueue to generate and queue a new schedule.")


if __name__ == "__main__":
    main()
