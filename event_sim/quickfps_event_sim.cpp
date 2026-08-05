#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <exception>
#include <limits>
#include <memory>
#include <queue>
#include <stdexcept>
#include <string>
#include <tuple>
#include <utility>
#include <vector>

namespace {

thread_local std::string g_last_error;

struct Point3 {
    float x = 0.0F;
    float y = 0.0F;
    float z = 0.0F;
};

struct Bucket {
    std::uint32_t point_ptr = 0;
    std::uint32_t point_count = 0;
    Point3 minimum{};
    Point3 maximum{};
    std::uint32_t far_index = 0;
    float far_distance = std::numeric_limits<float>::infinity();
    std::vector<std::uint32_t> merge_indices;
};

float f32(float value) noexcept { return value; }

float distance2(const Point3& a, const Point3& b) noexcept {
    const float dx = f32(a.x - b.x);
    const float dy = f32(a.y - b.y);
    const float dz = f32(a.z - b.z);
    const float xx = f32(dx * dx);
    const float yy = f32(dy * dy);
    const float zz = f32(dz * dz);
    return f32(f32(xx + yy) + zz);
}

float box_distance2(const Point3& point,
                    const Point3& minimum,
                    const Point3& maximum) noexcept {
    float gap_x = 0.0F;
    float gap_y = 0.0F;
    float gap_z = 0.0F;
    if (point.x < minimum.x) {
        gap_x = f32(minimum.x - point.x);
    } else if (point.x > maximum.x) {
        gap_x = f32(point.x - maximum.x);
    }
    if (point.y < minimum.y) {
        gap_y = f32(minimum.y - point.y);
    } else if (point.y > maximum.y) {
        gap_y = f32(point.y - maximum.y);
    }
    if (point.z < minimum.z) {
        gap_z = f32(minimum.z - point.z);
    } else if (point.z > maximum.z) {
        gap_z = f32(point.z - maximum.z);
    }
    const float xx = f32(gap_x * gap_x);
    const float yy = f32(gap_y * gap_y);
    const float zz = f32(gap_z * gap_z);
    return f32(f32(xx + yy) + zz);
}

bool better(float distance,
            std::uint32_t index,
            float best_distance,
            std::uint32_t best_index) noexcept {
    return distance > best_distance ||
           (distance == best_distance && index < best_index);
}

}  // namespace

extern "C" {

struct qfps_event_point {
    float x;
    float y;
    float z;
};

struct qfps_event_bucket_init {
    std::uint32_t point_ptr;
    std::uint32_t point_count;
    float min_x;
    float min_y;
    float min_z;
    float max_x;
    float max_y;
    float max_z;
    std::uint32_t far_index;
    float far_distance;
};

struct qfps_event_config {
    std::uint32_t point_count;
    std::uint32_t bucket_count;
    std::uint32_t sample_count;
    std::uint32_t first_sample;
    std::uint64_t clock_hz;
    std::uint64_t max_hardware_cycles;
    double max_wall_seconds;
    std::uint32_t progress_interval;

    std::uint32_t bucket_cd_latency;
    std::uint32_t bucket_issue_ii;
    std::uint32_t bucket_fifo_depth;
    std::uint32_t merge_buffer_capacity;
    std::uint32_t sram_read_latency;
    std::uint32_t sram_write_latency;

    std::uint32_t chunk_points;
    std::uint32_t pe_rows;
    std::uint32_t pe_cols;
    std::uint32_t pe_cell_latency;
    std::uint32_t merge_load_cycles;
    std::uint32_t point_ctrl_overhead;
    std::uint32_t point_io_pipeline_cycles;

    std::uint32_t coord_bytes_per_point;
    std::uint32_t dist_bytes_per_point;
    std::uint32_t point_buffer_capacity_bytes;
    std::uint32_t point_buffer_mode;
    std::uint32_t dma_channels;
    std::uint32_t dma_command_cycles;
    std::uint32_t dram_transaction_bytes;

    std::uint32_t dram_channels;
    std::uint32_t banks_per_channel;
    std::uint32_t row_bytes;
    std::uint32_t burst_bytes;
    std::uint32_t t_rcd;
    std::uint32_t t_cl;
    std::uint32_t t_rp;
    std::uint32_t t_burst;
    std::uint32_t write_recovery;
    std::uint32_t read_to_write_turnaround;
    std::uint32_t write_to_read_turnaround;

    double read_latency_scale;
    double write_latency_scale;

    std::uint64_t coord_base;
    std::uint64_t dist_base;
};

struct qfps_event_bucket_state {
    std::uint32_t point_ptr;
    std::uint32_t point_count;
    std::uint32_t far_index;
    float far_distance;
    std::uint32_t merge_count;
};

struct qfps_event_stats {
    std::uint64_t cycles;
    std::uint64_t iterations;
    std::uint64_t bucket_cd_inputs;
    std::uint64_t issued_buckets;
    std::uint64_t defer_buckets;
    std::uint64_t skip_buckets;
    std::uint64_t merge_forced_issue_buckets;
    std::uint64_t issued_points;
    std::uint64_t issued_merge_points;
    std::uint64_t functional_distance_evaluations;
    std::uint64_t functional_mdt_updates;
    std::uint64_t bucket_scan_cycles;
    std::uint64_t bucket_fifo_stall_cycles;
    std::uint64_t bucket_fifo_max_occupancy;
    std::uint64_t point_tasks;
    std::uint64_t point_compute_cycles;
    std::uint64_t point_engine_busy_cycles;
    std::uint64_t chunks;
    std::uint64_t coord_read_bytes;
    std::uint64_t dist_read_bytes;
    std::uint64_t dist_write_bytes;
    std::uint64_t dram_transactions;
    std::uint64_t dram_row_hits;
    std::uint64_t dram_row_misses;
    std::uint64_t dram_read_transactions;
    std::uint64_t dram_write_transactions;
    std::uint64_t dram_last_completion_cycle;
    std::uint64_t completed_samples;
    std::uint32_t point_buffer_resident;
};

}  // extern "C"

