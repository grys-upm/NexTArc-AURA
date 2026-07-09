# How to Create a Custom Inference Script

In the AURA Platform, an **Inference Script** is a user-defined Python module (`.py`) uploaded via the web console. The script defines how to preprocess raw inputs, run the neural network, and postprocess the results on the edge device.

The Edge Runtime dynamically loads this script and invokes its entrypoint for every incoming camera frame or sensory input.

---

## 1. The Script structure

Every inference script must implement the following components:

1. **`pre_inference(raw_input)`**: Processes the raw system input (e.g. OpenCV image frame, NumPy array, or JSON string) and transforms it into the format expected by the model.
2. **`post_inference(raw_output)`**: Parses the raw model outputs (typically a collection of PyTorch or ONNX tensors) into a structured JSON serializable list of dictionaries.
3. **`run(raw_input)`**: The main execution entrypoint. This function is invoked periodically by the AURA agent loop.
4. **`execute_inference()` function**: Imported from the special virtual library `aura_hw`, this function automatically executes the loaded model on the active NPU/CPU accelerator backend.

---

## 2. Example: Object Detection Script

Below is a complete, production-ready template for a YOLO object detection script obtaining the raw images from a Camera Sensor:

```python
"""
AURA Script: Camera Module & Inference
=====================================================
Uses the generic camera library to capture a frame and the generic
inference function to execute object detection.
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

CONF_THRESHOLD = float(os.environ.get("AURA_CONF_THRESHOLD", 0.2))
CLASSES = []  # Loaded dynamically from model or classes.json

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

```

---

## 3. Available Generic Libraries

AURA provides several generic hardware proxy libraries located under the `hardware/` package. These proxies abstract the underlying physical or simulated drivers (configured in `components_config.yaml`), allowing you to write portable inference scripts that run seamlessly on different edge configurations.

---

## 4. Uploading and deploying scripts

Once your script is ready:
1. Save it locally as a standard Python file (e.g. `detect_people.py`).
2. Open the **AURA Web Management Console**.
3. Navigate to **Scripts** and click **Upload Script**.
4. Upload your file, give it a name and version (e.g. `v1.0.0`), and save.
5. You can now select this script during the **New Deployment** creation flow alongside your target compiled model. The platform will automatically bundle and deploy it to the selected device.
