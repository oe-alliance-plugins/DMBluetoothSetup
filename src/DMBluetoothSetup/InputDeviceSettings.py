from Screens.Screen import Screen
from Components.ConfigList import ConfigListScreen
from Components.config import config, getConfigListEntry
from Components.Sources.StaticText import StaticText

from . import ensureInputDeviceManagerConfig


INPUT_DEVICE_SETTINGS_SKIN = """
<screen name="InputDeviceSettings" position="center,160" size="820,360" title="Bluetooth remote settings">
    <eLabel position="10,5" size="200,40" backgroundColor="#9f1313" />
    <eLabel position="210,5" size="200,40" backgroundColor="#1f771f" />
    <widget source="key_red" render="Label" position="10,5" size="200,40" zPosition="1" font="Regular;20" halign="center" valign="center" transparent="1" />
    <widget source="key_green" render="Label" position="210,5" size="200,40" zPosition="1" font="Regular;20" halign="center" valign="center" transparent="1" />
    <widget source="key_menu" render="Label" position="0,0" size="0,0" zPosition="1" font="Regular;20" transparent="1" />
    <widget source="key_text" render="Label" position="0,0" size="0,0" zPosition="1" font="Regular;20" transparent="1" />
    <eLabel position="10,50" size="800,1" backgroundColor="grey" />
    <widget name="config" position="10,60" size="800,180" itemHeight="34" scrollbarMode="showOnDemand" />
    <eLabel position="10,250" size="800,1" backgroundColor="grey" />
    <widget source="description" render="Label" position="10,260" size="800,85" font="Regular;20" halign="center" valign="center" transparent="1" />
    <widget name="HelpWindow" position="0,0" size="0,0" />
</screen>
"""


class InputDeviceSettings(Screen, ConfigListScreen):
    skin = INPUT_DEVICE_SETTINGS_SKIN

    def __init__(self, session):
        Screen.__init__(self, session)
        self.setTitle(_("Bluetooth remote settings"))
        ensureInputDeviceManagerConfig()
        self["description"] = StaticText("")
        configList = [
            getConfigListEntry(
                _("LED color when connected to this receiver"),
                config.inputDevices.settings.connectedColor,
                _("LED ring color used when the remote control is connected in Bluetooth mode."),
            ),
            getConfigListEntry(
                _("IR-Mode LED color when connected to this receiver"),
                config.inputDevices.settings.connectedColorIr,
                _("LED ring color used when the remote control is connected in IR mode."),
            ),
            getConfigListEntry(
                _("Haptic feedback in lists"),
                config.inputDevices.settings.listboxFeedback,
                _("Enable vibration feedback when moving through Bluetooth remote-control lists."),
            ),
        ]
        ConfigListScreen.__init__(self, configList, session=session, on_change=self._changedEntry, fullUI=True)
        self["config"].onSelectionChanged.append(self._selectionChanged)
        self.onLayoutFinish.append(self._selectionChanged)

    def _changedEntry(self):
        # The ConfigSelection notifiers in __init__.py send the changed color
        # directly to the connected RCU. Do not send again here, otherwise one
        # left/right key press creates two identical /dev/ble writes.
        self._selectionChanged()

    def _selectionChanged(self):
        self["description"].setText(self.getCurrentDescription())
