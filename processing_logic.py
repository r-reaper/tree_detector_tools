from qgis.core import QgsMessageLog, Qgis

def run_detection_on_array(task, model, image_array, transform, crs_wkt, conf_threshold=0.5, iou_threshold=0.4, tile_size=640, overlap=100):
    """
    Runs YOLO detection on a numpy array.
    This function is designed to be run in a QgsTask background thread.
    Returns a tuple: (success, data or error_message)
    """
    try:
        import numpy as np
        import cv2
        from ultralytics import YOLO
        import torch
        import torchvision.ops as ops
    except ImportError as e:
        QgsMessageLog.logMessage(f"Dependency error inside task: {e}", "TreeDetector", Qgis.Critical)
        return (False, f"Dependency error: {e}")

    try:
        QgsMessageLog.logMessage("Starting detection task in background.", "TreeDetector", Qgis.Info)
        height, width = image_array.shape[1], image_array.shape[2]
        
        all_detections = []
        
        num_tiles_y = len(range(0, height, tile_size - overlap))
        num_tiles_x = len(range(0, width, tile_size - overlap))
        total_tiles = num_tiles_y * num_tiles_x if num_tiles_y > 0 and num_tiles_x > 0 else 1
        processed_tiles = 0
        QgsMessageLog.logMessage(f"Processing {total_tiles} tiles...", "TreeDetector", Qgis.Info)

        for y in range(0, height, tile_size - overlap):
            for x in range(0, width, tile_size - overlap):
                if task.isCanceled():
                    return (False, "Task Canceled")
                
                y_end = min(y + tile_size, height)
                x_end = min(x + tile_size, width)
                
                tile_np = image_array[:, y:y_end, x:x_end]
                
                padded_tile = np.zeros((image_array.shape[0], tile_size, tile_size), dtype=tile_np.dtype)
                padded_tile[:, :tile_np.shape[1], :tile_np.shape[2]] = tile_np
                
                processed_tile = process_for_yolo(padded_tile)

                results = model(processed_tile, verbose=False)
                
                for r in results:
                    for box in r.boxes:
                        if box.conf[0] < conf_threshold:
                            continue
                        x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                        abs_x1, abs_y1 = x + x1, y + y1
                        abs_x2, abs_y2 = x + x2, y + y2
                        geo_x1, geo_y1 = transform * (abs_x1, abs_y1)
                        geo_x2, geo_y2 = transform * (abs_x2, abs_y2)

                        all_detections.append({
                            'geo_bbox': [geo_x1, geo_y1, geo_x2, geo_y2],
                            'confidence': float(box.conf[0]),
                            'class': model.names[int(box.cls[0])]
                        })
                
                processed_tiles += 1
                if total_tiles > 0:
                    task.setProgress((processed_tiles / total_tiles) * 100)

        if not all_detections:
            return (True, [])
            
        boxes = torch.tensor([d['geo_bbox'] for d in all_detections], dtype=torch.float)
        scores = torch.tensor([d['confidence'] for d in all_detections], dtype=torch.float)
        keep_indices = ops.nms(boxes, scores, iou_threshold)

        final_detections = [all_detections[i] for i in keep_indices]
        QgsMessageLog.logMessage(f"Finished. Found {len(final_detections)} detections after NMS.", "TreeDetector", Qgis.Info)
        return (True, final_detections)

    except Exception as e:
        QgsMessageLog.logMessage(f"An exception occurred in the detection task: {e}", "TreeDetector", Qgis.Critical)
        import traceback
        traceback.print_exc()
        return (False, str(e))

def load_yolo_model(model_path):
    from ultralytics import YOLO
    try:
        model = YOLO(model_path)
        return model
    except Exception as e:
        QgsMessageLog.logMessage(f"Error loading YOLO model: {e}", "TreeDetector", Qgis.Critical)
        return None

def process_for_yolo(image_np):
    import cv2
    import numpy as np
    img = image_np.transpose(1, 2, 0)
    
    if img.shape[2] > 3:
        img = img[:, :, :3]
        
    if len(img.shape) == 3 and img.shape[2] == 3:
        img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)

    if img.dtype != np.uint8:
        max_val = np.max(img)
        if max_val > 0:
             img = (img / max_val * 255).astype(np.uint8)
        else:
             img = img.astype(np.uint8)
    
    return img