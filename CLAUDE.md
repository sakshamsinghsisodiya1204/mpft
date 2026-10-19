# MPFT - Multipath Reliable File Transfer (CN university project)
Resume: read this + PROGRESS.md, continue from first unfinished phase.

## Constraints
- macOS, Python 3.11+, core = stdlib only. Extras: pytest, matplotlib, fastapi+uvicorn (dashboard), markdown (PDF).
- Stream chunks from disk, never whole file in RAM. Paths emulated by Python TCP proxy (mpft/emulator.py).
- Files <= ~200 lines, clear names, comments only for non-obvious logic (viva-explainable).
- Never commit pcaps, downloads, big test data (generate in temp dirs).

## Protocol (fixed)
20-byte big-endian header: magic "MP"(2) ver(1) type(1) session(4) chunk_index(4) payload_len(4) crc32(first 16 bytes)(4).
Types: 1 HELLO, 2 MANIFEST(JSON), 3 MANIFEST_ACK(JSON held idx), 4 CHUNK, 5 ACK, 6 NACK, 7 DONE, 8 ERROR.
Paths pull chunk idx from shared queue (work stealing); NACK/timeout/dead socket requeue (max 5 retries, exp backoff).
Receiver verifies chunk sha256, writes at offset into file.part, verifies whole-file sha256, renames, sends DONE.

## Contracts
- status/<session>.json written >=1/s (role, session_id, file_name, file_size, total_chunks, chunks_done, retransmissions, per_path[{path_id,bytes,state,throughput_mbit}], hash_status, started_at, updated_at).
- sender.run_transfer(file_path, targets, chunk_size=1048576, corrupt_rate=0.0) -> dict(total_time_s, goodput_mbit, bytes_per_path, retransmitted_chunks, rtt_mean_ms, rtt_jitter_ms, recovery_time_s, success).
- receiver.start_receiver(listen, out_dir) -> handle.stop().
- Emulator config: list of {listen_port,to,delay_ms,jitter_ms,rate_mbit,drop_after_s,corrupt_rate}.

## Layout
mpft/{protocol,sender,receiver,emulator,cli}.py, experiments/, results/, web/, wireshark/, scripts/make_pdfs.py, tests/, docs/, pdf/

## Rules
One commit per logical change on main; after each phase: tests, commit, push, append to PROGRESS.md.
Token-efficient: small edits, `pytest -q | tail`, no file dumps, 1-2 line reports.
Run: .venv/bin/python -m mpft ...; tests: .venv/bin/pytest -q
