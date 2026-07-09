"""Sphinx configuration for AURA Platform documentation."""
import os
import sys

# ── Path setup ────────────────────────────────────────────────────────────────
_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))

sys.path.insert(0, _root)
sys.path.insert(0, os.path.dirname(__file__))


# ── Project info ──────────────────────────────────────────────────────────────
project   = "AURA Platform"
copyright = "2026, Estela Mora Barba"
author    = "Estela Mora Barba"
release   = "1.0"

# ── Extensions ────────────────────────────────────────────────────────────────
extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",        # Google / NumPy docstring styles
    "sphinx.ext.viewcode",        # [source] links
    "sphinx.ext.intersphinx",
    "sphinx.ext.todo",
    "myst_parser",                # Markdown support for .md files
]

# ── Autodoc mock imports ───────────────────────────────────────────────────────
# Packages not installed in the docs build environment are mocked so that
# autodoc can import the source modules and extract docstrings without errors.
autodoc_mock_imports = [
    "aiomqtt",
    "sqlalchemy",
    "grpc",
    "miniopy_async",
    "fastapi",
    "pydantic",
    "uvicorn",
    "motor",
    "pymongo",
    "prometheus_client",
    "hailo_platform",
    "picamera2",
    "libcamera",
    "numpy",
    "cv2",
    "onnxruntime",
    "imx500",
]

# ── Napoleon (docstring style) ────────────────────────────────────────────────
napoleon_google_docstring = True
napoleon_numpy_docstring  = False
napoleon_include_init_with_doc = True
napoleon_use_rtype        = True

# ── Intersphinx ───────────────────────────────────────────────────────────────
intersphinx_mapping = {
    "python":    ("https://docs.python.org/3", None),
    "sqlalchemy": ("https://docs.sqlalchemy.org/en/20/", None),
}

# ── General ───────────────────────────────────────────────────────────────────
templates_path    = ["_templates"]
exclude_patterns  = ["_build", "Thumbs.db", ".DS_Store"]
source_suffix     = {".rst": "restructuredtext", ".md": "markdown"}
master_doc        = "index"

# ── HTML output ───────────────────────────────────────────────────────────────
html_theme         = "furo"
html_static_path   = ["_static"]
html_title         = "AURA Platform"
html_theme_options = {
    "sidebar_hide_name":    False,
    "light_css_variables": {
        "color-brand-primary":   "#6366f1",
        "color-brand-content":   "#6366f1",
    },
    "dark_css_variables": {
        "color-brand-primary":   "#818cf8",
        "color-brand-content":   "#818cf8",
    },
    "source_repository":   "https://github.com/Estelamb/TFM_MIoT/",
    "source_branch":       "main",
    "source_directory":    "docs/sphinx/source/",
}
todo_include_todos = True

# Suppress known warnings:
suppress_warnings = [
    "ref.duplicate",
    "autodoc.import_object",
    "toc.not_readable",
    "toc.excluded",
    "app.add_node",
]
