from enigma import eInputDeviceManager
from Components.config import config
from Components.ActionMap import ActionMap
from Components.Sources.List import List
from Components.Sources.StaticText import StaticText
from Components.Label import Label
from Screens.MessageBox import MessageBox
from Screens.Screen import Screen
from Tools.Log import Log

from twisted.internet import reactor

from .InputDeviceAdapterFlasher import InputDeviceUpdateChecker
from .InputDeviceUpdateHandlerBase import InputDeviceUpdateHandlerBase
from .InputDeviceIRProg import InputDeviceIRProg
from .InputDeviceSettings import InputDeviceSettings
from . import (
    _, ensureInputDeviceManagerConfig, filterInputDevices, getInputDeviceAddress,
    getInputDeviceConnected, isValidInputDeviceAddress, markInputDeviceConnected,
    markInputDeviceDisconnected
)

try:
    from Screens.SetupGuide import SetupGuide
except ImportError:
    SetupGuide = None


INPUT_DEVICE_MANAGEMENT_SKIN = """
<screen name="InputDeviceManagement" position="center,120" size="920,520" title="Input devices">
    <eLabel position="10,5" size="210,40" backgroundColor="#9f1313" />
    <eLabel position="230,5" size="210,40" backgroundColor="#1f771f" />
    <eLabel position="450,5" size="210,40" backgroundColor="#a08500" />
    <eLabel position="670,5" size="210,40" backgroundColor="#18188b" />
    <widget name="key_red" position="10,5" size="210,40" zPosition="1" font="Regular;20" halign="center" valign="center" transparent="1" />
    <widget name="key_green" position="230,5" size="210,40" zPosition="1" font="Regular;20" halign="center" valign="center" transparent="1" />
    <widget name="key_yellow" position="450,5" size="210,40" zPosition="1" font="Regular;20" halign="center" valign="center" transparent="1" />
    <widget name="key_blue" position="670,5" size="210,40" zPosition="1" font="Regular;20" halign="center" valign="center" transparent="1" />
    <eLabel position="10,50" size="900,1" backgroundColor="grey" />
    <widget source="list" render="Listbox" position="10,60" size="900,360" scrollbarMode="showOnDemand" transparent="1">
        <convert type="TemplatedMultiContent">
            {"template": [
                    MultiContentEntryText(pos=(10, 4), size=(500, 28), font=0, flags=RT_HALIGN_LEFT | RT_VALIGN_CENTER, text=0),
                    MultiContentEntryText(pos=(665, 4), size=(210, 28), font=1, flags=RT_HALIGN_RIGHT | RT_VALIGN_CENTER, text=4),
                    MultiContentEntryText(pos=(10, 36), size=(300, 22), font=1, flags=RT_HALIGN_LEFT | RT_VALIGN_CENTER, text=2),
                    MultiContentEntryText(pos=(320, 36), size=(330, 22), font=1, flags=RT_HALIGN_RIGHT | RT_VALIGN_CENTER, text=1),
                    MultiContentEntryText(pos=(665, 36), size=(210, 22), font=1, flags=RT_HALIGN_RIGHT | RT_VALIGN_CENTER, text=3),
                ],
                "fonts": [gFont("Regular", 24), gFont("Regular", 18)],
                "itemHeight": 74
            }
        </convert>
    </widget>
    <eLabel position="10,430" size="900,1" backgroundColor="grey" />
    <widget source="description" render="Label" position="10,440" size="900,70" font="Regular;22" halign="center" valign="center" transparent="1" />
</screen>
"""


