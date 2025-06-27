# vsplit

`vsplit` can be used to "virtually" split a file. This is similar to [the
UNIX split command](https://en.wikipedia.org/wiki/Split_(Unix)), but with the
key difference being that `vsplit` does not write the chunks of the file to
disk.  Instead, the offsets and lengths of the file chunks are computed and
made available for downstream processing.

The use case is when you want to write code to process pieces of a file in
parallel but need to reduce I/O overhead. With the traditional UNIX `split`
approach, the file data are first read from disk and then each chunk is
written to a separate file. This requires I/O of the entire dataset _twice_
before the intended processing can even begin. For a small local file this is
rarely a problem, but if the storage is on a networked filesystem (as is
common in HPCS clusters) and the file is large, the additional overhead can
be significant. An obvious alternative is to initially find the offsets and
lengths of the chunks that `split` would have written to the disk and give
these directly to the program doing the actual processing. That program can
open the large file, `seek` to the offset of its chunk and read just the
number of bytes of its chunk.

## Installation

```sh
$ pip install vsplit
```

Or if you have [uv](https://docs.astral.sh/uv/) installed, you can use it to
run `vsplit` directly:

```sh
$ uvx vsplit ....
```

## Example data file

The examples below use the SARS-CoV-2 `sequences.fasta` file downloaded (and
uncompressed) from [GISAID](https://gisaid.org) on April 19, 2025. The file
is about 0.5TB (511,448,191,537 bytes).

## Basic usage

### Either: You provide a desired number of chunks

The simplest usage is to just print details of the file chunks. You give a
pattern to split the file on and the number of chunks you want and get
TAB-separated output with **zero-based** file offsets and chunk lengths:

```sh
$ vsplit --pattern \> --n-chunks 10 sequences.fasta
0               51596653008
51596653008     51192803792
102789456800    51405791696
154195248496    51180888528
205376137024    51315241424
256691378448    51195830736
307887209184    51176833488
359064042672    51299463632
410363506304    51177325008
461540831312    49907360225
```

Note: the backslash in the `\>` is to prevent the `>` from redirecting the
shell output, and I have adjusted the spacing on the TAB-separated output to
better line things up.

You can pipe that outut into `awk '{sum += $2} END {print sum}'` if you want
to quickly confirm that the sum of all the chunk lengths is 511,448,191,537.

### Or: You provide a desired chunk size

Instead of giving a number of chunks, you can give a chunk size:

```sh
$ vsplit --pattern \> --chunk-size 50000000000 sequences.fasta
0               50014110719
50014110719     50225394687
100239505406    50092671999
150332177405    50210952191
200543129596    50089251839
250632381435    50038522879
300670904314    50020840447
350691744761    50124010495
400815755256    50052318207
450868073463    50000001102
500868074565    10580116972
```

Note that the requested number of chunks or chunk size are just your
suggestions. The actual values in the `vsplit` output will depend heavily on
where the pattern is present in the data as well as the suggested values
(which determine where `vsplit` jumps to in the file to look for the next
splitting pattern).

### Printing initial data from the chunk

If you want a look at the start of the chunks that are found, you can provide
a `--prefix` length and that many bytes from the start of the chunk will be
printed.

```sh
$ vsplit --prefix 20 --pattern \> --chunk-size 50000000000 sequences.fasta
0               50014110719 '>hCoV-19/Australia/N'
50014110719     50225394687 '>hCoV-19/Chongqing/Y'
100239505406    50092671999 '>hCoV-19/England/ALD'
150332177405    50210952191 '>hCoV-19/USA/CA-CZB-'
200543129596    50089251839 '>hCoV-19/USA/VA-VCUV'
250632381435    50038522879 '>hCoV-19/England/ALD'
300670904314    50020840447 '>hCoV-19/Scotland/QE'
350691744761    50124010495 '>hCoV-19/France/GES-'
400815755256    50052318207 '>hCoV-19/USA/CA-CDC-'
450868073463    50000001102 '>hCoV-19/USA/TX-CDC-'
500868074565    10580116972 '>hCoV-19/USA/MN-CDC-'
```

### The split pattern can span lines

In the above example, we are splitting on `>`. In a FASTA file it might be
more reliable to split on the pattern `"\n>"` (i.e., a newline followed by a
`>`). You can embed the newline in the pattern as follows:

```sh
$ vsplit --prefix 20 --pattern '"\n>"' --eval-pattern --chunk-size 50000000000 sequences.fasta
0               50014110718 '>hCoV-19/Australia/N'
50014110718     50048541694 '\n>hCoV-19/Chongqing/'
100062652412    50094859262 '\n>hCoV-19/Australia/'
150157511674    50089751550 '\n>hCoV-19/USA/IL-CDC'
200247263224    50000002084 '\n>hCoV-19/Brazil/SP-'
250247265308    50172081150 '\n>hCoV-19/USA/CA-CDC'
300419346458    50200663038 '\n>hCoV-19/USA/TN-VUM'
350620009496    50222236670 '\n>hCoV-19/USA/WI-CDC'
400842246166    50183771134 '\n>hCoV-19/England/PL'
451026017300    50220909566 '\n>hCoV-19/Mexico/VER'
501246926866    10201264671 '\n>hCoV-19/USA/SC-CDC'
```

In the above, the extra `--eval-pattern` argument tells `vsplit` to use
Python's `eval` function to evaluate the string pattern. This allows you to
use the regular backslash escaping to specify any string. The single quotes
are used to make sure the double-quoted string is passed through to Python
instead of being interpreted by your shell.

### Splitting on a byte pattern

You can also split on a byte pattern using Python's convention of putting a
`b` before your string pattern:

```sh
$ vsplit --prefix 20 --pattern 'b"\n>"' --eval-pattern \
         --chunk-size 50000000000 sequences.fasta
# Output is identical to the command above.
```

### Skipping the initial chunk

In the previous examples where we split on `\n>`, you can see that the
initial chunk (beginning `>hCoV-19/Australia/N`) does not start with the
split pattern. That's because `vsplit` jumps to its first offset in your file
without even looking at the initial data (that's kind of the point, after
all). The default is to return the details of the initial chunk (before the
first instance of the pattern is located). If you don't want this initial
chunk to be returned, you can use `--skip-zero-chunk`:

```sh
$ vsplit --skip-zero-chunk --prefix 20 --pattern '"\n>"' --eval-pattern \
         --chunk-size 50000000000 sequences.fasta
100062652412    50094859262 '\n>hCoV-19/Australia/'
150157511674    50089751550 '\n>hCoV-19/USA/IL-CDC'
200247263224    50000002084 '\n>hCoV-19/Brazil/SP-'
250247265308    50172081150 '\n>hCoV-19/USA/CA-CDC'
300419346458    50200663038 '\n>hCoV-19/USA/TN-VUM'
350620009496    50222236670 '\n>hCoV-19/USA/WI-CDC'
400842246166    50183771134 '\n>hCoV-19/England/PL'
451026017300    50220909566 '\n>hCoV-19/Mexico/VER'
501246926866    10201264671 '\n>hCoV-19/USA/SC-CDC'
```

### Discarding a fixed-length prefix from the matched pattern

Also in the previous examples where we split on `\n>`, we actually don't want
the leading newline to be part of the chunk. You can indicate that a certain
number of leading characters be dropped from the pattern in the returned
chunk using `--remove-prefix` to indicate a number of prefix characters to
drop:

```sh
$ vsplit --remove-prefix 1 --prefix 20 --pattern '"\n>"' --eval \
         --chunk-size 50000000000 sequences.fasta
0               50014110718 '>hCoV-19/Australia/N'
50014110719     50225394686 '>hCoV-19/Chongqing/Y'
100239505406    50092671998 '>hCoV-19/England/ALD'
150332177405    50210952190 '>hCoV-19/USA/CA-CZB-'
200543129596    50089251838 '>hCoV-19/USA/VA-VCUV'
250632381435    50038522878 '>hCoV-19/England/ALD'
300670904314    50020840446 '>hCoV-19/Scotland/QE'
350691744761    50124010494 '>hCoV-19/France/GES-'
400815755256    50052318206 '>hCoV-19/USA/CA-CDC-'
450868073463    50000001101 '>hCoV-19/USA/TX-CDC-'
500868074565    10580116972 '>hCoV-19/USA/MN-CDC-'
```

## Getting chunk information into your program

So much for printing the basic information about chunks.

The next step is to make use of this information in your program. You can
obviously save the above TAB-separated output to a file, count the number of
lines (i.e., chunks), and run your program once for each chunk, passing an
argument each time to indicate which chunk to read. Then, your program simply
opens the chunk offset/length file, reads to the line with the offset and
length for the given chunk, opens the file, seeks to its offset, and reads
just the correct amount of data (as given by the length).

This is pretty straightforward, but it's fiddly in several ways, mostly
because you will need to keep track of how much data you have read.

To make your life easier, `vsplit` offers several mechanisms to get data
chunks to your program.

Two things are needed: 1) a mechanism for reading the chunk given the
filename, and the chunk offset and length, and 2) a way to pass the filename,
offset, and length to your program.

### Reading chunks

If you are writing Python, you can use the `FileChunk` class to read your
data. Given variables `filename`, `offset`, and `length` you can write, for
example

```python
from vsplit import FileChunk

with FileChunk(filename, offset, length) as fp:
    for line in fp:
        print(line)

# or

with FileChunk(filename, offset, length) as fp:
    print(line.read())
```

Here `fp` is a file-like object that will return just the data from the chunk
of the original (virtually split) file. If you use it via [the with
statement](https://docs.python.org/3/reference/compound_stmts.html#with) in a
context manager (as in the above two examples), the file will be opened and
closed for you. If you don't want to do that, you can call regular
file-object methods on the `FileChunk` instance (e.g., `open`, `close`,
`seek`, etc).

### Passing chunk information to your script

To help with the issue of getting chunk information to your program, `vsplit`
gives you three options.  In all cases, `vsplit` simply print commands for
you. You can store the commands in a file and run them as a shell script, or
pipe them into a shell process or into [GNU
parallel](https://www.gnu.org/software/parallel/) to run the commands
directly.

#### Using command line arguments

Suppose you write a program `process-chunk` that accepts three arguments,
`--filename`, `--chunk-offset`, and `--chunk-length`. You can ask `vsplit` to
print commands to call your program for each chunk:

```sh
$ vsplit --command 'process-chunk --filename [F] --chunk-offset [O] --chunk-length [L]' \
         --pattern \> --n-chunks 3 sequences.fasta
process-chunk --filename sequences.fasta --chunk-offset 0 --chunk-length 170570581519
process-chunk --filename sequences.fasta --chunk-offset 170570581519 --chunk-length 170633512463
process-chunk --filename sequences.fasta --chunk-offset 341204093982 --chunk-length 170244097555
```

In the above, you use `[x]` markers on your command line to indicate things
that should be replaced with per-chunk information.  The full set of
indicators is

    [F]: The (shell-quoted) filename.
    [I]: The (zero-based) chunk index.
    [0I]: The (zero-based) chunk index, but padded with leading zeroes.
    [L]: The chunk length.
    [N]: The overall number of chunks found.
    [O]: The chunk offset.
    [C]: The (shell-quoted) name of the file containing the TAB-separated chunk offset/lengths.

These are all provided but for any particular program only some subset will
be used. Note that there is no reliance on Python here, your program could be
written in any language and then just open the file and read its data however
it likes.  But if you are in Python you can use the `FileChunk` class
described above.

### Using environment variables

Alternatively, you might prefer to run `vsplit` with `--env` and a command to
have it print `env` (see `man env`) commands to set environment variables
that your program can then examine and use to get its chunk:

```sh
$ vsplit --env --command process-chunk --pattern \> --n-chunks 3 sequences.fasta
env VSPLIT_INPUT_FILENAME=sequences.fasta VSPLIT_N_CHUNKS=3 \
    VSPLIT_CHUNK_OFFSETS_FILENAME=/tmp/tmp8tzjf1dk/chunks.tsv \
    VSPLIT_CHUNK_INDEX=0 VSPLIT_LENGTH=170570581519 VSPLIT_OFFSET=0 process-chunk
env VSPLIT_INPUT_FILENAME=sequences.fasta VSPLIT_N_CHUNKS=3 \
    VSPLIT_CHUNK_OFFSETS_FILENAME=/tmp/tmp8tzjf1dk/chunks.tsv \
    VSPLIT_CHUNK_INDEX=1 VSPLIT_LENGTH=170633512463 VSPLIT_OFFSET=170570581519 process-chunk
env VSPLIT_INPUT_FILENAME=sequences.fasta VSPLIT_N_CHUNKS=3 \
    VSPLIT_CHUNK_OFFSETS_FILENAME=/tmp/tmp8tzjf1dk/chunks.tsv \
    VSPLIT_CHUNK_INDEX=2 VSPLIT_LENGTH=170244097555 VSPLIT_OFFSET=341204093982 process-chunk
```

Note that the chunk offsets filename refers to a `chunks.tsv` file in a
temporary directory). You can pass an explicit filename via
`--chunk-offsets-filename`, if you prefer. This file will eventually be
removed by your operating system. `vsplit` cannot remove it because you might
be needing it in your script (if you are relying on the chunk index variable
as opposed to the offset and length variables).

If your script is in Python, there is a convenience function for reading the
environment variables and getting you a `FileChunk` instance. E.g.:

```python
from vsplit import chunk_from_env

with chunk_from_env() as fp:
    for line in fp:
        print(line)
```

Or if your program needs to read its chunk in binary mode:

```python
from vsplit import chunk_from_env

with chunk_from_env(binary=True) as fp:
    while data := fp.read(4095)
        # Do something.
```

#### Complete examples: reading sequence ids from a FASTA file

Here's a simple working example that reads the first FASTA sequence from a
chunk and prints its id. The following is saved as `print-ids.py`:

```python
from Bio import SeqIO
from vsplit import chunk_from_env

for record in SeqIO.parse(chunk_from_env(), "fasta"):
    print(record.id)
    break
```

Which I can run using GNU `parallel` as follows:

```sh
$ vsplit --env --command print-ids.py --pattern \> --n-chunks 5 sequences.fasta | parallel
hCoV-19/Brazil/PR-IPEC_VIGCV19_GPA_0359/2021|2021-04-26|2022-04-29
hCoV-19/Spain/VC-FISABIO-100036/2021|2021-10-01|2022-03-17
hCoV-19/USA/MI-UM-10049052165/2022|2022-12-26|2023-01-12
hCoV-19/Japan/TKYkbm71284/2022|2022-12-12|2023-01-13
hCoV-19/Australia/NSW-ICPMR-52165/2023|2023-11-07|2024-01-08
```

And here's a version that saves the output from each invocation of the
program into a separate file:

```sh
$ vsplit --env --command 'print-ids.py > OUT-[0I].txt' --pattern \> --n-chunks 20 sequences.fasta | parallel
```

This creates 20 output files, named `OUT-00.txt` through `OUT-19.txt`, each
containing one FASTA sequence id.

### Using a SLURM job array

If you will run your script under SLURM, you can use the `--sbatch` argument
to ask `vsplit` to print an `sbatch` command that will submit a job array to
launch a task for each chunk:

```sh
$ vsplit --sbatch --chunk-offsets-filename chunks.tsv --command process-chunk \
         --pattern \> --n-chunks 100 sequences.fasta
env VSPLIT_INPUT_FILENAME=sequences.fasta VSPLIT_N_CHUNKS=3 \
    VSPLIT_CHUNK_OFFSETS_FILENAME=chunks.tsv \
    sbatch --array=0-99 \
    process-chunk
```

As in the previous example, the chunk details will be communicated by
environment variables (`--env` is implied if you use `--sbatch`).

When using `--sbatch`, you must explicitly specify (via
`--chunk-offsets-filename`) the location for `vsplit` to store the chunk
offset/length information. Obviously, this will need to be a file that will
be accessible to your SLURM jobs once they are started, otherwise your script
will not be able to determine its chunk details.

You can specify additional arguments to be given to `sbatch` using the
`--sbatch-args` option (see `man sbatch` for the many options, including
e.g., specification of the output file via `--output`). Because `vsplit` does
not actually run your command (it just prints it), you can always insert
additional `sbatch` arguments manually before running the command.

Note that your command will be wrapped in a script using the `--wrap` option
of `sbatch`. That means you can include arguments on the command line.

Here's a silly example (just to prove that this works) that would result in a
number of nanoseconds (the output from `date +%N`) appearing as a command-line
argument to `process-chunk` on each invocation.

```sh
$ vsplit --sbatch --chunk-offsets-filename chunks.tsv \
         --command 'process-chunk $(date +%N)'\
         --pattern \> --n-chunks 100 sequences.fasta
```

#### Reading a file chunk in Python in a SLURM job

If your script is written in Python, it can use the `chunk_from_env` function
to read its chunk, exactly as above. The chunk index is obtained from the
SLURM `SLURM_ARRAY_TASK_ID` environment variable for the job array. Based on
this, the chunk offset and length are then taken from the corresponding line
in the chunks TSV file (`chunks.tsv` in the above `vsplit` example). As
above, your code would look something like

```python
from vsplit import chunk_from_env

with chunk_from_env() as fp:
    for line in fp:
        print(line)
```

Or you could read the chunk in binary via `chunk_from_env(binary=True)`.

## Additional details

### If vsplit is slow

If `vsplit` is running for a long time (more than a handful of seconds)
without printing anything, it means your pattern is not being found. The most
likely cause of this is forgetting to use `--eval-pattern` to cause embedded
backslash indicators to be evaluated.

### Buffer size

`vsplit` has a `--buffer-size` argument that can be used to set the size of
the chunks it reads when looking for your pattern. The default is the optimal
filesystem I/O block size (obtained from `os.stat` by Python). If the pieces
of your file (as delimited by your pattern) tend to be bigger than this, you
can increase this value to possibly get a speed gain. `vsplit` will typically
be very fast so you are not likely to need this option.

To give an example, the `sequences.fasta` file used in the examples above
contains SARS-CoV-2 genome sequences that are each about 30,000 characters.
The `>` separator between FASTA sequences will therefore only be found after
reading ~30,000 characters, so if the default buffer size is 4096, there will
typically be seven reads before the next `>` pattern is found. You can see
the default buffer size (for the filesystem where you run the command from)
in the help text for `--buffer-size` when you run `vsplit --help`.

Here's example timing for identifying 100 chunks using the default buffer
size and a 32K one:

```sh
$ time vsplit --pattern \> --n-chunks 100 sequences.fasta > /dev/null

________________________________________________________
Executed in    3.90 secs    fish           external
   usr time    2.00 secs    0.44 millis    2.00 secs
   sys time    1.62 secs    2.21 millis    1.62 secs

$ time vsplit --buffer-size 32000 --pattern \> --n-chunks 100 sequences.fasta > /dev/null

________________________________________________________
Executed in   70.06 millis    fish           external
   usr time   38.81 millis    0.39 millis   38.42 millis
   sys time   14.16 millis    1.73 millis   12.44 millis
```

### Maximum pattern length

`vsplit` reads chunks of the file in its search for your pattern. If the
pattern is not found in a chunk, it will read more of the file and examine
that. To guard against the situation where the chunk it reads ends in the
middle of your pattern, it prepends the final part of the current chunk to
the next chunk. By default, the number of bytes kept is the length of your
pattern minus one. In the case of a fixed-length pattern, this will always be
sufficient to ensure your pattern is not missed. But there is a
`--max-pattern-length` option that you can set to give an alternate value.
This will be useful when support for regular expression patterns is
implemented.

## Todo

Make it possible to use a regular expression to split the file.
