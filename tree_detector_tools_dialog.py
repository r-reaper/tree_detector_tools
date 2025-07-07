import os
import tempfile
import subprocess
import json
import platform
from qgis.PyQt.QtWidgets import QDialog, QLineEdit, QPushButton, QFileDialog
from qgis.PyQt.QtCore import QVariant, Qt
from qgis.core import (QgsProject, QgsVectorLayer, QgsField, QgsFeature, 
                       QgsGeometry, QgsPointXY, QgsRasterLayer, QgsWkbTypes,
                       QgsTask, QgsApplication, QgsMessageLog, Qgis,
                       QgsMapLayerProxyModel)
from qgis.gui import QgsMapLayerComboBox

from .ui_tree_detector_tools_dialog_base import Ui_TreeDetectorDialogBase

def run_external_script(task, python_path, script_path, input_raster, model_path, confidence, iou):

    QgsMessageLog.logMessage(f"Starting external script: {script_path}", "TreeDetector", Qgis.Info)
    
    command = [
        python_path,
        script_path,
        '--input', input_raster,
        '--model', model_path,
        '--conf', str(confidence),
        '--iou', str(iou)
    ]
    
    env = os.environ.copy()
    env.pop('PYTHONHOME', None)
    env.pop('PYTHONPATH', None)
    
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding='utf-8',
        env=env
    )

    json_output = ""
    for line in iter(process.stdout.readline, ''):
        line = line.strip()
        if task.isCanceled():
            process.kill()
            return {'success': False, 'error': 'Task Canceled'}

        if line.startswith('PROGRESS:'):
            try:
                progress = int(line.split(':')[1])
                task.setProgress(progress)
            except (ValueError, IndexError):
                pass
        else:
            json_output += line

    process.wait()

    if process.returncode != 0:
        error_message = f"External script failed with exit code {process.returncode}.\nStderr: {process.stderr.read()}"
        QgsMessageLog.logMessage(error_message, "TreeDetector", Qgis.Critical)
        return {'success': False, 'error': error_message}

    try:
        detections = json.loads(json_output)
        return {'success': True, 'detections': detections}
    except json.JSONDecodeError as e:
        error_message = f"Failed to parse JSON from script output.\nError: {e}\nOutput: {json_output}"
        QgsMessageLog.logMessage(error_message, "TreeDetector", Qgis.Critical)
        return {'success': False, 'error': error_message}