namespace {

struct BankState {
    std::uint64_t available_cycle = 0;
    std::uint64_t open_row = 0;
    bool has_open_row = false;
};

struct ChannelState {
    std::uint64_t bus_available_cycle = 0;
    bool has_last_direction = false;
    bool last_was_write = false;
};

struct MemoryRange {
    std::uint64_t address = 0;
    std::uint64_t size = 0;
    bool is_write = false;
};

class EventMemoryModel {
public:
    EventMemoryModel(const qfps_event_config& config,
                     qfps_event_stats& stats)
        : config_(config),
          stats_(stats),
          banks_(static_cast<std::size_t>(config.dram_channels) *
                 config.banks_per_channel),
          channels_(config.dram_channels),
          dma_lane_available_(config.dma_channels, 0) {}

    std::uint64_t schedule(std::uint64_t arrival_cycle,
                           const std::vector<MemoryRange>& ranges) {
        std::vector<std::vector<MemoryRange>> transactions;
        transactions.reserve(ranges.size());
        std::size_t remaining = 0;
        for (const MemoryRange& range : ranges) {
            if (range.size == 0) {
                transactions.emplace_back();
                continue;
            }
            std::vector<MemoryRange> stream;
            const std::uint64_t line = config_.dram_transaction_bytes;
            const std::uint64_t first = range.address / line;
            const std::uint64_t last =
                (range.address + range.size - 1U) / line;
            stream.reserve(static_cast<std::size_t>(last - first + 1U));
            for (std::uint64_t line_index = first;
                 line_index <= last; ++line_index) {
                const std::uint64_t line_address = line_index * line;
                const std::uint64_t begin =
                    std::max(range.address, line_address);
                const std::uint64_t end = std::min(
                    range.address + range.size, line_address + line);
                stream.push_back(
                    MemoryRange{line_address, end - begin, range.is_write});
            }
            remaining += stream.size();
            transactions.push_back(std::move(stream));
        }

        std::vector<std::size_t> offsets(transactions.size(), 0);
        std::uint64_t completion = arrival_cycle;
        std::uint64_t sequence = 0;
        while (remaining != 0U) {
            bool made_progress = false;
            for (std::size_t stream_id = 0;
                 stream_id < transactions.size(); ++stream_id) {
                if (offsets[stream_id] >= transactions[stream_id].size()) {
                    continue;
                }
                const MemoryRange& transaction =
                    transactions[stream_id][offsets[stream_id]++];
                --remaining;
                made_progress = true;
                const std::size_t lane = static_cast<std::size_t>(
                    sequence % config_.dma_channels);
                const std::uint64_t nominal =
                    arrival_cycle + config_.dma_command_cycles +
                    sequence / config_.dma_channels;
                const std::uint64_t injection =
                    std::max(nominal, dma_lane_available_[lane]);
                dma_lane_available_[lane] = injection + 1U;
                completion = std::max(
                    completion, schedule_transaction(injection, transaction));
                ++sequence;
            }
            if (!made_progress) {
                throw std::logic_error("memory transaction interleaver stalled");
            }
        }
        stats_.dram_last_completion_cycle = std::max(
            stats_.dram_last_completion_cycle, completion);
        return completion;
    }

private:
    std::uint64_t scaled_latency(std::uint64_t latency,
                                 bool is_write) const {
        const double scale =
            is_write ? config_.write_latency_scale
                     : config_.read_latency_scale;
        return static_cast<std::uint64_t>(
            std::ceil(static_cast<double>(latency) * scale));
    }

