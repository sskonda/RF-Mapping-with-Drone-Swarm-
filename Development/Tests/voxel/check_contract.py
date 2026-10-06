#!/usr/bin/env python3
"""Verify exported parameters; record immutable hardware hashes."""
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parents[3]
XSA = ROOT / 'FPGA/bitstreams/voxel_readout_with_droneID.xsa'
EXPECTED = {
    'rf_packet_unpacker_wrapper': {'DATA_WIDTH': '32'},
    'voxel_wrapper': {'VOXEL_SIZE_MM': '500', 'X_ORIGIN_MM': '0',
                      'Y_ORIGIN_MM': '0', 'Z_ORIGIN_MM': '0'},
    'voxel_lookup_wrapper': {'MAX_VOXELS': '1024', 'TABLE_SIZE': '2048'},
    'voxel_accumulator_wrapper': {'MAX_VOXELS': '1024', 'COUNT_WIDTH': '32'},
    'voxel_dma_readout_wrapper': {'MAX_VOXELS': '1024', 'COUNT_WIDTH': '32'},
    'axi_dma': {'C_INCLUDE_SG': '0', 'C_INCLUDE_MM2S_DRE': '0',
                'C_INCLUDE_S2MM_DRE': '0', 'C_M_AXIS_MM2S_TDATA_WIDTH': '32',
                'C_S_AXIS_S2MM_TDATA_WIDTH': '32'},
    'processing_system7': {'PCW_CLK0_FREQ': '100000000', 'PCW_EN_UART1': '1'},
}

def check():
    with zipfile.ZipFile(XSA) as archive:
        root = ET.fromstring(archive.read('design_1.hwh'))
    found = {}
    for module in root.findall('.//MODULE'):
        kind = module.get('MODTYPE')
        if kind not in EXPECTED:
            continue
        params = {p.get('NAME').upper(): p.get('VALUE')
                  for p in module.findall('./PARAMETERS/PARAMETER')}
        for name, value in EXPECTED[kind].items():
            assert params[name] == value, (kind, name, params[name], value)
        found[kind] = EXPECTED[kind]
    assert found.keys() == EXPECTED.keys()
    files = sorted((ROOT / 'FPGA/rtl').glob('*')) + sorted((ROOT / 'FPGA/bitstreams').glob('*'))
    return {'parameters': found, 'sha256': {str(p.relative_to(ROOT)):
            hashlib.sha256(p.read_bytes()).hexdigest() for p in files if p.is_file()},
            'scope': 'HWH parameters verified; payload semantics verified from frozen RTL, not recoverable from HWH alone.'}

if __name__ == '__main__':
    print(json.dumps(check(), indent=2))
