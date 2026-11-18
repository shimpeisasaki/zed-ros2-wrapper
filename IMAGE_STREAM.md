# ROS image publication control

The stereo wrapper starts with image publication **OFF**, including after a
process restart. Camera grab, SDK VIO/IMU fusion, depth required by GEN_1 VIO,
ROS odometry and configured ROS sensors continue independently. Subscribing or
starting rosbag does not enable images. This is a shared gate for all visual
image topics (raw/rectified, color/gray, left/right/stereo), not a D1 lease.
CameraInfo, depth/disparity/confidence, point clouds and SDK streaming are outside
this gate. Keep one controlling client; no automatic retries or owner arbitration.

The service `/zed/zed_node/set_image_stream` uses
`d1vision_interfaces/srv/SetImageStream`. Its temporary placement in D1 interfaces
is explicitly requested for this change and should be revisited during D1
refactoring. The ZED wrapper implements the callback and settings; no D1 manager,
model, crop, task registration or navigation code is required or started.

| Direction | Field | Contract |
|---|---|---|
| request | `enabled: bool` | Start/stop continuous ROS visual image publication |
| request | `period_sec: float64` | Finite positive seconds, at least `1/grab_frame_rate`, also for OFF |
| response | `success: bool` | Entire request applied, or rejected without state changes |
| response | `applied_period_sec: float64` | Configured image period; previous period on rejection |
| response | `message: string` | Status or rejection reason |

NaN, infinities, zero, negative values and faster-than-grab requests are rejected.
The initial configured period is 1 second, with publication disabled. Repeated
ON/OFF is supported; ON while enabled updates the period without creating threads
or timers. Accepted calls discard queued visual frames and reset scheduling;
frames acquired before the call cannot be published after it. OFF response waits
for any concurrent image publish to finish. Messages already handed to DDS can
still arrive afterward. Camera-not-ready/stopping requests are rejected.

The actual image rate is capped by camera grab and the existing shared
`general.pub_frame_rate` worker limit (CAT: 30 Hz grab, 24 Hz worker). A service
period does not alter that parameter, VIO or depth cadence. Discrete capture and
worker scheduling cause jitter; `applied_period_sec` is not a measured period.
Image retrieval and ROS conversion are gated before the SDK retrieve calls.
Accepted configuration updates invalidate pending images under the same mutex,
preventing queued frames from crossing an OFF/reconfiguration boundary. Acquisition stamps and the unrectified field of view are preserved. With
`video.raw_jpeg_only=false`, the existing Image and transport paths remain
available. CAT now adopts JPEG-only mode as described below.


## Adopted raw JPEG output

Both CAT profiles (`zed_vio.yaml`, `zed_sensors.yaml`) now set:

```yaml
video:
  publish_rgb: true
  publish_raw: true
  publish_compressed: true
  raw_jpeg_only: true
  jpeg_quality: 90
  publish_left_right: false
  publish_gray: false
  publish_stereo: false
```

`raw` means the **unrectified left color view**, not an uncompressed wire encoding.
The wrapper retrieves `LEFT_UNRECTIFIED_BGR` (SDK 5.4), converts to an internal
Image, then uses the installed `compressed_image_transport` JPEG plugin **inside
the wrapper process**. It publishes exactly one visual image topic:

| Topic | ROS type | Content |
|---|---|---|
| `/zed/zed_node/rgb/color/raw/image/compressed` | `sensor_msgs/msg/CompressedImage` | JPEG, format `bgr8; jpeg compressed bgr8`, decoded 672 × 376 |

`frame_id` remains `zed_left_camera_frame_optical`, with source acquisition time.
No non-compressed base Image publisher, rectified image publisher, Theora, PNG,
TIFF, zstd or compressedDepth visual publisher is created in this mode. The raw
CameraInfo topics remain (`rgb/color/raw/camera_info` and the existing
`rgb/color/raw/image/camera_info` alias); rectified CameraInfo is absent. VIO,
IMU, diagnostic and other non-visual outputs remain independent. Optional metric
depth/confidence outputs keep their existing contract.

The existing image_transport factory manages the plugin lifetime. Its read-only
`enable_pub_plugins` allowlist is restricted to `image_transport/compressed`
before publisher creation. Ordinary
`video.publish_compressed=true` alone cannot provide this restriction: the
existing dual publisher path also creates a non-compressed IPC publisher and
loads other compatible transports. That default path is preserved when the new
mode is false (the shared wrapper default).

