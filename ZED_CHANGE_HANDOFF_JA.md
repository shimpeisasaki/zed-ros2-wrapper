# ZED 内部処理と画像配信制御の修正方針

2026-11-18。別の会話でZED関連の修正を実装するための引き継ぎ。
今回確定した作業範囲は、**内部の不要処理の調査・修正**と、
**画像配信ON/OFF・配信周期を指定するサービスの受付・適用**の2点。
この資料を作成した時点では、コード・設定の修正、ビルド、実機起動はしていない。

## 全体タスクと今回の境界

D1の利用者は設問IDを指定して判定を開始・停止する。将来のD1管理ノードが有効な設問を
順番に実行し、共通結果topicへ継続配信する。画像集合を扱うopen_skyは対象外。
ZED側は設問、crop、推論、走行判断を持たず、カメラ・VIOと汎用画像配信を担当する。

```text
利用者 → D1管理ノード：設問IDの開始・停止
         D1管理ノード → ZED wrapper：画像配信ON/OFF・周期指定
         D1管理ノード ← ZED wrapper：既存の非圧縮raw画像topic
利用者 ← D1管理ノード：設問ID・分類結果・状態・画像時刻・推論時間
```

今回実装するのはZED側だけ。D1管理ノード、D1の設問制御サービス、結果メッセージ、
HTTP最適化、画像記録機能、共有メモリ・ポインタ共有は実装しない。
必要な記録は外部のrosbag recordで行う。

主な変更先はこのリポジトリのzed_components。ZED専用の採用設定を直す必要があれば、
所有元のcat_robot/cat_bringup/config/zed_vio.yaml・zed_sensors.yamlに限って関連変更を行う。
CATの走行制御・安全・navigationアルゴリズムには変更を広げない。

## 確定した画像の扱い

**D1入力は /zed/zed_node/rgb/color/raw/image を維持する。rectへ変更しない。**
利用者は以前、画角の問題でrawを選んだことを想起し、未補正画像を使う方針を確定した。
今回、画角比較やrectへの移行は行わない。

**画像配信は起動時・wrapper再起動時とも既定OFF。開始は新サービスのON要求で行う。**
通常のVIO構成はカメラ・VIOと必要な内部深度処理を起動時から維持する。
wheel odom構成では姿勢融合に必要なROS IMU出力を維持し、不要なZED位置追跡を停止する。
画像の購読やrosbag recordの開始だけでは配信を開始しない。
D1利用開始時にON、不要になった時にOFFを指示する。D1側の自動呼出し実装は別作業。

| 項目 | 現行CAT設定とwrapperの処理 |
| --- | --- |
| 画像 | 左カメラの歪み未補正カラー。センサーのBayer生データではない |
| SDK取得 | LEFT_UNRECTIFIED_BGR。SDK 5.1未満では旧BGRA経路 |
| ROS型 | sensor_msgs/msg/Image、非圧縮 |
| 解像度 | VGA、672×376、NATIVE配信 |
| 色形式 | enable_24bit_output=true、SDK 5.4ではbgr8 |
| 現行周期 | 撮影30 fps、画像配信設定24 fps |
| 時刻 | debug.use_pub_timestamps=false。SDKの画像取得時刻を使用 |
| frame_id | zed_left_camera_frame_optical。画像そのものではなく座標系名 |

採用中ground_hazards評価の1,542枚もraw由来。
[dataset.json](../../data/d1_vision_eval/run_20261017_143742_1s_forward_safety_v3/dataset.json)
のtopicが上記raw画像を指す。これは抽出元を記す885 bytesのメタデータであり、画像は未読。
さらに古い評価にはrectを使った記録もあるため、「過去の推論は全て同じ入力」とは扱わない。
参照先bagの旧パス data/bags/run_20261017_143742/metadata.yaml は確認時には存在しなかった。
今回bag本体の探索・再生・再評価は不要。

## 内部処理の調査結果と修正方針

