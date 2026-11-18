#!/usr/bin/env python3
"""Explicitly authorized, bounded camera-only acceptance. Never starts motors.

Run with --hardware --profile vio|sensors|restart after sourcing the fresh install.
Fixtures are the source CAT YAML and connected ZED Mini SN10028118. Image bytes
are never saved. JPEG mode decodes one frame to verify geometry and codec.
"""
import argparse
import json
import math
import os
from pathlib import Path
import signal
import statistics
import subprocess
import time

import cv2
import numpy as np
import rclpy
from rclpy.qos import qos_profile_sensor_data, QoSProfile, DurabilityPolicy
from sensor_msgs.msg import Image, Imu, CameraInfo, CompressedImage
from nav_msgs.msg import Odometry, Path as PathMsg
from geometry_msgs.msg import PoseWithCovarianceStamped
from tf2_msgs.msg import TFMessage
from d1vision_interfaces.srv import SetImageStream


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--hardware', action='store_true', required=True)
    parser.add_argument('--profile', choices=['vio', 'sensors', 'restart', 'path', 'depth'], required=True)
    parser.add_argument('--transport', choices=['jpeg', 'uncompressed'], default='jpeg')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    root = Path(__file__).resolve().parents[3]
    profile = 'vio' if args.profile in ('restart', 'path', 'depth') else args.profile
    config = root / 'src/cat_robot/cat_bringup/config' / f'zed_{profile}.yaml'
    command = [
        'ros2', 'launch', 'zed_wrapper', 'zed_camera.launch.py',
        'camera_model:=zedm', 'camera_name:=zed', 'node_name:=zed_node',
        'serial_number:=10028118', 'publish_urdf:=true', 'publish_tf:=false',
        'publish_map_tf:=false', 'publish_imu_tf:=true', 'enable_gnss:=false',
        'enable_ipc:=false', 'use_sim_time:=false',
        f'ros_params_override_path:={config}',
    ]
    overrides = []
    if args.profile == 'path':
        overrides.extend(['pos_tracking.publish_cam_path:=true', 'pos_tracking.path_max_count:=6'])
    if args.profile == 'depth':
        overrides.append('depth.publish_depth_map:=true')
    if args.transport == 'uncompressed':
        overrides.extend(['video.raw_jpeg_only:=false', 'video.publish_compressed:=false'])
    if overrides:
        command.append('param_overrides:=' + ';'.join(overrides))
    jpeg_mode = args.transport == 'jpeg'
    image_type = CompressedImage if jpeg_mode else Image
    image_topic = 'rgb/color/raw/image' + ('/compressed' if jpeg_mode else '')
    report = {'profile': args.profile, 'transport': args.transport, 'command': command, 'phases': {}, 'checks': []}
    rclpy.init()
    node = rclpy.create_node('image_stream_acceptance')
    messages = {key: [] for key in ['image', 'imu', 'odom', 'pose', 'path', 'info', 'depth']}
    frames = []
    contract = []
    path_lengths = []
    jpeg_sizes = []

    def callback(key):
        def receive(msg):
            stamp = msg.header.stamp.sec + msg.header.stamp.nanosec * 1e-9
            messages[key].append((time.monotonic(), stamp))
            if key == 'path':
                path_lengths.append(len(msg.poses))
            if key == 'image':
                jpeg_sizes.append(len(msg.data))
                if not contract:
                    if jpeg_mode:
                        # Decode one bounded frame to verify a real JPEG, not just its format field.
                        decoded = cv2.imdecode(np.frombuffer(msg.data, np.uint8), cv2.IMREAD_COLOR)
                        if decoded is None:
                            raise AssertionError('Invalid JPEG payload')
                        contract.append({'width': decoded.shape[1], 'height': decoded.shape[0],
                                         'encoding': 'bgr8', 'format': msg.format,
                                         'frame_id': msg.header.frame_id})
                    else:
                        contract.append({'width': msg.width, 'height': msg.height,
                                         'encoding': msg.encoding, 'frame_id': msg.header.frame_id,
                                         'step': msg.step, 'size': len(msg.data)})
        return receive

    subscriptions = [node.create_subscription(typ, '/zed/zed_node/' + topic,
                     callback(key), QoSProfile(depth=10) if key == 'image' else qos_profile_sensor_data)
                     for key, typ, topic in [
                         ('image', image_type, image_topic),
                         ('info', CameraInfo, 'rgb/color/raw/camera_info'),
                         ('imu', Imu, 'imu/data'), ('odom', Odometry, 'odom'),
                         ('pose', PoseWithCovarianceStamped, 'pose_with_covariance'),
                         ('path', PathMsg, 'path_map')]]
    if args.profile == 'depth':
        subscriptions.append(node.create_subscription(
            Image, '/zed/zed_node/depth/depth_registered', callback('depth'), QoSProfile(depth=10)))
    subscriptions.append(node.create_subscription(
        TFMessage, '/tf_static',
        lambda msg: frames.extend(t.child_frame_id for t in msg.transforms),
        QoSProfile(depth=10, durability=DurabilityPolicy.TRANSIENT_LOCAL)))
    client = node.create_client(SetImageStream, '/zed/zed_node/set_image_stream')
    process = None

    def check(name, condition, details=None):
        report['checks'].append({'name': name, 'pass': bool(condition), 'details': details})
        print(json.dumps(report['checks'][-1]), flush=True)
        if not condition:
            raise AssertionError(name)

    def spin(seconds):
        until = time.monotonic() + seconds
        while time.monotonic() < until:
            if process.poll() is not None:
                raise RuntimeError(f'Launch exited {process.returncode}')
            rclpy.spin_once(node, timeout_sec=0.05)

    def phase(name, seconds=4):
        spin(0.5)  # Bound previously queued DDS messages before measurement.
        start = {k: len(v) for k, v in messages.items()}
        spin(seconds)
        result = {}
        for key, values in messages.items():
            rows = values[start[key]:]
            stamps = [row[1] for row in rows]
            diffs = [b-a for a, b in zip(stamps, stamps[1:])]
            result[key] = {'count': len(rows), 'wall_hz': len(rows)/seconds,
                           'source_hz': 1/statistics.mean(diffs) if diffs else None,
                           'min_dt': min(diffs) if diffs else None,
                           'max_dt': max(diffs) if diffs else None}
        if args.profile == 'depth':
            check(f'depth independent during {name}', 18 <= result['depth']['wall_hz'] <= 28)
        report['phases'][name] = result
        print(json.dumps({'phase': name, 'result': result}), flush=True)
        return result

    def service(enabled, period, success=True):
        future = client.call_async(SetImageStream.Request(enabled=enabled, period_sec=period))
        until = time.monotonic() + 10
        while not future.done() and time.monotonic() < until:
            rclpy.spin_once(node, timeout_sec=0.05)
        check(f'service {enabled}/{period}', future.done() and future.result() is not None)
        response = future.result()
        check('service result', response.success == success, response.message)
        if success:
            check('applied period', response.applied_period_sec == period)
        return response

    try:
        with (args.output / f'{args.profile}_launch.log').open('w') as output:
            process = subprocess.Popen(command, stdout=output, stderr=subprocess.STDOUT,
                                       start_new_session=True)
            until = time.monotonic() + 60
            while not client.wait_for_service(timeout_sec=0.2):
                spin(0.1)
                if time.monotonic() > until:
                    raise TimeoutError('Service unavailable after 60 seconds')
            spin(5)
            initial = phase('default_off')
            check('startup images off despite subscriber', initial['image']['count'] == 0)
            check('CameraInfo while images off', initial['info']['count'] > 0)
            if jpeg_mode:
                image_publishers = sorted(topic for topic, types in node.get_topic_names_and_types()
                    if topic.startswith(('/zed/zed_node/rgb/', '/zed/zed_node/left/',
                                         '/zed/zed_node/right/', '/zed/zed_node/stereo/')) and
                    any(t in ('sensor_msgs/msg/Image', 'sensor_msgs/msg/CompressedImage') for t in types)
                    and node.count_publishers(topic) > 0)
                expected = ['/zed/zed_node/' + image_topic]
                check('only requested image publishers', image_publishers == sorted(expected), image_publishers)
                check('no rect CameraInfo', node.count_publishers('/zed/zed_node/rgb/color/rect/camera_info') == 0)
            check('static IMU TF', 'zed_imu_link' in frames, sorted(set(frames)))
            needed = 'odom' if profile == 'vio' else 'imu'
            check('required output while images off', initial[needed]['wall_hz'] > 10)
            if profile == 'vio':
                check('world pose with covariance', initial['pose']['wall_hz'] > 10)
                if args.profile == 'path':
                    check('enabled Path cadence', 1 <= initial['path']['wall_hz'] <= 3)
                    check('enabled Path limit', path_lengths and max(path_lengths) == 6)
                else:
                    check('disabled Path', initial['path']['count'] == 0)
            else:
                check('wheel has no odometry', initial['odom']['count'] == 0)
                check('wheel IMU cadence', 85 < initial['imu']['source_hz'] < 115)
            if args.profile not in ('restart', 'path'):
                for period in [0.0, -1.0, float('nan'), float('inf'), 0.001]:
                    for enabled in [True, False]:
                        service(enabled, period, False)
                check('invalid calls leave stream off', phase('rejected_off', 2)['image']['count'] == 0)
                service(True, 0.2)
                result = phase('five_hz')
                check('5 Hz images', 4 <= result['image']['wall_hz'] <= 6)
                if jpeg_mode:
                    check('raw JPEG contract', contract == [{'width': 672, 'height': 376,
                          'encoding': 'bgr8', 'format': 'bgr8; jpeg compressed bgr8',
                          'frame_id': 'zed_left_camera_frame_optical'}], contract)
                    check('JPEG payload reduced', max(jpeg_sizes) < 758016,
                          {'min': min(jpeg_sizes), 'max': max(jpeg_sizes)})
                else:
                    check('raw contract', contract == [{'width': 672, 'height': 376,
                          'encoding': 'bgr8', 'frame_id': 'zed_left_camera_frame_optical',
                          'step': 2016, 'size': 758016}], contract)
                service(True, 0.1)
                service(True, 0.1)
                result = phase('ten_hz')
                check('10 Hz images', 8 <= result['image']['wall_hz'] <= 12)
                check('required output continues', result[needed]['wall_hz'] > 10)
                service(False, 0.1)
                service(False, 0.1)
                check('OFF stops images', phase('stopped')['image']['count'] == 0)
                before = messages['image'][-1][1]
                resume_time = time.time()
                service(True, 0.2)
                phase('resumed', 2)
                check('fresh increasing source stamps', all(
                    a[1] < b[1] for a, b in zip(messages['image'], messages['image'][1:])))
                check('resume freshness', messages['image'][-1][1] > max(before, resume_time))
                service(False, 0.2)
                # With no raw subscriber ON/OFF must remain callable.
                node.destroy_subscription(subscriptions[0])
                service(True, 0.2)
                spin(1)
                service(False, 0.2)
                service(True, 0.2)
            report['contract'] = contract
            report['payload_bytes'] = {'min': min(jpeg_sizes), 'max': max(jpeg_sizes)} if jpeg_sizes else None
    finally:
        if process is not None:
            try:
                os.killpg(process.pid, signal.SIGINT)
                process.wait(timeout=15)
            except (ProcessLookupError, subprocess.TimeoutExpired):
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                    process.wait(timeout=5)
                except (ProcessLookupError, subprocess.TimeoutExpired):
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait(timeout=5)
            report['launch_exit'] = process.returncode
        (args.output / f'{args.profile}_results.json').write_text(json.dumps(report, indent=2))
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
