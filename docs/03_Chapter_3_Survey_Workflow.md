## Chapter 3 — Survey Workflow

### 1. Existing Survey Process

The current workflow for transmission line corridor surveys relies heavily on manual labor and siloed software tools. The typical process involves:

1. **Data Collection:** Drones fly along the planned or existing transmission corridor, capturing thousands of high-resolution RGB images and raw LiDAR point clouds.
2. **Data Preprocessing:** The raw data is run through vendor-specific software (e.g., DJI Terra) to generate initial point clouds and basic orthomosaics.
3. **Manual Review:** Engineers manually inspect the images and point clouds to identify existing towers, utility crossings, roads, rivers, buildings, and vegetation.
4. **Data Extraction:** Geographic coordinates and engineering measurements (e.g., clearance heights, distances) are manually extracted using generic GIS or CAD software.
5. **Report Generation:** Survey teams manually compile spreadsheets for Tower Schedules and Crossing Schedules.
6. **CAD Drafting:** Draftspersons manually draw the corridor plans, profile views, and crossing details in CAD software based on the extracted data.

This manual process is highly repetitive, prone to human error, and creates significant bottlenecks, often taking weeks to process a single long-distance survey.

### 2. DJI Matrice L1 Data Acquisition

The proposed software is optimized specifically for data acquired by the DJI Matrice platform equipped with the DJI L1 LiDAR payload. The simultaneous collection of multiple data types is a key enabler for the automated workflow.
During a flight, the DJI L1 captures:

* **High-Resolution RGB Imagery:** 20MP photos captured at regular intervals.
* **LiDAR Point Clouds:** High-density 3D geometric data with return intensity.
* **Trajectory Data:** The precise flight path of the drone.
* **Camera Poses & Orientation:** Yaw, pitch, roll, and precise coordinates for every captured frame, enabling accurate photogrammetry and projection.
* **RTK GPS & IMU Data:** Centimeter-level accuracy positioning and orientation data critical for georeferencing.
* **Timestamps:** Microsecond-accurate timestamps linking the imagery, LiDAR, and positional data.

### 3. Span Definition

The fundamental unit of organization within the software is the **Span**.
A span is defined as the continuous geographic section of the transmission corridor between two consecutive transmission towers (or angle points).

* **Example:** Tower 1 ---------- Tower 2 ---------- Tower 3. This represents two distinct spans.
* As the drone flies the corridor, it captures many overlapping images within each span.
* Objects located within a span (e.g., a road crossing the line between Tower 1 and Tower 2) will appear in multiple overlapping images.
* The software groups data processing and user validation at the span level, allowing engineers to review the corridor section by section logically.

### 4. Engineering Deliverables

The ultimate goal of the survey workflow is to produce standardized engineering deliverables. The automated system aims to generate these directly from the validated database:

* **Tower Schedule:** A comprehensive tabular report detailing every transmission tower, including its ID, geographic coordinates, elevation, type, and associated span lengths.
* **Crossing Schedule:** A detailed report listing every object that crosses the transmission corridor (e.g., roads, railways, rivers, other power lines). It includes the object type, location, and critical engineering measurements such as clearance heights.
* **DXF/DWG Drawings:** Automatically generated 2D plan and profile CAD drawings that map out the corridor, towers, conductors, and crossing objects, complete with standard layers and annotations.
* **GIS Layers:** Exportable spatial datasets (Shapefile, GeoPackage, GeoJSON) containing all detected objects for ingestion into enterprise GIS systems.
* **Engineering Measurements:** Specific calculated values, such as conductor sag, vertical clearances to ground/objects, and precise distances between infrastructure.

### 5. Survey Constraints

To ensure the automated system functions correctly, certain constraints and assumptions regarding the survey methodology must be met:

* **Continuous Flight Path:** The drone must follow the corridor continuously. Significant gaps in the trajectory or imagery may result in broken spans or missed objects.
* **Sufficient Image Overlap:** Standard photogrammetry overlap (e.g., 70-80% front and side overlap) is required to ensure objects are captured from multiple angles, aiding in accurate object association and 3D projection.
* **Proper RTK Fix:** A robust RTK GPS fix must be maintained during the flight. Loss of RTK accuracy will directly degrade the geospatial accuracy of the final engineering deliverables.
* **Consistent Calibration:** The DJI L1 sensor must be properly calibrated according to manufacturer specifications to ensure alignment between the RGB camera and the LiDAR sensor.
* **Standardized Coordinate Systems:** All input data must be correctly georeferenced to a known projected coordinate system (e.g., UTM) to allow for accurate distance and area calculations.
