#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <deque>
#include <exception>
#include <limits>
#include <memory>
#include <stdexcept>
#include <string>
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

enum class DecisionKind : std::uint32_t {
    Issue = 0,
    Defer = 1,
    Skip = 2,
};

struct Decision {
    std::uint32_t bucket_id = 0;
    DecisionKind kind = DecisionKind::Skip;
    std::uint32_t merge_count = 0;
    std::uint32_t sampled_index = 0;
    std::vector<std::uint32_t> references;
    float far_to_sample = 0.0F;
    float lower_bound = 0.0F;
    bool forced_issue = false;
};

struct FarResult {
    std::uint32_t bucket_id = 0;
    std::uint32_t far_index = 0;
    float far_distance = 0.0F;
};

struct TimedBucket {
    std::uint64_t ready_cycle = 0;
    std::uint32_t bucket_id = 0;
};

struct TimedDecision {
    std::uint64_t ready_cycle = 0;
    Decision decision{};
};

struct TimedWriteback {
    std::uint64_t ready_cycle = 0;
    FarResult result{};
};

float f32(float value) noexcept { return value; }

float distance2(const Point3& a, const Point3& b) noexcept {
    const float dx = f32(a.x - b.x);
    const float dy = f32(a.y - b.y);
    const float dz = f32(a.z - b.z);
    const float xx = f32(dx * dx);
    const float yy = f32(dy * dy);
    const float zz = f32(dz * dz);
    const float xy = f32(xx + yy);
    return f32(xy + zz);
}

