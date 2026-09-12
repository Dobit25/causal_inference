from __future__ import annotations

import argparse
import hashlib
import os
import urllib.request
from pathlib import Path


COMMIT = "092a8cf13a9b31809d4256fd9aa3c98c52b88002"
SHA256 = "5A3BA56ADECE35DA8A209B39DB8B8BF29D4037FB79ED56C4B63F8D3B4C1A7051"
URL = (
    "https://raw.githubusercontent.com/cmu-phil/py-tetrad/"
    f"{COMMIT}/pytetrad/resources/tetrad-current.jar"
)
DEFAULT_OUTPUT = Path(
    "data/raw/t05/py-tetrad/pytetrad/resources/tetrad-current.jar"
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def fetch(output: Path) -> None:
    output = output.resolve()
    if output.exists():
        actual = sha256(output)
        if actual != SHA256:
            raise ValueError(
                f"Existing file has unexpected hash; not overwriting: {actual}"
            )
        print(f"Pinned Tetrad jar already verified: {output}")
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".part")
    try:
        with urllib.request.urlopen(URL, timeout=120) as response, temporary.open(
            "wb"
        ) as handle:
            while chunk := response.read(1024 * 1024):
                handle.write(chunk)
        actual = sha256(temporary)
        if actual != SHA256:
            raise ValueError(f"Downloaded jar hash mismatch: {actual}")
        os.replace(temporary, output)
    finally:
        if temporary.exists():
            temporary.unlink()
    print(f"Downloaded and verified pinned Tetrad jar: {output}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    fetch(parser.parse_args().output)
