# Closed-loop QuickFPS cycle simulator

The closed-loop mode joins CPU KD-tree preprocessing, QuickFPS functional
state, hardware timing, memory timing, and sampled-point generation in one
iterative simulation.

## What changed

The older timing path consumed a workload containing precomputed
`issue/defer/skip` actions and precomputed sampled indices. That mode remains
available as `trace-replay` for fast design-space studies.

Closed-loop mode instead loads the actual preprocessing image:

```text
coords.hex
  reordered FP32 coordinates

dist.hex
  initial MDT values, normally +INF

buckets.csv
  AABB, point pointer/count, and initial bucket far index

reorder_map.txt
  reordered index -> original input index

manifest.json
  point/bucket/sample counts, preprocessing latency, and RAPL energy
```

The cycle loop then performs:

```text
current sampled point
        |
        v
winner-bucket-first descriptor traversal
        |
        v
AABB lower bound + far-point-to-sample distance
        |
        v
issue / defer / implicit skip
        |
        +---- defer: append the current sample to the bucket merge buffer
        |
        +---- skip: retain the existing bucket far point
        |
        `---- issue
               |
               v
       bucket FIFO -> ping-pong coordinate/MDT loads
               |
               v
       timed 4x4 Point-Engine execution
               |
               v
       real MDT update for every processed point
               |
               v
       MDT writeback -> real bucket far result
               |
               v
       FarPoint FIFO -> bucket descriptor writeback
        |
        v
global bucket far reduction
        |
        v
next sampled point and next iteration
```

The simulator therefore no longer reads the next sampled point from a trace.
It derives the next point from the live MDT and bucket states.

## Run from a preprocessing directory

```bash
PYTHONPATH=cmodel python3 -m quickfps_cycle \
  --preprocessed build/preprocessed \
  --samples 256 \
  --chunk-points 256 \
  --bucket-decision-fifo-depth 8 \
  --bucket-fifo-depth 8 \
  --far-fifo-depth 8 \
  --output build/closed_loop_result.json
```

When `--samples` is omitted, `sample_count` is read from `manifest.json`.
The default first sampled point is reordered index zero and can be changed with
`--first-sample`.

If `golden_indices.txt` exists, the CLI compares the dynamically generated
sequence against it and fails on a mismatch. Use `--no-golden-check` only for
experiments intentionally using a different numerical or tie-breaking policy.

## One-command raw-point-cloud flow

```bash
bash scripts/run_closed_loop_e2e.sh \
  HOST/test_points.xyz \
  2 \
  4 \
  build/closed-loop-e2e \
  --chunk-points 4 \
  --bucket-fifo-depth 2 \
  --far-fifo-depth 2
```

This performs:

```text
XYZ input
 -> common-scale normalization
 -> deterministic max-range median KD partition
 -> bucket-contiguous reorder and metadata generation
 -> closed-loop cycle simulation
 -> comparison against vanilla-FPS golden indices
```

## DRAMsim3 and PTPX

Closed-loop mode uses the same memory and energy backends as trace replay:

```bash
PYTHONPATH=cmodel python3 -m quickfps_cycle \
  --preprocessed build/preprocessed \
  --samples 256 \
  --dramsim3-lib build/dramsim3_bridge/libquickfps_dramsim3_bridge.so \
  --dramsim3-config path/to/DDR4_8Gb_x8_2400.ini \
  --ptpx-energy reports/quickfps_cycle_strict_1ghz_energy.json \
  --output build/closed_loop_dramsim3_energy.json
```

The output includes:

- reordered and original sampled-point sequences;
- accelerator cycles and seconds;
- preprocessing and partial end-to-end latency;
- dynamic action, FIFO, Point-Engine, DMA, and DRAM counters;
- final MDT and bucket far-state summary;
- PTPX-composed characterized logic energy when supplied;
- RAPL preprocessing energy when available.

## Numerical and timing contract

Functional squared distances use explicit FP32 rounding after subtract,
multiply, and add steps, matching the existing workload generator's numerical
contract. Larger distance wins; equal distances select the smaller reordered
point index.

The timing path retains:

- strict pre-edge bucket-decision credit semantics;
- four-cycle Bucket-CD latency and input II=1;
- registered Bucket and FarPoint FIFO visibility;
- RTL-calibrated 4x4 Point-Engine latency;
- finite merge-buffer capacity with forced issue on defer overflow;
- two-slot chunk ping-pong scheduling;
- AXI burst and DRAM transaction separation;
- analytical banked-DDR or clock-scaled official DRAMsim3 timing.

## Remaining boundary

The accelerator FPS iterations are now functionally and temporally closed.
The following remain outside the reported accelerator cycle count unless added
by a future system-level transport model:

- initial host-to-device transfer of coordinates, MDT, and bucket metadata;
- CPU preprocessing execution inside the cycle clock domain;
- physical AXI interconnect and DDR controller/PHY timing;
- SRAM macro and DRAM-device energy unless separately supplied;
- place-and-route, clock-tree, routed-interconnect, and DFT effects.

CPU preprocessing latency and RAPL energy are still carried into the JSON as a
separate host stage, so end-to-end software-plus-accelerator accounting can be
reported without pretending that CPU time is an ASIC cycle count.