    std::uint64_t schedule_transaction(
        std::uint64_t injection,
        const MemoryRange& transaction) {
        const std::uint64_t burst_index =
            transaction.address / config_.burst_bytes;
        const std::uint32_t bank = static_cast<std::uint32_t>(
            burst_index % config_.banks_per_channel);
        const std::uint32_t channel = static_cast<std::uint32_t>(
            (burst_index / config_.banks_per_channel) %
            config_.dram_channels);
        const std::uint64_t row = transaction.address / config_.row_bytes;
        const std::size_t bank_index =
            static_cast<std::size_t>(channel) *
                config_.banks_per_channel +
            bank;
        BankState& bank_state = banks_.at(bank_index);
        ChannelState& channel_state = channels_.at(channel);

        std::uint64_t command_latency = 0;
        if (bank_state.has_open_row && bank_state.open_row == row) {
            command_latency = config_.t_cl;
            ++stats_.dram_row_hits;
        } else {
            command_latency = config_.t_rcd + config_.t_cl;
            if (bank_state.has_open_row) {
                command_latency += config_.t_rp;
            }
            bank_state.open_row = row;
            bank_state.has_open_row = true;
            ++stats_.dram_row_misses;
        }
        command_latency = scaled_latency(
            command_latency, transaction.is_write);

        const std::uint64_t command_start =
            std::max(injection, bank_state.available_cycle);
        std::uint64_t data_start = command_start + command_latency;
        if (channel_state.has_last_direction &&
            channel_state.last_was_write != transaction.is_write) {
            const std::uint64_t turnaround =
                transaction.is_write
                    ? config_.read_to_write_turnaround
                    : config_.write_to_read_turnaround;
            data_start = std::max(
                data_start,
                channel_state.bus_available_cycle + turnaround);
        } else {
            data_start = std::max(
                data_start, channel_state.bus_available_cycle);
        }
        const std::uint64_t transfer = std::max<std::uint64_t>(
            1U, config_.t_burst);
        std::uint64_t completion = data_start + transfer;
        if (transaction.is_write) {
            completion += config_.write_recovery;
            ++stats_.dram_write_transactions;
        } else {
            ++stats_.dram_read_transactions;
        }
        ++stats_.dram_transactions;
        channel_state.bus_available_cycle = data_start + transfer;
        channel_state.last_was_write = transaction.is_write;
        channel_state.has_last_direction = true;
        bank_state.available_cycle = completion;
        return completion;
    }

