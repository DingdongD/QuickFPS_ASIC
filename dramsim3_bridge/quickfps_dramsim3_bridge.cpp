#include <cstdint>
#include <deque>
#include <exception>
#include <memory>
#include <string>
#include <unordered_map>
#include <utility>

#include "memory_system.h"

namespace {

struct Completion {
    std::uint64_t tag = 0;
    std::uint64_t address = 0;
    bool is_write = false;
};

struct Key {
    std::uint64_t address = 0;
    bool is_write = false;

    bool operator==(const Key& other) const noexcept {
        return address == other.address && is_write == other.is_write;
    }
};

struct KeyHash {
    std::size_t operator()(const Key& key) const noexcept {
        return std::hash<std::uint64_t>{}(key.address) ^
               (static_cast<std::size_t>(key.is_write) << 1U);
    }
};

class Bridge {
public:
    Bridge(const std::string& config_file, const std::string& output_dir) {
        memory_ = std::make_unique<dramsim3::MemorySystem>(
            config_file,
            output_dir,
            [this](std::uint64_t address) { complete(address, false); },
            [this](std::uint64_t address) { complete(address, true); });
    }

    bool will_accept(std::uint64_t address, bool is_write) const {
        return memory_->WillAcceptTransaction(address, is_write);
    }

    bool add(std::uint64_t address, bool is_write, std::uint64_t tag) {
        if (!memory_->WillAcceptTransaction(address, is_write)) {
            return false;
        }
        if (!memory_->AddTransaction(address, is_write)) {
            return false;
        }
        tags_[Key{address, is_write}].push_back(tag);
        return true;
    }

    void tick() { memory_->ClockTick(); }

    bool poll(Completion& completion) {
        if (completions_.empty()) {
            return false;
        }
        completion = completions_.front();
        completions_.pop_front();
        return true;
    }

private:
    void complete(std::uint64_t address, bool is_write) {
        const Key key{address, is_write};
        auto found = tags_.find(key);
        if (found == tags_.end() || found->second.empty()) {
            // A callback without a matching submission indicates a bridge or
            // simulator contract violation. Keep the C ABI noexcept and expose
            // a sentinel tag that the Python model rejects explicitly.
            completions_.push_back(Completion{UINT64_MAX, address, is_write});
            return;
        }
        const std::uint64_t tag = found->second.front();
        found->second.pop_front();
        if (found->second.empty()) {
            tags_.erase(found);
        }
        completions_.push_back(Completion{tag, address, is_write});
    }

    std::unique_ptr<dramsim3::MemorySystem> memory_;
    std::unordered_map<Key, std::deque<std::uint64_t>, KeyHash> tags_;
    std::deque<Completion> completions_;
};

}  // namespace

extern "C" {

void* qfps_dramsim3_create(const char* config_file, const char* output_dir) {
    try {
        if (config_file == nullptr || output_dir == nullptr) {
            return nullptr;
        }
        return new Bridge(config_file, output_dir);
    } catch (const std::exception&) {
        return nullptr;
    } catch (...) {
        return nullptr;
    }
}

void qfps_dramsim3_destroy(void* handle) {
    delete static_cast<Bridge*>(handle);
}

int qfps_dramsim3_will_accept(void* handle,
                              std::uint64_t address,
                              int is_write) {
    if (handle == nullptr) {
        return 0;
    }
    return static_cast<Bridge*>(handle)->will_accept(address, is_write != 0)
               ? 1
               : 0;
}

int qfps_dramsim3_add(void* handle,
                      std::uint64_t address,
                      int is_write,
                      std::uint64_t tag) {
    if (handle == nullptr) {
        return 0;
    }
    return static_cast<Bridge*>(handle)->add(address, is_write != 0, tag)
               ? 1
               : 0;
}

void qfps_dramsim3_tick(void* handle) {
    if (handle != nullptr) {
        static_cast<Bridge*>(handle)->tick();
    }
}

int qfps_dramsim3_poll(void* handle,
                       std::uint64_t* tag,
                       std::uint64_t* address,
                       int* is_write) {
    if (handle == nullptr || tag == nullptr || address == nullptr ||
        is_write == nullptr) {
        return 0;
    }
    Completion completion;
    if (!static_cast<Bridge*>(handle)->poll(completion)) {
        return 0;
    }
    *tag = completion.tag;
    *address = completion.address;
    *is_write = completion.is_write ? 1 : 0;
    return 1;
}

}  // extern "C"
