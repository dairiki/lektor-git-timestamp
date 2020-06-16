# Lektor-Git-Timestamp

[![PyPI version](https://img.shields.io/pypi/v/lektor-git-timestamp.svg)](https://pypi.org/project/lektor-git-timestamp/)
[![PyPI Supported Python Versions](https://img.shields.io/pypi/pyversions/lektor-git-timestamp.svg)](https://pypi.python.org/pypi/lektor-git-timestamp/)
[![GitHub license](https://img.shields.io/github/license/dairiki/lektor-git-timestamp)](https://github.com/dairiki/lektor-git-timestamp/blob/master/LICENSE)
[![GitHub Actions (Tests)](https://github.com/dairiki/lektor-git-timestamp/workflows/Tests/badge.svg)](https://github.com/dairiki/lektor-git-timestamp)

This Lektor plugin implements a new datetime-like type,
`gittimestamp`, which gets it's default value from git timestamps.
This can be used to implement auto-updating `pub_date` and `last_mod`
fields in Lektor datamodels.

## Description

The `gittimestamp` type behaves just like the built-in `datetime`
type, except that if the field is left blank in `contents.lr` a
default value will be deduced from git timestamps for the file (or
possibly the file’s filesystem mtime.)

If an explicit value for the field is not found, the git log for the
source file (typically `contents.lr`) is searched using `git log
--follow --remove-empty -- <source_filename>`, and the author
timestamp of all matching commits are considered.  Additionally, if
the source file is dirty with respect to git’s HEAD, or if the file is
not checked into the git tree, the file’s mtime is prepended to that
list of timestamps.  That list of timestamps is filtered based on the
`ignore_commits` and `skip_first_commit` options (see below); then,
finally, a timestamp is selected from those that remain based on the
setting of the `strategy` option.

### Options

The `gittimestamp` type supports the following options.

#### `ignore_commits`

This can be set to a string, which is interpreted as a regular
expression.  Any git commits whose commit message matches this pattern
are ignored when computing a default timestamp value for the field.
(The matching is performed using `re.search`.)

#### `skip_first_commit`

If this boolean option is set, the first commit in the git log for the
source file will be ignored.  This is useful for implementing a
`last_mod` field which has a defined value only if the source file has
actually been modified since the initial commit.

#### `strategy`

This option determines which timestamp is selected from the git log
(and/or the file mtime).  This can be set to one of four values:

- `last`: If the source file is dirty (with respect to the git HEAD
    tree), the mtime of the file is used.  Otherwise, the timestamp of
    the last (nominally the most recent) non-ignored git commit is
    used. This is the default strategy.

- `first`: The timestamp of the first (nominally the earliest) commit
    is used.

- `latest`: The latest timestamp is used.  Normally this produces the same
    result at `last`, however due to rebasing, cherry-picking, etc. the git timestamps
    may not be monotonically increasing, in which case this option causes the
    greatest (most recent) timestamp remaining after any filtering to be selected.

- `earliest`: The earliest timestamp is used.  Normally this produces the same
    result at `first`, but if the timestamps in the git log are not monotonic,
    this will select the minimum of all the timestamps remaining after any filtering.

## Examples

Here is a simple example excerpt from a datamodel file:

```ini
<...>

[fields.last_mod]
label = Time last modified
type = gittimestamp

```

On a page using the above datamodel, so long as the `last_mod` field
is left blank in the `contents.lr` file, the page modification time
will be deduced from timestamp of the most recent git commit which
affected that `contents.lr`.  (Or if that file is dirty, the value of
`last_mod` will be taken from the file’s filesystem mtime.)

----

Here is a more complicated example which demonstrates the use of all the options.

```ini
<...>

[fields.pub_date]
label = Time first published
type = gittimestamp
strategy = first

[fields.last_mod]
label = Time last modified
type = gittimestamp
ignore_commits = \[nochange\]
skip_first_commit = true

```

This will get the default value of the `pub_date` field from the
timestamp of the first (earliest) git commit for the source file.

The default value for `last_mod` will, as in the previous example, be taken from the
most recent commit for the file, except that:

- any commits whose commit message include the tag `[nochange]` will be ignored
- the first commit (the one whose timestamp is used for `pub_date`) is ignored

If there has only been one commit of the source file, `last_mod` will not have
a default value.  (It will evaluate to a jinja2 Undefined instance.)

## Author

Jeff Dairiki <dairiki@dairiki.org>
