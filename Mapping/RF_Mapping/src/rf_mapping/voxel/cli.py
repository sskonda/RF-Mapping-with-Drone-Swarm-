"""UART first workflow. Run plotting in a separate process from acquisition."""
import argparse
import json
from pathlib import Path
import time

from . import wire
from .transport import live
from .bridge import adapter_from_config, joined_events, serial_events
from .view import SparseMap, draw


def replay(path, image=None, follow=False):
    import matplotlib.pyplot as plt
    parser, sparse = wire.Parser(), SparseMap()
    figure = plt.figure(figsize=(9, 7), layout='constrained')
    ax = figure.add_subplot(projection='3d')
    colorbar = None
    last_draw = 0.0
    with Path(path).open('rb') as source:
        while True:
            chunk = source.read(4096)
            for message in parser.feed(chunk):
                if message.kind in (wire.RESULT, wire.SNAPSHOT_SLOT):
                    sparse.apply(wire.update_record(message))
            if not chunk and not follow:
                break
            if follow and time.monotonic() - last_draw >= 0.5:
                if colorbar:
                    colorbar.remove()
                colorbar = figure.colorbar(draw(ax, sparse), ax=ax, label='Arithmetic mean RSSI (dBm)', shrink=0.65, pad=0.12)
                plt.pause(0.01)
                last_draw = time.monotonic()
            if not chunk:
                time.sleep(0.05)
    if colorbar:
        colorbar.remove()
    figure.colorbar(draw(ax, sparse), ax=ax, label='Arithmetic mean RSSI (dBm)', shrink=0.65, pad=0.12)
    if image:
        figure.savefig(image, dpi=140)
        plt.close(figure)
    else:
        plt.show()
    return {'occupied': len(sparse.slots), 'framing_errors': parser.errors}


def export_json(path, output):
    parser = wire.Parser()
    sparse = SparseMap()
    with open(path, 'rb') as source, open(output, 'w') as destination:
        while chunk := source.read(8192):
            for message in parser.feed(chunk):
                if message.kind in (wire.RESULT, wire.SNAPSHOT_SLOT):
                    record = wire.update_record(message)
                    sparse.apply(record)
                    destination.write(json.dumps(record, separators=(',', ':')) + '\n')
        if parser.errors:
            raise ValueError(f'{parser.errors} corrupt frames in capture')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    export_p = sub.add_parser('export')
    export_p.add_argument('wire_log')
    export_p.add_argument('--output', required=True)
    replay_p = sub.add_parser('replay')
    replay_p.add_argument('wire_log')
    replay_p.add_argument('--image')
    replay_p.add_argument('--follow', action='store_true')
    for name in ('bridge-replay', 'bridge-live'):
        command = sub.add_parser(name)
        command.add_argument('--config', required=True)
        command.add_argument('--raw-log', required=True)
        if name == 'bridge-replay':
            command.add_argument('events')
            command.add_argument('--output', required=True)
        else:
            command.add_argument('--esp-port', required=True)
            command.add_argument('--annotation-cm', nargs=2, type=int, metavar=('X', 'Y'), help='manual legacy annotations; continuously trigger MEASURE after READY; never used as measured pose')
            command.add_argument('--pose-port', required=True)
            command.add_argument('--zybo-port', required=True)
            command.add_argument('--wire-log', required=True)
            command.add_argument('--fresh-map', action='store_true')
    live_p = sub.add_parser('live')
    live_p.add_argument('observations', help='JSONL arrays [x_mm,y_mm,z_mm,rssi,drone_id,timestamp_us]')
    live_p.add_argument('--port', required=True)
    live_p.add_argument('--wire-log', required=True)
    live_p.add_argument('--fresh-map', action='store_true')
    live_p.add_argument('--rate', type=float, default=0, help='pace file input in observations/s; zero sends without pacing')
    args = parser.parse_args(argv)
    if args.command == 'export':
        export_json(args.wire_log, args.output)
    elif args.command == 'replay':
        print(json.dumps(replay(args.wire_log, args.image, args.follow)))
    elif args.command == 'live':
        with open(args.observations) as source:
            live(args.port, (json.loads(line) for line in source), args.wire_log, args.fresh_map, source_rate=args.rate)
    else:
        config, adapter = adapter_from_config(args.config)
        with open(args.raw_log, 'w') as raw:
            if args.command == 'bridge-replay':
                with open(args.events) as source, open(args.output, 'w') as output:
                    for observation in joined_events((json.loads(line) for line in source), adapter, raw):
                        output.write(json.dumps(observation) + '\n')
            else:
                events = serial_events(args.esp_port, args.pose_port, config['alignment']['boot_id'], args.annotation_cm)
                live(args.zybo_port, joined_events(events, adapter, raw), args.wire_log, args.fresh_map)

if __name__ == '__main__':
    main()
