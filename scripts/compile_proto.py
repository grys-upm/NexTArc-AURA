"""
AURA Platform Proto Compiler.
==============================
Automatically installs/upgrades grpcio-tools, compiles gRPC and protobuf definitions
located in `shared/proto` into Python modules, and fixes absolute imports in generated
gRPC modules so they refer to the correct `shared.proto_gen` package path.
"""
import glob
import os
import re
import subprocess
import sys


def main() -> None:
    """
    Core execution method for compiling protobuf and gRPC files and fixing import paths.
    """
    print("Installing/upgrading grpcio-tools...")
    # Run pip to ensure the latest grpcio-tools package is installed
    subprocess.check_call([sys.executable, "-m", "pip", "install", "grpcio-tools"])

    print("Compiling proto files...")
    # Find all .proto files in shared/proto
    proto_files = glob.glob("shared/proto/*.proto")
    if not proto_files:
        print("No proto files found!")
        sys.exit(1)

    # Construct the protoc command line arguments
    cmd = [
        sys.executable, "-m", "grpc_tools.protoc",
        "-I", "shared/proto",
        "--python_out=shared/proto_gen",
        "--grpc_python_out=shared/proto_gen"
    ] + proto_files

    print("Running command:", " ".join(cmd))
    subprocess.check_call(cmd)

    print("Fixing generated imports...")
    # grpcio-tools compiles imports with relative naming, which breaks absolute imports in nested packages.
    # We locate all generated _pb2_grpc.py files to correct their import lines.
    grpc_files = glob.glob("shared/proto_gen/*_pb2_grpc.py")
    for filepath in grpc_files:
        print(f"Fixing imports in: {filepath}")
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()

        # Replace 'import xxx_pb2 as xxx__pb2' with 'from shared.proto_gen import xxx_pb2 as xxx__pb2'
        # and 'import xxx_pb2' with 'from shared.proto_gen import xxx_pb2'
        new_content = re.sub(
            r"^import\s+([a-zA-Z0-9_]+_pb2)",
            r"from shared.proto_gen import \1",
            content,
            flags=re.MULTILINE
        )
        
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(new_content)

    print("Proto compilation successful!")


if __name__ == "__main__":
    main()
