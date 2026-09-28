# Legacy Perl sources

These are the original Perl tools that `telemetry-cli` replaces, imported with
their full git history from:

- https://github.com/donalgrant/pick
- https://github.com/donalgrant/recs
- https://github.com/donalgrant/recl
- https://github.com/donalgrant/tgen

`Util/Msg.pm` comes from https://github.com/donalgrant/Util. recs and recl
need it.

The files are kept unmodified. The test suite runs them to generate reference
output (see `tools/make_golden.py`). To run one by hand:

```console
$ perl -I legacy legacy/recl/recl legacy/recs/testfile
```
