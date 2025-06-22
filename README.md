# vsplit

[![Release](https://img.shields.io/github/v/release/virologyCharite/vsplit)](https://img.shields.io/github/v/release/virologyCharite/vsplit)
[![Build status](https://img.shields.io/github/actions/workflow/status/virologyCharite/vsplit/main.yml?branch=main)](https://github.com/virologyCharite/vsplit/actions/workflows/main.yml?query=branch%3Amain)
[![codecov](https://codecov.io/gh/virologyCharite/vsplit/branch/main/graph/badge.svg)](https://codecov.io/gh/virologyCharite/vsplit)
[![Commit activity](https://img.shields.io/github/commit-activity/m/virologyCharite/vsplit)](https://img.shields.io/github/commit-activity/m/virologyCharite/vsplit)
[![License](https://img.shields.io/github/license/virologyCharite/vsplit)](https://img.shields.io/github/license/virologyCharite/vsplit)

**NOTE**: although the code here works, it is still under development and
documentation needs to be written!

`vsplit` is a small set of utilities for virtually splitting files. This is
similar to [the UNIX split](https://en.wikipedia.org/wiki/Split_(Unix))
command, but with the key difference being that `vsplit` does not write the
chunks of the file to disk.  Instead, the offsets and lengths of the file
chunks are computed and can be printed or otherwise made available for
downstream processing.

The use case is when you want to write code to process pieces of a file in
parallel but want to minimize the amount of I/O that would be incurred from
first writing file chunks to disk and then reading them into your program for
processing.


- **Github repository**: <https://github.com/virologyCharite/vsplit/>
- **Documentation** <https://virologyCharite.github.io/vsplit/>
