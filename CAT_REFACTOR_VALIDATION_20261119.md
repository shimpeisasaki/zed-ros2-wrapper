# CAT refactor offline verification, 2026-11-19

The wrapper source starts at `3878297b762883c94010978269b050f4c5e78ace`, clean.
This unit updates current documentation only. Generic wrapper Image, rectified,
gray, left/right and JPEG paths, parameters, defaults and launch precedence are
unchanged. CAT owns the common/profile expansion and passes one override path.
Standalone custom ROS YAML remains unchanged. See [IMAGE_STREAM.md](IMAGE_STREAM.md)
and [CAT startup](../cat_robot/docs/startup.md).

Complete commands, baseline/after source manifests, environment, dirty diffs and
logs are retained in workspace `log/cat_zed_refactor_20261119_172436/`.
`run_phase.sh baseline` built the explicit 21-package checkout set in fresh
outputs using Humble alone, sequential packages and at most two build workers.
The selected `image_stream_gate` and `raw_jpeg_publisher` CTests passed, exit 0;
the latter uses a synthetic 672x376 BGR image and localhost/domain84 only.
No camera, SDK device calls, motor, model, simulation or bag replay was executed.
Historical camera measurements in dated November 18 records remain historical.

CAT byte/header/odom capture and D1 service-to-result flow use synthetic JPEG,
mock localhost HTTP and domain89; baseline proof and teardown receipts are in
`baseline/surface_clean.log`. The owning CAT validation record and final workspace
report contain the final after comparison and any environmental limitations.
The separate after output built the same 21 packages, exit 0; both selected
wrapper CTests passed again. Baseline and after wrapper parameter-layer snapshots
are identical for VIO, wheel, custom standalone, inline overrides and generic mode.
The inspected launch is only constructed; no camera container/action is executed.
Artifacts: `baseline/wrapper_layers.json`, `after/wrapper_layers.json`,
`after/installed_checks_final.log`. CAT/D1 installed surfaces passed in
`after/surface.log`, with cleanup receipts.
The final core result after the focused GUI snapshot regression fix is 232 tests,
0 errors, 0 failures and 1 pre-existing hardware skip; the GUI12 tests also pass.
Livox SDK is missing and is not downloaded. LSP is unavailable and is not installed.
