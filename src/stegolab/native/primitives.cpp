// Batch the existing STEG-BP/1 operations without changing a single wire byte.
// Cryptographic hashing is provided by Windows CNG, not implemented here.
#include <algorithm>
#include <cstdint>
#include <cstring>
#include <limits>
#include <vector>

#ifdef _WIN32
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>
#include <bcrypt.h>
#define API extern "C" __declspec(dllexport)

namespace {
class Hmac {
    BCRYPT_ALG_HANDLE algorithm = nullptr;
    BCRYPT_HASH_HANDLE hash = nullptr;
    std::vector<uint8_t> object;
public:
    Hmac() = default;
    Hmac(const Hmac&) = delete;
    Hmac& operator=(const Hmac&) = delete;
    ~Hmac() {
        if (hash) BCryptDestroyHash(hash);
        if (!object.empty()) SecureZeroMemory(object.data(), object.size());
        if (algorithm) BCryptCloseAlgorithmProvider(algorithm, 0);
    }
    bool initialize(const uint8_t* key, uint64_t length) {
        if (length > std::numeric_limits<ULONG>::max() || (!key && length)) return false;
        if (BCryptOpenAlgorithmProvider(&algorithm, BCRYPT_SHA256_ALGORITHM,
                MS_PRIMITIVE_PROVIDER, BCRYPT_ALG_HANDLE_HMAC_FLAG | BCRYPT_HASH_REUSABLE_FLAG) < 0)
            return false;
        ULONG size = 0, received = 0;
        if (BCryptGetProperty(algorithm, BCRYPT_OBJECT_LENGTH,
                reinterpret_cast<PUCHAR>(&size), sizeof(size), &received, 0) < 0)
            return false;
        object.resize(size);
        return BCryptCreateHash(algorithm, &hash, object.data(), size,
                const_cast<PUCHAR>(key), ULONG(length), BCRYPT_HASH_REUSABLE_FLAG) >= 0;
    }
    bool digest(const uint8_t* input, ULONG length, uint8_t* output) {
        // Finishing a reusable hash resets it to the same keyed initial state.
        return BCryptHashData(hash, const_cast<PUCHAR>(input), length, 0) >= 0
            && BCryptFinishHash(hash, output, 32, 0) >= 0;
    }
};

void big_endian(uint8_t* output, uint64_t value, unsigned bytes) {
    for (unsigned i = 0; i < bytes; ++i) output[bytes - 1 - i] = uint8_t(value >> (i * 8));
}

bool stream_block(Hmac& hmac, uint64_t counter, uint8_t* output) {
    const char label[] = "STEG-BP/1/stream";
    uint8_t message[sizeof(label) + 8];
    std::memcpy(message, label, sizeof(label)); // Include the required NUL separator.
    big_endian(message + sizeof(label), counter, 8);
    return hmac.digest(message, sizeof(message), output);
}
}

API int wire_backend_version() { return 1; }

API int wire_stream(const uint8_t* key, uint64_t key_length, uint64_t first,
                    uint64_t blocks, uint8_t* output) {
    if (!output || (blocks && blocks - 1 > UINT64_MAX - first)
            || blocks > SIZE_MAX / 32) return -2;
    try {
        Hmac hmac;
        if (!hmac.initialize(key, key_length)) return -1;
        for (uint64_t i = 0; i < blocks; ++i)
            if (!stream_block(hmac, first + i, output + i * 32)) return -1;
        return 0;
    } catch (...) { return -1; }
}

