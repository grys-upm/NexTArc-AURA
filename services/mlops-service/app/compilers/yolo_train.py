"""YOLO Dataset Preparation and Training Pipeline script.

This script parses training configurations, partitions images into training, validation,
and test subsets, formats the YOLO yaml dataset configuration, and triggers Ultralytics
YOLOv8/v10/v11 training runs using PyTorch on CPU or GPU targets.
"""
import argparse
import os
import random
import json
from typing import List, Dict, Any

try:
    import torch
    from ultralytics import YOLO
except ImportError as e:
    import traceback
    print("\n" + "=" * 80)
    print(f"ERROR: Failed to import torch or ultralytics: {e}")
    traceback.print_exc()
    print("\nPlease install them before running this training pipeline:")
    print("  pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121")
    print("  pip install ultralytics")
    print("=" * 80 + "\n")
    import sys
    sys.exit(1)

def parse_arguments() -> argparse.Namespace:
    """Parses command-line arguments for the dataset setup and training pipeline.

    Returns:
        Argparse Namespace containing parsed arguments.
    """
    parser = argparse.ArgumentParser(description="YOLO Dataset Preparer and Trainer")
    
    # --- Dataset Preparation Arguments ---
    parser.add_argument('--data_dir', type=str, default=None, 
                        help='Base directory to load images. If provided, generates a new dataset split and config.')
    parser.add_argument('--test_split', type=float, help='Percentage of images to split into the test set', default=0.2)
    parser.add_argument('--val_split', type=float, help='Percentage of images to split into the val set', default=0.1)
    parser.add_argument('--num_classes', type=int, help='Specify the number of classes if classes json does not exist', default=1)
    parser.add_argument("--onnx_config",  action='store_true', help="Create a Split and Config for onnx export (limits to 300 images)")

    # --- Original Dataset and Model Configuration ---
    parser.add_argument("--config", type=str, default="config.yaml", 
                        help="The dataset config file (used if --data_dir is not provided)")
    parser.add_argument("--init_model", type=str, default="yolo11n.pt", help="The pre-trained model weights")

    # --- Training Parameters ---
    parser.add_argument("--name", type=str, default="yolo", help="Save dir")
    parser.add_argument("--epochs", type=int, default=20, help="Number of training epochs")
    parser.add_argument("--device", type=str, default="0", help="Device training index (e.g. '0' for GPU or 'cpu')")
    parser.add_argument("--gpu_percent", type=float, default=0.9, help="How much of the GPU RAM to use")
    
    # --- Operation Mode Flags ---
    parser.add_argument("--resume_training",  action='store_true', help="Resume training of a model")
    parser.add_argument("--val_model",  action='store_true', help="Validate the model only")
    
    # --- Model Configuration ---
    parser.add_argument("--image_size", type=str, default="640x640",
                        help="Image size as width height (default: 640x640)")

    return parser.parse_args()