float box_distance2(const Point3& point,
                    const Point3& minimum,
                    const Point3& maximum) noexcept {
    float gaps[3] = {0.0F, 0.0F, 0.0F};
    const float values[3] = {point.x, point.y, point.z};
    const float lowers[3] = {minimum.x, minimum.y, minimum.z};
    const float uppers[3] = {maximum.x, maximum.y, maximum.z};
    for (std::size_t index = 0; index < 3; ++index) {
        if (values[index] < lowers[index]) {
            gaps[index] = f32(lowers[index] - values[index]);
        } else if (values[index] > uppers[index]) {
            gaps[index] = f32(values[index] - uppers[index]);
        }
    }
    const float xx = f32(gaps[0] * gaps[0]);
    const float yy = f32(gaps[1] * gaps[1]);
    const float zz = f32(gaps[2] * gaps[2]);
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

struct qfps_native_config {
    std::uint32_t point_count;
    std::uint32_t bucket_count;
    std::uint32_t sample_count;
    std::uint32_t first_sample;
    std::uint32_t bucket_cd_latency;
    std::uint32_t bucket_issue_ii;
    std::uint32_t bucket_decision_fifo_depth;
    std::uint32_t merge_buffer_capacity;
    std::uint32_t sram_read_latency;
    std::uint32_t sram_write_latency;
};

struct qfps_native_point {
    float x;
    float y;
    float z;
};

struct qfps_native_bucket_init {
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

struct qfps_native_far_input {
    std::uint32_t valid;
    std::uint32_t bucket_id;
    std::uint32_t far_index;
    float far_distance;
};

struct qfps_native_step_input {
    std::uint64_t cycle;
    std::uint32_t bucket_fifo_ready_before;
    std::uint32_t external_idle_after_point_step;
    qfps_native_far_input far;
};

struct qfps_native_step_output {
    std::uint32_t issue_valid;
    std::uint32_t issue_bucket_id;
    std::uint32_t issue_merge_count;
    std::uint32_t issue_sampled_index;
    std::uint32_t issue_reference_count;
    std::uint32_t issue_forced;
    std::uint32_t iteration_completed;
    std::uint32_t completed_iteration;
    std::uint32_t next_sampled_index;
    std::uint32_t simulation_done;
};

struct qfps_native_bucket_state {
    std::uint32_t point_ptr;
    std::uint32_t point_count;
    std::uint32_t far_index;
    float far_distance;
    std::uint32_t merge_count;
};

struct qfps_native_stats {
    std::uint64_t cycles;
    std::uint64_t bucket_cd_inputs;
    std::uint64_t bucket_decision_fifo_pushes;
    std::uint64_t bucket_decision_fifo_max_occupancy;
    std::uint64_t bucket_reserved_credit_max;
    std::uint64_t bucket_fetch_max_occupancy;
    std::uint64_t bucket_decision_credit_stall_cycles;
    std::uint64_t bucket_fifo_backpressure_cycles;
    std::uint64_t decision_fifo_head_stall_cycles;
    std::uint64_t bucket_buffer_read_requests;
    std::uint64_t bucket_buffer_read_responses;
    std::uint64_t bucket_buffer_read_stall_cycles;
    std::uint64_t bucket_buffer_read_busy_cycles;
    std::uint64_t bucket_buffer_write_requests;
    std::uint64_t bucket_buffer_write_commits;
    std::uint64_t bucket_buffer_write_busy_cycles;
    std::uint64_t bucket_pipeline_active_cycles;
    std::uint64_t issued_buckets;
    std::uint64_t defer_buckets;
    std::uint64_t skip_buckets;
    std::uint64_t merge_forced_issue_buckets;
    std::uint64_t bucket_completions;
    std::uint64_t max_outstanding_buckets;
    std::uint64_t iterations_completed;
};

}  // extern "C"

namespace {

class Scheduler {
public:
    Scheduler(const qfps_native_config& config,
              const qfps_native_point* points,
              const qfps_native_bucket_init* buckets)
        : config_(config) {
        validate_config();
        if (points == nullptr || buckets == nullptr) {
            throw std::invalid_argument("points and buckets must be non-null");
        }
        points_.reserve(config_.point_count);
        for (std::uint32_t index = 0; index < config_.point_count; ++index) {
            points_.push_back(Point3{points[index].x, points[index].y,
                                     points[index].z});
        }
        buckets_.reserve(config_.bucket_count);
        point_to_bucket_.assign(config_.point_count,
                                std::numeric_limits<std::uint32_t>::max());
        std::uint32_t expected_ptr = 0;
        for (std::uint32_t bucket_id = 0; bucket_id < config_.bucket_count;
             ++bucket_id) {
            const auto& input = buckets[bucket_id];
            if (input.point_ptr != expected_ptr || input.point_count == 0) {
                throw std::invalid_argument(
                    "bucket ranges must be nonempty, contiguous, and ordered");
            }
            const std::uint64_t stop =
                static_cast<std::uint64_t>(input.point_ptr) + input.point_count;
            if (stop > config_.point_count || input.far_index < input.point_ptr ||
                input.far_index >= stop) {
                throw std::invalid_argument("invalid bucket range or far index");
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
            throw std::invalid_argument("bucket ranges do not cover all points");
        }
        current_sample_ = config_.first_sample;
        sampled_count_ = 1;
        rebuild_traversal();
    }

    void step(const qfps_native_step_input& input,
              qfps_native_step_output& output) {
        std::memset(&output, 0, sizeof(output));
        if (done_) {
            throw std::logic_error("native scheduler stepped after completion");
        }
        if (input.cycle != expected_cycle_) {
            throw std::logic_error("native scheduler cycle is not monotonic");
        }

        const std::size_t reserved_before =
            cd_pipeline_.size() + decision_fifo_.size();
        const bool cd_input_ready_before =
            reserved_before < config_.bucket_decision_fifo_depth;
        const bool fetched_head_before = !fetch_fifo_.empty();
        const std::uint32_t fetched_bucket_before =
            fetched_head_before ? fetch_fifo_.front() : 0;
        const bool fetch_ready_before =
            !fetch_pipeline_.empty() &&
            fetch_pipeline_.front().ready_cycle <= input.cycle &&
            fetch_fifo_.size() < config_.bucket_decision_fifo_depth;
        const bool decision_head_before = !decision_fifo_.empty();
        const bool cd_ready_before =
            !cd_pipeline_.empty() &&
            cd_pipeline_.front().ready_cycle <= input.cycle;
        const bool writeback_ready_before =
            !writeback_pipeline_.empty() &&
            writeback_pipeline_.front().ready_cycle <= input.cycle;

        if (writeback_ready_before) {
            commit_writeback(writeback_pipeline_.front().result);
            writeback_pipeline_.pop_front();
        }

        if (input.far.valid != 0U) {
            validate_far(input.far);
            const FarResult result{input.far.bucket_id, input.far.far_index,
                                   input.far.far_distance};
            writeback_pipeline_.push_back(
                TimedWriteback{input.cycle + config_.sram_write_latency,
                               result});
            ++stats_.bucket_buffer_write_requests;
        }

        if (decision_head_before) {
            Decision& decision = decision_fifo_.front();
            if (decision.kind == DecisionKind::Issue) {
                if (input.bucket_fifo_ready_before != 0U) {
                    last_issue_references_ = decision.references;
                    output.issue_valid = 1;
                    output.issue_bucket_id = decision.bucket_id;
                    output.issue_merge_count = decision.merge_count;
                    output.issue_sampled_index = decision.sampled_index;
                    output.issue_reference_count = static_cast<std::uint32_t>(
                        last_issue_references_.size());
                    output.issue_forced = decision.forced_issue ? 1U : 0U;
                    buckets_[decision.bucket_id].merge_indices.clear();
                    decision_fifo_.pop_front();
                    ++outstanding_;
                    ++stats_.issued_buckets;
                    if (decision.forced_issue) {
                        ++stats_.merge_forced_issue_buckets;
                    }
                } else {
                    ++stats_.bucket_fifo_backpressure_cycles;
                    ++stats_.decision_fifo_head_stall_cycles;
                }
            } else {
                const Decision completed = decision;
                decision_fifo_.pop_front();
                if (completed.kind == DecisionKind::Defer) {
                    Bucket& bucket = buckets_[completed.bucket_id];
                    if (bucket.merge_indices.size() >=
                        config_.merge_buffer_capacity) {
                        throw std::logic_error(
                            "defer exceeded native merge-buffer capacity");
                    }
                    bucket.merge_indices.push_back(completed.sampled_index);
                    ++stats_.defer_buckets;
                } else {
                    ++stats_.skip_buckets;
                }
            }
        }

        if (cd_ready_before) {
            if (decision_fifo_.size() >=
                config_.bucket_decision_fifo_depth) {
                throw std::logic_error(
                    "native decision FIFO credit invariant failed");
            }
            decision_fifo_.push_back(
                std::move(cd_pipeline_.front().decision));
            cd_pipeline_.pop_front();
            ++stats_.bucket_decision_fifo_pushes;
        }

        if (inject_cooldown_ > 0U) {
            --inject_cooldown_;
        }
        if (fetched_head_before && inject_cooldown_ == 0U &&
            cd_input_ready_before) {
            if (fetch_fifo_.front() != fetched_bucket_before) {
                throw std::logic_error("native fetch FIFO head changed");
            }
            fetch_fifo_.pop_front();
            Decision decision = decide(fetched_bucket_before);
            cd_pipeline_.push_back(TimedDecision{
                input.cycle + config_.bucket_cd_latency,
                std::move(decision)});
            inject_cooldown_ = config_.bucket_issue_ii - 1U;
            ++stats_.bucket_cd_inputs;
        } else if (fetched_head_before && inject_cooldown_ == 0U) {
            ++stats_.bucket_decision_credit_stall_cycles;
        }

        if (fetch_ready_before) {
            fetch_fifo_.push_back(fetch_pipeline_.front().bucket_id);
            fetch_pipeline_.pop_front();
            ++stats_.bucket_buffer_read_responses;
        }

        const std::size_t fetch_reserved_after =
            fetch_pipeline_.size() + fetch_fifo_.size();
        if (traversal_index_ < traversal_.size() &&
            fetch_reserved_after < config_.bucket_decision_fifo_depth) {
            const std::uint32_t bucket_id = traversal_[traversal_index_++];
            fetch_pipeline_.push_back(
                TimedBucket{input.cycle + config_.sram_read_latency,
                            bucket_id});
            ++stats_.bucket_buffer_read_requests;
        } else if (traversal_index_ < traversal_.size()) {
            ++stats_.bucket_buffer_read_stall_cycles;
        }

        const std::size_t cd_reserved_after =
            cd_pipeline_.size() + decision_fifo_.size();
        stats_.bucket_decision_fifo_max_occupancy = std::max(
            stats_.bucket_decision_fifo_max_occupancy,
            static_cast<std::uint64_t>(decision_fifo_.size()));
        stats_.bucket_reserved_credit_max = std::max(
            stats_.bucket_reserved_credit_max,
            static_cast<std::uint64_t>(cd_reserved_after));
        stats_.bucket_fetch_max_occupancy = std::max(
            stats_.bucket_fetch_max_occupancy,
            static_cast<std::uint64_t>(fetch_pipeline_.size() +
                                       fetch_fifo_.size()));
        if (cd_reserved_after > config_.bucket_decision_fifo_depth) {
            throw std::logic_error(
                "native reserved credits exceeded configured depth");
        }

        const bool scan_done =
            traversal_index_ == traversal_.size() && fetch_pipeline_.empty() &&
            fetch_fifo_.empty() && cd_pipeline_.empty() &&
            decision_fifo_.empty();
        if (scan_done && outstanding_ == 0U && writeback_pipeline_.empty() &&
            input.external_idle_after_point_step != 0U) {
            const FarResult global = global_far();
            output.iteration_completed = 1;
            output.completed_iteration = iteration_;
            output.next_sampled_index = global.far_index;
            current_sample_ = global.far_index;
            ++sampled_count_;
            ++iteration_;
            ++stats_.iterations_completed;
            if (sampled_count_ == config_.sample_count) {
                done_ = true;
                output.simulation_done = 1;
            } else {
                rebuild_traversal();
                inject_cooldown_ = 0;
            }
        }

        if (!cd_pipeline_.empty() || !decision_fifo_.empty()) {
            ++stats_.bucket_pipeline_active_cycles;
        }
        if (!fetch_pipeline_.empty() || !fetch_fifo_.empty()) {
            ++stats_.bucket_buffer_read_busy_cycles;
        }
        if (!writeback_pipeline_.empty()) {
            ++stats_.bucket_buffer_write_busy_cycles;
        }
        stats_.max_outstanding_buckets = std::max(
            stats_.max_outstanding_buckets,
            static_cast<std::uint64_t>(outstanding_));
        ++stats_.cycles;
        ++expected_cycle_;
    }

    std::uint32_t copy_issue_references(std::uint32_t* output,
                                        std::uint32_t capacity) const {
        const std::uint32_t count = static_cast<std::uint32_t>(
            last_issue_references_.size());
        if (count > capacity) {
            throw std::invalid_argument(
                "issue-reference output buffer is too small");
        }
        if (count != 0U && output == nullptr) {
            throw std::invalid_argument(
                "issue-reference output pointer is null");
        }
        std::copy(last_issue_references_.begin(),
                  last_issue_references_.end(), output);
        return count;
    }

    qfps_native_bucket_state bucket_state(std::uint32_t bucket_id) const {
        if (bucket_id >= buckets_.size()) {
            throw std::out_of_range("native bucket id out of range");
        }
        const Bucket& bucket = buckets_[bucket_id];
        return qfps_native_bucket_state{
            bucket.point_ptr,
            bucket.point_count,
            bucket.far_index,
            bucket.far_distance,
            static_cast<std::uint32_t>(bucket.merge_indices.size())};
    }

    std::uint32_t copy_bucket_merge_indices(std::uint32_t bucket_id,
                                            std::uint32_t* output,
                                            std::uint32_t capacity) const {
        if (bucket_id >= buckets_.size()) {
            throw std::out_of_range("native bucket id out of range");
        }
        const auto& indices = buckets_[bucket_id].merge_indices;
        const std::uint32_t count =
            static_cast<std::uint32_t>(indices.size());
        if (count > capacity) {
            throw std::invalid_argument(
                "merge-index output buffer is too small");
        }
        if (count != 0U && output == nullptr) {
            throw std::invalid_argument("merge-index output pointer is null");
        }
        std::copy(indices.begin(), indices.end(), output);
        return count;
    }

    const qfps_native_stats& stats() const noexcept { return stats_; }

private:
    void validate_config() const {
        if (config_.point_count == 0U || config_.bucket_count == 0U ||
            config_.sample_count == 0U ||
            config_.sample_count > config_.point_count ||
            config_.first_sample >= config_.point_count ||
            config_.bucket_cd_latency == 0U ||
            config_.bucket_issue_ii == 0U ||
            config_.bucket_decision_fifo_depth <
                config_.bucket_cd_latency ||
            config_.merge_buffer_capacity == 0U ||
            config_.sram_read_latency == 0U ||
            config_.sram_write_latency == 0U) {
            throw std::invalid_argument("invalid native scheduler config");
        }
    }

    void validate_far(const qfps_native_far_input& far) const {
        if (far.bucket_id >= buckets_.size()) {
            throw std::invalid_argument("far result bucket id out of range");
        }
        const Bucket& bucket = buckets_[far.bucket_id];
        const std::uint64_t stop =
            static_cast<std::uint64_t>(bucket.point_ptr) + bucket.point_count;
        if (far.far_index < bucket.point_ptr || far.far_index >= stop ||
            !std::isfinite(far.far_distance)) {
            throw std::invalid_argument("invalid far result payload");
        }
    }

    Decision decide(std::uint32_t bucket_id) const {
        const Bucket& bucket = buckets_.at(bucket_id);
        const Point3& sample = points_.at(current_sample_);
        const float far_to_sample =
            distance2(points_.at(bucket.far_index), sample);
        const float lower_bound =
            box_distance2(sample, bucket.minimum, bucket.maximum);
        const std::uint32_t merge_count = static_cast<std::uint32_t>(
            bucket.merge_indices.size());
        const bool merge_ok = bucket.far_distance < far_to_sample;
        const bool implicit_ok = bucket.far_distance < lower_bound;
        DecisionKind kind = DecisionKind::Skip;
        bool forced = false;
        if (iteration_ == 0U || !merge_ok) {
            kind = DecisionKind::Issue;
        } else if (implicit_ok) {
            kind = DecisionKind::Skip;
        } else if (merge_count >= config_.merge_buffer_capacity) {
            kind = DecisionKind::Issue;
            forced = true;
        } else {
            kind = DecisionKind::Defer;
        }

        Decision decision;
        decision.bucket_id = bucket_id;
        decision.kind = kind;
        decision.merge_count = merge_count;
        decision.sampled_index = current_sample_;
        decision.far_to_sample = far_to_sample;
        decision.lower_bound = lower_bound;
        decision.forced_issue = forced;
        if (kind == DecisionKind::Issue) {
            decision.references = bucket.merge_indices;
            decision.references.push_back(current_sample_);
        }
        return decision;
    }

    void commit_writeback(const FarResult& result) {
        validate_far(qfps_native_far_input{1U, result.bucket_id,
                                           result.far_index,
                                           result.far_distance});
        Bucket& bucket = buckets_[result.bucket_id];
        bucket.far_index = result.far_index;
        bucket.far_distance = result.far_distance;
        bucket.merge_indices.clear();
        if (outstanding_ == 0U) {
            throw std::logic_error(
                "native writeback committed without an outstanding bucket");
        }
        --outstanding_;
        ++stats_.bucket_completions;
        ++stats_.bucket_buffer_write_commits;
    }

    FarResult global_far() const {
        if (buckets_.empty()) {
            throw std::logic_error("native global far on empty bucket set");
        }
        std::uint32_t best_bucket = 0;
        std::uint32_t best_index = buckets_[0].far_index;
        float best_distance = buckets_[0].far_distance;
        for (std::uint32_t bucket_id = 1;
             bucket_id < buckets_.size(); ++bucket_id) {
            const Bucket& bucket = buckets_[bucket_id];
            if (better(bucket.far_distance, bucket.far_index,
                       best_distance, best_index)) {
                best_bucket = bucket_id;
                best_index = bucket.far_index;
                best_distance = bucket.far_distance;
            }
        }
        if (!std::isfinite(best_distance)) {
            throw std::logic_error(
                "native global far observed no finite bucket result");
        }
        return FarResult{best_bucket, best_index, best_distance};
    }

    void rebuild_traversal() {
        if (current_sample_ >= point_to_bucket_.size()) {
            throw std::logic_error("native current sample out of range");
        }
        const std::uint32_t winner_bucket =
            point_to_bucket_[current_sample_];
        if (winner_bucket == std::numeric_limits<std::uint32_t>::max()) {
            throw std::logic_error("native current sample is not in a bucket");
        }
        traversal_.clear();
        traversal_.reserve(buckets_.size());
        traversal_.push_back(winner_bucket);
        for (std::uint32_t bucket_id = 0;
             bucket_id < buckets_.size(); ++bucket_id) {
            if (bucket_id != winner_bucket) {
                traversal_.push_back(bucket_id);
            }
        }
        traversal_index_ = 0;
    }

    qfps_native_config config_{};
    std::vector<Point3> points_;
    std::vector<Bucket> buckets_;
    std::vector<std::uint32_t> point_to_bucket_;
    std::vector<std::uint32_t> traversal_;
    std::size_t traversal_index_ = 0;
    std::deque<TimedBucket> fetch_pipeline_;
    std::deque<std::uint32_t> fetch_fifo_;
    std::deque<TimedDecision> cd_pipeline_;
    std::deque<Decision> decision_fifo_;
    std::deque<TimedWriteback> writeback_pipeline_;
    std::vector<std::uint32_t> last_issue_references_;
    std::uint32_t current_sample_ = 0;
    std::uint32_t sampled_count_ = 0;
    std::uint32_t iteration_ = 0;
    std::uint32_t outstanding_ = 0;
    std::uint32_t inject_cooldown_ = 0;
    std::uint64_t expected_cycle_ = 0;
    bool done_ = false;
    qfps_native_stats stats_{};
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
        g_last_error = "unknown native scheduler error";
        return 0;
    }
}

}  // namespace

extern "C" {

void* qfps_native_scheduler_create(const qfps_native_config* config,
                                   const qfps_native_point* points,
                                   const qfps_native_bucket_init* buckets) {
    try {
        if (config == nullptr) {
            throw std::invalid_argument("native config pointer is null");
        }
        auto scheduler =
            std::make_unique<Scheduler>(*config, points, buckets);
        g_last_error.clear();
        return scheduler.release();
    } catch (const std::exception& error) {
        g_last_error = error.what();
        return nullptr;
    } catch (...) {
        g_last_error = "unknown native scheduler construction error";
        return nullptr;
    }
}

void qfps_native_scheduler_destroy(void* handle) {
    delete static_cast<Scheduler*>(handle);
}

int qfps_native_scheduler_step(void* handle,
                               const qfps_native_step_input* input,
                               qfps_native_step_output* output) {
    return guard([&]() {
        if (handle == nullptr || input == nullptr || output == nullptr) {
            throw std::invalid_argument("native step pointer is null");
        }
        static_cast<Scheduler*>(handle)->step(*input, *output);
    });
}

int qfps_native_scheduler_copy_issue_references(
    void* handle,
    std::uint32_t* output,
    std::uint32_t capacity,
    std::uint32_t* count) {
    return guard([&]() {
        if (handle == nullptr || count == nullptr) {
            throw std::invalid_argument(
                "native issue-reference pointer is null");
        }
        *count = static_cast<Scheduler*>(handle)->copy_issue_references(
            output, capacity);
    });
}

int qfps_native_scheduler_get_bucket_state(
    void* handle,
    std::uint32_t bucket_id,
    qfps_native_bucket_state* output) {
    return guard([&]() {
        if (handle == nullptr || output == nullptr) {
            throw std::invalid_argument("native bucket-state pointer is null");
        }
        *output =
            static_cast<Scheduler*>(handle)->bucket_state(bucket_id);
    });
}

int qfps_native_scheduler_copy_bucket_merge_indices(
    void* handle,
    std::uint32_t bucket_id,
    std::uint32_t* output,
    std::uint32_t capacity,
    std::uint32_t* count) {
    return guard([&]() {
        if (handle == nullptr || count == nullptr) {
            throw std::invalid_argument("native merge-index pointer is null");
        }
        *count = static_cast<Scheduler*>(handle)->copy_bucket_merge_indices(
            bucket_id, output, capacity);
    });
}

int qfps_native_scheduler_get_stats(void* handle,
                                    qfps_native_stats* output) {
    return guard([&]() {
        if (handle == nullptr || output == nullptr) {
            throw std::invalid_argument("native stats pointer is null");
        }
        *output = static_cast<Scheduler*>(handle)->stats();
    });
}

const char* qfps_native_scheduler_last_error() {
    return g_last_error.c_str();
}

}  // extern "C"