以下はソースと設定の静的確認。稼働時の負荷削減量やSDK内部の実行量は未測定。
配信OFF、SDK処理OFF、worker待機を区別して修正する。

### Path配信OFFでも内部履歴を蓄積する

catの両設定はpublish_cam_path=false。共通設定はpath_pub_rate=2.0、path_max_count=-1。
しかしstartPosTrackingはstartPathPubTimerを無条件で呼び、callback_pubPathsは
publishフラグ・購読者の有無にかかわらずmPosePath・mOdomPathへ姿勢を追加する。
そのため追跡が動くと、Path配信がOFFでも2 Hzのタイマーと上限なしの蓄積が残る。

修正ではpublish_cam_path=falseならタイマーと内部履歴の生成・追加を止める。
Path有効時の既存動作・設定は維持する。publish_cam_pathの動的変更を既存コードが
許可するかも確認し、許可する場合は無効化・再有効化時の履歴の扱いを明示する。
path_pub_rate=0だけで止めようとしない。共通設定の説明と実装に0の扱いの差があるため、
今回の主修正は配信フラグによる明示的な停止とする。

### ROS用IMU配信OFFでもセンサー取得が続く

ZED Miniではsensors_image_sync=falseのときセンサーthreadが起動する。
publishSensorsDataは購読者ゼロでもgetSensorsDataBatchを呼び、ハードウェアIMU周期を
基準にpollし、時刻検査・間引き・診断統計を処理する。VIO設定ではROSのIMU配信は全てOFF。

SDK内部のVIOのIMU融合と、wrapperのROS配信用データ取得を分ける。
ROSセンサー出力・センサー依存の診断・静的IMU TFの実需要を調べ、不要な取得を省く。
ただしFIFOを読まない場合のSDK側の蓄積・再購読時の古いサンプル、再開時の時刻状態も
確認する。購読者ゼロを理由に単純returnを追加するだけで完了としない。
静的IMU TFの初回配信を失わず、wheel用のIMU配信・既存の間引き・時刻品質を維持する。

### wheel用設定でも位置追跡を有効にする条件がある

zed_sensors.yamlはpos_tracking_enabled=falseだが、共通設定のdepth_stabilization=-1を
上書きしていない。isPosTrackingRequiredはdepth_stabilization!=0を理由に追跡を要求する。
さらにisDepthRequiredはGEN_3以外の位置追跡要求を理由に深度処理を有効にする。
「wheel用ではZED VIOなし」という設定意図に対して、不要な追跡・深度計算が残る経路。

ZED専用のwheel設定で安定化等の依存を明示的に整理する。通常VIO設定には適用しない。
wrapper全体の既存の深度安定化契約を、個別用途に合わせて無条件変更しない。
wheel設定が画像＋校正済みIMUだけで成立することと、SDKの対応条件を確認する。

### 停止済みの重い処理と待機中の処理

| 対象 | 現状と扱い |
| --- | --- |
| 通常VIOの深度計算 | GEN_1追跡に必要。画像配信OFFでも維持する |
| 深度画像・信頼度・視差・点群の取り出し | 配信フラグと購読者で抑止。不要なretrieveMeasureは確認されなかった |
| 左右別・グレー・合成画像 | CATでは無効。対応する画像の取り出しも不要時は行わない |
| JPEG等の圧縮配信 | CATのpublish_compressed=falseでplugin publisher初期化を省略。維持する |
| 物体検出・人体追跡・mapping・自動ROI | 現設定では開始しない。フラグ確認の軽い分岐は残る |
| 点群worker | 深度有効なら起動し、未使用時は条件変数で待機。取得・変換は動かない |
| 画像worker | 未使用時は待機。通常の待機を重い画像処理と混同しない |
| 診断・状態情報 | 必要性を確認して維持。ZED MiniではZED X専用の照度読取りは早期return |