    const qfps_event_config& config_;
    qfps_event_stats& stats_;
    std::vector<BankState> banks_;
    std::vector<ChannelState> channels_;
    std::vector<std::uint64_t> dma_lane_available_;
};

enum class ChunkEventKind : std::uint32_t {
    LoadDone = 0,
    WriteDone = 1,
    LoadStart = 2,
    ComputeDone = 3,
};

struct ChunkEvent {
    std::uint64_t cycle = 0;
    ChunkEventKind kind = ChunkEventKind::LoadStart;
    std::uint32_t chunk = 0;
};

struct ChunkEventGreater {
    bool operator()(const ChunkEvent& left,
                    const ChunkEvent& right) const noexcept {
        if (left.cycle != right.cycle) {
            return left.cycle > right.cycle;
        }
        if (left.kind != right.kind) {
            return static_cast<std::uint32_t>(left.kind) >
                   static_cast<std::uint32_t>(right.kind);
        }
        return left.chunk > right.chunk;
    }
};

struct ChunkState {
    std::uint32_t point_offset = 0;
    std::uint32_t point_count = 0;
    std::uint32_t slot = 0;
    bool loaded = false;
    bool compute_started = false;
    bool write_done = false;
};

struct TaskResult {
    std::uint64_t done_cycle = 0;
    std::uint32_t far_index = 0;
    float far_distance = -1.0F;
};

class EventSimulator {
public:
    EventSimulator(const qfps_event_config& config,
                   const qfps_event_point* points,
                   const float* mdt,
                   const qfps_event_bucket_init* buckets)
        : config_(config), memory_(config_, stats_) {
        validate_config();
        if (points == nullptr || mdt == nullptr || buckets == nullptr) {
            throw std::invalid_argument("event simulator input pointer is null");
        }
        points_.reserve(config_.point_count);
        mdt_.reserve(config_.point_count);
        for (std::uint32_t index = 0; index < config_.point_count; ++index) {
            points_.push_back(Point3{points[index].x, points[index].y,
                                     points[index].z});
            mdt_.push_back(mdt[index]);
        }
        point_to_bucket_.assign(
            config_.point_count,
            std::numeric_limits<std::uint32_t>::max());
        buckets_.reserve(config_.bucket_count);
        std::uint32_t expected_ptr = 0;
        for (std::uint32_t bucket_id = 0;
             bucket_id < config_.bucket_count; ++bucket_id) {
            const qfps_event_bucket_init& input = buckets[bucket_id];
            const std::uint64_t stop =
                static_cast<std::uint64_t>(input.point_ptr) +
                input.point_count;
            if (input.point_ptr != expected_ptr || input.point_count == 0U ||
                stop > config_.point_count ||
                input.far_index < input.point_ptr ||
                input.far_index >= stop) {
                throw std::invalid_argument("invalid event-simulator bucket range");
            }
            Bucket bucket;
            bucket.point_ptr = input.point_ptr;
            bucket.point_count = input.point_count;
            bucket.minimum = Point3{input.min_x, input.min_y, input.min_z};
            bucket.maximum = Point3{input.max_x, input.max_y, input.max_z};
            bucket.far_index = input.far_index;
            bucket.far_distance = input.far_distance;
            buckets_.push_back(std::move(bucket));
            for (std::uint32_t point_index = input.point_ptr;
                 point_index < stop; ++point_index) {
                point_to_bucket_[point_index] = bucket_id;
            }
            expected_ptr = static_cast<std::uint32_t>(stop);
        }
        if (expected_ptr != config_.point_count) {
            throw std::invalid_argument("event buckets do not cover all points");
        }
        const std::uint64_t working_set =
            static_cast<std::uint64_t>(config_.point_count) *
            (config_.coord_bytes_per_point + config_.dist_bytes_per_point);
        if (config_.point_buffer_mode == 2U &&
            working_set > config_.point_buffer_capacity_bytes) {
            throw std::invalid_argument(
                "forced resident Point Buffer is smaller than the working set");
        }
        resident_ = config_.point_buffer_mode == 2U ||
                    (config_.point_buffer_mode == 0U &&
                     working_set <= config_.point_buffer_capacity_bytes);
        stats_.point_buffer_resident = resident_ ? 1U : 0U;
        sampled_.push_back(config_.first_sample);
    }

    void run() {
        const auto wall_start = std::chrono::steady_clock::now();
        if (config_.sample_count == 1U) {
            stats_.completed_samples = 1;
            return;
        }
        std::uint32_t current_sample = config_.first_sample;
        std::uint64_t iteration_start = 0;
        for (std::uint32_t iteration = 0;
             iteration + 1U < config_.sample_count; ++iteration) {
            check_limits(iteration, wall_start, iteration_start);
            iteration_start = simulate_iteration(
                iteration, current_sample, iteration_start);
            current_sample = global_far_index();
            sampled_.push_back(current_sample);
            stats_.iterations = iteration + 1U;
            stats_.completed_samples = sampled_.size();
            if (config_.progress_interval != 0U &&
                ((iteration + 1U) % config_.progress_interval == 0U ||
                 iteration + 2U == config_.sample_count)) {
                const double wall = std::chrono::duration<double>(
                    std::chrono::steady_clock::now() - wall_start).count();
                std::fprintf(
                    stderr,
                    "QFPS_EVENT_PROGRESS iteration=%u/%u cycle=%llu wall_s=%.3f\n",
                    iteration + 1U,
                    config_.sample_count - 1U,
                    static_cast<unsigned long long>(iteration_start),
                    wall);
            }
        }
        stats_.cycles = iteration_start;
    }

    std::uint32_t copy_samples(std::uint32_t* output,
                               std::uint32_t capacity) const {
        if (sampled_.size() > capacity ||
            (!sampled_.empty() && output == nullptr)) {
            throw std::invalid_argument("sample output buffer is too small");
        }
        std::copy(sampled_.begin(), sampled_.end(), output);
        return static_cast<std::uint32_t>(sampled_.size());
    }

    std::uint32_t copy_mdt(float* output,
                           std::uint32_t capacity) const {
        if (mdt_.size() > capacity || (!mdt_.empty() && output == nullptr)) {
            throw std::invalid_argument("MDT output buffer is too small");
        }
        std::copy(mdt_.begin(), mdt_.end(), output);
        return static_cast<std::uint32_t>(mdt_.size());
    }

