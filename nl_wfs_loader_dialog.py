import os
import requests
import json
from qgis.PyQt import uic
from qgis.PyQt.QtWidgets import QDialog, QTableWidgetItem, QHeaderView
from qgis.PyQt.QtCore import QThread, pyqtSignal
from qgis.core import QgsVectorLayer, QgsProject, QgsField, QgsFields, QgsFeature, QgsGeometry, QgsPointXY, QgsCoordinateReferenceSystem, QgsWkbTypes
from PyQt5.QtCore import QVariant
from owslib.wfs import WebFeatureService

FORM_CLASS, _ = uic.loadUiType(os.path.join(
    os.path.dirname(__file__), 'nl_wfs_loader_dialog_base.ui'))

class WFSLoader(QThread):
    progress = pyqtSignal(int)
    finished = pyqtSignal(list)

    def __init__(self, url):
        super().__init__()
        self.url = url

    def run(self):
        wfs = WebFeatureService(url=self.url, version='2.0.0')
        layers = list(wfs.contents.items())
        total = len(layers)
        layer_info = []
        for i, (name, layer) in enumerate(layers):
            title = layer.title if layer.title else name
            abstract = layer.abstract if layer.abstract else ""
            url = f"{self.url}?service=WFS&version=2.0.0&request=GetFeature&typeName={name}&outputFormat=json"
            layer_info.append((name, title, abstract, url))
            self.progress.emit(int((i + 1) / total * 100))
        self.finished.emit(layer_info)

