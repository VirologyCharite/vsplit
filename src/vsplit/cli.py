import argparse
import csv
import os
import sys
from ast import literal_eval
from pathlib import Path
from shlex import quote
from tempfile import mkdtemp
from typing import Any

from vsplit.chunk import env_str, expand_command
from vsplit.fs import block_size
from vsplit.splitter import Splitter


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Virtually split a file.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    parser.add_argument(
        "filename",
        help=(
            "The file to virtually split. If you use --sbatch to process chunks "
            "using SLURM, this file must be accessible to all SLURM compute nodes "
            "so that jobs can access their data chunks."
        ),
    )

    parser.add_argument(
        "--chunk-offsets-filename",
        help=(
            "The filename to write chunk offsets and lengths to. If you use --sbatch "
            "to process chunks using SLURM, this file must be accessible to all SLURM "
            "compute nodes so that jobs can access their data chunks."
        ),
    )

    parser.add_argument(
        "--pattern",
        required=True,
        help="The pattern to split on.",
    )

    group = parser.add_mutually_exclusive_group(required=True)

    group.add_argument(
        "--n-chunks",
        type=int,
        help="The (approximate) number of chunks to produce.",
    )

    group.add_argument(
        "--chunk-size",
        type=int,
        help="The (approximate) size of the chunks to produce.",
    )

    parser.add_argument(
        "--buffer-size",
        type=int,
        default=block_size(),
        help=(
            "The size (in bytes) of the buffer to read chunks of the file from when "
            "searching for the split pattern."
        ),
    )

    parser.add_argument(
        "--max-pattern-length",
        type=int,
        help=(
            "The maximum length of a pattern. This could only be needed if we "
            "support regular expressions."
        ),
    )

    parser.add_argument(
        "--prefix",
        type=int,
        default=0,
        metavar="N",
        help=(
            "When printing offsets, add a prefix (of this length) of data found "
            "at the offset."
        ),
    )

    parser.add_argument(
        "--remove-prefix",
        type=int,
        default=0,
        help=(
            "The number of prefix characters to remove from the first pattern in each "
            "chunk. E.g., if you specify a pattern that starts with a newline, "
            "you might not want the newline to be returned. You could remove it via "
            "'--remove-prefix 1'."
        ),
    )

    parser.add_argument(
        "--skip-zero-chunk",
        action="store_false",
        dest="return_zero_chunk",
        help=(
            "Do not output the first chunk of the file. This is useful when "
            "the first part of the file (before the first occurrence of the "
            "split pattern is not wanted."
        ),
    )

    parser.add_argument(
        "--command",
        help="Print lines to run a command multiple times on different chunks.",
    )

    parser.add_argument(
        "--sbatch-args",
        help="Additional arguments to pass to sbatch (implies --sbatch).",
    )

    parser.add_argument(
        "--env",
        action="store_true",
        help=(
            "Print an environment-variable setting 'env' in conjuction with the "
            "--command output (only valid when --command is used)."
        ),
    )

    parser.add_argument(
        "--sbatch",
        action="store_true",
        help=(
            "Print commands to be run using sbatch. If given, --command must be used "
            "to supply a command to be run by SLURM."
        ),
    )

    parser.add_argument(
        "--eval-pattern",
        action="store_true",
        help=(
            "Evaluate the pattern (this allows you to use Python backslash-escaped "
            "strings on the command line."
        ),
    )

    args = parser.parse_args()

    if args.sbatch_args:
        args.sbatch = True

    if args.sbatch:
        if not args.command:
            sys.exit(
                "If you use --sbatch, you must also provide a command to be run via "
                "--command."
            )

        if not args.chunk_offsets_filename:
            sys.exit(
                "If you use --sbatch, you must also use --chunk-offsets-filename to "
                "provide a filename for all chunk offsets and lengths to be stored. "
                "This file must be accessible to all SLURM compute nodes so that jobs "
                "can look up their chunk details."
            )

    pattern = literal_eval(args.pattern) if args.eval_pattern else args.pattern

    splitter = Splitter(
        Path(args.filename),
        binary=isinstance(pattern, bytes),
        buffer_size=args.buffer_size,
    )

    chunks = list(
        splitter.chunks(
            n_chunks=args.n_chunks,
            chunk_size=args.chunk_size,
            pattern=pattern,
            return_zero_chunk=args.return_zero_chunk,
            max_pattern_length=args.max_pattern_length,
            remove_prefix=args.remove_prefix,
        )
    )

    chunk_offsets_path = save_offsets(args.chunk_offsets_filename, chunks)

    if args.command:
        if args.sbatch:
            print_sbatch_command(
                splitter, chunks, args.command, chunk_offsets_path, args.sbatch_args
            )
        else:
            print_commands(splitter, chunks, args.command, chunk_offsets_path, args.env)
    else:
        print_offsets(splitter, chunks, args.prefix)


def save_offsets(filename: str | None, chunks: list[tuple[int, int]]) -> Path:
    """
    Save TAB-separated split offsets and lengths. Return the Path to the filename.
    """
    if filename:
        path = Path(filename)
    else:
        # Note that this temp dir will not be removed!
        tmp_dir = Path(mkdtemp())
        path = tmp_dir / "chunks.tsv"

    with open(path, "w") as fp:
        writerow = csv.writer(fp, delimiter="\t").writerow
        for offset, length in chunks:
            writerow((offset, length))

    return path


def print_offsets(splitter: Splitter, chunks: list[tuple[int, int]], prefix: int) -> None:
    """
    Print TAB-separated split offsets, lengths, and (optionally) a prefix from the
    file for each chunk.
    """
    writerow = csv.writer(sys.stdout, delimiter="\t").writerow
    with open(splitter.filename) as fp:
        for offset, length in chunks:
            fields: list[Any] = [offset, length]
            if prefix:
                fp.seek(offset, os.SEEK_SET)
                fields.append(f"{fp.read(prefix)!r}")
            writerow(fields)


def print_commands(
    splitter: Splitter,
    chunks: list[tuple[int, int]],
    command: str,
    chunk_offsets_path: Path,
    env: bool,
) -> None:
    for index, (offset, length) in enumerate(chunks):
        if env:
            e = (
                env_str(
                    filename=splitter.filename,
                    index=index,
                    length=length,
                    n_chunks=len(chunks),
                    offset=offset,
                    chunk_offsets_filename=chunk_offsets_path,
                )
                + " "
            )
        else:
            e = ""

        c = expand_command(
            command=command,
            filename=splitter.filename,
            index=index,
            length=length,
            n_chunks=len(chunks),
            offset=offset,
            chunk_offsets_filename=chunk_offsets_path,
        )

        print(f"{e}{c}")


def print_sbatch_command(
    splitter: Splitter,
    chunks: list[tuple[int, int]],
    command: str,
    chunk_offsets_path: Path,
    sbatch_args: str | None,
) -> None:
    env = env_str(
        filename=splitter.filename,
        n_chunks=len(chunks),
        chunk_offsets_filename=chunk_offsets_path,
    )

    command = expand_command(
        command=command,
        filename=splitter.filename,
        n_chunks=len(chunks),
        chunk_offsets_filename=chunk_offsets_path,
        allow_single_chunk_variables=False,
    )

    print(
        f"{env} sbatch {(sbatch_args or '') + ' '}--array=0-{len(chunks) - 1} "
        f"--wrap {quote(command)}"
    )
