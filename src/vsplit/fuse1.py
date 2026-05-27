#!/usr/bin/env python3
"""
FUSE Subfile Overlay - Create virtual files that represent ranges of other files

Usage:
    python3 fuse_subfile.py /path/to/underlying/storage /path/to/mountpoint

Create subfiles using special filenames:
    touch "filename.txt@1000:2000"  # Creates a subfile of filename.txt from byte 1000 to 2000
    touch "data.bin@0:1024"         # Creates a subfile of data.bin from byte 0 to 1024

Requirements:
    pip install fusepy
"""

import errno
import json
import logging
import os
import sys

from fuse import FUSE, FuseOSError, Operations

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class SubfileFS(Operations):
    def __init__(self, root):
        self.root = os.path.realpath(root)
        self.metadata_file = os.path.join(self.root, ".subfile_metadata.json")
        self.subfiles = self._load_metadata()

    def _load_metadata(self):
        """Load subfile metadata from disk"""
        try:
            if os.path.exists(self.metadata_file):
                with open(self.metadata_file) as f:
                    return json.load(f)
        except Exception as e:
            logger.error(f"Error loading metadata: {e}")
        return {}

    def _save_metadata(self):
        """Save subfile metadata to disk"""
        try:
            with open(self.metadata_file, "w") as f:
                json.dump(self.subfiles, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving metadata: {e}")

    def _full_path(self, partial):
        """Convert a partial path to a full path"""
        if partial.startswith("/"):
            partial = partial[1:]
        path = os.path.join(self.root, partial)
        return path

    def _parse_subfile_name(self, filename):
        """Parse subfile notation: filename@offset:length"""
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
            end_or_length = int(range_parts[1])

            # Determine if second number is end position or length
            # If it's smaller than offset, treat as length
            if end_or_length <= offset:
                length = end_or_length
            else:
                length = end_or_length - offset

            return base_filename, offset, length
        except ValueError:
            return None, None, None

    def _is_subfile(self, path):
        """Check if a path represents a subfile"""
        filename = os.path.basename(path)
        base, offset, length = self._parse_subfile_name(filename)
        return base is not None

    def _get_subfile_info(self, path):
        """Get subfile information"""
        if path in self.subfiles:
            return self.subfiles[path]

        filename = os.path.basename(path)
        base, offset, length = self._parse_subfile_name(filename)
        if base is not None:
            base_path = os.path.join(os.path.dirname(path), base)
            return {"base_file": base_path, "offset": offset, "length": length}
        return None

    # Filesystem methods
    def getattr(self, path, fh=None):
        """Get file attributes"""
        if self._is_subfile(path):
            subfile_info = self._get_subfile_info(path)
            if subfile_info:
                # Get attributes of the base file
                base_path = self._full_path(subfile_info["base_file"])
                if os.path.exists(base_path):
                    st = os.lstat(base_path)
                    # Modify size to reflect the subfile range
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
        """Read directory contents"""
        full_path = self._full_path(path)
        dirents = [".", ".."]
        if os.path.isdir(full_path):
            dirents.extend(os.listdir(full_path))

        # Add virtual subfiles
        for subfile_path in self.subfiles:
            if os.path.dirname(subfile_path) == path:
                dirents.append(os.path.basename(subfile_path))

        return dirents

    def open(self, path, flags):
        """Open a file"""
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

    def create(self, path, mode, fi=None):
        """Create a new file"""
        if self._is_subfile(path):
            filename = os.path.basename(path)
            base, offset, length = self._parse_subfile_name(filename)
            if base is not None:
                base_path = os.path.join(os.path.dirname(path), base)
                base_full_path = self._full_path(base_path)

                # Check if base file exists
                if not os.path.exists(base_full_path):
                    raise FuseOSError(errno.ENOENT)

                # Register the subfile
                self.subfiles[path] = {
                    "base_file": base_path,
                    "offset": offset,
                    "length": length,
                }
                self._save_metadata()

                # Return a file descriptor to the base file
                return os.open(base_full_path, os.O_RDONLY)
            else:
                raise FuseOSError(errno.EINVAL)
        else:
            full_path = self._full_path(path)
            return os.open(full_path, os.O_WRONLY | os.O_CREAT, mode)

    def read(self, path, length, offset, fh):
        """Read data from a file"""
        if self._is_subfile(path):
            subfile_info = self._get_subfile_info(path)
            if subfile_info:
                # Adjust offset and length for subfile range
                subfile_offset = subfile_info["offset"]
                subfile_length = subfile_info["length"]

                # Calculate actual file offset
                actual_offset = subfile_offset + offset

                # Limit read length to subfile boundaries
                max_readable = max(0, subfile_length - offset)
                actual_length = min(length, max_readable)

                if actual_length <= 0:
                    return b""

                # Read from the actual file
                os.lseek(fh, actual_offset, os.SEEK_SET)
                return os.read(fh, actual_length)
            else:
                raise FuseOSError(errno.ENOENT)
        else:
            os.lseek(fh, offset, os.SEEK_SET)
            return os.read(fh, length)

    def write(self, path, buf, offset, fh):
        """Write data to a file"""
        if self._is_subfile(path):
            subfile_info = self._get_subfile_info(path)
            if subfile_info:
                # Adjust offset for subfile range
                subfile_offset = subfile_info["offset"]
                subfile_length = subfile_info["length"]

                # Calculate actual file offset
                actual_offset = subfile_offset + offset

                # Limit write length to subfile boundaries
                max_writable = max(0, subfile_length - offset)
                actual_length = min(len(buf), max_writable)

                if actual_length <= 0:
                    return 0

                # Write to the actual file
                os.lseek(fh, actual_offset, os.SEEK_SET)
                return os.write(fh, buf[:actual_length])
            else:
                raise FuseOSError(errno.ENOENT)
        else:
            os.lseek(fh, offset, os.SEEK_SET)
            return os.write(fh, buf)

    def truncate(self, path, length, fh=None):
        """Truncate a file"""
        if self._is_subfile(path):
            # Don't allow truncating subfiles
            raise FuseOSError(errno.EPERM)
        else:
            full_path = self._full_path(path)
            with open(full_path, "r+") as f:
                f.truncate(length)

    def flush(self, path, fh):
        """Flush file data"""
        return os.fsync(fh)

    def release(self, path, fh):
        """Release/close a file"""
        return os.close(fh)

    def unlink(self, path):
        """Delete a file"""
        if self._is_subfile(path):
            # Remove from metadata
            if path in self.subfiles:
                del self.subfiles[path]
                self._save_metadata()
        else:
            full_path = self._full_path(path)
            return os.unlink(full_path)

    # Pass through other operations
    def chmod(self, path, mode):
        full_path = self._full_path(path)
        return os.chmod(full_path, mode)

    def chown(self, path, uid, gid):
        full_path = self._full_path(path)
        return os.chown(full_path, uid, gid)

    def utimens(self, path, times=None):
        full_path = self._full_path(path)
        return os.utime(full_path, times)

    def mkdir(self, path, mode):
        full_path = self._full_path(path)
        return os.mkdir(full_path, mode)

    def rmdir(self, path):
        full_path = self._full_path(path)
        return os.rmdir(full_path)


def main(mountpoint, root):
    FUSE(SubfileFS(root), mountpoint, nothreads=True, foreground=True)


def create_subfile_tool():
    """Separate tool to create subfiles more intuitively"""
    import argparse

    parser = argparse.ArgumentParser(description="Create subfiles in the FUSE overlay")
    parser.add_argument("mountpoint", help="Path to the mounted FUSE overlay")
    parser.add_argument("base_file", help="Base file to create subfile from")
    parser.add_argument("subfile_name", help="Name for the new subfile")
    parser.add_argument("offset", type=int, help="Starting byte offset")
    parser.add_argument("length", type=int, help="Length in bytes")

    args = parser.parse_args()

    # Create the subfile using the @ syntax
    subfile_path = os.path.join(
        args.mountpoint, f"{args.base_file}@{args.offset}:{args.length}"
    )

    try:
        # Create the subfile
        with open(subfile_path, "w") as f:
            pass  # Just create it

        # Create a symlink with the friendly name
        friendly_path = os.path.join(args.mountpoint, args.subfile_name)
        if not os.path.exists(friendly_path):
            os.symlink(os.path.basename(subfile_path), friendly_path)

        print(f"Created subfile: {args.subfile_name}")
        print(f"  Base file: {args.base_file}")
        print(f"  Range: bytes {args.offset}-{args.offset + args.length}")

    except Exception as e:
        print(f"Error creating subfile: {e}")
        return 1

    return 0


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "create-subfile":
        # Remove the 'create-subfile' argument and run the tool
        sys.argv.pop(1)
        sys.exit(create_subfile_tool())

    if len(sys.argv) != 3:
        print("Usage: %s <underlying_storage_path> <mountpoint>" % sys.argv[0])
        print(
            "   or: %s create-subfile <mountpoint> <base_file> <subfile_name> <offset> <length>"
            % sys.argv[0]
        )
        print()
        print("Examples:")
        print("  # Mount the overlay")
        print("  %s /data /mnt/subfiles" % sys.argv[0])
        print()
        print("  # Create subfiles (in another terminal)")
        print(
            "  %s create-subfile /mnt/subfiles largefile.dat section1 1000 2048"
            % sys.argv[0]
        )
        print(
            '  # This creates a subfile named "section1" showing bytes 1000-3048 of largefile.dat'
        )
        print()
        print("  # Or use the @ syntax directly:")
        print("  touch /mnt/subfiles/largefile.dat@1000:2048")
        sys.exit(1)

    root = sys.argv[1]
    mountpoint = sys.argv[2]

    if not os.path.exists(root):
        print(f"Error: Underlying storage path '{root}' does not exist")
        sys.exit(1)

    if not os.path.exists(mountpoint):
        print(f"Error: Mount point '{mountpoint}' does not exist")
        sys.exit(1)

    print("Mounting subfile overlay...")
    print(f"  Underlying storage: {root}")
    print(f"  Mount point: {mountpoint}")
    print("  Use 'python3 fuse_subfile.py create-subfile ...' to create subfiles")

    main(mountpoint, root)
