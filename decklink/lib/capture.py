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
Capture backends.

The frame source has to be a *screen region*, not a window. OpenLP renders
lyrics into a QWebEngineView inside its display window, but plays video by
handing VLC the native window id of a separate top-level window
(``vlcplayer.py`` gives the live frame ``Qt.Tool`` flags, which promotes it out
of the display window). The two are siblings on the same rectangle, so any
window-targeted capture would show lyrics and a black hole where video should
be. OpenLP's own code concedes this and falls back to a desktop grab.

Each backend returns a gst-launch fragment ending in raw video, with its source
element named ``capsrc`` so the pipeline can find it again.
"""
import logging

from .config import BACKEND_AUTO, BACKEND_PIPEWIRE, BACKEND_TEST, BACKEND_X11
from .gst import element_available, session_type


log = logging.getLogger(__name__)


class CaptureBackend(object):
    """
    Base class for a frame source.
    """
    name = 'base'
    #: Human-readable label for the settings tab.
    label = 'Base'

    def is_available(self):
        """
        Return ``(available, reason)``. ``reason`` explains a False.
        """
        raise NotImplementedError

    def fragment(self, config):
        """
        Return the gst-launch fragment for this source, ending in raw video.
        """
        raise NotImplementedError

    def configure(self, pipeline):
        """
        Apply any post-construction setup that cannot go in the fragment.
        """

    def release(self):
        """
        Release any resources held outside GStreamer.
        """

    @property
    def restore_token(self):
        """
        A token worth persisting between runs, or ''.
        """
        return ''


class TestPatternBackend(CaptureBackend):
    """
    A moving test pattern. Needs no display server and no permissions, which
    makes the output path testable before any capture is configured.
    """
    name = BACKEND_TEST
    label = 'Test pattern (no capture)'

    def is_available(self):
        if not element_available('videotestsrc'):
            return False, 'videotestsrc is missing (install gstreamer1.0-plugins-base)'
        return True, ''

    def fragment(self, config):
        return 'videotestsrc name=capsrc pattern=smpte is-live=true'


class X11RegionBackend(CaptureBackend):
    """
    Reads a rectangle of the X11 root window with ximagesrc.

    Cheap, permissionless and well-trodden, but X11 only. ``use-damage=false``
    forces full frames: damage-based capture emits nothing while the slide is
    static, which starves a hardware output that needs a steady cadence.
    """
    name = BACKEND_X11
    label = 'X11 screen region (ximagesrc)'

    def is_available(self):
        if session_type() != 'x11':
            return False, 'not an X11 session (XDG_SESSION_TYPE={})'.format(session_type())
        if not element_available('ximagesrc'):
            return False, 'ximagesrc is missing (install gstreamer1.0-plugins-good)'
        return True, ''

    def fragment(self, config):
        region = config.region
        if region is None or not region.is_valid():
            raise ValueError('X11 capture needs a valid region')
        return ('ximagesrc name=capsrc use-damage=false show-pointer=false '
                'startx={r.x} starty={r.y} endx={r.endx} endy={r.endy}'.format(r=region))


class PipeWireBackend(CaptureBackend):
    """
    Captures under Wayland via an xdg-desktop-portal screencast.

    Unlike the X11 backend this needs a negotiated session before the pipeline
    can be built, and the compositor decides which output is shared. The
    restore token is what stops it prompting on every start.
    """
    name = BACKEND_PIPEWIRE
    label = 'Wayland screencast (PipeWire portal)'

    def __init__(self, restore_token=''):
        self._requested_token = restore_token or ''
        self._session = None

    def is_available(self):
        if not element_available('pipewiresrc'):
            return False, 'pipewiresrc is missing (install gstreamer1.0-pipewire)'
        try:
            from . import portal
        except ImportError as error:
            return False, 'no Qt D-Bus support available: {}'.format(error)
        if not portal.is_available():
            return False, 'the xdg-desktop-portal ScreenCast interface is not responding'
        return True, ''

    def fragment(self, config):
        if self._session is None:
            from . import portal
            self._session = portal.negotiate(restore_token=self._requested_token)
        return ('pipewiresrc name=capsrc do-timestamp=true path={}'
                .format(self._session.node_id))

    def configure(self, pipeline):
        """
        Hand the PipeWire socket fd to the source element.

        The fd cannot travel through a gst-launch string, so it is set once the
        element exists.
        """
        if self._session is None or self._session.fd is None:
            return
        source = pipeline.get_by_name('capsrc')
        if source is None:
            return
        source.set_property('fd', self._session.fd)

    def release(self):
        if self._session is not None:
            self._session.close()
            self._session = None

    @property
    def restore_token(self):
        return self._session.restore_token if self._session else self._requested_token


#: Concrete backends, in the order ``auto`` prefers them.
def build_backend(config):
    """
    Return the capture backend the config asks for.

    ``auto`` picks by session type, then falls back to the test pattern so the
    plugin still starts and reports something useful rather than failing hard.
    """
    requested = config.backend
    if requested == BACKEND_X11:
        return X11RegionBackend()
    if requested == BACKEND_PIPEWIRE:
        return PipeWireBackend(config.portal_restore_token)
    if requested == BACKEND_TEST:
        return TestPatternBackend()
    if requested != BACKEND_AUTO:
        log.warning('Unknown capture backend %r, falling back to auto', requested)
    session = session_type()
    candidates = []
    if session == 'wayland':
        candidates = [PipeWireBackend(config.portal_restore_token), X11RegionBackend()]
    elif session == 'x11':
        candidates = [X11RegionBackend(), PipeWireBackend(config.portal_restore_token)]
    else:
        candidates = [PipeWireBackend(config.portal_restore_token), X11RegionBackend()]
    for candidate in candidates:
        available, reason = candidate.is_available()
        if available:
            log.info('Auto-selected capture backend: %s', candidate.name)
            return candidate
        log.info('Capture backend %s unavailable: %s', candidate.name, reason)
    log.warning('No screen capture backend available; using a test pattern')
    return TestPatternBackend()
