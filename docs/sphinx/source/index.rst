AURA Platform Documentation
============================

.. meta::
   :description: Official documentation for the AURA Platform, an end-to-end MLOps system for deploying AI models on IoT Edge devices.
   :keywords: AURA, IoT, Edge AI, MLOps, Hailo, IMX500, FastAPI, MQTT, Raspberry Pi

.. rubric:: AI Deployment Platform for IoT Edge Devices

AURA is an end-to-end platform that automates the full lifecycle of ML model deployment on
resource-constrained edge hardware, from uploading a trained model to monitoring live inference
results in real time.

.. tip::
   New here? Start with the :doc:`introduction` for a high-level overview and then follow
   the :doc:`tutorials/run_platform` guide to get the stack running locally.

----

General Overview
----------------

High-level introduction to the AURA Platform, covering its motivation, system architecture,
supported hardware targets, and key design principles.

.. toctree::
   :maxdepth: 1
   :caption: General

   introduction
   architecture

----

Guides & Tutorials
------------------

Step-by-step tutorials to run the platform stack, operate the web console, set up edge devices,
and extend the system with new compilation targets or hardware driver peripherals.

.. toctree::
   :maxdepth: 1
   :caption: Tutorials

   tutorials/run_platform
   tutorials/use_platform
   tutorials/add_hardware
   tutorials/create_script
   tutorials/hardware/index

----

Codebase Explanation
--------------------

A detailed structural walkthrough of the AURA codebase, components, files, and physical device integrations.

.. toctree::
   :maxdepth: 1
   :caption: Codebase Explanation

   code_explanation
