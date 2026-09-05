# RF Mapping with Drone Swarm

This repository is the research and development stack for a planned swarm of small autonomous drones that cooperatively maps an unknown environment using **visual-inertial sensing and Wi-Fi RF measurements**.

The long-term system is intended to produce two complementary representations of the environment:

1. a **3D geometric map** produced primarily from cameras, IMUs, visual-inertial odometry, SLAM, and multi-agent Structure from Motion; and
2. a **probabilistic RF map** produced from synchronized Wi-Fi measurements collected by the drones as they move through the environment.

The RF system is an additional sensing layer. It is **not** intended to replace cameras, IMUs, VIO, SLAM, or other collision-critical geometric sensing.

The current working implementation is in [`rf_mapping_project`](rf_mapping_project/README.md).

---

## Project status

The project is currently at the **RF mapping prototype** stage.

The repository already contains a working ESP32 RSSI measurement pipeline and an offline probabilistic RF inference framework. Autonomous flight, visual localization, 3D reconstruction, CSI acquisition, multi-drone communication, and real-time swarm fusion are later stages of the project.

| Subsystem                            | Status                    |
| ------------------------------------ | ------------------------- |
| ESP32 scalar RSSI acquisition        | Implemented               |
| Manual 2D survey workflow            | Implemented               |
| Measured RSSI heatmap                | Implemented               |
| Versioned RF acquisition metadata    | Implemented               |
| Open-space path-loss calibration     | Implemented               |
| Probabilistic RF field estimation    | Implemented               |
| Attenuation/obstacle evidence model  | Implemented               |
| Observability and uncertainty gating | Implemented               |
| Synthetic RF experiments             | Implemented               |
| Automated Python test suite          | Implemented               |
| Wi-Fi CSI acquisition                | Planned / not implemented |
| Camera + IMU pose estimation         | Planned                   |
| Visual-inertial odometry             | Planned                   |
| Single-drone autonomous mapping      | Planned                   |
| 3D geometric mapping                 | Planned                   |
| 3D RF voxel mapping                  | Planned                   |
| Multi-drone communication            | Planned                   |
| Multi-agent map fusion               | Planned                   |
| Base-station global mapping          | Planned                   |
| Swarm trajectory coordination        | Planned                   |
| Fully autonomous mapping swarm       | Long-term target          |

---

# Current RF Mapping Prototype

The present system uses:

* an ESP32-family Wi-Fi receiver;
* a fixed 2.4 GHz Wi-Fi access point or hotspot;
* Arduino firmware for RF measurement;
* Python for acquisition, calibration, probabilistic inference, visualization, simulation, and validation.

The original prototype collected RSSI at manually specified coordinates and produced a measured two-dimensional signal-strength heatmap.

The current software extends that baseline with:

* robust open-space RF calibration;
* richer timestamped acquisition metadata;
* transmitter and receiver geometry;
* receiver pose and orientation metadata;
* path-loss modeling;
* Gaussian-process RF field estimation;
* posterior uncertainty;
* ray-based attenuation estimation;
* probabilistic attenuation evidence;
* bootstrap confidence estimates;
* observability checks;
* deterministic artifacts and simulations;
* automated tests.

The complete setup, calibration, collection, inference, validation, and troubleshooting workflow is documented in:

[`rf_mapping_project/README.md`](rf_mapping_project/README.md)

---

## Current measured dataset

The checked-in physical experiment contains:

* **450 RSSI samples**
* **9 receiver positions**
* **50 measurements per position**
* **1 pass**
* a **3 × 3 measurement grid**
* a **100 cm × 100 cm survey area**

This is sufficient to demonstrate the acquisition pipeline and measured RF coverage mapping.

It is **not** sufficient to claim that walls, obstacle positions, obstacle dimensions, or object shapes have been reconstructed.

The existing dataset does not contain all of the calibration, AP geometry, pose uncertainty, antenna orientation, repeated-pass, and independent-link information required by the current observability checks. The inference pipeline therefore intentionally refuses to generate unsupported obstacle-geometry claims.

Increasing the plotting resolution does not create new physical information. A 5 cm visualization grid constructed from measurements spaced much farther apart is still an estimate, not a 5 cm sensor.

---

# Intended System

The final project is intended to move from a manually positioned ESP32 to a group of autonomous flying sensing agents.

Each drone will eventually combine:

