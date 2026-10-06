#!/usr/bin/env python3
"""Fail closed unless the actual GNU link map places the entire mirror in DDR."""
import argparse
from pathlib import Path
import re


def check(text, ddr_start, ddr_end):
    match = re.search(r'^\.voxel_ddr\s+(?:\n\s*)?(0x[0-9a-fA-F]+)\s+(0x[0-9a-fA-F]+)', text, re.M)
    if not match:
        raise ValueError('missing .voxel_ddr output section; orphan placement is not accepted')
    start, size = map(lambda v: int(v, 16), match.groups())
    if not size or start % 64 or size % 64 or not ddr_start <= start < start + size <= ddr_end:
        raise ValueError(f'.voxel_ddr is not aligned and entirely in DDR: {start:#x}+{size:#x}')
    for symbol, expected in (('__voxel_ddr_start', start), ('__voxel_ddr_end', start + size)):
        value = re.search(r'(?m)^\s*(0x[0-9a-fA-F]+)\s+' + symbol + r'\b', text)
        if value is None or int(value.group(1), 16) != expected:
            raise ValueError(f'missing/inconsistent linker assertion symbol {symbol}')
    return {'address': hex(start), 'bytes': size, 'DDR_end_exclusive': hex(ddr_end)}

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('map', type=Path)
    parser.add_argument('--ddr-start', type=lambda v: int(v, 0), required=True)
    parser.add_argument('--ddr-end', type=lambda v: int(v, 0), required=True, help='exclusive; from actual BSP memory region')
    args = parser.parse_args()
    print(check(args.map.read_text(), args.ddr_start, args.ddr_end))
