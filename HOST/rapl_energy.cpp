#include "rapl_energy.hpp"

#include <algorithm>
#include <fstream>
#include <stdexcept>

namespace quickfps {
namespace {

std::uint64_t read_u64(const std::filesystem::path& path) {
    std::ifstream in(path);
    std::uint64_t value = 0;
    if (!(in >> value)) {
        throw std::runtime_error("failed to read RAPL counter: " + path.string());
    }
    return value;
}

std::string read_text(const std::filesystem::path& path) {
    std::ifstream in(path);
    std::string value;
    if (!(in >> value)) {
        throw std::runtime_error("failed to read RAPL name: " + path.string());
    }
    return value;
}

bool is_top_level_package(const std::filesystem::path& path) {
    const std::string filename = path.filename().string();
    if (filename.rfind("intel-rapl:", 0) != 0) {
        return false;
    }
    return std::count(filename.begin(), filename.end(), ':') == 1;
}

}  // namespace

RaplMeter RaplMeter::discover(const std::filesystem::path& root) {
    std::vector<RaplDomain> domains;
    if (!std::filesystem::exists(root)) {
        return RaplMeter({});
    }

    for (const auto& entry : std::filesystem::directory_iterator(root)) {
        const auto path = entry.path();
        if (!is_top_level_package(path)) {
            continue;
        }
        const auto energy = path / "energy_uj";
        const auto maximum = path / "max_energy_range_uj";
        const auto name = path / "name";
        if (std::filesystem::exists(energy) &&
            std::filesystem::exists(maximum) &&
            std::filesystem::exists(name)) {
            try {
                domains.push_back({read_text(name), energy, maximum});
            } catch (const std::exception&) {
                // Permission-restricted domains are omitted.  The caller can
                // still report timing when no readable RAPL package exists.
            }
        }
    }

    std::sort(domains.begin(), domains.end(),
              [](const RaplDomain& a, const RaplDomain& b) {
                  return a.energy_path < b.energy_path;
              });
    return RaplMeter(std::move(domains));
}

RaplSnapshot RaplMeter::snapshot() const {
    RaplSnapshot result;
    result.energy_uj.reserve(domains_.size());
    for (const auto& domain : domains_) {
        result.energy_uj.push_back(read_u64(domain.energy_path));
    }
    return result;
}

double RaplMeter::delta_joules(const RaplSnapshot& begin,
                               const RaplSnapshot& end) const {
    if (begin.energy_uj.size() != domains_.size() ||
        end.energy_uj.size() != domains_.size()) {
        throw std::invalid_argument("RAPL snapshot/domain size mismatch");
    }

    std::uint64_t total_uj = 0;
    for (std::size_t i = 0; i < domains_.size(); ++i) {
        const std::uint64_t maximum = read_u64(domains_[i].max_energy_path);
        const std::uint64_t first = begin.energy_uj[i];
        const std::uint64_t last = end.energy_uj[i];
        total_uj += (last >= first) ? (last - first)
                                    : (maximum - first + last);
    }
    return static_cast<double>(total_uj) * 1.0e-6;
}

}  // namespace quickfps
