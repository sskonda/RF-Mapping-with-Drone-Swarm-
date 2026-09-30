#!/usr/bin/env python3
"""Compile every FPGA RTL/testbench file, create the project, and run all tests."""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
TESTS = {
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
    bad = re.search(r"\*\* (?:Error|Fatal):|Errors: [1-9]|Error loading design", output)
    return output, code == 0 and bad is None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--native-runtime", type=Path,
                        help="Intel install root containing modelsim_ase and modelsim_compat; "
                             "invoke vlog with its private ELF loader, bypassing PRoot")
    parser.add_argument("--seed", type=int, default=20260929)
    args = parser.parse_args()
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

    for top, marker in TESTS.items():
        output, passed = invoke(
            ["vsim", "-c", "-onfinish", "stop", "-t", "1ps", "-sv_seed", str(args.seed),
             "-voptargs=+acc", "-wlf", f"waves/{top}.wlf", f"work.{top}",
             "-do", "simulate.do"], logs / f"{top}.log")
        # ModelSim can return zero after $fatal: require the final PASS and $finish.
        passed = passed and marker in output and "** Note: $finish" in output
        details = [line.removeprefix("# ") for line in output.splitlines()
                   if line.startswith("# PASS")]
        summary["tests"].append({"top": top, "status": "PASS" if passed else "FAIL",
                                  "details": details, "log": f"logs/{top}.log",
                                  "waveform": f"waves/{top}.wlf"})
        print(f"{'PASS' if passed else 'FAIL'} {top}", flush=True)
        if not passed:
            print(output)
        summary_path.write_text(json.dumps(summary, indent=2) + "\n")
    passed = all(test["status"] == "PASS" for test in summary["tests"])
    summary["status"] = "PASS" if passed else "FAIL"
    summary["finished_utc"] = datetime.now(timezone.utc).isoformat()
    summary_path.write_text(json.dumps(summary, indent=2) + "\n")
    print(f"{sum(t['status'] == 'PASS' for t in summary['tests'])}/{len(TESTS)} tests passed.")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