* camera sensing;
* IMU measurements;
* visual-inertial pose estimation;
* local obstacle mapping;
* Wi-Fi RSSI and potentially CSI measurements;
* local trajectory planning;
* inter-drone communication;
* timestamped sensor logging.

The drones will cooperatively explore the environment while a base station performs the computationally heavier global mapping and RF inference operations.

A high-level target architecture is:

```text
                 UNKNOWN ENVIRONMENT
                        │
        ┌───────────────┼───────────────┐
        │               │               │
        ▼               ▼               ▼
     Drone 1         Drone 2         Drone N
   ┌─────────┐     ┌─────────┐     ┌─────────┐
   │ Camera  │     │ Camera  │     │ Camera  │
   │ IMU     │     │ IMU     │     │ IMU     │
   │ Wi-Fi RF│     │ Wi-Fi RF│     │ Wi-Fi RF│
   └────┬────┘     └────┬────┘     └────┬────┘
        │               │               │
        ▼               ▼               ▼
   Local VIO       Local VIO       Local VIO
   Local Map       Local Map       Local Map
   Local Planner   Local Planner   Local Planner
        │               │               │
        └───────────────┬───────────────┘
                        │
             Swarm communication link
                        │
                        ▼
                ┌─────────────────┐
                │ Base / Dock     │
                │ Station         │
                ├─────────────────┤
                │ Time / origin   │
                │ coordination    │
                │ mission control │
                │ map fusion      │
                │ global SfM      │
                │ RF inference    │
                │ data storage    │
                └────────┬────────┘
                         │
             ┌───────────┴───────────┐
             ▼                       ▼
      3D geometric map        Probabilistic RF map
             │                       │
             └───────────┬───────────┘
                         ▼
                 Fused world model
```

---

# Sensor Responsibilities

A central design rule of this project is that different sensing modalities have different responsibilities.

## Camera + IMU

The camera and IMU are intended to provide the primary information for:

* drone pose;
* motion estimation;
* visual-inertial odometry;
* local obstacle detection;
* geometric reconstruction;
* metric free space;
* collision avoidance;
* visual loop closure;
* multi-view reconstruction.

This geometric sensing remains the authoritative source for collision-critical navigation.

## Wi-Fi RF

RF sensing is intended to provide complementary information about the propagation environment.

The RF layer may eventually estimate:

* spatial RSSI fields;
* RF coverage;
* attenuation regions;
* propagation boundaries;
* RF signatures associated with physical structures;
* uncertainty in those estimates;
* potentially additional multipath information from CSI.

RF information may help strengthen a geometric map or identify regions that deserve additional sensing.

It must **not** be interpreted as proof that an apparently unobstructed region is physically safe to fly through.

---

# Why Combine RF and Vision?

Vision and RF observe different physical properties.

A camera primarily measures light reflected from visible surfaces. Wi-Fi measurements instead contain information about radio propagation through reflection, diffraction, scattering, absorption, and multipath.

The goal is therefore not to make Wi-Fi duplicate a camera.

The goal is to determine whether RF measurements provide **additional statistically supported information** that improves mapping when fused with the geometric map.

For example, a region could be:

```text
Visual map:
    strong wall evidence

RF map:
    strong attenuation evidence

Result:
    higher confidence that a persistent physical boundary exists
```

Or:

```text
Visual map:
    incomplete / uncertain

RF map:
    unusual attenuation

Result:
    region marked for further observation
```

The second case is **not** automatically considered an obstacle. The drone should obtain additional geometric evidence before treating RF evidence as collision geometry.

---

# Mapping Architecture

The planned mapping stack contains several different maps rather than attempting to force all sensor measurements into one representation.

## Local geometric map

Each drone should maintain a local map for immediate navigation.

This map must be available with low latency and should not require a functioning connection to the base station to prevent collisions.

Possible representations include:

* local point clouds;
* occupancy grids;
* signed-distance fields;
* voxel maps.

The exact representation has not yet been selected.

## Global geometric map

The base station will eventually merge data from multiple drones into a common world coordinate system.

The planned visual pipeline is based around concepts such as:

* keyframe selection;
* feature matching;
* multi-view geometry;
* bundle adjustment;
* visual loop closure;
* multi-agent Structure from Motion;
* sparse reconstruction;
* later dense reconstruction or surface generation.

The purpose of the global map is accurate environment reconstruction and long-term swarm coordination rather than immediate motor-level collision avoidance.

## RF map

Every RF measurement should eventually be associated with:

