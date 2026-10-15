from time import time
from twisted.internet import reactor

from enigma import eInputDeviceManager

from Components.config import config
from Plugins.Plugin import PluginDescriptor
from Screens.MessageBox import MessageBox
from Tools.BoundFunction import boundFunction
from Tools.Directories import createDir, fileExists
from Tools.Log import Log
from Tools.Notifications import AddModalNotification, AddPopup, showError, showInfo

from . import _, ensureInputDeviceManagerConfig, filterInputDevices, getInputDeviceAddress, getInputDeviceConnected, isValidInputDeviceAddress, markInputDeviceConnected
from .InputDeviceAdapterFlasher import InputDeviceUpdateChecker
from .InputDeviceManagement import InputDeviceManagement
from .InputDeviceUpdateHandlerBase import InputDeviceUpdateHandlerBase

ensureInputDeviceManagerConfig()

global inputDeviceWatcher
inputDeviceWatcher = None


class InputDeviceWatcher(InputDeviceUpdateHandlerBase):
	BATTERY_LOG_DIR = "/var/lib/enigma2"
	BATTERY_LOW_LEVEL = 20  # Normal use; firmware updates require at least 50 percent.

	def __init__(self, session):
		ensureInputDeviceManagerConfig()
		InputDeviceUpdateHandlerBase.__init__(self)
		self.session = session
		self._updateChecker = InputDeviceUpdateChecker()
		self._updateChecker.onUpdateAvailable.append(self._onUpdateAvailable)
		self._updateChecker.check()
		self._dm = eInputDeviceManager.getInstance()
		self._dm.deviceStateChanged.append(self._onDeviceStateChanged)
		self._dm.batteryLow.append(self._onBatteryLow)
		self.__deviceListChangedRegistered = False
		self._batteryStates = {}
		self._batteryLowWarned = set()
		self.pendingConnections = set()
		logdir = "/tmp"
		if fileExists(self.BATTERY_LOG_DIR) or createDir(self.BATTERY_LOG_DIR):
			logdir = self.BATTERY_LOG_DIR
		self._batteryLogFile = "%s/battery.dat" % (logdir,)
		# Wait 10 seconds before looking for connected devices
		reactor.callLater(10, self._start)

	def _start(self):
		if not self.__deviceListChangedRegistered:
			self._dm.deviceListChanged.append(self._onDeviceListChanged)
			self.__deviceListChangedRegistered = True
		self._onDeviceListChanged()

	def _onDeviceStateChanged(self, address, state):
		if not isValidInputDeviceAddress(address):
			return
		old = self._batteryStates.get(address, 0)
		device = self._dm.getDevice(address)
		if device and address in self.pendingConnections and getInputDeviceConnected(device):
			self.pendingConnections.discard(address)
			showInfo(_("Bluetooth remote connected: %s") % (device.shortName() or _("DM Remote")))
		if device.ready():
			new = device.batteryLevel()
			if old != device.batteryLevel():
				if config.inputDevices.settings.logBattery.value:
					Log.i("%s\t%s%% Battery" % (address, device.batteryLevel()))
					try:
						with open(self._batteryLogFile, "a", encoding="utf-8") as f:
							f.write(f"{address} {int(time())} {new}\n")
					except Exception as e:
						Log.w(e)
				self._batteryStates[address] = device.batteryLevel()
			if new >= self.BATTERY_LOW_LEVEL:
				self._batteryLowWarned.discard(address)

	def _onBatteryLow(self, address):
		# Sent with every battery report below the threshold, warn once per remote.
		if not isValidInputDeviceAddress(address) or address in self._batteryLowWarned:
			return
		self._batteryLowWarned.add(address)
		device = self._dm.getDevice(address)
		level = device.batteryLevel() if device else 0
		AddPopup(_("The battery of the Bluetooth remote control is low (%d%%). Please replace the batteries.") % (level,), MessageBox.TYPE_WARNING, 10, "dmbluetooth_battery_low")

	def _onDeviceListChanged(self):
		if config.misc.firstrun.value:  # Wizard will run!
			return
		if not config.inputDevices.settings.firstDevice.value:
			return
		devices = filterInputDevices(self._dm.getAvailableDevices())
		if devices:
			config.inputDevices.settings.firstDevice.value = False
			config.inputDevices.settings.save()

			for device in devices:
				Log.i("%s:: %s" % (getInputDeviceAddress(device), device.ready()))
				if device.ready():
					return
			if isinstance(self.session.current_dialog, InputDeviceManagement) or any(isinstance(x[0], InputDeviceManagement) for x in self.session.dialog_stack):
				return  # The open setup screen reports discovery and connection with toasts.
			AddModalNotification(
				_("A new Bluetooth remote has been discovered. Connect now?"),
				typeIcon=MessageBox.TYPE_YESNO,
				windowTitle=_("New Bluetooth Remote"),
				callback=boundFunction(self._onDiscoveryAnswer, address=getInputDeviceAddress(devices[0]) if len(devices) == 1 else None),
			)

	def _onDiscoveryAnswer(self, answer, address=None):
		if answer:
			if address:
				device = self._dm.getDevice(address)
				if device:
					if getInputDeviceConnected(device):
						showInfo(_("Bluetooth remote connected: %s") % (device.shortName() or _("DM Remote")))
						return
					self.pendingConnections.add(address)
					markInputDeviceConnected(address)
					if not self._dm.connectDevice(device):
						return
				self.pendingConnections.discard(address)
				showError(_("Could not connect the Bluetooth remote."))
			else:
				self.session.open(InputDeviceManagement)

	def _onUpdateAvailable(self):
		text = self._fpUpdateText()
		AddModalNotification(
			text,
			typeIcon=MessageBox.TYPE_YESNO,
			windowTitle=_("New Firmware"),
			callback=self._onUpdateAnswer,
		)


def idm_setup(session, **kwargs):
	session.open(InputDeviceManagement)


def idm_menu(menuid, **kwargs):
	if menuid == "system":
		return [(_("Bluetooth Setup"), idm_setup, "dmbluetooth_setup", 10)]
	return []


def sessionStart(reason, session, *args, **kwargs):
	global inputDeviceWatcher
	inputDeviceWatcher = InputDeviceWatcher(session)


def Plugins(**kwargs):
	return [
		PluginDescriptor(
			name=_("Bluetooth Setup Autosetup"),
			where=PluginDescriptor.WHERE_SESSIONSTART,
			fnc=sessionStart,
		),
		PluginDescriptor(
			name=_("Bluetooth Setup"),
			description=_("Set up Bluetooth remote controls"),
			where=PluginDescriptor.WHERE_MENU,
			needsRestart=True,
			fnc=idm_menu,
		)
	]
