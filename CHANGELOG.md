# Changelog

## Unreleased

`telemetry-cli` brings four Perl tools into one Python package: `pick`, `recs`,
`recl` and `tgen`. The originals, with their git history, are in `legacy/`.

The command-line interfaces are unchanged. Output is identical to the
originals' except for the fixes listed here.

### Fixes found so far (to be implemented as each tool is ported)

- **pick:** `-l` printed the record number and `-n` the line count, the
  reverse of the documentation. They now match the documentation.
- **pick:** the help listed octal output as `'x'`; it is `'o'`.
- **pick:** the manual page contained unresolved merge-conflict markers.
- **recs:** warnings were printed to stdout, mixed into the extracted records.
  They now go to stderr.
- **recl:** the autocorrelation counted only the first eighth of the bits in
  each buffer, so it usually guessed wrong. `-full`, `-limit` and `-reduce`
  were accepted but ignored.
