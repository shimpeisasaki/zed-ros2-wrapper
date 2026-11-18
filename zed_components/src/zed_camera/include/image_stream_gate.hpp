// Copyright 2026 CAT workspace contributors
// SPDX-License-Identifier: Apache-2.0
#ifndef IMAGE_STREAM_GATE_HPP_
#define IMAGE_STREAM_GATE_HPP_

#include <algorithm>
#include <cmath>
#include <cstdint>

namespace stereolabs
{
// Caller serializes all access, including image retrieval and publication.
class ImageStreamGate
{
public:
  bool configure(bool enabled, double period, double grab_rate, uint64_t resume_after_ns)
  {
    if (!std::isfinite(period) || period <= 0.0 ||
      !std::isfinite(grab_rate) || grab_rate <= 0.0 || period < 1.0 / grab_rate)
    {
      return false;
    }
    enabled_ = enabled;
    period_ = period;
    resume_after_ns_ = resume_after_ns;
    next_sec_ = 0.0;
    ready_ = false;  // Invalidate queued images, including ON->ON.
    return true;
  }

  double period() const {return period_;}

  bool due(uint64_t stamp_ns) const
  {
    return enabled_ && stamp_ns > resume_after_ns_ && stamp_ns > last_ns_ &&
           static_cast<double>(stamp_ns) * 1e-9 >= next_sec_;
  }

  void retrieved(uint64_t stamp_ns, bool available)
  {
    ready_ = available;
    if (available) {
      last_ns_ = stamp_ns;
      const double sec = static_cast<double>(stamp_ns) * 1e-9;
      next_sec_ = next_sec_ == 0.0 ? sec + period_ : std::max(next_sec_ + period_, sec);
    }
  }

  bool take()
  {
    const bool publish = enabled_ && ready_;
    ready_ = false;
    return publish;
  }

private:
  bool enabled_ = false;
  bool ready_ = false;
  double period_ = 1.0;
  double next_sec_ = 0.0;
  uint64_t resume_after_ns_ = 0;
  uint64_t last_ns_ = 0;
};
}  // namespace stereolabs
#endif  // IMAGE_STREAM_GATE_HPP_
