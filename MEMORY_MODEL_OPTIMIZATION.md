# QuickFPS memory-model optimization

This branch now separates functional correctness, accelerator-cycle timing, and
DRAM timing without using a single fixed-latency memory approximation.

## Point Buffer residency

The modeled Point Buffer is 16 KiB by default.  Each point consumes 12 B of
coordinates and 4 B of MDT state, so a complete 1024-point cloud fits exactly.

```text
working_set_bytes = point_count * (12 + 4)
```

`--point-buffer-mode auto` therefore keeps up to 1024 points resident during
the timed FPS sampling window. Coordinate/MDT reads and MDT writes become
synchronous local-SRAM operations and do not generate repeated DDR traffic.
The initial preload is reported as excluded rather than silently added to the
accelerator cycle count.

Modes:

- `auto`: resident only when the complete working set fits;
- `streaming`: always generate DDR traffic;
- `resident`: require the complete working set to fit or reject the run.

Example:

```bash
PYTHONPATH=cmodel python3 -m quickfps_cycle \
  --preprocessed build/preprocessed \
  --samples 256 \
  --point-buffer-mode auto \
  --no-events \
  --output build/result.json
```

## Independent DMA streams

The closed-loop Point-Engine no longer injects coordinate reads, MDT reads, and
MDT writes through one head-of-line FIFO. It maintains independent queues and
outstanding windows for:

```text
coord_read
mdt_read
mdt_write
```

The default arbiter is round robin. `--dma-stream-outstanding` limits each
stream independently. `--dma-arbiter priority` is retained as a diagnostic
baseline.

## Batched DRAMsim3 bridge

The DRAMsim3 C ABI supports batched transaction submission and completion
polling. The Python scheduler still makes all cycle-level decisions, but up to
`dma_channels` ready 64-B transactions cross the Python/C++ boundary in one
call. This reduces ctypes overhead without changing request addresses, order,
queue acceptance, DRAM clock ticks, or completion dependencies.

The batched path is selected automatically whenever `--dramsim3-lib` and
`--dramsim3-config` are supplied.

## Functional-kernel acceleration

`--functional-kernel auto` uses a NumPy float32 distance kernel when NumPy is
available and falls back to the scalar reference otherwise. `scalar` remains
the strict reference mode; `numpy` requires NumPy and fails explicitly if it is
not installed.

For final numerical validation, compare both kernels on the target point cloud.
The generated sampled sequence and final MDT state must match.

## Large-workload command

```bash
LIB=$(find build/dramsim3_bridge \
  -name 'libquickfps_dramsim3_bridge.so' -print -quit)
CFG=build/dramsim3_bridge/_deps/dramsim3_external-src/configs/DDR4_8Gb_x8_2400.ini

PYTHONPATH=cmodel python3 -m quickfps_cycle \
  --preprocessed build/preprocessed \
  --samples 30000 \
  --chunk-points 1024 \
  --point-buffer-mode streaming \
  --functional-kernel auto \
  --dma-arbiter round_robin \
  --dma-stream-outstanding 16 \
  --dramsim3-lib "$LIB" \
  --dramsim3-config "$CFG" \
  --dramsim3-output-dir build/dramsim3_stats \
  --no-events \
  --output build/closed_loop_dramsim3.json
```

`--no-events` is strongly recommended for point clouds above a few tens of
thousands of points. Counters and summary diagnostics are still preserved.

## Diagnostics

The result JSON now reports:

- average issued buckets per iteration;
- issue/defer/skip ratios;
- average issued points per iteration;
- average deferred merge points per issue;
- coordinate-read, MDT-read, and MDT-write bytes;
- AXI bursts and DRAM transactions;
- effective off-chip bandwidth;
- Point-Engine, Bucket-Engine, and DMA busy fractions;
- DRAMsim3 batch size and backpressure cycles;
- resident/streaming Point Buffer status.

These counters are intended to distinguish algorithmic divergence from memory
model divergence. In particular, large latency error should first be separated
into:

1. too many issued buckets or processed points;
2. insufficient DMA overlap or outstanding depth;
3. low DRAM row locality/effective bandwidth;
4. Point-Engine compute latency.

## Explicit boundary

The model still excludes initial host-to-device transfer latency/energy, SRAM
macro energy unless supplied separately, DDR controller/PHY energy, and DRAM
device energy. The batched bridge is an execution-speed optimization, not a
replacement for DRAMsim3 timing.