```text
timestamp
drone ID
receiver pose
pose covariance
receiver orientation
transmitter ID
transmitter position when known
channel
bandwidth / PHY metadata
RSSI
CSI when available
measurement quality
```

The measurements from all drones can then be transformed into the common map frame and fused.

The current 2D RF implementation is the first version of this subsystem.

## Future 3D RF representation

Once reliable 3D drone poses are available, the RF model can be extended from an `(x, y)` field to an `(x, y, z)` representation.

A likely representation is a **voxel grid**, where the environment is divided into small three-dimensional cells and each voxel stores quantities such as:

```text
RF posterior mean
RF posterior uncertainty
measurement support
attenuation evidence
observability
geometric occupancy
```

The voxel size must be chosen from actual sensing resolution and uncertainty. Making voxels arbitrarily small does not increase the physical resolution of the RF measurements.

---

# Planned Data Flow

For every drone:

```text
Camera ───────┐
              ├──> VIO / pose estimator ──> position + orientation + covariance
IMU ──────────┘
                                      │
                                      │ synchronized pose
                                      ▼
Wi-Fi receiver ──> RSSI / CSI measurement
                                      │
                                      ▼
                       timestamped RF observation
                                      │
                                      ▼
                              Local data buffer
                                      │
                                      ▼
                           Swarm communication
                                      │
                                      ▼
                               Base station
```

At the base station:

```text
Drone poses + keyframes
          │
          ▼
Multi-agent visual reconstruction
          │
          ▼
Global geometric map
          │
          ├──────────────────────────┐
          │                          │
          ▼                          ▼
RF observations               Pose uncertainty
          │                          │
          └──────────────┬───────────┘
                         ▼
               Probabilistic RF fusion
                         │
                         ▼
                  Global RF layer
                         │
                         ▼
                Fused environment map
```

---

# Swarm Architecture

The long-term system should avoid making every drone dependent on a central computer for immediate flight safety.

Each drone should eventually perform onboard:

* state estimation;
* local VIO;
* local obstacle detection;
* short-horizon trajectory generation;
* emergency collision avoidance;
* basic inter-drone separation.

The base station should perform tasks that benefit from more computation or information from the entire swarm:

* common coordinate-frame management;
* map merging;
* global bundle adjustment;
* multi-agent visual reconstruction;
* RF field reconstruction;
* RF observability analysis;
* mission allocation;
* exploration coordination;
* long-term map storage;
* global route updates.

If communication with the base station is temporarily lost, a drone should retain enough local perception and planning capability to remain safe rather than continuing blindly.

---

# RF Development Roadmap

## Stage 1 — Manual RSSI mapping

**Status: implemented**

Current system:

```text
fixed Wi-Fi AP
      │
      ▼
    ESP32
      │
      ▼
serial RSSI measurements
      │
      ▼
Python acquisition
      │
      ▼
2D measured RF map
```

This establishes the hardware/software acquisition path and provides real RF datasets for later algorithm development.

---

## Stage 2 — Controlled probabilistic RSSI inference

**Status: current development stage**

The current repository already contains the software infrastructure for:

* controlled calibration;
* path-loss estimation;
* probabilistic field modeling;
* uncertainty;
* ray-based attenuation inference;
* observability checks;
* repeated-trial validation;
* synthetic experiments.

The next physical experiments must provide sufficiently controlled metadata and measurement geometry for those models to be meaningfully evaluated.

Important experimental variables include:

* known AP position;
* calibrated path loss;
* fixed or measured antenna orientation;
* receiver height;
* pose uncertainty;
* multiple survey passes;
* independent propagation paths;
* controlled obstacle geometry;
* held-out validation trials.

Only after these experiments succeed should wall position or obstacle dimensions be evaluated.

---

## Stage 3 — Multi-link RF sensing

A major limitation of a single transmitter-receiver path is poor spatial observability.

The planned system should investigate measurements involving multiple independent RF paths created by combinations of:

* fixed APs;
* base-station radios;
* multiple drones;
* known transmitter locations.

Crossing the same region from different directions provides substantially more information than repeatedly sampling a single RF path.

The value of additional RF infrastructure must be measured experimentally rather than assumed.

---

## Stage 4 — Wi-Fi CSI

**Status: experiment designed, firmware not implemented**

RSSI reduces an entire received Wi-Fi packet to a scalar signal-strength measurement.