点群workerの起動条件の改善は、上位の問題を直した後に必要性を判断する。
微小な分岐を消すために、停止・終了や再有効化の仕組みを複雑化しない。

## 新しい画像配信制御サービス

受付と適用はZED wrapper内に追加する。サービスの意味はROS画像配信の制御であり、
SDKのカメラgrab、VIO、深度計算やセンサー処理の開始停止ではない。
既存のenable_streamingサービスはSDK映像ストリーミング用なので流用しない。

サービス名案は /zed/zed_node/set_image_stream。フィールド契約は次を基本とする。
名前と型の配置は実装時に既存のinterface依存を調べて決め、実装後の正本へ明記する。
zed_msgsが別配布であることを確認し、D1やnavigationのinterfaceには依存させない。

| 方向 | 項目 | 意味 |
| --- | --- | --- |
| request | enabled | trueで連続配信、falseで停止 |
| request | period_sec | 正の有限値。配信間隔の指定 |
| response | success | 受付・設定適用の成否 |
| response | applied_period_sec | 適用した設定周期。実測の配信周期ではない |
| response | message | 拒否理由等 |

ON中に再度ONを受けてもタイマーやthreadを増殖させず、必要なら周期だけ更新する。
OFFは繰り返し可能とする。周期の検証・状態更新は一括で行い、拒否時に部分適用しない。
NaN、無限大、0以下、撮影fpsを超える要求の扱いを決め、試験と文書で一致させる。
OFF要求でも有効な周期を渡す単純な契約を基本とし、0を停止等の別用途に兼用しない。

画像取得・ROSメッセージ化の前に配信ゲートと周期を確認し、未使用画像の取り出し・
コピーを避ける。SDK内部でVIO等に必要な処理は維持する。JPEG化、D1用cropは加えない。
撮影時刻を維持し、再開時に停止前の画像や同一stampを再配信しない。
OFF応答後の新規配信は止める。すでにDDSへ渡した画像の到着まで取り消せるとは保証しない。

general.pub_frame_rateは既存では画像と深度配信に共通の周期。
新サービスの「画像周期」を実現するために深度やVIOまで減速させない。
既存周期との優先順位・上限を明示し、画像だけの制御が必要な箇所へ実装する。

### 既存利用者との互換性

既存raw topic名と画像内容は維持する。bringupは既定でpanorama_captureを起動し、
同じraw画像を購読する。RViz・operator GUI・既存探索も同topicを参照する。
サービスによるOFFは、それらに対しても画像を止める共通制御である。
D1だけを止める専用制御ではない。購読者が増えてもOFFを自動解除しない。

既存launchでカメラ・VIOまたは必要なIMUを起動する方法は維持するが、
画像配信の既定は利用者の決定によりOFFへ変更する。プロセス再起動後もOFFに戻し、
以前のON状態を自動復元しない。既存の撮影・画像表示・画像録画にも、必要なら同サービスの
ON操作が必要となる。この操作変更をcat_bringupの利用手順に明記する。
画像はONかつ購読者ありで配信する。自動的な利用者別lease・再試行サービス・複数所有者の
調停は追加せず、運用では1つの制御元にする。
rectの配信口の削除や他用途のraw利用停止は今回の目的に含めない。

## 読むソースと設定

- [wrapper本体](zed_components/src/zed_camera/src/zed_camera_component_main.cpp)：startPosTracking、startPathPubTimer、callback_pubPaths、publishSensorsData、threadFunc_pubSensorsData、isPosTrackingRequired、既存service生成。
- [画像・深度処理](zed_components/src/zed_camera/src/zed_camera_component_video_depth.cpp)：retrieveLeftRawImage、processVideoDepth、isDepthRequired、applyDepthSettings、processPointCloud、配信周期の動的設定。
- [共通設定](zed_wrapper/config/common_stereo.yaml)：depth_stabilization、Path既定値、センサー設定。
- [VIO設定](../cat_robot/cat_bringup/config/zed_vio.yaml)と[wheel用設定](../cat_robot/cat_bringup/config/zed_sensors.yaml)。
- [起動監視](../cat_robot/cat_bringup/scripts/zed_supervisor)：カメラ単一所有、odom監視、終了・再起動。既存のretry設定は変更しない。
- [CATのZED運用](../cat_robot/cat_bringup/README.md)と[wrapper保守](LOCAL_MAINTENANCE.md)。

