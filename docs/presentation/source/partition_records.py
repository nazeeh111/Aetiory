"""Owned CSV workload with an intentionally retained floor-allocation defect. Python3.12+."""
import csv
import itertools
import json
import sys
from pathlib import Path


def planned_capacity(rows, workers):
    return len(rows) // workers


def partition_records(rows, workers):
    capacity = planned_capacity(rows, workers)
    return list(itertools.batched(rows, capacity))


def main():
    rows = list(csv.DictReader(Path(sys.argv[1]).read_text().splitlines()))
    batches = partition_records(rows, int(sys.argv[2]))
    recovered = [record for batch in batches for record in batch]
    assert recovered == rows
    print(json.dumps({'records': len(recovered), 'batches': len(batches),
                      'total': sum(int(row['amount']) for row in recovered)}, sort_keys=True))


if __name__ == '__main__':
    main()
