#include "rapl_energy.hpp"

#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <numeric>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

namespace fs = std::filesystem;
using Clock = std::chrono::steady_clock;

namespace quickfps {

constexpr std::uint32_t kPidxWidth = 18;
constexpr std::uint32_t kMcntWidth = 8;
constexpr std::uint32_t kEntryBits = 368 + kPidxWidth + kMcntWidth;

constexpr std::uint32_t E_MINX = 0;
constexpr std::uint32_t E_MINY = 32;
constexpr std::uint32_t E_MINZ = 64;
constexpr std::uint32_t E_MAXX = 96;
constexpr std::uint32_t E_MAXY = 128;
constexpr std::uint32_t E_MAXZ = 160;
constexpr std::uint32_t E_PTR = 192;
constexpr std::uint32_t E_NUMP = 224;
constexpr std::uint32_t E_FX = 240;
constexpr std::uint32_t E_FY = 272;
constexpr std::uint32_t E_FZ = 304;
constexpr std::uint32_t E_FDIST = 336;
constexpr std::uint32_t E_FIDX = 368;
constexpr std::uint32_t E_MCNT = E_FIDX + kPidxWidth;

struct Point {
    float x = 0.0f;
    float y = 0.0f;
    float z = 0.0f;
    std::uint32_t original_index = 0;
};

struct Bounds {
    std::array<float, 3> min{
        std::numeric_limits<float>::infinity(),
        std::numeric_limits<float>::infinity(),
        std::numeric_limits<float>::infinity()};
    std::array<float, 3> max{
        -std::numeric_limits<float>::infinity(),
        -std::numeric_limits<float>::infinity(),
        -std::numeric_limits<float>::infinity()};
};

struct Leaf {
    std::vector<std::uint32_t> ids;
};

struct Bucket {
    Bounds bounds;
    std::uint32_t point_ptr = 0;
    std::uint32_t point_count = 0;
    std::uint32_t far_index = 0;
};

struct BuildResult {
    std::vector<Point> reordered;
    std::vector<std::uint32_t> reordered_to_original;
    std::vector<Bucket> buckets;
    std::array<float, 3> translation{0.0f, 0.0f, 0.0f};
    float common_scale = 1.0f;
};

struct PhaseTimes {
    double normalize_s = 0.0;
    double tree_s = 0.0;
    double reorder_s = 0.0;
};

struct Options {
    fs::path input;
    fs::path output = "quickfps_preprocessed";
    std::size_t bucket_count = 0;
    std::size_t sample_count = 0;
    std::size_t repeat = 1;
    double idle_power_w = 0.0;
    bool normalize = true;
};

float coord(const Point& p, int dim) {
    return dim == 0 ? p.x : (dim == 1 ? p.y : p.z);
}

std::uint32_t float_bits(float value) {
    std::uint32_t bits = 0;
    static_assert(sizeof(bits) == sizeof(value));
    std::memcpy(&bits, &value, sizeof(bits));
    return bits;
}

Bounds compute_bounds(const std::vector<Point>& points,
                      const std::vector<std::uint32_t>& ids) {
    Bounds bounds;
    for (std::uint32_t id : ids) {
        const Point& p = points.at(id);
        const std::array<float, 3> c{p.x, p.y, p.z};
        for (int d = 0; d < 3; ++d) {
            bounds.min[d] = std::min(bounds.min[d], c[d]);
            bounds.max[d] = std::max(bounds.max[d], c[d]);
        }
    }
    return bounds;
}

int split_dimension(const Bounds& bounds) {
    const std::array<float, 3> range{
        bounds.max[0] - bounds.min[0],
        bounds.max[1] - bounds.min[1],
        bounds.max[2] - bounds.min[2]};
    int dim = 0;
    if (range[1] > range[dim]) dim = 1;
    if (range[2] > range[dim]) dim = 2;
    return dim;
}

std::vector<Point> load_xyz(const fs::path& path) {
    std::ifstream in(path);
    if (!in) {
        throw std::runtime_error("cannot open point file: " + path.string());
    }

    std::vector<Point> points;
    std::string line;
    std::uint32_t index = 0;
    while (std::getline(in, line)) {
        if (line.empty() || line[0] == '#') {
            continue;
        }
        std::istringstream iss(line);
        Point p;
        if (!(iss >> p.x >> p.y >> p.z)) {
            throw std::runtime_error("invalid XYZ line: " + line);
        }
        if (!std::isfinite(p.x) || !std::isfinite(p.y) || !std::isfinite(p.z)) {
            throw std::runtime_error("input contains NaN or Inf coordinates");
        }
        p.original_index = index++;
        points.push_back(p);
    }
    if (points.empty()) {
        throw std::runtime_error("input point cloud is empty");
    }
    return points;
}

void normalize_points(std::vector<Point>& points,
                      std::array<float, 3>& translation,
                      float& common_scale) {
    std::vector<std::uint32_t> ids(points.size());
    std::iota(ids.begin(), ids.end(), 0);
    const Bounds bounds = compute_bounds(points, ids);
    translation = bounds.min;
    common_scale = std::max({bounds.max[0] - bounds.min[0],
                             bounds.max[1] - bounds.min[1],
                             bounds.max[2] - bounds.min[2]});
    if (!(common_scale > 0.0f)) {
        common_scale = 1.0f;
    }
    for (Point& p : points) {
        p.x = (p.x - translation[0]) / common_scale;
        p.y = (p.y - translation[1]) / common_scale;
        p.z = (p.z - translation[2]) / common_scale;
    }
}

std::vector<Leaf> build_leaves(const std::vector<Point>& points,
                               std::size_t target_buckets) {
    if (target_buckets == 0 || target_buckets > points.size()) {
        throw std::invalid_argument("bucket count must be in [1, point_count]");
    }

    Leaf root;
    root.ids.resize(points.size());
    std::iota(root.ids.begin(), root.ids.end(), 0);
    std::vector<Leaf> leaves;
    leaves.push_back(std::move(root));

    while (leaves.size() < target_buckets) {
        std::size_t best = leaves.size();
        std::size_t best_size = 0;
        float best_range = -1.0f;
        for (std::size_t i = 0; i < leaves.size(); ++i) {
            if (leaves[i].ids.size() < 2) continue;
            const Bounds b = compute_bounds(points, leaves[i].ids);
            const int dim = split_dimension(b);
            const float range = b.max[dim] - b.min[dim];
            if (leaves[i].ids.size() > best_size ||
                (leaves[i].ids.size() == best_size && range > best_range)) {
                best = i;
                best_size = leaves[i].ids.size();
                best_range = range;
            }
        }
        if (best == leaves.size()) {
            throw std::runtime_error("cannot split leaves to requested bucket count");
        }

        std::vector<std::uint32_t> ids = std::move(leaves[best].ids);
        const Bounds b = compute_bounds(points, ids);
        const int dim = split_dimension(b);
        const std::size_t mid = ids.size() / 2;
        std::nth_element(ids.begin(), ids.begin() + static_cast<std::ptrdiff_t>(mid),
                         ids.end(), [&](std::uint32_t a, std::uint32_t c) {
            const float va = coord(points[a], dim);
            const float vc = coord(points[c], dim);
            return va < vc || (va == vc &&
                               points[a].original_index < points[c].original_index);
        });

        Leaf left, right;
        left.ids.assign(ids.begin(), ids.begin() + static_cast<std::ptrdiff_t>(mid));
        right.ids.assign(ids.begin() + static_cast<std::ptrdiff_t>(mid), ids.end());
        leaves[best] = std::move(left);
        leaves.insert(leaves.begin() + static_cast<std::ptrdiff_t>(best + 1),
                      std::move(right));
    }
    return leaves;
}

BuildResult preprocess_once(const std::vector<Point>& input,
                            std::size_t bucket_count,
                            bool normalize,
                            PhaseTimes& times) {
    BuildResult result;
    std::vector<Point> points = input;

    auto t0 = Clock::now();
    if (normalize) {
        normalize_points(points, result.translation, result.common_scale);
    }
    auto t1 = Clock::now();

    std::vector<Leaf> leaves = build_leaves(points, bucket_count);
    auto t2 = Clock::now();

    result.reordered.reserve(points.size());
    result.reordered_to_original.reserve(points.size());
    result.buckets.reserve(leaves.size());
    std::uint32_t ptr = 0;
    for (Leaf& leaf : leaves) {
        // nth_element defines bucket membership but intentionally leaves the
        // order inside each leaf unspecified. Canonicalize that order so host
        // output, RTL fixtures, and repeated toolchain runs share one index
        // domain.
        std::sort(leaf.ids.begin(), leaf.ids.end(),
                  [&](std::uint32_t a, std::uint32_t b) {
            return points[a].original_index < points[b].original_index;
        });
        Bucket bucket;
        bucket.bounds = compute_bounds(points, leaf.ids);
        bucket.point_ptr = ptr;
        bucket.point_count = static_cast<std::uint32_t>(leaf.ids.size());
        bucket.far_index = ptr;
        for (std::uint32_t id : leaf.ids) {
            result.reordered.push_back(points[id]);
            result.reordered_to_original.push_back(points[id].original_index);
            ++ptr;
        }
        result.buckets.push_back(bucket);
    }
    auto t3 = Clock::now();

    times.normalize_s += std::chrono::duration<double>(t1 - t0).count();
    times.tree_s += std::chrono::duration<double>(t2 - t1).count();
    times.reorder_s += std::chrono::duration<double>(t3 - t2).count();
    return result;
}

class BitPacker {
public:
    explicit BitPacker(std::size_t bits) : bits_(bits, false) {}

