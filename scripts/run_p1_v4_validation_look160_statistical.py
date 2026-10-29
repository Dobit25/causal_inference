"""Run the frozen P1V4 statistical implementation on validation look 160."""
from pathlib import Path
import hashlib
import sys
import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / 'configs/p1_v4_validation_look160_statistical_execution.yaml'
cfg = yaml.safe_load(CONFIG.read_text(encoding='utf-8'))
for name, spec in cfg['parents'].items():
    path = ROOT / spec['path']
    if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest().upper() != spec['sha256']:
        raise RuntimeError(f'pinned parent drift: {name}')
source = ROOT / cfg['parents']['frozen_statistical_runner']['path']
body = source.read_text(encoding='utf-8')
if body.count('8240') != 6:
    raise RuntimeError(f'unexpected frozen runner job-count sites: {body.count("8240")}')
body = body.replace('8240', '32960')
namespace = {'__name__':'p1_v4_validation_look160_statistical_runtime', '__file__':str(Path(__file__).resolve())}
exec(compile(body, str(source), 'exec'), namespace)
namespace.update({
    'PLAN': ROOT / cfg['scope']['plan'],
    'AUTH': ROOT / cfg['scope']['authorization'],
    'MAT': ROOT / cfg['parents']['materialization_manifest']['path'],
    'OUT': ROOT / cfg['scope']['output_root'],
    'AUD': ROOT / cfg['scope']['final_audit'],
})
if __name__ == '__main__':
    namespace['main']()
