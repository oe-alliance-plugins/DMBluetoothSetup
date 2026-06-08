from Plugins.SystemPlugins.BluetoothSetup.InputDeviceAdapterFlasher import InputDeviceAdapterFlasher
from Screens.MessageBox import MessageBox
from Tools.DreamboxHardware import getFPVersion
from enigma import quitMainloop


class InputDeviceUpdateHandlerBase:
    def __init__(self):
        self._numTries = 0

    def _fpUpdateText(self):
        self._numTries = 0
        updateText = _("There is a new firmware for your frontprocessor available. Update now?")
        if getFPVersion() <= 1.12:
            updateText += _(
                "\n\n!!! ATTENTION !!!\n"
                "Due to major firmware changes you can not downgrade to images "
                "dated before this one anymore!\n"
                "This update is mandatory and should not be skipped!\n"
                "!!! ATTENTION !!!!"
            )
        return updateText

    def _onUpdateAnswer(self, answer):
        if answer:
            self._numTries += 1
            self.session.openWithCallback(self._onUpdateFinished, InputDeviceAdapterFlasher)

    def _onUpdateFinished(self, result):
        if result:
            self._numTries = 0
            self.session.openWithCallback(
                self._onRebootAnswer,
                MessageBox,
                _("The Frontprocessor was updated successfully!\nYour Dreambox must be rebooted for the changes to take effect.\nReboot now?"),
                type=MessageBox.TYPE_YESNO,
                title=_("Reboot required"),
                windowTitle=_("Reboot required"),
            )
        elif self._numTries < 3:
            self.session.openWithCallback(
                self._onUpdateAnswer,
                MessageBox,
                _("Frontprocessor update failed!\nRetry?"),
                type=MessageBox.TYPE_YESNO,
                title=_("Retry?"),
                windowTitle=_("ERROR! Retry Firmware Update?"),
            )
        else:
            self.session.open(
                MessageBox,
                _(
                    "Frontprocessor update failed multiple times!\n"
                    "Please contact the support!\n"
                    "You can try executing\n"
                    "'flash-nrf52 --program --verify --start'\n"
                    "on a console manually"
                ),
                type=MessageBox.TYPE_ERROR,
                title=_("ERROR!"),
                windowTitle=_("ERROR! Frontprocessor Update"),
            )

    def _onRebootAnswer(self, answer):
        if answer:
            quitMainloop(3)
