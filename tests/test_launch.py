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
Tests for the pipeline launch-string builders.
"""
import pytest

from decklink.lib.config import OutputConfig, Region
from decklink.lib.launch import PipelineError, build_caps, build_launch, build_sink_fragment


def test_caps_for_1080p30_are_progressive_uyvy():
    caps = build_caps(OutputConfig(mode='1080p30'))
    assert 'format=UYVY' in caps
    assert 'width=1920,height=1080' in caps
    assert 'framerate=30/1' in caps
    assert 'interlace-mode=progressive' in caps


def test_caps_for_1080i50_are_interleaved_at_25fps():
    caps = build_caps(OutputConfig(mode='1080i50'))
    assert 'interlace-mode=interleaved' in caps
    # 1080i50 is 50 fields, which is 25 frames.
    assert 'framerate=25/1' in caps


def test_caps_for_fractional_mode_keep_the_1001_denominator():
    assert 'framerate=60000/1001' in build_caps(OutputConfig(mode='1080p5994'))


def test_unknown_mode_falls_back_to_1080p30_rather_than_crashing():
    caps = build_caps(OutputConfig(mode='not-a-mode'))
    assert 'width=1920,height=1080' in caps
    assert 'framerate=30/1' in caps


def test_decklink_sink_carries_device_and_mode():
    fragment = build_sink_fragment(OutputConfig(device_number=2, mode='1080p30'))
    assert 'decklinkvideosink' in fragment
    assert 'device-number=2' in fragment
    assert 'mode=1080p30' in fragment
    assert 'video-format=8bit-yuv' in fragment


def test_keyer_is_omitted_when_off():
    assert 'keyer-mode' not in build_sink_fragment(OutputConfig(keyer_mode='off'))


def test_keyer_is_included_when_set():
    assert 'keyer-mode=internal' in build_sink_fragment(OutputConfig(keyer_mode='internal'))


def test_preview_sink_needs_no_hardware():
    assert build_sink_fragment(OutputConfig(sink='preview')).startswith('autovideosink')


def test_unknown_sink_is_rejected():
    with pytest.raises(PipelineError):
        build_sink_fragment(OutputConfig(sink='teleport'))


def test_launch_has_both_selector_branches_and_one_sink():
    launch = build_launch(OutputConfig(mode='1080p30'), 'videotestsrc name=capsrc')
    # The live branch and the black branch must both feed the selector, or
    # blanking would have nothing to switch to.
    assert launch.count('! selector.') == 2
    assert 'input-selector name=selector' in launch
    assert launch.count('decklinkvideosink') == 1
    assert 'pattern=black' in launch


def test_launch_applies_identical_caps_to_both_branches():
    config = OutputConfig(mode='1080p50')
    launch = build_launch(config, 'videotestsrc name=capsrc')
    assert launch.count(build_caps(config)) == 2


def test_region_end_coordinates_are_inclusive():
    # ximagesrc's endx/endy are inclusive, so a 1920-wide region ends at 1919.
    region = Region(0, 0, 1920, 1080)
    assert (region.endx, region.endy) == (1919, 1079)


def test_region_offset_is_preserved_for_a_second_monitor():
    region = Region(1920, 0, 1920, 1080)
    assert (region.endx, region.endy) == (3839, 1079)


def test_zero_size_region_is_invalid():
    assert not Region(0, 0, 0, 0).is_valid()
