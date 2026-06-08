from setuptools import setup
import setup_translate

pkg = 'SystemPlugins.BluetoothSetup'
setup(name='enigma2-plugin-systemplugins-bluetoothsetup',
       version='1.0',
       description='Dreambox bluetooth plugin',
       package_dir={pkg: 'DMBluetoothSetup'},
       packages=[pkg],
       package_data={pkg: ['images/*.png', 'images/*.svg', '*.png', '*.xml', 'locale/*/LC_MESSAGES/*.mo', 'plugin.png', 'irdb.json']},
       cmdclass=setup_translate.cmdclass,  # for translation
      )
