"""Apply the reviewed quiz fix and compose the two shared PDF host files."""
from pathlib import Path
import argparse
import hashlib
from importlib.metadata import version
import json
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent))
from integration_manager import run, IntegrationError

SHARED = ('tools/builtin/__init__.py', 'services/session/turns/executor.py')


def compose_pdf(action: str, release: str, *, write: bool = False):
    pdf = ROOT.parent / 'pdf_ocr'
    manifest_path = pdf / f'integration-manifest-{release}.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    before = json.loads((ROOT / 'pdf-integration-before' / manifest_path.name).read_text(encoding='utf-8'))
    quiz = json.loads((ROOT / f'integration-manifest-{release}.json').read_text(encoding='utf-8'))
    for relative in SHARED:
        snapshot = pdf / f'patched-{release}' / relative
        digest = hashlib.sha256(snapshot.read_bytes()).hexdigest()
        accepted = (before[relative]['patched'], quiz[relative]['patched'])
        if digest not in accepted or manifest[relative]['patched'] != digest:
            raise IntegrationError(f'PDF integration has unreviewed changes: {relative}')
    if not write:
        return
    flavor = 'upstream' if action == 'restore' else 'patched'
    for relative in SHARED:
        data = (ROOT / f'{flavor}-{release}' / relative).read_bytes()
        (pdf / f'patched-{release}' / relative).write_bytes(data)
        manifest[relative]['patched'] = hashlib.sha256(data).hexdigest()
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('status', 'check', 'apply', 'restore'))
    parser.add_argument('--target', type=Path)
    args = parser.parse_args()
    release = version('deeptutor')
    import deeptutor
    installed = Path(deeptutor.__file__).parent.resolve()
    target = args.target.resolve() if args.target else installed
    try:
        if target == installed:
            compose_pdf(args.action, release)
        run(ROOT, target, release, args.action)
        if target == installed and args.action in ('apply', 'restore'):
            compose_pdf(args.action, release, write=True)
    except IntegrationError as exc:
        raise SystemExit(str(exc)) from exc


if __name__ == '__main__':
    main()