class NLWFSLoaderDialog(QDialog, FORM_CLASS):
    def __init__(self, parent=None):
        super(NLWFSLoaderDialog, self).__init__(parent)
        self.setupUi(self)
        self.layers = []

        # Set up the server combo box
        self.serverComboBox.addItem("Atlas Leefomgeving - RIVM ALO WFS", "https://data.rivm.nl/geo/alo/wfs")
        self.serverComboBox.addItem("Risicokaart - REV WFS", "https://rev-portaal.nl/geoserver/wfs/rev_public")
        self.serverComboBox.addItem("Atlas Natuurlijk Kapitaal - RIVM ANK WFS", "https://data.rivm.nl/geo/ank/wfs")
        self.serverComboBox.addItem("VWS - RIVM NL WFS", "https://data.rivm.nl/geo/nl/wfs")
        # self.serverComboBox.addItem("RIVM Basisnet WFS", "https://data.rivm.nl/geo/basisnet/wms")
        self.serverComboBox.addItem("GEODAN WFS", " https://apps.geodan.nl/public/data/org/gws/YWFMLMWERURF/kea_public/wfs")

        # Connect signals
        self.loadLayersButton.clicked.connect(self.load_layers)
        self.addLayerButton.clicked.connect(self.add_selected_layer)

        # Set up the table widget
        self.layerTableWidget.setColumnCount(4)
        self.layerTableWidget.setHorizontalHeaderLabels(["Name", "Title", "Abstract", "URL"])
        self.layerTableWidget.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)

    def load_layers(self):
        url = self.serverComboBox.currentData()
        self.statusLabel.setText(f"Loading layers from {url}...")
        self.progressBar.setValue(0)
        self.layerTableWidget.setRowCount(0)
        self.loader = WFSLoader(url)
        self.loader.progress.connect(self.update_progress)
        self.loader.finished.connect(self.on_layers_loaded)
        self.loader.start()

    def update_progress(self, value):
        self.progressBar.setValue(value)

    def on_layers_loaded(self, layer_info):
        self.layers = layer_info
        self.layerTableWidget.setRowCount(len(self.layers))
        for i, (name, title, abstract, url) in enumerate(self.layers):
            self.layerTableWidget.setItem(i, 0, QTableWidgetItem(name))
            self.layerTableWidget.setItem(i, 1, QTableWidgetItem(title))
            self.layerTableWidget.setItem(i, 2, QTableWidgetItem(abstract))
            self.layerTableWidget.setItem(i, 3, QTableWidgetItem(url))
        self.statusLabel.setText(f"Loaded {len(self.layers)} layers")

    def add_selected_layer(self):
        selected_items = self.layerTableWidget.selectedItems()
        if selected_items:
            row = selected_items[0].row()
            _, layer_name, _, url = self.layers[row]
            self.add_wfs_layer(layer_name, url)

    def geojson_to_wkt(self, geometry):
        geom_type = geometry.get('type')
        coordinates = geometry.get('coordinates')
        
        if not geom_type or not coordinates:
            # Invalid geometry structure
            return None
        
        def coords_to_wkt(rings):
            # Convert a list of rings to WKT format
            return ','.join(f"({','.join(f'{x} {y}' for x, y in ring)})" for ring in rings)
        
        if geom_type == 'Point':
            return f"POINT({coordinates[0]} {coordinates[1]})"
        
        elif geom_type == 'MultiPoint':
            points = [f"{x} {y}" for x, y in coordinates]
            return f"MULTIPOINT({','.join(points)})"
        
        elif geom_type == 'Polygon':
            # Include outer ring and holes
            rings = coords_to_wkt(coordinates)
            return f"POLYGON({rings})"
        
        elif geom_type == 'MultiPolygon':
            # Include multiple polygons with outer rings and holes
            polygons = [f"({coords_to_wkt(polygon)})" for polygon in coordinates]
            return f"MULTIPOLYGON({','.join(polygons)})"
        
        else:
            # Unsupported geometry type
            return None


    def coords_to_wkt(self, coords):
        return ','.join([f"{x} {y}" for x, y in coords])
    
    def add_wfs_layer(self, layer_name, url):
        response = requests.get(url)
        if response.status_code != 200:
            self.statusLabel.setText(f"Failed to fetch data for layer '{layer_name}'")
            return

        geojson_dict = json.loads(response.content)

        # Determine the geometry type from the first feature
        first_feature = geojson_dict['features'][0]
        geom_type = first_feature['geometry']['type']
        
        # Create a new vector layer with the appropriate geometry type
        if geom_type in ['Point', 'MultiPoint']:
            vl = QgsVectorLayer("Point?crs=EPSG:28992", layer_name, "memory")
        elif geom_type in ['Polygon', 'MultiPolygon']:
            vl = QgsVectorLayer("MultiPolygon?crs=EPSG:28992", layer_name, "memory")
        else:
            self.statusLabel.setText(f"Unsupported geometry type: {geom_type}")
            return

        pr = vl.dataProvider()

        # Add fields to the layer based on the first feature's properties
        if geojson_dict['features']:
            properties = geojson_dict['features'][0]['properties']
            fields = QgsFields()
            for name, value in properties.items():
                if isinstance(value, int):
                    fields.append(QgsField(name, QVariant.Int))
                elif isinstance(value, float):
                    fields.append(QgsField(name, QVariant.Double))
                else:
                    fields.append(QgsField(name, QVariant.String))
            pr.addAttributes(fields)
            vl.updateFields()


        # Iterate through the features in the GeoJSON and add them to the layer
        for feature in geojson_dict['features']:
            try:
                # Create a new QGIS feature
                fet = QgsFeature()
                
                # Extract geometry and convert to WKT
                geometry = feature.get('geometry')
                if not geometry:
                    continue  # Skip if geometry is missing
                
                wkt = self.geojson_to_wkt(geometry)
                if not wkt:
                    continue  # Skip if WKT conversion fails
                
                fet.setGeometry(QgsGeometry.fromWkt(wkt))
                
                # Extract properties and ensure they are properly serialized
                properties = feature.get('properties', {})
                if not isinstance(properties, dict):
                    properties = {}  # Default to empty if properties are not a dictionary
                
                # Convert properties to a list of strings, handle nested structures if needed
                attributes = [json.dumps(value) if isinstance(value, (dict, list)) else str(value) 
                            for value in properties.values()]
                
                # Append WKT as an additional attribute
                attributes.append(wkt)
                
                # Set attributes for the feature
                fet.setAttributes(attributes)
                
                # Add the feature to the provider
                pr.addFeature(fet)
            except Exception as e:
                QgsMessageLog.logMessage(f"Error processing feature: {e}", "NL WFS Loader", Qgis.Critical)
                continue  # Log and skip problematic features


        # Update the layer's extent
        vl.updateExtents()

        # Set the correct CRS
        vl.setCrs(QgsCoordinateReferenceSystem("EPSG:28992"))

        # Add the layer to the QGIS project
        QgsProject.instance().addMapLayer(vl)
        self.statusLabel.setText(f"Layer '{layer_name}' added to the map")
