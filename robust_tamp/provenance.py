"""Content identity for an archive with no Git history."""
import hashlib
import json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]

def identity(root=ROOT):
    manifest = root / 'release-manifest.json'
    if not manifest.exists():
        return {'commit': None, 'dirty': None, 'provenance': 'missing release-manifest.json'}
    files = json.loads(manifest.read_text())['files']
    changed = [name for name, sha in files.items() if not (root/name).is_file()
               or hashlib.sha256((root/name).read_bytes()).hexdigest() != sha]
    for path in root.rglob('*.py'):
        rel=path.relative_to(root)
        if any(part in {'runs','validation','builds','__pycache__'} or part.startswith('.venv') for part in rel.parts):
            continue
        if str(rel) not in files: changed.append(str(rel))
    return {'commit': 'release-sha256:' + hashlib.sha256(manifest.read_bytes()).hexdigest(),
            'dirty': bool(changed), 'changed_files': changed, 'provenance': 'content manifest; no version history'}
