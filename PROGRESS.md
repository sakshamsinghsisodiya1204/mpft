# Progress

- Setup: repo, venv, CLAUDE.md done.
- Phase 1 done: protocol/receiver/sender/cli + 8 tests pass (20MB loopback in <1s).
- Deviation: status files named status/<role>-<session>.json (sender+receiver can share a machine). DONE is a 2-way handshake (sender DONE -> receiver verifies, replies DONE/ERROR).
- Resume works by hashing existing file.part chunks against manifest.
- Phase 2 done: path kill, silent path timeout, corruption, max-retry, resume (incl. damaged part chunk) tests pass. Path-level backoff added (MAX_PATH_FAILS=6).
- Phase 3 done: emulator.py (delay/jitter/rate/drop/corrupt), topology.example.json, docs/TOPOLOGY.md, 4 tests.
- corrupt_rate in emulator is per 16KiB block; experiments use sender --corrupt-rate (per chunk) for exact %.
