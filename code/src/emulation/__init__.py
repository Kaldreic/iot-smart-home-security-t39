"""emulation — the hardware-free test bed.

Holds the Gilbert-Elliott channel, the crash-report variation model,
AirBugCatcher's exact-id crash matcher (shared device infrastructure) and the
device oracles: the six-bug target, the suppressor, the synthetic scale target,
the live host-native binary and the cause-swap co-present binary. Each oracle
duck-types the tool's rdd.oracle Protocol and touches rdd only through its data
types (rdd.observation.DumpObs, rdd.sprt.Rep). Swapping the package for a real
radio and target device leaves the RDD tool unchanged; each benchmarks/<suite>.py
re-wires its oracle constructor at the device boundary.

The AirBug minimiser arm and the pre-RDD fuzz-campaign and crash-grouping stages
are evaluation code and live in benchmarks (baseline.py / scenario.py).
"""
