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

#: Every mode the plugin can build correct caps for:
#: name -> (width, height, fps numerator, fps denominator, interlaced).
#:
#: This is deliberately the single source of truth. The sink's ``mode`` enum
#: lists 67 modes, including DCI, 8K and anamorphic SD that no entry-level card
#: can output, and a mode missing from here used to fall back silently to
#: 1080p30 caps -- so ``1080p2997`` built a pipeline whose caps contradicted its
#: own mode and refused to start. Only modes defined here are offered, and
#: anything else is an error rather than a wrong guess.
#:
#: Interlaced frame rates are frames, not fields: 1080i50 is 25 frames/s.
MODES = {
    'ntsc': (720, 486, 30000, 1001, True),
    'pal': (720, 576, 25, 1, True),
    '720p50': (1280, 720, 50, 1, False),
    '720p5994': (1280, 720, 60000, 1001, False),
    '720p60': (1280, 720, 60, 1, False),
    '1080i50': (1920, 1080, 25, 1, True),
    '1080i5994': (1920, 1080, 30000, 1001, True),
    '1080i60': (1920, 1080, 30, 1, True),
    '1080p2398': (1920, 1080, 24000, 1001, False),
    '1080p24': (1920, 1080, 24, 1, False),
    '1080p25': (1920, 1080, 25, 1, False),
    '1080p2997': (1920, 1080, 30000, 1001, False),
    '1080p30': (1920, 1080, 30, 1, False),
    '1080p50': (1920, 1080, 50, 1, False),
    '1080p5994': (1920, 1080, 60000, 1001, False),
    '1080p60': (1920, 1080, 60, 1, False),
    '2160p2398': (3840, 2160, 24000, 1001, False),
    '2160p24': (3840, 2160, 24, 1, False),
    '2160p25': (3840, 2160, 25, 1, False),
    '2160p2997': (3840, 2160, 30000, 1001, False),
    '2160p30': (3840, 2160, 30, 1, False),
    '2160p50': (3840, 2160, 50, 1, False),
    '2160p5994': (3840, 2160, 60000, 1001, False),
    '2160p60': (3840, 2160, 60, 1, False),
}

#: Offered when the installed sink cannot be introspected.
FALLBACK_MODES = tuple(MODES)

#: OpenLP's HideMode values, mirrored so this module stays importable without
#: OpenLP present. Verified against openlp/core/ui/__init__.py in 3.1.7;
#: the plugin checks these against the real enum at runtime and warns on drift.
HIDE_BLANK = 1
HIDE_THEME = 2
HIDE_DESKTOP = 3

DEFAULT_SETTINGS = {
    'decklink/enabled': False,
    'decklink/device number': 0,
    'decklink/mode': '1080p30',
    'decklink/capture backend': BACKEND_AUTO,
    'decklink/sink': SINK_DECKLINK,
    'decklink/screen number': -1,
    'decklink/black on show desktop': False,
    'decklink/portal restore token': '',
    'decklink/keyer mode': 'off',
}


class UnknownModeError(ValueError):
    """
    Raised for a video mode the plugin has no caps definition for.
    """

    def __init__(self, mode):
        super().__init__('Unsupported video mode {!r}. Supported modes: {}'
                         .format(mode, ', '.join(MODES)))
        self.mode = mode


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
    black_on_show_desktop: bool = False
    keyer_mode: str = 'off'
    region: Region = None
    portal_restore_token: str = ''

    @property
    def _mode_spec(self):
        try:
            return MODES[self.mode]
        except KeyError:
            raise UnknownModeError(self.mode) from None

    @property
    def framerate(self):
        """
        The (numerator, denominator) frame rate for the configured mode.

        :raises UnknownModeError: for a mode not in :data:`MODES`.
        """
        return self._mode_spec[2], self._mode_spec[3]

    @property
    def size(self):
        """
        The (width, height) frame size for the configured mode.

        :raises UnknownModeError: for a mode not in :data:`MODES`.
        """
        return self._mode_spec[0], self._mode_spec[1]

    @property
    def is_interlaced(self):
        """
        True for interlaced modes, including NTSC and PAL.

        :raises UnknownModeError: for a mode not in :data:`MODES`.
        """
        return self._mode_spec[4]

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
            black_on_show_desktop=bool(settings.value('decklink/black on show desktop')),
            keyer_mode=str(settings.value('decklink/keyer mode')),
            portal_restore_token=str(settings.value('decklink/portal restore token') or ''),
        )


def should_blank(hide_mode, config):
    """
    Decide whether the SDI feed should be forced to black.

    The answer is almost always no, because OpenLP already renders each hide
    mode into its display window and a screen capture picks that up verbatim:

    * ``Blank`` ("Black") runs ``toBlack``, so the window really is black.
    * ``Theme`` runs ``toTheme``, so the theme background really is drawn.
    * ``Screen`` ("Show Desktop") makes the window transparent or hides it, so
      the capture shows the desktop -- which is the point of the button. Some
      installations deliberately put external content there, and forcing black
      would break that.

    The one case for overriding is an operator who does not want their desktop
    on air at all. That is opt-in via ``black on show desktop``.

    :param hide_mode: OpenLP's HideMode value, or None when not hidden.
    :param config: an :class:`OutputConfig`.
    """
    if hide_mode is None:
        return False
    if hide_mode == HIDE_DESKTOP:
        return bool(config.black_on_show_desktop)
    return False
