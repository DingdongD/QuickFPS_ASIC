# Strict QuickFPS cycle semantics

`python -m quickfps_cycle` now selects the edge-accurate scheduler in
`quickfps_cycle/strict_cycle_model.py`.  The older
`python -m quickfps_cycle.cli` entry point is retained only for compatibility
with existing experiment scripts.

## Bucket decision credits

The RTL `bucket_decision_pipe` computes `in_ready` from the credit count that
exists before the active clock edge:

```text
reserved = entries in bucket_cd + entries in decision FIFO
in_ready = reserved < decision_fifo_depth
```

A decision FIFO pop and a new input acceptance are therefore not permitted to
share an edge when `reserved` was full before that edge.  The released credit is
visible in the next cycle.  The strict scheduler snapshots the pre-edge state
before applying:

1. FarPoint FIFO collection;
2. decision FIFO pop;
3. bucket_cd output write;
4. bucket_cd input acceptance.

This ordering is regression-tested with a four-credit pipeline.  The first four
buckets are accepted in cycles `0,1,2,3`; after saturation, the fifth is
accepted in cycle `6`, not cycle `5`.

## DRAMsim3 clock domain

The official DRAMsim3 API advances one memory clock per `ClockTick()`.  A
QuickFPS simulator step advances one accelerator clock.  These clocks must not
be assumed equal.

`ClockScaledDramSim3Backend` reads `tCK` from the selected DRAMsim3 INI file and
uses a fractional time accumulator:

```text
accelerator_period_ns = 1e9 / accelerator_clock_hz
credit_ns += accelerator_period_ns
while credit_ns >= dram_tCK_ns:
    DRAMsim3.ClockTick()
    credit_ns -= dram_tCK_ns
```

Completions, queue activity, and DMA busy windows are translated back to the
accelerator-cycle domain before they enter the QuickFPS scheduler or PTPX
energy estimator.  The result JSON records both `accelerator_cycles` and
`dram_clock_ticks`.

## Recommended invocation

```bash
PYTHONPATH=cmodel python3 -m quickfps_cycle \
  --workload build/quickfps_workload.json \
  --chunk-points 256 \
  --bucket-decision-fifo-depth 8 \
  --bucket-fifo-depth 8 \
  --far-fifo-depth 8 \
  --output build/strict_cycle_result.json
```

With DRAMsim3:

```bash
bash scripts/build_dramsim3_bridge.sh
LIB=$(find build/dramsim3_bridge \
  -name 'libquickfps_dramsim3_bridge.so' -print -quit)
CFG=build/dramsim3_bridge/_deps/dramsim3_external-src/configs/DDR4_8Gb_x8_2400.ini

PYTHONPATH=cmodel python3 -m quickfps_cycle \
  --workload build/quickfps_workload.json \
  --dramsim3-lib "$LIB" \
  --dramsim3-config "$CFG" \
  --output build/strict_cycle_dramsim3.json
```

## Validation boundary

The strict model is cycle-calibrated against:

- four-cycle bucket-distance latency and II=1 admission;
- registered decision FIFO behavior under full-credit backpressure;
- the 39-cycle 48-point Point-Engine case;
- ping-pong read/compute/write causal order;
- AXI burst and 64-byte DRAM transaction separation;
- reordered-memory and original-point index domains.

It does not claim post-route timing, clock-tree effects, DDR controller/PHY
implementation latency, scan timing, or compiler-macro SRAM energy unless those
are supplied through the PTPX and macro-characterization inputs.
