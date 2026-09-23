#include <algorithm>
#include <cstdint>
#include <limits>
#include <new>
#include <vector>

#ifdef _WIN32
#define API extern "C" __declspec(dllexport)
#else
#define API extern "C"
#endif

// Exact integer dynamic programming with bit-packed traceback.
API int stc_embed(const uint8_t* x, const uint32_t* costs,
                  const uint8_t* target, const uint16_t* columns,
                  uint64_t n, uint64_t m, uint32_t height,
                  uint8_t* output, uint64_t* optimum) {
    if (!x || !costs || !target || !columns || !output || !optimum ||
        m == 0 || m > n || height < 1 || height > 15) return -2;
    const uint32_t states = 1u << height;
    const uint64_t inf = uint64_t(1) << 60;
    if (n > (uint64_t(1) << 29) / states * 64) return -3;
    try {
        std::vector<uint64_t> a(states, inf), b(states, inf);
        std::vector<uint64_t> trace((n * states + 63) / 64, 0);
        a[0] = 0;
        for (uint64_t row = 0; row < m; ++row) {
            const uint64_t begin = row * n / m, end = (row + 1) * n / m;
            for (uint64_t i = begin; i < end; ++i) {
                uint64_t cost = costs[i] == UINT32_MAX ? inf : costs[i];
                const uint64_t c0 = x[i] == 0 ? 0 : cost;
                const uint64_t c1 = x[i] == 1 ? 0 : cost;
                const uint32_t mask = columns[i];
                if (mask >= states) return -2;
                for (uint32_t s = 0; s < states; ++s) {
                    uint64_t zero = a[s] + c0, one = a[s ^ mask] + c1;
                    bool choose_one = one < zero;
                    b[s] = std::min(inf, choose_one ? one : zero);
                    if (choose_one) {
                        uint64_t bit = i * states + s;
                        trace[bit >> 6] |= uint64_t(1) << (bit & 63);
                    }
                }
                a.swap(b);
            }
            std::fill(b.begin(), b.end(), inf);
            for (uint32_t s = target[row]; s < states; s += 2) b[s >> 1] = a[s];
            a.swap(b);
        }
        if (a[0] >= inf) return -1;
        *optimum = a[0];
        uint32_t state = 0;
        for (uint64_t row = m; row-- > 0;) {
            state = (state << 1) | target[row];
            const uint64_t begin = row * n / m, end = (row + 1) * n / m;
            for (uint64_t i = end; i-- > begin;) {
                uint64_t bit = i * states + state;
                output[i] = (trace[bit >> 6] >> (bit & 63)) & 1;
                if (output[i]) state ^= columns[i];
            }
        }
        return state == 0 ? 0 : -4;
    } catch (const std::bad_alloc&) { return -3; }
    catch (...) { return -4; }
}

API void stc_extract(const uint8_t* values, const uint16_t* columns,
                     uint64_t n, uint64_t m, uint32_t height, uint8_t* out) {
    std::fill(out, out + m, 0);
    for (uint64_t row = 0; row < m; ++row)
        for (uint64_t i = row * n / m; i < (row + 1) * n / m; ++i)
            if (values[i])
                for (uint32_t bit = 0; bit < height && row + bit < m; ++bit)
                    out[row + bit] ^= (columns[i] >> bit) & 1;
}

// Experimental sign-only optimization. Parities and modification locations are fixed.
// Match residual histograms at three quantizations, conditioned on cover activity.
// This is an explicit feature surrogate, NOT a statistical-security proof.
struct Tap { int dr, dc, value; };

