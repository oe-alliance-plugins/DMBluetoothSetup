# -*- coding: utf-8 -*-
from __future__ import print_function
from Components.config import config, ConfigOnOff, ConfigSelection, ConfigSubsection, ConfigYesNo
from Components.Language import language
from Tools.Directories import resolveFilename, SCOPE_PLUGINS, SCOPE_LANGUAGE
import os
import gettext

PluginLanguageDomain = "BluetoothSetup"
PluginLanguagePath = "SystemPlugins/BluetoothSetup/locale"


def localeInit():
	gettext.bindtextdomain(PluginLanguageDomain, resolveFilename(SCOPE_PLUGINS, PluginLanguagePath))


def _(txt):
	if gettext.dgettext(PluginLanguageDomain, txt):
		return gettext.dgettext(PluginLanguageDomain, txt)
	else:
		print("[" + PluginLanguageDomain + "] fallback to default translation for " + txt)
		return gettext.gettext(txt)


localeInit()
language.addCallback(localeInit)

__version__ = "2.0"

COLOR_CHOICES = [
    ("0xFF0000", _("red")),
    ("0xFF3333", _("rose")),
    ("0xFF5500", _("orange")),
    ("0xDD9900", _("yellow")),
    ("0x99DD00", _("lime")),
    ("0x00FF00", _("green")),
    ("0x00FF99", _("aqua")),
    ("0x00BBFF", _("olympic blue")),
    ("0x0000FF", _("blue")),
    ("0x6666FF", _("azure")),
    ("0x9900FF", _("purple")),
    ("0xFF0066", _("pink")),
]

_COLOR_VALUES = tuple(choice[0] for choice in COLOR_CHOICES)
_COLOR_NOTIFIERS_INSTALLED = False

_FORCED_DISCONNECTED_ADDRESSES = set()


def markInputDeviceDisconnected(address):
    address = str(address or "").strip().lower()
    if isValidInputDeviceAddress(address):
        _FORCED_DISCONNECTED_ADDRESSES.add(address)


def markInputDeviceConnected(address):
    address = str(address or "").strip().lower()
    _FORCED_DISCONNECTED_ADDRESSES.discard(address)


def isInputDeviceMarkedDisconnected(device):
    return getInputDeviceAddress(device) in _FORCED_DISCONNECTED_ADDRESSES


def getInputDeviceConnected(device):
    if isInputDeviceMarkedDisconnected(device):
        return False
    return bool(_safeCall(device, "connected", False))



def _validColorValue(value, default):
    value = str(value) if value is not None else default
    return value if value in _COLOR_VALUES else default


def _getConfigValue(configElement, default):
    try:
        return configElement.value
    except AttributeError:
        return default


def _setLedColor(methodName, value, label):
    try:
        from enigma import eInputDeviceManager
        manager = eInputDeviceManager.getInstance()
        rgb = int(value, 0)
    except Exception:
        return False

    sent = False
    devices = filterInputDevices(manager.getAvailableDevices())
    for device in devices:
        address = getInputDeviceAddress(device)
        if not getInputDeviceConnected(device):
            continue
        method = getattr(device, methodName, None)
        if not callable(method):
            continue
        try:
            method(rgb)
            sent = True
        except Exception:
            pass
    return sent


def applyInputDeviceBtColor():
    ensureInputDeviceManagerConfig()
    return _setLedColor("setLedColor", config.inputDevices.settings.connectedColor.value, "BT")


def applyInputDeviceIrColor():
    ensureInputDeviceManagerConfig()
    return _setLedColor("setLedColorIr", config.inputDevices.settings.connectedColorIr.value, "IR")


def _onConnectedRcuColorChanged(configElement):
    _setLedColor("setLedColor", configElement.value, "BT")


def _onConnectedRcuColorIrChanged(configElement):
    _setLedColor("setLedColorIr", configElement.value, "IR")


def applyInputDeviceColors():
    applyInputDeviceBtColor()
    applyInputDeviceIrColor()


def ensureInputDeviceManagerConfig():
    global _COLOR_NOTIFIERS_INSTALLED
    if not hasattr(config, "inputDevices"):
        config.inputDevices = ConfigSubsection()
    if not hasattr(config.inputDevices, "settings"):
        config.inputDevices.settings = ConfigSubsection()
    settings = config.inputDevices.settings
    if not hasattr(settings, "firstDevice"):
        settings.firstDevice = ConfigYesNo(default=True)
    if not hasattr(settings, "logBattery"):
        settings.logBattery = ConfigYesNo(default=False)
    if not hasattr(settings, "listboxFeedback"):
        settings.listboxFeedback = ConfigOnOff(default=False)

    currentColor = _validColorValue(_getConfigValue(getattr(settings, "connectedColor", None), "0xFF0066"), "0xFF0066")
    if not hasattr(settings, "connectedColor") or not hasattr(settings.connectedColor, "choices"):
        settings.connectedColor = ConfigSelection(COLOR_CHOICES, default=currentColor)

    currentIrColor = _validColorValue(_getConfigValue(getattr(settings, "connectedColorIr", None), "0x99DD00"), "0x99DD00")
    if not hasattr(settings, "connectedColorIr") or not hasattr(settings.connectedColorIr, "choices"):
        settings.connectedColorIr = ConfigSelection(COLOR_CHOICES, default=currentIrColor)

    if not _COLOR_NOTIFIERS_INSTALLED:
        settings.connectedColor.addNotifier(_onConnectedRcuColorChanged, initial_call=False)
        settings.connectedColorIr.addNotifier(_onConnectedRcuColorIrChanged, initial_call=False)
        _COLOR_NOTIFIERS_INSTALLED = True



def _safeCall(obj, method, default=None):
    func = getattr(obj, method, None)
    if not callable(func):
        return default
    try:
        return func()
    except Exception:
        return default


def getInputDeviceAddress(device):
    address = _safeCall(device, "address", "")
    if address is None:
        return ""
    return str(address).strip().lower()


def isValidInputDeviceAddress(address):
    if not address:
        return False
    address = str(address).strip().lower()
    if address in ("00:00:00:00:00:00", "000000000000"):
        return False
    parts = address.split(":")
    if len(parts) != 6:
        return False
    try:
        values = [int(part, 16) for part in parts]
    except ValueError:
        return False
    return any(values)


def isValidInputDevice(device):
    return isValidInputDeviceAddress(getInputDeviceAddress(device))


def _deviceScore(device):
    score = 0
    if _safeCall(device, "connected", False):
        score += 8
    if _safeCall(device, "bound", False):
        score += 4
    if _safeCall(device, "ready", False):
        score += 2
    try:
        score += max(min(int(_safeCall(device, "rssi", -127)), 0), -127) + 127
    except (TypeError, ValueError):
        pass
    return score


def filterInputDevices(devices):
    filtered = []
    indexByAddress = {}
    for device in devices or []:
        address = getInputDeviceAddress(device)
        if not isValidInputDeviceAddress(address):
            continue
        currentIndex = indexByAddress.get(address)
        if currentIndex is None:
            indexByAddress[address] = len(filtered)
            filtered.append(device)
        elif _deviceScore(device) > _deviceScore(filtered[currentIndex]):
            filtered[currentIndex] = device
    return filtered


initInputDeviceManagerConfig = ensureInputDeviceManagerConfig
ensureInputDeviceManagerConfig()