def prepare_dataset(args: argparse.Namespace) -> str | None:
    """Discovers images, splits them into train/val/test sets, and generates a YOLO YAML config.

    Args:
        args: Command-line configuration settings.

    Returns:
        The file path to the generated YAML configuration, or None if validation fails.
    """
    actual_data_dir = args.data_dir
    if not os.path.exists(os.path.join(args.data_dir, "classes.json")):
        for root, dirs, files in os.walk(args.data_dir):
            if "classes.json" in files:
                actual_data_dir = root
                break

    print(f"--- Starting Dataset Preparation from {actual_data_dir} ---")
    
    img_input_root_dir: str = os.path.join(actual_data_dir, "images")
    all_img_paths: List[str] = []
    
    if not os.path.exists(img_input_root_dir):
        print(f"Error: Images directory not found at {img_input_root_dir}")
        return None

    for root, _, files in os.walk(img_input_root_dir):
        if len(files) == 0:
            continue
        for file in files:
            if file.lower().endswith(('.jpg', '.jpeg', '.png', '.bmp', '.webp')):
                file_path: str = os.path.join(root, file)
                relative_path: str = file_path.replace(img_input_root_dir, "./images").replace('\\', '/')
                all_img_paths.append(relative_path + '\n')

    if not all_img_paths:
        print(f"Error: No images found in {img_input_root_dir}")
        return None

    random.shuffle(all_img_paths)
    file_suffix: str = "_onnx" if args.onnx_config else ""
    total_images: int = len(all_img_paths)
    test_num: int = int(args.test_split * total_images)
    val_num: int = int(args.val_split * total_images)

    test_filepath: str = os.path.join(actual_data_dir, f"test{file_suffix}.txt")
    val_filepath: str = os.path.join(actual_data_dir, f"val{file_suffix}.txt")
    train_filepath: str = os.path.join(actual_data_dir, f"train{file_suffix}.txt")

    test_num = min(test_num, len(all_img_paths))
    test_images: List[str] = [all_img_paths.pop() for _ in range(test_num)]
    
    val_num = min(val_num, len(all_img_paths))
    val_images: List[str] = [all_img_paths.pop() for _ in range(val_num)]

    if args.onnx_config:
        test_images = test_images[:300]
        val_images = val_images[:300]
        all_img_paths = all_img_paths[:300]

    with open(test_filepath, 'w') as f:
        f.writelines(test_images)
    with open(val_filepath, 'w') as f:
        f.writelines(val_images)
    with open(train_filepath, 'w') as f:
        f.writelines(all_img_paths)

    try:
        class_dict_filepath: str = os.path.join(actual_data_dir, "classes.json")
        with open(class_dict_filepath) as f:
            d: Dict[str, Any] = json.load(f)
            num_classes: int = len(list(d.keys()))
    except Exception as e:
        print(f"Error: No classes.json file found at {actual_data_dir}, please define!")
        print(e)
        return None

    base_dir: str = os.path.basename(os.path.normpath(actual_data_dir))
    parent_dir: str = os.path.dirname(os.path.normpath(actual_data_dir))
    config_dir: str = os.path.join(os.path.dirname(os.path.normpath(args.data_dir)), "configs")
    os.makedirs(config_dir, exist_ok=True)
    
    yaml_filename: str = os.path.join(config_dir, f"{base_dir}{file_suffix}_config.yaml")

    with open(yaml_filename, 'w') as f:
        f.write(f"# Train images - Path to training dataset split\n")
        f.write(f"train: {train_filepath.replace('\\', '/')}\n\n")
        f.write(f"# Validation images - Path to validation dataset split\n")
        f.write(f"val: {val_filepath.replace('\\', '/')}\n\n")
        f.write(f"# Test images - Path to test dataset split\n")
        f.write(f"test: {test_filepath.replace('\\', '/')}\n\n")
        f.write(f"# Number of classes - Total object classes in dataset\n")
        f.write(f"nc: {str(num_classes)}\n\n")
        f.write(f"# Class names - List of all object class labels\n")
        f.write(f"names: {list(d.keys())}\n")

    print(f"--- Dataset Prepared! Config saved to: {yaml_filename} ---\n")
    return yaml_filename

def main() -> None:
    """Orchestrates GPU environment validation, dataset generation and model training."""
    args = parse_arguments()

    # 1. GPU / CUDA Diagnostics
    cuda_available = torch.cuda.is_available()
    print(f"\n--- GPU/CUDA Diagnostics ---")
    print(f"PyTorch Version: {torch.__version__}")
    print(f"CUDA Available: {cuda_available}")
    if cuda_available:
        print(f"CUDA Device Count: {torch.cuda.device_count()}")
        print(f"Current Device Name: {torch.cuda.get_device_name(0)}")
    else:
        print("WARNING: CUDA is NOT available to PyTorch.")
        print("Training will execute on the CPU. If you have an NVIDIA GPU, make sure you have installed")
        print("the CUDA-compatible PyTorch wheels.")
    print("-" * 28 + "\n")

    # Resolve training device
    device = args.device
    if not cuda_available:
        if device != "cpu":
            print(f"Requested device '{device}' but CUDA is not available. Falling back to 'cpu'.")
            device = "cpu"
    else:
        try:
            device = int(device)
        except ValueError:
            pass

    # 2. Dataset Preparation Phase
    active_config = args.config
    if args.data_dir:
        generated_config = prepare_dataset(args)
        if generated_config:
            active_config = generated_config
        else:
            print("Dataset preparation failed. Exiting.")
            return

    # 3. Model Initialization Phase
    init_model = args.init_model
    if not os.path.exists(init_model):
        basename = os.path.basename(init_model)
        if basename.lower().startswith("yolov10"):
            init_model = "yolo10" + basename[7:]
        elif basename.lower().startswith("yolov11"):
            init_model = "yolo11" + basename[7:]
    
    print(f"Loading model: {init_model}")
    model = YOLO(init_model)
    image_h, image_w = map(int, args.image_size.split('x'))
    image_size = max(image_h, image_w)
    print(f"Image Size: {image_size}")

    project_dir = "run"

    # 4. Execution Phase (Train or Validate)
    if not args.val_model:
        print(f"Starting training with config: {active_config} on device: {device}")
        print("[INFO] Epoch progress will be logged at the end of each epoch. Please wait...")
        _ = model.train(data=active_config, 
                        epochs=args.epochs, 
                        imgsz=image_size, 
                        save=True,
                        device=device, 
                        name=args.name, 
                        batch=args.gpu_percent, 
                        resume=args.resume_training,
                        cache=False, 
                        project=project_dir, 
                        workers=0)
                              
    elif args.val_model:
        print(f"Starting validation for project: {args.name}")
        _ = model.val(name=args.name, project=project_dir)

if __name__ == "__main__":
    main()
