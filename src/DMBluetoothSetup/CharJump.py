# -*- coding: utf-8 -*-
from enigma import eRCInput, getPrevAsciiCode
from Components.ActionMap import NumberActionMap
from Tools.Log import Log
from Tools.NumericalTextInput import NumericalTextInput


class CharJump:

    def __init__(self, session, char='ABCDEFGHIJKLMNOPQRSTUVWXYZ'):
        rcinput = eRCInput.getInstance()
        rcinput.setKeyboardMode(rcinput.kmAscii)

        self.numericalTextInput = NumericalTextInput()
        self.numericalTextInput.setUseableChars(char)

        self["NumberActions"] = NumberActionMap(["NumberActions", "InputAsciiActions"],
        {
            "gotAsciiCode": self._keyAsciiCode,
            "1": self._keyNumberGlobal,
            "2": self._keyNumberGlobal,
            "3": self._keyNumberGlobal,
            "4": self._keyNumberGlobal,
            "5": self._keyNumberGlobal,
            "6": self._keyNumberGlobal,
            "7": self._keyNumberGlobal,
            "8": self._keyNumberGlobal,
            "9": self._keyNumberGlobal,
            "0": self._onKey0
        }, -1)

        self.onClose.append(self.__onClose)

    def __onClose(self):
        rcinput = eRCInput.getInstance()
        rcinput.setKeyboardMode(rcinput.kmNone)

    def _onKey0(self, unused):
        Log.w()
        pass

    def _getFirstForChar(self):
        raise NotImplementedError

    def _keyAsciiCode(self):
        char = chr(getPrevAsciiCode())
        if char:
            if char[0] == "0":
                self.__KeyNull(0)
            else:
                self._getFirstForChar(char[0].upper())

    def _keyNumberGlobal(self, number):
        char = self.numericalTextInput.getKey(number)
        if char:
            if char[0] == "0":
                self.__KeyNull(0)
            else:
                self._getFirstForChar(char[0])