    qfps_event_bucket_state bucket_state(std::uint32_t bucket_id) const {
        if (bucket_id >= buckets_.size()) {
            throw std::out_of_range("event bucket id is out of range");
        }
        const Bucket& bucket = buckets_[bucket_id];
        return qfps_event_bucket_state{
            bucket.point_ptr,
            bucket.point_count,
            bucket.far_index,
            bucket.far_distance,
            static_cast<std::uint32_t>(bucket.merge_indices.size())};
    }

    const qfps_event_stats& stats() const noexcept { return stats_; }

private:
    void validate_config() const {
        if (config_.point_count == 0U || config_.bucket_count == 0U ||
            config_.sample_count == 0U ||
            config_.sample_count > config_.point_count ||
            config_.first_sample >= config_.point_count ||
            config_.clock_hz == 0U || config_.max_hardware_cycles == 0U ||
            config_.bucket_cd_latency == 0U ||
            config_.bucket_issue_ii == 0U ||
            config_.bucket_fifo_depth == 0U ||
            config_.merge_buffer_capacity == 0U ||
            config_.sram_read_latency == 0U ||
            config_.sram_write_latency == 0U ||
            config_.chunk_points == 0U || config_.pe_rows == 0U ||
            config_.pe_cols == 0U || config_.pe_cell_latency == 0U ||
            config_.coord_bytes_per_point == 0U ||
            config_.dist_bytes_per_point == 0U ||
            config_.point_buffer_capacity_bytes == 0U ||
            config_.point_buffer_mode > 2U || config_.dma_channels == 0U ||
            config_.dram_transaction_bytes == 0U ||
            config_.dram_channels == 0U ||
            config_.banks_per_channel == 0U || config_.row_bytes == 0U ||
            config_.burst_bytes == 0U || config_.t_rcd == 0U ||
            config_.t_cl == 0U || config_.t_rp == 0U ||
            config_.t_burst == 0U || config_.read_latency_scale <= 0.0 ||
            config_.write_latency_scale <= 0.0) {
            throw std::invalid_argument("invalid event-simulator configuration");
        }
    }

    void check_limits(
        std::uint32_t iteration,
        const std::chrono::steady_clock::time_point& wall_start,
        std::uint64_t cycle) const {
        if (cycle > config_.max_hardware_cycles) {
            throw std::runtime_error(
                "event simulation exceeded max_hardware_cycles at iteration " +
                std::to_string(iteration));
        }
        if (config_.max_wall_seconds > 0.0) {
            const double wall = std::chrono::duration<double>(
                std::chrono::steady_clock::now() - wall_start).count();
            if (wall > config_.max_wall_seconds) {
                throw std::runtime_error(
                    "event simulation exceeded max_wall_seconds at iteration " +
                    std::to_string(iteration));
            }
        }
    }

    std::uint32_t winner_bucket(std::uint32_t sampled_index) const {
        const std::uint32_t value = point_to_bucket_.at(sampled_index);
        if (value == std::numeric_limits<std::uint32_t>::max()) {
            throw std::logic_error("sample is not covered by a bucket");
        }
        return value;
    }

    std::uint64_t point_latency(std::uint32_t point_count,
                                std::uint32_t merge_count) const {
        const std::uint64_t batches =
            (point_count + config_.pe_rows - 1U) / config_.pe_rows;
        const std::uint64_t passes =
            (merge_count + 1U + config_.pe_cols - 1U) / config_.pe_cols;
        return passes *
                   (config_.merge_load_cycles + batches +
                    static_cast<std::uint64_t>(config_.pe_cols) *
                        config_.pe_cell_latency) +
               config_.point_ctrl_overhead +
               config_.point_io_pipeline_cycles;
    }

    std::uint64_t schedule_load(std::uint64_t cycle,
                                const Bucket& bucket,
                                const ChunkState& chunk) {
        if (resident_) {
            return cycle + config_.sram_read_latency;
        }
        const std::uint64_t point_index =
            bucket.point_ptr + chunk.point_offset;
        const std::uint64_t coord_address =
            config_.coord_base +
            point_index * config_.coord_bytes_per_point;
        const std::uint64_t dist_address =
            config_.dist_base +
            point_index * config_.dist_bytes_per_point;
        const std::uint64_t coord_size =
            static_cast<std::uint64_t>(chunk.point_count) *
            config_.coord_bytes_per_point;
        const std::uint64_t dist_size =
            static_cast<std::uint64_t>(chunk.point_count) *
            config_.dist_bytes_per_point;
        stats_.coord_read_bytes += coord_size;
        stats_.dist_read_bytes += dist_size;
        return memory_.schedule(
            cycle,
            {MemoryRange{coord_address, coord_size, false},
             MemoryRange{dist_address, dist_size, false}});
    }

