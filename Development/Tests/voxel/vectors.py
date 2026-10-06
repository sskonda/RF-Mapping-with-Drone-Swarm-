#!/usr/bin/env python3
"""Independent integer/dictionary golden model shared by host C and RTL."""
import argparse
import random
from pathlib import Path

SLOTS = 1024
MASK = (1 << 32) - 1

def observations(seed, count):
    rng = random.Random(seed)
    boundary = [-(1 << 31), (1 << 31)-1, -501, -500, -499, -1, 0, 499, 500, 501]
    for index in range(count):
        if index < SLOTS:
            xyz = (index * 500, 0, 0)
        elif index % 5 == 0:
            xyz = (rng.randrange(SLOTS) * 500 + rng.randrange(500), 0, 0)
        elif index % 5 == 1:
            xyz = (rng.randrange(SLOTS + 1, SLOTS + 200) * 500, -500, 500)
        elif index % 5 == 2:
            xyz = (boundary[rng.randrange(len(boundary))], -1, 500)
        else:
            xyz = (rng.randrange(SLOTS) * 500, 0, 0)
        rssi = (-(1 << 31), (1 << 31)-1, -63, -67, -99)[index % 5]
        drone = (0, MASK, 101, 202)[index % 4]
        time = (0, (1 << 32)-1, 1 << 32, (1 << 64)-1, (index << 32) | index)[index % 5]
        yield (*xyz, rssi, drone, time)

def rows(seed, count):
    model = {}
    for x, y, z, rssi, drone, time in observations(seed, count):
        key = (x // 500, y // 500, z // 500)
        flags = 0
        if key not in model and len(model) < SLOTS:
            model[key] = [len(model), 0, 0]
            flags = 1
        if key not in model:
            slot, total, samples, flags = 0, 0, 0, 2
        else:
            state = model[key]
            state[1] += rssi
            state[2] += 1
            slot, total, samples = state
        words = (x, y, z, rssi, drone, time & MASK, time >> 32,
                 slot, total & MASK, (total >> 32) & MASK, samples, flags,
                 drone, time & MASK, time >> 32)
        yield tuple(w & MASK for w in words)

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('output', type=Path)
    parser.add_argument('--seed', type=int, default=1)
    parser.add_argument('--count', type=int, default=10000)
    args = parser.parse_args()
    with args.output.open('w') as out:
        for row in rows(args.seed, args.count):
            out.write(' '.join(f'{v:08x}' for v in row) + '\n')
