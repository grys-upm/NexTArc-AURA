#!/usr/bin/env python3
import os
import sys
import subprocess
import base64
import urllib.request
import urllib.error
import re
import psycopg2
from pymongo import MongoClient
from pathlib import Path

# ANSI colors for styling
BLUE = "\033[38;5;39m"
CYAN = "\033[38;5;86m"
GREEN = "\033[38;5;78m"
YELLOW = "\033[38;5;221m"
MAGENTA = "\033[38;5;213m"
RED = "\033[38;5;196m"
BOLD = "\033[1m"
RESET = "\033[0m"

TABLE_DESCRIPTIONS = {
    "devices": "Represents hardware nodes executing inference and monitoring.",
    "datasets": "Stores information about uploaded datasets for training.",
    "dataset_versions": "Represents specific versioned artifacts of a dataset.",
    "models": "Contains metadata of both original PyTorch models (.pt) and compiled models (.hef).",
    "model_compilations": "Tracks individual compilation jobs for various hardware types.",
    "scripts": "Inference processing scripts (pre-processing or post-processing).",
    "deployments": "Join table that orchestrates the deployment of a model and a script on an edge device."
}

COLUMN_DESCRIPTIONS = {
    "id": "Unique identifier (Primary Key)",
    "name": "Descriptive name of the entity",
    "hardware_type": "Hardware target architecture (e.g., hailo8, hailo8l, jetson_orin_nano)",
    "description": "Additional details or notes",
    "status": "Current operational status",
    "sensors": "Configured sensors",
    "actuators": "Configured actuators",
    "others": "Other hardware parameters or metadata",
    "last_seen_at": "Timestamp of the last reported activity",
    "created_at": "Record creation timestamp",
    "dataset_id": "Associated dataset (Foreign Key)",
    "dataset_version_id": "Associated dataset version (Foreign Key)",
    "object_key": "Path/URI in the object storage",
    "sha256": "Verification hash of the artifact",
    "size_bytes": "File/folder size in bytes",
    "meta_info": "Additional metadata in JSON format",
    "version": "Semantic version or label",
    "source_key": "Path of original model in object storage",
    "source_sha256": "SHA256 of original model source file",
    "compiled_key": "Path of compiled model binary in object storage",
    "compiled_sha256": "SHA256 of compiled model binary",
    "compile_status": "Status of the compilation job",
    "compile_error": "Error details if compilation failed",
    "base_architecture": "Base YOLO model architecture",
    "epochs": "Number of epochs used in training",
    "input_size": "Inference input dimensions",
    "batch_size": "Batch size used during training/compilation",
    "model_id": "Associated model (Foreign Key)",
    "device_id": "Target edge device (Foreign Key)",
    "script_id": "Associated execution script (Foreign Key)",
    "script_key": "Path of the script in object storage",
    "script_sha256": "SHA256 of script source file",
    "language": "Inference execution programming language",
    "sent_at": "Timestamp of deployment message dispatch",
    "running_at": "Timestamp of deployment confirmation",
    "error_msg": "Deployment execution error description"
}

