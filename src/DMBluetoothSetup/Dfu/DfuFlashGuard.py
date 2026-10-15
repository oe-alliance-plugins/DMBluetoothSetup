from enigma import DFU_BATTERY_MIN, eInputDeviceDfuFlasher as Dfu, eInputDeviceManager

from Components.ActionMap import ActionMap
from Components.Label import Label
from Components.Sources.Progress import Progress
from Screens.MessageBox import MessageBox
from Screens.Screen import Screen

from .DfuFlash import DfuFileset, DfuFlash
from .. import _


class DfuLog(Screen):
	IS_DIALOG = True
	skin = """<screen name="DfuLog" position="center,center" size="820,520">
		<widget name="log" position="10,10" size="800,500" font="Regular;22" />
	</screen>"""

	def __init__(self, session, text):
		Screen.__init__(self, session)
		self.setTitle(_("DFU Log"))
		self["log"] = Label(text)
		self["actions"] = ActionMap(["OkCancelActions"], {"ok": self.close, "cancel": self.close})

	def getText(self):
		return self["log"].text

	def setText(self, text):
		self["log"].text = text

	text = property(getText, setText)


class DfuFlashGuard(Screen):
	IS_DIALOG = True
	ALLOW_SUSPEND = False
	# Existing screen and widget names remain available to external skins.
	skin = """<screen name="DfuFlashGuard" position="center,center" size="820,420" title="DFU Firmware Upgrade">
		<widget name="log" position="10,5" size="800,30" halign="right" font="Regular;18" />
		<widget name="text" position="10,40" size="800,280" font="Regular;24" halign="center" valign="center" />
		<widget name="bytes" position="10,330" size="800,30" font="Regular;22" />
		<widget source="progress" render="Progress" position="10,375" size="800,30" borderWidth="1" />
	</screen>"""

	def __init__(self, session, device):
		Screen.__init__(self, session)
		self.setTitle(_("DFU Firmware Upgrade"))
		self.device = device
		self.flasher = DfuFlash(self.onEvent, self.onUploadProgress)
		self.running = False
		self.success = False
		self.logText = ""
		self.logScreen = None
		self["text"] = Label()
		self["bytes"] = Label()
		self["progress"] = Progress(valuerange=1000)
		self["log"] = Label(_("INFO: Show Full Log"))
		self["actions"] = ActionMap(["OkCancelActions"], {"ok": self.closeGuard, "cancel": self.closeGuard})
		self["logAction"] = ActionMap(["TimerEditActions"], {"log": self.showLog})
		self.onFirstExecBegin.append(self.load)
		self.onClose.append(self.flasher.close)

	def closeGuard(self):
		if not self.running:
			self.close(self.success)

	def appendText(self, text):
		self["text"].text = text
		self.logText = f"{self.logText}\n{text}".strip()
		if self.logScreen:
			self.logScreen.text = self.logText

	def showLog(self):
		self.logScreen = self.session.openWithCallback(self.logClosed, DfuLog, self.logText)

	def logClosed(self, *args):
		self.logScreen = None

	def load(self):
		manager = eInputDeviceManager.getInstance()
		if not manager.hasFeature(eInputDeviceManager.FEATURE_DFU_UPDATE) or manager.dfuActive():
			self.appendText(_("DFU is not available on this receiver or an update is already running."))
			return
		types = self.flasher.load(self.flasher.FIRMWARE_DIRECTORY)
		if not types:
			self.appendText(_("The remote control firmware package is missing or invalid."))
			return
		if not self.device.isDfu():
			if not self.device.connected():
				self.appendText(_("Connect the remote control before starting the update."))
				return
			if self.device.batteryLevel() < DFU_BATTERY_MIN:
				self.appendText(_("The battery level must be at least %d%% before updating.") % DFU_BATTERY_MIN)
				return
		version = self.flasher.applicationVersion
		versionText = ".".join(str(x) for x in version) if version else _("unknown")
		text = _("Install remote control firmware %s on %s?\n\nKeep the remote close to the receiver and leave its batteries inserted until the update has finished.") % (versionText, self.device.address())
		if not self.device.isDfu() and version and self.device.checkVersion(*version) >= 0:
			text = _("The remote already has this or a newer firmware version. Force installation?\n\n") + text
		if not self.device.isDfu() and self.device.checkVersion(1, 5) < 0 and types & DfuFileset.TYPE_SYSTEM:
			text += _("\n\nThe remote may not respond during the system update. Control returns after it restarts.")
		self.appendText(_("Waiting for confirmation..."))
		self.session.openWithCallback(self.confirmUpdate, MessageBox, text, type=MessageBox.TYPE_YESNO, default=False, windowTitle=_("Update remote control firmware?"))

	def confirmUpdate(self, answer):
		if not answer:
			self.close(False)
			return
		self.running = True
		self.appendText(_("Initializing DFU Mode..."))
		if not self.flasher.update(self.device):
			self.running = False

	def onEvent(self, event, value):
		errors = {
			DfuFlash.EVT_DFU_NA: _("DFU is not available or the connection could not be started."),
			DfuFlash.EVT_DFU_TIMEOUT: _("The remote did not connect in DFU mode. The update has stopped."),
			DfuFlash.EVT_DFU_LOWBAT: _("The battery level must be at least %d%% before updating.") % DFU_BATTERY_MIN,
			DfuFlash.EVT_FLASH_REJECTED: _("The firmware files could not be loaded or were rejected."),
			DfuFlash.EVT_INIT_FAIL: _("The remote rejected update initialization. The update has stopped."),
			DfuFlash.EVT_DFU_CONTROL_ERROR: _("No valid response was received from the remote. The update has stopped."),
			DfuFlash.EVT_RECONNECT_TIMEOUT: _("The firmware was sent, but reconnection and the new version could not be confirmed. Check the remote in Bluetooth Setup."),
		}
		if event in errors or (event == DfuFlash.EVT_UPLOAD_RESULT and not value):
			self.running = False
			self.appendText(errors.get(event, _("Firmware transfer or verification failed. The update has stopped.")))
		elif event == DfuFlash.EVT_FLASH_BEGIN:
			self["progress"].value = 0
			self.appendText(_("Starting system update...") if value == DfuFileset.TYPE_SYSTEM else _("Starting application update..."))
		elif event == DfuFlash.EVT_UPLOAD_BEGIN:
			sectionText = _("firmware data") if value == Dfu.DFU_FIRMWARE_TYPE_BIN else _("firmware information")
			self.appendText(_("Transferring %s...") % sectionText)
		elif event == DfuFlash.EVT_BL_SKIPPED:
			self.appendText(_("The installed system version does not need this update. Continuing with the application."))
		elif event == DfuFlash.EVT_REBOOT_AWAIT:
			self.appendText(_("Waiting for the remote to restart and reconnect..."))
		elif event == DfuFlash.EVT_FINISHED:
			self.success = True
			self.running = False
			self["progress"].value = 1000
			self.appendText(_("Firmware update completed. The remote has reconnected.\n\nPress OK or EXIT to close."))

	def onUploadProgress(self, currentBytes, totalBytes):
		self["progress"].value = min(1000, currentBytes * 1000 // totalBytes) if totalBytes else 0
		self["bytes"].text = _("Uploaded %d of %d bytes") % (currentBytes, totalBytes)
