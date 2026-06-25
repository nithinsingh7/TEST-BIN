# PART III — Overall Software Architecture

## Chapter 6 — High-Level System Architecture

The AI-Powered Transmission Line Corridor Survey Automation System is architected as a local, multi-process desktop application. To handle the massive datasets and complex computational requirements, the system embraces a decoupled, modular design. It leverages the strengths of different programming languages: React for UI, Rust for robust backend orchestration and I/O, Python for AI and data science libraries, and PostgreSQL for spatial data management.

### 1. Architectural Overview Diagram

The following diagram illustrates the high-level flow of data and control between the major system components:

```text
+-----------------------------------------------------------------------------------+
|                            Tauri Desktop Application                              |
|                                                                                   |
|  +-----------------------------------------------------------------------------+  |
|  |                             React Frontend                                  |  |
|  |  (UI, Dashboards, 2D Maps, 3D Point Cloud Viewer, Validation Workspaces)    |  |
|  +-----------------------------------------------------------------------------+  |
|                                     | (IPC - Inter-Process Communication)         |
|                                     v                                             |
|  +-----------------------------------------------------------------------------+  |
|  |                              Rust Backend                                   |  |
|  |  (App State, File I/O, Job Scheduler, Process Management, DB Connection)    |  |
|  +-----------------------------------------------------------------------------+  |
+-------------------------------------+---------------------------------------------+
                                      | (Local API / gRPC)
                                      v
+-----------------------------------------------------------------------------------+
|                           Python Microservices                                    |
|                                                                                   |
|  +-------------------+  +-------------------+  +-------------------+              |
|  |   AI Detection    |  | LiDAR Processing  |  | Geometry & Export |              |
|  | (RF-DETR, SAM 2)  |  |  (PDAL, Open3D)   |  | (Shapely, ezdxf)  |              |
|  +-------------------+  +-------------------+  +-------------------+              |
+-------------------------------------+---------------------------------------------+
                                      | (SQL / Spatial Queries)
                                      v
+-----------------------------------------------------------------------------------+
|                        PostgreSQL + PostGIS Database                              |
|                                                                                   |
|  +-------------------+  +-------------------+  +-------------------+              |
|  |  Survey Metadata  |  | Engineering Objs  |  | Spatial Indexes   |              |
|  | (Images, Traj)    |  | (Towers, Roads)   |  | (Bounding Boxes)  |              |
|  +-------------------+  +-------------------+  +-------------------+              |
+-----------------------------------------------------------------------------------+
                                      | (Export Generation)
                                      v
+-----------------------------------------------------------------------------------+
|                           Engineering Outputs                                     |
|                                                                                   |
|  [ Tower Schedules ]  [ Crossing Schedules ]  [ DXF/DWG Drawings ]  [ GIS Layers ]|
+-----------------------------------------------------------------------------------+
```

### 2. Core Architectural Components

#### A. Frontend (React + Tauri UI)

The user interface is built using React and hosted within the lightweight Tauri framework. It acts strictly as a presentation and user-interaction layer.

* **Responsibility:** Displaying maps, rendering tiled point clouds (using libraries like Potree or deck.gl), presenting image review panels, and capturing user validation inputs.
* **Constraint:** The frontend does not process raw survey data or execute AI models. It requests processed data and status updates from the Rust backend.

#### B. Rust Backend (The Orchestrator)

Rust serves as the core engine of the desktop application.

* **Responsibility:** Managing the SQLite/PostgreSQL connection pool, reading and chunking heavy files (like parsing LAS headers), managing background task queues (e.g., dispatching 1,000 images to the Python AI service), and routing IPC messages from the React frontend.
* **Why Rust?** It provides memory safety, extremely fast I/O performance, and predictable execution without the heavy overhead of an Electron/Node.js backend.

#### C. Python Microservices (The Workers)

Given the dominance of Python in the AI and spatial data science ecosystems, heavy computational tasks are isolated in separate Python processes.

* **Responsibility:** Executing PyTorch neural networks for object detection, running PDAL pipelines to filter point clouds, mathematically projecting 2D bounding boxes into 3D space, and generating complex DXF CAD files.
* **Communication:** The Rust backend communicates with the Python services via local REST APIs, JSON-RPC, or gRPC to ensure clean separation of concerns.

#### D. The Spatial Database (The Source of Truth)

A local instance of PostgreSQL enhanced with the PostGIS extension.

* **Responsibility:** Storing the definitive state of the project. Every image location, every AI detection, every LiDAR tile boundary, and every validated engineering object is stored here as geometric data.
* **Philosophy:** By making the database the central hub, the AI and LiDAR services become stateless workers. If the AI service crashes, the project state is safely preserved in the database. Engineering reports are simply SQL queries executed against this truth.
