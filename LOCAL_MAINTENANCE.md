# Local maintenance

## Adopted fork

The adopted local `master` is
`c06abb044d59e99819867f3c5e7ed478c485f289`.
The locally available `origin/master` points to the same commit. Its parent,
`32448b386d550a8f85f3bf0cc316f373d500a73a`, is the comparison anchor for the
raw-image change; it is not claimed to be a freshly verified upstream release.
No independent upstream remote or network refresh was used for this documentation unit.
Work proceeds on `refactor/implementation-20261112`; keep the baseline name `master`,
upstream packages/layout and [LICENSE](LICENSE).

Commit `c06abb0` changes only
[zed_camera_component_video_depth.cpp](zed_components/src/zed_camera/src/zed_camera_component_video_depth.cpp):
`video.publish_compressed` defaults to true. When false, the raw IPC publisher is
still created but image_transport plugin publisher initialization is skipped.
Preserve that raw-only path when updating the upstream camera component.
Do not describe the parameter as disabling raw images or all camera data.

Deployment configuration, raw image topics, VIO WORLD pose input and process ownership
are documented in [cat_bringup](../cat_robot/cat_bringup/README.md).
Do not replace its gravity-aligned VIO input with camera-relative odometry or
move navigation/capture policy into this wrapper.
The panorama backup's extra logging argument is not part of this adopted change;
compare actual consumers before importing a branch.

## Offline maintenance

The scoped follow-up for internal unused processing and image publication control
is [ZED修正の引き継ぎ](ZED_CHANGE_HANDOFF_JA.md). It preserves the existing
unrectified raw input; the historical proposal describes its original unimplemented state.
The implemented contract is [ROS image publication control](IMAGE_STREAM.md).
The agreed image publication default is OFF at startup/restart, enabled only by
the new service. VIO or the wheel configuration's required IMU stays independent
of image publication. Existing image consumers will need an explicit ON call.

The [README prerequisites](README.md#prerequisites) for this source list ZED SDK 5.2,
CUDA and supported ROS environments; the workspace uses ROS 2 Humble.
Record the actual installed SDK/CUDA versions for a code build rather than treating
the README's supported-version list as evidence that those dependencies are installed.
Keep [zed_components/CMakeLists.txt](zed_components/CMakeLists.txt) and
the [wrapper configuration directory](zed_wrapper/config) with the upstream package layout.

For documentation changes, check relative paths and diff only; do not open a camera,
execute a launch, load an SVO or start simulation.
For a separately authorized code change, coordinate a focused Humble build for
`zed_wrapper` and its dependencies from the actual checkout, using existing SDK/CUDA
and at most two workers. Review selected test fixtures before executing tests.
No driver build, SDK validation, image-stream test or hardware check ran for this prose change.

## Evidence and data

Update the authoritative interface/configuration/user instructions in the same change
as behavior. Preserve dated results. Record full tested SHA and dirty diff, OS/ROS,
SDK/CUDA/dependencies, input identity, exact commands, counts, exit status, failures/skips,
log locations and unverified conditions. Separate offline, simulation and hardware.

Inspect filenames, sizes, metadata and summaries before SVO/images/clouds/models/logs.
Only read payloads for a named question, with bounded files/topics/time/sample counts.
Exclude generated output/data/cache from broad searches. Store complete logs separately,
show bounded causal excerpts and preserve exit codes. Follow [AGENTS.md](AGENTS.md).

Implementation and camera-only test evidence from 2026-11-18 is recorded in
[the validation record](ZED_CHANGE_VALIDATION_20261118.md). This is not full CAT
bringup, motor/safety acceptance, simulation, or a D1 inference evaluation.

CAT's adopted profiles now select the explicitly requested
[raw JPEG-only mode](IMAGE_STREAM.md#adopted-raw-jpeg-output). The historical
non-compressed path remains the shared wrapper default; CAT JPEG mode creates
only the compressed raw visual publisher. See the separate
[JPEG validation record](ZED_JPEG_VALIDATION_20261118.md) for evidence and consumer
migration limits; earlier non-compressed test records remain historical.
