#!/usr/bin/env python3
"""Generate explicit synthetic observations for a fresh-map board capacity test."""
import argparse
import json
from pathlib import Path
from vectors import observations

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--count', type=int, default=10000)
    parser.add_argument('--seed', type=int, default=1)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    with args.output.open('w') as output:
        for observation in observations(args.seed, args.count):
            output.write(json.dumps(observation) + '\n')
