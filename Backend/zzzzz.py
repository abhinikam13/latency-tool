import os
import csv
import re
import requests
from datetime import datetime, timezone, timedelta

# ── ClickHouse Configuration ──────────────────────────────────────────────────
CH_HOST = "34.100.173.221"
CH_USER = "admin"
CH_PASS = "27ff0399-0d3a-4bd8-919d-17c2181e6fb9"
CH_URL  = f"http://{CH_HOST}:8123/"

CH_TIME_FROM = "2026-06-22 10:00:31"
CH_TIME_TO   = "2026-06-22 20:00:00"
CH_TIMEZONE  = "Asia/Calcutta"

CIDs = [
  "19eeddffe92-6bc2dd33",
  "19eedea9022-2531c635",
  "19eedf07b16-4551e898",
  "19eedf35132-b1de8821",
  "19eedf66058-6c30d775",
  "19eedf9a5fe-37b006ba",
  "19eedfe69d2-90c0beb8",
  "19eee0191c0-1e02b4f1",
  "19eee04534f-8fdd96d0",
  "19eee0709b8-a529702e"
]

CONFIG = {
    "time_from": CH_TIME_FROM,
    "time_to":   CH_TIME_TO,
    "timezone":  CH_TIMEZONE,
    "cids":      CIDs,
}

IST = timezone(timedelta(hours=5, minutes=30))

# ── Timestamp parser ──────────────────────────────────────────────────────────
def parse_ts(ts_str: str):
    """
    Handles two formats:
      - LogChef ISO:   2026-06-10T23:48:27.602+05:30
      - Embedded log:  2026-06-10 18:18:27,602
    """
    ts_str = ts_str.strip()
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            return datetime.strptime(ts_str, fmt)
        except ValueError:
            pass
    ts_str2 = ts_str.replace(',', '.')
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(ts_str2, fmt).replace(tzinfo=IST)
        except ValueError:
            pass
    return None


# ── Regex patterns (verified against actual logs) ────────────────────────────
#
# TURN START  : orchestrator-main  → "VAD voice_activity_detected"
# LLM START   : orchestrator-main  → "SENT TO LLM 2"
# LLM END     : llm-deployment     → "END sending to orchestrator 1.23s"
#               ↳ The float value IS the LLM elapsed time — no delta needed.
# TOOL CALL   : llm-deployment     → "TOOL_CALL sending" / "ToolMessage received"
# SYNTH       : synthesizer-deployment → "Audio received from synthesizer providers 0.28"
#
RE_LLM_END   = re.compile(r"END sending to orchestrator\s+([\d.]+)s", re.IGNORECASE)
RE_SYNTH_LAT = re.compile(r"Audio received from synthesizer providers\s+([\d.]+)", re.IGNORECASE)
RE_TOOL_CALL = re.compile(r"TOOL_CALL sending", re.IGNORECASE)
RE_TOOL_RES  = re.compile(r"ToolMessage received", re.IGNORECASE)
RE_TRANS_END = re.compile(r"\\?['\"]?type\\?['\"]?\s*[:=]\s*\\?['\"]?final", re.IGNORECASE)


