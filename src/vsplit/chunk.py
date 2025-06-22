from __future__ import annotations

import io
import os
from pathlib import Path
from shlex import quote
from typing import IO, Any

from vsplit.vars import (
    VSPLIT_CHUNK_OFFSETS_FILENAME_VAR,
    VSPLIT_FILENAME_VAR,
    VSPLIT_INDEX_VAR,
    VSPLIT_LENGTH_VAR,
    VSPLIT_N_CHUNKS_VAR,
    VSPLIT_OFFSET_VAR,
)


class FileChunk(io.IOBase):
    """
    A file-like object that provides access to a section of a file.

    Adapted from code originally written by https://claude.ai.
    """

    def __init__(
        self,
        filename: str | Path,
        offset: int,
        length: int,
        binary: bool = False,
    ):
        self.filename = filename
        self.offset = offset
        self.length = length
        self.binary = binary
        self._file: IO[Any] | None = None
        self._position = 0

    def __enter__(self) -> FileChunk:
        self.open()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    def open(self) -> None:
        if self._file is None:
            self._file = open(self.filename, "rb" if self.binary else "rt")
            assert self._file is not None
            self._file.seek(self.offset)

    def close(self) -> None:
        if self._file:
            self._file.close()
            self._file = None

    @property
    def closed(self):
        return self._file is None

    def readable(self):
        return True

    def seekable(self):
        return True

    def writable(self):
        return False

    def read(self, size: int = -1) -> str | bytes:
        """Read up to size bytes from the section."""
        if self._file is None:
            self.open()

        assert self._file is not None

        if size == -1:
            size = self.length - self._position
        else:
            size = min(size, self.length - self._position)

        if size <= 0:
            return b"" if self.binary else ""

        # Ensure we're at the right position in the actual file (I'm not sure this is
        # needed.)
        self._file.seek(self.offset + self._position)

        data = self._file.read(size)
        self._position += len(data)

        return data

    def readline(self, size: int = -1, /) -> str | bytes:
        """Read a line from the section."""
        if self._file is None:
            self.open()

        assert self._file

        if size == -1:
            size = self.length - self._position
        else:
            size = min(size, self.length - self._position)

        if size <= 0:
            return b"" if self.binary else ""

        self._file.seek(self.offset + self._position)

        # Read byte-by-byte until newline or size limit
        if self.binary:
            line = b""
            newline = b"\n"
        else:
            line = ""
            newline = "\n"

        for _ in range(size):
            byte = self._file.read(1)
            if not byte:
                break
            line += byte
            self._position += 1
            if byte == newline:
                break

        return line

    def readlines(self, hint: int = -1, /) -> list[str | bytes]:
        """
        Read all lines from the chunk.
        """
        lines = []
        total_read = 0
        while True:
            line = self.readline()
            if not line:
                break
            lines.append(line)
            total_read += len(line)
            if hint != -1 and total_read >= hint:
                break
        return lines

    def seek(self, offset: int, whence: int = os.SEEK_SET, /) -> int:
        """
        Seek to a position within the chunk.
        """
        if whence == os.SEEK_SET:
            new_pos = offset
        elif whence == os.SEEK_CUR:
            new_pos = self._position + offset
        elif whence == os.SEEK_END:
            new_pos = self.length + offset
        else:
            raise ValueError("Invalid whence value")

        # Clamp to section boundaries
        self._position = max(0, min(new_pos, self.length))
        return self._position

    def tell(self) -> int:
        """
        Return current position within the chunk.
        """
        return self._position

    def __iter__(self, /) -> FileChunk:
        """
        Iterate over lines in the section.
        """
        return self

    def __next__(self, /) -> str | bytes:
        """
        Get the next line from the chunk.
        """
        if not (line := self.readline()):
            raise StopIteration
        return line


def _chunk_from_env(binary: bool = False) -> FileChunk:
    """
    Helper function to prepare to read a chunk from a file based on
    environment variables.
    """
    values = []

    for var in VSPLIT_FILENAME_VAR, VSPLIT_OFFSET_VAR, VSPLIT_LENGTH_VAR:
        try:
            values.append(os.environ[var])
        except KeyError as err:
            raise KeyError(f"Variable {var} is not set in the environment!") from err

    filename, offset, length = Path(values[0]), int(values[1]), int(values[2])

    return FileChunk(filename, offset, length, binary)