class TreeDetectorDialog(QDialog, Ui_TreeDetectorDialogBase):
    def __init__(self, iface, parent=None):
        super(TreeDetectorDialog, self).__init__(parent)
        self.iface = iface
        self.setupUi(self)

        self.mMapLayerComboBox.setFilters(QgsMapLayerProxyModel.RasterLayer)
        self.mFileWidget_model.setFilter("YOLO Model (*.pt)")
        
        self.python_path_edit = QLineEdit()
        self.python_path_button = QPushButton("...")
        self.python_path_button.clicked.connect(self.select_python_path)
        self.python_path_layout.setContentsMargins(0,0,0,0)
        self.python_path_layout.addWidget(self.python_path_edit)
        self.python_path_layout.addWidget(self.python_path_button)

        self.btn_start_detection.clicked.connect(self.start_external_process)
        self.button_box.rejected.connect(self.reject)
        
        self.task = None
        self.auto_detect_python_path()

    def auto_detect_python_path(self):
        # *** FIX: Read from a standard config location in the user's home directory ***
        config_dir = os.path.join(os.path.expanduser("~"), ".tree_detector_plugin")
        config_path = os.path.join(config_dir, 'config.txt')
        
        if os.path.exists(config_path):
            with open(config_path, 'r') as f:
                python_exe = f.read().strip()
            
            if os.path.exists(python_exe):
                self.python_path_edit.setText(python_exe)
                self.iface.messageBar().pushMessage("Info", "Processing Python environment detected automatically.", level=Qgis.Info, duration=5)
            else:
                self.iface.messageBar().pushMessage("Warning", "Config file found, but Python path is invalid. Please re-run the setup script.", level=Qgis.Warning, duration=10)
        else:
            self.iface.messageBar().pushMessage("Warning", "Could not find config file. Please run the setup script.", level=Qgis.Warning, duration=10)

    def select_python_path(self):
        start_dir = os.path.dirname(self.python_path_edit.text()) if self.python_path_edit.text() else os.path.expanduser("~")
        dialog = QFileDialog(self, "Select Python Executable", start_dir)
        dialog.setFileMode(QFileDialog.ExistingFile)
        dialog.setOption(QFileDialog.DontResolveSymlinks)
        
        if dialog.exec_():
            selected_file = dialog.selectedFiles()[0]
            self.python_path_edit.setText(selected_file)

    def start_external_process(self):
        raster_layer = self.mMapLayerComboBox.currentLayer()
        model_path = self.mFileWidget_model.filePath()
        python_path = self.python_path_edit.text()
        confidence = self.mDoubleSpinBox_confidence.value()
        iou = self.mDoubleSpinBox_iou.value()

        if not isinstance(raster_layer, QgsRasterLayer):
            self.iface.messageBar().pushMessage("ผิดพลาด", "โปรดเลือก Input Raster Layer", level=Qgis.Critical)
            return
        if not os.path.exists(model_path):
            self.iface.messageBar().pushMessage("ผิดพลาด", f"ไม่พบไฟล์โมเดลที่: {model_path}", level=Qgis.Critical)
            return
        if not os.path.exists(python_path):
            self.iface.messageBar().pushMessage("ผิดพลาด", f"ไม่พบ Python executable ที่: {python_path}", level=Qgis.Critical)
            return

        self.label_status.setText("Status: กำลังเรียกใช้สคริปต์ภายนอก...")
        self.progressBar.setValue(0)

        self.task = QgsTask.fromFunction(
            'External Tree Detection',
            run_external_script,
            on_finished=self.processing_finished,
            python_path=python_path,
            script_path=os.path.join(os.path.dirname(__file__), 'external_processor.py'),
            input_raster=raster_layer.source(),
            model_path=model_path,
            confidence=confidence,
            iou=iou
        )
        self.task.progressChanged.connect(self.progressBar.setValue)
        QgsApplication.taskManager().addTask(self.task)

    def processing_finished(self, exception, result=None):
        self.progressBar.setValue(100)
        if exception:
            self.iface.messageBar().pushMessage("ผิดพลาด", f"Task failed: {exception}", level=Qgis.Critical)
            self.label_status.setText("Status: Error")
            return

        if result is None or not result['success']:
            error_msg = result.get('error', 'Unknown error in external script.') if result else 'Task did not return a result.'
            self.iface.messageBar().pushMessage("ผิดพลาด", f"การประมวลผลล้มเหลว: {error_msg}", level=Qgis.Critical)
            self.label_status.setText("Status: Failed")
            return
        
        self.label_status.setText("Status: กำลังสร้าง Layer ผลลัพธ์...")
        detections = result.get('detections', [])
        self.display_results(detections)

    def display_results(self, detections):
        if not detections:
            self.iface.messageBar().pushMessage("Info", "ไม่พบต้นไม้ในพื้นที่ที่เลือก")
            self.label_status.setText("Status: Finished (No Detections)")
            return

        source_crs = self.mMapLayerComboBox.currentLayer().crs()
        vl = QgsVectorLayer(f"Point?crs={source_crs.authid()}", "Detections", "memory")
        provider = vl.dataProvider()
        provider.addAttributes([
            QgsField("confidence", QVariant.Double), 
            QgsField("class", QVariant.String)
        ])
        vl.updateFields()

        for det in detections:
            feature = QgsFeature()
            coords = det['geometry']['coordinates']
            point = QgsPointXY(coords[0], coords[1])
            geom = QgsGeometry.fromPointXY(point)
            
            feature.setGeometry(geom)
            feature.setAttributes([det['properties']['confidence'], det['properties']['class']])
            provider.addFeature(feature)
        
        vl.updateExtents()
        QgsProject.instance().addMapLayer(vl)
        self.iface.messageBar().pushMessage("สำเร็จ", "การตรวจจับเสร็จสิ้นและเพิ่ม Layer ใหม่แล้ว", level=Qgis.Success)
        self.label_status.setText(f"Status: Finished! Found {len(detections)} trees.")

    def closingPlugin(self):
        if self.task and self.task.isRunning():
            self.task.cancel()