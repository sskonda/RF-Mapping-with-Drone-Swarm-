"""ESP32 command/capture bridge and measured-pose event joins."""
import json
from pathlib import Path
import sys
import time
from .pose import Alignment, PoseAdapter

def adapter_from_config(path):
    config = json.loads(Path(path).read_text())
    adapter = PoseAdapter(config['drone_id'], config['frame'], Alignment(**config['alignment']), config['max_pose_age_us'])
    return config, adapter


def joined_events(events, adapter, raw_log):
    for event in events:
        raw_log.write(json.dumps(event, separators=(',', ':')) + '\n')
        raw_log.flush()
        try:
            if event['type'] == 'pose':
                adapter.pose(event)
            elif event['type'] == 'rssi':
                yield adapter.measurement(event['line'], event['boot_id'])
            elif event['type'] == 'command':
                continue
            elif event['type'] == 'source_error':
                raise RuntimeError(event['line'])
            elif event['type'] == 'reboot':
                raise RuntimeError('Source reboot: stop and recalibrate clock alignment')
            else:
                raise ValueError('unknown event type')
        except (ValueError, KeyError) as error:
            print(f'pose/input rejected: {error}', file=sys.stderr)


def measurement_command(annotation_cm):
    if len(annotation_cm) != 2 or any(type(v) is not int or not 0 <= v <= 100000 for v in annotation_cm):
        raise ValueError('ESP manual annotation requires two centimetre integers in 0..100000')
    return f'MEASURE,{annotation_cm[0]},{annotation_cm[1]}\n'.encode('ascii')


def serial_events(esp_port, pose_port, boot_id, annotation_cm=None):
    import serial
    # Pose producer sends the documented measured-pose JSON schema on its own port.
    command = measurement_command(annotation_cm) if annotation_cm is not None else None
    with serial.Serial(esp_port, 115200, timeout=0, write_timeout=0) as esp, serial.Serial(pose_port, 115200, timeout=0) as poses:
        pending_command = bytearray(b'PING\n' if command else b'')
        measurement_active = False
        buffers = [bytearray(), bytearray()]
        discards = [False, False]
        while True:
            for index, port in ((1, poses), (0, esp)):
                for byte in port.read(256):
                    if byte == 10:
                        line = buffers[index].decode('utf8', errors='replace').strip()
                        buffers[index].clear()
                        if discards[index]:
                            discards[index] = False
                            print('oversized source line dropped', file=sys.stderr)
                            continue
                        if index == 0:
                            if line.startswith('STATUS,FIRMWARE,'):
                                yield {'type': 'reboot'}
                            elif line == 'READY' and command and not measurement_active and not pending_command:
                                pending_command.extend(command)
                                measurement_active = True
                                yield {'type': 'command', 'line': command.decode().strip()}
                            elif line.startswith('DONE,'):
                                measurement_active = False
                            elif line.startswith('ERROR,'):
                                yield {'type': 'source_error', 'line': line}
                            elif line.startswith('DATA,'):
                                yield {'type': 'rssi', 'line': line, 'boot_id': boot_id}
                        elif line:
                            try:
                                yield json.loads(line)
                            except json.JSONDecodeError:
                                print('invalid pose JSON dropped', file=sys.stderr)
                    elif not discards[index]:
                        if len(buffers[index]) == 1024:
                            discards[index] = True
                            buffers[index].clear()
                        else:
                            buffers[index].append(byte)
            if pending_command:
                written = esp.write(pending_command)
                del pending_command[:written]
            time.sleep(0.001)
