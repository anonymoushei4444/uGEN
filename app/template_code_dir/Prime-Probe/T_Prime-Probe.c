// GROUND TRUTH: PRIME-PROBE (Targeting L1D Set)
// - Scenario A: PRIME -> PROBE
// - Scenario B: PRIME -> VICTIM -> PROBE
// Prints average cycles for both scenarios and the delta.

#define _GNU_SOURCE
#include <stdio.h>
#include <stdint.h>
#include <x86intrin.h>
#include <stdlib.h>
#include <unistd.h>
#include <sys/mman.h>
#include <sched.h>
#include <time.h>


#include <fcntl.h>
#include <sys/types.h>
#include <unistd.h>
/********************/

// ------------ constants ------------
#define PAGE_SIZE            4096
#define CACHE_LINE_SIZE        64
#define L1D_ASSOCIATIVITY       8   
#define L1D_SETS               64   
#define TARGET_SET              5   
#define NUM_PAGES            2048   
#define NUM_TRIALS           1000   
#define VICTIM_ROUNDS         100   


static inline int get_cache_set_index(uintptr_t addr) {
    return (addr >> 6) & (L1D_SETS - 1);
}
static inline void serialize_full(void) { _mm_mfence(); _mm_lfence(); }

// M7. Probe and High-Resolution Timing
static inline uint64_t probe_chase(uint8_t **set) {
    volatile uint8_t *p = set[0];
    _mm_lfence();
    uint64_t t0 = __rdtsc();
    _mm_lfence();
    for (int k = 0; k < L1D_ASSOCIATIVITY; k++) {
        p = *(volatile uint8_t **)p; // dependent, volatile loads
    }
    _mm_lfence();
    uint64_t t1 = __rdtsc();
    _mm_lfence();
    asm volatile ("" :: "r"(p) : "memory"); // keep live
    return t1 - t0;
}

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
        *(uint8_t**)cur = nxt; // pointer at bytes [0..7] of the line
    }
}

// M4. Prime Function
static inline void prime_chase(uint8_t **set) {
    volatile uint8_t *p = set[0];
    for (int k = 0; k < L1D_ASSOCIATIVITY; k++) {
        p = *(volatile uint8_t **)p; // dependent, volatile loads
    }
    asm volatile ("" :: "r"(p) : "memory");
}

// M5. Victim Function
/* Accessing one cache line */
static void victim_function(uint8_t **victim, int *indices) {
    // Touch only the first cache line in the victim set, away from [0..7] pointer area
    for (int r = 0; r < VICTIM_ROUNDS; r++) {
        uint8_t *a = victim[0] + 8; // Only victim[0], offset +8
        a[0] ^= (uint8_t)r;         // write to allocate in L1D
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
    // Allocate a pool to find lines that map to TARGET_SET
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
        fprintf(stderr, "Failed to gather 8+8 lines for set %d\n", TARGET_SET);
        return 1;
    }

    // M3. Pointer-Chase Linked List Setup
    // Build random pointer-chase rings (attacker & victim)
    int perm[L1D_ASSOCIATIVITY]; 
    for (int i = 0; i < L1D_ASSOCIATIVITY; i++) 
        perm[i] = i;

    shuffle_indices(perm, L1D_ASSOCIATIVITY);
    build_linked_list(eviction_set, perm);
    shuffle_indices(perm, L1D_ASSOCIATIVITY);
    build_linked_list(victim_set, perm);

    // Output and Result Reporting (Mapping Verification)
    printf("############ Mapping Verification:\n");
    print_set_mapping("eviction_set", eviction_set, L1D_ASSOCIATIVITY);
    print_set_mapping("victim_set", victim_set, L1D_ASSOCIATIVITY);

    // ---- Two scenarios averaged over NUM_TRIALS ----
    // M7. Scenario Sequencing and Averaging
    uint64_t t1_total = 0, t2_total = 0;
    int idx[L1D_ASSOCIATIVITY]; 
    for (int i=0;i<L1D_ASSOCIATIVITY;i++) 
        idx[i]=i;

    for (int trial = 0; trial < NUM_TRIALS; trial++) {
        // Scenario A: PRIME -> PROBE
        // M4. Prime Function
        prime_chase(eviction_set);
        serialize_full();
        // M6. Probe and High-Resolution Timing
        uint64_t t1 = probe_chase(eviction_set);
        t1_total += t1;

        // Scenario B: PRIME -> VICTIM -> PROBE
        // M4. Prime Function
        prime_chase(eviction_set);
        serialize_full();
        // M5. Victim Function
        victim_function(victim_set, idx);
        serialize_full();
        // M6. Probe and High-Resolution Timing
        uint64_t t2 = probe_chase(eviction_set);
        t2_total += t2;
    }

    // M7, M8. Delta Calculation and Cache Contention Detection
    uint64_t avg_A = t1_total / NUM_TRIALS;
    uint64_t avg_B = t2_total / NUM_TRIALS;

    // Output and Result Reporting
    printf("TARGET_SET = %d\n", TARGET_SET);
    printf("Trials     = %d\n", NUM_TRIALS);
    printf("\nA) PRIME -> PROBE              : %lu cycles (avg)\n", avg_A);
    printf("B) PRIME -> VICTIM -> PROBE    : %lu cycles (avg)\n", avg_B);
    printf("Delta (B - A)                  : %ld cycles\n", (long)(avg_B - avg_A));

    munmap(pool, pool_sz);
    return 0;
}