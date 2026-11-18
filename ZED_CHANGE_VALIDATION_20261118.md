# 2026-11-18 ZED画像配信・内部処理の検証記録

実装契約は [IMAGE_STREAM.md](IMAGE_STREAM.md)、操作は
[cat_bringup](../cat_robot/cat_bringup/README.md)を正本とする。
引き継ぎ文書は作成当時の調査として保存した。サービス型の暫定D1配置と
接続ZEDの起動・topic確認は今回の利用者指示による。

## 実装と入力

- 起動・再起動時の画像OFF、画像だけの周期制御、取得前ゲート、待機画像破棄、
  配信とOFF応答の排他。不正周期は状態を変えず拒否。
- Path無効時のタイマー・履歴生成停止。フラグはread-only。
- ROSセンサー出力全OFFでは100 ms待機と1秒ごとのFIFO読み捨て。
  SDK内VIO融合・校正由来の静的IMU TF・wheel用の既存IMU間引きは維持。
- wheel設定はdepth NONE / stabilization 0。通常VIOはPERFORMANCE / GEN_1。
- `d1vision_interfaces/srv/SetImageStream` を暫定追加。wrapperに依存を明示。
  カメラgrabの開始停止ではなくROS画像配信を制御する。

入力はソース設定2件、共通wrapper設定、接続ZED Mini SN10028118の現在フレーム。
試験スクリプトは画像を受信するが内容の判定・保存はせず、型・寸法・encoding・
frame_id・stamp・件数だけを記録した。録画・モデル・過去datasetは読まず、
D1推論、bag再生、simulation、CATの走行ノードは起動していない。

## ソースと環境

| repository | テスト対象HEAD（未コミット差分を含む） |
|---|---|
| zed-ros2-wrapper | `e20278b461056d1c94733689b513ba9f544fb479` |
| cat_robot | `5f539ffb5872f79a4d3e784e572d9bbb236101b7` |
| d1vision_ros2 | `910a197eafd8856a8897961803318c538f9a40ac` |

開始時wrapperには既存の `LOCAL_MAINTENANCE.md` 差分と未追跡handoff文書があった。
元差分はログの `*_before.diff` / `*_before.txt` に保存し、保持した。
最終差分は `*_after.diff`、追加ファイルを含むSHA256は `source_manifest.json`。
後述ログは全てworkspaceの `log/zed_change_20261118/` に保存。

Ubuntu 22.04.5、Linux 6.8.0-138、ROS 2 Humble、Python 3.10.12、GCC 11。
実行時SDK 5.4.1 build 117278_137d3e18_3228228、CUDA toolkit 13.5.37、
NVIDIA driver 595.99.02、RTX 3060 Laptop GPU。
CMake Release。fresh build/installを `*_20261118_clean` 以下に作成。
`zed_msgs` と `zed_description` は `/opt/ros/humble` の既存依存を使用。
`ldd` とprefix照会で新規D1型・wrapperを確認した。旧workspace installは
clean build/runtimeのunderlayに含めず、依存更新・導入は行っていない。

## 正確なコマンドと終了状態

全てworkspace rootから実行。ビルドと実機試験は次のclean shellで実行した。
各scriptには実際のcolconパス・引数・環境変数を保存している。

```bash
env -i HOME=/home/uedalab USER=uedalab PATH=/usr/local/bin:/usr/bin:/bin LANG=C.UTF-8 \
  bash --noprofile --norc log/zed_change_20261118/build_command.sh
env -i HOME=/home/uedalab USER=uedalab PATH=/usr/local/bin:/usr/bin:/bin LANG=C.UTF-8 \
  bash --noprofile --norc log/zed_change_20261118/test_build_command.sh
env -i HOME=/home/uedalab USER=uedalab PATH=/usr/local/bin:/usr/bin:/bin LANG=C.UTF-8 \
  bash --noprofile --norc log/zed_change_20261118/test_command.sh
env -i HOME=/home/uedalab USER=uedalab PATH=/usr/local/bin:/usr/bin:/bin LANG=C.UTF-8 \
  bash --noprofile --norc log/zed_change_20261118/offline_command.sh
# 同じclean shellでhardware_command.shに vio / restart / sensors / path / depth を渡す。
# D1とsupervisorの既存pytestは d1_test_command.sh / supervisor_test_command.sh に保存。
```

`CMAKE_BUILD_PARALLEL_LEVEL=2 MAKEFLAGS=-j2`、colconはsequential。
実機は `ROS_DOMAIN_ID=82 ROS_LOCALHOST_ONLY=1`、supervisor単体fixtureはdomain83。
カメラ単体試験は取付TFを提供するため `publish_urdf:=true` を使用し、CAT全体の
bringupは使用していない。元の採用profile YAMLは明示パスで読み込んだ。

