import os
from collections.abc import Iterator
from pathlib import Path
from typing import IO


class Splitter:
    def __init__(
        self, filename: Path, binary: bool = False, buffer_size: int = 0
    ) -> None:
        self.filename = filename
        self.binary = binary
        self.buffer_size = buffer_size or 4096
        self.size = os.stat(filename).st_size

    def _next_pattern_offset(
        self,
        fp: IO,
        pattern: str | bytes,
        max_pattern_length: int | None = None,
        remove_prefix: int = 0,
    ) -> tuple[int, int]:
        """
        Find the offset of the next occurrence of the pattern.
        """
        data = b"" if self.binary else ""
        max_pattern_length = (
            len(pattern) if max_pattern_length is None else max_pattern_length
        )
        first = True
        prefix_length = 0

        while True:
            if chunk := fp.read(self.buffer_size):
                previous_length = len(data)
                start_offset = max(0, previous_length - max_pattern_length)
                data = data[start_offset:] + chunk
                if (match_index := data.find(pattern, start_offset)) > -1:
                    unused = len(data) - match_index
                    if first and remove_prefix:
                        prefix_length = remove_prefix
                    first = False
                    break
            else:
                # EOF
                unused = 0
                break

        return fp.tell() - unused + prefix_length, prefix_length

    def chunks(
        self,
        n_chunks: int | None,
        chunk_size: int | None,
        pattern: str | bytes,
        return_zero_chunk: bool = True,
        max_pattern_length: int | None = None,
        remove_prefix: int = 0,
    ) -> Iterator[tuple[int, int]]:
        """
        Produce offsets into our file at places where the pattern is found.
        """
        if self.binary:
            if not isinstance(pattern, bytes):
                raise ValueError(
                    "The split pattern must be type 'bytes' if you pass "
                    "binary=True to the Splitter initializer."
                )
        else:
            if not isinstance(pattern, str):
                raise ValueError(
                    "The split pattern must be type 'str' if you pass "
                    "binary=False (the default) to the Splitter initializer."
                )

        if n_chunks is None:
            if chunk_size is None:
                raise ValueError(
                    "Either a number of chunks or a chunk size must be given."
                )
        else:
            if chunk_size is not None:
                raise ValueError(
                    "A number of chunks or a chunk size must be given, not both."
                )

            chunk_size = max(self.size // n_chunks, 1)

        offset = 0

        with open(self.filename, "rb" if self.binary else "rt") as fp:
            while fp.tell() < self.size:
                fp.seek(min(self.size, offset + chunk_size), os.SEEK_SET)

                next_offset, next_prefix_length = self._next_pattern_offset(
                    fp, pattern, max_pattern_length, remove_prefix
                )
                length = next_offset - offset - next_prefix_length

                if length:
                    if offset or return_zero_chunk:
                        yield (offset, length)
                    offset = next_offset
                    fp.seek(offset, os.SEEK_SET)