API int wire_permute(int64_t* values, uint64_t n, const uint8_t* key, uint64_t key_length) {
    if (!values && n) return -2;
    if (n < 2) return 0;
    try {
        Hmac hmac;
        if (!hmac.initialize(key, key_length)) return -1;
        uint8_t block[32];
        unsigned cursor = 32;
        uint64_t counter = 0;
        for (uint64_t i = n - 1; i > 0; --i) {
            const uint64_t bound = i + 1;
            // Reject the HIGH tail exactly as the Python reference does.
            const uint64_t remainder = (uint64_t(0) - bound) % bound;
            const uint64_t threshold = uint64_t(0) - remainder;
            uint64_t value;
            do {
                if (cursor == 32) {
                    if (!stream_block(hmac, counter++, block)) return -1;
                    cursor = 0;
                }
                value = 0;
                for (unsigned j = 0; j < 8; ++j) value = (value << 8) | block[cursor++];
            } while (remainder && value >= threshold);
            std::swap(values[i], values[value % bound]);
        }
        return 0;
    } catch (...) { return -1; }
}

API int wire_columns(uint64_t n, uint64_t m, uint32_t height,
                     const uint8_t* key, uint64_t key_length, uint16_t* output) {
    if (!output || !m || m > n || height < 1 || height > 15
            || m > (uint64_t(1) << 32) || n > UINT64_MAX / m) return -2;
    try {
        Hmac hmac;
        if (!hmac.initialize(key, key_length)) return -1;
        const char label[] = "STEG-BP/1/column";
        uint8_t message[sizeof(label) + 4 + 8], digest[32];
        std::memcpy(message, label, sizeof(label));
        const uint32_t bitmask = (1u << height) - 1;
        const uint32_t forced = 1u | (1u << (height - 1));
        for (uint64_t row = 0; row < m; ++row) {
            big_endian(message + sizeof(label), row, 4);
            const uint32_t active = (1u << std::min<uint64_t>(height, m - row)) - 1;
            for (uint64_t col = row * n / m; col < (row + 1) * n / m; ++col) {
                big_endian(message + sizeof(label) + 4, col, 8);
                if (!hmac.digest(message, sizeof(message), digest)) return -1;
                output[col] = (((uint16_t(digest[0]) << 8 | digest[1]) & bitmask) | forced) & active;
            }
        }
        return 0;
    } catch (...) { return -1; }
}

// Extract H*y without materializing H. Each column's HMAC is independently
// addressed by row/index, so skipping y[i] == 0 does not advance any stream.
API int wire_extract(const uint8_t* values, uint64_t n, uint64_t m, uint32_t height,
                     const uint8_t* key, uint64_t key_length, uint8_t* output) {
    if (!values || !output || !m || m > n || height < 1 || height > 15
            || m > (uint64_t(1) << 32) || n > UINT64_MAX / m
            || n > SIZE_MAX || m > SIZE_MAX) return -2;
    try {
        Hmac hmac;
        if (!hmac.initialize(key, key_length)) return -1;
        std::fill(output, output + m, 0);
        const char label[] = "STEG-BP/1/column";
        uint8_t message[sizeof(label) + 4 + 8], digest[32];
        std::memcpy(message, label, sizeof(label));
        const uint32_t bitmask = (1u << height) - 1;
        const uint32_t forced = 1u | (1u << (height - 1));
        for (uint64_t row = 0; row < m; ++row) {
            big_endian(message + sizeof(label), row, 4);
            const unsigned remaining = unsigned(std::min<uint64_t>(height, m - row));
            const uint32_t active = (1u << remaining) - 1;
            for (uint64_t col = row * n / m; col < (row + 1) * n / m; ++col) {
                if (values[col] > 1) return -2;
                if (!values[col]) continue;
                big_endian(message + sizeof(label) + 4, col, 8);
                if (!hmac.digest(message, sizeof(message), digest)) return -1;
                const uint16_t mask = (((uint16_t(digest[0]) << 8 | digest[1])
                                        & bitmask) | forced) & active;
                for (unsigned bit = 0; bit < remaining; ++bit)
                    output[row + bit] ^= (mask >> bit) & 1;
            }
        }
        return 0;
    } catch (...) { return -1; }
}
#else
// Other platforms retain the original Python implementation.
extern "C" int wire_backend_version() { return 0; }
#endif