Channel State Information provides frequency-dependent complex channel measurements across Wi-Fi subcarriers and therefore exposes considerably more information about the multipath channel.

CSI is a major planned research direction, but it must remain separate from the stable RSSI implementation until the exact ESP32 chip, antenna implementation, ESP-IDF version, and CSI support are confirmed.

The proposed first CSI experiment is documented in:

[`rf_mapping_project/docs/CSI_FOLLOW_ON.md`](rf_mapping_project/docs/CSI_FOLLOW_ON.md)

The initial CSI goal is **not obstacle imaging**.

The first goal is to determine whether calibrated CSI provides repeatable environmental information beyond RSSI under controlled conditions.

Only then should CSI be incorporated into the mapping model.

---

## Stage 5 — RF-assisted motion estimation

RF multipath may eventually provide additional information about receiver motion.

This should be investigated as an **auxiliary motion constraint** that could potentially complement the IMU/VIO estimator.

It is not planned as a replacement for the physical IMU or visual-inertial estimator.

A future estimator could conceptually combine:

```text
IMU propagation
      +
visual motion constraints
      +
RF-derived motion constraints
      +
loop-closure constraints
```

The contribution of the RF term must be validated experimentally before being used in state estimation.

---

# Drone Integration Roadmap

## Stage 6 — Single-drone sensing platform

Replace the manual receiver position with actual vehicle state estimates.

The drone must provide synchronized:

```text
x, y, z
yaw, pitch, roll
timestamp
pose covariance
```

for every RF observation.

The first flight experiments should reproduce the existing controlled ground measurements before attempting autonomous exploration.

---

## Stage 7 — Visual-inertial mapping

Integrate the camera and IMU pipeline.

Target flow:

```text
Camera + IMU
      │
      ▼
Visual-Inertial Odometry
      │
      ├──> real-time drone pose
      │
      └──> local geometric map
```

This establishes the reference geometry required to place RF measurements correctly in three dimensions.

---

## Stage 8 — Single-drone 3D RF mapping

Once synchronized 6-DoF poses are reliable:

```text
3D pose + RF measurement
             │
             ▼
         RF samples
             │
             ▼
      3D probabilistic field
             │
             ▼
         RF voxel map
```

The system can then evaluate whether flying at different heights produces useful additional RF observability.

---

# Multi-Drone Roadmap

## Stage 9 — Shared coordinate system

All drones must ultimately express measurements in a common map frame.

This requires solving:

* relative map alignment;
* clock synchronization;
* inter-drone pose consistency;
* loop closures between drones;
* map-frame updates;
* uncertainty propagation.

Raw coordinates from separate drones cannot simply be combined unless their coordinate frames are known to agree.

---

## Stage 10 — Multi-agent visual reconstruction

Images and poses from multiple drones can be combined to improve coverage and reconstruct portions of the environment that no single vehicle sees sufficiently well.

The intended architecture is:

```text
Drone 1 keyframes ─┐
Drone 2 keyframes ─┼──> Multi-agent SfM ──> Global 3D reconstruction
Drone N keyframes ─┘
```

The base station is a natural location for this computation because it can receive information from all agents and perform global optimization without placing the full compute burden on every small drone.

---

## Stage 11 — Multi-drone RF fusion

After coordinate-frame alignment, the RF observations collected by every drone can be combined:

```text
Drone 1 RF observations ─┐
Drone 2 RF observations ─┼──> Global RF inference
Drone N RF observations ─┘
```

This is important because the drones can deliberately observe the same region from different transmitter-receiver geometries.

Instead of simply increasing the number of RSSI samples, swarm exploration can eventually be designed to increase **RF observability**.

---

## Stage 12 — Cooperative exploration

Once local navigation and global map fusion are reliable, the base station can allocate unexplored regions among drones.

The swarm should attempt to maximize:

* unexplored geometric coverage;
* visual reconstruction quality;
* RF observability;
* trajectory safety;
* separation between vehicles;
* remaining battery;
* communication reliability.

This transforms the swarm from several independent mapping drones into a coordinated sensing system.

---

# Base Station / Dock

The planned dock is more than a charging point.

It can eventually provide:

* a repeatable global origin;
* time synchronization;
* mission initialization;
* swarm communication coordination;
* high-compute global mapping;
* data storage;
* charging;
* map persistence between sorties.

Conceptually:

