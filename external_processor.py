import argparse
import json
import sys

def process_for_yolo(image_np, cv2, np):
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

def main(args):
    try:
        import numpy as np
        import cv2
        import rasterio
        from ultralytics import YOLO
        import torch
        import torchvision.ops as ops
        from shapely.geometry import box, mapping
    except ImportError as e:
        print(f"Error importing libraries: {e}", file=sys.stderr)
        sys.exit(1)

    model = YOLO(args.model)
    all_detections = []
    tile_size = 640
    overlap = 100

    with rasterio.open(args.input) as src:
        height, width = src.height, src.width
        transform = src.transform

        for y in range(0, height, tile_size - overlap):
            for x in range(0, width, tile_size - overlap):
                window = rasterio.windows.Window(x, y, tile_size, tile_size)
                tile_np = src.read(window=window)
                
                processed_tile = process_for_yolo(tile_np, cv2, np)
                results = model(processed_tile, verbose=False, conf=args.conf)
                
                for r in results:
                    for det_box in r.boxes:
                        x1, y1, x2, y2 = det_box.xyxy[0].cpu().numpy()
                        abs_x1, abs_y1 = x + x1, y + y1
                        abs_x2, abs_y2 = x + x2, y + y2
                        geo_x1, geo_y1 = transform * (abs_x1, abs_y1)
                        geo_x2, geo_y2 = transform * (abs_x2, abs_y2)

                        all_detections.append({
                            'geometry': box(geo_x1, min(geo_y1, geo_y2), geo_x2, max(geo_y1, geo_y2)),
                            'confidence': float(det_box.conf[0]),
                            'class': model.names[int(det_box.cls[0])]
                        })
    
    if not all_detections:
        final_detections = []
    else:
        boxes = torch.tensor([list(d['geometry'].bounds) for d in all_detections], dtype=torch.float)
        scores = torch.tensor([d['confidence'] for d in all_detections], dtype=torch.float)
        keep_indices = ops.nms(boxes, scores, args.iou)
        final_detections = [all_detections[i] for i in keep_indices]
    
    # *** FIX: Create a list of GeoJSON-like features and print it ***
    features = []
    for det in final_detections:
        center_point = det['geometry'].centroid
        features.append({
            'type': 'Feature',
            'geometry': mapping(center_point),
            'properties': {
                'confidence': det['confidence'],
                'class': det['class']
            }
        })

    # Print the final result as a JSON string to stdout
    print(json.dumps(features))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='YOLO Detection Script for QGIS Plugin')
    parser.add_argument('--input', required=True, help='Path to input raster file')
    parser.add_argument('--model', required=True, help='Path to YOLO model file')
    parser.add_argument('--conf', type=float, required=True, help='Confidence threshold')
    parser.add_argument('--iou', type=float, required=True, help='IoU threshold for NMS')
    
    args = parser.parse_args()
    main(args)