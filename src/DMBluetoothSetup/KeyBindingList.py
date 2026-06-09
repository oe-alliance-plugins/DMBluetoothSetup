# -*- coding: utf-8 -*-

from Components.GUIComponent import GUIComponent
from enigma import RT_VALIGN_CENTER, eListbox, eListboxPythonMultiContent, gFont
from keyids import KEYIDNAMES, KEYIDS
from skin import fonts as skinFonts

from . import _


class KeyBindingList(GUIComponent):
    KEY_NAMES = {
        "KEY_MUTE": _("Mute"),
        "KEY_MODE": _("Mode"),
        "KEY_POWER": _("Power"),
        "KEY_RED": _("Red"),
        "KEY_BLUE": _("Blue"),
        "KEY_GREEN": _("Green"),
        "KEY_YELLOW": _("Yellow"),
        "KEY_UP": _("Up"),
        "KEY_DOWN": _("Down"),
        "KEY_OK": _("OK"),
        "KEY_LEFT": _("Left"),
        "KEY_RIGHT": _("Right"),
        "KEY_MENU": _("Menu"),
        "KEY_VIDEO": _("PVR"),
        "KEY_INFO": _("Info"),
        "KEY_AUDIO": _("Audio"),
        "KEY_TEXT": _("TXT"),
        "KEY_PREVIOUS": _("<"),
        "KEY_NEXT": _(">"),
        "KEY_PLAY": _("Play/Pause"),
        "KEY_CHANNELUP": _("+"),
        "KEY_CHANNELDOWN": _("-"),
        "KEY_EXIT": _("Exit"),
        "KEY_STOP": _("Stop"),
        "KEY_RECORD": _("Record"),
        "KEY_VOLUMEUP": _("Volume +"),
        "KEY_VOLUMEDOWN": _("Volume -"),
        "KEY_FASTFORWARD": _("Fast Forward"),
        "KEY_REWIND": _("Rewind"),
    }

    KEY_ORDER = [
        "KEY_MUTE",
        "KEY_MODE",
        "KEY_POWER",
        "KEY_REWIND",
        "KEY_PLAY",
        "KEY_FASTFORWARD",
        "KEY_RECORD",
        "KEY_STOP",
        "KEY_TEXT",
        "KEY_RED",
        "KEY_GREEN",
        "KEY_YELLOW",
        "KEY_BLUE",
        "KEY_INFO",
        "KEY_MENU",
        "KEY_UP",
        "KEY_LEFT",
        "KEY_OK",
        "KEY_RIGHT",
        "KEY_DOWN",
        "KEY_AUDIO",
        "KEY_VIDEO",
        "KEY_VOLUMEUP",
        "KEY_EXIT",
        "KEY_CHANNELUP",
        "KEY_VOLUMEDOWN",
        "KEY_CHANNELDOWN",
        "KEY_1",
        "KEY_2",
        "KEY_3",
        "KEY_4",
        "KEY_5",
        "KEY_6",
        "KEY_7",
        "KEY_8",
        "KEY_9",
        "KEY_PREVIOUS",
        "KEY_0",
        "KEY_NEXT",
    ]

    DEFAULT_ITEM_HEIGHT = 30
    DEFAULT_TEXT_X = 5
    DEFAULT_TEXT_Y = 0
    DEFAULT_TEXT_WIDTH = 1000
    DEFAULT_TEXT_HEIGHT = 30

    def __init__(self, rcUsed, boundKeys):
        GUIComponent.__init__(self)
        self.onSelectionChanged = []
        self.l = eListboxPythonMultiContent()
        self._rcUsed = rcUsed
        boundKeys = set(boundKeys)

        entries = []
        for key in self.KEY_ORDER:
            if key not in boundKeys:
                continue
            keyId = KEYIDS.get(key)
            if keyId is None:
                continue
            description = self.KEY_NAMES.get(key, self._formatKeyName(keyId, key))
            entry = [(keyId, key)]
            entry.append((
                eListboxPythonMultiContent.TYPE_TEXT,
                self.DEFAULT_TEXT_X,
                self.DEFAULT_TEXT_Y,
                self.DEFAULT_TEXT_WIDTH,
                self.DEFAULT_TEXT_HEIGHT,
                0,
                RT_VALIGN_CENTER,
                description,
            ))
            entries.append(entry)
        self.l.setList(entries)

        choiceFace, choiceSize = self._getSkinFont("ChoiceList", "Regular", 20)
        bodyFace, bodySize = self._getSkinFont("Body", choiceFace, choiceSize)
        self.l.setFont(0, gFont(choiceFace, choiceSize))
        self.l.setFont(1, gFont(bodyFace, bodySize))
        self.l.setItemHeight(max(self.DEFAULT_ITEM_HEIGHT, choiceSize + 10))

    def _getSkinFont(self, name, defaultFace, defaultSize):
        font = skinFonts.get(name)
        if font:
            return font[0], font[1]
        return defaultFace, defaultSize

    def _formatKeyName(self, keyId, key):
        name = KEYIDNAMES.get(keyId, key)
        if name.startswith("KEY_"):
            name = name[4:]
        return name.replace("_", " ").title()

    def getCurrent(self):
        selection = self.l.getCurrentSelection()
        return selection and selection[0]

    GUI_WIDGET = eListbox

    def postWidgetCreate(self, instance):
        instance.setContent(self.l)
        instance.selectionChanged.get().append(self.selectionChanged)

    def preWidgetRemove(self, instance):
        instance.setContent(None)
        instance.selectionChanged.get().remove(self.selectionChanged)

    def selectionChanged(self):
        for callback in self.onSelectionChanged:
            callback()
