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
GStreamer access, kept deliberately lazy and non-fatal.

OpenLP imports community plugins during bootstrap, and any exception that is
not an ``ImportError`` propagates far enough to kill startup. So nothing in
this module raises at import time: GStreamer is loaded on first use and every
failure is reported as data instead.
"""
import logging
import os


log = logging.getLogger(__name__)

_gst = None
_glib = None
_load_error = None
_loaded = False


def load_gst():
    """
    Import and initialise GStreamer, returning ``(Gst, GLib)`` or ``(None, None)``.

    Safe to call repeatedly; the result is cached, including the failure.
    """
    global _gst, _glib, _load_error, _loaded
    if _loaded:
        return _gst, _glib
    _loaded = True
    try:
        import gi
        gi.require_version('Gst', '1.0')
        from gi.repository import GLib, Gst
        if not Gst.is_initialized():
            Gst.init(None)
        _gst, _glib = Gst, GLib
        log.info('GStreamer %s initialised', Gst.version_string())
    except Exception as error:  # noqa: BLE001 - must never escape
        _load_error = str(error)
        log.warning('GStreamer unavailable: %s', error)
    return _gst, _glib


def gst_available():
    """
    True when GStreamer could be imported and initialised.
    """
    gst, _ = load_gst()
    return gst is not None


def load_error():
    """
    The reason GStreamer is unavailable, or None.
    """
    load_gst()
    return _load_error


def element_available(name):
    """
    True when a GStreamer element factory of this name exists.
    """
    gst, _ = load_gst()
    if gst is None:
        return False
    return gst.ElementFactory.find(name) is not None


def session_type():
    """
    Best guess at the display server: 'wayland', 'x11' or 'unknown'.
    """
    value = (os.environ.get('XDG_SESSION_TYPE') or '').strip().lower()
    if value in ('wayland', 'x11'):
        return value
    if os.environ.get('WAYLAND_DISPLAY'):
        return 'wayland'
    if os.environ.get('DISPLAY'):
        return 'x11'
    return 'unknown'


def diagnostics():
    """
    Human-readable list of what is missing, for the settings tab and the log.

    Returns an empty list when everything the plugin needs is present.
    """
    problems = []
    if not gst_available():
        problems.append('GStreamer (python3-gi + gstreamer1.0) is not available: {}'
                        .format(load_error() or 'unknown reason'))
        return problems
    if not element_available('decklinkvideosink'):
        problems.append('decklinkvideosink is missing. Install "gstreamer1.0-plugins-bad" '
                        'and the Blackmagic Desktop Video driver.')
    if not element_available('videotestsrc'):
        problems.append('videotestsrc is missing. Install "gstreamer1.0-plugins-base".')
    session = session_type()
    if session == 'wayland' and not element_available('pipewiresrc'):
        problems.append('This is a Wayland session but pipewiresrc is missing. '
                        'Install "gstreamer1.0-pipewire".')
    if session == 'x11' and not element_available('ximagesrc'):
        problems.append('This is an X11 session but ximagesrc is missing. '
                        'Install "gstreamer1.0-plugins-good".')
    return problems
