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
Resolving which screen rectangle to capture.

OpenLP's ``ScreenList`` is the authority on where the live display window
lands, including any custom geometry the operator has set, so we ask it rather
than guessing from Qt directly. ``ScreenList.update_screens()`` rebuilds the
list on every monitor hotplug, which is why the plugin re-resolves the region
on ``config_screen_changed`` instead of caching it forever.
"""
import logging

from .config import Region


log = logging.getLogger(__name__)


def _screen_list():
    """
    Return OpenLP's ScreenList, or None when running outside OpenLP.
    """
    try:
        from openlp.core.display.screens import ScreenList
        return ScreenList()
    except Exception as error:  # noqa: BLE001 - tools run outside OpenLP
        log.debug('ScreenList unavailable: %s', error)
        return None


def list_screens():
    """
    Return ``[(number, label, is_display), ...]`` for the settings tab.
    """
    screens = _screen_list()
    if screens is None:
        return []
    entries = []
    for screen in screens:
        geometry = screen.display_geometry
        label = '{n}: {w}x{h} at {x},{y}{flag}'.format(
            n=screen.number, w=geometry.width(), h=geometry.height(),
            x=geometry.x(), y=geometry.y(),
            flag=' (OpenLP display)' if screen.is_display else '')
        entries.append((screen.number, label, bool(screen.is_display)))
    return entries


def resolve_region(screen_number=-1):
    """
    Return the :class:`Region` to capture, or None if it cannot be determined.

    :param screen_number: an explicit screen number, or -1 to follow whichever
        screen OpenLP is currently using for its live display.
    """
    screens = _screen_list()
    if screens is None:
        return None
    target = None
    if screen_number is not None and screen_number >= 0:
        for screen in screens:
            if screen.number == screen_number:
                target = screen
                break
        if target is None:
            log.warning('Configured screen %s is gone; following the display screen',
                        screen_number)
    if target is None:
        for screen in screens:
            if screen.is_display:
                target = screen
                break
    if target is None:
        log.warning('OpenLP has no display screen configured')
        return None
    geometry = target.display_geometry
    region = Region(geometry.x(), geometry.y(), geometry.width(), geometry.height())
    log.info('Capture region resolved to %s', region)
    return region
