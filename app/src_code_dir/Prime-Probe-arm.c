// GROUND TRUTH: PRIME-PROBE (Targeting L1D Set)
// - Scenario A: PRIME -> PROBE
// - Scenario B: PRIME -> VICTIM -> PROBE
// Prints average ticks for both scenarios and the delta.
// ARM64 port for Cortex-A78 / Neoverse N1:
//   L1D: 64K, 4-way, 64-byte lines, 256 sets

#define _GNU_SOURCE
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <unistd.h>
#include <sys/mman.h>
#include <sched.h>
#include <time.h>
#include <fcntl.h>
#include <sys/types.h>


// ------------ constants ------------
#define PAGE_SIZE            4096
#define CACHE_LINE_SIZE        64
#define L1D_ASSOCIATIVITY       4   // Neoverse N1: 4-way L1D
#define L1D_SETS              256   // 64K / (4 * 64) = 256 sets
#define TARGET_SET              5
#define NUM_PAGES            2048
#define NUM_TRIALS           1000
#define VICTIM_ROUNDS         100


// ARM64 virtual counter — always accessible from userspace (CNTVCT_EL0).
// ISB before the read drains the pipeline so in-flight loads are visible.
static inline uint64_t read_timer(void) {
    uint64_t val;
    asm volatile("isb; mrs %0, cntvct_el0" : "=r"(val) :: "memory");
    return val;
}

// ARM64 full-system barrier:  DSB SY flushes all pending memory ops,
// ISB flushes the instruction pipeline — equivalent to mfence + lfence.
static inline void serialize_full(void) {
    asm volatile("dsb sy" ::: "memory");
    asm volatile("isb"    ::: "memory");
}

static inline int get_cache_set_index(uintptr_t addr) {
    // bits [6 + log2(256) - 1 : 6] = bits [13:6]
    return (addr >> 6) & (L1D_SETS - 1);
}

// M7. Probe — pointer-chase with ARM64 timing
static inline uint64_t probe_chase(uint8_t **set) {
    volatile uint8_t *p = set[0];
    asm volatile("dsb sy" ::: "memory");
    asm volatile("isb"    ::: "memory");
    uint64_t t0 = read_timer();
    for (int k = 0; k < L1D_ASSOCIATIVITY; k++) {
        p = *(volatile uint8_t **)p;
    }
    asm volatile("dsb sy" ::: "memory");
    uint64_t t1 = read_timer();
    asm volatile("" :: "r"(p) : "memory");
    return t1 - t0;
}

// M3. Pointer-Chase Linked List Setup — helper: shuffle indices
static inline void shuffle_indices(int *a, int n) {
    for (int i = n - 1; i > 0; i--) {
        int j = rand() % (i + 1);
        int t = a[i]; a[i] = a[j]; a[j] = t;
    }
}

// M3. Pointer-Chase Linked List Setup
static void build_linked_list(uint8_t **set, int *perm) {
    for (int i = 0; i < L1D_ASSOCIATIVITY; i++) {
        uint8_t *cur = set[perm[i]];
        uint8_t *nxt = set[perm[(i + 1) % L1D_ASSOCIATIVITY]];
        *(uint8_t**)cur = nxt;
    }
}

// M4. Prime Function
static inline void prime_chase(uint8_t **set) {
    volatile uint8_t *p = set[0];
    for (int k = 0; k < L1D_ASSOCIATIVITY; k++) {
        p = *(volatile uint8_t **)p;
    }
    asm volatile("" :: "r"(p) : "memory");
}

// M5. Victim Function — touches one victim line (offset +8 avoids pointer area)
static void victim_function(uint8_t **victim, int *indices) {
    (void)indices;
    for (int r = 0; r < VICTIM_ROUNDS; r++) {
        uint8_t *a = victim[0] + 8;
        a[0] ^= (uint8_t)r;
        (void)*(volatile uint8_t*)a;
    }
}

