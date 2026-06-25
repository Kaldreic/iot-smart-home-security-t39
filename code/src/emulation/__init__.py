"""emulation — the hardware-free test bed: the Gilbert-Elliott channel, the crash-report variation
model, AirBugCatcher's exact-id crash matcher (shared device infra), and the concrete device oracles
(the real 6-bug target, the suppressor, the synthetic scale, the live native_sim binary, the cause-swap
co-present binary). Replace this whole package with real hardware (a real radio + a real target device)
and the RDD tool is unchanged (each benchmarks/<suite>.py re-wires its oracle constructor at the device
boundary). The device oracles duck-type the tool's rdd.oracle Protocol and depend on rdd only through its
data-types (rdd.observation.DumpObs, rdd.sprt.Rep). The AirBug minimiser arm and the pre-RDD
fuzz-campaign/crash-grouping stages are EVALUATION, and live in benchmarks (baseline.py / scenario.py)."""
