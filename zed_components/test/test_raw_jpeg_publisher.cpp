// Copyright 2026 CAT workspace contributors
// SPDX-License-Identifier: Apache-2.0
// Offline fixture: one synthetic BGR image; no camera, SDK calls or file payloads.
#include "raw_jpeg_publisher.hpp"
#include <rclcpp/rclcpp.hpp>
#include <chrono>
#include <iostream>
#include <sensor_msgs/msg/compressed_image.hpp>

void require(bool condition, const char * message)
{
  if (!condition) {throw std::runtime_error(message);}
}

int main(int argc, char ** argv)
{
  rclcpp::init(argc, argv);
  const std::string topic = "/jpeg_fixture/rgb/color/raw/image";
  auto node = std::make_shared<rclcpp::Node>("jpeg_fixture", "/jpeg_fixture");
  auto pub = stereolabs::makeRawJpegPublisher(node.get(), topic, rmw_qos_profile_default);
  require(pub.getTopic() == topic, "Unexpected JPEG topic");
  int raw_count = 0;
  sensor_msgs::msg::CompressedImage::ConstSharedPtr jpeg;
  auto raw_sub = node->create_subscription<sensor_msgs::msg::Image>(topic, 10,
    [&](sensor_msgs::msg::Image::ConstSharedPtr) {++raw_count;});
  auto sub = node->create_subscription<sensor_msgs::msg::CompressedImage>(topic + "/compressed", 10,
    [&](sensor_msgs::msg::CompressedImage::ConstSharedPtr msg) {jpeg = msg;});
  sensor_msgs::msg::Image image;
  image.header.stamp.sec = 123;
  image.header.stamp.nanosec = 456;
  image.header.frame_id = "test_left_camera_frame_optical";
  image.encoding = "bgr8";
  image.width = 672;
  image.height = 376;
  image.step = image.width * 3;
  image.data.resize(image.step * image.height, 0);
  const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(5);
  while (!jpeg && std::chrono::steady_clock::now() < deadline) {
    rclcpp::spin_some(node);
    if (pub.getNumSubscribers() > 0) {pub.publish(image);}
    rclcpp::sleep_for(std::chrono::milliseconds(20));
  }
  require(jpeg != nullptr, "No JPEG received");
  require(jpeg->format == "bgr8; jpeg compressed bgr8", "Unexpected codec");
  require(jpeg->header == image.header, "Source metadata changed");
  require(jpeg->data.size() > 4 && jpeg->data.size() < image.data.size(), "Unexpected payload size");
  require(jpeg->data[0] == 0xff && jpeg->data[1] == 0xd8, "Missing JPEG SOI");
  require(jpeg->data[jpeg->data.size()-2] == 0xff && jpeg->data.back() == 0xd9, "Missing JPEG EOI");
  require(raw_count == 0 && node->count_publishers(topic) == 0, "Uncompressed publisher exists");
  require(node->count_publishers(topic + "/theora") == 0, "Theora publisher exists");
  auto result = node->set_parameter(rclcpp::Parameter("video.jpeg_quality", int64_t(80)));
  require(!result.successful, "JPEG quality must be read-only");
  auto expect_rejected = [&](const rclcpp::Parameter & parameter) {
      auto options = rclcpp::NodeOptions().parameter_overrides({parameter});
      auto bad_node = std::make_shared<rclcpp::Node>("jpeg_invalid", "/jpeg_fixture", options);
      bool rejected = false;
      try {
        stereolabs::makeRawJpegPublisher(bad_node.get(), topic, rmw_qos_profile_default);
      } catch (const std::exception &) {rejected = true;}
      require(rejected, "Invalid JPEG configuration accepted");
    };
  expect_rejected(rclcpp::Parameter("video.jpeg_quality", int64_t(0)));
  expect_rejected(rclcpp::Parameter("video.jpeg_quality", int64_t(101)));
  expect_rejected(rclcpp::Parameter(".rgb.color.raw.image.format", "png"));
  expect_rejected(rclcpp::Parameter("rgb.color.raw.image.enable_pub_plugins",
    std::vector<std::string>{"image_transport/compressed", "image_transport/raw"}));
  std::cout << "PASS: JPEG codec, source stamp/frame, no raw/theora publisher, "
    "read-only quality, invalid quality/format; bytes=" << jpeg->data.size() << "\n";
  rclcpp::shutdown();
}