void print_set_mapping(const char *label, uint8_t **set, int n) {
    printf("%s mapping (virtual -> set):\n", label);
    for (int i = 0; i < n; i++) {
        uintptr_t vaddr = (uintptr_t)set[i];
        int set_idx = get_cache_set_index(vaddr);
        printf("  %s[%d]: %p -> set %d\n", label, i, (void*)vaddr, set_idx);
    }
}
/***********************************************************************************/

int main(void) {

    // M1, M2. Eviction and Victim Set Construction
    size_t pool_sz = NUM_PAGES * PAGE_SIZE;
    uint8_t *pool = mmap(NULL, pool_sz, PROT_READ | PROT_WRITE,
                         MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    if (pool == MAP_FAILED) { perror("mmap"); return 1; }

    uint8_t *eviction_set[L1D_ASSOCIATIVITY];
    uint8_t *victim_set[L1D_ASSOCIATIVITY];
    int ec = 0, vc = 0;

    for (int page = 0; page < NUM_PAGES; page++) {
        uint8_t *base = pool + page * PAGE_SIZE;
        for (int off = 0; off < PAGE_SIZE; off += CACHE_LINE_SIZE) {
            uint8_t *addr = base + off;
            if (get_cache_set_index((uintptr_t)addr) == TARGET_SET) {
                if (ec < L1D_ASSOCIATIVITY)      eviction_set[ec++] = addr;
                else if (vc < L1D_ASSOCIATIVITY) victim_set[vc++]   = addr;
            }
            if (ec >= L1D_ASSOCIATIVITY && vc >= L1D_ASSOCIATIVITY) break;
        }
        if (ec >= L1D_ASSOCIATIVITY && vc >= L1D_ASSOCIATIVITY) break;
    }
    if (ec < L1D_ASSOCIATIVITY || vc < L1D_ASSOCIATIVITY) {
        fprintf(stderr, "Failed to gather %d+%d lines for set %d\n",
                L1D_ASSOCIATIVITY, L1D_ASSOCIATIVITY, TARGET_SET);
        return 1;
    }

    // M3. Pointer-Chase Linked List Setup
    int perm[L1D_ASSOCIATIVITY];
    for (int i = 0; i < L1D_ASSOCIATIVITY; i++)
        perm[i] = i;

    shuffle_indices(perm, L1D_ASSOCIATIVITY);
    build_linked_list(eviction_set, perm);
    shuffle_indices(perm, L1D_ASSOCIATIVITY);
    build_linked_list(victim_set, perm);

    printf("############ Mapping Verification:\n");
    print_set_mapping("eviction_set", eviction_set, L1D_ASSOCIATIVITY);
    print_set_mapping("victim_set", victim_set, L1D_ASSOCIATIVITY);

    // M7. Scenario Sequencing and Averaging
    uint64_t t1_total = 0, t2_total = 0;
    int idx[L1D_ASSOCIATIVITY];
    for (int i = 0; i < L1D_ASSOCIATIVITY; i++)
        idx[i] = i;

    for (int trial = 0; trial < NUM_TRIALS; trial++) {
        // Scenario A: PRIME -> PROBE
        prime_chase(eviction_set);
        serialize_full();
        uint64_t t1 = probe_chase(eviction_set);
        t1_total += t1;

        // Scenario B: PRIME -> VICTIM -> PROBE
        prime_chase(eviction_set);
        serialize_full();
        victim_function(victim_set, idx);
        serialize_full();
        uint64_t t2 = probe_chase(eviction_set);
        t2_total += t2;
    }

    // M7, M8. Delta Calculation and Cache Contention Detection
    uint64_t avg_A = t1_total / NUM_TRIALS;
    uint64_t avg_B = t2_total / NUM_TRIALS;

    printf("TARGET_SET = %d\n", TARGET_SET);
    printf("Trials     = %d\n", NUM_TRIALS);
    printf("\nA) PRIME -> PROBE              : %lu ticks (avg)\n", avg_A);
    printf("B) PRIME -> VICTIM -> PROBE    : %lu ticks (avg)\n", avg_B);
    printf("Delta (B - A)                  : %ld ticks\n", (long)(avg_B - avg_A));

    munmap(pool, pool_sz);
    return 0;
}
