"""Run the hash-pinned P1V4 statistical implementation on 80 new scenes."""
from pathlib import Path
import hashlib
import json
import sys

import yaml

ROOT=Path(__file__).resolve().parents[1]
CONFIG=ROOT/'configs/p1_v4_partial_high_supplemental80_statistical_execution.yaml'
cfg=yaml.safe_load(CONFIG.read_text(encoding='utf-8'))
source=ROOT/cfg['parents']['frozen_statistical_runner']['path']
if hashlib.sha256(source.read_bytes()).hexdigest().upper()!=cfg['parents']['frozen_statistical_runner']['sha256']:
    raise RuntimeError('frozen P1V4 statistical runner hash drift')
body=source.read_text(encoding='utf-8')
if body.count('8240')!=6:
    raise RuntimeError(f'unexpected frozen runner job-count sites: {body.count("8240")}')
body=body.replace('8240','16480')
namespace={'__name__':'p1_v4_supplemental80_statistical_runtime','__file__':str(Path(__file__).resolve())}
exec(compile(body,str(source),'exec'),namespace)
namespace.update({
    'PLAN':ROOT/cfg['scope']['plan'],
    'AUTH':ROOT/cfg['scope']['authorization'],
    'MAT':ROOT/cfg['parents']['materialization_manifest']['path'],
    'OUT':ROOT/cfg['scope']['output_root'],
    'AUD':ROOT/cfg['scope']['final_audit'],
})
if __name__=='__main__':namespace['main']()
