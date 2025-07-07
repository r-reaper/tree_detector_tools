import os
import tempfile
import subprocess
import json
from qgis.PyQt.QtWidgets import QDialog, QLineEdit, QPushButton, QFileDialog
from qgis.PyQt.QtCore import QVariant, Qt
from qgis.core import (QgsProject, QgsVectorLayer, QgsField, QgsFeature, 
                       QgsGeometry, QgsPointXY, QgsRasterLayer, QgsWkbTypes,
                       QgsTask, QgsApplication, QgsMessageLog, Qgis,
                       QgsMapLayerProxyModel)
from qgis.gui import QgsMapLayerComboBox, QgsFileWidget

from .ui_tree_detector_tools_dialog_base import Ui_TreeDetectorDialogBase

def run_external_script(task, python_path, script_path, input_raster, model_path, confidence, iou):

    task.setProgress(10)
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
    
    try:
        process = subprocess.run(
            command, 
            capture_output=True, 
            text=True, 
            check=True, 
            encoding='utf-8',
            env=env
        )
        QgsMessageLog.logMessage(f"External script stdout:\n{process.stdout}", "TreeDetector", Qgis.Info)
        task.setProgress(90)
        detections = json.loads(process.stdout)
        return {'success': True, 'detections': detections}
    except subprocess.CalledProcessError as e:
        error_message = f"External script failed with exit code {e.returncode}.\nStderr: {e.stderr}"
        QgsMessageLog.logMessage(error_message, "TreeDetector", Qgis.Critical)
        return {'success': False, 'error': error_message}
    except json.JSONDecodeError as e:
        error_message = f"Failed to parse JSON from script output.\nError: {e}\nOutput: {process.stdout}"
        QgsMessageLog.logMessage(error_message, "TreeDetector", Qgis.Critical)
        return {'success': False, 'error': error_message}
    except Exception as e:
        QgsMessageLog.logMessage(f"An unexpected error occurred: {e}", "TreeDetector", Qgis.Critical)
        return {'success': False, 'error': str(e)}


class TreeDetectorDialog(QDialog, Ui_TreeDetectorDialogBase):
    def __init__(self, iface, parent=None):
        super(TreeDetectorDialog, self).__init__(parent)
        self.iface = iface
        self.setupUi(self)

        self.mMapLayerComboBox.setFilters(QgsMapLayerProxyModel.RasterLayer)
        self.mFileWidget_model.setFilter("YOLO Model (*.pt)")
        
        # *** FIX: Create a custom file selector to handle symlinks on macOS ***
        self.python_path_edit = QLineEdit()
        self.python_path_button = QPushButton("...")
        self.python_path_button.clicked.connect(self.select_python_path)
        self.python_path_layout.setContentsMargins(0,0,0,0)
        self.python_path_layout.addWidget(self.python_path_edit)
        self.python_path_layout.addWidget(self.python_path_button)

        self.btn_start_detection.clicked.connect(self.start_external_process)
        self.button_box.rejected.connect(self.reject)
        
        self.task = None

    def select_python_path(self):
        # Get the last used directory if available
        start_dir = os.path.dirname(self.python_path_edit.text()) if self.python_path_edit.text() else os.path.expanduser("~")

        dialog = QFileDialog(self, "Select Python Executable", start_dir)
        dialog.setFileMode(QFileDialog.ExistingFile)
        dialog.setOption(QFileDialog.DontResolveSymlinks) # This is the key option
        
        if dialog.exec_():
            selected_file = dialog.selectedFiles()[0]
            self.python_path_edit.setText(selected_file)

    def start_external_process(self):
        raster_layer = self.mMapLayerComboBox.currentLayer()
        model_path = self.mFileWidget_model.filePath()
        python_path = self.python_path_edit.text() # Read from the custom line edit
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
        QgsApplication.taskManager().addTask(self.task)

    def processing_finished(self, exception, result=None):
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
        self.progressBar.setValue(100)
        
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