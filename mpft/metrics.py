"""Turns a finished Sender into the metrics dict returned by run_transfer."""
import statistics


def build_result(s, elapsed, ok):
    sent = sum(s.path_bytes.values())  # bytes actually carried this run (excludes resumed chunks)
    return {"total_time_s": elapsed, "goodput_mbit": sent * 8 / 1e6 / elapsed if elapsed else 0.0,
            "bytes_per_path": dict(s.path_bytes), "retransmitted_chunks": s.retransmits,
            "rtt_mean_ms": statistics.fmean(s.rtts) if s.rtts else 0.0,
            "rtt_jitter_ms": statistics.stdev(s.rtts) if len(s.rtts) > 1 else 0.0,
            "recovery_time_s": s.recovery if s.recovery is not None else 0.0,
            "success": ok, "error": s.error, "resumed_chunks": s.resumed,
            "fail_time_s": s.t_fail, "events": s.events}
