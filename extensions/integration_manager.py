"""Manage reviewed, version-specific DeepTutor host integration snapshots.

A matching snapshot must be prepared by hand for every upstream release. This
module only detects exact bytes and copies reviewed files; it does not port code.
"""

import argparse
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import shutil


class IntegrationError(RuntimeError):
    """The installed files or reviewed snapshot are not safe to change."""


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(root: Path, target: Path, release: str, action: str) -> dict[str, str]:
    if action not in {"status", "check", "apply", "restore"}:
        raise ValueError(f"Unknown action: {action}")
    root, target = Path(root), Path(target)
    manifest_path = root / f"integration-manifest-{release}.json"
    if not manifest_path.is_file():
        available = ", ".join(
            sorted(p.stem.removeprefix("integration-manifest-")
                   for p in root.glob("integration-manifest-*.json"))
        ) or "none"
        raise IntegrationError(
            f"No reviewed snapshot for DeepTutor {release}; available: {available}. "
            "Port the patch before applying it to a new version."
        )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    states: dict[str, str] = {}
    operations: list[tuple[Path | None, Path]] = []
    for relative, hashes in manifest.items():
        rel = Path(relative)
        if rel.is_absolute() or ".." in rel.parts or not rel.parts:
            raise IntegrationError(f"Invalid snapshot path: {relative}")
        path = target / rel
        if path.is_symlink():
            raise IntegrationError(f"Refusing symlink target: {relative}")
        original, patched = hashes["original"], hashes["patched"]
        if not path.exists():
            state = "original" if original is None else "unknown"
        else:
            current = digest(path)
            if current == patched:
                state = "patched"
            elif original is not None and current == original:
                state = "original"
            else:
                state = "unknown"
        states[relative] = state
        print(f"{state}: {relative}")
        if action != "status" and state == "unknown":
            raise IntegrationError(f"Unrecognized changes in {relative}; no files modified.")
        if action == "status":
            continue
        for kind, expected in (("upstream", original), ("patched", patched)):
            source = root / f"{kind}-{release}" / rel
            if expected is None:
                if source.exists():
                    raise IntegrationError(f"Unexpected upstream snapshot for {relative}; no files modified.")
            elif not source.is_file() or digest(source) != expected:
                raise IntegrationError(f"Backup verification failed: {relative}; no files modified.")
        desired = "original" if action == "restore" else "patched"
        if action in {"apply", "restore"} and state != desired:
            source = None if desired == "original" and original is None else root / f"{'upstream' if desired == 'original' else 'patched'}-{release}" / rel
            operations.append((source, path))
    for source, path in operations:
        if source is None:
            path.unlink()
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, path)
    print(f"Checked {len(states)} files; updated {len(operations)}. Restart DeepTutor after changes.")
    return states


def main(root: Path) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["status", "check", "apply", "restore"])
    parser.add_argument("--target", type=Path, help="Alternative package root for an offline check")
    args = parser.parse_args()
    import deeptutor
    target = args.target if args.target else Path(deeptutor.__file__).parent
    try:
        run(root, target, version("deeptutor"), args.action)
    except IntegrationError as exc:
        raise SystemExit(str(exc)) from exc
