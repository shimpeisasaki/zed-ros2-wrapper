// Copyright 2026 CAT workspace contributors
// SPDX-License-Identifier: Apache-2.0
#ifndef RAW_JPEG_PUBLISHER_HPP_
#define RAW_JPEG_PUBLISHER_HPP_

#include <algorithm>
#include <memory>
#include <stdexcept>
#include <image_transport/image_transport.hpp>

namespace stereolabs
{
inline image_transport::Publisher makeRawJpegPublisher(
  rclcpp::Node * node, const std::string & topic, rmw_qos_profile_t qos)
{
  rcl_interfaces::msg::ParameterDescriptor fixed_format;
  fixed_format.read_only = true;
  rcl_interfaces::msg::ParameterDescriptor quality_desc;
  quality_desc.read_only = true;
  rcl_interfaces::msg::IntegerRange range;
  range.from_value = 1;
  range.to_value = 100;
  range.step = 1;
  quality_desc.integer_range.push_back(range);
  const auto quality = node->declare_parameter<int64_t>("video.jpeg_quality", 95, quality_desc);
  // Match compressed_image_transport 2.5.x's native parameter prefix.
  auto prefix = topic.substr(node->get_effective_namespace().length());
  std::replace(prefix.begin(), prefix.end(), '/', '.');
  const auto format = node->declare_parameter<std::string>(prefix + ".format", "jpeg", fixed_format);
  const auto plugin_quality = node->declare_parameter<int64_t>(
    prefix + ".jpeg_quality", quality, quality_desc);
  if (format != "jpeg" || plugin_quality != quality) {
    throw std::invalid_argument(
      "raw_jpeg_only fixes format=jpeg; set quality using video.jpeg_quality");
  }
  // Use image_transport's existing loader/lifetime management and restrict its
  // plugin allowlist before publisher creation. Never create the IPC publisher.
  const auto plugin_prefix = prefix.front() == '.' ? prefix.substr(1) : prefix;
  const std::vector<std::string> jpeg_only{"image_transport/compressed"};
  const auto plugins = node->declare_parameter<std::vector<std::string>>(
    plugin_prefix + ".enable_pub_plugins", jpeg_only, fixed_format);
  if (plugins != jpeg_only) {
    throw std::invalid_argument("raw_jpeg_only permits only image_transport/compressed");
  }
  return image_transport::create_publisher(node, topic, qos);
}
}  // namespace stereolabs
#endif  // RAW_JPEG_PUBLISHER_HPP_