    void set(std::size_t offset, std::size_t width, std::uint64_t value) {
        if (offset + width > bits_.size() || width > 64) {
            throw std::out_of_range("bit pack field out of range");
        }
        for (std::size_t i = 0; i < width; ++i) {
            bits_[offset + i] = ((value >> i) & 1u) != 0;
        }
    }

    void set_float(std::size_t offset, float value) {
        set(offset, 32, float_bits(value));
    }

    std::string hex() const {
        static constexpr char digits[] = "0123456789abcdef";
        const std::size_t nibbles = (bits_.size() + 3) / 4;
        std::string out(nibbles, '0');
        for (std::size_t nib = 0; nib < nibbles; ++nib) {
            unsigned value = 0;
            for (std::size_t b = 0; b < 4; ++b) {
                const std::size_t bit = nib * 4 + b;
                if (bit < bits_.size() && bits_[bit]) value |= 1u << b;
            }
            out[nibbles - 1 - nib] = digits[value];
        }
        return out;
    }

private:
    std::vector<bool> bits_;
};

std::vector<std::uint32_t> vanilla_fps(const std::vector<Point>& points,
                                       std::size_t samples) {
    if (samples == 0) return {};
    if (samples > points.size()) {
        throw std::invalid_argument("sample count exceeds point count");
    }
    std::vector<float> mdt(points.size(), std::numeric_limits<float>::infinity());
    std::vector<std::uint32_t> selected;
    selected.reserve(samples);
    std::uint32_t current = 0;
    for (std::size_t k = 0; k < samples; ++k) {
        selected.push_back(current);
        const Point& s = points[current];
        for (std::size_t i = 0; i < points.size(); ++i) {
            const float dx = points[i].x - s.x;
            const float dy = points[i].y - s.y;
            const float dz = points[i].z - s.z;
            const float d = dx * dx + dy * dy + dz * dz;
            mdt[i] = std::min(mdt[i], d);
        }
        if (k + 1 == samples) break;
        current = 0;
        for (std::uint32_t i = 1; i < mdt.size(); ++i) {
            if (mdt[i] > mdt[current] ||
                (mdt[i] == mdt[current] && i < current)) {
                current = i;
            }
        }
    }
    return selected;
}

void write_outputs(const BuildResult& result,
                   const Options& options,
                   const PhaseTimes& avg_times,
                   double gross_energy_j,
                   double dynamic_energy_j,
                   double average_power_w) {
    fs::create_directories(options.output);

    std::ofstream coords_hex(options.output / "coords.hex");
    std::ofstream dist_hex(options.output / "dist.hex");
    std::ofstream coords_bin(options.output / "coordinates.bin", std::ios::binary);
    std::ofstream dist_bin(options.output / "distances.bin", std::ios::binary);
    std::ofstream map_out(options.output / "reorder_map.txt");
    for (std::size_t i = 0; i < result.reordered.size(); ++i) {
        const Point& p = result.reordered[i];
        coords_hex << std::hex << std::setfill('0')
                   << std::setw(8) << float_bits(p.z)
                   << std::setw(8) << float_bits(p.y)
                   << std::setw(8) << float_bits(p.x) << '\n';
        dist_hex << "7f800000\n";
        coords_bin.write(reinterpret_cast<const char*>(&p.x), sizeof(float));
        coords_bin.write(reinterpret_cast<const char*>(&p.y), sizeof(float));
        coords_bin.write(reinterpret_cast<const char*>(&p.z), sizeof(float));
        const float inf = std::numeric_limits<float>::infinity();
        dist_bin.write(reinterpret_cast<const char*>(&inf), sizeof(float));
        map_out << i << ' ' << result.reordered_to_original[i] << '\n';
    }

    std::ofstream bucket_csv(options.output / "buckets.csv");
    std::ofstream bucket_hex(options.output / "buckets.hex");
    bucket_csv << "bucket,minx,miny,minz,maxx,maxy,maxz,point_ptr,point_count,far_index\n";
    for (std::size_t i = 0; i < result.buckets.size(); ++i) {
        const Bucket& b = result.buckets[i];
        const Point& far = result.reordered.at(b.far_index);
        bucket_csv << i << ','
                   << b.bounds.min[0] << ',' << b.bounds.min[1] << ',' << b.bounds.min[2] << ','
                   << b.bounds.max[0] << ',' << b.bounds.max[1] << ',' << b.bounds.max[2] << ','
                   << b.point_ptr << ',' << b.point_count << ',' << b.far_index << '\n';

        BitPacker pack(kEntryBits);
        pack.set_float(E_MINX, b.bounds.min[0]);
        pack.set_float(E_MINY, b.bounds.min[1]);
        pack.set_float(E_MINZ, b.bounds.min[2]);
        pack.set_float(E_MAXX, b.bounds.max[0]);
        pack.set_float(E_MAXY, b.bounds.max[1]);
        pack.set_float(E_MAXZ, b.bounds.max[2]);
        pack.set(E_PTR, 32, b.point_ptr);
        pack.set(E_NUMP, 16, b.point_count);
        pack.set_float(E_FX, far.x);
        pack.set_float(E_FY, far.y);
        pack.set_float(E_FZ, far.z);
        pack.set_float(E_FDIST, std::numeric_limits<float>::infinity());
        pack.set(E_FIDX, kPidxWidth, b.far_index);
        pack.set(E_MCNT, kMcntWidth, 0);
        bucket_hex << pack.hex() << '\n';
    }

    if (options.sample_count != 0) {
        const auto golden = vanilla_fps(result.reordered, options.sample_count);
        std::ofstream golden_out(options.output / "golden_indices.txt");
        for (std::uint32_t index : golden) golden_out << index << '\n';
    }

    std::ofstream manifest(options.output / "manifest.json");
    manifest << std::setprecision(10)
             << "{\n"
             << "  \"point_count\": " << result.reordered.size() << ",\n"
             << "  \"bucket_count\": " << result.buckets.size() << ",\n"
             << "  \"bucket_m_register\": " << (result.buckets.size() - 1) << ",\n"
             << "  \"sample_count\": " << options.sample_count << ",\n"
             << "  \"entry_bits\": " << kEntryBits << ",\n"
             << "  \"normalization_translation\": ["
             << result.translation[0] << ", " << result.translation[1] << ", "
             << result.translation[2] << "],\n"
             << "  \"normalization_common_scale\": " << result.common_scale << ",\n"
             << "  \"avg_normalize_s\": " << avg_times.normalize_s << ",\n"
             << "  \"avg_tree_s\": " << avg_times.tree_s << ",\n"
             << "  \"avg_reorder_s\": " << avg_times.reorder_s << ",\n"
             << "  \"avg_preprocess_s\": "
             << (avg_times.normalize_s + avg_times.tree_s + avg_times.reorder_s) << ",\n"
             << "  \"rapl_gross_energy_j\": " << gross_energy_j << ",\n"
             << "  \"rapl_dynamic_energy_j\": " << dynamic_energy_j << ",\n"
             << "  \"rapl_average_power_w\": " << average_power_w << "\n"
             << "}\n";
}

Options parse_options(int argc, char** argv) {
    Options o;
    for (int i = 1; i < argc; ++i) {
        const std::string arg = argv[i];
        auto require_value = [&](const char* name) -> std::string {
            if (i + 1 >= argc) throw std::invalid_argument(std::string(name) + " requires a value");
            return argv[++i];
        };
        if (arg == "--input") o.input = require_value("--input");
        else if (arg == "--out") o.output = require_value("--out");
        else if (arg == "--buckets") o.bucket_count = std::stoull(require_value("--buckets"));
        else if (arg == "--samples") o.sample_count = std::stoull(require_value("--samples"));
        else if (arg == "--repeat") o.repeat = std::stoull(require_value("--repeat"));
        else if (arg == "--idle-power-w") o.idle_power_w = std::stod(require_value("--idle-power-w"));
        else if (arg == "--no-normalize") o.normalize = false;
        else if (arg == "--help") {
            std::cout << "Usage: quickfps_preprocess --input points.xyz --buckets M [options]\n"
                      << "  --out DIR          output directory\n"
                      << "  --samples K        also generate vanilla-FPS golden indices\n"
                      << "  --repeat R         repeat preprocessing for stable RAPL measurement\n"
                      << "  --idle-power-w P   subtract P*time from gross RAPL energy\n"
                      << "  --no-normalize     preserve original coordinates\n";
            std::exit(0);
        } else {
            throw std::invalid_argument("unknown option: " + arg);
        }
    }
    if (o.input.empty() || o.bucket_count == 0 || o.repeat == 0) {
        throw std::invalid_argument("--input, --buckets, and repeat>0 are required");
    }
    return o;
}

}  // namespace quickfps

