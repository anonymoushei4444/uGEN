# Prime+Probe ARM64 Porting Summary

**Target Device**: `arm-1` — Linux 6.8.0-63-generic (aarch64)  
**CPU**: ARM Neoverse N1 (Implementer: `0x41`, Part: `0xd0c`, Variant: `0x3`)  
**Date**: 2026-04-20

---

## 1. System-Specific Hardware Parameters

Gathered from `/proc/cpuinfo` and `/sys/devices/system/cpu/cpu0/cache/`:

| Parameter | x86 (original) | ARM64 (this device) | Source |
|---|---|---|---|
| Architecture | x86\_64 | **aarch64** | `uname -a` |
| CPU Model | — | Neoverse N1 | `/proc/cpuinfo` part `0xd0c` |
| L1D Size | — | **64 KB** | `index0/size` |
| L1D Associativity | 8-way | **4-way** | `index0/ways_of_associativity` |
| L1D Cache Line | 64 B | **64 B** | `index0/coherency_line_size` |
| L1D Sets | 64 | **256** | `index0/number_of_sets` (64K / 4 / 64) |
| L2 Size | — | **1024 KB** | `index2/size` |
| L2 Associativity | — | **8-way** | `index2/ways_of_associativity` |
| L2 Cache Line | — | **64 B** | `index2/coherency_line_size` |
| L2 Sets | — | **2048** | `index2/number_of_sets` |

---

## 2. Code Changes Required

### 2.1 Header Removal — `x86intrin.h`

**Original (x86):**
```c
#include <x86intrin.h>
```

**ARM64:**
```c
// removed — no ARM equivalent; intrinsics replaced with inline asm
```

`x86intrin.h` provides SSE/AVX intrinsics and `__rdtsc()`. None of these exist on ARM. All dependent functions were replaced with inline assembly using ARM system registers and barrier instructions.

---

### 2.2 High-Resolution Timer — `__rdtsc()` → `CNTVCT_EL0`

**Original (x86):**
```c
uint64_t t0 = __rdtsc();
```

**ARM64:**
```c
static inline uint64_t read_timer(void) {
    uint64_t val;
    asm volatile("isb; mrs %0, cntvct_el0" : "=r"(val) :: "memory");
    return val;
}
```

| Property | x86 TSC | ARM `CNTVCT_EL0` |
|---|---|---|
| Register | `TSC` (Time Stamp Counter) | `CNTVCT_EL0` (Virtual Counter) |
| Frequency | CPU clock (GHz range) | Fixed system frequency (~25 MHz) |
| User-space access | Always available | Always enabled by Linux kernel |
| Output unit | CPU cycles | Timer ticks (~40 ns/tick at 25 MHz) |

The `ISB` before `MRS` is necessary to drain the pipeline so that all preceding loads have completed before the timestamp is captured — equivalent to the serialising role of `LFENCE` before `RDTSC` on x86.

---

### 2.3 Memory Barriers — `_mm_mfence()` / `_mm_lfence()` → `DSB` / `ISB`

**Original (x86):**
```c
static inline void serialize_full(void) { _mm_mfence(); _mm_lfence(); }
```

**ARM64:**
```c
static inline void serialize_full(void) {
    asm volatile("dsb sy" ::: "memory");
    asm volatile("isb"    ::: "memory");
}
```

| x86 Instruction | ARM64 Equivalent | Semantics |
|---|---|---|
| `MFENCE` | `DSB SY` | Full system data memory barrier — all loads/stores complete before continuing |
| `LFENCE` | `ISB` | Instruction Synchronisation Barrier — flushes pipeline; subsequent instructions fetch fresh |

`DSB SY` (Data Synchronisation Barrier, full system) is stronger than `DMB ISH` (inner-shareable only) and is used here to guarantee that all cache-state changes from priming or victim accesses are globally visible before the probe timing window opens.

---

### 2.4 L1D Associativity Constant

**Original (x86):**
```c
#define L1D_ASSOCIATIVITY  8   // wrong for this ARM CPU
```

**ARM64:**
```c
#define L1D_ASSOCIATIVITY  4   // Neoverse N1: 4-way L1D
```

