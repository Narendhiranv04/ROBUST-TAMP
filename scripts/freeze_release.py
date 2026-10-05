"""Record content identity after an intentional release modification (no Git required)."""
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
SKIP={'.git','__pycache__','.pytest_cache','.venv-sim','.venv-inference','runs','validation','builds'}
files={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
       for p in sorted(ROOT.rglob('*')) if p.is_file() and p.name!='release-manifest.json'
       and not any(part in SKIP or part.startswith('.venv') for part in p.relative_to(ROOT).parts)}
(ROOT/'release-manifest.json').write_text(json.dumps({'format':1,'files':files},indent=2)+'\n')
print(f'Recorded {len(files)} files. Subsequent batches use this new content identity.')
