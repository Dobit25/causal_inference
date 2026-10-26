"""Hash-pinned look-440 successor of the audited look-360 rescorer."""
from __future__ import annotations
import hashlib
from pathlib import Path

SOURCE = Path(__file__).with_name("freeze_and_rescore_p1_v4_look360_incremental.py")
EXPECTED_SOURCE_SHA256 = "9B9D192D4247D767FE048B15EDB3E837386B5F345EBE04C06D8AD62924B008F1"
if hashlib.sha256(SOURCE.read_bytes()).hexdigest().upper() != EXPECTED_SOURCE_SHA256:
    raise RuntimeError("look-360 rescorer hash drift")
source = SOURCE.read_text(encoding="utf-8")
source = source.replace("look-360", "look-440").replace("look360", "look440")
namespace = {"__name__": "p1_v4_look440_rescore_runtime", "__file__": str(Path(__file__).resolve())}
exec(compile(source, str(SOURCE), "exec"), namespace)
if __name__ == "__main__":
    namespace["main"]()
