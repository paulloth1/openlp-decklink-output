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
The DeckLink settings tab.
"""
import logging

from openlp.core.common.i18n import translate
from openlp.core.lib.settingstab import SettingsTab

from .compat import QtWidgets, align_top, all_fields_grow
from .config import (BACKEND_AUTO, BACKEND_PIPEWIRE, BACKEND_TEST, BACKEND_X11,
                     SINK_DECKLINK, SINK_NONE, SINK_PREVIEW)
from .devices import list_modes, probe_devices
from .gst import diagnostics, session_type
from .screens import list_screens


log = logging.getLogger(__name__)

TAB_CONTEXT = 'DecklinkPlugin.DecklinkTab'

BACKEND_CHOICES = (
    (BACKEND_AUTO, 'Automatic (recommended)'),
    (BACKEND_PIPEWIRE, 'Wayland screencast (PipeWire portal)'),
    (BACKEND_X11, 'X11 screen region (ximagesrc)'),
    (BACKEND_TEST, 'Test pattern (no capture)'),
)

SINK_CHOICES = (
    (SINK_DECKLINK, 'DeckLink hardware'),
    (SINK_PREVIEW, 'Preview window (no hardware needed)'),
    (SINK_NONE, 'Discard (measure only)'),
)

KEYER_CHOICES = (
    ('off', 'Off'),
    ('internal', 'Internal (needs a two-output card)'),
    ('external', 'External (needs a two-output card)'),
)


class DecklinkTab(SettingsTab):
    """
    Settings tab for configuring the SDI output.
    """

    def setup_ui(self):
        self.setObjectName('DecklinkTab')
        tab_layout = QtWidgets.QVBoxLayout(self)
        tab_layout.setObjectName('tab_layout')
        tab_layout.setAlignment(align_top())

        # --- Output ---
        self.output_group_box = QtWidgets.QGroupBox(self)
        tab_layout.addWidget(self.output_group_box)
        output_layout = QtWidgets.QFormLayout(self.output_group_box)
        output_layout.setFieldGrowthPolicy(all_fields_grow())
        self.enabled_check_box = QtWidgets.QCheckBox(self.output_group_box)
        output_layout.addRow(self.enabled_check_box)
        self.sink_label = QtWidgets.QLabel(self.output_group_box)
        self.sink_combo_box = QtWidgets.QComboBox(self.output_group_box)
        for value, label in SINK_CHOICES:
            self.sink_combo_box.addItem(label, value)
        output_layout.addRow(self.sink_label, self.sink_combo_box)
        self.device_label = QtWidgets.QLabel(self.output_group_box)
        device_row = QtWidgets.QHBoxLayout()
        self.device_spin_box = QtWidgets.QSpinBox(self.output_group_box)
        self.device_spin_box.setRange(0, 7)
        self.detect_button = QtWidgets.QPushButton(self.output_group_box)
        device_row.addWidget(self.device_spin_box)
        device_row.addWidget(self.detect_button)
        output_layout.addRow(self.device_label, device_row)
        self.mode_label = QtWidgets.QLabel(self.output_group_box)
        self.mode_combo_box = QtWidgets.QComboBox(self.output_group_box)
        for mode in list_modes():
            self.mode_combo_box.addItem(mode, mode)
        output_layout.addRow(self.mode_label, self.mode_combo_box)
        self.keyer_label = QtWidgets.QLabel(self.output_group_box)
        self.keyer_combo_box = QtWidgets.QComboBox(self.output_group_box)
        for value, label in KEYER_CHOICES:
            self.keyer_combo_box.addItem(label, value)
        output_layout.addRow(self.keyer_label, self.keyer_combo_box)

        # --- Capture ---
        self.capture_group_box = QtWidgets.QGroupBox(self)
        tab_layout.addWidget(self.capture_group_box)
        capture_layout = QtWidgets.QFormLayout(self.capture_group_box)
        capture_layout.setFieldGrowthPolicy(all_fields_grow())
        self.backend_label = QtWidgets.QLabel(self.capture_group_box)
        self.backend_combo_box = QtWidgets.QComboBox(self.capture_group_box)
        for value, label in BACKEND_CHOICES:
            self.backend_combo_box.addItem(label, value)
        capture_layout.addRow(self.backend_label, self.backend_combo_box)
        self.screen_label = QtWidgets.QLabel(self.capture_group_box)
        self.screen_combo_box = QtWidgets.QComboBox(self.capture_group_box)
        capture_layout.addRow(self.screen_label, self.screen_combo_box)
        self.black_desktop_check_box = QtWidgets.QCheckBox(self.capture_group_box)
        capture_layout.addRow(self.black_desktop_check_box)

        # --- Status ---
        self.status_group_box = QtWidgets.QGroupBox(self)
        tab_layout.addWidget(self.status_group_box)
        status_layout = QtWidgets.QVBoxLayout(self.status_group_box)
        self.status_label = QtWidgets.QLabel(self.status_group_box)
        self.status_label.setWordWrap(True)
        self.status_label.setTextInteractionFlags(
            self.status_label.textInteractionFlags())
        status_layout.addWidget(self.status_label)
        self.pipeline_label = QtWidgets.QLabel(self.status_group_box)
        self.pipeline_label.setWordWrap(True)
        self.pipeline_label.setStyleSheet('font-family: monospace; color: gray;')
        status_layout.addWidget(self.pipeline_label)
        self.refresh_button = QtWidgets.QPushButton(self.status_group_box)
        status_layout.addWidget(self.refresh_button)

        tab_layout.addStretch()
        self.detect_button.clicked.connect(self.on_detect_clicked)
        self.refresh_button.clicked.connect(self.on_refresh_clicked)

    def retranslate_ui(self):
        self.output_group_box.setTitle(translate(TAB_CONTEXT, 'SDI Output'))
        self.enabled_check_box.setText(
            translate(TAB_CONTEXT, 'Mirror the live output to a DeckLink device'))
        self.sink_label.setText(translate(TAB_CONTEXT, 'Send to:'))
        self.device_label.setText(translate(TAB_CONTEXT, 'Device number:'))
        self.detect_button.setText(translate(TAB_CONTEXT, 'Detect'))
        self.mode_label.setText(translate(TAB_CONTEXT, 'Video mode:'))
        self.keyer_label.setText(translate(TAB_CONTEXT, 'Keyer:'))
        self.capture_group_box.setTitle(translate(TAB_CONTEXT, 'Capture'))
        self.backend_label.setText(translate(TAB_CONTEXT, 'Method:'))
        self.screen_label.setText(translate(TAB_CONTEXT, 'Screen:'))
        self.black_desktop_check_box.setText(
            translate(TAB_CONTEXT,
                      'Send black instead of the desktop when "Show Desktop" is used'))
        self.black_desktop_check_box.setToolTip(
            translate(TAB_CONTEXT,
                      'Leave this off to mirror what the HDMI output does. OpenLP\'s '
                      '"Black" and "Blank to Theme" buttons are captured as-is either way.'))
        self.status_group_box.setTitle(translate(TAB_CONTEXT, 'Status'))
        self.refresh_button.setText(translate(TAB_CONTEXT, 'Refresh'))

    def resizeEvent(self, event=None):
        """
        Skip SettingsTab's two-column resize handling; this tab is single-column.
        """
        QtWidgets.QWidget.resizeEvent(self, event)

    def load(self):
        """
        Populate the UI from settings.
        """
        self._reload_screens()
        self.enabled_check_box.setChecked(bool(self.settings.value('decklink/enabled')))
        self._select(self.sink_combo_box, self.settings.value('decklink/sink'))
        self.device_spin_box.setValue(int(self.settings.value('decklink/device number')))
        self._select(self.mode_combo_box, self.settings.value('decklink/mode'))
        self._select(self.keyer_combo_box, self.settings.value('decklink/keyer mode'))
        self._select(self.backend_combo_box, self.settings.value('decklink/capture backend'))
        self._select(self.screen_combo_box, int(self.settings.value('decklink/screen number')))
        self.black_desktop_check_box.setChecked(
            bool(self.settings.value('decklink/black on show desktop')))
        self._update_status()

    def save(self):
        """
        Write the UI back to settings and ask the plugin to reconfigure.
        """
        self.settings.setValue('decklink/enabled', self.enabled_check_box.isChecked())
        self.settings.setValue('decklink/sink', self.sink_combo_box.currentData())
        self.settings.setValue('decklink/device number', self.device_spin_box.value())
        self.settings.setValue('decklink/mode', self.mode_combo_box.currentData())
        self.settings.setValue('decklink/keyer mode', self.keyer_combo_box.currentData())
        self.settings.setValue('decklink/capture backend', self.backend_combo_box.currentData())
        self.settings.setValue('decklink/screen number', self.screen_combo_box.currentData())
        self.settings.setValue('decklink/black on show desktop',
                               self.black_desktop_check_box.isChecked())
        self.settings_form.register_post_process('decklink_config_updated')

    def _reload_screens(self):
        self.screen_combo_box.clear()
        self.screen_combo_box.addItem(
            translate(TAB_CONTEXT, 'Follow the OpenLP display screen'), -1)
        for number, label, _is_display in list_screens():
            self.screen_combo_box.addItem(label, number)

    @staticmethod
    def _select(combo_box, value):
        index = combo_box.findData(value)
        if index >= 0:
            combo_box.setCurrentIndex(index)

    def _update_status(self):
        """
        Show what is and is not working, without touching the hardware.
        """
        lines = ['Session type: {}'.format(session_type())]
        problems = diagnostics()
        if problems:
            lines.append('')
            lines.extend('Problem: {}'.format(problem) for problem in problems)
        else:
            lines.append('GStreamer and decklinkvideosink are present.')
        self.status_label.setText('\n'.join(lines))
        self.pipeline_label.setText(self._describe_pipeline())

    def _describe_pipeline(self):
        """
        Render the pipeline this configuration would build.
        """
        try:
            from .config import OutputConfig
            from .launch import build_caps, build_sink_fragment
            config = OutputConfig(
                device_number=self.device_spin_box.value(),
                mode=self.mode_combo_box.currentData() or '1080p30',
                sink=self.sink_combo_box.currentData() or SINK_DECKLINK,
                keyer_mode=self.keyer_combo_box.currentData() or 'off')
            return '... ! {caps} ! {sink}'.format(caps=build_caps(config),
                                                  sink=build_sink_fragment(config))
        except Exception as error:  # noqa: BLE001 - display only
            return str(error)

    def on_detect_clicked(self):
        """
        Probe for DeckLink devices and report what answered.
        """
        found = probe_devices()
        if found:
            self.device_spin_box.setValue(found[0])
            message = translate(TAB_CONTEXT, 'Responding device numbers: {devices}').format(
                devices=', '.join(str(number) for number in found))
        else:
            message = translate(
                TAB_CONTEXT,
                'No DeckLink devices responded. Check that the Blackmagic Desktop Video '
                'driver is installed and that the card is not in use by another '
                'application.')
        QtWidgets.QMessageBox.information(
            self, translate(TAB_CONTEXT, 'DeckLink Device Detection'), message)
        self._update_status()

    def on_refresh_clicked(self):
        self._reload_screens()
        self._select(self.screen_combo_box, int(self.settings.value('decklink/screen number')))
        self._update_status()