# ── CSV loaders ───────────────────────────────────────────────────────────────
def is_logchef_format(csv_path: str) -> bool:
    with open(csv_path, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        return "pod_name" in (reader.fieldnames or [])


def load_logchef_csv(csv_path: str, cid_list: list) -> dict:
    """LogChef 16-col export: uses 'timestamp' and 'log' columns."""
    calls = {}
    with open(csv_path, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            ts = parse_ts(row.get("timestamp", ""))
            log = row.get("log", "")
            if ts is None:
                continue
            cid = next((c for c in cid_list if c in log), None)
            if cid:
                calls.setdefault(cid, []).append((ts, log))
    for cid in calls:
        calls[cid].sort(key=lambda x: x[0])
    print(f"    ✓ LogChef CSV: {sum(len(v) for v in calls.values())} rows across {len(calls)} CIDs")
    return calls


def load_standard_csv(csv_path: str) -> dict:
    """Standard ClickHouse-fetched CSV: call_sid, conversation_id, timestamp, log."""
    calls = {}
    with open(csv_path, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            sid = row.get("call_sid", "") or row.get("conversation_id", "")
            ts  = parse_ts(row.get("timestamp", ""))
            if ts is None or not sid:
                continue
            calls.setdefault(sid, []).append((ts, row.get("log", "")))
    for cid in calls:
        calls[cid].sort(key=lambda x: x[0])
    return calls


# ── ClickHouse fetcher ────────────────────────────────────────────────────────
def fetch_clickhouse_logs_bulk(cid_list, output_csv):
    print(f"  Fetching logs for {len(cid_list)} CIDs from ClickHouse...")
    conditions = " OR ".join(
        [f"positionCaseInsensitive(log, '{c}') > 0" for c in cid_list]
    )
    query = f"""
SELECT timestamp, log
FROM audit_db.ml_infra_logs
WHERE timestamp BETWEEN toDateTime('{CONFIG["time_from"]}', '{CONFIG["timezone"]}')
                    AND toDateTime('{CONFIG["time_to"]}', '{CONFIG["timezone"]}')
  AND ({conditions})
ORDER BY timestamp ASC
LIMIT 100000
SETTINGS max_execution_time = 600
"""
    try:
        r = requests.post(CH_URL, params={"query": query},
                          auth=(CH_USER, CH_PASS), timeout=600)
        if r.status_code == 200:
            lines = r.text.strip().splitlines()
            print(f"    ✓ Fetched {len(lines)} rows")
            with open(output_csv, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f,
                    fieldnames=["call_sid", "conversation_id", "timestamp", "log"])
                writer.writeheader()
                for line in lines:
                    parts = line.split("\t", 1)
                    if len(parts) == 2:
                        ts, msg = parts
                        cid = next((c for c in cid_list if c in msg), None)
                        if cid:
                            writer.writerow({
                                "call_sid": cid, "conversation_id": cid,
                                "timestamp": ts, "log": msg
                            })
        else:
            print(f"    ✗ ClickHouse error: {r.text[:200]}")
    except Exception as e:
        print(f"    ✗ Exception: {e}")


# ── Core latency parser ───────────────────────────────────────────────────────
def parse_latencies(csv_path: str, cid_list: list) -> dict:
    """
    Per-turn latency extraction.

    Turn lifecycle (actual log events):
      TURN START : VAD voice_activity_detected          (orchestrator-main)
      LLM START  : SENT TO LLM 2                        (orchestrator-main)
      LLM END    : END sending to orchestrator X.XXs    (llm-deployment)
                   ↳ X.XX is the authoritative LLM elapsed time (no delta).
      TOOL CALL  : TOOL_CALL sending / ToolMessage received (llm-deployment)
      SYNTH      : Audio received from synthesizer providers X.XX (synthesizer-deployment)

    Key fix vs v2:
      - Removed "LLM_MESSAGE_END_RECEIVED" (does NOT exist in logs).
      - LLM latency = float extracted from "END sending to orchestrator Xs"
        (self-reported elapsed time by the LLM service — most accurate).
      - SENT TO LLM is still tracked but only used to confirm turn pairing,
        not for delta calculation.
    """
    if is_logchef_format(csv_path):
        print("    Detected LogChef export format")
        calls = load_logchef_csv(csv_path, cid_list)
    else:
        print("    Detected standard ClickHouse CSV format")
        calls = load_standard_csv(csv_path)

    print(f"    Loaded {len(calls)} CIDs with data")

    latency_data = {}

    for sid, rows in calls.items():
        turns       = []
        cur         = None
        turn_idx    = 0

        for ts, log in rows:

            # ── TURN OPEN ────────────────────────────────────────────────
            if "VAD voice_activity_detected" in log:
                if cur is not None:
                    turns.append(cur)
                turn_idx += 1
                cur = {
                    "turn_index":      turn_idx,
                    "turn_start_ts":   ts,
                    "trans_start_ts":  ts,
                    "trans_end_ts":    None,
                    "trans_latency":   None,
                    "llm_send_ts":     None,
                    "llm_latency":     None,   # ← extracted float from log
                    "synth_latency":   None,
                    "has_tool_call":   False,
                    "tool_call_ts":    None,
                    "tool_result_ts":  None,
                    "tool_duration":   0.0,
                }
                continue

            if cur is None:
                continue

            # ── TRANSCRIBER END (final transcript) ──────────────────────────
            if RE_TRANS_END.search(log) and cur["trans_end_ts"] is None:
                cur["trans_end_ts"] = ts
                if cur["trans_start_ts"] is not None:
                    cur["trans_latency"] = (ts - cur["trans_start_ts"]).total_seconds()

            # ── LLM SEND (turn confirmation) ─────────────────────────────
            if "SENT TO LLM" in log and cur["llm_send_ts"] is None:
                cur["llm_send_ts"] = ts

            # ── TOOL CALL tracking ───────────────────────────────────────
            if RE_TOOL_CALL.search(log):
                cur["has_tool_call"] = True
                if cur["tool_call_ts"] is None:
                    cur["tool_call_ts"] = ts

            if RE_TOOL_RES.search(log) and cur["tool_call_ts"] is not None:
                if cur["tool_result_ts"] is None:
                    cur["tool_result_ts"] = ts
                    cur["tool_duration"] = (ts - cur["tool_call_ts"]).total_seconds()

            # ── LLM END — extract elapsed value directly ─────────────────
            # "END sending to orchestrator 1.23s"
            # This is self-reported by llm-deployment — most accurate signal.
            m_llm = RE_LLM_END.search(log)
            if m_llm and cur["llm_latency"] is None:
                cur["llm_latency"] = float(m_llm.group(1))

            # ── SYNTH + TURN CLOSE ───────────────────────────────────────
            m_synth = RE_SYNTH_LAT.search(log)
            if m_synth and cur["synth_latency"] is None:
                cur["synth_latency"] = float(m_synth.group(1))
                turns.append(cur)
                cur = None

        if cur is not None:
            turns.append(cur)

        if not turns:
            latency_data[sid] = _empty_metrics()
            continue

        def avg(vals): return sum(vals) / len(vals) if vals else 0.0
        def mx(vals):  return max(vals) if vals else 0.0

        no_tool  = [t for t in turns if not t["has_tool_call"]]
        w_tool   = [t for t in turns if t["has_tool_call"]]

        llm_no_tool   = [t["llm_latency"]  for t in no_tool if t["llm_latency"]  is not None]
        synth_no_tool = [t["synth_latency"] for t in no_tool if t["synth_latency"] is not None]
        trans_no_tool = [t["trans_latency"] for t in no_tool if t["trans_latency"] is not None]

        # For tool turns: pure LLM = total_llm - tool_duration
        llm_tool_total = [t["llm_latency"]  for t in w_tool if t["llm_latency"]  is not None]
        tool_durs      = [t["tool_duration"] for t in w_tool if t["tool_duration"] > 0]
        llm_tool_pure  = [t["llm_latency"] - t["tool_duration"]
                          for t in w_tool
                          if t["llm_latency"] is not None and t["tool_duration"] > 0]
        trans_w_tool   = [t["trans_latency"] for t in w_tool if t["trans_latency"] is not None]

        latency_data[sid] = {
            # ── User-experience turns (no tool calls) ──
            "turns_no_tools":      len(no_tool),
            "avg_llm":             avg(llm_no_tool),
            "max_llm":             mx(llm_no_tool),
            "avg_synth":           avg(synth_no_tool),
            "avg_trans":           avg(trans_no_tool),
            # ── Tool-call turns ────────────────────────
            "turns_with_tools":    len(w_tool),
            "avg_llm_tools_total": avg(llm_tool_total),
            "max_llm_tools_total": mx(llm_tool_total),
            "avg_llm_tools_pure":  avg(llm_tool_pure),
            "avg_tool_duration":   avg(tool_durs),
            "avg_trans_tools":     avg(trans_w_tool),
        }

    return latency_data


def _empty_metrics():
    return {
        "turns_no_tools": 0, "avg_llm": 0.0, "max_llm": 0.0, "avg_synth": 0.0, "avg_trans": 0.0,
        "turns_with_tools": 0, "avg_llm_tools_total": 0.0,
        "max_llm_tools_total": 0.0, "avg_llm_tools_pure": 0.0,
        "avg_tool_duration": 0.0, "avg_trans_tools": 0.0,
    }


# ── Report generator ──────────────────────────────────────────────────────────
def generate_report(metrics: dict, cid_list: list, report_file="LATENCY_REPORT.txt"):
    W = 125
    hdr = (f"{'Conversation ID':<28} | {'Turns':^6} | "
           f"{'Avg LLM':^10} | {'Max LLM':^10} | {'Avg Synth':^10} | {'Avg Trans':^10}")
    div = "─" * W

    lines = [
        "=" * W,
        "  LATENCY REPORT v4  —  LLM latency from 'END sending to orchestrator Xs', Transcriber from final transcript",
        f"  Window : {CONFIG['time_from']} → {CONFIG['time_to']}",
        f"  CIDs   : {len(cid_list)}",
        "=" * W, "",
        div, hdr, div,
    ]
    for cid in cid_list:
        m = metrics.get(cid)
        if m and m["turns_no_tools"] > 0:
            lines.append(
                f"{cid:<28} | {m['turns_no_tools']:^6} | "
                f"{m['avg_llm']:>9.2f}s | {m['max_llm']:>9.2f}s | "
                f"{m['avg_synth']:>9.2f}s | {m['avg_trans']:>9.2f}s"
            )
        else:
            lines.append(f"{cid:<28} | {'—':^6} | {'no data':^10}")
    lines += [div]

    report_text = "\n".join(lines)
    with open(report_file, "w", encoding="utf-8") as f:
        f.write(report_text)
    print(f"\n✓ Report written to: {report_file}")
    print("\n" + report_text)


# ── Entry point ───────────────────────────────────────────────────────────────
def main(cids=None, time_from=None, time_to=None, timezone=None, logchef_csv=None):
    if cids:       CONFIG["cids"]      = cids
    if time_from:  CONFIG["time_from"] = time_from
    if time_to:    CONFIG["time_to"]   = time_to
    if timezone:   CONFIG["timezone"]  = timezone

    cid_list = list(dict.fromkeys(CONFIG["cids"]))
    if not cid_list:
        print("No CIDs provided.")
        return

    print(f"── Latency Analyzer v3  ({len(cid_list)} CIDs) ──\n")

    if logchef_csv:
        print(f"Step 1 — Using LogChef CSV: {logchef_csv}")
        src = logchef_csv
    else:
        print("Step 1 — Fetching from ClickHouse...")
        src = "logs.csv"
        fetch_clickhouse_logs_bulk(cid_list, src)

    print("\nStep 2 — Parsing latencies...")
    metrics = parse_latencies(src, cid_list)

    print("\nStep 3 — Generating report...")
    generate_report(metrics, cid_list)

    return {"status": "success", "report_file": "LATENCY_REPORT.txt"}


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="Latency Analyzer v3")
    p.add_argument("--cids",         nargs="+")
    p.add_argument("--time-from")
    p.add_argument("--time-to")
    p.add_argument("--timezone")
    p.add_argument("--logchef-csv",  help="Path to LogChef export CSV (skips ClickHouse)")
    args = p.parse_args()
    main(
        cids=args.cids,
        time_from=args.time_from,
        time_to=args.time_to,
        timezone=args.timezone,
        logchef_csv=args.logchef_csv,
    )