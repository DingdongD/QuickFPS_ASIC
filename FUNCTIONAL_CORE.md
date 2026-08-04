# QuickFPS Functional Core

This branch completes a functionally executable QuickFPS reference around the
existing Bucket-Engine and 4x4 Point-Engine RTL.  It is intended to close
algorithmic correctness before AXI/DDR and physical-memory integration.

## Implemented data path

```text
CPU KD-tree preprocessing
        |
        +-- bucket entries (AABB, point pointer/count, far point, merge count)
        +-- bucket-contiguous coordinates
        +-- MDT initialized to +INF
        v
quickfps_core_top
  +-- bucket_buffer
  +-- Bucket-Engine
  |     +-- bucket reorder traversal
  |     +-- far-point and AABB-distance pipeline
  |     +-- merged / implicit / issue decision
  |     +-- deterministic global far-point reduction
  +-- bucket request FIFO / far-point return FIFO
  +-- merge_buffer
  +-- Point-Engine controller
  |     +-- merge-point pass scheduler
  |     +-- 4x4 PE array
  |     +-- partial-batch lane mask
  |     +-- explicit max_tree4
  +-- coordinate / MDT buffers
  +-- result buffer
```

All maximum reductions use the same rule: larger non-negative squared FP32
distance wins; equal distances select the smaller reordered point index.

## Functional verification

Run all RTL tests with:

```bash
bash scripts/run_functional_core_tests.sh
```

The suite covers:

- Max-Tree lane and cross-cycle tie-breaking;
- buckets whose point count is not divisible by four;
- the existing Point-Engine cycle test;
- a full two-bucket QuickFPS sequence (`0, 7, 3, 5`) for eight collinear
  points.

The GitHub Actions workflow also builds and checks the CPU preprocessing flow.

## CPU preprocessing and energy

Build:

```bash
cmake -S HOST -B build/host -DCMAKE_BUILD_TYPE=Release
cmake --build build/host --parallel
```

Example:

```bash
build/host/quickfps_preprocess \
  --input HOST/test_points.xyz \
  --buckets 2 \
  --samples 4 \
  --repeat 1000 \
  --out build/preprocessed
```

The program performs:

1. optional translation plus one common scale for all three coordinates;
2. deterministic max-range-dimension median KD splitting;
3. bucket-contiguous point reordering;
4. AABB and bucket-entry generation;
5. optional vanilla-FPS golden generation;
6. package-level Linux RAPL energy measurement with counter-wrap handling.

Generated files include:

- `coords.hex` / `coordinates.bin`;
- `dist.hex` / `distances.bin` initialized to positive infinity;
- `buckets.hex` packed to the RTL bucket-entry layout;
- `buckets.csv` and `reorder_map.txt`;
- `golden_indices.txt` when `--samples` is supplied;
- `manifest.json` with phase latency and RAPL energy statistics.

For short point clouds, use enough repetitions that the measured batch lasts at
least roughly 0.1 seconds.  Dynamic preprocessing energy can be reported with
`--idle-power-w`, which subtracts `idle_power * preprocessing_time` from gross
package energy.

## Memory and FIFO contract

The current memory files are behavioral functional models with asynchronous
reads and synchronous writes.  They are not SRAM macro wrappers.

The conservative Bucket-Engine launches one bucket at a time into the bucket
distance pipeline and collects issued-bucket results after bucket traversal.
Consequently the functional top requires:

```text
FIFO_DEPTH >= BUCKETS
```

The default configuration sets both to 512.  An optimized implementation should
collect completed buckets concurrently, after which the FIFO can be reduced to
a small decoupling queue.

## Numerical contract

The existing simplified FP32 add/subtract/multiply units are retained.  The host
normalizes all coordinates to non-negative values using a single common scale,
so squared-distance ordering is preserved and the simplified non-negative
floating-point comparisons remain valid.

This level validates QuickFPS control and sampled sequences; it does not claim
full IEEE-754 compliance.

## Remaining system-integration work

The following are intentionally outside the functional-core completion:

- AXI4/NoC command and response channels;
- DDR burst DMA and bucket chunking;
- coordinate/MDT ping-pong buffers;
- cycle-accurate DRAMsim3 integration;
- SRAM compiler wrappers and synchronous-read adapters;
- optimized bucket-II=1 traversal with concurrent completion collection;
- complete top-level gate simulation, PTPX activity, place-and-route, DFT, and
  signoff.

These should be added only after the functional regressions remain stable under
random memory and FIFO backpressure.
