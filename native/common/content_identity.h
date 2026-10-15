// Content identities for model artifacts. Portable C++17, no runtime dependency.
#pragma once
#include <algorithm>
#include <array>
#include <cstdint>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

namespace aji::identity {

class Sha256 {
    std::array<uint32_t, 8> state_ = {0x6a09e667,0xbb67ae85,0x3c6ef372,0xa54ff53a,0x510e527f,0x9b05688c,0x1f83d9ab,0x5be0cd19};
    std::array<uint8_t, 64> buffer_{};
    size_t used_ = 0;
    uint64_t bytes_ = 0;
    static uint32_t rotate(uint32_t x, unsigned n) { return (x >> n) | (x << (32 - n)); }
    void block(const uint8_t *p)
    {
        static constexpr uint32_t k[] = {
            0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,
            0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,
            0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,
            0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,
            0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,
            0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,
            0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,
            0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2};
        uint32_t w[64];
        for (unsigned i = 0; i < 16; ++i)
            w[i] = (uint32_t)p[4*i] << 24 | (uint32_t)p[4*i+1] << 16 | (uint32_t)p[4*i+2] << 8 | p[4*i+3];
        for (unsigned i = 16; i < 64; ++i) {
            uint32_t a = w[i-15], b = w[i-2];
            w[i] = w[i-16] + (rotate(a,7) ^ rotate(a,18) ^ (a>>3)) + w[i-7] + (rotate(b,17) ^ rotate(b,19) ^ (b>>10));
        }
        auto s = state_;
        for (unsigned i = 0; i < 64; ++i) {
            uint32_t first = s[7] + (rotate(s[4],6) ^ rotate(s[4],11) ^ rotate(s[4],25))
                + ((s[4] & s[5]) ^ (~s[4] & s[6])) + k[i] + w[i];
            uint32_t second = (rotate(s[0],2) ^ rotate(s[0],13) ^ rotate(s[0],22))
                + ((s[0] & s[1]) ^ (s[0] & s[2]) ^ (s[1] & s[2]));
            for (unsigned j = 7; j > 0; --j) s[j] = s[j-1];
            s[4] += first; s[0] = first + second;
        }
        for (unsigned i = 0; i < 8; ++i) state_[i] += s[i];
    }
public:
    void update(const void *data, size_t size)
    {
        const auto *p = static_cast<const uint8_t *>(data); bytes_ += size;
        while (size) {
            size_t n = std::min(size, buffer_.size() - used_);
            std::memcpy(buffer_.data() + used_, p, n); used_ += n; p += n; size -= n;
            if (used_ == buffer_.size()) { block(buffer_.data()); used_ = 0; }
        }
    }
    void integer(uint64_t value)
    {
        uint8_t data[8];
        for (unsigned i = 0; i < 8; ++i) data[7-i] = (uint8_t)(value >> (8*i));
        update(data, sizeof data);
    }
    void text(const std::string &value) { integer(value.size()); update(value.data(), value.size()); }
    std::string hex() const
    {
        Sha256 copy = *this; uint64_t bits = bytes_ * 8;
        uint8_t byte = 0x80; copy.update(&byte, 1); byte = 0;
        while (copy.used_ != 56) copy.update(&byte, 1);
        copy.integer(bits);
        const char *digits = "0123456789abcdef"; std::string result;
        for (auto word : copy.state_)
            for (int shift = 28; shift >= 0; shift -= 4) result += digits[(word >> shift) & 15];
        return result;
    }
};

using File = std::pair<std::string, std::filesystem::path>;

// Logical names and byte lengths are framed, so boundaries cannot alias. Paths
// outside the artifact tree, host mtimes and enumeration order are not identity.
inline std::string files(const std::string &domain, std::vector<File> input)
{
    namespace fs = std::filesystem;
    std::sort(input.begin(), input.end(), [](const File &a, const File &b) { return a.first < b.first; });
    Sha256 hash; hash.text("animejanai-content-v1"); hash.text(domain); hash.integer(input.size());
    std::string previous; bool first = true;
    std::array<char, 65536> buffer;
    for (const auto &file : input) {
        if (!first && file.first == previous) throw std::runtime_error("Duplicate artifact identity: " + file.first);
        first = false; previous = file.first;
        if (!fs::is_regular_file(file.second)) throw std::runtime_error("Model resource missing: " + file.second.string());
        auto size = fs::file_size(file.second); auto modified = fs::last_write_time(file.second);
        std::ifstream stream(file.second, std::ios::binary);
        if (!stream) throw std::runtime_error("Cannot read model resource: " + file.second.string());
        hash.text(file.first); hash.integer(size);
        uintmax_t read = 0;
        while (stream) {
            stream.read(buffer.data(), buffer.size()); auto count = stream.gcount();
            hash.update(buffer.data(), (size_t)count); read += (uintmax_t)count;
        }
        if (!stream.eof() || read != size || fs::file_size(file.second) != size || fs::last_write_time(file.second) != modified)
            throw std::runtime_error("Model resource changed or unreadable: " + file.second.string());
    }
    return hash.hex();
}

inline std::vector<File> tree(const std::filesystem::path &root, const std::string &prefix)
{
    namespace fs = std::filesystem;
    if (!fs::is_directory(root)) throw std::runtime_error("Model package missing: " + root.string());
    std::vector<File> result;
    for (const auto &entry : fs::recursive_directory_iterator(root)) {
        if (entry.is_directory()) {
            // A package may itself be a link (the macOS installer). Nested
            // directory links are rejected rather than silently omitting weights.
            if (entry.is_symlink()) throw std::runtime_error("Nested model directory link unsupported: " + entry.path().string());
        } else if (entry.is_regular_file())
            result.emplace_back(prefix + entry.path().lexically_relative(root).generic_u8string(), entry.path());
        else throw std::runtime_error("Unreadable model package resource: " + entry.path().string());
    }
    return result;
}

} // namespace aji::identity