class InputDeviceManagementBase:
    def __init__(self):
        ensureInputDeviceManagerConfig()
        try:
            self["pin"] = StaticText()  # Unused dummy
        except Exception as err:
            Log.w("Unable to create dummy pin widget: %s" % (err,))
        self._devices = []
        self._list = List([], enableWrapAround=True, templateName="inputdevice")

        self._dm = eInputDeviceManager.getInstance()

        self.__highlightDevice = None
        self._listFeedbackDisabled = False

        self._dm.deviceListChanged.append(self._devicesChanged)
        self._dm.deviceStateChanged.append(self._devicesChanged)
        self._dm.batteryLow.append(self._devicesChanged)
        self._dm.unboundRemoteKeyPressed.append(self._onUnboundRemoteKeyPressed)
        if hasattr(self, "onClose"):
            self.onClose.append(self._removeInputDeviceManagerCallbacks)
        self._refresh()

    def _removeInputDeviceManagerCallbacks(self):
        for signal, callback in (
            (self._dm.deviceListChanged, self._devicesChanged),
            (self._dm.deviceStateChanged, self._devicesChanged),
            (self._dm.batteryLow, self._devicesChanged),
            (self._dm.unboundRemoteKeyPressed, self._onUnboundRemoteKeyPressed),
        ):
            try:
                signal.remove(callback)
            except ValueError:
                pass

    def _disableListFeedback(self):
        # OpenATV-only: do not mutate the user setting while the screen is open.
        # Haptic feedback is controlled directly in _highlight().
        self._listFeedbackDisabled = False

    def _restoreListFeedback(self):
        self._listFeedbackDisabled = False

    def responding(self):
        return self._dm.responding()

    def available(self):
        return self._dm.available()

    def _entryToDevice(self, entry):
        if isinstance(entry, (list, tuple)):
            for item in reversed(entry):
                if hasattr(item, "address") and hasattr(item, "connected"):
                    return item
        return None

    def _getCurrentInputDevice(self):
        try:
            index = int(self._list.index)
        except (AttributeError, TypeError, ValueError):
            index = -1
        if 0 <= index < len(self._devices):
            device = self._entryToDevice(self._devices[index])
            if device:
                return device
        return self._entryToDevice(self._list.getCurrent())

    _currentInputDevice = property(_getCurrentInputDevice)

    def _reload(self):
        index = self._list.index
        if index < 0:
            index = 0
        self._devices = self._getInputDevices()
        self._list.list = self._devices
        if self._getInputDevicesCount() > index:
            self._list.index = index
        elif self._getInputDevicesCount():
            self._list.index = 0

    def _refresh(self):
        self._dm.refresh()

    def _getInputDevicesCount(self):
        return len(self._devices)

    def _getInputDevices(self):
        items = filterInputDevices(self._dm.getAvailableDevices())
        devices = []
        buildfunc = getattr(self, "buildfunc", self._inputDeviceBuildFunc)
        for device in items:
            try:
                entry = buildfunc(device.address(), device)
            except TypeError:
                entry = self._inputDeviceBuildFunc(device.address(), device)
            if not isinstance(entry, tuple):
                entry = (entry,)
            devices.append(entry + (device,))
        return devices

    def _inputDeviceBuildFunc(self, title, device):
        bound = ""
        connected = getInputDeviceConnected(device)
        if connected and device.bound():
            bound = _("bound")
        # A device may be connected but not yet bound right after binding has started!
        elif connected:
            bound = _("...")
        name = self._getDeviceDisplayName(device)
        return (
            name,
            self._getDeviceStatusLine(device),
            device.address(),
            bound,
            _("connected") if connected else _("disconnected")
       )

    def _getDeviceBatteryLevel(self, device):
        try:
            return int(device.batteryLevel())
        except (AttributeError, TypeError, ValueError):
            return None

    def _getDeviceBatteryText(self, device):
        level = self._getDeviceBatteryLevel(device)
        if level is None or level <= 0:
            return _("Battery: unknown")
        return _("Battery: %d%%") % level

    def _getDeviceRssiText(self, device):
        try:
            return _("RSSI: %d dBm") % int(device.rssi())
        except (AttributeError, TypeError, ValueError):
            return _("RSSI: unknown")

    def _getDeviceFirmwareVersion(self, device):
        try:
            version = str(device.version()).strip()
        except (AttributeError, TypeError, ValueError):
            version = ""
        return "" if not version or version == "0.0" else version

    def _getDeviceVersionText(self, device):
        version = self._getDeviceFirmwareVersion(device)
        if not version:
            return _("Firmware: unknown")
        return _("Firmware: %s") % version

    def _getDeviceDisplayName(self, device):
        name = device.name() or device.shortName() or _("DM Remote")
        name = _(name)
        version = self._getDeviceFirmwareVersion(device)
        if version:
            return _("%s  FW %s") % (name, version)
        return name

    def _getDeviceStatusLine(self, device):
        level = self._getDeviceBatteryLevel(device)
        if level is None or level <= 0:
            battery = _("Battery: --")
        else:
            battery = _("Battery: %d%%") % level
        try:
            rssi = _("RSSI: %d dBm") % int(device.rssi())
        except (AttributeError, TypeError, ValueError):
            rssi = _("RSSI: --")
        return "%s   %s" % (battery, rssi)

    def _getDeviceDetailsText(self, device):
        return "%s   %s   %s" % (
            self._getDeviceBatteryText(device),
            self._getDeviceRssiText(device),
            self._getDeviceVersionText(device),
        )

    def _devicesChanged(self, *args):
        pass

    def _connectDevice(self, device):
        if not device:
            return
        markInputDeviceConnected(device.address())
        self._dm.connectDevice(device)
        self._scheduleRefresh()

    def _disconnectDevice(self, device):
        if not device or not getInputDeviceConnected(device):
            return
        markInputDeviceDisconnected(device.address())
        self._dm.disconnectDevice(device)
        self._reload()
        self._updateSelectionState()
        self._scheduleRefresh()

    def _scheduleRefresh(self):
        for delay in (0.2, 1.0, 2.5):
            reactor.callLater(delay, self._refreshAndReload)

    def _refreshAndReload(self):
        self._refresh()
        self._reload()
        self._updateSelectionState()

    def _updateSelectionState(self):
        callback = getattr(self, "_InputDeviceManagement__onSelectionChanged", None)
        if callable(callback):
            callback()

    def _onUnboundRemoteKeyPressed(self, address, key):
        pass

    def _highlight(self):
        d = self._currentInputDevice
        if d:
            if not self.__highlightDevice or d.address() != self.__highlightDevice.address():
                if config.inputDevices.settings.listboxFeedback.value:
                    d.vibrate()
                    reactor.callLater(0.4, d.vibrate)

                try:
                    col = int(config.inputDevices.settings.connectedColor.value, 0)
                except ValueError:
                    col = 0x00ff00
                contrast = 0xffffff - col

                d.setLedColor(contrast)
                reactor.callLater(0.8, d.setLedColor, col)
                self.__highlightDevice = d
        else:
            self.__highlightDevice = None


