#pragma once

#include <cstdint>
#include <filesystem>
#include <string>
#include <vector>

namespace quickfps {

struct RaplDomain {
    std::string name;
    std::filesystem::path energy_path;
    std::filesystem::path max_energy_path;
};

struct RaplSnapshot {
    std::vector<std::uint64_t> energy_uj;
};

class RaplMeter {
public:
    static RaplMeter discover(
        const std::filesystem::path& root = "/sys/class/powercap");

    bool available() const noexcept { return !domains_.empty(); }
    const std::vector<RaplDomain>& domains() const noexcept { return domains_; }

    RaplSnapshot snapshot() const;
    double delta_joules(const RaplSnapshot& begin,
                        const RaplSnapshot& end) const;

private:
    explicit RaplMeter(std::vector<RaplDomain> domains)
        : domains_(std::move(domains)) {}

    std::vector<RaplDomain> domains_;
};

}  // namespace quickfps
