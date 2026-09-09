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
xdg-desktop-portal ScreenCast client, for capturing under Wayland.

Wayland has no equivalent of X11's "just read the root window", so a compositor
screencast must be negotiated over D-Bus. The portal returns a PipeWire node id
and a file descriptor for the PipeWire socket, which ``pipewiresrc`` consumes.

The negotiation uses QtDBus rather than a third-party D-Bus library, because
OpenLP already ships a Qt binding and a community plugin should not drag in
extra dependencies.

Persistence matters here. Without a stored ``restore_token`` the compositor
asks the operator to pick a screen every time OpenLP starts, which is unusable
on an unattended machine. We request ``persist_mode=2`` and pass the token back
on subsequent runs. Note KDE did not persist tokens across reboots before
Plasma 6.5 (KDE bug 480235).

UNVERIFIED: this module has not been executed against a live portal. It is the
one part of the plugin that needs testing on the target machine before it can
be trusted. ``tools/smoketest.py`` exercises it in isolation.
"""
import logging
import os
import secrets

from .compat import QtCore


log = logging.getLogger(__name__)

PORTAL_SERVICE = 'org.freedesktop.portal.Desktop'
PORTAL_PATH = '/org/freedesktop/portal/desktop'
SCREENCAST_IFACE = 'org.freedesktop.portal.ScreenCast'
REQUEST_IFACE = 'org.freedesktop.portal.Request'
SESSION_IFACE = 'org.freedesktop.portal.Session'

#: SelectSources "types" bitmask.
SOURCE_MONITOR = 1
SOURCE_WINDOW = 2
SOURCE_VIRTUAL = 4

#: SelectSources "cursor_mode" values.
CURSOR_HIDDEN = 1

#: SelectSources "persist_mode": 2 == persist until explicitly revoked.
PERSIST_UNTIL_REVOKED = 2

#: How long to wait for the operator to answer the portal dialog.
DEFAULT_TIMEOUT_MS = 120000


class PortalError(Exception):
    """
    Raised when the screencast portal cannot be negotiated.
    """


class ScreenCastSession(object):
    """
    One negotiated screencast: a PipeWire node id plus the socket fd.

    Keep the instance alive while the pipeline runs; closing it releases the
    compositor's stream.
    """

    def __init__(self, node_id, fd, restore_token, session_handle, connection):
        self.node_id = node_id
        self.fd = fd
        self.restore_token = restore_token
        self.session_handle = session_handle
        self._connection = connection
        self._closed = False

    def close(self):
        """
        Close the portal session and the PipeWire fd. Never raises.
        """
        if self._closed:
            return
        self._closed = True
        if self.fd is not None and self.fd >= 0:
            try:
                os.close(self.fd)
            except OSError as error:
                log.debug('Closing PipeWire fd failed: %s', error)
        try:
            message = QtCore.QDBusMessage.createMethodCall(
                PORTAL_SERVICE, self.session_handle, SESSION_IFACE, 'Close')
            self._connection.send(message)
        except Exception as error:  # noqa: BLE001 - teardown must not raise
            log.debug('Closing portal session failed: %s', error)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


class _ResponseWaiter(QtCore.QObject):
    """
    Waits for one portal Request's ``Response`` signal.

    The portal answers asynchronously, and the answer may involve a user
    dialog, so we spin a nested event loop with a timeout.
    """

    def __init__(self, connection, request_path, timeout_ms):
        super().__init__()
        self._connection = connection
        self._request_path = request_path
        self._timeout_ms = timeout_ms
        self.code = None
        self.results = None
        self._loop = QtCore.QEventLoop()

    def _handle(self, code, results):
        self.code = int(code)
        try:
            self.results = dict(results or {})
        except (TypeError, ValueError):
            self.results = {}
        self._loop.quit()

    def wait(self):
        """
        Return ``(code, results)``. Code 0 is success, 1 is user cancellation.
        """
        connected = self._connection.connect(
            PORTAL_SERVICE, self._request_path, REQUEST_IFACE, 'Response', self._handle)
        if not connected:
            raise PortalError('Could not subscribe to the portal response on {}'
                              .format(self._request_path))
        timer = QtCore.QTimer()
        timer.setSingleShot(True)
        timer.timeout.connect(self._loop.quit)
        timer.start(self._timeout_ms)
        _exec(self._loop)
        timer.stop()
        self._connection.disconnect(
            PORTAL_SERVICE, self._request_path, REQUEST_IFACE, 'Response', self._handle)
        if self.code is None:
            raise PortalError('Timed out waiting for the screen-sharing dialog. '
                              'On an unattended machine, grant the permission once '
                              'so it can be remembered.')
        return self.code, self.results


def _exec(loop):
    """
    Run a nested event loop across both Qt bindings.
    """
    runner = getattr(loop, 'exec', None) or getattr(loop, 'exec_')
    return runner()


def _token():
    """
    A fresh handle token, valid as a D-Bus object-path segment.
    """
    return 'openlp_decklink_{}'.format(secrets.token_hex(8))


def _call(connection, method, arguments):
    """
    Make a blocking call on the ScreenCast interface and return the reply.

    :raises PortalError: when D-Bus reports an error.
    """
    message = QtCore.QDBusMessage.createMethodCall(
        PORTAL_SERVICE, PORTAL_PATH, SCREENCAST_IFACE, method)
    message.setArguments(arguments)
    reply = connection.call(message)
    if reply.type() == QtCore.QDBusMessage.MessageType.ErrorMessage:
        raise PortalError('{} failed: {}'.format(method, reply.errorMessage()))
    return reply


def _request_path(reply):
    """
    Pull the Request object path out of a portal method reply.
    """
    arguments = reply.arguments()
    if not arguments:
        raise PortalError('Portal returned no request handle')
    handle = arguments[0]
    path = getattr(handle, 'path', None)
    return path() if callable(path) else str(handle)


def is_available():
    """
    True when a session bus is present and the ScreenCast portal answers.
    """
    try:
        connection = QtCore.QDBusConnection.sessionBus()
        if not connection.isConnected():
            return False
        message = QtCore.QDBusMessage.createMethodCall(
            PORTAL_SERVICE, PORTAL_PATH, 'org.freedesktop.DBus.Properties', 'Get')
        message.setArguments([SCREENCAST_IFACE, 'version'])
        reply = connection.call(message)
        return reply.type() != QtCore.QDBusMessage.MessageType.ErrorMessage
    except Exception as error:  # noqa: BLE001 - availability probe
        log.debug('ScreenCast portal probe failed: %s', error)
        return False


def negotiate(restore_token='', timeout_ms=DEFAULT_TIMEOUT_MS, source_types=SOURCE_MONITOR):
    """
    Negotiate a screencast and return a live :class:`ScreenCastSession`.

    :param restore_token: token from a previous run, to avoid re-prompting.
    :param timeout_ms: how long to wait for each portal step.
    :param source_types: SelectSources bitmask; monitors by default.
    :raises PortalError: on any failure, including user cancellation.
    """
    connection = QtCore.QDBusConnection.sessionBus()
    if not connection.isConnected():
        raise PortalError('No D-Bus session bus. Is this a desktop session?')

    # 1. CreateSession
    reply = _call(connection, 'CreateSession', [{
        'handle_token': _token(),
        'session_handle_token': _token(),
    }])
    code, results = _ResponseWaiter(connection, _request_path(reply), timeout_ms).wait()
    if code != 0:
        raise PortalError('Portal refused to create a session (code {})'.format(code))
    session_handle = results.get('session_handle')
    if not session_handle:
        raise PortalError('Portal returned no session handle')

    # 2. SelectSources
    options = {
        'handle_token': _token(),
        'types': source_types,
        'multiple': False,
        'cursor_mode': CURSOR_HIDDEN,
        'persist_mode': PERSIST_UNTIL_REVOKED,
    }
    if restore_token:
        options['restore_token'] = restore_token
    reply = _call(connection, 'SelectSources', [session_handle, options])
    code, results = _ResponseWaiter(connection, _request_path(reply), timeout_ms).wait()
    if code != 0:
        raise PortalError('Screen selection was cancelled (code {})'.format(code))

    # 3. Start
    reply = _call(connection, 'Start', [session_handle, '', {'handle_token': _token()}])
    code, results = _ResponseWaiter(connection, _request_path(reply), timeout_ms).wait()
    if code != 0:
        raise PortalError('Screen sharing was not started (code {})'.format(code))
    streams = results.get('streams') or []
    if not streams:
        raise PortalError('Portal started no streams')
    node_id = _first_node_id(streams)
    new_token = results.get('restore_token', '') or restore_token

    # 4. OpenPipeWireRemote
    reply = _call(connection, 'OpenPipeWireRemote', [session_handle, {}])
    fd = _extract_fd(reply)
    log.info('Portal screencast ready: node %s, fd %s', node_id, fd)
    return ScreenCastSession(node_id, fd, new_token, session_handle, connection)


def _first_node_id(streams):
    """
    Extract the PipeWire node id from the portal's stream list.

    The wire type is ``a(ua{sv})``; how QtDBus surfaces that varies, so probe.
    """
    first = streams[0]
    if isinstance(first, (list, tuple)) and first:
        return int(first[0])
    node_id = getattr(first, 'node_id', None)
    if node_id is not None:
        return int(node_id)
    raise PortalError('Could not read the PipeWire node id from {!r}'.format(first))


def _extract_fd(reply):
    """
    Pull the unix file descriptor out of the OpenPipeWireRemote reply.
    """
    arguments = reply.arguments()
    if not arguments:
        raise PortalError('OpenPipeWireRemote returned nothing')
    value = arguments[0]
    for attribute in ('fileDescriptor', 'fd'):
        accessor = getattr(value, attribute, None)
        if callable(accessor):
            return int(accessor())
    try:
        return int(value)
    except (TypeError, ValueError):
        raise PortalError('Could not read the PipeWire file descriptor from {!r}'.format(value))