    std::uint64_t schedule_write(std::uint64_t cycle,
                                 const Bucket& bucket,
                                 const ChunkState& chunk) {
        if (resident_) {
            return cycle + config_.sram_write_latency;
        }
        const std::uint64_t point_index =
            bucket.point_ptr + chunk.point_offset;
        const std::uint64_t address =
            config_.dist_base +
            point_index * config_.dist_bytes_per_point;
        const std::uint64_t size =
            static_cast<std::uint64_t>(chunk.point_count) *
            config_.dist_bytes_per_point;
        stats_.dist_write_bytes += size;
        return memory_.schedule(
            cycle, {MemoryRange{address, size, true}});
    }

    void compute_chunk(const Bucket& bucket,
                       const ChunkState& chunk,
                       const std::vector<std::uint32_t>& references,
                       std::uint32_t& best_index,
                       float& best_distance) {
        const std::uint32_t begin =
            bucket.point_ptr + chunk.point_offset;
        const std::uint32_t end = begin + chunk.point_count;
        for (std::uint32_t point_index = begin;
             point_index < end; ++point_index) {
            float value = mdt_[point_index];
            for (std::uint32_t reference : references) {
                value = std::min(
                    value, distance2(points_[point_index], points_[reference]));
            }
            value = f32(value);
            if (value != mdt_[point_index]) {
                ++stats_.functional_mdt_updates;
            }
            mdt_[point_index] = value;
            stats_.functional_distance_evaluations += references.size();
            if (better(value, point_index, best_distance, best_index)) {
                best_distance = value;
                best_index = point_index;
            }
        }
    }

    TaskResult schedule_task(
        std::uint64_t accept_cycle,
        Bucket& bucket,
        const std::vector<std::uint32_t>& references,
        std::uint32_t merge_count) {
        std::vector<ChunkState> chunks;
        for (std::uint32_t offset = 0, chunk_index = 0;
             offset < bucket.point_count;
             offset += config_.chunk_points, ++chunk_index) {
            const std::uint32_t count = std::min(
                config_.chunk_points, bucket.point_count - offset);
            chunks.push_back(
                ChunkState{offset, count, chunk_index & 1U, false, false, false});
        }
        stats_.chunks += chunks.size();
        ++stats_.point_tasks;
        stats_.issued_points += bucket.point_count;
        stats_.issued_merge_points += merge_count;

        std::priority_queue<ChunkEvent,
                            std::vector<ChunkEvent>,
                            ChunkEventGreater>
            events;
        events.push(ChunkEvent{accept_cycle, ChunkEventKind::LoadStart, 0});
        if (chunks.size() > 1U) {
            events.push(ChunkEvent{accept_cycle, ChunkEventKind::LoadStart, 1});
        }
        bool compute_active = false;
        std::uint32_t completed_chunks = 0;
        std::uint32_t best_index = bucket.point_ptr;
        float best_distance = -1.0F;
        std::uint64_t task_done = accept_cycle;

        while (completed_chunks < chunks.size()) {
            if (events.empty()) {
                throw std::logic_error("point task event queue became empty");
            }
            const std::uint64_t cycle = events.top().cycle;
            while (!events.empty() && events.top().cycle == cycle) {
                const ChunkEvent event = events.top();
                events.pop();
                ChunkState& chunk = chunks.at(event.chunk);
                switch (event.kind) {
                    case ChunkEventKind::LoadStart: {
                        const std::uint64_t done =
                            schedule_load(cycle, bucket, chunk);
                        events.push(ChunkEvent{
                            done, ChunkEventKind::LoadDone, event.chunk});
                        break;
                    }
                    case ChunkEventKind::LoadDone:
                        chunk.loaded = true;
                        break;
                    case ChunkEventKind::ComputeDone: {
                        compute_chunk(bucket, chunk, references,
                                      best_index, best_distance);
                        compute_active = false;
                        const std::uint64_t done =
                            schedule_write(cycle, bucket, chunk);
                        events.push(ChunkEvent{
                            done, ChunkEventKind::WriteDone, event.chunk});
                        break;
                    }
                    case ChunkEventKind::WriteDone: {
                        chunk.write_done = true;
                        ++completed_chunks;
                        task_done = std::max(task_done, cycle);
                        const std::uint32_t next = event.chunk + 2U;
                        if (next < chunks.size()) {
                            events.push(ChunkEvent{
                                cycle, ChunkEventKind::LoadStart, next});
                        }
                        break;
                    }
                }
            }

            if (!compute_active) {
                auto found = std::find_if(
                    chunks.begin(), chunks.end(), [](const ChunkState& chunk) {
                        return chunk.loaded && !chunk.compute_started;
                    });
                if (found != chunks.end()) {
                    const std::uint32_t chunk_index =
                        static_cast<std::uint32_t>(
                            std::distance(chunks.begin(), found));
                    found->compute_started = true;
                    compute_active = true;
                    const std::uint64_t latency = point_latency(
                        found->point_count, merge_count);
                    stats_.point_compute_cycles += latency;
                    events.push(ChunkEvent{
                        cycle + latency,
                        ChunkEventKind::ComputeDone,
                        chunk_index});
                }
            }
        }
        if (!std::isfinite(best_distance)) {
            throw std::logic_error("point task did not produce a finite far point");
        }
        stats_.point_engine_busy_cycles += task_done - accept_cycle + 1U;
        return TaskResult{task_done, best_index, best_distance};
    }

