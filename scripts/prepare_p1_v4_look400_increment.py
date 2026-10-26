"""Hash-pinned look-400 successor for materialization and execution planning."""
from __future__ import annotations
import hashlib
from pathlib import Path

SOURCE=Path(__file__).with_name('prepare_p1_v4_look360_increment.py')
EXPECTED='CD76A594B958DB8313675E9723B0C9B091CEF59041984F3776D46F0DDBABFBF8'
if hashlib.sha256(SOURCE.read_bytes()).hexdigest().upper()!=EXPECTED: raise RuntimeError('look-360 preparer hash drift')
source=SOURCE.read_text(encoding='utf-8').replace('look360','look400').replace('LOOK360','LOOK400')
source=source.replace('CONTINUE_TO_LOOK_360','CONTINUE_TO_LOOK_400').replace('look-320 review','look-360 review').replace("'oracle_scenes_separately_bounded':360","'oracle_scenes_separately_bounded':400")
namespace={'__name__':'p1_v4_look400_prepare_runtime','__file__':str(Path(__file__).resolve())}
exec(compile(source,str(SOURCE),'exec'),namespace)
if __name__=='__main__': namespace['main']()
