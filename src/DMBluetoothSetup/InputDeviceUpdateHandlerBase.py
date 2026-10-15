from enigma import quitMainloop

from Screens.MessageBox import MessageBox
from Tools.HardwareInfo import HardwareInfo
from Tools.StbHardware import getFPVersion

from . import _
from .InputDeviceAdapterFlasher import InputDeviceAdapterFlasher


class InputDeviceUpdateHandlerBase:
	def __init__(self):
		self.numTries = 0
		self.frontProcessor = HardwareInfo().get_device_name() in ("one", "two", "dreamone", "dreamtwo")

	def _fpUpdateText(self):
		self.numTries = 0
		if not self.frontProcessor:
			return _("There is a new firmware for your Bluetooth receiver available. Update now?")
		updateText = _("There is a new firmware for your frontprocessor available. Update now?")
		# "major.minor" as numbers, 1.9 is older than 1.12
		try:
			version = tuple(int(x) for x in str(getFPVersion()).strip().split("."))
		except (TypeError, ValueError):
			version = None
		if version is not None and version <= (1, 12):
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
			self.numTries += 1
			self.session.openWithCallback(self._onUpdateFinished, InputDeviceAdapterFlasher)

	def _onUpdateFinished(self, result):
		if result:
			self.numTries = 0
			if not self.frontProcessor:
				self.session.open(MessageBox, _("Bluetooth receiver firmware was updated successfully!"), type=MessageBox.TYPE_INFO)
				return
			self.session.openWithCallback(
				self._onRebootAnswer,
				MessageBox,
				_("The Frontprocessor was updated successfully!\nYour Dreambox must be rebooted for the changes to take effect.\nReboot now?"),
				type=MessageBox.TYPE_YESNO,
				title=_("Reboot required"),
				windowTitle=_("Reboot required"),
			)
		elif self.numTries < 3:
			self.session.openWithCallback(
				self._onUpdateAnswer,
				MessageBox,
				_("Frontprocessor update failed!\nRetry?") if self.frontProcessor else _("Bluetooth receiver update failed!\nRetry?"),
				type=MessageBox.TYPE_YESNO,
				title=_("Retry?"),
				windowTitle=_("ERROR! Retry Firmware Update?"),
			)
		else:
			self.session.open(
				MessageBox,
				(_("Frontprocessor update failed multiple times!") if self.frontProcessor else _("Bluetooth receiver update failed multiple times!")) + _("\nPlease contact the support!\nYou can try executing\n'flash-nrf52 --program --verify --start'\non a console manually"),
				type=MessageBox.TYPE_ERROR,
				title=_("ERROR!"),
				windowTitle=_("ERROR! Frontprocessor Update") if self.frontProcessor else _("Bluetooth Receiver Firmware"),
			)

	def _onRebootAnswer(self, answer):
		if answer:
			quitMainloop(3)