API int balance_signs(const uint8_t* cover, uint8_t* stego, const uint8_t* strata,
                      int height, int width, int rounds, double* before, double* after) {
    try {
        const int n = height * width, bins = 17, levels = 3, groups = 4;
        const std::vector<std::vector<Tap>> filters = {
            {{0,0,-1},{0,1,1}}, {{0,0,-1},{1,0,1}},
            {{0,-1,1},{0,0,-2},{0,1,1}}, {{-1,0,1},{0,0,-2},{1,0,1}},
            {{0,0,-1},{1,1,1}}, {{0,0,-1},{1,-1,1}},
            {{-1,0,1},{0,-1,1},{0,0,-4},{0,1,1},{1,0,1}},
            {{-1,-1,-1},{-1,0,2},{-1,1,-1},{0,-1,2},{0,0,-4},
             {0,1,2},{1,-1,-1},{1,0,2},{1,1,-1}}
        };
        const int nf = int(filters.size()), dimensions = nf * groups * levels * bins;
        std::vector<int16_t> residual(nf * n, 0);
        std::vector<int64_t> counts(dimensions, 0), delta(dimensions, 0);
        std::vector<double> weights(dimensions);
        auto bin = [](int value, int level) {
            const int q = 1 << level;
            int rounded = (std::abs(value) + q / 2) / q;
            if (value < 0) rounded = -rounded;
            return std::max(-8, std::min(8, rounded)) + 8;
        };
        auto index = [&](int f, int p, int level, int value) {
            return (((f * groups + strata[p]) * levels + level) * bins + bin(value, level));
        };
        for (int f = 0; f < nf; ++f) {
            for (int r = 2; r < height - 2; ++r) for (int c = 2; c < width - 2; ++c) {
                int p = r * width + c, original = 0, current = 0;
                for (auto t : filters[f]) {
                    int k = p + t.dr * width + t.dc;
                    original += t.value * cover[k];
                    current += t.value * stego[k];
                }
                residual[f*n+p] = int16_t(current);
                for (int level = 0; level < levels; ++level) {
                    int a = index(f, p, level, original), b = index(f, p, level, current);
                    ++counts[a]; --delta[a]; ++delta[b];
                }
            }
        }
        for (int j = 0; j < dimensions; ++j) weights[j] = 1.0 / (counts[j] + 32.0);
        auto objective = [&]() {
            double result = 0;
            for (int j = 0; j < dimensions; ++j) result += weights[j] * delta[j] * delta[j];
            return result;
        };
        *before = objective();
        std::vector<int> changed;
        for (int r = 16; r < height-16; ++r) for (int c = 16; c < width-16; ++c) {
            int p = r * width + c;
            if (cover[p] != stego[p] && cover[p] > 0 && cover[p] < 255) changed.push_back(p);
        }
        std::vector<int> difference(dimensions, 0), touched;
        std::vector<uint8_t> marked(dimensions, 0);
        int accepted = 0;
        for (int round = 0; round < rounds; ++round) {
            int round_accepted = 0;
            for (size_t z = 0; z < changed.size(); ++z) {
                int p = changed[round % 2 ? changed.size()-1-z : z];
                int step = -2 * (int(stego[p]) - int(cover[p]));
                touched.clear();
                auto add = [&](int idx, int value) {
                    if (!marked[idx]) { marked[idx] = 1; touched.push_back(idx); }
                    difference[idx] += value;
                };
                for (int f = 0; f < nf; ++f) for (auto t : filters[f]) {
                    int center = p - t.dr * width - t.dc;
                    int old = residual[f*n+center], next = old + t.value * step;
                    for (int level = 0; level < levels; ++level) {
                        add(index(f, center, level, old), -1);
                        add(index(f, center, level, next), 1);
                    }
                }
                double gain = 0;
                for (int idx : touched) {
                    double d = difference[idx];
                    gain += weights[idx] * (2.0 * delta[idx] * d + d*d);
                }
                if (gain < -1e-12) {
                    stego[p] = uint8_t(int(stego[p]) + step);
                    for (int idx : touched) delta[idx] += difference[idx];
                    for (int f = 0; f < nf; ++f) for (auto t : filters[f]) {
                        int center = p - t.dr * width - t.dc;
                        residual[f*n+center] += t.value * step;
                    }
                    ++accepted; ++round_accepted;
                }
                for (int idx : touched) { difference[idx] = 0; marked[idx] = 0; }
            }
            if (!round_accepted) break;
        }
        *after = objective();
        return accepted;
    } catch (...) { return -1; }
}