    std::uint64_t simulate_iteration(
        std::uint32_t iteration,
        std::uint32_t sampled_index,
        std::uint64_t iteration_start) {
        const std::uint32_t first_bucket = winner_bucket(sampled_index);
        std::vector<std::uint32_t> traversal;
        traversal.reserve(buckets_.size());
        traversal.push_back(first_bucket);
        for (std::uint32_t bucket_id = 0;
             bucket_id < buckets_.size(); ++bucket_id) {
            if (bucket_id != first_bucket) {
                traversal.push_back(bucket_id);
            }
        }

        std::vector<std::uint64_t> fifo_accept_cycles;
        fifo_accept_cycles.reserve(config_.bucket_fifo_depth + 1U);
        std::size_t fifo_head = 0;
        std::uint64_t previous_task_done = iteration_start;
        bool has_previous_task = false;
        std::uint64_t last_write_commit = iteration_start;
        std::uint64_t accumulated_stall = 0;
        const std::uint64_t frontend =
            config_.sram_read_latency + config_.bucket_cd_latency + 2U;
        const Point3& sample = points_[sampled_index];

        for (std::uint32_t position = 0;
             position < traversal.size(); ++position) {
            ++stats_.bucket_cd_inputs;
            const std::uint32_t bucket_id = traversal[position];
            Bucket& bucket = buckets_[bucket_id];
            const float far_to_sample =
                distance2(points_[bucket.far_index], sample);
            const float lower_bound =
                box_distance2(sample, bucket.minimum, bucket.maximum);
            const std::uint32_t merge_count = static_cast<std::uint32_t>(
                bucket.merge_indices.size());
            const bool merge_ok = bucket.far_distance < far_to_sample;
            const bool implicit_ok = bucket.far_distance < lower_bound;
            bool issue = false;
            bool forced = false;
            if (iteration == 0U || !merge_ok) {
                issue = true;
            } else if (implicit_ok) {
                ++stats_.skip_buckets;
            } else if (merge_count >= config_.merge_buffer_capacity) {
                issue = true;
                forced = true;
            } else {
                bucket.merge_indices.push_back(sampled_index);
                ++stats_.defer_buckets;
            }

            if (!issue) {
                continue;
            }
            ++stats_.issued_buckets;
            if (forced) {
                ++stats_.merge_forced_issue_buckets;
            }
            std::uint64_t issue_cycle =
                iteration_start + frontend + position + accumulated_stall;
            while (fifo_head < fifo_accept_cycles.size() &&
                   fifo_accept_cycles[fifo_head] < issue_cycle) {
                ++fifo_head;
            }
            std::size_t occupancy = fifo_accept_cycles.size() - fifo_head;
            if (occupancy >= config_.bucket_fifo_depth) {
                const std::uint64_t next_visible =
                    fifo_accept_cycles[fifo_head] + 1U;
                if (next_visible > issue_cycle) {
                    const std::uint64_t stall = next_visible - issue_cycle;
                    accumulated_stall += stall;
                    stats_.bucket_fifo_stall_cycles += stall;
                    issue_cycle = next_visible;
                }
                while (fifo_head < fifo_accept_cycles.size() &&
                       fifo_accept_cycles[fifo_head] < issue_cycle) {
                    ++fifo_head;
                }
                occupancy = fifo_accept_cycles.size() - fifo_head;
            }
            stats_.bucket_fifo_max_occupancy = std::max(
                stats_.bucket_fifo_max_occupancy,
                static_cast<std::uint64_t>(occupancy + 1U));

            const std::uint64_t accept_cycle = std::max(
                issue_cycle + 1U,
                has_previous_task ? previous_task_done + 1U
                                  : issue_cycle + 1U);
            fifo_accept_cycles.push_back(accept_cycle);
            std::vector<std::uint32_t> references = bucket.merge_indices;
            references.push_back(sampled_index);
            bucket.merge_indices.clear();
            const TaskResult task = schedule_task(
                accept_cycle, bucket, references, merge_count);
            bucket.far_index = task.far_index;
            bucket.far_distance = task.far_distance;
            previous_task_done = task.done_cycle;
            has_previous_task = true;
            last_write_commit = std::max(
                last_write_commit,
                task.done_cycle + 1U + config_.sram_write_latency);
        }

        const std::uint64_t scan_done =
            iteration_start + frontend + traversal.size() + accumulated_stall;
        stats_.bucket_scan_cycles += scan_done - iteration_start;
        const std::uint64_t completion =
            std::max(scan_done, last_write_commit) + 1U;
        if (completion > config_.max_hardware_cycles) {
            throw std::runtime_error(
                "event simulation exceeded max_hardware_cycles");
        }
        return completion;
    }

