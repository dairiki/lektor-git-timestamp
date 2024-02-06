## Changelog

### Release 1.0.0 (2024-02-06)

No code changes from 1.0.0b3

### Release 1.0.0b3 (2024-01-23)

#### Breaking Changes

- Drop support for python 3.8.
- The default value for the `follow_renames` global config setting has
  changed from _true_ to _false_.

#### Bugs Fixed

- Fix to work when [alternatives] are enabled. Note that in this case
  the `follow_renames` global option is not supported.

#### Testing

- Test under python 3.12.

#### Code Style

- Style: Use [ruff] for style linting and formatting. This replaces
  our usage of `black`, `reorder-python-imports`, and `flake8`.

[alternatives]: https://www.getlektor.com/docs/content/alts/
[ruff]: https://docs.astral.sh/ruff/

### Release 1.0.0b2 (2023-06-15)

- Added type annotations.
- Convert packaging to PDM.

#### Code Style

- Style: Run [black] and [reorder-python-imports] on code. Configure
  [pre-commit] to keep all up-to-date.

#### Tests

- Disuse the deprecated module `pkg_resources`.

#### Buglets

- Do not strip trailing whitespace from `git log` output. (This was
  erroneously removing trailing newlines from the final commit
  message.)

[black]: https://github.com/psf/black
[pre-commit]: https://pre-commit.com/
[reorder-python-imports]: https://github.com/asottile/reorder-python-imports

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
