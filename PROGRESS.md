# Progress

- Setup: repo, venv, CLAUDE.md done.
- Phase 1 done: protocol/receiver/sender/cli + 8 tests pass (20MB loopback in <1s).
- Deviation: status files named status/<role>-<session>.json (sender+receiver can share a machine). DONE is a 2-way handshake (sender DONE -> receiver verifies, replies DONE/ERROR).
- Resume works by hashing existing file.part chunks against manifest.
- Phase 2 done: path kill, silent path timeout, corruption, max-retry, resume (incl. damaged part chunk) tests pass. Path-level backoff added (MAX_PATH_FAILS=6).
- Phase 3 done: emulator.py (delay/jitter/rate/drop/corrupt), topology.example.json, docs/TOPOLOGY.md, 4 tests.
- corrupt_rate in emulator is per 16KiB block; experiments use sender --corrupt-rate (per chunk) for exact %.
- Phase 4 done: 7 experiments run at 50MB -> results/*.csv + 6 PNGs. Re-run: python experiments/run_experiments.py && python experiments/plot_results.py (~3 min).
- Retries use PriorityQueue (retransmit before fresh chunks): recovery 6.9s -> 0.22s.
- Findings: 1 path 23 Mbit/s of 40 (stop-and-wait per chunk); 8 paths 172; chunk 64K 50 vs 1M 107 Mbit/s.
- Phase 5 done: wireshark/mpft.lua (Lua syntax-checked only; no Wireshark here), CAPTURE.md, docs/REMOTE.md (untested on real hardware).
- Phase 6 done: web/app.py + static html/css/js, `python -m mpft dashboard --port 8080`; verified live in browser. status JSON gained file_sha256.
- Phase 7 done: README + docs/{PROTOCOL,ARCHITECTURE,TEST_REPORT,DEMO_SCRIPT,VIVA_PREP,WALKTHROUGH,CONTRIBUTIONS}.md written from real CSVs.
- Phase 8 done: scripts/make_pdfs.py (markdown + headless Chrome, images embedded) -> pdf/*.pdf and pdf/MPFT_Report.pdf (22 pages). Re-run after editing docs.
