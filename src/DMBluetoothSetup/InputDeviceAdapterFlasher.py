from enigma import eConsoleAppContainer, eEnv, eInputDeviceManager

from Screens.MessageBox import MessageBox
from Tools.Directories import fileExists
from Tools.HardwareInfo import HardwareInfo
from Tools.Log import Log

from . import _


class InputDeviceAdapterFlasher(MessageBox):
	FLASHER_BINARY = eEnv.resolve("${sbindir}/flash-nrf52")
	NRF_AS_FRONTPROCESSOR_DEVICES = ("one", "two", "dreamone", "dreamtwo")

	def __init__(self, session):
		self.frontProcessor = HardwareInfo().get_device_name() in self.NRF_AS_FRONTPROCESSOR_DEVICES
		if self.frontProcessor:
			title = _("Flashing Frontprocessor Firmware")
			windowTitle = _("Frontprocessor Firmware")
		else:
			title = _("Flashing Adapter Firmware")
			windowTitle = _("Bluetooth Receiver Firmware")

		fakeText = "\n.                                                         .\n.\n.\n."  # Reserve space for future text in the message box.
		MessageBox.__init__(self, session, fakeText, title=title, type=MessageBox.TYPE_WARNING, windowTitle=windowTitle, enableInput=False)
		self.skinName = "MessageBox"
		self.console = eConsoleAppContainer()
		self.console.dataAvail.append(self.onData)
		self.console.appClosed.append(self.onAppClosed)
		self.deviceManager = eInputDeviceManager.getInstance()
		self.success = False
		self.flasherMissing = False
		self.outputBuffer = ""
		self.managerStopped = False

		self.onShown.append(self.flashFirmware)
		self.onShow.append(self.showStart)
		self.onClose.append(self.finishFlash)

		self.blockFlashed = 0
		self.blocksVerified = 0

	def showStart(self):
		self["text"].setText(_("Please wait! We are about to start..."))

	def checkFlasher(self):
		if self.flasherMissing:
			self.session.openWithCallback(self.onMissingFlasherClosed, MessageBox, _("Firmware flasher is missing or broken! Cancelled!"), type=MessageBox.TYPE_ERROR)

	def onMissingFlasherClosed(self, answer):
		self.close(False)

	def finishFlash(self):
		if self.onData in self.console.dataAvail:
			self.console.dataAvail.remove(self.onData)
		if self.onAppClosed in self.console.appClosed:
			self.console.appClosed.remove(self.onAppClosed)
		if self.managerStopped:
			self.deviceManager.start()

	def onData(self, data):
		data = data.decode("utf-8", "replace") if isinstance(data, bytes) else str(data)
		self.outputBuffer += data.replace("\r", "\n")
		while "\n" in self.outputBuffer:
			line, self.outputBuffer = self.outputBuffer.split("\n", 1)
			self.showProgress(line)

	def showProgress(self, data):
		if not data.strip():
			return
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

		if self.frontProcessor:
			pre += _("\n\nDO NOT TURN OFF YOUR DREAMBOX!")
		if pre:
			if isFlashing or isVerifying:
				fields = data.split()
				address = fields[3] if len(fields) > 3 else ""
				if isFlashing:
					self.blockFlashed += 1
					text = _("%s\n\n%03d blocks written (%s)") % (pre, self.blockFlashed, address)
				elif isVerifying:
					self.blocksVerified += 1
					text = _("%s\n\n%03d blocks written\n%03d blocks verified (%s)") % (pre, self.blockFlashed, self.blocksVerified, address)
			else:
				text = f"{pre}\n\n{data}"
		else:
			text = pre
		self["text"].setText(text)
		if data.startswith("success:") and "bytes verified" in data:
			self.success = True

	def onAppClosed(self, returnCode):
		self.showProgress(self.outputBuffer)
		self.outputBuffer = ""
		self.close(returnCode == 0 and self.success)

	def flashFirmware(self):
		self.onShown.remove(self.flashFirmware)
		if not fileExists(self.FLASHER_BINARY):
			self.flasherMissing = True
			self.checkFlasher()
			return
		self.deviceManager.stop()
		self.managerStopped = True
		result = self.console.execute(self.FLASHER_BINARY, self.FLASHER_BINARY, "--program", "--force", "--verify", "--start")
		Log.w(f"Flasher start result: {result}")
		if result:
			self.close(False)


class InputDeviceUpdateChecker:
	def __init__(self):
		self.console = eConsoleAppContainer()
		self.console.dataAvail.append(self.onData)
		self.console.appClosed.append(self.onAppClosed)
		self.flasherMissing = not fileExists(InputDeviceAdapterFlasher.FLASHER_BINARY)
		self.onUpdateAvailable = []

	def check(self):
		if self.flasherMissing:
			return
		result = self.console.execute(InputDeviceAdapterFlasher.FLASHER_BINARY, InputDeviceAdapterFlasher.FLASHER_BINARY, "--check")
		Log.d(f"Firmware check start result: {result}")

	def onData(self, data):
		data = data.decode("utf-8", "replace") if isinstance(data, bytes) else str(data)
		Log.d(data)

	def onAppClosed(self, returnCode):
		Log.w(f"Firmware check result: {returnCode}")
		if returnCode == 1:  # 0 == no update, 1 == update, everything else is an error.
			for callback in self.onUpdateAvailable:
				callback()