def escape_html(text: str) -> str:
    """Escapes HTML special characters for Graphviz HTML labels."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")

def get_project_root() -> Path:
    """Returns the absolute path to the project root directory."""
    cwd = Path.cwd()
    if (cwd / "infra").exists() and (cwd / "services").exists():
        return cwd
    return Path(__file__).resolve().parent.parent

def load_env_file(filepath: Path) -> None:
    """Loads environment variables manually from the given file path."""
    if filepath.exists():
        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    parts = line.split("=", 1)
                    if len(parts) == 2:
                        key, val = parts
                        os.environ[key.strip()] = val.strip()

def get_postgres_connection():
    db_user = os.getenv("POSTGRES_USER", "aura")
    db_password = os.getenv("POSTGRES_PASSWORD", "aura_dev")
    db_name = os.getenv("POSTGRES_DB", "aura")
    
    hosts = ["localhost", "postgres", "127.0.0.1"]
    last_err = None
    for host in hosts:
        try:
            conn = psycopg2.connect(
                dbname=db_name,
                user=db_user,
                password=db_password,
                host=host,
                port="5432",
                connect_timeout=3
            )
            return conn, host
        except Exception as e:
            last_err = e
    raise last_err

def get_mongo_connection():
    mongo_user = os.getenv("POSTGRES_USER", "aura")
    mongo_password = os.getenv("POSTGRES_PASSWORD", "aura_dev")
    mongo_db = "aura"
    
    hosts = ["localhost", "mongodb", "127.0.0.1"]
    last_err = None
    for host in hosts:
        try:
            mongo_uri = f"mongodb://{mongo_user}:{mongo_password}@{host}:27017/{mongo_db}?authSource=admin"
            client = MongoClient(mongo_uri, serverSelectionTimeoutMS=2000)
            client.admin.command('ping')
            return client, host
        except Exception as e:
            last_err = e
    raise last_err

def fetch_postgres_metadata(conn):
    cursor = conn.cursor()
    
    # 1. Fetch tables
    cursor.execute("""
        SELECT table_name 
        FROM information_schema.tables 
        WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
        ORDER BY table_name;
    """)
    tables = [row[0] for row in cursor.fetchall()]
    
    # 2. Fetch columns for each table
    columns = {}
    for table in tables:
        cursor.execute("""
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = %s
            ORDER BY ordinal_position;
        """, (table,))
        columns[table] = cursor.fetchall()
        
    # 3. Fetch primary keys
    cursor.execute("""
        SELECT kcu.table_name, kcu.column_name
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
          ON tc.constraint_name = kcu.constraint_name
          AND tc.table_schema = kcu.table_schema
        WHERE tc.constraint_type = 'PRIMARY KEY' AND tc.table_schema = 'public';
    """)
    primary_keys = {}
    for table, col in cursor.fetchall():
        if table not in primary_keys:
            primary_keys[table] = []
        primary_keys[table].append(col)
        
    # 4. Fetch foreign keys
    cursor.execute("""
        SELECT
            tc.table_name AS source_table,
            kcu.column_name AS source_column,
            ccu.table_name AS target_table,
            ccu.column_name AS target_column
        FROM
            information_schema.table_constraints AS tc
            JOIN information_schema.key_column_usage AS kcu
              ON tc.constraint_name = kcu.constraint_name
              AND tc.table_schema = kcu.table_schema
            JOIN information_schema.constraint_column_usage AS ccu
              ON ccu.constraint_name = tc.constraint_name
              AND ccu.table_schema = tc.table_schema
        WHERE tc.constraint_type = 'FOREIGN KEY' AND tc.table_schema = 'public';
    """)
    foreign_keys = cursor.fetchall()
    
    cursor.close()
    return tables, columns, primary_keys, foreign_keys

def get_column_icon(name, is_pk=False, is_fk=False):
    if is_pk:
        return "🔑 "
    if is_fk:
        return "🔗 "
    
    name_lower = name.lower()
    if name_lower in ("name", "version", "title"):
        return "🏷️ "
    elif "description" in name_lower or "desc" in name_lower:
        return "📝 "
    elif "key" in name_lower or "path" in name_lower:
        return "📁 "
    elif "sha256" in name_lower or "hash" in name_lower or "md5" in name_lower:
        return "🔒 "
    elif "size" in name_lower or "bytes" in name_lower:
        return "💾 "
    elif "meta" in name_lower or "info" in name_lower:
        return "ℹ️ "
    elif "created" in name_lower or "updated" in name_lower or "time" in name_lower or "seen" in name_lower or "at" in name_lower:
        if "seen" in name_lower:
            return "🕒 "
        if "sent" in name_lower:
            return "📤 "
        if "running" in name_lower:
            return "🚀 "
        return "📅 "
    elif "hw" in name_lower or "hardware" in name_lower:
        return "⚙️ "
    elif "status" in name_lower:
        return "⚡ "
    elif "error" in name_lower or "err" in name_lower:
        return "❌ "
    elif "arch" in name_lower or "architecture" in name_lower:
        return "🧠 "
    elif "epoch" in name_lower:
        return "🔄 "
    elif "input" in name_lower:
        return "📐 "
    elif "batch" in name_lower:
        return "📦 "
    elif "sensor" in name_lower:
        return "📡 "
    elif "actuator" in name_lower:
        return "🔌 "
    elif "language" in name_lower:
        return "🌐 "
    elif name_lower == "others":
        return "📂 "
    return "🔹 "

def map_postgres_type_to_mermaid(pg_type):
    pg_type = pg_type.lower()
    if "uuid" in pg_type:
        return "uuid"
    if "character" in pg_type or "text" in pg_type:
        return "string"
    if "int" in pg_type or "serial" in pg_type:
        return "int"
    if "timestamp" in pg_type or "date" in pg_type or "time" in pg_type:
        return "timestamp"
    if "json" in pg_type:
        return "json"
    if "array" in pg_type or pg_type.startswith("_"):
        return "string_array"
    return pg_type.replace(" ", "_")

def get_mermaid_relationship_label(src_tbl, ref_table):
    if src_tbl == "dataset_versions" and ref_table == "datasets":
        return "contains"
    if src_tbl == "models" and ref_table == "dataset_versions":
        return "calibrates"
    if src_tbl == "models" and ref_table == "datasets":
        return "used by"
    if src_tbl == "model_compilations" and ref_table == "models":
        return "produces"
    if src_tbl == "deployments" and ref_table == "models":
        return "deployed"
    if src_tbl == "deployments" and ref_table == "devices":
        return "target"
    if src_tbl == "deployments" and ref_table == "scripts":
        return "executed by"
    return "references"

def generate_dot_code(tables, columns, primary_keys, foreign_keys):
    dot = []
    dot.append("digraph G {")
    dot.append('    graph [')
    dot.append('        pad="0.4",')
    dot.append('        nodesep="0.4",')
    dot.append('        ranksep="0.4",')
    dot.append('        bgcolor="#f8fafc",')
    dot.append('        label="AURA PLATFORM - DATABASE ER DIAGRAM",')
    dot.append('        labelloc="t",')
    dot.append('        fontname="Segoe UI,Arial,sans-serif",')
    dot.append('        fontsize="14",')
    dot.append('        fontcolor="#0f172a",')
    dot.append('        rankdir=TB,')
    dot.append('        splines=ortho')
    dot.append('    ];')
    dot.append('    node [')
    dot.append('        shape=plain,')
    dot.append('        fontname="Segoe UI,Arial,sans-serif",')
    dot.append('        fontsize="10",')
    dot.append('        fontcolor="#1e293b"')
    dot.append('    ];')
    dot.append('    edge [')
    dot.append('        color="#6366f1",')
    dot.append('        penwidth=2,')
    dot.append('        arrowsize=0.8,')
    dot.append('        fontname="Segoe UI,Arial,sans-serif",')
    dot.append('        fontsize="8",')
    dot.append('        fontcolor="#64748b"')
    dot.append('    ];')
    dot.append('')

    # Premium layout alignment constraints
    known_tables = set(tables)
    if "models" in known_tables and "datasets" in known_tables and "scripts" in known_tables:
        dot.append("    // --- MAIN HORIZONTAL ROWS ---")
        dot.append("    { rank=same; models; datasets; scripts; }")
        dot.append("")
        
    if "models" in known_tables and "model_compilations" in known_tables:
        dot.append("    subgraph cluster_col1 {")
        dot.append("        style=invis;")
        dot.append("        models;")
        dot.append("        model_compilations;")
        dot.append("        models -> model_compilations [style=invis];")
        dot.append("    }")
        
    if "datasets" in known_tables and "dataset_versions" in known_tables and "devices" in known_tables:
        dot.append("    subgraph cluster_col2 {")
        dot.append("        style=invis;")
        dot.append("        datasets;")
        dot.append("        dataset_versions;")
        dot.append("        devices;")
        dot.append("        datasets -> dataset_versions [style=invis];")
        dot.append("        dataset_versions -> devices [style=invis];")
        dot.append("    }")
        
    if "scripts" in known_tables and "deployments" in known_tables:
        dot.append("    subgraph cluster_col3 {")
        dot.append("        style=invis;")
        dot.append("        scripts;")
        dot.append("        deployments;")
        dot.append("        scripts -> deployments [style=invis];")
        dot.append("    }")
        dot.append("")
        
    if "models" in known_tables and "datasets" in known_tables and "scripts" in known_tables:
        dot.append("    // Alignment helper constraints")
        dot.append("    models -> datasets [style=invis];")
        dot.append("    datasets -> scripts [style=invis];")
        dot.append("")

    table_colors = {
        "datasets": "#d97706",
        "dataset_versions": "#d97706",
        "models": "#4f46e5",
        "model_compilations": "#4f46e5",
        "deployments": "#059669",
        "devices": "#0284c7",
        "scripts": "#7c3aed"
    }
    fallback_colors = ["#ec4899", "#8b5cf6", "#06b6d4", "#f43f5e", "#10b981", "#f59e0b", "#6366f1"]
    
    for i, table in enumerate(tables):
        color = table_colors.get(table, fallback_colors[i % len(fallback_colors)])
        subtitle = ""
        if table == "datasets":
            subtitle = " (Data Catalog)"
        elif table == "models":
            subtitle = " (AI Models)"
        elif table == "deployments":
            subtitle = " (Orchestration)"
        elif table == "devices":
            subtitle = " (IoT Edge Nodes)"
            
        dot.append(f'    // --- ENTITY: {table} ---')
        dot.append(f'    {table} [label=<<table border="0" cellborder="1" cellspacing="0" cellpadding="6" bgcolor="#ffffff" color="#cbd5e1" style="rounded">')
        dot.append(f'        <tr><td bgcolor="{color}" align="center" colspan="3"><font color="#ffffff"><b>{table}{subtitle}</b></font></td></tr>')
        
        table_cols = columns[table]
        table_pks = primary_keys.get(table, [])
        table_fks = {col: ref_table for src_tbl, col, ref_table, ref_col in foreign_keys if src_tbl == table}
        
        for col_name, col_type, is_nullable in table_cols:
            is_pk = col_name in table_pks
            is_fk = col_name in table_fks
            
            icon = get_column_icon(col_name, is_pk, is_fk)
            
            escaped_col_name = escape_html(col_name)
            escaped_col_type = escape_html(col_type)
            
            col_name_str = f"<b>{escaped_col_name}</b>" if (is_pk or is_fk) else escaped_col_name
            pk_fk_label = "<b>PK</b>" if is_pk else ("<b>FK</b>" if is_fk else "")
            
            port_attr = f' port="{escaped_col_name}"' if (is_pk or is_fk) else ''
            dot.append(f'        <tr><td{port_attr} align="left">{icon}{col_name_str}</td><td align="left"><i>{escaped_col_type}</i></td><td align="center">{pk_fk_label}</td></tr>')
            
        dot.append('    </table>>];')
        dot.append('')
        
    dot.append("    // --- Relationships / Edges ---")
    for src_tbl, col, ref_table, ref_col in foreign_keys:
        color = table_colors.get(ref_table, "#6366f1")
        style_attr = ""
        xlabel_attr = ""
        
        if src_tbl == "dataset_versions" and ref_table == "datasets":
            xlabel_attr = 'xlabel="contains", '
        elif src_tbl == "models" and ref_table == "dataset_versions":
            xlabel_attr = 'xlabel="calibrates", '
            style_attr = ', style=dashed'
        elif src_tbl == "models" and ref_table == "datasets":
            xlabel_attr = 'xlabel="trains", '
            style_attr = ', style=dashed'
        elif src_tbl == "model_compilations" and ref_table == "models":
            xlabel_attr = 'xlabel="produces", '
        elif src_tbl == "deployments" and ref_table == "models":
            xlabel_attr = 'xlabel="deployed", '
        elif src_tbl == "deployments" and ref_table == "devices":
            xlabel_attr = 'xlabel="target", '
        elif src_tbl == "deployments" and ref_table == "scripts":
            xlabel_attr = 'xlabel="executed by", '
            
        dot.append(f'    {ref_table} -> {src_tbl} [{xlabel_attr}color="{color}"{style_attr}];')

    dot.append("}")
    return "\n".join(dot)

def generate_mermaid_code(tables, columns, primary_keys, foreign_keys):
    mermaid = []
    mermaid.append("%%{init: {")
    mermaid.append('  "theme": "neutral",')
    mermaid.append('  "themeVariables": {')
    mermaid.append('    "fontFamily": "Segoe UI, system-ui, sans-serif",')
    mermaid.append('    "fontSize": "13px"')
    mermaid.append('  }')
    mermaid.append("}}%%")
    mermaid.append("erDiagram")
    
    for table in tables:
        mermaid.append(f"    {table} {{")
        table_cols = columns[table]
        table_pks = primary_keys.get(table, [])
        table_fks = {col: ref_table for src_tbl, col, ref_table, ref_col in foreign_keys if src_tbl == table}
        
        for col_name, col_type, is_nullable in table_cols:
            m_type = map_postgres_type_to_mermaid(col_type)
            is_pk = col_name in table_pks
            is_fk = col_name in table_fks
            
            pk_fk_suffix = ""
            if is_pk:
                pk_fk_suffix = " PK"
            elif is_fk:
                pk_fk_suffix = " FK"
                
            mermaid.append(f"        {m_type} {col_name}{pk_fk_suffix}")
        mermaid.append("    }")
        
    for src_tbl, col, ref_table, ref_col in foreign_keys:
        label = get_mermaid_relationship_label(src_tbl, ref_table)
        mermaid.append(f'    {ref_table} ||--o{{ {src_tbl} : "{label}"')
        
    return "\n".join(mermaid)

def find_grpc_contracts(proto_dir: Path):
    contracts = []
    if not proto_dir.exists():
        return contracts
    for filepath in sorted(proto_dir.glob("*.proto")):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
            package_match = re.search(r'package\s+([^;]+);', content)
            package_name = package_match.group(1).strip() if package_match else ""
            
            services = re.findall(r'service\s+(\w+)\s*\{', content)
            for service in services:
                description = ""
                comment_lines = []
                for line in content.splitlines():
                    line_strip = line.strip()
                    if line_strip.startswith("//"):
                        comment_lines.append(line_strip.lstrip("/").strip())
                    elif f"service {service}" in line:
                        description = " ".join(comment_lines)
                        break
                    else:
                        if not line_strip:
                            comment_lines = []
                if not description:
                    description = f"gRPC Service for {service} defined in {filepath.name}."
                contracts.append((filepath.name, description, f"{package_name}.{service}" if package_name else service))
        except Exception:
            pass
    return contracts

def print_header() -> None:
    try:
        if hasattr(sys.stdout, 'reconfigure'):
            sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass
    print(f"\n{BLUE}{BOLD}=== AURA PLATFORM - LIVE INFORMATION MODEL (COMBINED VIEWER) ==={RESET}\n")

def print_dynamic_entities(tables, columns, primary_keys, foreign_keys):
    print(f"{CYAN}{BOLD}1. MAIN RELATIONAL ENTITIES (POSTGRESQL & ORM/METADATA){RESET}")
    print("-" * 70)
    
    for table in tables:
        desc = TABLE_DESCRIPTIONS.get(table, "Dynamically discovered database table.")
        orm_path = "N/A"
        if table in ("devices", "datasets", "models", "scripts", "dataset_versions"):
            orm_path = f"registry-service/app/models/orm.py -> {table.rstrip('s').title()}"
        elif table == "deployments":
            orm_path = "edge-connector-service/app/models/orm.py -> Deployment"
        elif table == "model_compilations":
            orm_path = "registry-service/app/models/orm.py -> ModelCompilation"
            
        print(f"\n{GREEN}{BOLD}■ {table}{RESET}")
        print(f"  {BOLD}Description:{RESET} {desc}")
        print(f"  {BOLD}ORM Definition:{RESET} {BLUE}{orm_path}{RESET}")
        print(f"  {BOLD}Attributes / Columns:{RESET}")
        
        table_cols = columns[table]
        table_pks = primary_keys.get(table, [])
        table_fks = {col: ref_table for src_tbl, col, ref_table, ref_col in foreign_keys if src_tbl == table}
        
        for col_name, col_type, is_nullable in table_cols:
            is_pk = col_name in table_pks
            is_fk = col_name in table_fks
            
            type_label = col_type
            if is_pk:
                type_label += " (PK)"
            elif is_fk:
                type_label += " (FK)"
                
            if is_nullable == "YES":
                type_label += " (Null)"
                
            col_desc = COLUMN_DESCRIPTIONS.get(col_name, "Dynamically discovered column.")
            print(f"    - {YELLOW}{col_name:<25}{RESET} {type_label:<25} | {col_desc}")
        print("-" * 70)

def print_mongodb_entities(mongo_client, db_name):
    print(f"\n{CYAN}{BOLD}1.2 TELEMETRY & MONITORING ENTITIES (MONGODB){RESET}")
    print("-" * 70)
    try:
        db = mongo_client[db_name]
        collections = db.list_collection_names()
        if not collections:
            print("  No collections found in MongoDB.")
        for coll in collections:
            count = db[coll].count_documents({})
            print(f"\n{GREEN}{BOLD}■ {coll}{RESET} ({count} documents)")
            
            desc = "Dynamically discovered MongoDB collection."
            if coll == "device_states":
                desc = "Stores the current telemetry status for each device ID (upsert)."
            elif coll == "inference_results":
                desc = "Stores historical YOLO inference result records (append-only)."
            print(f"  {BOLD}Description:{RESET} {desc}")
            
            sample = db[coll].find_one()
            if sample:
                print(f"  {BOLD}Attributes / Fields:{RESET}")
                for key, val in sample.items():
                    val_type = type(val).__name__
                    print(f"    - {YELLOW}{key:<25}{RESET} {val_type:<25}")
            else:
                print("  (Empty collection - no sample document available to infer fields)")
    except Exception as e:
        print(f"  {RED}Error reading MongoDB info: {e}{RESET}")
    print("-" * 70)

def print_minio_mapping() -> None:
    print(f"\n{CYAN}{BOLD}2. FILE STORAGE (MINIO OBJECT STORAGE){RESET}")
    print("-" * 70)
    models_bucket = os.getenv("MINIO_BUCKET_MODELS", "models")
    scripts_bucket = os.getenv("MINIO_BUCKET_SCRIPTS", "scripts")
    compiled_bucket = os.getenv("MINIO_BUCKET_COMPILED", "compiled")
    datasets_bucket = os.getenv("MINIO_BUCKET_DATASETS", "datasets")
    
    mappings = [
        ("Original/versioned datasets", f"{datasets_bucket}/<dataset_id>/<version>/<file>"),
        ("Original PyTorch models (.pt)", f"{models_bucket}/<model_id>/source.pt"),
        ("Compiled models (.hef, etc.)", f"{compiled_bucket}/<model_id>/model.hef"),
        ("Inference scripts (.py)", f"{scripts_bucket}/<script_id>/script.py")
    ]
    for key, path in mappings:
        print(f"  * {BOLD}{key:<35}{RESET} -> {GREEN}{path}{RESET}")
    print("-" * 70)

def print_grpc_contracts(root_dir: Path) -> None:
    print(f"\n{CYAN}{BOLD}3. gRPC CONTRACTS (COMMUNICATION BETWEEN SERVICES){RESET}")
    print("-" * 70)
    proto_dir = root_dir / "shared" / "proto"
    contracts = find_grpc_contracts(proto_dir)
    for file, desc, package in contracts:
        print(f"  * {YELLOW}{file:<20}{RESET} [{BLUE}{package}{RESET}]")
        print(f"    {desc}")
    print("-" * 70)

def print_raw_sql(root_dir: Path) -> None:
    sql_path = root_dir / "infra" / "postgres" / "init.sql"
    print(f"\n{CYAN}{BOLD}4. DETAILED SQL SCHEMA (infra/postgres/init.sql){RESET}")
    print("-" * 70)
    if sql_path.exists():
        try:
            with open(sql_path, "r", encoding="utf-8") as f:
                content = f.read()
            for line in content.splitlines():
                if line.strip().startswith("--"):
                    print(f"\033[90m{line}{RESET}")
                elif "CREATE TABLE" in line or "CREATE INDEX" in line:
                    print(f"{BLUE}{BOLD}{line}{RESET}")
                elif "REFERENCES" in line or "PRIMARY KEY" in line or "FOREIGN KEY" in line:
                    print(f"{YELLOW}{line}{RESET}")
                else:
                    print(line)
        except Exception as e:
            print(f"{RED}Error reading SQL file: {e}{RESET}")
    else:
        print(f"{RED}SQL file not found at {sql_path}{RESET}")
    print("-" * 70)

def download_diagram_png(mermaid_code: str, output_path: Path) -> None:
    print(f"\n{CYAN}{BOLD}GENERATING MERMAID DIAGRAM IMAGE (via mermaid.ink)...{RESET}")
    print("-" * 70)
    try:
        graph_bytes = mermaid_code.encode("utf-8")
        base64_bytes = base64.urlsafe_b64encode(graph_bytes)
        base64_string = base64_bytes.decode("ascii")
        url = f"https://mermaid.ink/img/{base64_string}"
        
        print(f"Connecting to Mermaid API and downloading image...")
        req = urllib.request.Request(
            url, 
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        )
        with urllib.request.urlopen(req, timeout=15) as response:
            with open(output_path, "wb") as f:
                f.write(response.read())
        print(f"{GREEN}{BOLD}Success! Mermaid diagram image saved at:{RESET} {output_path.resolve()}")
    except urllib.error.URLError as e:
        print(f"{RED}Network error trying to download image: {e.reason}{RESET}")
    except Exception as e:
        print(f"{RED}Unexpected error generating PNG image: {e}{RESET}")
    print("-" * 70)

def compile_graphviz_diagram(dot_code: str, dot_path: Path, png_path: Path, svg_path: Path) -> None:
    print(f"\n{CYAN}{BOLD}COMPILING GRAPHVIZ DIAGRAM LOCALLY...{RESET}")
    print("-" * 70)
    print(f"Writing Graphviz DOT code to: {dot_path.resolve()}")
    try:
        with open(dot_path, "w", encoding="utf-8") as f:
            f.write(dot_code)
        
        print("Attempting to compile diagram using local Graphviz ('dot')...")
        subprocess.run(["dot", "-Tsvg", str(dot_path), "-o", str(svg_path)], check=True)
        print(f"Success! SVG diagram generated at: {svg_path.resolve()}")
        subprocess.run(["dot", "-Tpng", str(dot_path), "-o", str(png_path)], check=True)
        print(f"Success! PNG diagram generated at: {png_path.resolve()}")
    except (subprocess.SubprocessError, FileNotFoundError) as e:
        print(f"\n[!] WARNING: Graphviz 'dot' command is not available or failed: {e}")
        print("To generate the PNG/SVG automatically, install Graphviz and add it to your Windows PATH.")
    except Exception as e:
        print(f"{RED}Unexpected error compiling Graphviz diagram: {e}{RESET}")
    print("-" * 70)

def print_diagram(mermaid_code: str, dot_code: str, docs_dir: Path) -> None:
    print(f"\n{CYAN}{BOLD}ENTITY-RELATIONSHIP DIAGRAM (ASCII & MERMAID){RESET}")
    print("-" * 70)
    
    ascii_diagram = """
  +------------------+  1:N (used by)  +------------------+         +------------------+
  |      models      | <-------------- |     datasets     |         |     scripts      |
  +--------┬---------+                 +------------------+         +--------┬---------+
           |                                                                 |
           |                                                                 | 1:N (executed by)
           |                                                                 v
           |                           +------------------+         +------------------+
           |                           |     devices      | ------> |   deployments    |
           |                           +------------------+   1:N   +----^-------------+
           |                                                        (target) |
           |                                                                 |
           +-----------------------------------------------------------------+ 1:N (deployed)
