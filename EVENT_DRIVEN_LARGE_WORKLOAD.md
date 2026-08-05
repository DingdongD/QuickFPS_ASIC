# Event-driven large-workload QuickFPS simulation

The strict closed-loop simulator remains the RTL-aligned golden timing model for
small and medium workloads. Large point clouds use a separate native
full-workload mode that executes every FPS iteration but avoids advancing Python
and DRAMsim3 one clock at a time.

## Model hierarchy

| Mode | Functional execution | Bucket/Point timing | Memory timing | Intended use |
|---|---|---|---|---|
| Strict | full closed loop | pre-edge cycle loop | DRAMsim3 or analytical tick model | RTL validation, 1K--128K |
| Event | full closed loop | native discrete events | calibrated bank/row transaction C-model | 256K--1M full workloads |
| Statistical | counters or fitted trends | estimated | estimated | early DSE only |

An event-model result is not an extrapolation. It scans all buckets, performs
all issue/defer/skip decisions, updates every issued point's MDT value, and
generates the complete sampled sequence. Its approximation boundary is the
memory/controller timing model rather than the QuickFPS algorithm.

## Native event engine

`event_sim/quickfps_event_sim.cpp` executes:

- winner-bucket-first traversal for every iteration;
- float32 AABB lower bounds and far-to-sample distances;
- issue, defer, implicit skip, and forced issue;
- real merge-reference state;
- actual MDT updates and deterministic far-point selection;
- finite Bucket FIFO stalls;
- exact configured 4x4 Point-Engine latency per chunk;
- ping-pong chunk load, compute, and write events;
- transaction-level coordinate reads, MDT reads, and MDT writes;
- channel/bank/row decoding, open-row state, row hits/misses, read/write
  turnaround, burst occupancy, and per-DMA-lane injection;
- global far reduction and complete sampled sequence generation.

The event engine advances directly between load completion, compute completion,
write completion, issue, and iteration-boundary events. Simulated accelerator
cycles are retained; idle host loops are removed.

## Build

```bash
bash scripts/build_event_sim.sh
```

The default library is:

```text
build/event_sim/libquickfps_event_sim.so
```

## Run a full workload

```bash
LIB=build/event_sim/libquickfps_event_sim.so

PYTHONPATH=cmodel python3 -m quickfps_cycle.event_cli \
  --preprocessed build/preprocessed_1m_b512 \
  --samples 262144 \
  --event-sim-lib "$LIB" \
  --chunk-points 1024 \
  --bucket-fifo-depth 8 \
  --point-buffer-mode streaming \
  --max-hardware-cycles 10000000000 \
  --max-wall-seconds 86400 \
  --progress-every 1024 \
  --output build/event_1m_b512.json
```

The helper script builds the library and runs the same mode:

```bash
bash scripts/run_event_large_workload.sh \
  build/preprocessed_1m_b512 \
  262144 \
  build/event_1m_b512.json \
  build/event-sim-1m \
  --point-buffer-mode streaming
```

Result files explicitly contain:

```json
{
  "mode": "closed-loop-event",
  "memory_backend": "calibrated-event-dram-cmodel",
  "config": {
    "full_workload_executed": true,
    "extrapolated": false
  },
  "result_classification": {
    "functional_execution": "full-workload",
    "cycle_model": "event-driven",
    "dram_model": "transaction-level bank-row C-model",
    "strict_dramsim3": false,
    "extrapolation": false
  }
}
```

## DRAM calibration

Run the strict DRAMsim3 model and event model on identical point clouds and
configurations. Use completed 64K and 128K results for fitting, and reserve at
least one configuration or point cloud as held-out validation.

```bash
python3 scripts/calibrate_event_dram.py \
  --pair strict_64k_b128.json event_64k_b128.json \
  --pair strict_64k_b512.json event_64k_b512.json \
  --pair strict_128k_b128.json event_128k_b128.json \
  --pair strict_128k_b512.json event_128k_b512.json \
  --holdout 1 \
  --output build/event_dram_calibration.json
```

Apply the profile:

```bash
PYTHONPATH=cmodel python3 -m quickfps_cycle.event_cli \
  --preprocessed build/preprocessed_1m_b512 \
  --samples 262144 \
  --event-sim-lib build/event_sim/libquickfps_event_sim.so \
  --dram-calibration build/event_dram_calibration.json \
  --output build/event_1m_b512_calibrated.json
```

The calibration tool fits the exposed memory contribution rather than blindly
scaling the complete accelerator cycle count. Final papers or reports should
include held-out mean and maximum cycle error. A recommended acceptance target
is mean error no larger than 5% and maximum held-out error no larger than 10%.

## Watchdogs and progress

The event model separates:

- `--max-hardware-cycles`: simulated accelerator-cycle safety limit;
- `--max-wall-seconds`: host execution-time safety limit;
- `--progress-every`: iteration interval for progress and wall-time output.

A one-million-point experiment should normally use a hardware-cycle limit of at
least ten billion rather than the strict model's original 100-million-cycle
default.

## Current boundary

The event model does not reproduce every DRAMsim3 command-queue and refresh
state. It preserves the actual post-partition address order and the major
channel/bank/row timing effects, then relies on matched strict DRAMsim3 runs for
calibration. It currently starts from the beginning of a workload; resumable
checkpoint serialization is not yet claimed.
