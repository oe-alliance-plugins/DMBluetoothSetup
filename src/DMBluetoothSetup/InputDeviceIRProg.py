# -*- coding: utf-8 -*-

from enigma import eInputDeviceManager, eTimer
from Screens.Screen import Screen
from Screens.MessageBox import MessageBox
from .Rc import Rc
from Components.Sources.List import List
from Components.ActionMap import ActionMap
from Components.config import config
from Components.Sources.StaticText import StaticText
from Tools.Directories import pathExists, resolveFilename, SCOPE_CURRENT_SKIN
from Tools.LoadPixmap import LoadPixmap
from Tools.Log import Log

from os import path as os_path


from . import _
from .CharJump import CharJump
from .InputDeviceIRDatabase import irdb
from .IrProtocols.ProtocolMaster import ProtocolMaster
from .KeyBindingList import KeyBindingList


INPUT_DEVICE_IR_PROG_SKIN = """
<screen name="InputDeviceIRProg" position="center,100" size="920,560" title="IR Setup">
    <eLabel position="10,5" size="220,40" backgroundColor="#9f1313" />
    <eLabel position="230,5" size="220,40" backgroundColor="#1f771f" />
    <eLabel position="450,5" size="220,40" backgroundColor="#a08500" />
    <eLabel position="670,5" size="240,40" backgroundColor="#18188b" />
    <widget source="key_red" render="Label" position="10,5" size="220,40" zPosition="1" font="Regular;20" halign="center" valign="center" transparent="1" />
    <widget source="key_green" render="Label" position="230,5" size="220,40" zPosition="1" font="Regular;20" halign="center" valign="center" transparent="1" />
    <widget source="key_yellow" render="Label" position="450,5" size="220,40" zPosition="1" font="Regular;20" halign="center" valign="center" transparent="1" />
    <widget source="key_blue" render="Label" position="670,5" size="240,40" zPosition="1" font="Regular;20" halign="center" valign="center" transparent="1" />
    <widget source="list" render="Listbox" position="10,55" size="900,430" scrollbarMode="showOnDemand" transparent="1">
        <convert type="TemplatedMultiContent">
            {"template": [
                    MultiContentEntryPixmapAlphaBlend(pos=(14, 9), size=(48, 48), png=1),
                    MultiContentEntryText(pos=(78, 6), size=(810, 30), font=0, flags=RT_HALIGN_LEFT | RT_VALIGN_CENTER, text=3),
                    MultiContentEntryText(pos=(78, 38), size=(810, 23), font=1, flags=RT_HALIGN_LEFT | RT_VALIGN_CENTER, text=2),
                    MultiContentEntryPixmapAlphaBlend(pos=(0, 67), size=(900, 1), png=4),
                ],
                "fonts": [gFont("Regular", 24), gFont("Regular", 18)],
                "itemHeight": 68
            }
        </convert>
    </widget>
    <eLabel position="10,495" size="900,1" backgroundColor="grey" />
    <widget source="status" render="Label" position="10,505" size="900,40" font="Regular;22" halign="center" valign="center" transparent="1" />
</screen>
"""

INPUT_DEVICE_KEY_INFO_SKIN = """
<screen name="InputDeviceKeyInfo" position="center,60" size="920,660" title="IR Keys">
    <eLabel position="10,5" size="220,40" backgroundColor="#9f1313" />
    <widget source="key_red" render="Label" position="10,5" size="220,40" zPosition="1" font="Regular;20" halign="center" valign="center" transparent="1" />
    <widget name="rc" position="10,55" size="260,590" alphatest="blend" />
    <widget name="arrowdown" position="0,0" size="37,70" pixmap="skin_default/arrowdown.png" zPosition="2" alphatest="blend" />
    <widget name="arrowdown2" position="0,0" size="37,70" pixmap="skin_default/arrowdown.png" zPosition="2" alphatest="blend" />
    <widget name="arrowup" position="0,0" size="37,70" pixmap="skin_default/arrowup.png" zPosition="2" alphatest="blend" />
    <widget name="arrowup2" position="0,0" size="37,70" pixmap="skin_default/arrowup.png" zPosition="2" alphatest="blend" />
    <widget name="list" position="290,55" size="620,590" itemHeight="32" scrollbarMode="showOnDemand" />
</screen>
"""


def ensure_text(value):
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    return str(value)


