from collections.abc import Callable
from pathlib import Path

from Bio import SeqIO
from Bio.SeqIO.QualityIO import FastqGeneralIterator

from vsplit import (
    VSPLIT_CHUNK_OFFSETS_FILENAME_VAR,
    VSPLIT_FILENAME_VAR,
    VSPLIT_INDEX_VAR,
    VSPLIT_LENGTH_VAR,
    VSPLIT_N_CHUNKS_VAR,
    VSPLIT_OFFSET_VAR,
)
from vsplit.chunk import (
    FileSectionReader,
    chunk_from_env,
    chunk_from_file,
    env_str,
    expand_command,
)


def test_env_str(data_factory: Callable[[str | bytes, str], Path]):
    """
    The 'env_str' method should return the correct value.
    """
    data = "The data"
    filename = data_factory(data, "/top/don't use spaces in filenames!")
    assert env_str(
        filename=filename,
        chunk_offsets_filename=Path("/top/spaced out chunks.tsv"),
        index=3,
        offset=12,
        length=30,
        n_chunks=150,
    ) == (
        f"env "
        f"{VSPLIT_FILENAME_VAR}='/top/don'\"'\"'t use spaces in filenames!' "
        f"{VSPLIT_N_CHUNKS_VAR}=150 "
        f"{VSPLIT_CHUNK_OFFSETS_FILENAME_VAR}='/top/spaced out chunks.tsv' "
        f"{VSPLIT_INDEX_VAR}=3 "
        f"{VSPLIT_LENGTH_VAR}=30 "
        f"{VSPLIT_OFFSET_VAR}=12"
    )


class Test_chunk_from_file:
    """
    Tests for the chunk_from_file function.
    """

    def test_chunk_str(self, data_factory: Callable[[str | bytes], Path]):
        """
        Read a str chunk from a file.
        """
        data = "The data"
        filename = data_factory(data)
        assert chunk_from_file(filename, 2, 3) == "e d"

    def test_chunk_bytes(self, data_factory: Callable[[str | bytes], Path]):
        """
        Read a bytes chunk from a file.
        """
        data = "The data"
        filename = data_factory(data)
        assert chunk_from_file(filename, 2, 3, binary=True) == b"e d"


class Test_chunk_from_env:
    """
    Tests for the chunk_from_env function.
    """

    def test_chunk_str(self, monkeypatch, data_factory: Callable[[str | bytes], Path]):
        """
        Read a str chunk from a file, based on environment variables.
        """
        data = "The data"
        filename = data_factory(data)
        monkeypatch.setenv(VSPLIT_FILENAME_VAR, str(filename))
        monkeypatch.setenv(VSPLIT_OFFSET_VAR, "2")
        monkeypatch.setenv(VSPLIT_LENGTH_VAR, "3")
        assert chunk_from_env() == "e d"

    def test_chunk_bytes(self, monkeypatch, data_factory: Callable[[str | bytes], Path]):
        """
        Read a bytes chunk from a file, based on environment variables.
        """
        data = "The data"
        filename = data_factory(data)
        monkeypatch.setenv(VSPLIT_FILENAME_VAR, str(filename))
        monkeypatch.setenv(VSPLIT_OFFSET_VAR, "2")
        monkeypatch.setenv(VSPLIT_LENGTH_VAR, "3")
        assert chunk_from_env(binary=True) == b"e d"

    def test_chunk_str_as_file(
        self, monkeypatch, data_factory: Callable[[str | bytes], Path]
    ):
        """
        Read a str chunk from a file, based on environment variables, asking for
        a FileSectionReader to be returned.
        """
        data = "The data"
        filename = data_factory(data)
        monkeypatch.setenv(VSPLIT_FILENAME_VAR, str(filename))
        monkeypatch.setenv(VSPLIT_OFFSET_VAR, "2")
        monkeypatch.setenv(VSPLIT_LENGTH_VAR, "3")
        datafile = chunk_from_env(return_data=False)
        assert isinstance(datafile, FileSectionReader)
        with datafile as fp:
            assert fp.read() == "e d"

    def test_chunk_bytes_as_file(
        self, monkeypatch, data_factory: Callable[[str | bytes], Path]
    ):
        """
        Read a bytes chunk from a file, based on environment variables, asking for
        a FileSectionReader to be returned.
        """
        data = "The data"
        filename = data_factory(data)
        monkeypatch.setenv(VSPLIT_FILENAME_VAR, str(filename))
        monkeypatch.setenv(VSPLIT_OFFSET_VAR, "2")
        monkeypatch.setenv(VSPLIT_LENGTH_VAR, "3")
        datafile = chunk_from_env(binary=True, return_data=False)
        assert isinstance(datafile, FileSectionReader)
        with datafile as fp:
            assert fp.read() == b"e d"


