# -*- coding: utf-8 -*-
##########################################################################
# OpenLP DeckLink Output - SDI output for OpenLP via Blackmagic DeckLink  #
# ---------------------------------------------------------------------- #
# Copyright (c) 2026 OpenLP DeckLink Output contributors                 #
# ---------------------------------------------------------------------- #
# This program is free software: you can redistribute it and/or modify   #
# it under the terms of the GNU General Public License as published by   #
# the Free Software Foundation, either version 3 of the License, or      #
# (at your option) any later version.                                    #
#                                                                        #
# This program is distributed in the hope that it will be useful,        #
# but WITHOUT ANY WARRANTY; without even the implied warranty of         #
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the          #
# GNU General Public License for more details.                           #
#                                                                        #
# You should have received a copy of the GNU General Public License      #
# along with this program.  If not, see <https://www.gnu.org/licenses/>. #
##########################################################################
"""
Standalone diagnostics for the DeckLink output plugin.

Runs without OpenLP, so it can answer the questions that decide whether the
plugin will work at all on a given machine:

  check     What is installed, what is missing, which session type is running.
  modes     Which video modes the installed decklinkvideosink accepts.
  devices   Which DeckLink device numbers respond.
  snapshot  Grab one frame of a screen region to a PNG.
  bars      Send colour bars to a sink for N seconds.
  mirror    Mirror a screen region to a sink for N seconds.

The important one is ``snapshot`` while a video is playing on OpenLP's live
display. OpenLP hands VLC its own top-level window, so it is worth proving with
a real frame that a screen capture picks the video up rather than showing black
where it should be.

Examples::

    python3 tools/smoketest.py check
    python3 tools/smoketest.py bars --sink preview --seconds 5
    python3 tools/smoketest.py snapshot --region 0,0,1920,1080 --out /tmp/frame.png
    python3 tools/smoketest.py mirror --region 0,0,1920,1080 --sink decklink --seconds 20
"""
import argparse
import logging
import pathlib
import sys
import time


sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from decklink.lib.capture import (PipeWireBackend, TestPatternBackend,  # noqa: E402
                                  X11RegionBackend, build_backend)
from decklink.lib.config import OutputConfig, Region  # noqa: E402
from decklink.lib.devices import list_modes, probe_devices  # noqa: E402
from decklink.lib.gst import diagnostics, element_available, load_gst, session_type  # noqa: E402
from decklink.lib.launch import build_launch  # noqa: E402


log = logging.getLogger('smoketest')

ELEMENTS = ('decklinkvideosink', 'ximagesrc', 'pipewiresrc', 'videotestsrc',
            'videoconvert', 'videoscale', 'videorate', 'input-selector', 'pngenc')


def parse_region(text):
    """
    Parse ``x,y,w,h`` into a :class:`Region`.
    """
    parts = [int(piece.strip()) for piece in text.split(',')]
    if len(parts) != 4:
        raise argparse.ArgumentTypeError('expected x,y,width,height')
    return Region(*parts)


def cmd_check(args):
    """
    Report the environment and what is missing.
    """
    print('Session type:      {}'.format(session_type()))
    gst, _ = load_gst()
    if gst is None:
        print('GStreamer:         NOT AVAILABLE')
    else:
        print('GStreamer:         {}'.format(gst.version_string()))
    print('')
    for name in ELEMENTS:
        print('  {:<20} {}'.format(name, 'yes' if element_available(name) else 'MISSING'))
    print('')
    problems = diagnostics()
    if problems:
        print('Problems:')
        for problem in problems:
            print('  - {}'.format(problem))
    else:
        print('No problems detected.')
    print('')
    backend = build_backend(OutputConfig(backend='auto'))
    print('Auto-selected capture backend: {} ({})'.format(backend.name, backend.label))
    return 0 if not problems else 1


def cmd_modes(args):
    """
    List the video modes the sink accepts.
    """
    modes = list_modes()
    print('{} modes reported:'.format(len(modes)))
    for mode in modes:
        print('  {}'.format(mode))
    if '1080p30' not in modes:
        print('\nWARNING: 1080p30 is not in this list.')
        return 1
    return 0


def cmd_devices(args):
    """
    Probe DeckLink device numbers.
    """
    found = probe_devices(args.max_devices)
    if not found:
        print('No DeckLink devices responded.')
        print('Check that the Blackmagic Desktop Video driver is loaded '
              '(lsmod | grep blackmagic) and that no other application holds the card.')
        return 1
    print('Responding device numbers: {}'.format(', '.join(str(n) for n in found)))
    return 0


def _run_for(pipeline, gst, seconds, backend=None):
    """
    Run a pipeline for a fixed time, reporting bus errors.
    """
    result = pipeline.set_state(gst.State.PLAYING)
    if result == gst.StateChangeReturn.FAILURE:
        print('FAILED to start the pipeline.')
        pipeline.set_state(gst.State.NULL)
        return 1
    bus = pipeline.get_bus()
    deadline = time.monotonic() + seconds
    status = 0
    print('Running for {}s...'.format(seconds))
    while time.monotonic() < deadline:
        message = bus.timed_pop_filtered(
            100 * gst.MSECOND, gst.MessageType.ERROR | gst.MessageType.EOS)
        if message is None:
            continue
        if message.type == gst.MessageType.ERROR:
            error, debug = message.parse_error()
            print('ERROR: {}\n{}'.format(error.message, debug))
            status = 1
            break
        print('End of stream.')
        break
    pipeline.set_state(gst.State.NULL)
    if backend is not None:
        backend.release()
    if status == 0:
        print('Completed without errors.')
    return status


