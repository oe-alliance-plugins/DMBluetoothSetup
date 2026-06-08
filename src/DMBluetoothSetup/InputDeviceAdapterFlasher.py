from enigma import eConsoleAppContainer, eEnv, eInputDeviceManager
from Tools.Log import Log
from Screens.MessageBox import MessageBox
from Tools.Directories import fileExists

from Tools.HardwareInfo import HardwareInfo


def ensure_text(value):
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    return str(value)


class InputDeviceAdapterFlasher(MessageBox):
    FLASHER_BINARY = eEnv.resolve("${sbindir}/flash-nrf52")
    NRF_AS_FRONTPROCESSOR_DEVICES = ["one", "two"]

    def __init__(self, session):
        self._isFrontProcessor = HardwareInfo().get_device_name() in self.NRF_AS_FRONTPROCESSOR_DEVICES
        if self._isFrontProcessor:
            title = _("Flashing Frontprocessor Firmware")
            windowTitle = _("Frontprocessor Firmware")
        else:
            title = _("Flashing Adapter Firmware")
            windowTitle = _("Bluetooth Frontprocessor Firmware")

        fakeText = "\n.                                                         .\n.\n.\n."  # Reserve space for future text in the message box.
        MessageBox.__init__(self, session, fakeText, title=title, type=MessageBox.TYPE_WARNING, windowTitle=windowTitle)
        self.skinName = "MessageBox"
        self._console = eConsoleAppContainer()
        self._console.dataAvail.append(self._onData)
        self._console.appClosed.append(self._onAppClosed)
        self._dm = eInputDeviceManager.getInstance()
        self._success = False
        self._flasherMissing = False

        self.onFirstExecBegin.append(self._check)
        self.onShow.append(self.__onShow)
        self.onClose.append(self.__onClose)

        self.blockFlashed = 0
        self.blocksVerified = 0

        self._flashFirmware()

    def __onShow(self):
        t = _("Please wait! We are about to start...")
        self["Text"].setText(t)
        self["text"].setText(t)

    def _check(self):
        if self._flasherMissing:
            self.session.openWithCallback(self.close, MessageBox, _("Firmware flasher is missing or broken! Cancelled!"), type=MessageBox.TYPE_ERROR)
            self.close(False)

    def __onClose(self):
        if self._onData in self._console.dataAvail:
            self._console.dataAvail.remove(self._onData)
        if self._onAppClosed in self._console.appClosed:
            self._console.appClosed.remove(self._onAppClosed)
        self._dm.start()

    def _onData(self, data):
        data = ensure_text(data)
        Log.i(data)
        pre = _("Working...")
        isVerifying = False
        isFlashing = False

        if data.strip().startswith("flashing"):
            pre = _("Flashing firmware...")
            isFlashing = True
        elif data.strip().startswith("verifying"):
            pre = _("Verifying firmware...")
            isVerifying = True

        if self._isFrontProcessor:
            pre += _("\n\nDO NOT TURN OFF YOUR DREAMBOX!")
        if pre:
            if isFlashing or isVerifying:
                splitted = data.split(" ")
                address = splitted[3]
                if isFlashing:
                    self.blockFlashed += 1
                    text = _("%s\n\n%03d blocks written (%s)") % (pre, self.blockFlashed, address)
                elif isVerifying:
                    self.blocksVerified += 1
                    text = _("%s\n\n%03d blocks written\n%03d blocks verified (%s)") % (pre, self.blockFlashed, self.blocksVerified, address)
            else:
                text = "%s\n\n%s" % (pre, data)
        else:
            text = pre
        self["Text"].setText(text)
        self["text"].setText(text)
        if data.find("success:") >= 0:
            self._success = True

    def _onAppClosed(self, data):
        self.close(self._success)

    def _flashFirmware(self):
        if not fileExists(self.FLASHER_BINARY):
            self._flasherMissing = True
            return
        self._dm.stop()
        res = self._console.execute("%s --program --force --verify --start" % (self.FLASHER_BINARY))
        Log.w("%s" % (res,))


class InputDeviceUpdateChecker:
    def __init__(self):
        self._console = eConsoleAppContainer()
        self._console.dataAvail.append(self._onData)
        self._console.appClosed.append(self._onAppClosed)
        self._flasherMissing = not fileExists(InputDeviceAdapterFlasher.FLASHER_BINARY)
        self.onUpdateAvailable = []

    def check(self):
        if self._flasherMissing:
            return
        res = self._console.execute("%s --check" % (InputDeviceAdapterFlasher.FLASHER_BINARY))
        Log.d("%s" % (res,))

    def _onData(self, data):
        data = ensure_text(data)
        Log.d(data)

    def _onAppClosed(self, returncode):
        Log.w("%s" % (returncode,))
        if returncode == 1:  # 0 == no update, 1 == update, everything else is an error.
            for callback in self.onUpdateAvailable:
                callback()
