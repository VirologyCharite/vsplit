#!/usr/bin/env python

"""VSplit FUSE Wrapper - Create FUSE subfiles for vsplit chunks

This script takes the same arguments as the vsplit command-line tool but creates FUSE
files instead of printing chunk information. Each chunk becomes a virtual file in the
specified mount point.

Requirements:
    pip install mfusepy vsplit

Usage:
    python3 vsplit_fuse.py [vsplit options] --mount-point /path/to/mount input_file

Examples:
    # Split FASTA file into 10 chunks and create FUSE files
    python3 vsplit_fuse.py --pattern '>' --n-chunks 10 --mount-point /mnt/chunks sequences.fasta

    # Split by chunk size with prefix display
    python3 vsplit_fuse.py --pattern '"\\n>"' --eval-pattern --chunk-size 1000000 \\
                          --prefix 20 --mount-point /mnt/chunks data.txt
"""

import argparse
import errno
import json
import logging
import os
import subprocess
import sys
import tempfile

from fuse import FUSE, FuseOSError, Operations

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class SubfileFS(Operations):
    """FUSE filesystem for subfiles"""

    def __init__(self, root):
        self.root = os.path.realpath(root)
        self.metadata_file = os.path.join(self.root, ".subfile_metadata.json")
        self.subfiles = self._load_metadata()

    def _load_metadata(self):
        try:
            if os.path.exists(self.metadata_file):
                with open(self.metadata_file) as f:
                    return json.load(f)
        except Exception as e:
            logger.error(f"Error loading metadata: {e}")
        return {}

    def _save_metadata(self):
        try:
            with open(self.metadata_file, "w") as f:
                json.dump(self.subfiles, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving metadata: {e}")

    def _full_path(self, partial):
        if partial.startswith("/"):
            partial = partial[1:]
        path = os.path.join(self.root, partial)
        return path

    def _parse_subfile_name(self, filename):
        if "@" not in filename:
            return None, None, None

        parts = filename.split("@")
        if len(parts) != 2:
            return None, None, None

        base_filename = parts[0]
        try:
            range_parts = parts[1].split(":")
            if len(range_parts) != 2:
                return None, None, None

            offset = int(range_parts[0])
            length = int(range_parts[1])
            return base_filename, offset, length
        except ValueError:
            return None, None, None

    def _is_subfile(self, path):
        filename = os.path.basename(path)
        base, offset, length = self._parse_subfile_name(filename)
        return base is not None

    def _get_subfile_info(self, path):
        if path in self.subfiles:
            return self.subfiles[path]

        filename = os.path.basename(path)
        base, offset, length = self._parse_subfile_name(filename)
        if base is not None:
            base_path = os.path.join(os.path.dirname(path), base)
            return {"base_file": base_path, "offset": offset, "length": length}
        return None

    def getattr(self, path, fh=None):
        if self._is_subfile(path):
            subfile_info = self._get_subfile_info(path)
            if subfile_info:
                base_path = self._full_path(subfile_info["base_file"])
                if os.path.exists(base_path):
                    st = os.lstat(base_path)
                    attrs = dict(
                        (key, getattr(st, key))
                        for key in (
                            "st_mode",
                            "st_ino",
                            "st_dev",
                            "st_nlink",
                            "st_uid",
                            "st_gid",
                            "st_atime",
                            "st_mtime",
                            "st_ctime",
                        )
                    )
                    attrs["st_size"] = min(
                        subfile_info["length"],
                        max(0, st.st_size - subfile_info["offset"]),
                    )
                    return attrs
                else:
                    raise FuseOSError(errno.ENOENT)
            else:
                raise FuseOSError(errno.ENOENT)
        else:
            full_path = self._full_path(path)
            try:
                st = os.lstat(full_path)
                return dict(
                    (key, getattr(st, key))
                    for key in (
                        "st_atime",
                        "st_ctime",
                        "st_gid",
                        "st_mode",
                        "st_mtime",
                        "st_nlink",
                        "st_size",
                        "st_uid",
                        "st_dev",
                        "st_ino",
                    )
                )
            except OSError:
                raise FuseOSError(errno.ENOENT)

    def readdir(self, path, fh):
        full_path = self._full_path(path)
        dirents = [".", ".."]
        if os.path.isdir(full_path):
            dirents.extend(os.listdir(full_path))

        for subfile_path in self.subfiles:
            if os.path.dirname(subfile_path) == path:
                dirents.append(os.path.basename(subfile_path))

        return dirents

    def open(self, path, flags):
        if self._is_subfile(path):
            subfile_info = self._get_subfile_info(path)
            if subfile_info:
                base_path = self._full_path(subfile_info["base_file"])
                if os.path.exists(base_path):
                    return os.open(base_path, flags)
                else:
                    raise FuseOSError(errno.ENOENT)
            else:
                raise FuseOSError(errno.ENOENT)
        else:
            full_path = self._full_path(path)
            return os.open(full_path, flags)

    def read(self, path, length, offset, fh):
        if self._is_subfile(path):
            subfile_info = self._get_subfile_info(path)
            if subfile_info:
                subfile_offset = subfile_info["offset"]
                subfile_length = subfile_info["length"]

                actual_offset = subfile_offset + offset
                max_readable = max(0, subfile_length - offset)
                actual_length = min(length, max_readable)

                if actual_length <= 0:
                    return b""

                os.lseek(fh, actual_offset, os.SEEK_SET)
                return os.read(fh, actual_length)
            else:
                raise FuseOSError(errno.ENOENT)
        else:
            os.lseek(fh, offset, os.SEEK_SET)
            return os.read(fh, length)

    def write(self, path, buf, offset, fh):
        if self._is_subfile(path):
            subfile_info = self._get_subfile_info(path)
            if subfile_info:
                subfile_offset = subfile_info["offset"]
                subfile_length = subfile_info["length"]

                actual_offset = subfile_offset + offset
                max_writable = max(0, subfile_length - offset)
                actual_length = min(len(buf), max_writable)

                if actual_length <= 0:
                    return 0

                os.lseek(fh, actual_offset, os.SEEK_SET)
                return os.write(fh, buf[:actual_length])
            else:
                raise FuseOSError(errno.ENOENT)
        else:
            os.lseek(fh, offset, os.SEEK_SET)
            return os.write(fh, buf)

    def flush(self, path, fh):
        return os.fsync(fh)

    def release(self, path, fh):
        return os.close(fh)


def run_vsplit_get_chunks(args, input_file):
    """Run vsplit and parse its output to get chunk information"""

    # Build vsplit command
    cmd = ["vsplit"]

    # Add all the vsplit arguments
    if args.pattern:
        cmd.extend(["--pattern", args.pattern])
    if args.eval_pattern:
        cmd.append("--eval-pattern")
    if args.n_chunks:
        cmd.extend(["--n-chunks", str(args.n_chunks)])
    if args.chunk_size:
        cmd.extend(["--chunk-size", str(args.chunk_size)])
    if args.prefix:
        cmd.extend(["--prefix", str(args.prefix)])
    if args.remove_prefix:
        cmd.extend(["--remove-prefix", str(args.remove_prefix)])
    if args.skip_zero_chunk:
        cmd.append("--skip-zero-chunk")
    if args.buffer_size:
        cmd.extend(["--buffer-size", str(args.buffer_size)])
    if args.max_pattern_length:
        cmd.extend(["--max-pattern-length", str(args.max_pattern_length)])

    # Add input file
    cmd.append(input_file)

    logger.info(f"Running: {' '.join(cmd)}")

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        output = result.stdout.strip()

        chunks = []
        for i, line in enumerate(output.split("\n")):
            if not line.strip():
                continue

            parts = line.split("\t")
            if len(parts) < 2:
                continue

            try:
                offset = int(parts[0])
                length = int(parts[1])
                prefix = parts[2] if len(parts) > 2 else ""

                chunks.append({
                    "index": i,
                    "offset": offset,
                    "length": length,
                    "prefix": prefix,
                })
            except ValueError as e:
                logger.warning(f"Could not parse line: {line} - {e}")
                continue

        return chunks

    except subprocess.CalledProcessError as e:
        logger.error(f"vsplit failed: {e}")
        logger.error(f"stderr: {e.stderr}")
        return []
    except FileNotFoundError:
        logger.error(
            "vsplit command not found. Make sure vsplit is installed: pip install vsplit"
        )
        return []


def create_chunk_files(chunks, input_file, mount_point_root):
    """Create FUSE subfiles for each chunk"""

    fs = SubfileFS(mount_point_root)
    input_filename = os.path.basename(input_file)

    logger.info(f"Creating {len(chunks)} chunk files...")

    for chunk in chunks:
        # Create a descriptive filename for each chunk
        chunk_name = f"chunk_{chunk['index']:04d}_{input_filename}@{chunk['offset']}:{chunk['length']}"
        chunk_path = f"/{chunk_name}"

        # Register the subfile
        fs.subfiles[chunk_path] = {
            "base_file": f"/{input_filename}",
            "offset": chunk["offset"],
            "length": chunk["length"],
        }

        logger.info(f"Created chunk file: {chunk_name}")
        if chunk["prefix"]:
            logger.info(f"  Prefix: {chunk['prefix'][:50]!r}...")
        logger.info(f"  Offset: {chunk['offset']}, Length: {chunk['length']}")

    # Save metadata
    fs._save_metadata()
    logger.info(f"Saved metadata to {fs.metadata_file}")

    return fs


def setup_mount_environment(input_file, mount_point):
    """Set up the mount point with the input file accessible"""
    mount_root = tempfile.mkdtemp(prefix="vsplit_fuse_")

    # Create a symlink to the input file in the mount root
    input_filename = os.path.basename(input_file)
    input_link_path = os.path.join(mount_root, input_filename)

    try:
        os.symlink(os.path.abspath(input_file), input_link_path)
        logger.info(
            f"Created symlink: {input_link_path} -> {os.path.abspath(input_file)}"
        )
    except OSError as e:
        logger.error(f"Could not create symlink: {e}")
        return None

    return mount_root


def main():
    parser = argparse.ArgumentParser(description="Create FUSE files for vsplit chunks")

    # vsplit arguments
    parser.add_argument("--pattern", help="Pattern to split on")
    parser.add_argument(
        "--eval-pattern", action="store_true", help="Evaluate pattern using Python eval()"
    )
    parser.add_argument("--n-chunks", type=int, help="Number of chunks to create")
    parser.add_argument("--chunk-size", type=int, help="Approximate size of each chunk")
    parser.add_argument("--prefix", type=int, help="Show this many prefix characters")
    parser.add_argument(
        "--remove-prefix",
        type=int,
        help="Remove this many characters from pattern prefix",
    )
    parser.add_argument(
        "--skip-zero-chunk",
        action="store_true",
        help="Skip the initial chunk before first pattern",
    )
    parser.add_argument("--buffer-size", type=int, help="Buffer size for reading file")
    parser.add_argument(
        "--max-pattern-length",
        type=int,
        help="Maximum pattern length for overlap handling",
    )

    # Our additional arguments
    parser.add_argument(
        "--mount-point", required=True, help="Directory to mount FUSE filesystem"
    )
    parser.add_argument(
        "--foreground",
        action="store_true",
        help="Run FUSE in foreground (useful for debugging)",
    )
    parser.add_argument("input_file", help="File to split")

    args = parser.parse_args()

    # Validate input file
    if not os.path.exists(args.input_file):
        logger.error(f"Input file does not exist: {args.input_file}")
        return 1

    # Validate mount point
    if not os.path.exists(args.mount_point):
        logger.error(f"Mount point does not exist: {args.mount_point}")
        return 1

    # Validate that either n_chunks or chunk_size is provided
    if not args.n_chunks and not args.chunk_size:
        logger.error("Must specify either --n-chunks or --chunk-size")
        return 1

    if not args.pattern:
        logger.error("Must specify --pattern")
        return 1

    # Get chunks from vsplit
    logger.info("Getting chunk information from vsplit...")
    chunks = run_vsplit_get_chunks(args, args.input_file)

    if not chunks:
        logger.error("No chunks found or vsplit failed")
        return 1

    logger.info(f"Found {len(chunks)} chunks")

    # Set up mount environment
    mount_root = setup_mount_environment(args.input_file, args.mount_point)
    if not mount_root:
        return 1

    try:
        # Create FUSE filesystem with chunks
        fs = create_chunk_files(chunks, args.input_file, mount_root)

        # Mount the filesystem
        logger.info(f"Mounting FUSE filesystem at {args.mount_point}")
        logger.info("Chunk files will be available as chunk_XXXX_filename@offset:length")
        logger.info("Press Ctrl+C to unmount")

        FUSE(fs, args.mount_point, nothreads=True, foreground=args.foreground)

    except KeyboardInterrupt:
        logger.info("Unmounting...")
    except Exception as e:
        logger.error(f"FUSE error: {e}")
        return 1
    finally:
        # Clean up temporary directory
        try:
            import shutil

            shutil.rmtree(mount_root)
            logger.info(f"Cleaned up temporary directory: {mount_root}")
        except Exception as e:
            logger.warning(f"Could not clean up temporary directory: {e}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
