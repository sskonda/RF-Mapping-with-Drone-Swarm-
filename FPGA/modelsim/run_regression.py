#!/usr/bin/env python3
"""Compile every FPGA RTL/testbench file, create the project, and run all tests."""

import argparse
from datetime import datetime, timezone
import json
import hashlib
import time
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
TESTS = {
    "tb_voxel_shared_vectors": "PASS shared vectors",
    "tb_voxel_dma_readout": "PASS all readout configurations",
    "tb_voxel_dma_pipeline": "PASS all DMA pipeline configurations",
    "axis_passthrough_tb": "PASS: all axis passthrough configurations",
    "rf_packet_unpacker_tb": "PASS: 11 observations accepted",
    "voxel_tb": "PASS: all voxel cases completed",
    "rf_voxel_pipeline_tb": "PASS: unpacker -> voxel:",
    "tb_voxel_lookup": "PASS: all voxel lookup configurations",
    "tb_voxel_accumulator": "PASS: all accumulator configurations",
    "tb_voxel_accumulator_pipeline": "PASS pipeline:",
}


def invoke(command, logfile, env=None):
    try:
        result = subprocess.run(command, cwd=ROOT, env=env, text=True,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                timeout=120)
        output, code = result.stdout, result.returncode
    except subprocess.TimeoutExpired as error:
        output = error.stdout or b""
        if isinstance(output, bytes):
            output = output.decode(errors="replace")
        output += "\nERROR: host timeout after 120 seconds\n"
        code = 124
    logfile.write_text(output)
    bad = re.search(r"\*\* (?:Error|Fatal):|Errors: [1-9]|Warnings: [1-9]|Error loading design", output)
    return output, code == 0 and bad is None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--native-runtime", type=Path,
                        help="Intel install root containing modelsim_ase and modelsim_compat; "
                             "invoke vlog with its private ELF loader, bypassing PRoot")
    parser.add_argument("--seed", type=int, default=20260929)
    parser.add_argument("--only", choices=TESTS)
    parser.add_argument("--vectors", type=Path)
    parser.add_argument("--no-waves", action="store_true")
    parser.add_argument("--no-stalls", action="store_true", help="shared-vector throughput measurement")
    args = parser.parse_args()
    if args.vectors is None:
        args.vectors = ROOT / "logs/shared.vec"
        args.vectors.parent.mkdir(exist_ok=True)
        subprocess.run([sys.executable, str(ROOT.parents[1] / "Development/Tests/voxel/vectors.py"),
                        str(args.vectors), "--seed", str(args.seed), "--count", "10000"], check=True)
    args.vectors = args.vectors.resolve()
    logs, waves = ROOT / "logs", ROOT / "waves"
    logs.mkdir(exist_ok=True)
    waves.mkdir(exist_ok=True)
    # Never leave an old PASS summary after a failed compile or project creation.
    summary = {"started_utc": datetime.now(timezone.utc).isoformat(),
               "seed": args.seed, "status": "incomplete", "tests": []}
    summary_path = logs / "results.json"
    summary_path.write_text(json.dumps(summary, indent=2) + "\n")

    version = subprocess.check_output(["vsim", "-version"], text=True).strip()
    summary["simulator"] = version
    summary["command"] = sys.argv
    summary["runner_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    summary["head"] = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    summary["vectors_sha256"] = hashlib.sha256(args.vectors.read_bytes()).hexdigest()
    if not (ROOT / "work").exists():
        subprocess.run(["vlib", "work"], cwd=ROOT, check=True)
    sources = sorted((ROOT.parent / "rtl").glob("*.sv"))
    sources += sorted((ROOT.parent / "rtl").glob("*.v"))
    sources += sorted((ROOT.parent / "tb").glob("*.sv"))
    source_names = [os.path.relpath(path, ROOT) for path in sources]
    compiler, compiler_env = ["vlog"], os.environ.copy()
    if args.native_runtime:
        install = args.native_runtime.expanduser().resolve()
        libs = install / "modelsim_compat/usr/lib/i386-linux-gnu"
        compiler = [str(libs / "ld-linux.so.2"),
                    str(install / "modelsim_ase/linuxaloem/vlog")]
        compiler_env["LD_LIBRARY_PATH"] = str(libs)
    summary["sources"] = source_names
    summary["sha256"] = {name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in zip(source_names, sources)}
    started = time.monotonic()
    output, passed = invoke(compiler + ["-sv", "-work", "work"] + source_names,
                            logs / "compile.log", compiler_env)
    if not passed:
        print(output)
        return 1
    print(f"Compiled {len(sources)} files without errors.", flush=True)

    # Reuse an existing project so a rerun preserves the user's GUI settings.
    if not (ROOT / "rf_mapping.mpf").exists():
        output, passed = invoke(["vsim", "-c", "-do", "create_project.do"],
                                logs / "create_project.log")
        if not passed:
            print(output)
            return 1

    selected = {args.only: TESTS[args.only]} if args.only else TESTS
    for top, marker in selected.items():
        test_started = time.monotonic()
        output, passed = invoke(
            ["vsim", "-c", "-onfinish", "stop", "-t", "1ps", "-sv_seed", str(args.seed),
             "-voptargs=+acc", "-wlf", f"waves/{top}.wlf", f"work.{top}",
             f"+VECTORS={args.vectors}", f"+SEED={args.seed}",
             "+NO_STALL" if args.no_stalls else "+RANDOM_STALLS",
             "-do", "simulate_no_waves.do" if args.no_waves else "simulate.do"], logs / f"{top}.log")
        # ModelSim can return zero after $fatal: require the final PASS and $finish.
        passed = passed and marker in output and "** Note: $finish" in output
        details = [line.removeprefix("# ") for line in output.splitlines()
                   if line.startswith("# PASS")]
        summary["tests"].append({"top": top, "status": "PASS" if passed else "FAIL",
                                  "duration_seconds": time.monotonic()-test_started, "details": details, "log": f"logs/{top}.log",
                                  "waveform": f"waves/{top}.wlf"})
        print(f"{'PASS' if passed else 'FAIL'} {top}", flush=True)
        if not passed:
            print(output)
        summary_path.write_text(json.dumps(summary, indent=2) + "\n")
    passed = all(test["status"] == "PASS" for test in summary["tests"])
    summary["status"] = "PASS" if passed else "FAIL"
    summary["duration_seconds"] = time.monotonic() - started
    summary["finished_utc"] = datetime.now(timezone.utc).isoformat()
    summary_path.write_text(json.dumps(summary, indent=2) + "\n")
    print(f"{sum(t['status'] == 'PASS' for t in summary['tests'])}/{len(selected)} tests passed.")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
