"""Utilities for reproducible experiment execution."""

from __future__ import annotations

import os
import random


def set_seed(seed: int) -> None:
    """Seed Python and NumPy, when NumPy is installed.

    PYTHONHASHSEED is also exported for child Python processes. Hash
    randomization for the current interpreter is fixed at process startup.
    """
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise TypeError("seed must be an integer")

    os.environ["PYTHONHASHSEED"] = str(seed)
    random.seed(seed)

    try:
        import numpy as np
    except ImportError:
        return

    np.random.seed(seed)