## 完了条件と検証

まず該当テスト・fixtureを読み、カメラを使わない単体試験と設定・launch展開確認を行う。
今回の確認ではこのfork内に既存の専用testファイルは見つからなかったため、実装時に再確認する。
必要な試験は次の通り。

- Path無効時にタイマー・履歴追加が動かず、有効時の既存動作が維持される。
- VIOのSDK内IMU融合、静的TF、wheel用IMU出力を壊さず、不要なROSセンサー取得を省く。
- wheel用の採用設定で不要な追跡・深度要求を出さず、通常GEN_1 VIOは深度を維持する。
- 配信ON/OFF、ON中の周期変更、繰り返し操作、不正周期、未購読、停止との競合を確認する。
- 起動時・再起動時は購読者がいても画像を配信せず、ONサービス後にだけ開始する。
- 画像停止中もVIO・odom監視・既存停止条件が維持される。
- wheel odom構成では画像停止中も必要なIMU出力・時刻品質が維持される。
- raw画像の型・色形式・解像度・frame_id・source時刻を維持し、再開後に古い画像を流さない。
- build/install後に新サービス型とノード実行物が存在し、古いinstallへの隠れた依存がない。

ビルドはROS 2 Humble、実ソースの明示パス、新しいbuild/install/log出力先を使用する。
最大2 workersとし、必要に応じてコンパイラ並列数も2以下に制限する。
インターフェース追加時はそのパッケージを探索・依存ビルド対象に含める。
必要なSDK/CUDAの版と使用したCMake設定を記録し、勝手に依存更新・導入をしない。

**カメラ・実機・ROS launch・simulation・bag再生・D1推論を開始するには、その操作への
明示的な指示が別途必要。** オフライン試験を実機検証と扱わない。
実行許可が得られた場合のみ、VIO出力、画像周期、CPU/GPU、長時間の履歴メモリ増加、
停止再開を比較する。公開SDKの外側のソース調査だけでGPU負荷削減量を断定しない。

## 引き継ぎ時点の証拠

| 対象 | 確認値 |
| --- | --- |
| wrapper HEAD | e20278b461056d1c94733689b513ba9f544fb479 |
| cat_robot HEAD | 5f539ffb5872f79a4d3e784e572d9bbb236101b7 |
| d1vision_ros2 HEAD | 910a197eafd8856a8897961803318c538f9a40ac |
| 元のdirty差分 | 上記3repoのgit status --shortは空。本資料作成でwrapperの文書だけ変更 |
| 環境 | Ubuntu 22.04.5、Python 3.10.12、対象ROS Humble |
| SDK | /usr/local/zed/include/sl/Camera.hppの定義は5.4.1。実行物のリンク版・CUDAは未検証 |
| 入力 | 上記ソース・YAML・小さなdataset.json、校正ファイルSN10028118.confの係数。画像・bag payload・モデルは未読 |
| 調査 | rg、bounded sed/cat、stat、git rev-parse HEAD、git status --short |
| 実行試験 | 0件。build、推論、simulation、実機は未実行 |

旧bag metadataのstat/rgと、存在しない候補ソース名への探索には非0終了があった。
性能試験の失敗ではなく、現存する実ソースとdatasetメタデータで調査を継続した。
実装の報告では新しいソースSHA・dirty diff、入力、環境、正確な実行コマンド、
exit status、pass/fail/skip件数、未検証条件を記録し、完全な検証ログは生成log下へ保存する。
この資料の問題記述を、修正・受入完了の記録として読み替えない。