def _chunk_from_slurm_env(chunk_index: int, binary: bool = False) -> FileChunk:
    """
    Helper function to prepare to read a chunk from a file based on
    environment variables including the SLURM_ARRAY_TASK_ID.
    """
    values = []

    for var in (
        VSPLIT_FILENAME_VAR,
        VSPLIT_CHUNK_OFFSETS_FILENAME_VAR,
    ):
        try:
            values.append(os.environ[var])
        except KeyError as err:
            raise KeyError(f"Variable {var} is not set in the environment!") from err

    filename, chunks_file = map(Path, values)

    with open(chunks_file) as fp:
        index = 0
        for index, line in enumerate(fp):
            if index == chunk_index:
                offset, length = map(int, line.strip().split())
                break
        else:
            raise ValueError(
                f"Could not find offset and length for chunk {chunk_index + 1} in "
                f"{str(chunks_file)!r}. The file only contains {index + 1} lines."
            )

    return FileChunk(filename, offset, length, binary)


def chunk_from_env(binary: bool = False) -> FileChunk:
    try:
        chunk_index = int(os.environ["SLURM_ARRAY_TASK_ID"])
    except KeyError:
        return _chunk_from_env(binary)
    else:
        return _chunk_from_slurm_env(chunk_index, binary)


def env_str(
    filename: Path,
    n_chunks: int,
    chunk_offsets_filename: Path,
    index: int | None = None,
    length: int | None = None,
    offset: int | None = None,
) -> str:
    """
    Produce a /usr/bin/env string that can be used by a program to retrieve a chunk
    from a file based on environment variables.
    """
    result = [
        "env",
        f"{VSPLIT_FILENAME_VAR}={quote(str(filename))}",
        f"{VSPLIT_N_CHUNKS_VAR}={n_chunks}",
        f"{VSPLIT_CHUNK_OFFSETS_FILENAME_VAR}={quote(str(chunk_offsets_filename))}",
    ]

    if index is not None:
        result.append(f"{VSPLIT_INDEX_VAR}={index}")

    if length is not None:
        result.append(f"{VSPLIT_LENGTH_VAR}={length}")

    if offset is not None:
        result.append(f"{VSPLIT_OFFSET_VAR}={offset}")

    return " ".join(result)


def expand_command(
    command: str,
    filename: Path,
    n_chunks: int,
    chunk_offsets_filename: Path,
    allow_single_chunk_variables: bool = True,
    index: int | None = None,
    length: int | None = None,
    offset: int | None = None,
) -> str:
    """
    Replace %-style command markers by specific values for a chunk and the
    file it came from.
    """
    width = len(str(n_chunks))

    values = {
        "F": quote(str(filename)),
        "I": index,
        "0I": "" if index is None else f"{index:0{width}d}",
        "L": length,
        "N": n_chunks,
        "O": offset,
        "C": quote(str(chunk_offsets_filename)),
    }

    single_chunk_symbols = "I", "0I", "L", "O"
    multi_chunk_symbols = "F", "N", "C"

    def format_symbol(s: str) -> str:
        return f"[{s}]"

    if allow_single_chunk_variables:
        symbols = single_chunk_symbols + multi_chunk_symbols
    else:
        # Check that the command doesn't seem to contain the variables that
        # are only supported when we are dealing with a command to process a
        # single chunk (as opposed to a SLURM array command which has just one
        # command and figures out its chunk based on the VSPLIT_CHUNK_INDEX
        # environment variable).
        for symbol in map(format_symbol, single_chunk_symbols):
            if symbol in command:
                raise ValueError(
                    f"The per-chunk command-line symbol {symbol!r} makes no sense in "
                    f"a command ({command}) when all chunks are being processed in a "
                    "SLURM job array using a single command (in which case the script "
                    "being run needs to get its chunk via environment variables not "
                    "from the command line)."
                )

        symbols = multi_chunk_symbols

    for symbol in symbols:
        command = command.replace(format_symbol(symbol), str(values[symbol]))

    return command
