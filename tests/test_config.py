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
Tests for settings mapping.
"""
import pytest

from decklink.lib.config import (DEFAULT_SETTINGS, HIDE_BLANK, HIDE_DESKTOP, HIDE_THEME,
                                 OutputConfig, Region, should_blank)


class FakeSettings:
    """
    Stands in for OpenLP's Settings, which raises KeyError on unknown keys.
    """

    def __init__(self, values=None):
        self._values = dict(DEFAULT_SETTINGS)
        self._values.update(values or {})

    def value(self, key):
        # OpenLP's Settings.value raises KeyError for unregistered keys, and
        # that behaviour is the whole reason the plugin registers defaults
        # before Plugin.__init__ runs. Reproduce it here.
        return self._values[key]


def test_defaults_round_trip_into_a_config():
    config = OutputConfig.from_settings(FakeSettings())
    assert config.enabled is False
    assert config.mode == '1080p30'
    assert config.device_number == 0
    assert config.sink == 'decklink'
    assert config.backend == 'auto'
    assert config.screen_number == -1
    assert config.black_on_show_desktop is False


def test_settings_override_the_defaults():
    config = OutputConfig.from_settings(FakeSettings({
        'decklink/enabled': True,
        'decklink/mode': '1080p50',
        'decklink/device number': 3,
        'decklink/capture backend': 'x11',
    }))
    assert config.enabled is True
    assert config.mode == '1080p50'
    assert config.device_number == 3
    assert config.backend == 'x11'


def test_every_key_the_config_reads_has_a_registered_default():
    # If this fails, OpenLP will raise KeyError at startup rather than
    # falling back, so it is worth asserting explicitly.
    OutputConfig.from_settings(FakeSettings())


def test_default_settings_cover_the_status_key_prefix():
    for key in DEFAULT_SETTINGS:
        assert key.startswith('decklink/')


def test_string_numbers_from_an_ini_file_are_coerced():
    # Settings read back from an ini can arrive as strings.
    config = OutputConfig.from_settings(FakeSettings({
        'decklink/device number': '2',
        'decklink/screen number': '1',
    }))
    assert config.device_number == 2
    assert config.screen_number == 1


def test_with_region_does_not_mutate_the_original():
    config = OutputConfig()
    updated = config.with_region(Region(0, 0, 1920, 1080))
    assert config.region is None
    assert updated.region.width == 1920


def test_configs_compare_by_value_so_changes_can_be_detected():
    # update_config() compares configs to decide whether to restart, so
    # equality has to be value-based.
    assert OutputConfig(mode='1080p30') == OutputConfig(mode='1080p30')
    assert OutputConfig(mode='1080p30') != OutputConfig(mode='1080p50')


class TestBlankingPolicy:
    """
    OpenLP has three hide modes and renders all of them itself, so the capture
    normally just passes them through. Getting this wrong is user-visible in
    the worst way: forcing black would break the "Show Desktop" workflow that
    installations use to put external content on the programme feed.
    """

    def test_black_button_is_passed_through(self):
        # HideMode.Blank runs toBlack in the display, so the captured window
        # is already black. Overriding would be redundant.
        assert should_blank(HIDE_BLANK, OutputConfig()) is False

    def test_blank_to_theme_is_passed_through(self):
        assert should_blank(HIDE_THEME, OutputConfig()) is False

    def test_show_desktop_is_passed_through_by_default(self):
        # This is the requirement: external content shown via Show Desktop
        # must reach the SDI feed, exactly as it reaches HDMI.
        assert should_blank(HIDE_DESKTOP, OutputConfig()) is False

    def test_show_desktop_can_be_forced_to_black_opt_in(self):
        config = OutputConfig(black_on_show_desktop=True)
        assert should_blank(HIDE_DESKTOP, config) is True

    def test_opt_in_does_not_affect_the_other_modes(self):
        config = OutputConfig(black_on_show_desktop=True)
        assert should_blank(HIDE_BLANK, config) is False
        assert should_blank(HIDE_THEME, config) is False

    def test_not_hidden_is_never_blanked(self):
        assert should_blank(None, OutputConfig()) is False
        assert should_blank(None, OutputConfig(black_on_show_desktop=True)) is False

    def test_unknown_hide_mode_passes_through_rather_than_blacking_out(self):
        # If OpenLP adds a fourth mode, showing something is better than
        # showing nothing on a live feed.
        assert should_blank(99, OutputConfig()) is False

    def test_mirrored_hide_mode_values_match_openlp_3_1_7(self):
        # Documented values from openlp/core/ui/__init__.py; the plugin also
        # checks these against the real enum at runtime.
        assert (HIDE_BLANK, HIDE_THEME, HIDE_DESKTOP) == (1, 2, 3)
