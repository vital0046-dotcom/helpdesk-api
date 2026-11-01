"""Compare nested loops O(n*k) with a dictionary pass O(n) over JSONL access logs."""

import argparse
import json
from collections import Counter
from pathlib import Path
from time import perf_counter


def read_logs(path):
    entries, skipped = [], 0
    with Path(path).open(encoding="utf-8") as file:
        for line in file:
            try:
                row = json.loads(line)
                if (
                    not isinstance(row, dict)
                    or not isinstance(row.get("path"), str)
                    or type(row.get("status")) is not int
                    or not 100 <= row["status"] <= 599
                ):
                    raise ValueError("Invalid log entry")
                entries.append(row)
            except (ValueError, TypeError):
                skipped += 1
    return entries, skipped


def nested_counts(entries):
    result = {}
    for path in {entry["path"] for entry in entries}:
        count = 0
        for entry in entries:
            if entry["path"] == path:
                count += 1
        result[path] = count
    return result


def optimized_counts(entries):
    return dict(Counter(entry["path"] for entry in entries))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path")
    parser.add_argument(
        "--repeat", type=int, default=1, help="Repeat records for benchmark (1..10000)"
    )
    args = parser.parse_args()
    if not 1 <= args.repeat <= 10000:
        parser.error("--repeat must be in 1..10000")
    entries, skipped = read_logs(args.path)
    entries = entries * args.repeat
    timings, results = {}, []
    for fn in (nested_counts, optimized_counts):
        start = perf_counter()
        result = fn(entries)
        timings[fn.__name__] = round((perf_counter() - start) * 1000, 4)
        results.append(result)
    assert results[0] == results[1]
    print(
        json.dumps(
            {
                "records": len(entries),
                "skipped_lines": skipped,
                "requests_by_path": results[1],
                "client_errors": sum(400 <= e["status"] < 500 for e in entries),
                "server_errors": sum(500 <= e["status"] < 600 for e in entries),
                "time_ms": timings,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
