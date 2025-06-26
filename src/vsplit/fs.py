import os
from pathlib import Path

_DEFAULT = 4096


def block_size(path: Path = Path(".")) -> int:
    """
    Get the optimal I/O block size for the filesystem on which 'path' resides.
    """
    st = os.stat(path)
    return getattr(st, "st_blksize", _DEFAULT)