| 検証 | 結果 / exit | 完全ログ |
|---|---|---|
| clean build（3 packages） | 成功 / 0 | `build_clean.log` |
| 最終コードbuild、test target追加build | 3 packages成功 / 各0 | `build_verified.log`, `test_build.log` |
| CTest image_stream_gate | 1 pass / 0 fail / 0 skip、exit0 | `ctest.log`, `test_result.log` |
| D1 decoder・frame sampling・ground adapter既存pytest | 4 pass / 0 fail / 0 skip、exit0 | `d1_tests.log` |
| supervisor子プロセス終了fixture | 2 pass / 0 fail / 0 skip、exit0 | `supervisor_test.log` |
| install型serialization（5値）、prefix、launch引数展開 | 成功 / 0 | `offline.log` |
| 実機VIO | 64 checks pass / 0 fail、exit0 | `vio_results.json`, `vio_test.log`, `vio_launch.log` |
| ON状態で終了後の再起動 | 6 checks pass / 0 fail、exit0 | `restart_*` |
| 実機wheel sensors | 64 checks pass / 0 fail、exit0 | `sensors_*` |
| Path有効 + max_count=6 override | 7 checks pass / 0 fail、exit0 | `path_*` |
| depth map有効override | 70 checks pass / 0 fail、exit0 | `depth_*` |

実機5ケースは計211個のassertionが成功（独立した211シナリオという意味ではない）。
全launchはSIGINTで正常終了（exit0）、試験プロセスグループを停止した。

## 実機で観測した値

| 条件 | 画像 | odom / WORLD pose | wheel IMU | 深度 |
|---|---|---|---|---|
| 通常VIO・起動時OFF | 0件 | 約30 Hz / 約30 Hz | 設定OFF | 設定OFF |
| 通常VIO・0.2 s指定 | 5 Hz | 約30 Hz / 約30 Hz | 設定OFF | 設定OFF |
| 通常VIO・0.1 s指定 | 10 Hz | 約30 Hz / 約30 Hz | 設定OFF | 設定OFF |
| 通常VIO・OFF後 | 0件 | 約30 Hz / 約30 Hz | 設定OFF | 設定OFF |
| wheel画像OFF / 5 Hz / 10 Hz | 0 / 5 / 10 Hz | 0件 | source約100.8–100.9 Hz | NONE |
| depth有効の追加試験・画像OFF / 5 / 10 Hz | 0 / 5 / 10 Hz | 約30 Hz | 設定OFF | 約23.5–24 Hz |

各測定窓は基本4秒、resumeは2秒、事前に0.5秒のDDS排出時間を設けた。
購読者ありの起動OFF、ON中の周期更新、ON/OFF反復、0・負・NaN・inf・
撮影fps超の要求、未購読でのサービス操作を確認。
rawは672×376、bgr8、step2016、758016 bytes、
`zed_left_camera_frame_optical`。source stampは単調増加し、再開後は再開要求より新しい。
CameraInfoは画像OFFでも約24 Hz、静的 `zed_imu_link` TFも受信。
通常設定のPathは0件、有効overrideでは2 Hzかつ履歴上限6を確認。
wheelログはdepth NONE、位置追跡開始ログなし、odom0件。

## 失敗・制約を含む記録

- 最初のbuildは継承環境で旧workspace underlayが入り、colconが `-j20` を選択した。
  発見後に当該buildのプロセスツリーを中断（exit143、`build.log`）。
  この出力は検証根拠に使わず、環境を空にした新規build/installでやり直した。
  以後はcompilerを最大2、colconをsequentialに固定。
- 最初の実機fixtureは画像をBest Effortで購読し、10 Hz要求時の受信が5.25 Hzとなり
  assertion失敗（test exit1、launch exit0）。`attempt1_vio_*` に保存。
  画像購読だけReliableへ変更すると5/10 Hzを受信した。受信欠落の切り分け結果であり、
  Best Effortで安定受信できるという保証はしない。先行Reliable試験も
  `reliable_initial_vio_*` に保持し、未購読OFF確認を追加した最終fixtureで再実行した。
- SDKは実機で `Extended IMU calibration in EEPROM is invalid; falling back to basic bias path`
  を警告した。IMU topicとVIOの継続は確認したが、校正・軌跡精度の合格とは扱わない。
  SDKはVIOのPERFORMANCE非推奨、既定の最小深度0.01 mを0.1 mへclampする警告も出した。
  採用VIOモードや校正データをこの作業で変更していない。
- 参照ソース名・存在しないtest候補への探索で非0終了があった。実在ファイルを確認して
  継続しており、テスト失敗には数えない。
- CPU/GPU削減率のbefore/after比較、長時間メモリ傾向、SVO/simulation、SDK旧版、
  他カメラ、IPC/NITROS、圧縮、depth以外の全出力組合せ、USB抜去時の運用、
  CAT全体のodom監視・走行安全統合・D1管理側自動呼出しは未検証。
  終了コードと通常停止は確認したが、全てのshutdown/service競合順序を網羅していない。
  全上流lintは実行せず、CTestは追加したpolicy testだけを選択した。

使用時は `source install/zed_change_20261118_clean/setup.bash` で検証済みoverlayを読み込む。
通常installの古い実行物だけをsourceした状態を、新実装の動作証拠として扱わない。
