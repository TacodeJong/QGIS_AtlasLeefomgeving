import os
from PyQt5.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction
from qgis.core import QgsProject, QgsVectorLayer
from .nl_wfs_loader_dialog import NLWFSLoaderDialog

class NLWFSLoader:
    def __init__(self, iface):
        self.iface = iface
        self.actions = []
        self.toolbar = self.iface.addToolBar('NL WFS Loader')  # Create a toolbar specifically for your plugin
        self.toolbar.setObjectName('NL WFS Loader')

    def add_action(self, icon_path, text, callback, enabled_flag=True, parent=None):
        # Create an action with an icon and text
        icon = QIcon(icon_path)
        action = QAction(icon, text, parent)
        action.triggered.connect(callback)
        action.setEnabled(enabled_flag)

        # Add the action to the toolbar
        self.toolbar.addAction(action)

        # Track actions for cleanup later
        self.actions.append(action)
        return action

    def initGui(self):
        # Path to the plugin's icon file
        icon_path = os.path.join(os.path.dirname(__file__), 'icon.svg')
        
        # Add the action to the toolbar
        self.add_action(
            icon_path,
            text='Load NL WFS Layers',
            callback=self.run,
            parent=self.iface.mainWindow()
        )

    def unload(self):
        # Remove actions from the toolbar
        for action in self.actions:
            self.toolbar.removeAction(action)
        del self.toolbar

    def run(self):
        # Open the dialog to load WFS layers
        dialog = NLWFSLoaderDialog()
        result = dialog.exec_()
        if result:
            selected_layer = dialog.selected_layer
            if selected_layer:
                url = dialog.server_combo.currentData()
                self.load_wfs_layer(selected_layer, url)

    def load_wfs_layer(self, layer_name, url):
        uri = f"{url}?service=WFS&version=2.0.0&request=GetFeature&typeName={layer_name}&outputFormat=application/json"
        layer = QgsVectorLayer(uri, layer_name, "WFS")
        if layer.isValid():
            QgsProject.instance().addMapLayer(layer)
            self.iface.messageBar().pushSuccess("Success", f"Layer '{layer_name}' added to the map")
        else:
            self.iface.messageBar().pushCritical("Error", f"Failed to load layer '{layer_name}'")