    std::uint32_t global_far_index() const {
        std::uint32_t best_index = buckets_.front().far_index;
        float best_distance = buckets_.front().far_distance;
        for (std::size_t index = 1; index < buckets_.size(); ++index) {
            const Bucket& bucket = buckets_[index];
            if (better(bucket.far_distance, bucket.far_index,
                       best_distance, best_index)) {
                best_distance = bucket.far_distance;
                best_index = bucket.far_index;
            }
        }
        if (!std::isfinite(best_distance)) {
            throw std::logic_error("global far result is not finite");
        }
        return best_index;
    }

    qfps_event_config config_{};
    qfps_event_stats stats_{};
    EventMemoryModel memory_;
    std::vector<Point3> points_;
    std::vector<float> mdt_;
    std::vector<Bucket> buckets_;
    std::vector<std::uint32_t> point_to_bucket_;
    std::vector<std::uint32_t> sampled_;
    bool resident_ = false;
};

template <typename Function>
int guard(Function&& function) noexcept {
    try {
        function();
        g_last_error.clear();
        return 1;
    } catch (const std::exception& error) {
        g_last_error = error.what();
        return 0;
    } catch (...) {
        g_last_error = "unknown event-simulator error";
        return 0;
    }
}

}  // namespace

extern "C" {

void* qfps_event_create(const qfps_event_config* config,
                        const qfps_event_point* points,
                        const float* mdt,
                        const qfps_event_bucket_init* buckets) {
    try {
        if (config == nullptr) {
            throw std::invalid_argument("event config pointer is null");
        }
        auto simulator =
            std::make_unique<EventSimulator>(*config, points, mdt, buckets);
        g_last_error.clear();
        return simulator.release();
    } catch (const std::exception& error) {
        g_last_error = error.what();
        return nullptr;
    } catch (...) {
        g_last_error = "unknown event-simulator construction error";
        return nullptr;
    }
}

void qfps_event_destroy(void* handle) {
    delete static_cast<EventSimulator*>(handle);
}

int qfps_event_run(void* handle) {
    return guard([&]() {
        if (handle == nullptr) {
            throw std::invalid_argument("event simulator handle is null");
        }
        static_cast<EventSimulator*>(handle)->run();
    });
}

int qfps_event_copy_samples(void* handle,
                            std::uint32_t* output,
                            std::uint32_t capacity,
                            std::uint32_t* count) {
    return guard([&]() {
        if (handle == nullptr || count == nullptr) {
            throw std::invalid_argument("event sample output pointer is null");
        }
        *count = static_cast<EventSimulator*>(handle)->copy_samples(
            output, capacity);
    });
}

int qfps_event_copy_mdt(void* handle,
                        float* output,
                        std::uint32_t capacity,
                        std::uint32_t* count) {
    return guard([&]() {
        if (handle == nullptr || count == nullptr) {
            throw std::invalid_argument("event MDT output pointer is null");
        }
        *count = static_cast<EventSimulator*>(handle)->copy_mdt(
            output, capacity);
    });
}

int qfps_event_get_bucket_state(void* handle,
                                std::uint32_t bucket_id,
                                qfps_event_bucket_state* output) {
    return guard([&]() {
        if (handle == nullptr || output == nullptr) {
            throw std::invalid_argument("event bucket output pointer is null");
        }
        *output = static_cast<EventSimulator*>(handle)->bucket_state(bucket_id);
    });
}

int qfps_event_get_stats(void* handle,
                         qfps_event_stats* output) {
    return guard([&]() {
        if (handle == nullptr || output == nullptr) {
            throw std::invalid_argument("event stats output pointer is null");
        }
        *output = static_cast<EventSimulator*>(handle)->stats();
    });
}

const char* qfps_event_last_error() { return g_last_error.c_str(); }

}  // extern "C"
