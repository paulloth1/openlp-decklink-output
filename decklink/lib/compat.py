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
Qt binding compatibility shim.

OpenLP 3.1.x runs on PyQt5; the 4.0 alpha branch has moved to PySide6. This
module exposes the handful of Qt names the plugin needs from whichever binding
the host application already imported, so the plugin works on both without a
separate code path.
"""
import logging

log = logging.getLogger(__name__)

QT_BINDING = None

try:
    from PyQt5 import QtCore, QtWidgets  # noqa: F401
    from PyQt5.QtCore import pyqtSlot as Slot  # noqa: F401

    QT_BINDING = 'PyQt5'
except ImportError:  # pragma: no cover - depends on host install
    from PySide6 import QtCore, QtWidgets  # noqa: F401
    from PySide6.QtCore import Slot  # noqa: F401

    QT_BINDING = 'PySide6'

log.debug('Using Qt binding %s', QT_BINDING)


def align_top():
    """
    Return the AlignTop flag, which moved namespace between Qt5 and Qt6.
    """
    try:
        return QtCore.Qt.AlignmentFlag.AlignTop
    except AttributeError:  # pragma: no cover - PyQt5 path
        return QtCore.Qt.AlignTop


def all_fields_grow():
    """
    Return QFormLayout's AllNonFixedFieldsGrow, which also moved namespace.
    """
    try:
        return QtWidgets.QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow
    except AttributeError:  # pragma: no cover - PyQt5 path
        return QtWidgets.QFormLayout.AllNonFixedFieldsGrow