int main(int argc, char** argv) {
    try {
        const quickfps::Options options = quickfps::parse_options(argc, argv);
        const auto load_begin = Clock::now();
        const std::vector<quickfps::Point> points = quickfps::load_xyz(options.input);
        const auto load_end = Clock::now();

        quickfps::RaplMeter rapl = quickfps::RaplMeter::discover();
        quickfps::RaplSnapshot energy_begin, energy_end;
        if (rapl.available()) energy_begin = rapl.snapshot();
        const auto prep_begin = Clock::now();

        quickfps::PhaseTimes times;
        quickfps::BuildResult result;
        for (std::size_t r = 0; r < options.repeat; ++r) {
            result = quickfps::preprocess_once(points, options.bucket_count,
                                               options.normalize, times);
        }

        const auto prep_end = Clock::now();
        if (rapl.available()) energy_end = rapl.snapshot();
        const double batch_s = std::chrono::duration<double>(prep_end - prep_begin).count();
        const double average_s = batch_s / static_cast<double>(options.repeat);
        const double gross_batch_j = rapl.available() ?
            rapl.delta_joules(energy_begin, energy_end) : 0.0;
        const double gross_j = gross_batch_j / static_cast<double>(options.repeat);
        const double dynamic_j = std::max(0.0, gross_j - options.idle_power_w * average_s);
        const double average_power_w = average_s > 0.0 ? gross_j / average_s : 0.0;

        times.normalize_s /= static_cast<double>(options.repeat);
        times.tree_s /= static_cast<double>(options.repeat);
        times.reorder_s /= static_cast<double>(options.repeat);
        quickfps::write_outputs(result, options, times,
                                gross_j, dynamic_j, average_power_w);

        const double load_s = std::chrono::duration<double>(load_end - load_begin).count();
        std::cout << std::fixed << std::setprecision(6)
                  << "points=" << points.size()
                  << " buckets=" << options.bucket_count
                  << " repeat=" << options.repeat << '\n'
                  << "load_s=" << load_s << '\n'
                  << "normalize_s=" << times.normalize_s << '\n'
                  << "tree_s=" << times.tree_s << '\n'
                  << "reorder_s=" << times.reorder_s << '\n'
                  << "preprocess_s=" << average_s << '\n';
        if (rapl.available()) {
            std::cout << "rapl_gross_j=" << gross_j << '\n'
                      << "rapl_dynamic_j=" << dynamic_j << '\n'
                      << "rapl_avg_power_w=" << average_power_w << '\n';
        } else {
            std::cout << "rapl=unavailable\n";
        }
        std::cout << "output=" << options.output << '\n';
        return 0;
    } catch (const std::exception& e) {
        std::cerr << "error: " << e.what() << '\n';
        return 1;
    }
}
