import geopandas as gpd
import matplotlib.pyplot as plt
import json
from owslib.etree import etree
from owslib.wfs import WebFeatureService
from PyQt5.QtWidgets import QApplication, QTextEdit, QWidget, QVBoxLayout, QTableWidget, QPushButton, QTableWidgetItem, QHeaderView, QLabel, QProgressBar, QComboBox
from PyQt5.QtCore import QThread, pyqtSignal, QRunnable, QObject, QThreadPool

class WFSLoaderSignals(QObject):
    progress = pyqtSignal(int)
    finished = pyqtSignal(list)
    metadata_loaded = pyqtSignal(dict)

class WFSLoader(QRunnable):
    def __init__(self, url):
        super().__init__()
        self.url = url
        self.signals = WFSLoaderSignals()

    def run(self):
        wfs = WebFeatureService(url=self.url, version='2.0.0')
        
        # Get server metadata
        capabilities_xml = wfs.getcapabilities().read()
        root = etree.fromstring(capabilities_xml)
        ns = {'ows': 'http://www.opengis.net/ows/1.1'}
        
        service_identification = root.find('.//ows:ServiceIdentification', namespaces=ns)
        
        metadata = {
            'title': service_identification.findtext('ows:Title', namespaces=ns),
            'abstract': service_identification.findtext('ows:Abstract', namespaces=ns),
            'keywords': [keyword.text for keyword in service_identification.findall('ows:Keywords/ows:Keyword', namespaces=ns)],
            'fees': service_identification.findtext('ows:Fees', namespaces=ns),
            'access_constraints': service_identification.findtext('ows:AccessConstraints', namespaces=ns)
        }
        self.signals.metadata_loaded.emit(metadata)
        
        layers = list(wfs.contents.items())
        total = len(layers)
        layer_info = []
        for i, (name, layer) in enumerate(layers):
            title = layer.title if layer.title else name
            abstract = layer.abstract if layer.abstract else ""
            url = f"{self.url}?service=WFS&version=2.0.0&request=GetFeature&typeName={name}&outputFormat=json"
            layer_info.append((name, title, abstract, url))
            self.signals.progress.emit(int((i + 1) / total * 100))
        self.signals.finished.emit(layer_info)

class LayerSelector(QWidget):
    def __init__(self):
        super().__init__()
        self.layers = []
        self.selected_layer = None
        self.thread_pool = QThreadPool()
        self.initUI()

    def initUI(self):
        layout = QVBoxLayout()
        
        self.status_label = QLabel("Select a server and click 'Load Layers'")
        layout.addWidget(self.status_label)

        self.server_combo = QComboBox()
        self.server_combo.addItem("RIVM ALO WFS", "https://data.rivm.nl/geo/alo/wfs")
        self.server_combo.addItem("REV WFS", "https://rev-portaal.nl/geoserver/wfs/rev_public")
        self.server_combo.addItem("RIVM ANK WFS", "https://data.rivm.nl/geo/ank/wfs")
        self.server_combo.addItem("RIVM Basisnet WFS", "https://data.rivm.nl/geo/basisnet/ows")
        self.server_combo.addItem("RIVM NL WFS", "https://data.rivm.nl/geo/nl/wfs")
        self.server_combo.addItem("GEODAN WFS", " https://apps.geodan.nl/public/data/org/gws/YWFMLMWERURF/kea_public/wfs")
        self.server_combo.currentIndexChanged.connect(self.load_server)
        layout.addWidget(self.server_combo)

        load_button = QPushButton('Load selected server')
        load_button.clicked.connect(self.load_server)
        layout.addWidget(load_button)

        self.metadata_label = QLabel("Server Metadata:")
        layout.addWidget(self.metadata_label)

        self.metadata_text = QTextEdit()
        self.metadata_text.setReadOnly(True)
        self.metadata_text.setFixedHeight(170)  # Set a fixed height (e.g., 100 pixels)
        layout.addWidget(self.metadata_text)
        
        self.progress_bar = QProgressBar()
        layout.addWidget(self.progress_bar)
        
        self.tableWidget = QTableWidget()
        self.tableWidget.setColumnCount(4)
        self.tableWidget.setHorizontalHeaderLabels(["Name", "Title", "Abstract", "URL"])
        self.tableWidget.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.tableWidget.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.tableWidget)

        select_button = QPushButton('Load Selected Layer')
        select_button.clicked.connect(self.on_select)
        layout.addWidget(select_button)

        self.setLayout(layout)
        self.setWindowTitle('Select a Layer')
        self.resize(1200, 600)

    def load_server(self):
        url = self.server_combo.currentData()
        self.status_label.setText(f"Loading layers from {url}...")
        self.progress_bar.setValue(0)
        self.tableWidget.setRowCount(0)
        self.metadata_text.clear()
        loader = WFSLoader(url)
        loader.signals.progress.connect(self.update_progress)
        loader.signals.finished.connect(self.on_layers_loaded)
        loader.signals.metadata_loaded.connect(self.display_metadata)
        self.thread_pool.start(loader)

    def update_progress(self, value):
        self.progress_bar.setValue(value)

    def display_metadata(self, metadata):
        metadata_text = f"Title: {metadata['title']}\n\n"
        metadata_text += f"Abstract: {metadata['abstract']}\n\n"
        metadata_text += f"Keywords: {', '.join(metadata['keywords'])}\n\n"
        metadata_text += f"Fees: {metadata['fees']}\n\n"
        metadata_text += f"Access Constraints: {metadata['access_constraints']}"
        self.metadata_text.setPlainText(metadata_text)

    def on_layers_loaded(self, layer_info):
        self.layers = layer_info
        self.tableWidget.setRowCount(len(self.layers))
        for i, (name, title, abstract, url) in enumerate(self.layers):
            self.tableWidget.setItem(i, 0, QTableWidgetItem(name))
            self.tableWidget.setItem(i, 1, QTableWidgetItem(title))
            self.tableWidget.setItem(i, 2, QTableWidgetItem(abstract))
            self.tableWidget.setItem(i, 3, QTableWidgetItem(url))
        self.status_label.setText(f"Loaded {len(self.layers)} layers")
        
        self.tableWidget.setColumnWidth(0, 250)
        self.tableWidget.setColumnWidth(1, 250)
        self.tableWidget.setColumnWidth(2, 300)

    def on_select(self):
        selected_items = self.tableWidget.selectedItems()
        if selected_items:
            row = selected_items[0].row()
            self.selected_layer = self.layers[row][0]
            self.close()

def visualize_layer(layer_name, url):
    wfs = WebFeatureService(url=url, version='2.0.0')
    response = wfs.getfeature(typename=layer_name, outputFormat='application/json')
    data = json.loads(response.read())
    gdf = gpd.GeoDataFrame.from_features(data['features'])
    gdf.plot()
    plt.title(layer_name)
    plt.axis('off')
    plt.show()

if __name__ == '__main__':
    app = QApplication([])
    selector = LayerSelector()
    selector.show()
    app.exec_()

    # Ensure all threads are finished before exiting
    selector.thread_pool.waitForDone()

    if selector.selected_layer:
        url = selector.server_combo.currentData()
        visualize_layer(selector.selected_layer, url)

