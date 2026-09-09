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
Configuration for the DeckLink output plugin.

Everything the plugin needs to build a pipeline is captured in
:class:`OutputConfig`, which is a plain value object so it can be constructed
and compared in tests without OpenLP or GStreamer present.
"""
import logging
from dataclasses import dataclass, replace


log = logging.getLogger(__name__)

#: Settings section/prefix. OpenLP settings keys use spaces inside a section.
SECTION = 'decklink'

#: Capture backends, in the order ``auto`` will try them.
BACKEND_AUTO = 'auto'
BACKEND_PIPEWIRE = 'pipewire'
BACKEND_X11 = 'x11'
BACKEND_TEST = 'test'

BACKENDS = (BACKEND_AUTO, BACKEND_PIPEWIRE, BACKEND_X11, BACKEND_TEST)

#: Output sinks. ``preview`` needs no DeckLink hardware, which makes the whole
#: plugin developable and demonstrable before a card is installed.
SINK_DECKLINK = 'decklink'
SINK_PREVIEW = 'preview'
SINK_NONE = 'none'

SINKS = (SINK_DECKLINK, SINK_PREVIEW, SINK_NONE)

#: Fallback mode list, used when the installed decklinkvideosink cannot be
#: introspected (no Desktop Video driver, or plugin not installed yet).
FALLBACK_MODES = (
    '720p50', '720p5994', '720p60',
    '1080p24', '1080p25', '1080p30',
    '1080i50', '1080i5994', '1080i60',
    '1080p50', '1080p5994', '1080p60',
)

#: Frame rate implied by each mode, for the pipeline's framerate caps.
MODE_FRAMERATES = {
    '720p50': (50, 1), '720p5994': (60000, 1001), '720p60': (60, 1),
    '1080p24': (24, 1), '1080p25': (25, 1), '1080p30': (30, 1),
    '1080i50': (25, 1), '1080i5994': (30000, 1001), '1080i60': (30, 1),
    '1080p50': (50, 1), '1080p5994': (60000, 1001), '1080p60': (60, 1),
}

#: Frame size implied by each mode.
MODE_SIZES = {
    '720p50': (1280, 720), '720p5994': (1280, 720), '720p60': (1280, 720),
    '1080p24': (1920, 1080), '1080p25': (1920, 1080), '1080p30': (1920, 1080),
    '1080i50': (1920, 1080), '1080i5994': (1920, 1080), '1080i60': (1920, 1080),
    '1080p50': (1920, 1080), '1080p5994': (1920, 1080), '1080p60': (1920, 1080),
}

DEFAULT_SETTINGS = {
    'decklink/enabled': False,
    'decklink/device number': 0,
    'decklink/mode': '1080p30',
    'decklink/capture backend': BACKEND_AUTO,
    'decklink/sink': SINK_DECKLINK,
    'decklink/screen number': -1,
    'decklink/blank on hide': True,
    'decklink/portal restore token': '',
    'decklink/keyer mode': 'off',
}


@dataclass(frozen=True)
class Region:
    """
    A capture rectangle in desktop coordinates.
    """
    x: int
    y: int
    width: int
    height: int

    @property
    def endx(self):
        """
        ximagesrc's endx is inclusive, so the last pixel column is width - 1.
        """
        return self.x + self.width - 1

    @property
    def endy(self):
        """
        ximagesrc's endy is inclusive, so the last pixel row is height - 1.
        """
        return self.y + self.height - 1

    def is_valid(self):
        return self.width > 0 and self.height > 0


@dataclass(frozen=True)
class OutputConfig:
    """
    Everything needed to build one output pipeline.
    """
    enabled: bool = False
    device_number: int = 0
    mode: str = '1080p30'
    backend: str = BACKEND_AUTO
    sink: str = SINK_DECKLINK
    screen_number: int = -1
    blank_on_hide: bool = True
    keyer_mode: str = 'off'
    region: Region = None
    portal_restore_token: str = ''

    @property
    def framerate(self):
        """
        The (numerator, denominator) frame rate for the configured mode.
        """
        return MODE_FRAMERATES.get(self.mode, (30, 1))

    @property
    def size(self):
        """
        The (width, height) frame size for the configured mode.
        """
        return MODE_SIZES.get(self.mode, (1920, 1080))

    @property
    def is_interlaced(self):
        """
        True for the ``1080i*`` modes. No mode name contains 'i' otherwise.
        """
        return 'i' in self.mode

    def with_region(self, region):
        return replace(self, region=region)

    @classmethod
    def from_settings(cls, settings):
        """
        Build a config from an OpenLP ``Settings`` object.

        :param settings: anything with a ``value(key)`` method.
        """
        return cls(
            enabled=bool(settings.value('decklink/enabled')),
            device_number=int(settings.value('decklink/device number')),
            mode=str(settings.value('decklink/mode')),
            backend=str(settings.value('decklink/capture backend')),
            sink=str(settings.value('decklink/sink')),
            screen_number=int(settings.value('decklink/screen number')),
            blank_on_hide=bool(settings.value('decklink/blank on hide')),
            keyer_mode=str(settings.value('decklink/keyer mode')),
            portal_restore_token=str(settings.value('decklink/portal restore token') or ''),
        )
