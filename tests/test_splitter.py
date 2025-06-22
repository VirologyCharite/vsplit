import os
from collections.abc import Callable
from pathlib import Path

import pytest

from vsplit.splitter import Splitter

from .data import data_factory  # noqa: F401


def chunk_from_file(
    filename: Path,
    offset: int,
    length: int,
    binary: bool = False,
) -> str | bytes:
    """
    Read a chunk of data from a file.
    """
    with open(filename, "rb" if binary else "rt") as fp:
        fp.seek(offset, os.SEEK_SET)
        return fp.read(length)


class Test_Basics:
    """
    Tests for basic Splitter functionality.
    """

    def test_size_zero(self, data_factory: Callable[[str | bytes], Path]):  # noqa: F811
        """
        The Splitter class should have a 'size' attribute that is zero when there is
        no data in the file.
        """
        filename = data_factory("")
        s = Splitter(filename)
        assert s.size == 0

    def test_size(self, data_factory: Callable[[str | bytes], Path]):  # noqa: F811
        """
        A Splitter should have a 'size' attribute holding the length of the file data.
        """
        data = "The data"
        filename = data_factory(data)
        s = Splitter(filename)
        assert s.size == len(data)


class Test_Chunks_By_Number_Of_Chunks:
    """
    Tests for the Splitter.chunks method when called with a number of chunks (as
    opposed to calling it with a chunk size).
    """

    @pytest.mark.parametrize("n_chunks", (2, 3, 10, 100))
    def test_missing_pattern(
        self,
        data_factory: Callable[[str | bytes], Path],  # noqa: F811
        n_chunks: int,
    ):
        """
        Test that when the pattern the data file is split on is missing we get one
        chunk back that spans the whole file.
        """
        pattern = "missing"
        data = "The data"
        filename = data_factory(data)

        s = Splitter(filename)

        chunks = list(s.chunks(n_chunks, None, pattern))
        assert chunks == [(0, len(data))]

        offset, length = chunks[0]
        assert chunk_from_file(filename, offset, length) == data

    def test_pattern_too_early(self, data_factory: Callable[[str | bytes], Path]):  # noqa: F811
        """
        Test that when the pattern the data file is split on appears early in the
        file that it is missed when two chunks are requested.
        """
        pattern = "xxx"
        data = "The pattern xxx is at the start of this string."
        filename = data_factory(data)

        s = Splitter(filename)

        chunks = list(s.chunks(2, None, pattern))
        assert chunks == [(0, len(data))]

        offset, length = chunks[0]
        assert chunk_from_file(filename, offset, length) == data

    @pytest.mark.parametrize("n_chunks", (2, 3, 10, 100))
    def test_one_pattern(
        self,
        data_factory: Callable[[str | bytes], Path],  # noqa: F811
        n_chunks: int,
    ):
        """
        Test that when the pattern the data file is split on appears late in the
        file that it is found when two or more chunks are requested.
        """
        pattern = "this"
        data_1 = "The pattern is at the end of "
        data_2 = "this string."
        data = data_1 + data_2
        filename = data_factory(data)

        s = Splitter(filename)

        chunks = list(s.chunks(n_chunks, None, pattern))
        assert chunks == [(0, len(data_1)), (len(data_1), len(data_2))]

        for (offset, length), data in zip(chunks, (data_1, data_2)):
            assert chunk_from_file(filename, offset, length) == data

    def test_one_pattern_one_chunk(self, data_factory: Callable[[str | bytes], Path]):  # noqa: F811
        """
        Test that when the pattern the data file is split on appears in the
        file that it is not found when one chunk is requested.
        """
        pattern = "this"
        data_1 = "The pattern is at the end of "
        data_2 = "this string."
        data = data_1 + data_2
        filename = data_factory(data)

        s = Splitter(filename)

        chunks = list(s.chunks(1, None, pattern))
        assert chunks == [(0, len(data))]

        offset, length = chunks[0]
        assert chunk_from_file(filename, offset, length) == data

    def test_one_pattern_one_chunk_no_zero_chunk(
        self,
        data_factory: Callable[[str | bytes], Path],  # noqa: F811
    ):
        """
        Test that when the pattern the data file is split on appears in the
        file that it is not found when one chunk is requested, and if return_zero_chunk
        is True then no results are returned.
        """
        pattern = "this"
        data = "The pattern is at the end of this string."
        filename = data_factory(data)

        s = Splitter(filename)

        chunks = list(s.chunks(1, None, pattern, return_zero_chunk=False))
        assert chunks == []

    def test_fasta_str(self, data_factory: Callable[[str | bytes], Path]):  # noqa: F811
        """
        Test that several FASTA str sequences can be found.
        """
        pattern = ">"
        data_1 = ">id1\nACTG\n"
        data_2 = ">id2\nGGGGG\n"
        data = data_1 + data_2
        filename = data_factory(data)

        s = Splitter(filename)

        chunks = list(s.chunks(2, None, pattern, return_zero_chunk=True))
        assert chunks == [(0, len(data_1)), (len(data_1), len(data_2))]

        for (offset, length), data in zip(chunks, (data_1, data_2)):
            assert chunk_from_file(filename, offset, length) == data

    def test_fasta_bytes(self, data_factory: Callable[[str | bytes], Path]):  # noqa: F811
        """
        Test that several FASTA bytes sequences can be found.
        """
        pattern = b">"
        data_1 = b">id1\nACTG\n"
        data_2 = b">id2\nGGGGG\n"
        data = data_1 + data_2
        filename = data_factory(data)

        s = Splitter(filename, binary=True)

        chunks = list(s.chunks(2, None, pattern, return_zero_chunk=True))
        assert chunks == [(0, len(data_1)), (len(data_1), len(data_2))]

        for (offset, length), data in zip(chunks, (data_1, data_2)):
            assert chunk_from_file(filename, offset, length, binary=True) == data

    def test_fasta_newline_plus_id_bytes(
        self,
        data_factory: Callable[[str | bytes], Path],  # noqa: F811
    ):
        """
        Test that several FASTA bytes sequences can be found when the pattern
        is a newline followed by a >.
        """
        pattern = b"\n>"
        data_1 = b">id1\nACTGCCCCC"
        data_2 = b"\n>id2\nGGGGG\n"
        data = data_1 + data_2
        filename = data_factory(data)

        s = Splitter(filename, binary=True)

        chunks = list(s.chunks(2, None, pattern, return_zero_chunk=True))
        assert chunks == [(0, len(data_1)), (len(data_1), len(data_2))]

        for (offset, length), data in zip(chunks, (data_1, data_2)):
            assert chunk_from_file(filename, offset, length, binary=True) == data

    @pytest.mark.parametrize("n_chunks", (2, 10, 100))
    def test_fasta_newline_plus_id_ignore_newline_str(
        self,
        data_factory: Callable[[str | bytes], Path],  # noqa: F811
        n_chunks: int,
    ):
        """
        Test that several FASTA bytes sequences can be found when the pattern
        is a newline followed by a > and the newline should not be returned.
        """
        pattern = "\n>"
        data_1 = ">id1\nACTGCCCCC"
        data_2 = ">id2\nGGGGG\n"
        data = data_1 + "\n" + data_2
        filename = data_factory(data)

        s = Splitter(filename)

        chunks = list(s.chunks(n_chunks, None, pattern, remove_prefix=1))
        assert chunks == [(0, len(data_1)), (len(data_1) + 1, len(data_2))]

        for (offset, length), data in zip(chunks, (data_1, data_2)):
            assert chunk_from_file(filename, offset, length) == data

    @pytest.mark.parametrize("n_chunks", (4, 10, 100))
    def test_fasta_newline_plus_id_ignore_newline_bytes(
        self,
        data_factory: Callable[[str | bytes], Path],  # noqa: F811
        n_chunks: int,
    ):
        """
        Test that several FASTA bytes sequences can be found when the pattern
        is a newline followed by a > and the newline that is part of the split
        pattern should not be returned.

        Note that the results depend on the requested number of chunks. If the value
        is less than four only two chunks will be found.
        """
        pattern = b"\n>"
        data_1 = b">id1\nACTGCCCCC"
        data_2 = b">id2\nGGGGG"
        data_3 = b">id3\nCCCC"
        data = b"\n".join((data_1, data_2, data_3))
        filename = data_factory(data)

        s = Splitter(filename, binary=True)

        chunks = list(s.chunks(n_chunks, None, pattern, remove_prefix=1))

        assert chunks == [
            (0, len(data_1)),
            (len(data_1) + 1, len(data_2)),
            (len(data_1) + 1 + len(data_2) + 1, len(data_3)),
        ]

        for (offset, length), data in zip(chunks, (data_1, data_2, data_3)):
            assert chunk_from_file(filename, offset, length, binary=True) == data
