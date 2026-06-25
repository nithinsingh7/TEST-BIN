## Chapter 2 — System Goals

### 1. Functional Goals

The software must provide a comprehensive set of functional capabilities to automate the survey processing pipeline. These include:

* **Data Ingestion:** Seamless import of DJI Matrice L1 survey datasets, including RGB imagery, LiDAR (LAS/LAZ format), IMU data, and camera metadata.
* **Automated Object Detection:** Utilization of AI models (e.g., RF-DETR) to identify semantic features such as towers, conductors, buildings, roads, and vegetation from RGB images.
* **Geometric Object Association:** Tracking and associating repeated detections of the same physical object across multiple overlapping images to prevent duplicate records.
* **LiDAR-RGB Fusion:** Combining semantic labels from 2D RGB imagery with 3D geometric data from LiDAR to pinpoint the exact location, height, and boundaries of objects.
* **Spatial Database Management:** Establishing a PostgreSQL + PostGIS database as the central repository for all identified engineering objects and spatial metadata.
* **Automated Report Generation:** Creating standardized engineering deliverables such as Tower Schedules and Crossing Schedules.
* **CAD and GIS Export:** Exporting verified data into industry-standard formats, including DXF/DWG for CAD drafting and Shapefile/GeoJSON/GeoPackage for GIS applications.

### 2. Engineering Goals

The system is built as an engineering tool first, meaning accuracy and consistency are paramount:

* **Geospatial Accuracy:** Ensure all extracted objects maintain high spatial accuracy by relying on LiDAR as the geometric source of truth.
* **Modularity:** Maintain a highly decoupled architecture where the UI, AI processing, database management, and LiDAR services can operate independently and be upgraded without system-wide refactoring.
* **Extensibility:** Design the system to easily accommodate future AI models, new object classes, or additional sensor inputs.
* **Robust Calculations:** Implement precise engineering calculations for span lengths, catenary curve fitting (sag), and clearance measurements.
* **Data Persistence:** Ensure every detected and validated object is securely stored with complete history and metadata in the database.

### 3. User Goals

The user interface and overall experience must be tailored to the needs of transmission line survey engineers:

* **Workflow-Centric Design:** The UI should guide users through the logical progression of the task: Project Setup → Data Processing → Span Review → Object Validation → Export.
* **Manual Validation Tools:** Provide intuitive tools for engineers to inspect AI detections, adjust boundaries, correct misclassifications, and manually add missing objects.
* **Multi-View Workspace:** Offer synchronized views of the 2D Map, 3D LiDAR Viewer, and raw RGB imagery to facilitate confident decision-making.
* **Performance:** The desktop application must remain responsive even when handling massive datasets, utilizing tile-based rendering and lazy loading where appropriate.

### 4. Performance Goals

Given the massive size of the survey datasets, the system must be highly optimized:

* **Efficient Memory Management:** Out-of-core processing must be used for large point clouds. LiDAR data should be tiled and streamed, rather than loaded entirely into RAM.
* **Parallel Processing:** Utilize multi-threading and GPU acceleration for AI inference, image processing, and point cloud analysis.
* **Database Optimization:** Implement spatial indexing (e.g., R-trees in PostGIS) to ensure rapid spatial queries and bounding box searches.
* **Scalability:** The architecture must comfortably handle surveys spanning tens of kilometers and comprising hundreds of gigabytes of raw data.

### 5. Scope

The scope of this project encompasses the development of the desktop software and its immediate dependencies:

* Development of the Tauri/React-based desktop UI.
* Implementation of the Rust-based backend for local processing, I/O, and service orchestration.
* Integration of Python microservices for AI inference (RF-DETR, SAM 2) and point cloud processing (PDAL, Open3D).
* Setup and schema definition for the local PostgreSQL/PostGIS database.
* Development of algorithms for object detection, RGB-LiDAR fusion, and object association.
* Generation of standard engineering reports (Tower/Crossing Schedules) and CAD/GIS exports.

### 6. Out-of-Scope Items

To maintain focus on the core objectives, the following features are explicitly out of scope for Version 1.0:

* **Cloud Hosting / SaaS Deployment:** The system is strictly a local desktop application. Cloud-assisted processing is considered a future enhancement.
* **Real-time Drone Control:** The software processes pre-collected survey data and does not interface directly with the drone during flight.
* **Full 3D Structural Engineering Design:** While the software measures clearances and identifies tower locations, it does not perform structural load calculations or tower design.
* **Video Processing:** The system processes discrete RGB images, not continuous video feeds.
* **Support for Non-DJI L1 Sensors:** Initial development is strictly optimized for the DJI Matrice L1 payload. Support for other LiDAR or camera systems is deferred to future updates.