```text
                    BASE / DOCK
                         │
        ┌────────────────┼────────────────┐
        │                │                │
        ▼                ▼                ▼
   Coordination      Computation       Physical
   ------------      -----------       --------
   drone IDs         global SfM        charging
   missions          RF fusion         home position
   time sync         optimization      deployment
   map versions      validation        recovery
```

The dock/base station is therefore intended to connect repeated flights into a persistent mapping system.

---

# Optional Radar / SAR Research Track

Synthetic-aperture radar is relevant to aerial mapping research, but it is a separate sensing architecture from the current Wi-Fi project.

A true SAR implementation requires radar measurements with appropriate bandwidth, phase coherence, trajectory knowledge, and motion compensation.

The current ESP32 RSSI system is **not SAR**.

Wi-Fi CSI should also not automatically be described as SAR.

If a later drone version carries dedicated ultra-wideband or other radar hardware, SAR can be investigated as an additional mapping modality:

```text
Dedicated radar
      +
known drone trajectory
      +
motion compensation
      +
synthetic aperture processing
      =
radar image
```

That would be a separate payload and processing pipeline that could ultimately be registered to the same global 3D map.

---

# Safety and Scientific Boundaries

The project deliberately keeps several claims separate.

### RF is not collision-safe free-space sensing

A weak, strong, or apparently unobstructed RF measurement does not prove that a physical flight path is clear.

Camera/VIO/geometric sensing remains responsible for collision safety.

### The current system is not SLAM

The present RF prototype receives manually supplied positions. It does not jointly estimate pose and map, perform loop closure, or optimize a pose graph.

### The current system does not reconstruct walls

The existing physical dataset does not provide enough independent geometry or calibration to support wall polygons or obstacle dimensions.

### Higher plotting resolution is not higher sensing resolution

Interpolation and smaller grid cells can improve visualization but cannot create information that was never measured.

### CSI is not currently implemented

The exact ESP32 hardware and toolchain must first be verified and a controlled CSI acquisition experiment completed.

### RF-based inertial measurement is not the current system

Research showing motion information in RF multipath uses substantially different signal processing and hardware assumptions. Any RF motion estimator must be independently validated before entering the navigation stack.

### Wi-Fi sensing is not equivalent to radar

The project must not describe RSSI or CSI experiments as radar unless the sensing and signal-processing architecture actually satisfies that definition.

---

# Repository Layout

```text
RF-Mapping-with-Drone-Swarm-/
│
├── README.md
│
└── rf_mapping_project/
    │
    ├── README.md
    ├── rf_mapper.py
    ├── requirements.txt
    │
    ├── esp32_rssi_mapper/
    │   └── ESP32 RSSI firmware
    │
    ├── rf_mapping/
    │   ├── calibration.py
    │   ├── data.py
    │   ├── field_model.py
    │   ├── inference.py
    │   ├── observability.py
    │   ├── occupancy.py
    │   ├── simulation.py
    │   └── visualization.py
    │
    ├── docs/
    │   └── CSI_FOLLOW_ON.md
    │
    ├── examples/
    ├── survey_output/
    └── tests/
```

For installation, firmware configuration, data collection, calibration, inference commands, simulation, validation, and troubleshooting, see:

## [`rf_mapping_project/README.md`](rf_mapping_project/README.md)

---

# End Goal

The final system is intended to operate approximately as follows:

```text
1. Multiple drones leave the base station.

2. Each drone performs onboard visual-inertial localization.

3. Each drone builds enough local geometry to navigate safely.

4. Cameras, IMUs, and RF measurements are timestamped in a common
   coordinate and timing framework.

5. Drones distribute themselves through unexplored regions.

6. Each drone continuously sends selected poses, keyframes, RF measurements,
   trajectory information, and map updates to the base station and/or peers.

7. The base station merges visual observations into a global 3D map.

8. RF observations from all drones are transformed into the same coordinate
   system and fused into a probabilistic RF map.

9. Geometric and RF uncertainty are maintained separately.

10. The global map is returned to the swarm for higher-level planning while
    every drone retains local collision-avoidance capability.

11. The base station assigns new exploration regions according to remaining
    uncertainty, coverage, RF observability, battery state, and vehicle safety.

12. The process repeats until the desired region has been mapped.

13. Drones return to the dock, recharge, and retain the global map for
    subsequent sorties.
```

The near-term objective is much narrower: **validate that controlled Wi-Fi measurements contain reproducible and spatially useful information before integrating the RF system onto an autonomous drone.**
