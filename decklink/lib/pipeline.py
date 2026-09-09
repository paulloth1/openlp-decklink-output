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
Pipeline lifecycle management.

Owns the GStreamer pipeline object, its bus and its state transitions. The
launch string itself is built by :mod:`.launch`, which is deliberately free of
Qt and GStreamer so it can be unit-tested anywhere.
"""
import logging

from .capture import build_backend
from .compat import QtCore
from .gst import load_gst
from .launch import PipelineError, build_launch


log = logging.getLogger(__name__)

#: How often to drain the GStreamer bus, in milliseconds. Polling from a Qt
#: timer avoids running a GLib main loop alongside Qt's.
BUS_POLL_MS = 250


class DecklinkPipeline(QtCore.QObject):
    """
    Owns one GStreamer pipeline and its lifecycle.

    ``start`` and ``stop`` are idempotent. Errors are recorded on
    :attr:`last_error` and reported through :attr:`error_occurred` rather than
    raised from the bus callback, because a failing SDI feed must never take
    OpenLP down with it.
    """

    #: Emitted with a human-readable message when the pipeline fails.
    error_occurred = QtCore.pyqtSignal(str) if hasattr(QtCore, 'pyqtSignal') else QtCore.Signal(str)

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self._config = config
        self._gst = None
        self._pipeline = None
        self._selector = None
        self._live_pad = None
        self._black_pad = None
        self._backend = None
        self._blank = False
        self.last_error = None
        self._bus_timer = QtCore.QTimer(self)
        self._bus_timer.setInterval(BUS_POLL_MS)
        self._bus_timer.timeout.connect(self._drain_bus)

    @property
    def config(self):
        return self._config

    @property
    def is_running(self):
        return self._pipeline is not None

    @property
    def restore_token(self):
        """
        The portal restore token to persist, or ''.
        """
        return self._backend.restore_token if self._backend else ''

    def describe(self):
        """
        The launch string for this config, without starting anything.

        Useful in the settings tab and in bug reports; building it does not
        touch the capture backend's session.
        """
        try:
            backend = self._backend or build_backend(self._config)
            return build_launch(self._config, backend.fragment(self._config))
        except Exception as error:  # noqa: BLE001 - description is best-effort
            return 'unavailable: {}'.format(error)

    def start(self):
        """
        Build and start the pipeline. Returns True on success.
        """
        if self._pipeline is not None:
            return True
        gst, _ = load_gst()
        if gst is None:
            return self._fail('GStreamer is not available')
        self._gst = gst
        try:
            self._backend = build_backend(self._config)
            available, reason = self._backend.is_available()
            if not available:
                return self._fail('Capture backend {} is unavailable: {}'
                                  .format(self._backend.name, reason))
            launch = build_launch(self._config, self._backend.fragment(self._config))
            log.info('Starting pipeline: %s', launch)
            self._pipeline = gst.parse_launch(launch)
            self._backend.configure(self._pipeline)
            self._wire_selector()
            self._apply_blank()
            result = self._pipeline.set_state(gst.State.PLAYING)
            if result == gst.StateChangeReturn.FAILURE:
                return self._fail('The pipeline refused to start. '
                                  'Check the DeckLink device number and mode.')
            self._bus_timer.start()
            self.last_error = None
            return True
        except Exception as error:  # noqa: BLE001 - never propagate into OpenLP
            log.exception('Failed to start the DeckLink pipeline')
            self.stop()
            return self._fail(str(error))

    def stop(self):
        """
        Tear everything down. Safe to call when already stopped.
        """
        self._bus_timer.stop()
        if self._pipeline is not None and self._gst is not None:
            try:
                self._pipeline.set_state(self._gst.State.NULL)
            except Exception as error:  # noqa: BLE001 - teardown must not raise
                log.debug('Setting pipeline to NULL failed: %s', error)
        self._pipeline = None
        self._selector = None
        self._live_pad = None
        self._black_pad = None
        if self._backend is not None:
            self._backend.release()
        log.info('DeckLink pipeline stopped')

    def restart(self):
        """
        Stop and start, used when a change cannot be applied live.
        """
        was_running = self.is_running
        self.stop()
        if was_running:
            return self.start()
        return False

    def update_config(self, config):
        """
        Swap in a new config, restarting if anything structural changed.
        """
        structural = (
            config.mode != self._config.mode
            or config.device_number != self._config.device_number
            or config.backend != self._config.backend
            or config.sink != self._config.sink
            or config.keyer_mode != self._config.keyer_mode
            or config.region != self._config.region
        )
        self._config = config
        if structural and self.is_running:
            log.info('Configuration changed structurally; restarting pipeline')
            self.restart()

    def set_blank(self, blank):
        """
        Switch the output between the captured screen and hard black.
        """
        blank = bool(blank)
        if blank == self._blank:
            return
        self._blank = blank
        log.info('DeckLink output %s', 'blanked' if blank else 'unblanked')
        self._apply_blank()

    def _apply_blank(self):
        if self._selector is None:
            return
        pad = self._black_pad if self._blank else self._live_pad
        if pad is None:
            return
        try:
            self._selector.set_property('active-pad', pad)
        except Exception as error:  # noqa: BLE001
            log.warning('Could not switch the output selector: %s', error)

    def _wire_selector(self):
        """
        Find the selector's two sink pads.

        parse_launch requests them in link order, so the live branch is first
        and the black branch second.
        """
        self._selector = self._pipeline.get_by_name('selector')
        if self._selector is None:
            raise PipelineError('input-selector missing from the pipeline')
        pads = list(self._selector.sinkpads)
        if len(pads) < 2:
            raise PipelineError('Expected two selector inputs, found {}'.format(len(pads)))
        self._live_pad, self._black_pad = pads[0], pads[1]

    def _drain_bus(self):
        """
        Pull any pending messages off the bus without blocking.
        """
        if self._pipeline is None or self._gst is None:
            return
        gst = self._gst
        bus = self._pipeline.get_bus()
        if bus is None:
            return
        message_types = (gst.MessageType.ERROR | gst.MessageType.WARNING
                         | gst.MessageType.EOS | gst.MessageType.STATE_CHANGED)
        while True:
            message = bus.timed_pop_filtered(0, message_types)
            if message is None:
                return
            if message.type == gst.MessageType.ERROR:
                error, debug = message.parse_error()
                log.error('Pipeline error: %s (%s)', error.message, debug)
                self._fail(error.message)
                self.stop()
                return
            if message.type == gst.MessageType.WARNING:
                warning, debug = message.parse_warning()
                log.warning('Pipeline warning: %s (%s)', warning.message, debug)
            elif message.type == gst.MessageType.EOS:
                log.warning('Pipeline reached end of stream unexpectedly')
                self._fail('The capture source ended unexpectedly')
                self.stop()
                return

    def _fail(self, message):
        self.last_error = message
        log.error('DeckLink output error: %s', message)
        try:
            self.error_occurred.emit(message)
        except Exception:  # noqa: BLE001 - signal delivery is best-effort
            pass
        return False
