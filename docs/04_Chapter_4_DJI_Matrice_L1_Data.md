# PART II — Survey Data

## Chapter 4 — DJI Matrice L1 Data

The DJI Matrice drone, equipped with the DJI Zenmuse L1 payload, is the core data acquisition platform for this system. The L1 payload uniquely integrates a Livox LiDAR module, a high-accuracy IMU, and a 1-inch CMOS visual camera on a 3-axis stabilized gimbal. This integration allows for the simultaneous capture of highly correlated spatial geometry and visual semantics.

### 1. RGB Images

The built-in visual camera captures high-resolution 20-megapixel RGB imagery. These images serve a dual purpose:

* **Semantic Information:** Providing the primary input for the artificial intelligence models (RF-DETR, SAM 2) to detect and classify objects (e.g., towers, conductors, buildings).
* **Photogrammetry & Texturing:** Used to colorize the LiDAR point cloud and optionally generate 2D orthomosaics or 3D mesh models via secondary photogrammetry software.
The images are captured at regular intervals (distance or time) to ensure the necessary 70-80% overlap required for accurate object tracking and 3D reconstruction.

### 2. LiDAR Point Cloud

The Livox LiDAR sensor emits laser pulses to measure the distance to the Earth's surface and objects upon it.

* **Geometry:** It provides the absolute source of truth for the 3D geometry of the transmission line corridor.
* **Density:** The sensor generates high-density point clouds, allowing for the capture of thin structures like transmission conductors (wires) that are often missed by photogrammetry alone.
* **Attributes:** Each point captured includes XYZ coordinates, intensity (reflectivity of the surface), return number (essential for penetrating vegetation), and time of capture.

### 3. Trajectory

The trajectory data records the exact flight path of the drone through 3D space over time.

* It combines RTK GPS positioning with the IMU measurements.
* The trajectory is crucial for the post-processing of raw LiDAR data (SBET - Smoothed Best Estimate of Trajectory) to ensure point cloud accuracy and alignment.

### 4. Camera Poses (Yaw, Pitch, Roll)

For every single RGB image captured, the exact orientation of the camera is recorded.

* **Gimbal Angles:** Yaw (heading), Pitch (elevation angle), and Roll (bank angle) are logged.
* **Application:** These poses, combined with the precise coordinate of the camera center at the moment of exposure, are mathematically required to project a 2D pixel from an image into the 3D space of the LiDAR point cloud (and vice-versa).

### 5. RTK GPS

Real-Time Kinematic (RTK) positioning is an advanced satellite navigation technique used to enhance the precision of position data derived from satellite-based positioning systems.

* **Accuracy:** It provides centimeter-level accuracy for the drone's location during flight.
* **Requirement:** An active RTK fix is mandatory during the survey to ensure the resulting engineering outputs (like clearance measurements) are geographically accurate and reliable.

### 6. IMU (Inertial Measurement Unit)

The high-accuracy IMU constantly measures the drone's specific force, angular rate, and orientation.

* It operates at a high frequency, filling in the gaps between the lower-frequency GPS updates.
* The IMU is critical for correcting the LiDAR point cloud, compensating for the rapid movements, vibrations, and tilting of the drone in flight.

### 7. Metadata and Timestamps

Synchronization is the most critical aspect of the L1 dataset.

* **Microsecond Accuracy:** Every RGB image, LiDAR pulse, GPS coordinate, and IMU reading is tagged with a highly precise timestamp based on GPS time.
* **Sensor Fusion:** These timestamps allow the software to perfectly synchronize the camera shutter opening with the corresponding LiDAR points and the exact position/orientation of the drone at that millisecond.
* **EXIF/XMP:** Image metadata stores intrinsic camera parameters (focal length, principal point) and extrinsic parameters (location, altitude).

### 8. Coordinate Systems

Proper handling of spatial reference systems is vital.

* Raw DJI data is typically captured in the WGS84 geographic coordinate system (Latitude/Longitude/Ellipsoidal Height).
* For engineering software and accurate distance/area calculations, this data must be projected into a local Cartesian coordinate system (e.g., the specific UTM zone for the survey area).
* The software must handle robust coordinate transformations (using libraries like PROJ) to translate between WGS84, local UTM zones, and custom local grid systems if required by the engineering client.
