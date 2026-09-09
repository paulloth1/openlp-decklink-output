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
Enumeration of DeckLink devices and their supported video modes.

The GStreamer decklink elements do not expose a device-listing API, so modes
come from introspecting the sink's ``mode`` property and devices are found by
probing device numbers until one refuses to reach READY.
"""
import logging

from .config import FALLBACK_MODES
from .gst import element_available, load_gst


log = logging.getLogger(__name__)

#: How many device numbers to probe. Blackmagic's own tooling stops well
#: before this on consumer hardware.
MAX_DEVICES = 8


def list_modes():
    """
    Return the video mode nicknames the installed sink accepts.

    Falls back to a known-good list when the element cannot be introspected,
    so the settings tab is still usable before the driver is installed.
    """
    gst, _ = load_gst()
    if gst is None or not element_available('decklinkvideosink'):
        return list(FALLBACK_MODES)
    sink = gst.ElementFactory.make('decklinkvideosink', None)
    if sink is None:
        return list(FALLBACK_MODES)
    try:
        pspec = sink.find_property('mode')
        modes = [value.value_nick for value in type(pspec.default_value).__enum_values__.values()]
        # 'auto' is offered by the element but is not a real output mode.
        modes = [mode for mode in modes if mode and mode != 'auto']
        if modes:
            return modes
    except Exception as error:  # noqa: BLE001 - introspection differs by version
        log.debug('Could not introspect decklinkvideosink modes: %s', error)
    return list(FALLBACK_MODES)


def probe_devices(max_devices=MAX_DEVICES):
    """
    Return the list of device numbers that accept the READY state.

    Each probe builds a throwaway ``videotestsrc ! decklinkvideosink`` and
    tries to bring it to READY, which opens the card without starting output.
    A device that is missing, already in use, or input-only fails here.
    """
    gst, _ = load_gst()
    if gst is None or not element_available('decklinkvideosink'):
        return []
    found = []
    for number in range(max_devices):
        pipeline = None
        try:
            pipeline = gst.parse_launch(
                'videotestsrc num-buffers=1 ! decklinkvideosink device-number={}'.format(number))
            result = pipeline.set_state(gst.State.READY)
            if result != gst.StateChangeReturn.FAILURE:
                found.append(number)
        except Exception as error:  # noqa: BLE001 - probing is best-effort
            log.debug('Device %s probe failed: %s', number, error)
        finally:
            if pipeline is not None:
                pipeline.set_state(gst.State.NULL)
    log.info('DeckLink devices responding: %s', found or 'none')
    return found
