# 2026-11-18 raw JPEG専用配信の調査・検証

現行仕様・設定・制約は [IMAGE_STREAM.md](IMAGE_STREAM.md#adopted-raw-jpeg-output)、
操作は [cat_bringup](../cat_robot/cat_bringup/README.md)が正本。
[前段の非圧縮画像試験](ZED_CHANGE_VALIDATION_20261118.md)は当時の結果として保存する。
本変更は利用者の「既存機能を調べ、可能ならrawをJPEG化した画像だけ配信したい」
という指示による。接続ZEDのカメラ起動試験許可は同じ会話の先行指示による。

## 調査と実装

既存の `video.publish_compressed=true` はimage_transport経由の圧縮を有効にするが、
同時に非圧縮IPC publisherを作り、画像ファミリーに応じてrect等も作る。
その設定だけでは「JPEG化したrawだけ」にはならない。

導入済み `compressed_image_transport` 2.5.5はOpenCVでJPEGを生成し、
元ImageのheaderをCompressedImageに引き継ぐ。
[圧縮処理の一次ソース](https://github.com/ros-perception/image_transport_plugins/blob/2.5.5/compressed_image_transport/src/compressed_publisher.cpp)と
[image_transport 3.1.13のplugin許可リスト](https://github.com/ros-perception/image_common/blob/3.1.13/image_transport/src/publisher.cpp)を確認した。
新しいエンコーダや圧縮用別ノードは追加せず、この既存経路を使用する。

追加した起動時専用 `video.raw_jpeg_only` は共有wrapperでは既定false。
CATのVIO/wheel両profileでtrueにし、`video.jpeg_quality=95`を指定。
このモードでは非圧縮IPC publisherを生成せず、許可リストをcompressedの1つに固定。
codecはJPEG、品質と許可リストはread-only。不正な品質・別codec・raw追加設定を拒否する。
rectの画像・CameraInfoは作らない。深度等の内部VIO処理や必要なIMUは維持する。
前段の画像ON/OFF・周期ゲートはJPEGの取得・コピー・符号化より前に働く。

配信する画像は `/zed/zed_node/rgb/color/raw/image/compressed`、型は
`sensor_msgs/msg/CompressedImage`。rawは歪み未補正を意味する。
元の取得時刻と `zed_left_camera_frame_optical` を引き継ぎ、復号後672×376 BGR。
非圧縮ImageをDDSへ送って別ノードで圧縮する方式ではない。
raw CameraInfoの既存2口は維持する。

## 検証対象と環境

| repository | HEAD（未コミット差分を含む） |
|---|---|
| zed-ros2-wrapper | `e20278b461056d1c94733689b513ba9f544fb479` |
| cat_robot | `5f539ffb5872f79a4d3e784e572d9bbb236101b7` |
| d1vision_ros2（既存の暫定service型を依存ビルド） | `910a197eafd8856a8897961803318c538f9a40ac` |

前段の未コミット実装・handoff・文書を保持。開始時tracked diffはログの
`*_before.diff`、前段の追加ファイル内容は `log/zed_change_20261118/*_after.diff` にある。
今回の最終追加ファイルを含む差分は `*_after.diff`、SHA256は `source_manifest.json`。
以下のログ・scriptはすべてworkspaceの `log/zed_jpeg_20261118/` に保存した。

Ubuntu 22.04.5、Linux 6.8.0-138、Python 3.10.12、ROS Humble、GCC11、CMake Release。
実機SDK 5.4.1、CUDA toolkit13.5、NVIDIA595.99.02、RTX3060 Laptop。
image_transport3.1.13、compressed_image_transport2.5.5。正確な導入版は
`environment.txt`、リンク先は `links.log`、prefixは `prefix.log`。
依存更新・インストールは行っていない。

入力は接続ZED Mini SN10028118、sourceのVIO/wheel YAML、共通設定。
オフラインfixtureはコード内で作る黒色672×376 BGR画像1種類。
実機では各profileの最初のJPEGだけを復号して形式・寸法を確認し、
以後はstamp・件数・payload長を集計した。画像・bag・モデルは保存／再生せず、
過去datasetを読まず、D1推論・走行・simulationは起動していない。

## 実行方法と結果

実際の完全な引数・sourceパス・ログ保存・exit保持は下記scriptに保存した。
workspace rootから、継承workspace underlayを除いたshellで実行。

```bash
env -i HOME=/home/uedalab USER=uedalab PATH=/usr/local/bin:/usr/bin:/bin LANG=C.UTF-8 \
  bash --noprofile --norc log/zed_jpeg_20261118/build_command.sh
env -i HOME=/home/uedalab USER=uedalab PATH=/usr/local/bin:/usr/bin:/bin LANG=C.UTF-8 \
  bash --noprofile --norc log/zed_jpeg_20261118/test_command.sh
# 同じclean shellで以下をそれぞれ実行:
# hardware_command.sh vio
# hardware_command.sh restart
# hardware_command.sh sensors
# legacy_command.sh
```

fresh出力は `build/zed_jpeg_20261118` / `install/zed_jpeg_20261118`。
ビルドsourceはd1vision_interfaces・zed_components・zed_wrapperの明示パス。
`CMAKE_BUILD_PARALLEL_LEVEL=2 MAKEFLAGS=-j2`、colcon sequential。
オフラインROSはdomain84、実機はdomain85、共にlocalhostのみ。
カメラ単体のTF提供のため `publish_urdf=true`。採用CAT全体は起動していない。

| 検証 | 結果 | exit / ログ |
|---|---|---|
| 最終build | 3 packages成功 | 0、`build.log` |
| CTest image_stream_gate / raw_jpeg_publisher | 2 pass、0 fail、0 skip | test/test-result共に0、`ctest.log`, `test_result.log` |
| 新installの依存解決 | unresolved / not foundなし | 0、`links.log` |
| JPEG VIO | 67 assertions pass、0 fail | 0、`vio_*` |
| ONで終了した後の再起動 | 8 assertions pass、0 fail | 0、`restart_*` |
| JPEG wheel IMU | 67 assertions pass、0 fail | 0、`sensors_*` |
| 共有wrapperの従来非圧縮経路 | 64 assertions pass、0 fail | 0、`legacy_test.log`, `legacy/vio_*` |

実機4ケース合計206 assertions成功。206個の独立シナリオという意味ではない。
各測定窓4秒、resume2秒、測定前0.5秒のDDS排出時間を置いた。
起動OFF、購読者ありでもOFF維持、ON、ON中の周期変更、反復ON/OFF、不正周期10通り、
停止、再開のsource stamp単調増加・要求後の新しいstamp、未購読操作を確認。
実機graphでvisual image publisherがcompressedの1口だけであることと、
rect CameraInfo publisher不在も確認した。

| 実測 | VIO JPEG | wheel JPEG |
|---|---|---|
| 起動OFF / 停止後の画像 | 0件 | 0件 |
| 0.2秒指定 | 4.75–5 Hz | 5 Hz |
| 0.1秒指定 | 10 Hz | 10 Hz |
| VIO odom / WORLD pose | 約29.5–30 Hz | 設定OFF、0件 |
| IMU source周期 | ROS出力OFF | 約100.1–100.9 Hz |
| JPEG bytes/frame | 31,118–55,383 | 32,244–53,376 |

今回のsceneではJPEG約31–55 KB、元の非圧縮758,016 bytes/frame。
帯域・CPU/GPU使用量の総量／削減率を測定した値ではなく、sceneや品質に依存する。
JPEGのformatは `bgr8; jpeg compressed bgr8`、復号寸法672×376、frame_idは従来通り。
旧経路overrideでは同じビルドから非圧縮bgr8・672×376・5/10 Hzを確認した。

## 途中失敗と未検証条件

- 初案でcodecクラスへ直接リンクしようとしたが、Humbleのcodec packageは直接利用用の
  CMake include/libraryをexportしないためfixture build失敗（exit2、
  `build_direct_link_failed.log`）。fixtureのrclcpp header不足も修正した
  （exit2、`build_fixture_header_failed.log`）。
- 独自plugin loaderをpublisherと同時に解放するとNode callback group終了時にsegfault。
  static loaderにした案もstatic終了順序でsegfault。いずれもカメラを使わないfixtureで
  発見し、`test_result_loader_lifetime_failed.log` / `test_result_static_loader_failed.log`
  と `LastTest_*` に保存した。このときcolcon testは0を返したがtest-resultは1だった。
  最終実装は独自loaderを廃止し、既存image_transport factoryの寿命管理を使用する。
  その後のCTest2件と実機4ケースは終了まで通った。
- wheel試験のSDK closeは約6秒かかり、launchの既存5秒タイムアウトでSIGTERMへ
  escalationした。その後CAMERA CLOSEDとchild process finished cleanlyを確認した。
  launch/test exit0だけを即時正常終了の証明とは扱わない。既存retryやtimeoutは変更していない。
- SDKの拡張IMU校正が無効で基本biasへfallbackする警告、低texture/occlusionで
  self-calibrationがskipされる警告が出た。VIOのPERFORMANCE非推奨と最小深度clamp警告も
  継続している。topic到達を校正・追跡精度の合格と扱わず、校正値は変更していない。
- JPEGは非可逆。D1認識精度、JPEG由来の再圧縮影響、長時間メモリ、総帯域、CPU/GPU、
  他SDK／圧縮plugin版、NITROS/IPCモード、JPEGと全metric出力の同時使用、USB抜去、
  CAT全体の運転統合、走行安全、既存Image購読側のJPEG移行は未検証。
  全上流lintは実行せず、CTestは明示した2件のみ。

既存panorama_capture、GUI画像録画preset、RViz設定、D1旧Image抽出器は別途JPEG対応が
必要。非圧縮互換publisherは起動しない。過去の評価画像・Logbookは変更していない。

使用時は `/opt/ros/humble/setup.bash` に続けて
`source install/zed_jpeg_20261118/setup.bash` で今回の検証済みoverlayを読む。

## 同日追記: 採用品質90

利用者の追加指示でCAT VIO/wheel両profileのJPEG品質を90へ変更した。
撮影30 Hz・配信上限24 Hz・IMU100 Hz・サービス契約は維持。現行値の正本は
[IMAGE_STREAM.md](IMAGE_STREAM.md#adopted-raw-jpeg-output)。上記の実機値は品質95で
得た歴史的結果であり、品質90の実機・認識精度の結果には読み替えない。
品質90の確認はsource YAML2件の構文・値と差分検査のみで、カメラ再起動・再ビルドは
行っていない。適用には対象profileでwrapperを再起動する。
SHA・差分・環境・正確な確認script・exitはworkspaceの
`log/zed_jpeg_quality90_20261118/` に保存。
