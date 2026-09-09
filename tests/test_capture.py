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
Tests for capture backend selection.

These matter because the choice is made from the environment, and getting it
wrong on the target machine means either a black feed or a permission prompt
nobody is there to answer.
"""
import pytest

from decklink.lib import capture
from decklink.lib.config import OutputConfig, Region


@pytest.fixture
def environment(monkeypatch):
    """
    Control what the backends see: session type and available elements.
    """
    state = {'session': 'x11', 'elements': set()}

    monkeypatch.setattr(capture, 'session_type', lambda: state['session'])
    monkeypatch.setattr(capture, 'element_available', lambda name: name in state['elements'])
    return state


def test_explicit_x11_is_honoured(environment):
    backend = capture.build_backend(OutputConfig(backend='x11'))
    assert isinstance(backend, capture.X11RegionBackend)


def test_explicit_test_pattern_is_honoured(environment):
    backend = capture.build_backend(OutputConfig(backend='test'))
    assert isinstance(backend, capture.TestPatternBackend)


def test_auto_prefers_x11_on_an_x11_session(environment):
    environment['session'] = 'x11'
    environment['elements'] = {'ximagesrc', 'videotestsrc'}
    backend = capture.build_backend(OutputConfig(backend='auto'))
    assert isinstance(backend, capture.X11RegionBackend)


def test_auto_falls_back_to_a_test_pattern_when_nothing_can_capture(environment):
    environment['session'] = 'unknown'
    environment['elements'] = {'videotestsrc'}
    backend = capture.build_backend(OutputConfig(backend='auto'))
    # Falling back keeps the plugin alive and diagnosable instead of failing
    # hard with no output and no explanation.
    assert isinstance(backend, capture.TestPatternBackend)


def test_x11_is_unavailable_on_a_wayland_session(environment):
    environment['session'] = 'wayland'
    environment['elements'] = {'ximagesrc'}
    available, reason = capture.X11RegionBackend().is_available()
    assert available is False
    assert 'x11' in reason.lower() or 'wayland' in reason.lower()


def test_x11_reports_a_missing_element(environment):
    environment['session'] = 'x11'
    environment['elements'] = set()
    available, reason = capture.X11RegionBackend().is_available()
    assert available is False
    assert 'ximagesrc' in reason


def test_x11_fragment_uses_inclusive_end_coordinates(environment):
    config = OutputConfig(backend='x11').with_region(Region(1920, 0, 1920, 1080))
    fragment = capture.X11RegionBackend().fragment(config)
    assert 'startx=1920' in fragment
    assert 'endx=3839' in fragment
    assert 'name=capsrc' in fragment


def test_x11_fragment_disables_damage_events(environment):
    # Damage-based capture emits nothing while a slide is static, which
    # starves a hardware output that needs a steady frame cadence.
    config = OutputConfig(backend='x11').with_region(Region(0, 0, 1920, 1080))
    assert 'use-damage=false' in capture.X11RegionBackend().fragment(config)


def test_x11_fragment_hides_the_pointer(environment):
    config = OutputConfig(backend='x11').with_region(Region(0, 0, 1920, 1080))
    assert 'show-pointer=false' in capture.X11RegionBackend().fragment(config)


def test_x11_fragment_refuses_an_invalid_region(environment):
    config = OutputConfig(backend='x11').with_region(Region(0, 0, 0, 0))
    with pytest.raises(ValueError):
        capture.X11RegionBackend().fragment(config)


def test_x11_fragment_refuses_a_missing_region(environment):
    with pytest.raises(ValueError):
        capture.X11RegionBackend().fragment(OutputConfig(backend='x11'))


def test_test_pattern_needs_only_videotestsrc(environment):
    environment['elements'] = {'videotestsrc'}
    available, reason = capture.TestPatternBackend().is_available()
    assert available is True
    assert reason == ''