class InputDeviceIRProg(Screen, CharJump):
    skin = INPUT_DEVICE_IR_PROG_SKIN

    PLUGIN_IMAGES_PATH = "%s/images/" % (os_path.dirname(__file__))
    SKIN_IMAGES_PATH = resolveFilename(SCOPE_CURRENT_SKIN, config.skin.primary_skin.value.replace("/skin.xml", "/images/"))
    MAJOR_CODELIST_ITEMS = ["amp", "av ", "tv", "vcr", "sat"]

    def __init__(self, session, remote):
        Screen.__init__(self, session)
        CharJump.__init__(self, session)
        self._remote = remote

        self["actions"] = ActionMap(["ListboxActions", "OkCancelActions", "EPGSelectActions"],
        {
            "ok": self._onKeyOK,
            "cancel": self._onKeyExit,
            "info": self._onKeyInfo
        }, -1)

        self["ColorActions"] = ActionMap(["ColorActions"],
        {
            "red": self._onKeyRed,
            "green": self._onKeyOK,
            "blue": self._onKeyInfo,
        }, -1)

        self["key_red"] = StaticText(_("Exit"))
        self["key_green"] = StaticText("")
        self["key_yellow"] = StaticText("")
        self["key_blue"] = StaticText("")

        self["list"] = List()
        self["list"].onSelectionChanged.append(self._onSelectionChanged)
        self._status = StaticText()
        self["status"] = self._status

        self._vendorPixmap = self._loadPixmap("vendor.png")
        self._seperatorPixmap = self._loadPixmap("div-h.svg")
        self._level = 0
        self._lastLevel = 0
        self._lastVendor = ""
        self._keysAcknowledged = 0
        self._expectedKeyAcks = 0
        self._transferActive = False
        self._sendQueue = []
        self._sentKeyCount = 0
        self._sendTimer = eTimer()
        self._sendTimer.callback.append(self._sendNext)
        self._keysAckTimer = eTimer()
        self._keysAckTimer.callback.append(self._onKeysAckTimeout)
        self._dm = eInputDeviceManager.getInstance()
        self._dm.irKeyCount.append(self._onIrKeyCount)
        self.onClose.append(self._removeInputDeviceManagerCallbacks)
        self.onLayoutFinish.append(self._reload)

    def _removeInputDeviceManagerCallbacks(self):
        try:
            self._dm.irKeyCount.remove(self._onIrKeyCount)
        except ValueError:
            pass
        try:
            self._keysAckTimer.callback.remove(self._onKeysAckTimeout)
        except ValueError:
            pass
        try:
            self._sendTimer.callback.remove(self._sendNext)
        except ValueError:
            pass

    def _onIrKeyCount(self, address, count):
        if address == self._remote.address():
            self._keysAcknowledged = count
            self._keysAckTimer.startLongTimer(2)

    def _onKeysAckTimeout(self):
        acknowledged = self._keysAcknowledged
        expected = self._expectedKeyAcks
        self._keysAcknowledged = 0
        self._expectedKeyAcks = 0
        if acknowledged:
            status = _("IR setup complete. %s IR codes acknowledged.") % (acknowledged,)
            self["status"].setText(status)
            if expected and acknowledged != expected:
                text = _("IR setup complete.\n%s of %s IR codes acknowledged.") % (acknowledged, expected)
            else:
                text = status
            self.session.open(MessageBox, text, type=MessageBox.TYPE_INFO, timeout=6)

    def _loadPixmap(self, filename, desktop=None):
        picfile = None
        if filename[0] == "/" and pathExists(filename):
            picfile = filename
        else:
            for p in (self.SKIN_IMAGES_PATH, self.PLUGIN_IMAGES_PATH):
                imagepath = "%s%s" % (p, filename)
                if pathExists(imagepath):
                    picfile = "%s%s" % (p, filename)
                    break
        if picfile:
            return LoadPixmap(path=picfile, desktop=desktop, cached=False)
        return None

    def _onKeyRed(self):
        self.close()

    def _onKeyExit(self):
        if self._level == 1:
            self._level = 0
            self._reload()
            return
        self.close()

    def _getFirstForChar(self, char):  # CharJump
        idx = 0
        for x in self["list"].list:
            val = x[0][0]
            if val and val[0].upper() == char:
                self["list"].setIndex(idx)
                break
            idx += 1

    def _onKey0(self, unused):  # CharJump
        if self["list"].count():
            self["list"].setIndex(0)

    def _reload(self, dlist=None):
        if self._level == 0 or dlist is None:
            dlist = irdb.data
        mlist = []
        for x, y in dlist.items():
            x = ensure_text(x)
            title = x
            subtitle = ""
            pic = self._seperatorPixmap
            if self._level == 0:
                lendev = len(y)
                if lendev == 1:
                    subtitle = "%s" % (ensure_text(next(iter(y))))
                else:
                    subtitle = _("%s devices") % (lendev,)
            else:
                models = y.get("models", [])
                sorted_models = []
                if models:
                    for dev in models:
                        dev = ensure_text(dev)
                        append = True
                        for item in self.MAJOR_CODELIST_ITEMS:
                            if dev.lower().startswith(item):
                                append = False
                        if append:
                            sorted_models.append(dev)
                        else:
                            sorted_models.insert(0, dev)
                    title = " / ".join(sorted_models)
                if title == "":
                    title = _("Unknown")
                if not len(y["keys"]):
                    Log.w("No known automap-keys for %s" % (title,))
                subtitle = _("%s mapped keys") % (len(y["keys"]))
            mlist.append(((x, y), self._vendorPixmap, subtitle, title, pic))
        if self._level != 0:
            def sortCodelist(x):
                x = x[0][0]
                val = "000000"
                items = self.MAJOR_CODELIST_ITEMS[:]
                items.reverse()
                for key in items:
                    if x.lower().startswith(key):
                        return val + x
                    val = "{}{}".format(val, "000000")
                return x

            mlist = sorted(mlist, key=sortCodelist)
        self["list"].setList(mlist)
        if self._level == 0:
            self["list"].setIndex(self._lastLevel)
            self.setTitle(_("Vendors"))
            self["key_green"].setText(_("Select"))
            self["key_blue"].setText("")
            self["status"].setText(_("%s entries") % (len(mlist),))
        else:
            self.setTitle(self._lastVendor)
            self["key_green"].setText(_("Apply"))
            self["key_blue"].setText(_("Info"))
            self._onSelectionChanged()

    def _onKeyOK(self):
        sel = self["list"].getCurrent()
        entry = sel and sel[0]
        if not entry:
            return
        if self._level == 0:
            self._level = 1
            self._lastLevel = self["list"].getIndex()
            self._lastVendor = ensure_text(entry[0])
            self._reload(entry[1])
        else:
            self._send(entry[1])

    def _onKeyInfo(self):
        if self._level == 0:
            return
        sel = self["list"].getCurrent()
        entry = sel and sel[0]
        if not entry:
            return
        device, data = entry[0:2]
        title = ensure_text("%s - %s (%s - %s:%s)" % (self._lastVendor, device, data["protocol"], data["device"], data["subdevice"]))
        self.session.open(InputDeviceKeyInfo, title, list(data["keys"]))

    def _send(self, data):
        if self._transferActive:
            return
        protocolData = ProtocolMaster.buildProtocol(data)
        self._sendQueue = []
        self._sentKeyCount = 0
        self._keysAcknowledged = 0
        self._expectedKeyAcks = 0
        for protocol, isRepeat, keys in protocolData:  # Initial / repeat
            if protocol:
                self._sendQueue.append(("protocol", isRepeat, protocol))
            for irKey in keys or []:
                self._sendQueue.append(("key", irKey))
                self._expectedKeyAcks += 1
        self._remote.resetIr()
        self._transferActive = True
        self["status"].setText(_("Transferring %s IR codes...") % (self._expectedKeyAcks,))
        self._sendTimer.start(1, True)

    def _sendNext(self):
        if not self._sendQueue:
            self._transferActive = False
            self._remote.getIrKeyCount()
            self["status"].setText(_("IR codes sent. Waiting for remote confirmation..."))
            return
        item = self._sendQueue.pop(0)
        if item[0] == "protocol":
            _kind, isRepeat, protocol = item
            self._remote.setIrProtocol(isRepeat, protocol)
        else:
            _kind, irKey = item
            self._remote.setIrKey(irKey)
            self._sentKeyCount += 1
            self["status"].setText(_("Transferring IR codes... %s/%s") % (self._sentKeyCount, self._expectedKeyAcks))
        self._sendTimer.start(1, True)

    def _onSelectionChanged(self):
        if self._level == 0:
            return
        entry = self["list"].getCurrent()
        entry = entry and entry[0]
        if not entry:
            return
        device, data = entry
        count = len(data["keys"])
        self["status"].setText(_("Press OK to apply %s IR keys for '%s'") % (count, device))


class InputDeviceKeyInfo(Screen, Rc):
    skin = INPUT_DEVICE_KEY_INFO_SKIN

    def __init__(self, session, title, boundKeys):
        Screen.__init__(self, session)
        self.setTitle(title)
        Rc.__init__(self, 3)
        keys = sorted(ensure_text(x) for x in boundKeys)
        self["list"] = KeyBindingList(3, keys)
        self["list"].onSelectionChanged.append(self._onSelectionChanged)
        self["key_red"] = StaticText(_("Exit"))
        self["actions"] = ActionMap(["OkCancelActions"],
        {
            "cancel": self.close,
        }, -1)
        self["ColorActions"] = ActionMap(["ColorActions"],
        {
            "red": self.close,
        }, -1)
        self.onLayoutFinish.append(self._onSelectionChanged)

    def _onSelectionChanged(self):
        self.clearSelectedKeys()
        selection = self["list"].getCurrent()
        selection = selection and selection[0]
        if not selection:
            return
        self.selectKey(selection)