class Test_FileSectionReader_str:
    """
    Test the FileSectionReader class reading a binary file.
    """

    def test_read_all(self, data_factory):
        data = "Line 1\nLine 2\nLine 3\nLine 4\nLine 5\nLine 6\n"
        filename = data_factory(data)

        with FileSectionReader(filename, 7, 20) as fp:
            assert fp.read() == "Line 2\nLine 3\nLine 4"

    def test_iter(self, data_factory):
        data = "Line 1\nLine 2\nLine 3\nLine 4\nLine 5\nLine 6\n"
        filename = data_factory(data)

        with FileSectionReader(filename, 7, 20) as fp:
            lines = []
            for line in fp:
                lines.append(line)

            assert lines == [
                "Line 2\n",
                "Line 3\n",
                "Line 4",
            ]

    def test_readlines(self, data_factory):
        data = "Line 1\nLine 2\nLine 3\nLine 4\nLine 5\nLine 6\n"
        filename = data_factory(data)

        with FileSectionReader(filename, 7, 20) as fp:
            assert fp.readlines() == [
                "Line 2\n",
                "Line 3\n",
                "Line 4",
            ]

    def test_seek_and_tell(self, data_factory):
        data = "Line 1\nLine 2\nLine 3\nLine 4\nLine 5\nLine 6\n"
        filename = data_factory(data)

        with FileSectionReader(filename, 7, 20) as fp:
            assert fp.tell() == 0
            fp.read(5)
            assert fp.tell() == 5
            fp.seek(0)
            assert fp.tell() == 0


class Test_FileSectionReader_bytes:
    """
    Test the FileSectionReader class reading a binary file.
    """

    def test_read_all(self, data_factory):
        data = b"Line 1\nLine 2\nLine 3\nLine 4\nLine 5\nLine 6\n"
        filename = data_factory(data)

        with FileSectionReader(filename, 7, 20, binary=True) as fp:
            assert fp.read() == b"Line 2\nLine 3\nLine 4"

    def test_iter(self, data_factory):
        data = b"Line 1\nLine 2\nLine 3\nLine 4\nLine 5\nLine 6\n"
        filename = data_factory(data)

        with FileSectionReader(filename, 7, 20, binary=True) as fp:
            lines = []
            for line in fp:
                lines.append(line)

            assert lines == [
                b"Line 2\n",
                b"Line 3\n",
                b"Line 4",
            ]

    def test_readlines(self, data_factory):
        data = b"Line 1\nLine 2\nLine 3\nLine 4\nLine 5\nLine 6\n"
        filename = data_factory(data)

        with FileSectionReader(filename, 7, 20, binary=True) as fp:
            assert fp.readlines() == [
                b"Line 2\n",
                b"Line 3\n",
                b"Line 4",
            ]

    def test_seek_and_tell(self, data_factory):
        data = b"Line 1\nLine 2\nLine 3\nLine 4\nLine 5\nLine 6\n"
        filename = data_factory(data)

        with FileSectionReader(filename, 7, 20, binary=True) as fp:
            assert fp.tell() == 0
            fp.read(5)
            assert fp.tell() == 5
            fp.seek(0)
            assert fp.tell() == 0


class Test_FileSectionReader_Bio:
    """
    Test the FileSectionReader class reading FASTA/FASTQ sequences with Bio.
    """

    def test_one_fasta(self, data_factory):
        """
        It must be possible to read a FASTA sequence using BioPython.
        """
        data = ">id1\nACGT\n>id2\nACGTTCT\n>id3\nGGGT\n"
        filename = data_factory(data)

        with FileSectionReader(filename, 10, 12) as fp:
            (record,) = list(SeqIO.parse(fp, "fasta"))
            assert record.id == "id2"
            assert record.seq == "ACGTTCT"

    def test_two_fasta(self, data_factory):
        """
        It must be possible to read two FASTA sequences using BioPython.
        """
        data = ">id1\nACGT\n>id2\nACGT\n>id3\nGGGT\n>id4\nCCT\n>id5\nTTAA\n>id6\nTCGG\n"
        filename = data_factory(data)

        with FileSectionReader(filename, 20, 29) as fp:
            record1, record2, record3 = list(SeqIO.parse(fp, "fasta"))

            assert record1.id == "id3"
            assert record1.seq == "GGGT"

            assert record2.id == "id4"
            assert record2.seq == "CCT"

            assert record3.id == "id5"
            assert record3.seq == "TTAA"

    def test_one_fastq(self, data_factory):
        """
        It must be possible to read FASTQ using BioPython.
        """
        data = "@id1\nACGT\n+\n!!!!\n@id2\nACGTTCT\n+\n!!!!!!!\n@id3\nGGGT\n+\n!!!!\n"
        filename = data_factory(data)

        with FileSectionReader(filename, 17, 23) as fp:
            (record,) = list(FastqGeneralIterator(fp))
            id_, sequence, quality = record
            assert id_ == "id2"
            assert sequence == "ACGTTCT"
            assert quality == "!!!!!!!"


class Test_expand_command:
    def test_replace_all(self):
        """
        Test replacing all %-style variables.
        """
        assert expand_command(
            command=(
                "program.py --chunk-offset [O] --chunk-length [L] "
                "--index [I] --padded-index [0I] --n-chunks [N] "
                "--file [F] --chunk-file [C]"
            ),
            filename=Path("/top/don't use spaces in filenames!"),
            index=3,
            length=100,
            n_chunks=150,
            offset=4000,
            chunk_offsets_filename=Path("/top/chunks.tsv"),
        ) == (
            "program.py --chunk-offset 4000 --chunk-length 100 "
            "--index 3 --padded-index 003 --n-chunks 150 "
            "--file '/top/don'\"'\"'t use spaces in filenames!' "
            "--chunk-file /top/chunks.tsv"
        )