`video.raw_jpeg_only` and `video.jpeg_quality` are startup-only. Quality must be
1..100, shared-wrapper default 95 (CAT profiles override to 90); the plugin's format is fixed to JPEG and its codec settings
are read-only in this mode. Use `video.jpeg_quality` rather than overriding
plugin-internal parameters. JPEG-only mode rejects incompatible image flags,
ROI/disparity output, `publish_compressed=false`, or active NITROS. It requires
`publish_rgb=true` and `publish_raw=true`; `publish_rgb` still enables the RGB
family, but the mode suppresses its rectified output.

The same stream service controls JPEG output: startup/restart OFF, ON plus a
compressed subscriber enables retrieval and encoding, OFF stops both. Merely
subscribing to the former Image topic cannot start encoding. JPEG is lossy;
quality/size depends on scene content. Existing D1 offline results are historical
uncompressed inputs and are not JPEG recognition-accuracy validation.

Consumers must subscribe as CompressedImage or use image_transport's `compressed`
transport. `cat_capture` currently subscribes to Image, the operator GUI's
recording preset still names the former Image topic, RViz uses its old display
configuration, and D1's offline frame extractor defaults to the historical
Image topic/decoder. These consumers need a separate JPEG migration before use
with new JPEG recordings. No compatibility Image republisher is started, since
that would defeat the requested output restriction. Existing datasets, labels,
Logbooks and archived input identities are unchanged.

Implementation reference: installed `compressed_image_transport` 2.5.5,
[source codec and metadata handling](https://github.com/ros-perception/image_transport_plugins/blob/2.5.5/compressed_image_transport/src/compressed_publisher.cpp).

With ROS sensor outputs disabled, calibration-based IMU TF remains available.
The sensor worker wakes every 100 ms and drains/discards the SDK FIFO once per
second without per-sample timestamp/decimation/diagnostic processing. The installed
SDK header does not guarantee a FIFO size bound, so acquisition is reduced rather
than eliminated. With any ROS sensor output configured, the existing full drain
and decimation remain active even without subscribers, preventing a backlog on
resubscription. Output enable flags are read-only; changing profiles restarts the
camera. This does not disable the SDK's own VIO fusion.

`pos_tracking.publish_cam_path` is read-only. When false no Path timer or history
is created or appended; enabling it requires a restart and uses a fresh history.
Enabled Path behavior and count limits are preserved. CAT wheel profile uses
`depth_mode: NONE`, `depth_stabilization: 0`, tracking disabled and calibrated IMU;
CAT VIO retains PERFORMANCE depth and GEN_1 tracking.

Build from explicit sources including the nested interface package, in a shell
with only `/opt/ros/humble/setup.bash` sourced, with fresh output directories:

```bash
export CMAKE_BUILD_PARALLEL_LEVEL=2 MAKEFLAGS=-j2
colcon --log-base log/zed_check build --build-base build/zed_check \
  --install-base install/zed_check --executor sequential \
  --base-paths src/d1vision_ros2/d1vision_interfaces \
    src/zed-ros2-wrapper/zed_components src/zed-ros2-wrapper/zed_wrapper \
  --packages-up-to zed_wrapper --cmake-args -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=OFF
source install/zed_check/setup.bash
```

Runtime calls and CAT operational ownership are documented in
[cat_bringup](../cat_robot/cat_bringup/README.md).
The CTests `image_stream_gate` and `raw_jpeg_publisher` check scheduling and a
synthetic JPEG fixture without a camera.
Build with `-DBUILD_TESTING=ON`, then run `colcon test --packages-select
zed_components --ctest-args -R '^(image_stream_gate|raw_jpeg_publisher)$'` with the same build/install
and explicit base paths.

The manual acceptance script `tests/check_image_stream_hardware.py` requires
`--hardware --profile vio|sensors|restart|path|depth --output <generated log directory>`.
JPEG is the default test transport; `--transport uncompressed` explicitly tests
the legacy path using launch overrides. The script starts only the ZED wrapper
and robot_state_publisher, receives bounded samples and decodes one JPEG frame, and stops its own process group. Use only with explicit camera permission,
an isolated ROS domain and localhost. It never starts CAT motors/navigation or D1.

Dated implementation evidence: [2026-11-18 validation](ZED_CHANGE_VALIDATION_20261118.md).

JPEG adoption evidence: [2026-11-18 JPEG validation](ZED_JPEG_VALIDATION_20261118.md).
