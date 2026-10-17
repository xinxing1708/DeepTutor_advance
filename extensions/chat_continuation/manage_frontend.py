"""Check/apply/restore the runtime frontend without restarting the server."""
import argparse
import hashlib
from importlib.metadata import version
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["check", "status", "apply", "restore"])
    parser.add_argument("--target", type=Path, default=ROOT.parents[1] / "data/user/runtime/web")
    args = parser.parse_args()
    installed = version("deeptutor")
    manifest = json.loads((ROOT / f"frontend-manifest-{installed}.json").read_text(encoding="utf-8"))
    target = args.target.resolve()
    planned = []
    for record in manifest["files"]:
        path = (target / record["path"]).resolve()
        if not path.is_relative_to(target):
            raise ValueError("Patch path escapes target")
        added = record.get("added", False)
        digest = hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None
        states = (["patched"] if added else ["upstream", "patched"]) + (["previous"] if "previous_sha256" in record else [])
        state = "missing" if added and digest is None else next((name for name in states if digest == record[name + "_sha256"]), None)
        if state is None:
            raise ValueError(f"Unknown frontend bytes: {path}")
        for name in states:
            snapshot = ROOT / f"{name}-{installed}" / record.get("snapshot", path.name)
            if hashlib.sha256(snapshot.read_bytes()).hexdigest() != record[name + "_sha256"]:
                raise ValueError(f"Snapshot mismatch: {snapshot}")
        planned.append((path, state, record.get("snapshot", path.name), added))
    for path, state, snapshot, added in planned:
        print(f"{path.name}: {state}")
    if args.action in ["check", "status"]:
        return
    desired = "patched" if args.action == "apply" else "upstream"
    # Validate every input before writing; replace individual files atomically.
    for path, state, snapshot, added in planned:
        file_desired = "patched" if added else desired
        if state == file_desired:
            continue
        staging = path.with_name(path.name + ".continuation-staging")
        staging.write_bytes((ROOT / f"{file_desired}-{installed}" / snapshot).read_bytes())
        os.replace(staging, path)
    print(f"Frontend {args.action} complete; existing browser documents are unchanged")


if __name__ == "__main__":
    main()