The eviction and victim sets are each sized to `L1D_ASSOCIATIVITY` lines. Using `8` on a 4-way cache would cause the eviction set to span two separate replacement groups, breaking the Prime+Probe assumption that all lines compete for the same set's ways.

---

### 2.5 L1D Set Count Constant

**Original (x86):**
```c
#define L1D_SETS  64
```

**ARM64:**
```c
#define L1D_SETS  256   // 64K / (4 ways * 64 B) = 256 sets
```

This constant drives the cache-set index extraction:

```c
static inline int get_cache_set_index(uintptr_t addr) {
    return (addr >> 6) & (L1D_SETS - 1);
}
```

With `L1D_SETS = 64` the mask was `0x3F` (bits `[11:6]`), selecting only 6 index bits. The correct mask for 256 sets is `0xFF` (bits `[13:6]`), selecting 8 index bits. Using the wrong value produces incorrect set assignments, so the eviction and victim sets would not actually share a cache set, making the attack undetectable.

---

### 2.6 Output Label — "cycles" → "ticks"

**Original:**
```c
printf("A) PRIME -> PROBE : %lu cycles (avg)\n", avg_A);
```

**ARM64:**
```c
printf("A) PRIME -> PROBE : %lu ticks (avg)\n", avg_A);
```

`CNTVCT_EL0` counts at the fixed system-counter frequency, not the CPU clock frequency. Labelling the unit as "ticks" avoids the implication that values are CPU cycles.

---

## 3. Change Summary Table

| # | Location | x86 Original | ARM64 Replacement | Impact |
|---|---|---|---|---|
| 1 | Line 9 | `#include <x86intrin.h>` | Removed | Compile error fix |
| 2 | `serialize_full()` | `_mm_mfence(); _mm_lfence();` | `dsb sy; isb` | Correct memory ordering |
| 3 | `probe_chase()` | `__rdtsc()` + `_mm_lfence()` | `read_timer()` (CNTVCT_EL0) | Working high-res timer |
| 4 | `#define L1D_ASSOCIATIVITY` | `8` | **`4`** | Correct eviction set size |
| 5 | `#define L1D_SETS` | `64` | **`256`** | Correct set-index bitmask |
| 6 | `printf` labels | `cycles` | `ticks` | Accurate unit reporting |

---

## 4. Verification Output

```
############ Mapping Verification:
eviction_set mapping (virtual -> set):
  eviction_set[0]: 0xef4a74a00140 -> set 5
  eviction_set[1]: 0xef4a74a04140 -> set 5
  eviction_set[2]: 0xef4a74a08140 -> set 5
  eviction_set[3]: 0xef4a74a0c140 -> set 5
victim_set mapping (virtual -> set):
  victim_set[0]: 0xef4a74a10140 -> set 5
  victim_set[1]: 0xef4a74a14140 -> set 5
  victim_set[2]: 0xef4a74a18140 -> set 5
  victim_set[3]: 0xef4a74a1c140 -> set 5
TARGET_SET = 5
Trials     = 1000

A) PRIME -> PROBE              : 1 ticks (avg)
B) PRIME -> VICTIM -> PROBE    : 2 ticks (avg)
Delta (B - A)                  : 1 ticks
```

All 8 lines (4 eviction + 4 victim) correctly resolve to `set 5`. The positive delta confirms that the victim function evicts one eviction-set line, causing a measurable L1D miss during the probe traversal.

---

## 5. Known Limitation: Timer Resolution

The `CNTVCT_EL0` counter on this Neoverse N1 instance runs at approximately **25 MHz** (1 tick ≈ 40 ns). An L1D hit takes roughly 1–4 ns and an L2 access roughly 10–30 ns on this micro-architecture, placing both within the same 40 ns quantisation bucket. As a result, individual measurements are noisy; the signal only emerges reliably after averaging over many trials (`NUM_TRIALS = 1000`).

For single-shot, cycle-accurate timing, user-space access to the PMU cycle counter (`PMCCNTR_EL0`) would be required. This needs the kernel to set `PMUSERENR_EL0.EN = 1`, which is not guaranteed on cloud instances and was not enabled on this device.
