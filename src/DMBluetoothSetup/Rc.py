# -*- coding: utf-8 -*-

from Components.InputDevice import remoteControl
from Components.Pixmap import MovingPixmap, Pixmap
from Tools.LoadPixmap import LoadPixmap
from keyids import KEYIDS


class Rc:
    def __init__(self, rcUsed=False):
        self["rc"] = Pixmap()
        self["arrowdown"] = MovingPixmap()
        self["arrowdown2"] = MovingPixmap()
        self["arrowup"] = MovingPixmap()
        self["arrowup2"] = MovingPixmap()
        self._rcUsed = rcUsed
        self._rcPosition = None
        self.selectpics = []
        self.selectedKeys = []
        self.onLayoutFinish.append(self.initRc)

    def initRc(self):
        rcPixmap = LoadPixmap(remoteControl.getRemoteControlPixmap())
        if rcPixmap and self["rc"].instance:
            self["rc"].instance.setPixmap(rcPixmap)
        self._rcPosition = self["rc"].getPosition()
        rcHeight = self["rc"].getSize()[1] or 500
        self.selectpics = [
            ((rcHeight + 1) // 2, ["arrowdown", "arrowdown2"], (-18, -70)),
            (rcHeight, ["arrowup", "arrowup2"], (-18, 0)),
        ]
        self.clearSelectedKeys()

    def getSelectPic(self, pos):
        for selectPic in self.selectpics:
            if pos[1] <= selectPic[0]:
                return selectPic[1], selectPic[2]
        return None

    def hideRc(self):
        self["rc"].hide()
        self.hideSelectPics()

    def showRc(self):
        self["rc"].show()

    def _getKeyId(self, key):
        if isinstance(key, int):
            return key
        if isinstance(key, str):
            key = key.strip()
            keyId = KEYIDS.get(key)
            if keyId is None and not key.startswith("KEY_"):
                keyId = KEYIDS.get("KEY_%s" % key)
            return keyId
        return None

    def selectKey(self, key):
        keyId = self._getKeyId(key)
        if keyId is None:
            return
        pos = remoteControl.getRemoteControlKeyPos(keyId)
        if not pos:
            return
        rcpos = self._rcPosition or self["rc"].getPosition()
        selectPics = self.getSelectPic(pos)
        if selectPics is None:
            return
        selectPic = None
        for pic in selectPics[0]:
            if pic not in self.selectedKeys:
                selectPic = pic
                break
        if selectPic is None:
            return
        self[selectPic].moveTo(rcpos[0] + pos[0] + selectPics[1][0], rcpos[1] + pos[1] + selectPics[1][1], 1)
        self[selectPic].startMoving()
        self[selectPic].show()
        self.selectedKeys.append(selectPic)

    def clearSelectedKeys(self):
        self.showRc()
        self.selectedKeys = []
        self.hideSelectPics()

    def hideSelectPics(self):
        for selectPic in self.selectpics:
            for pic in selectPic[1]:
                self[pic].hide()
