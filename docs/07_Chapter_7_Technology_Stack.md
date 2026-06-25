## Chapter 7 — Technology Stack

To achieve the performance, modularity, and engineering accuracy required for the Transmission Line Corridor Survey Automation System, a carefully selected mix of modern frameworks and industry-standard geospatial libraries is utilized.

### 1. Desktop Framework

* **Tauri:** Chosen over Electron for its significantly lower memory footprint, smaller binary size, and enhanced security. Tauri uses the system's native webview to render the frontend while leveraging Rust for the backend architecture, ensuring maximum resources are left available for data processing and 3D rendering.

### 2. Frontend

* **React:** The core library for building the complex, stateful user interface. Its component-based architecture is ideal for managing the various workspaces (Map, 3D Viewer, Image Inspector).
* **TypeScript:** Used universally across the frontend to enforce strict typing, reducing runtime errors and improving code maintainability when handling complex geometric data structures.
* **Tailwind CSS:** A utility-first CSS framework used for rapid, consistent styling of the UI components, ensuring a professional, dense engineering interface.
* **Deck.gl / Potree (Proposed):** Specialized WebGL-powered frameworks for streaming and rendering massive LiDAR point clouds natively within the browser environment.

### 3. Backend Orchestration

* **Rust:** The primary backend language driving the Tauri application. Rust guarantees memory safety and thread safety, making it ideal for managing intensive parallel tasks, file I/O operations on massive datasets (e.g., hundreds of GBs of LAS files), and coordinating the job queues sent to the Python microservices.

### 4. Database Layer

* **PostgreSQL:** A highly robust, open-source relational database used as the central repository for all project metadata, configuration, and engineering object attributes.
* **PostGIS:** The spatial extension for PostgreSQL. This is a critical component that enables the database to natively understand, store, and query geographic objects (Points, Lines, Polygons, 3D Geometries). It handles the heavy lifting for spatial intersections (e.g., finding all AI detections within a specific geographic bounding box).

### 5. Artificial Intelligence & Processing (Python Ecosystem)

Python is utilized purely as an offline data-processing engine, exposed via local microservices.

* **PyTorch:** The foundational deep learning framework used to train, load, and execute the underlying neural network models.
* **RF-DETR (RT-DETR):** Real-Time DEtection TRansformer. Selected for its state-of-the-art performance in object detection tasks, offering a superior balance of accuracy and inference speed compared to traditional CNNs (like YOLO) when analyzing high-resolution aerial imagery.
* **SAM 2 (Segment Anything Model 2):** Utilized for precise image segmentation. Once RF-DETR identifies a bounding box around an object, SAM 2 can be used to extract the exact pixel-perfect outline, aiding in precise LiDAR projection.
* **OpenCV:** The industry standard for classical computer vision tasks, utilized for image pre-processing, thumbnail generation, and manipulating camera intrinsic/extrinsic matrices.

### 6. LiDAR and Point Cloud Processing

* **PDAL (Point Data Abstraction Library):** The backbone for translating and manipulating point cloud data. PDAL is used to filter, reproject, and extract subsets from the massive raw LAS/LAZ files efficiently.
* **Open3D:** A modern 3D data processing library used for complex geometric calculations, nearest-neighbor searches, ground plane extraction, and bounding box validations against the point cloud.

### 7. GIS and Spatial Data Science

* **GDAL (Geospatial Data Abstraction Library):** Used for reading and manipulating raster data formats (like DSMs, DTMs, and Orthomosaics).
* **PROJ:** Essential for executing accurate coordinate system transformations (e.g., converting WGS84 GPS coordinates to local projected UTM grids).
* **GeoPandas & Shapely:** Used within the Python services for rapid, in-memory manipulation and mathematical evaluation of 2D and 3D geometric shapes (calculating intersections, buffers, and areas).

### 8. CAD Generation

* **ezdxf:** A mature Python library used to programmatically construct DXF (Drawing Exchange Format) files. This allows the software to take the validated spatial geometries from the database and translate them into standard layers, blocks, and polylines required for final engineering CAD deliverables.
