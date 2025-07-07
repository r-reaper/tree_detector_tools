import os
from qgis.PyQt.QtWidgets import QAction, QMessageBox
from qgis.PyQt.QtGui import QIcon

from . import resources_rc

try:
    from .tree_detector_tools_dialog import TreeDetectorDialog
except Exception as e:
    QMessageBox.critical(
        None,
        "Plugin Load Error",
        f"ไม่สามารถโหลดปลั๊กอินได้: {e}"
    )
    raise e

class TreeDetectorPlugin:
    def __init__(self, iface):
        self.iface = iface
        self.plugin_dir = os.path.dirname(__file__)
        self.actions = []
        self.toolbar = self.iface.addToolBar('TreeDetectorToolbar')
        self.toolbar.setObjectName('TreeDetectorToolbar')
        self.dialog = None

    def initGui(self):
        icon_path = ':/plugins/tree_detector_tools/icon.svg'
        self.action = QAction(
            QIcon(icon_path),
            'Run Tree Detection',
            self.iface.mainWindow()
        )
        self.action.triggered.connect(self.run)
        self.toolbar.addAction(self.action)
        self.actions.append(self.action)

    def unload(self):
        for action in self.actions:
            self.iface.removeToolBarIcon(action)
        del self.toolbar
        if self.dialog:
            self.dialog.closingPlugin()

    def run(self):
        if self.dialog is None:
            self.dialog = TreeDetectorDialog(self.iface)
        self.dialog.show()