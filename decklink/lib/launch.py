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
Building the gst-launch description.

Kept free of Qt, D-Bus and GStreamer imports on purpose: this is the part worth
unit-testing, and it must be testable on a machine with no desktop session and
no DeckLink hardware.

Pipeline shape::

    <capture> ! queue ! videorate ! videoscale ! videoconvert ! caps -.
                                                                    input-selector ! <sink>
    videotestsrc pattern=black ! videoconvert ! caps ----------------'

No video frame passes through Python. Capture, conversion and the sink are all
GStreamer C code driven by the DeckLink sink's own hardware clock, which avoids
a Python timer trying to push 1080p30 buffers through the GIL and dropping
frames whenever OpenLP does something expensive on the GUI thread.

The black branch exists because of how OpenLP blanks. ``HideMode.Screen`` makes
the display window *transparent* rather than black, so a naive screen capture
would put the operator's desktop wallpaper on the programme feed mid-service.
Switching the selector to a black source is deterministic and independent of
whatever OpenLP happens to be drawing.
"""
from .config import SINK_DECKLINK, SINK_NONE, SINK_PREVIEW


class PipelineError(Exception):
    """
    Raised when the pipeline cannot be built or started.
    """


def build_caps(config):
    """
    Return the raw-video caps string the sink should receive.

    UYVY pairs with the sink's ``8bit-yuv`` format, which is what DeckLink
    hardware wants; letting GStreamer negotiate RGB would add a conversion on
    the hot path for no benefit.
    """
    width, height = config.size
    numerator, denominator = config.framerate
    caps = ('video/x-raw,format=UYVY,width={w},height={h},framerate={n}/{d}'
            .format(w=width, h=height, n=numerator, d=denominator))
    caps += ',interlace-mode=interleaved' if config.is_interlaced else ',interlace-mode=progressive'
    return caps


def build_sink_fragment(config):
    """
    Return the gst-launch fragment for the configured sink.
    """
    if config.sink == SINK_PREVIEW:
        return 'autovideosink name=sink sync=true'
    if config.sink == SINK_NONE:
        return 'fakesink name=sink sync=true'
    if config.sink != SINK_DECKLINK:
        raise PipelineError('Unknown sink {!r}'.format(config.sink))
    fragment = ('decklinkvideosink name=sink device-number={n} mode={m} video-format=8bit-yuv'
                .format(n=config.device_number, m=config.mode))
    if config.keyer_mode and config.keyer_mode != 'off':
        # Keying needs a card with two SDI outputs. A Mini Monitor HD has one
        # and will refuse; left configurable for a Duo 2 and similar.
        fragment += ' keyer-mode={}'.format(config.keyer_mode)
    return fragment


def build_launch(config, source_fragment):
    """
    Assemble the full gst-launch description.

    :param config: an :class:`~.config.OutputConfig`.
    :param source_fragment: the capture backend's fragment, ending in raw video.
    """
    caps = build_caps(config)
    return (
        '{source} ! queue name=livequeue max-size-buffers=4 leaky=downstream '
        '! videorate ! videoscale ! videoconvert ! {caps} ! selector. '
        'videotestsrc name=blacksrc pattern=black is-live=true '
        '! videoconvert ! {caps} ! selector. '
        'input-selector name=selector sync-streams=false ! {sink}'
    ).format(source=source_fragment, caps=caps, sink=build_sink_fragment(config))
