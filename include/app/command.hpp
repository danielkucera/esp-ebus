#pragma once

#if defined(EBUS_INTERNAL)

#include <ebus/data_types.hpp>
#include <ebus/detail/json_reader.hpp>
#include <ebus/static_vector.hpp>
#include <ebus/types.hpp>
#include <limits>
#include <string>
#include <string_view>

#include "app/data_profile.hpp"
#include "app/ha_profile.hpp"
#include "system/string_pool.hpp"

namespace command_types {

enum class WriteType : uint8_t { simple, weishaupt, invalid };

#ifndef COMMAND_MAX_FIELDS
inline constexpr size_t max_fields = 4;
#else
inline constexpr size_t max_fields = COMMAND_MAX_FIELDS;
#endif

struct FieldRef {
  uint8_t name_id = 0;
  uint8_t profile_idx = 0;
  uint8_t position = 0;
  // Home Assistant - per-field (0 = no HA profile)
  uint8_t ha_profile_idx = 0;
  // Raw presentation: skip sentinel-to-null mapping in decode, return the
  // raw numeric value instead. Opt-in per field (default false).
  bool raw = false;
};

using FieldVector = ebus::StaticVector<FieldRef, max_fields>;
}  // namespace command_types

namespace ebus::detail {
class JsonWriter;
}

using PollSequence =
    ebus::SequenceImpl<ebus::detail::SequenceLimits::poll_capacity>;

class Command {
 public:
  const uint32_t& getSessionId() const;
  void setSessionId(const uint32_t id);

  const uint16_t& getPollId() const;
  void setPollId(const uint16_t id);

  const uint32_t& getLast() const;
  void setLast(const uint32_t time);

  ebus::ByteView getData() const;
  void setData(ebus::ByteView data);

  std::string_view getKey() const;
  uint8_t getKeyId() const;
  std::string_view getName() const;

  // Compact telegram identity (ebusd model): zz + id (read) + wid (write).
  // Wire telegrams are built on demand; NN is derived from the id length
  // unless an explicit override (nn_ovr) was parsed.
  ebus::ByteView getZz() const;
  ebus::ByteView getId() const;
  ebus::ByteView getWid() const;
  // Explicit read-NN override (legacy read_cmd where NN != len(id)-2).
  bool hasNnOverride() const;
  ebus::ByteView getNn() const;
  // Builds the read master telegram ZZ id[0] id[1] NN id[2..] into out;
  // returns the length, or 0 when there is no id or cap is too small.
  size_t buildReadCmd(uint8_t* out, size_t cap) const;
  // Builds the complete write master telegram ZZ wid[0] wid[1] NN
  // wid[2..] + value. NN = legacy write_cmd NN when one was parsed,
  // otherwise len(wid)-2 + value.size(). Simple write_type only; empty
  // when the command is not writable.
  ebus::Sequence buildWriteCmd(ebus::ByteView value) const;

  bool hasWriteCmd() const;

  // Builds the full write frame for the command's write_type: buildWriteCmd
  // for simple, the weishaupt 5023 encoding for weishaupt. Empty for
  // read-only commands, empty values and rejected encodings.
  ebus::Sequence buildWriteSequence(const class CommandManager& manager,
                                    ebus::ByteView value) const;

  command_types::WriteType getWriteType() const { return write_type_; }
  const char* getWriteTypeName() const;

  bool getActive() const;
  const uint16_t& getInterval() const;
  bool getMaster() const;

  const command_types::FieldVector& getFields() const;
  const DataProfile* getFieldProfile(size_t i) const;
  const char* getFieldName(size_t i) const;
  size_t getFieldPosition(size_t i) const;
  ebus::DataType getFieldDatatype(size_t i) const;
  float getFieldDivider(size_t i) const;
  float getFieldMin(size_t i) const;
  float getFieldMax(size_t i) const;
  uint8_t getFieldDigits(size_t i) const;
  const char* getFieldUnit(size_t i) const;
  size_t getFieldCount() const;
  size_t getFieldIndex(std::string_view name) const;

  // Per-field HA accessors
  bool hasFieldHA(size_t i) const;
  const HAProfile* getFieldHAProfile(size_t i) const;
  std::string_view getFieldHAProfileName(size_t i) const;

  // Raw presentation flag for field i (out of range reads false).
  bool isFieldRaw(size_t i) const;

  bool matches(ebus::ByteView master_view) const;

  void writeFieldValue(ebus::detail::JsonWriter& writer, size_t i) const;
  // Writes "text" with the HA enum display name when the decoded number
  // maps (key_value_pairs); returns false (writes nothing) otherwise.
  bool writeFieldText(ebus::detail::JsonWriter& writer, size_t i) const;
  void writeValuePayload(ebus::detail::JsonWriter& writer) const;

  void getValueJson(ebus::detail::JsonWriter& writer) const;

  ebus::Sequence getVectorFromJson(std::string_view json) const;
  ebus::Sequence getVectorFromValue(std::string_view value_json,
                                    size_t field_idx = 0) const;
  ebus::Sequence getVectorFromDouble(double value, size_t field_idx = 0) const;
  ebus::Sequence getVectorFromString(std::string_view value,
                                     size_t field_idx = 0) const;

  size_t writeLogMessage(char* buf, size_t len) const;

  static Command fromJson(ebus::detail::JsonReader& reader);
  // legacy: rows carry read_cmd/write_cmd wire hex instead of zz/id/wid.
  // has_nn: compact rows include the optional nn column (see saveCommands;
  // sniffed from the header row by the loaders).
  static Command fromTabular(ebus::detail::JsonReader& reader, bool legacy,
                             bool has_nn = true);

  static std::string_view evaluate(ebus::detail::JsonReader& reader);

 private:
  // Parsers shared by fromJson/fromTabular. Compact id/wid carry 2..6
  // bytes (PB SB DD...); legacy read_cmd/write_cmd carry the full wire
  // hex (ZZ PB SB NN D...): read keeps NN only when it differs from
  // len(id)-2 (explicit override), write keeps its NN as a candidate -
  // the value length is unknowable at parse time, so buildWriteCmd
  // decides between the stored and the derived NN.
  void setIdBytes(ebus::ByteView bytes);
  void setWidBytes(ebus::ByteView bytes);
  void setLegacyReadCmd(ebus::ByteView bytes);
  void setLegacyWriteCmd(ebus::ByteView bytes);

  uint32_t session_id_ = 0;
  uint16_t poll_id_ = 0;
  uint32_t last_ = 0;
  PollSequence data_;

  uint8_t key_id_ = 0;
  uint8_t name_id_ = 0;
  uint8_t zz_ = 0;
  uint8_t id_len_ = 0;
  uint8_t id_[6] = {};
  uint8_t wid_len_ = 0;
  uint8_t wid_[6] = {};
  bool has_nn_ovr_ = false;
  uint8_t nn_ovr_ = 0;
  // Legacy write-NN candidate (in-memory only, never serialized): the
  // effective write NN is wnn_ when set, the derived one otherwise.
  bool has_wnn_ = false;
  uint8_t wnn_ = 0;
  uint16_t interval_ = 60;
  bool master_ = false;
  command_types::WriteType write_type_ = command_types::WriteType::simple;

  command_types::FieldVector fields_;
};

#endif