from setuptools import setup
import setup_translate

pkg = "SystemPlugins.BluetoothSetup"

setup(
    name="enigma2-plugin-systemplugins-bluetoothsetup",
    version="1.0",
    description="Dreambox bluetooth plugin",
    package_dir={
        pkg: "DMBluetoothSetup",
        f"{pkg}.IrProtocols": "DMBluetoothSetup/IrProtocols",
        f"{pkg}.IrDatabase": "DMBluetoothSetup/IrDatabase",
        f"{pkg}.Tools": "DMBluetoothSetup/Tools",
    },
    packages=[
        pkg,
        f"{pkg}.IrProtocols",
        f"{pkg}.IrDatabase",
        f"{pkg}.Tools",
    ],
    package_data={
        pkg: [
            "images/*.png",
            "images/*.svg",
            "*.png",
            "*.xml",
            "locale/*/LC_MESSAGES/*.mo",
            "plugin.png",
            "irdb.json",
        ],
    },
    cmdclass=setup_translate.cmdclass,
)