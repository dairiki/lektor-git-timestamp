## Changelog

### Release 1.0.0b1 (2023-04-11)

- Drop support for python 2.7 and 3.6. ([#2])

#### Testing

- Test under python 3.10 and 3.11. ([#2])

- Test that `lektor.db.Record.get_sort_key` works with
  descriptor-valued fields. (This requires `lektor>=3.3`.)

[#2]: https://github.com/dairiki/lektor-git-timestamp/pull/2


### Release 0.1.0.post1 (2021-08-12)

No code changes.

Add warning to README about `lektor > 3.2` (not yet released) being
required in order to be able to sort records by `gittimestamp` fields.

### Release 0.1 (2021-02-05)

No code changes.

Update development status classifier to "stable".

Add functional tests.

### Release 0.1a2 (2021-02-03)

#### Bugs Fixed

Fixed attrocious typo which prevented the use of anything other than the
default `strategy=last` for picking timestamps.

### Release 0.1a1 (2020-06-16)

Initial release.

