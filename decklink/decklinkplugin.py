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
The DeckLink output plugin.

Mirrors OpenLP's live output to a Blackmagic DeckLink card as SDI, by capturing
the display screen and feeding it to GStreamer's ``decklinkvideosink``.

Installed as an OpenLP community plugin::

    ~/.local/share/openlp/contrib/plugins/decklink/decklinkplugin.py

OpenLP's plugin manager globs ``plugins/*/[!.]*plugin.py`` under both its own
package and the community directory, so the file name must keep its
``plugin.py`` suffix.

Nothing here may raise during import. OpenLP's ``extension_loader`` lets any
non-ImportError exception propagate far enough to abort startup, so GStreamer
and D-Bus are only touched lazily, from inside methods.
"""
import logging

from openlp.core.common.enum import PluginStatus
from openlp.core.common.i18n import translate
from openlp.core.common.registry import Registry
from openlp.core.common.settings import Settings
from openlp.core.lib.plugin import Plugin, StringContent
from openlp.core.state import State
from openlp.core.ui.icons import UiIcons

from .lib.config import DEFAULT_SETTINGS, OutputConfig
from .lib.gst import diagnostics
from .lib.pipeline import DecklinkPipeline
from .lib.screens import resolve_region
from .lib.tab import DecklinkTab


log = logging.getLogger(__name__)

__version__ = '0.1.0'

# Registered at import time so that anything reading these keys later, the
# settings tab included, finds a default instead of a KeyError.
Settings.extend_default_settings(
    dict(DEFAULT_SETTINGS, **{'decklink/status': PluginStatus.Inactive}))


class DecklinkPlugin(Plugin):
    """
    Mirrors the live display to a DeckLink SDI output.
    """
    log.info('DeckLink Output plugin loaded')

    def __init__(self):
        super().__init__('decklink', settings_tab_class=DecklinkTab, version=__version__)
        self.icon = UiIcons().desktop
        self.icon_path = self.icon
        self.weight = -1
        self.pipeline = None
        self._hooked = False
        State().add_service('decklink', self.weight, is_plugin=True)
        State().update_pre_conditions('decklink', self.check_pre_conditions())

    def check_pre_conditions(self):
        """
        Always available.

        GStreamer might well be missing, but reporting that in the settings tab
        is far more useful than silently vanishing from the plugin list, which
        is what returning False here would do.
        """
        return True

    def initialise(self):
        """
        Hook OpenLP's live-display events and start output if enabled.
        """
        log.info('DeckLink Output plugin initialising')
        super().initialise()
        for problem in diagnostics():
            log.warning('DeckLink prerequisite: %s', problem)
        self._hook_events()
        self._reconfigure()

    def finalise(self):
        """
        Stop output and unhook.
        """
        log.info('DeckLink Output plugin finalising')
        self._stop_pipeline()
        self._unhook_events()
        super().finalise()

    def config_update(self):
        """
        Called after the settings dialog is accepted.
        """
        log.info('DeckLink configuration updated')
        self._reconfigure()

    # -- event wiring ----------------------------------------------------

    def _hook_events(self):
        if self._hooked:
            return
        Registry().register_function('live_display_hide', self.on_live_display_hide)
        Registry().register_function('live_display_show', self.on_live_display_show)
        Registry().register_function('config_screen_changed', self.on_screen_changed)
        self._hooked = True

    def _unhook_events(self):
        if not self._hooked:
            return
        for event, handler in (('live_display_hide', self.on_live_display_hide),
                               ('live_display_show', self.on_live_display_show),
                               ('config_screen_changed', self.on_screen_changed)):
            try:
                Registry().remove_function(event, handler)
            except Exception as error:  # noqa: BLE001 - teardown must not raise
                log.debug('Could not remove %s handler: %s', event, error)
        self._hooked = False

    def on_live_display_hide(self, hide_mode=None):
        """
        Blank the SDI feed when OpenLP hides the display.

        This has to be explicit. ``HideMode.Screen`` makes OpenLP's display
        window transparent rather than black, so a screen capture would put the
        desktop wallpaper on the programme feed.
        """
        if self.pipeline is not None and self.pipeline.config.blank_on_hide:
            self.pipeline.set_blank(True)

    def on_live_display_show(self):
        """
        Return to the captured screen.
        """
        if self.pipeline is not None:
            self.pipeline.set_blank(False)

    def on_screen_changed(self):
        """
        Re-resolve the capture region after a monitor or geometry change.
        """
        log.info('Screen configuration changed; re-resolving the capture region')
        self._reconfigure()

    # -- pipeline lifecycle ----------------------------------------------

    def _current_config(self):
        """
        Build an OutputConfig from settings plus the resolved capture region.
        """
        config = OutputConfig.from_settings(self.settings)
        return config.with_region(resolve_region(config.screen_number))

    def _reconfigure(self):
        """
        Bring the pipeline into line with the current settings.
        """
        config = self._current_config()
        if not config.enabled:
            self._stop_pipeline()
            return
        if self.pipeline is None:
            self.pipeline = DecklinkPipeline(config)
            self.pipeline.error_occurred.connect(self.on_pipeline_error)
            if not self.pipeline.start():
                log.error('DeckLink output could not be started: %s',
                          self.pipeline.last_error)
        else:
            self.pipeline.update_config(config)
        self._persist_restore_token()

    def _stop_pipeline(self):
        if self.pipeline is None:
            return
        self._persist_restore_token()
        self.pipeline.stop()
        self.pipeline = None

    def _persist_restore_token(self):
        """
        Save the portal restore token so Wayland does not re-prompt next start.
        """
        if self.pipeline is None:
            return
        token = self.pipeline.restore_token
        if token and token != self.settings.value('decklink/portal restore token'):
            log.info('Storing a new screencast restore token')
            self.settings.setValue('decklink/portal restore token', token)

    def on_pipeline_error(self, message):
        """
        Log a pipeline failure. Deliberately not a modal dialog: an SDI feed
        dying mid-service must not put a message box over the operator's UI.
        """
        log.error('DeckLink output failed: %s', message)

    # -- plugin metadata -------------------------------------------------

    def set_plugin_text_strings(self):
        """
        Define the plugin's translatable strings.
        """
        self.text_strings[StringContent.Name] = {
            'singular': translate('DecklinkPlugin', 'DeckLink Output', 'name singular'),
            'plural': translate('DecklinkPlugin', 'DeckLink Output', 'name plural')
        }
        self.text_strings[StringContent.VisibleName] = {
            'title': translate('DecklinkPlugin', 'DeckLink Output', 'container title')
        }
        self.set_plugin_ui_text_strings({
            'load': '', 'import': '', 'new': '', 'edit': '',
            'delete': '', 'preview': '', 'live': '', 'service': '',
        })

    @staticmethod
    def about():
        """
        Information for the plugin manager.
        """
        return translate(
            'DecklinkPlugin',
            '<strong>DeckLink Output</strong><br/>Mirrors the live display to a Blackmagic '
            'DeckLink card as SDI, using GStreamer. Captures the display screen, so video '
            'clips are included as well as lyrics and images.')
