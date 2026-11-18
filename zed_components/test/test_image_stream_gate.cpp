// Copyright 2026 CAT workspace contributors
// SPDX-License-Identifier: Apache-2.0
#include "image_stream_gate.hpp"
#include <stdexcept>
#include <limits>
#include <iostream>

void require(bool condition)
{
  if (!condition) {throw std::runtime_error("image stream gate assertion failed");}
}

int main()
{
  using stereolabs::ImageStreamGate;
  ImageStreamGate gate;
  require(!gate.due(1000000000));
  require(!gate.take());
  require(gate.configure(true, 0.2, 30, 1000000000));
  require(!gate.due(1000000000));
  require(gate.due(1100000000));
  gate.retrieved(1100000000, true);
  require(gate.take());
  require(!gate.take());
  require(!gate.due(1100000000));
  require(!gate.due(1200000000));
  require(gate.due(1400000000));
  gate.retrieved(1400000000, true);
  for (double invalid : {0.0, -1.0, 0.001,
    std::numeric_limits<double>::infinity(), std::numeric_limits<double>::quiet_NaN()})
  {
    for (bool enabled : {true, false}) {
      require(!gate.configure(enabled, invalid, 30, 1400000000));
      require(gate.period() == 0.2);
    }
  }
  require(gate.take());  // Rejection preserves pending frame, too.
  gate.retrieved(1600000000, true);
  require(gate.configure(false, 0.2, 30, 1700000000));
  require(!gate.take());
  require(!gate.due(1800000000));
  require(gate.configure(false, 0.2, 30, 1800000000));
  require(gate.configure(true, 0.1, 30, 1900000000));
  require(!gate.due(1800000000));
  require(gate.due(2000000000));
  gate.retrieved(2000000000, true);
  require(gate.configure(true, 0.1, 30, 2000000000));
  require(!gate.take());  // Reconfiguration drops previously queued images.
  require(!gate.due(2000000000));
  gate.retrieved(2100000000, false);  // No subscribers/retrieve failure.
  require(gate.due(2200000000));
  require(!gate.take());
  require(gate.configure(true, 1.0/30, 30, 2200000000));
  require(!gate.configure(true, 1, 0, 0));
  ImageStreamGate restarted;
  require(!restarted.due(3000000000));
  std::cout << "PASS: default OFF, validation atomicity (10 cases), rate limit, "
    "queued frame invalidation, repeats, no reader, freshness, restart\n";
}
