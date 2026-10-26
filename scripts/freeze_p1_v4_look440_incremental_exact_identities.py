"""Registered look-440 successor of the hash-pinned look-360 identity freezer."""
from __future__ import annotations
import hashlib
from pathlib import Path

SOURCE=Path(__file__).with_name('freeze_p1_v4_look360_incremental_exact_identities.py')
EXPECTED='FE882FE1707C957902254F2B2AC35E5DDE1E3109D109D7FEE6180819F2EE614B'
if hashlib.sha256(SOURCE.read_bytes()).hexdigest().upper()!=EXPECTED:
    raise RuntimeError('look-360 identity freezer hash drift')
source=SOURCE.read_text(encoding='utf-8')
source=source.replace('look360','__CURRENT_LOOK__').replace('look320','look400').replace('__CURRENT_LOOK__','look440')
source=source.replace('LOOK360','__CURRENT_LOOK_UPPER__').replace('LOOK320','LOOK400').replace('__CURRENT_LOOK_UPPER__','LOOK440')
for old,new in {
    "ordered_ids[320:360]":"ordered_ids[400:440]",
    "row['first_registered_look']==360":"row['first_registered_look']==440",
    "360 in row['included_in_registered_looks']":"440 in row['included_in_registered_looks']",
    "look-360":"look-440",
    "look-320":"look-400",
    "slice 320–359":"slice 400–439",
    "first 320 scenes":"first 400 scenes",
    "Look-360 materialization":"Look-440 materialization",
    "CONTINUE_TO_LOOK_360":"CONTINUE_TO_LOOK_440",
    "review.get('next_registered_look')==360":"review.get('next_registered_look')==440",
    "exact_360_cumulative":"exact_440_cumulative",
    "no_overlap_with_first_320":"no_overlap_with_first_400",
}.items():
    if old not in source: raise RuntimeError(f'look-440 successor replacement missing: {old}')
    source=source.replace(old,new)
namespace={'__name__':'p1_v4_look440_identity_runtime','__file__':str(Path(__file__).resolve())}
exec(compile(source,str(SOURCE),'exec'),namespace)
if __name__=='__main__':
    raise SystemExit(namespace['main']())
