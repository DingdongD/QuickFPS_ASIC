# Native strict Bucket-Engine scheduler

The closed-loop simulator can execute the RTL-aligned Bucket-Engine scheduler in
C++ while retaining the existing Python Point-Engine, DMA, DRAMsim3, and PTPX
interfaces.

## Migrated state

`native_scheduler/quickfps_bucket_scheduler.cpp` owns the following live state:

- winner-bucket-first traversal order;
- synchronous Bucket Buffer read requests and responses;
- four-stage Bucket-CD latency and input II;
- in-flight-CD plus decision-FIFO credit accounting;
- issue, defer, implicit-skip, and forced-issue decisions;
- per-bucket merge-buffer sampled-point indices;
- finite Bucket FIFO backpressure at the decision head;
- FarPoint writeback latency and bucket far state;
- outstanding issued-bucket count;
- deterministic global far reduction and next-sample generation.

The C++ implementation uses separate float32 intermediate operations and is
compiled with floating-point contraction disabled. Tie breaking remains:

```text
larger distance wins;
equal distance -> smaller reordered point index wins.
```

## Python/C++ boundary

The Python loop still owns:

- real MDT values and their functional updates;
- Point-Engine chunk timing;
- Point Buffer resident/streaming policy;
- coordinate-read, MDT-read, and MDT-write DMA queues;
- analytical DDR or DRAMsim3 clocking;
- PTPX activity counters and result serialization.

At each accelerator edge Python sends only:

```text
bucket_fifo_ready_before
optional FarPoint result
external Point-Engine + memory idle state
```

C++ returns at most one issued bucket, its frozen merge-reference indices, and
an optional iteration-complete/next-sample event. This removes per-bucket Python
objects and Python-side FIFO/pipeline bookkeeping while preserving the strict
pre-edge contract.

## Build

```bash
bash scripts/build_native_scheduler.sh
```

The default output is:

```text
build/native_scheduler/libquickfps_bucket_scheduler.so
```

## Run

```bash
LIB=build/native_scheduler/libquickfps_bucket_scheduler.so

PYTHONPATH=cmodel python3 -m quickfps_cycle \
  --preprocessed build/preprocessed \
  --samples 4096 \
  --bucket-scheduler native \
  --native-bucket-scheduler-lib "$LIB" \
  --point-buffer-mode streaming \
  --functional-kernel auto \
  --no-events \
  --output build/native_result.json
```

`--bucket-scheduler auto` selects the native backend when the library exists at
the default build path and otherwise falls back to the Python reference.
`--bucket-scheduler python` always selects the reference scheduler.

For large experiments, `--no-events` remains recommended. The native backend
still returns all counters and final functional state.

## Validation

The native workflow performs three checks:

1. C++ library compilation;
2. cycle/counter/sample/MDT differential tests against the Python strict
   scheduler in resident and streaming modes;
3. an end-to-end public-CLI run from KD-tree preprocessing with the sequence
   `0,7,3,5`.

The differential test compares Bucket-CD inputs, FIFO occupancies and stalls,
Bucket Buffer read/write activity, issue/defer/skip counts, forced issues,
outstanding buckets, Point-Engine activity, final MDT values, and complete
bucket far state.

## Performance boundary

This migration removes the `iterations x buckets` Python decision workload, but
the top-level simulator still advances accelerator cycles in Python to keep the
Point-Engine and DRAM backend synchronized. Very large 25%-sampling experiments
can therefore remain expensive. A future native top-level event loop may move
Point-Engine timing and DRAM clock dispatch into the same C++ process; that is a
separate optimization and is not required for cycle equivalence of the current
Bucket-Engine migration.