class InputDeviceManagement(Screen, InputDeviceManagementBase, InputDeviceUpdateHandlerBase):
    skin = INPUT_DEVICE_MANAGEMENT_SKIN

    def __init__(self, session):
        Screen.__init__(self, session)
        self.setTitle(_("Input devices"))
        InputDeviceManagementBase.__init__(self)
        InputDeviceUpdateHandlerBase.__init__(self)
        self["description"] = StaticText("")
        self["list"] = self._list
        self["inputActions"] = ActionMap(["OkCancelActions", "ColorActions"],
        actions={
            "ok": self._onOk,
            "cancel": self.close,
            "red": self._dfu,
            "green": self._irProg,
            "yellow": self._rescan,
            "blue": self._settings,
        })

        self["key_red"] = Label()
        self["key_green"] = Label()
        self["key_yellow"] = Label(_("Rescan"))
        self["key_blue"] = Label(_("Settings"))
        self._updateChecker = InputDeviceUpdateChecker()
        self._updateChecker.onUpdateAvailable.append(self._onUpdateAvailable)
        self._updateChecker.check()
        self._list.onSelectionChanged.append(self.__onSelectionChanged)
        self._devices = []
        self._rescanStatusActive = False
        self._reload()
        self.onShow.append(self._onShow)
        self.onHide.append(self._restoreListFeedback)
        self.onFirstExecBegin.append(self._checkAdapter)
        self.onLayoutFinish.append(self.__onSelectionChanged)

    def _onShow(self):
        self._disableListFeedback()
        self._refresh()

    def _dfu(self):
        if not self._dm.hasFeature(eInputDeviceManager.FEATURE_DFU_UPDATE):
            return
        if SetupGuide is None:
            self.session.open(MessageBox, _("DFU update setup is not available on this image."), type=MessageBox.TYPE_INFO)
            return
        from .Dfu.DfuGuide import DfuWelcomeStep, DfuUpdateStep, DfuFinishStep
        steps = [{
            10: DfuWelcomeStep,
            20: DfuUpdateStep,
            30: DfuFinishStep,
        }]
        self.session.open(SetupGuide, steps=steps)

    def _updateButtons(self):
        device = self._currentInputDevice
        if device and getInputDeviceConnected(device) and device.checkVersion(1, 3) >= 0:
            self["key_green"].setText(_("IR-Setup"))
        else:
            self["key_green"].setText("")

        if self._dm.hasFeature(eInputDeviceManager.FEATURE_DFU_UPDATE):
            self["key_red"].setText(_("Update"))
        else:
            self["key_red"].setText("")

    def _irProg(self):
        device = self._currentInputDevice
        if not device or not getInputDeviceConnected(device) or device.checkVersion(1, 3) < 0:
            return
        self.session.open(InputDeviceIRProg, device)

    def _settings(self):
        self.session.open(InputDeviceSettings)

    def _rescan(self):
        Log.i("[BluetoothSetup] Rescan requested")
        self._rescanStatusActive = True
        self["description"].text = _("Rescanning...")
        try:
            self._dm.rescan()
        except AttributeError:
            self._dm.refresh()
        reactor.callLater(0.5, self._refreshAndReload)
        reactor.callLater(1.5, self._finishRescan)
        reactor.callLater(3.0, self._refreshAndReload)

    def _finishRescan(self):
        self._reload()
        count = self._getInputDevicesCount()
        Log.i("[BluetoothSetup] Rescan complete: %d devices" % count)
        self["description"].text = _("Scan complete (%d devices)") % count
        reactor.callLater(1.2, self._endRescanStatus)

    def _endRescanStatus(self):
        self._rescanStatusActive = False
        self.__onSelectionChanged()

    def _onUpdateAvailable(self):
        text = self._fpUpdateText()
        self.session.openWithCallback(
            self._onUpdateAnswer,
            MessageBox,
            text,
            type=MessageBox.TYPE_YESNO,
            windowTitle=_("Update Bluetooth Receiver Firmware?"))

    def _checkAdapter(self):
        if self.available() and not self.responding():
            self.session.openWithCallback(
                self._onUpdateAnswer,
                MessageBox,
                _("Your Dreambox Bluetooth receiver has no firmware installed.\nInstall the latest firmware now?"),
                type=MessageBox.TYPE_YESNO,
                windowTitle=_("Flash Bluetooth Receiver Firmware?"))
            return

    def __onSelectionChanged(self):
        self._highlight()
        self._updateButtons()
        if getattr(self, "_rescanStatusActive", False):
            return
        if not self.available():
            self["description"].text = _("No Dreambox Bluetooth receiver detected! Sorry!")
            return
        text = ""
        device = self._currentInputDevice
        if device and getInputDeviceConnected(device):
            text = _("Press OK to disconnect")
        elif device:
            text = _("Press OK to connect the selected remote control.")
            if self._dm.hasFeature(eInputDeviceManager.FEATURE_UNCONNECTED_KEYPRESS) and len(self._devices) > 1:
                text = "%s\n%s" % (_("Please pick up the remote control you want to connect and press any number key on it to select it in the list."), text)
        if device:
            details = self._getDeviceDetailsText(device)
            text = "%s\n%s" % (text, details) if text else details
        if text != self["description"].text:
            self["description"].text = text

    def _devicesChanged(self, *args):
        if len(args) >= 2:
            address = args[0]
            try:
                state = int(args[1])
            except (TypeError, ValueError):
                state = -1
            if state == 0:
                markInputDeviceDisconnected(address)
        self._reload()
        self.__onSelectionChanged()

    def _onOk(self):
        device = self._currentInputDevice
        if not device:
            return
        name = device.shortName() or "Dream RCU"
        if getInputDeviceConnected(device):
            self.session.openWithCallback(
                self._onDisconnectResult,
                MessageBox,
                _("Really disconnect %s (%s)?") % (name, device.address()),
                windowTitle=_("Disconnect paired remote?"),
            )
        else:
            self.session.openWithCallback(
                self._onConnectResult,
                MessageBox,
                _("Do you really want to connect %s (%s) ") % (name, device.address()),
                windowTitle=_("Connect new remote?"),
            )

    def _onDisconnectResult(self, result):
        if result:
            self._disconnectDevice(self._currentInputDevice)
            self._reload()
            self._updateSelectionState()

    def _onConnectResult(self, result):
        if result:
            self._connectDevice(self._currentInputDevice)

    def _onUnboundRemoteKeyPressed(self, address, key):
        if not isValidInputDeviceAddress(address):
            return
        index = 0
        for entry in self._devices:
            device = self._entryToDevice(entry)
            if device and getInputDeviceAddress(device) == str(address).strip().lower():
                self._list.index = index
                break
            index += 1
