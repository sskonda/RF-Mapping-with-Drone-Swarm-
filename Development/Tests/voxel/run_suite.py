#!/usr/bin/env python3
"""Quick/stress/soak evidence with bounded-memory shared-vector integration."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

from vectors import rows
from rf_mapping.voxel import wire
from rf_mapping.voxel.view import SparseMap

ROOT = Path(__file__).resolve().parents[3]
CFILES = [ROOT / 'FPGA/software/voxel' / name for name in ('voxel_core.c', 'voxel_wire.c', 'voxel_app.c')]
HARNESS = Path(__file__).with_name('host_harness.c')

def sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as source:
        while chunk := source.read(65536): digest.update(chunk)
    return digest.hexdigest()

def run(command, cwd=ROOT, timeout=180):
    started = time.monotonic()
    result = subprocess.run(list(map(str, command)), cwd=cwd, capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError(f'{command}\n{result.stdout}\n{result.stderr}')
    return {'command': list(map(str, command)), 'seconds': time.monotonic() - started,
            'stdout': result.stdout.strip(), 'stderr': result.stderr.strip()}

def resident_kib():
    # Sample live RSS: import-time high-water marks can conceal later growth.
    fields = Path('/proc/self/statm').read_text().split()
    return int(fields[1]) * os.sysconf('SC_PAGE_SIZE') // 1024

def check_wire(path, seed, count):
    parser, sparse = wire.Parser(), SparseMap()
    golden = iter(rows(seed, count))
    received = accepted = rejected = snapshots = ends = diagnostics = 0
    started = time.monotonic()
    baseline_rss = None
    sampled_peak_rss = resident_kib()
    with path.open('rb') as source:
        while chunk := source.read(8192):
            for message in parser.feed(chunk):
                assert message.session == 123
                if message.kind == wire.RESULT:
                    row = next(golden)
                    record = wire.update_record(message)
                    total = row[8] | row[9] << 32
                    if total & (1 << 63): total -= 1 << 64
                    xyz = [((v if v < 1 << 31 else v - (1 << 32)) // 500) for v in row[:3]]
                    received += 1
                    assert message.sequence == received and record['voxel'] == xyz
                    assert (record['slot'], record['sum_dbm'], record['count'], record['flags'], record['drone_id'], record['timestamp_us']) == (row[7], total, row[10], row[11], row[12], row[13] | row[14] << 32)
                    if record['flags'] & 2: rejected += 1
                    else:
                        accepted += 1
                        assert record['mean_dbm'] == total / row[10]
                    sparse.apply(record)
                    if received % 10000 == 0:
                        current_rss = resident_kib()
                        if baseline_rss is None: baseline_rss = current_rss
                        sampled_peak_rss = max(sampled_peak_rss, current_rss)
                elif message.kind == wire.SNAPSHOT_SLOT:
                    record = wire.update_record(message)
                    previous = sparse.slots[record['slot']]
                    assert all(record[k] == previous[k] for k in ('voxel', 'sum_dbm', 'count', 'mean_dbm'))
                    snapshots += 1
                elif message.kind == wire.SNAPSHOT_END:
                    assert int.from_bytes(message.payload, 'little') == 1024
                    ends += 1
                elif message.kind == wire.DIAGNOSTIC:
                    import struct
                    counters = struct.unpack('<16Q', message.payload)
                    assert counters[3:10] == (count, count, 0, count, count, accepted, rejected)
                    diagnostics += 1
                assert len(sparse.slots) <= 1024 and len(parser.raw) <= 148
    assert received == count and accepted + rejected == count
    assert next(golden, None) is None and parser.errors == 0
    assert snapshots == 1024 and ends == 1 and diagnostics == 1
    rss = max(sampled_peak_rss, resident_kib())
    if baseline_rss is not None:
        assert rss - baseline_rss < 16384, (baseline_rss, rss)
    return {'count': received, 'accepted': accepted, 'rejected': rejected, 'dropped': 0,
            'snapshots': snapshots, 'parser_errors': parser.errors, 'seconds': time.monotonic() - started,
            'parser_map_sampled_peak_rss_kib': rss, 'parser_warm_rss_kib': baseline_rss, 'rss_growth_after_10000_kib': None if baseline_rss is None else rss - baseline_rss,
            'max_slots': len(sparse.slots)}

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--mode', choices=('quick', 'stress', 'soak'), default='quick')
    p.add_argument('--build', type=Path, default=Path('/tmp/voxel-build'))
    p.add_argument('--native-runtime', type=Path, default=Path.home() / 'intelFPGA/20.1')
    p.add_argument('--rtl', action='store_true')
    args = p.parse_args()
    args.build.mkdir(parents=True, exist_ok=True)
    report_path = ROOT / f'Development/Reports/voxel/{args.mode}.json'
    report = {'status': 'incomplete', 'started_utc': datetime.now(timezone.utc).isoformat(), 'runs': [],
              'mode': args.mode, 'python': sys.version, 'platform': os.uname()._asdict() if hasattr(os.uname(), '_asdict') else list(os.uname()),
              'head': subprocess.check_output(['git','rev-parse','HEAD'], text=True).strip()}
    paths = CFILES + [HARNESS, Path(__file__), Path(__file__).with_name('vectors.py')]
    paths += sorted(Path(__file__).parent.glob('*.c')) + sorted(Path(__file__).parent.glob('*.py'))
    paths += sorted((Path(__file__).parent/'bsp_mock').glob('*.h'))
    paths += sorted((ROOT/'FPGA/software/voxel').glob('*.[ch]'))
    paths += sorted((ROOT/'Mapping/RF_Mapping/src/rf_mapping/voxel').glob('*.py'))
    report['sha256'] = {str(path.relative_to(ROOT)): sha256(path) for path in paths}
    report_path.write_text(json.dumps(report, indent=2)+'\n')
    executable = args.build / 'host_harness'
    command = ['gcc','-std=c11','-O1','-g','-Wall','-Wextra','-Werror','-Wconversion','-Wshadow','-Wpedantic',
               '-fsanitize=address,undefined','-fno-sanitize-recover=all','-fno-omit-frame-pointer','-I',ROOT/'FPGA/software/voxel',*CFILES,HARNESS,'-o',executable]
    report['compiler'] = run(['gcc','--version'])['stdout']
    report['compile'] = run(command)
    report['bsp_mock'] = []
    for mode in ([], ['-DSDT']):
        mock_executable = args.build / ('test_bsp_sdt' if mode else 'test_bsp')
        mock = command[:command.index(HARNESS)] + [ROOT/'Development/Tests/voxel/test_bsp.c',
               '-I', ROOT/'Development/Tests/voxel/bsp_mock', *mode, '-o', mock_executable]
        report['bsp_mock'].append({'compile': run(mock), 'test': run([mock_executable])})
    report['python_tests'] = run([sys.executable, '-m', 'unittest', 'discover', '-s', 'Development/Tests/voxel', '-p', 'test_host.py', '-v'])
    seeds = range(1, 11) if args.mode == 'stress' else [42 if args.mode == 'soak' else 1]
    count = {'quick': 10000, 'stress': 100000, 'soak': 1000000}[args.mode]
    try:
        for seed in seeds:
            vector = args.build / f'seed{seed}.vec'
            with vector.open('w') as output:
                for row in rows(seed, count): output.write(' '.join(f'{word:08x}' for word in row)+'\n')
            wire_path, memory = args.build / 'output.wire', args.build / 'rss.txt'
            entry = {'seed': seed, 'count': count, 'vectors_sha256': sha256(vector)}
            entry['host'] = run(['/usr/bin/time','-f','%e %M','-o',memory,executable,vector,wire_path,seed])
            entry['host']['time_seconds_peak_rss_kib'] = memory.read_text().strip()
            assert int(memory.read_text().split()[1]) < 65536, 'C peak RSS exceeds 64 MiB bound'
            entry['integration'] = check_wire(wire_path, seed, count)
            if args.rtl:
                rtl_vector = args.build / 'rtl.vec'
                with rtl_vector.open('w') as out:
                    for row in rows(seed, 10000): out.write(' '.join(f'{v:08x}' for v in row)+'\n')
                entry['rtl'] = run([sys.executable, ROOT/'FPGA/modelsim/run_regression.py', '--native-runtime',args.native_runtime,
                                    '--only','tb_voxel_shared_vectors','--vectors',rtl_vector,'--seed',seed,'--no-waves'])
                entry['rtl_results'] = json.loads((ROOT/'FPGA/modelsim/logs/results.json').read_text())
            report['runs'].append(entry)
            report_path.write_text(json.dumps(report, indent=2)+'\n')
            print(f'PASS seed={seed} host={count} accepted={entry["integration"]["accepted"]} rejected={entry["integration"]["rejected"]}', flush=True)
            vector.unlink()
        report['status'] = 'PASS'
    except Exception as error:
        report['status'] = 'FAIL'; report['error'] = str(error); raise
    finally:
        report['finished_utc'] = datetime.now(timezone.utc).isoformat()
        report_path.write_text(json.dumps(report, indent=2)+'\n')

if __name__ == '__main__':
    main()
