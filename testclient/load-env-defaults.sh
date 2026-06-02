#!/usr/bin/env bash

load_env_defaults() {
  local env_file="${1:-.env}"
  [ -f "$env_file" ] || return 0

  local existing_keys=()
  local existing_values=()
  local line key
  while IFS= read -r line || [ -n "$line" ]; do
    line="${line#"${line%%[![:space:]]*}"}"
    line="${line%"${line##*[![:space:]]}"}"
    [[ -z "$line" || "$line" == \#* ]] && continue
    [[ "$line" == export\ * ]] && line="${line#export }"
    [[ "$line" == *=* ]] || continue
    key="${line%%=*}"
    key="${key%"${key##*[![:space:]]}"}"
    [[ "$key" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] || continue
    if [ -n "${!key+x}" ]; then
      existing_keys+=("$key")
      existing_values+=("${!key}")
    fi
  done < "$env_file"

  set -a
  . "$env_file"
  set +a

  local index
  for index in "${!existing_keys[@]}"; do
    export "${existing_keys[$index]}=${existing_values[$index]}"
  done
}
