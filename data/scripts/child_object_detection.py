"""
AURA Script: RPi Camera Module 3 & RPi CPU Inference
=====================================================
Uses the generic camera library to capture a frame and the generic
inference function to execute object detection on the RPi CPU.
"""
from __future__ import annotations
import sys
import os
from pathlib import Path
import json
import numpy as np

# Ensure project root is in path for standalone execution
project_root = Path(__file__).resolve().parents[2]
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from aura_hw import execute_inference, load_model, get_model_classes
from hardware.sensors.camera.library import Camera, take_photo

CONF_THRESHOLD = float(os.environ.get("AURA_CONF_THRESHOLD", 0.3))
CLASSES = []  # Loaded dynamically from model or classes.json

# Thresholds for 'person' class size classification
SIZE_THRESHOLD_X_REL = 0.1   # Threshold for relative box area (w * h)
SIZE_THRESHOLD_X_ABS = 40000 # Threshold for absolute box area in pixels (e.g., 200x200)

def load_classes_from_json(json_path: str | Path) -> list[str]:
    """Load class names from a JSON file (either list or dictionary mapping index to name)."""
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                return [str(x) for x in data]
            elif isinstance(data, dict):
                try:
                    sorted_keys = sorted(data.keys(), key=lambda x: int(x))
                    return [str(data[k]) for k in sorted_keys]
                except ValueError:
                    return [str(data[k]) for k in sorted(data.keys())]
    except Exception:
        pass
    return []

def pre_inference(raw_input) -> np.ndarray:
    """Pass-through function. The raw captured frame is sent directly to execute_inference()
    and resolved dynamically by the loaded model's backend library."""
    return raw_input

def post_inference(raw_output) -> dict[str, int]:
    """Parse model raw output tensor and return count of each detected class."""
    counts = {}
    outputs = list(raw_output.values())[0] if isinstance(raw_output, dict) else raw_output
    if outputs is None or len(outputs) == 0:
        return counts
    
    classes = get_model_classes()
    if not classes:
        classes = CLASSES

    for box in outputs[0].T:
        scores = box[4:]
        class_id = int(np.argmax(scores))
        confidence = float(scores[class_id])
        if confidence < CONF_THRESHOLD:
            continue
        class_name = classes[class_id] if class_id < len(classes) else str(class_id)
        if "/" in class_name:
            class_name = class_name.split("/")[-1]
            
        if class_name == "person":
            w = float(box[2])
            h = float(box[3])
            size = w * h
            is_relative = (w <= 1.0 and h <= 1.0)
            threshold_x = SIZE_THRESHOLD_X_REL if is_relative else SIZE_THRESHOLD_X_ABS
            if size < threshold_x:
                class_name = "baby"
            else:
                class_name = "adult"
                
        counts[class_name] = counts.get(class_name, 0) + 1
    return counts

def run(raw_input=None, classes_json_path=None) -> dict[str, int]:
    """
    Main execution script entrypoint.
    Captures a photo using the generic camera library if raw_input is not provided,
    preprocesses the image, performs inference, and parses the outputs.
    """
    global CLASSES
    
    # 1. Load classes from explicitly passed path if provided
    if classes_json_path:
        loaded = load_classes_from_json(classes_json_path)
        if loaded:
            CLASSES = loaded
            
    # 2. If CLASSES is still empty, and we don't have model classes from backend, try to auto-discover classes.json
    if not CLASSES and not get_model_classes():
        auto_paths = [
            os.environ.get("AURA_CLASSES_JSON"),
            # Agent runtime paths (inside Docker, where /tmp/aura is mapped to ./data)
            Path("/tmp/aura/classes.json"),
        ]
        for path_str in auto_paths:
            if path_str:
                path = Path(path_str)
                if path.exists():
                    loaded = load_classes_from_json(path)
                    if loaded:
                        CLASSES = loaded
                        break

    # 3. Capture image from the generic camera library
    frame = raw_input if raw_input is not None else take_photo()
    
    # 4. Run preprocessing
    model_input = pre_inference(frame)
    
    # 5. Execute inference using the generic runtime function
    model_output = execute_inference(model_input)
    
    # 6. Parse detections
    return post_inference(model_output)

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Run Camera Inference")
    parser.add_argument("-m", "--model", required=True, help="Path to the compiled model file")
    parser.add_argument("-c", "--classes", help="Path to the classes JSON file")
    args = parser.parse_args()
    
    # Resolve classes path
    classes_json = args.classes
    if not classes_json and args.model:
        # Check if there is a classes.json in the same directory as the model
        model_dir = Path(args.model).parent
        possible_classes = model_dir / "classes.json"
        if possible_classes.exists():
            classes_json = str(possible_classes)

    class_names = None
    if classes_json:
        class_names = load_classes_from_json(classes_json)
        print(f"Loaded class names: {class_names}")
    
    print("Loading model...")
    load_model(args.model, class_names=class_names)
    
    print("Capturing photo and executing inference...")
    try:
        results = run(classes_json_path=classes_json)
        print("\nDetections:")
        import json
        print(json.dumps(results, indent=2))
    except Exception as e:
        print(f"Execution failed: {e}")
