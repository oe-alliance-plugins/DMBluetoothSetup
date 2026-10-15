from json import load
from os.path import basename, getsize, isfile, join

from enigma import eEnv, eInputDeviceDfuFlasher as Dfu, eInputDeviceManager, eTimer

from Tools.Log import Log


class DfuFileset:
	TYPE_SYSTEM = 1
	TYPE_APP = 1 << 1
	SECTION_INIT = 1 << 4
	SECTION_DATA = 1 << 5

	def __init__(self, fileType, datFile, binFile):
		self.type = fileType
		self.dat = datFile
		self.bin = binFile


class DfuFlash:
	EVT_DFU_LOWBAT = 1 << 9
	EVT_DFU_NA = 1 << 10
	EVT_DFU_TIMEOUT = 1 << 11
	EVT_DFU_AVAILABLE = 1 << 12
	EVT_DFU_CONNECTED = 1 << 13
	EVT_FLASH_BEGIN = 1 << 14
	EVT_FLASH_REJECTED = 1 << 15
	EVT_INIT_FAIL = 1 << 16
	EVT_UPLOAD_BEGIN = 1 << 17
	EVT_UPLOAD_PROGRESS = 1 << 18
	EVT_UPLOAD_RESULT = 1 << 19
	EVT_BL_SKIPPED = 1 << 20
	EVT_REBOOT_AWAIT = 1 << 21
	EVT_FINISHED = 1 << 31
	EVT_DFU_CONTROL_ERROR = 1 << 32
	EVT_RECONNECT_TIMEOUT = 1 << 33
	UPLOAD_RESULT_ERROR = 0
	UPLOAD_RESULT_SUCCESS = 1
	FILENAME_MANIFEST = "manifest.json"
	FIRMWARE_DIRECTORY = eEnv.resolve("${datadir}/nrf52-firmware-rcu")
	VERSION_MAP = {5: (1, 0), 6: (1, 3), 7: (1, 4), 8: (1, 5), 9: (1, 6), 10: (1, 7)}

	def __init__(self, eventCallback, progressCallback):
		self.manager = eInputDeviceManager.getInstance()
		self.onEvent = eventCallback
		self.onProgress = progressCallback
		self.phaseTimer = eTimer()
		self.phaseTimer.callback.append(self.phaseTimeout)
		self.pollTimer = eTimer()
		self.pollTimer.callback.append(self.pollDevices)
		self.sets = []
		self.currentSet = None
		self.section = None
		self.applicationVersion = None
		self.address = None
		self.dfuAddress = None
		self.connectingAddress = None
		self.phase = "idle"
		self.watching = False
		self.closed = False

	@property
	def currentSetType(self):
		return self.currentSet.type if self.currentSet else None

	def event(self, event, value=None):
		self.onEvent(event, value)

	def load(self, targetdir):
		self.sets = []
		self.applicationVersion = None
		try:
			with open(join(targetdir, self.FILENAME_MANIFEST), encoding="utf-8") as manifestFile:
				manifest = load(manifestFile)["manifest"]
			fileSets = []
			for name, fileType in (("softdevice_bootloader", DfuFileset.TYPE_SYSTEM), ("application", DfuFileset.TYPE_APP)):
				if name not in manifest:
					continue
				entry = manifest[name]
				paths = []
				for key, limit in (("dat_file", 4096), ("bin_file", 1024 * 1024)):
					fileName = entry[key]
					if not isinstance(fileName, str) or basename(fileName) != fileName:
						raise ValueError("Firmware manifest must use local file names")
					path = join(targetdir, fileName)
					if not isfile(path) or not 0 < getsize(path) <= limit:
						raise ValueError(f"Invalid firmware file: {fileName}")
					paths.append(path)
				fileSets.append(DfuFileset(fileType, *paths))
			if not fileSets or fileSets[-1].type != DfuFileset.TYPE_APP:
				raise ValueError("Firmware package has no application")
			with open(fileSets[-1].dat, "rb") as initFile:
				initData = initFile.read(11)
			if len(initData) != 11:
				raise ValueError("Application init packet is too short")
			self.applicationVersion = self.VERSION_MAP.get(initData[10])
			self.sets = fileSets
		except (OSError, ValueError, KeyError, TypeError) as error:
			Log.w(f"Unable to load RCU firmware: {error}")
			return 0
		return sum(x.type for x in self.sets)

	def update(self, device):
		if self.closed or self.phase != "idle" or not self.sets or not device:
			return False
		try:
			address = device.address().lower()
			parts = address.split(":")
			if len(parts) != 6 or any(len(x) != 2 or not 0 <= int(x, 16) <= 255 for x in parts):
				raise ValueError("Invalid remote address")
			delta = -1 if device.isDfu() else 1
			lastByte = int(parts[-1], 16) + delta
			if not 0 <= lastByte <= 255:
				raise ValueError("DFU address wraparound is not verified")
			parts[-1] = f"{lastByte:02x}"
			otherAddress = ":".join(parts)
			self.address, self.dfuAddress = (otherAddress, address) if device.isDfu() else (address, otherAddress)
		except (AttributeError, ValueError) as error:
			Log.w(str(error))
			self.event(self.EVT_DFU_NA)
			return False
		if self.manager.dfuActive():
			self.event(self.EVT_DFU_NA)
			return False
		for signal, callback in self.callbacks():
			signal.append(callback)
		self.watching = True
		if device.isDfu():
			self.waitForDevice("dfu", 30)
			self.devicesChanged()
			return True
		return self.enterDfu(device)

	def callbacks(self):
		return (
			(self.manager.deviceListChanged, self.devicesChanged),
			(self.manager.deviceStateChanged, self.devicesChanged),
			(self.manager.dfuEvent, self.dfuEvent),
			(self.manager.dfuProgress, self.dfuProgress),
		)

	def stopWatching(self):
		self.phaseTimer.stop()
		self.pollTimer.stop()
		if self.watching:
			for signal, callback in self.callbacks():
				if callback in signal:
					signal.remove(callback)
			self.watching = False
		self.phase = "idle"

	def close(self):
		if self.closed:
			return
		if self.phase == "flashing":
			self.manager.dfuCancel()
		self.stopWatching()
		self.phaseTimer.callback.remove(self.phaseTimeout)
		self.pollTimer.callback.remove(self.pollDevices)
		self.closed = True

	def finish(self, event, value=None):
		if self.phase == "flashing":
			self.manager.dfuCancel()
		self.stopWatching()
		self.event(event, value)

	def waitForDevice(self, phase, timeout):
		Log.i(f"DFU phase {phase}, waiting up to {timeout} seconds")
		self.phase = phase
		self.connectingAddress = None
		self.phaseTimer.startLongTimer(timeout)
		self.pollTimer.start(2000, False)

	def enterDfu(self, device):
		Log.i(f"Entering DFU for {device.address()}, firmware {device.version()}, battery {device.batteryLevel()}%")
		self.waitForDevice("dfu", 30)
		result = device.dfu()
		if result != Dfu.DFU_SUCCESS:
			self.finish(self.EVT_DFU_LOWBAT if result == Dfu.DFU_LOWBAT else self.EVT_DFU_NA)
			return False
		return True

	def pollDevices(self):
		if self.phase in ("dfu", "reboot", "return"):
			# A connect command may be accepted while the remote is still
			# rebooting. Retry on the next poll until its state confirms it.
			self.connectingAddress = None
			self.manager.refresh()
			self.manager.rescan()
			self.devicesChanged()

	def phaseTimeout(self):
		if self.phase == "reenter":
			device = self.findDevice(self.address)
			if device and device.connected():
				self.enterDfu(device)
			else:
				self.finish(self.EVT_DFU_TIMEOUT)
		else:
			self.finish(self.EVT_RECONNECT_TIMEOUT if self.phase == "return" else self.EVT_DFU_TIMEOUT)

	def findDevice(self, address):
		return next((x for x in self.manager.getAvailableDevices() if x.address().lower() == address), None)

	def devicesChanged(self, *args):
		if self.phase not in ("dfu", "reboot", "return"):
			return
		device = self.findDevice(self.dfuAddress if self.phase == "dfu" else self.address)
		if not device or (self.phase == "dfu" and not device.isDfu()):
			return
		if not device.connected():
			if self.connectingAddress != device.address():
				self.connectingAddress = device.address()
				if self.phase == "dfu":
					self.event(self.EVT_DFU_AVAILABLE)
				if device.connect() != 0:
					self.finish(self.EVT_DFU_NA)
			return
		if self.phase == "dfu":
			self.phaseTimer.stop()
			self.pollTimer.stop()
			self.phase = "flashing"
			self.event(self.EVT_DFU_CONNECTED)
			self.flashNextSet(device)
		elif self.phase == "reboot":
			# Link-up precedes service discovery. Start the settling delay only
			# after fresh version and battery replies confirm the RCU is ready.
			if device.version() == "0.0" or device.batteryLevel() <= 0:
				return
			Log.i(f"RCU {device.address()} reports firmware {device.version()} after reboot; waiting 4 seconds before DFU")
			self.pollTimer.stop()
			self.phase = "reenter"
			self.phaseTimer.startLongTimer(4)
		elif self.applicationVersion is None or device.checkVersion(*self.applicationVersion) == 0:
			self.finish(self.EVT_FINISHED)

	def flashNextSet(self, device):
		if not self.sets or not device:
			self.finish(self.EVT_FLASH_REJECTED)
			return
		self.section = None
		self.currentSet = self.sets.pop(0)
		self.phase = "flashing"
		self.event(self.EVT_FLASH_BEGIN, self.currentSet.type)
		if device.dfuFlash(self.currentSet.dat, self.currentSet.bin) != Dfu.DFU_SUCCESS and self.phase == "flashing":
			self.finish(self.EVT_FLASH_REJECTED)

	def dfuEvent(self, event, value):
		if self.phase != "flashing":
			return
		Log.d(f"DFU event {event}, value {value}")
		if event == Dfu.DFU_EVT_OBJECT_CREATE_SUCCESS:
			self.section = value
			self.event(self.EVT_UPLOAD_BEGIN, value)
		elif event == Dfu.DFU_EVT_EXECUTE_ERROR:
			# DreamOS 1.7 reports extended firmware-version failure for its
			# already installed bootloader. Other failures must not be skipped.
			if self.currentSetType == DfuFileset.TYPE_SYSTEM and self.section == Dfu.DFU_FIRMWARE_TYPE_DAT and value == 0x0B05:
				self.event(self.EVT_BL_SKIPPED)
				self.flashNextSet(self.findDevice(self.dfuAddress))
			else:
				self.finish(self.EVT_UPLOAD_RESULT, False)
		elif event == Dfu.DFU_EVT_EXECUTE_SUCCESS:
			self.event(self.EVT_UPLOAD_RESULT, True)
			if value == Dfu.DFU_FIRMWARE_TYPE_BIN:
				self.waitForDevice("reboot" if self.sets else "return", 60)
				self.event(self.EVT_REBOOT_AWAIT)
		elif event in (Dfu.DFU_EVT_FILE_INVALID, Dfu.DFU_EVT_FILE_READ_ERROR):
			self.finish(self.EVT_FLASH_REJECTED)
		elif event in (Dfu.DFU_EVT_CHECKSUM_INVALID, Dfu.DFU_EVT_UPLOAD_ERROR):
			self.finish(self.EVT_UPLOAD_RESULT, False)
		elif event == Dfu.DFU_EVT_WRITE_CONTROL_ERROR:
			self.finish(self.EVT_DFU_CONTROL_ERROR, value)
		elif event in (Dfu.DFU_EVT_ENABLE_NOTIFY_ERROR, Dfu.DFU_EVT_OBJECT_CREATE_ERROR, Dfu.DFU_EVT_OBJECT_READ_ERROR, Dfu.DFU_EVT_COMMAND_ERROR):
			self.finish(self.EVT_INIT_FAIL, value)

	def dfuProgress(self, currentBytes, totalBytes):
		if self.phase == "flashing":
			self.onProgress(currentBytes, totalBytes)