def _sink_config(args):
    return OutputConfig(device_number=args.device, mode=args.mode, sink=args.sink)


def cmd_bars(args):
    """
    Send colour bars to a sink. Proves the output path with no capture involved.
    """
    gst, _ = load_gst()
    if gst is None:
        print('GStreamer is not available.')
        return 1
    config = _sink_config(args)
    launch = build_launch(config, TestPatternBackend().fragment(config))
    print('Pipeline:\n  {}\n'.format(launch))
    return _run_for(gst.parse_launch(launch), gst, args.seconds)


def cmd_mirror(args):
    """
    Mirror a screen region to a sink. The full production path.
    """
    gst, _ = load_gst()
    if gst is None:
        print('GStreamer is not available.')
        return 1
    config = _sink_config(args)
    if args.region:
        config = config.with_region(args.region)
    backend = _backend_for(args, config)
    available, reason = backend.is_available()
    if not available:
        print('Capture backend {} is unavailable: {}'.format(backend.name, reason))
        return 1
    launch = build_launch(config, backend.fragment(config))
    print('Pipeline:\n  {}\n'.format(launch))
    pipeline = gst.parse_launch(launch)
    backend.configure(pipeline)
    return _run_for(pipeline, gst, args.seconds, backend)


def _backend_for(args, config):
    if args.backend == 'x11':
        return X11RegionBackend()
    if args.backend == 'pipewire':
        return PipeWireBackend()
    if args.backend == 'test':
        return TestPatternBackend()
    return build_backend(config)


def cmd_snapshot(args):
    """
    Write one captured frame to a PNG.

    This is the test that matters: run it while a video is playing on OpenLP's
    live output. If the PNG shows the video, a screen capture is a valid frame
    source. If the video area is black, the capture is not seeing VLC's window
    and the plugin needs a different approach.
    """
    gst, _ = load_gst()
    if gst is None:
        print('GStreamer is not available.')
        return 1
    if not element_available('pngenc'):
        print('pngenc is missing (install gstreamer1.0-plugins-good).')
        return 1
    config = OutputConfig(backend=args.backend)
    if args.region:
        config = config.with_region(args.region)
    backend = _backend_for(args, config)
    available, reason = backend.is_available()
    if not available:
        print('Capture backend {} is unavailable: {}'.format(backend.name, reason))
        return 1
    launch = ('{source} ! videoconvert ! pngenc snapshot=true ! '
              'filesink location={out}'.format(source=backend.fragment(config), out=args.out))
    print('Pipeline:\n  {}\n'.format(launch))
    pipeline = gst.parse_launch(launch)
    backend.configure(pipeline)
    status = _run_for(pipeline, gst, args.seconds, backend)
    target = pathlib.Path(args.out)
    if target.exists() and target.stat().st_size > 0:
        print('Wrote {} ({} bytes). Open it and check whether video is visible.'
              .format(target, target.stat().st_size))
        return 0
    print('No snapshot was written.')
    return 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('-v', '--verbose', action='store_true', help='debug logging')
    subparsers = parser.add_subparsers(dest='command', required=True)

    subparsers.add_parser('check', help='report the environment').set_defaults(func=cmd_check)
    subparsers.add_parser('modes', help='list sink video modes').set_defaults(func=cmd_modes)

    devices = subparsers.add_parser('devices', help='probe DeckLink devices')
    devices.add_argument('--max-devices', type=int, default=8)
    devices.set_defaults(func=cmd_devices)

    def add_sink_args(sub):
        sub.add_argument('--sink', choices=('decklink', 'preview', 'none'), default='preview')
        sub.add_argument('--device', type=int, default=0)
        sub.add_argument('--mode', default='1080p30')
        sub.add_argument('--seconds', type=int, default=10)

    bars = subparsers.add_parser('bars', help='send colour bars to a sink')
    add_sink_args(bars)
    bars.set_defaults(func=cmd_bars)

    mirror = subparsers.add_parser('mirror', help='mirror a screen region to a sink')
    add_sink_args(mirror)
    mirror.add_argument('--region', type=parse_region, help='x,y,width,height')
    mirror.add_argument('--backend', choices=('auto', 'x11', 'pipewire', 'test'), default='auto')
    mirror.set_defaults(func=cmd_mirror)

    snapshot = subparsers.add_parser('snapshot', help='write one captured frame to a PNG')
    snapshot.add_argument('--region', type=parse_region, help='x,y,width,height')
    snapshot.add_argument('--backend', choices=('auto', 'x11', 'pipewire', 'test'), default='auto')
    snapshot.add_argument('--out', default='/tmp/openlp-decklink-frame.png')
    snapshot.add_argument('--seconds', type=int, default=5)
    snapshot.set_defaults(func=cmd_snapshot)

    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format='%(levelname)s %(name)s: %(message)s')
    return args.func(args)


if __name__ == '__main__':
    sys.exit(main())