"""
    print(f"{YELLOW}{BOLD}Conceptual Relationship Diagram:{RESET}")
    print(ascii_diagram)
    print("-" * 70)

    print(f"{GREEN}{BOLD}Mermaid.js Code:{RESET}")
    print(mermaid_code)
    print("-" * 70)
    
    docs_dir.mkdir(parents=True, exist_ok=True)
    mermaid_path = docs_dir / "model_diagram.mermaid"
    try:
        with open(mermaid_path, "w", encoding="utf-8") as f:
            f.write(mermaid_code)
        print(f"{BLUE}Mermaid diagram successfully exported to:{RESET} {mermaid_path.resolve()}")
    except Exception as e:
        print(f"{RED}Could not write .mermaid diagram to disk: {e}{RESET}")
        
    png_path = docs_dir / "model_diagram.png"
    download_diagram_png(mermaid_code, png_path)
    
    dot_path = docs_dir / "model_diagram_premium.dot"
    gv_png_path = docs_dir / "model_diagram_premium.png"
    gv_svg_path = docs_dir / "model_diagram_premium.svg"
    compile_graphviz_diagram(dot_code, dot_path, gv_png_path, gv_svg_path)

def main() -> None:
    if os.name == 'nt':
        import ctypes
        try:
            kernel32 = ctypes.windll.kernel32
            kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
        except Exception:
            pass

    print_header()
    root = get_project_root()
    load_env_file(root / ".env")
    
    print(f"Connecting to database...")
    try:
        pg_conn, pg_host = get_postgres_connection()
        print(f"{GREEN}Successfully connected to PostgreSQL on host: {pg_host}{RESET}")
    except Exception as e:
        print(f"{RED}Failed to connect to PostgreSQL: {e}{RESET}")
        print("Please check your .env settings and ensure the PostgreSQL Docker container is running.")
        sys.exit(1)
        
    mongo_client = None
    try:
        mongo_client, mongo_host = get_mongo_connection()
        print(f"{GREEN}Successfully connected to MongoDB on host: {mongo_host}{RESET}")
    except Exception as e:
        print(f"{YELLOW}Warning: Could not connect to MongoDB: {e}{RESET}")

    tables, columns, primary_keys, foreign_keys = fetch_postgres_metadata(pg_conn)
    pg_conn.close()

    dot_code = generate_dot_code(tables, columns, primary_keys, foreign_keys)
    mermaid_code = generate_mermaid_code(tables, columns, primary_keys, foreign_keys)
    
    docs_dir = root / "docs" / "images"
    
    if len(sys.argv) > 1:
        arg = sys.argv[1].lower()
        if arg == "--entities":
            print_dynamic_entities(tables, columns, primary_keys, foreign_keys)
            if mongo_client:
                print_mongodb_entities(mongo_client, "aura")
        elif arg == "--minio":
            print_minio_mapping()
        elif arg == "--grpc":
            print_grpc_contracts(root)
        elif arg == "--sql":
            print_raw_sql(root)
        elif arg == "--diagram":
            print_diagram(mermaid_code, dot_code, docs_dir)
        elif arg == "--png":
            download_diagram_png(mermaid_code, docs_dir / "model_diagram.png")
            compile_graphviz_diagram(dot_code, docs_dir / "model_diagram_premium.dot", docs_dir / "model_diagram_premium.png", docs_dir / "model_diagram_premium.svg")
        elif arg == "--help":
            print(f"Usage: python {sys.argv[0]} [option]")
            print("Options:")
            print("  --entities  Prints only the relational tables, columns, and MongoDB collections")
            print("  --minio     Prints only the MinIO key structure")
            print("  --grpc      Prints only the gRPC service definitions")
            print("  --sql       Prints the raw initialization SQL file")
            print("  --diagram   Shows the ASCII diagram, Mermaid code, and generates/compiles diagram files")
            print("  --png       Generates/downloads both diagram images (PNG/SVG) in docs/")
            print("  (without args)  Prints all information and generates all diagrams (.mermaid, .dot, .png, .svg)")
        else:
            print(f"{RED}Unrecognized option: {sys.argv[1]}{RESET}")
            print("Use --help to see available options.")
    else:
        print_dynamic_entities(tables, columns, primary_keys, foreign_keys)
        if mongo_client:
            print_mongodb_entities(mongo_client, "aura")
        print_minio_mapping()
        print_grpc_contracts(root)
        print_raw_sql(root)
        print_diagram(mermaid_code, dot_code, docs_dir)

    if mongo_client:
        mongo_client.close()

if __name__ == "__main__":
    main()
