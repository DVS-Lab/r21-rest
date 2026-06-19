#!/usr/bin/env bash

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    echo "common.sh is a shared library and must be sourced by another script." >&2
    exit 2
fi

repo_root() {
    local common_dir
    common_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
    cd "${common_dir}/../.." && pwd -P
}

REPO_ROOT="$(repo_root)"
SCRIPT_ROOT="${REPO_ROOT}/code"

info() {
    printf '[INFO] %s\n' "$*" >&2
}

warn() {
    printf '[WARN] %s\n' "$*" >&2
}

die() {
    printf '[ERROR] %s\n' "$*" >&2
    exit 1
}

timestamp_utc() {
    date -u '+%Y-%m-%dT%H:%M:%SZ'
}

timestamp_file() {
    date -u '+%Y%m%dT%H%M%SZ'
}

current_host() {
    hostname -f 2>/dev/null || hostname
}

trim() {
    local value="$1"
    value="${value#"${value%%[![:space:]]*}"}"
    value="${value%"${value##*[![:space:]]}"}"
    printf '%s\n' "$value"
}

is_truthy() {
    case "${1:-0}" in
        1|true|TRUE|yes|YES|on|ON) return 0 ;;
        *) return 1 ;;
    esac
}

normalize_participant_id() {
    local label
    label="$(trim "$1")"
    label="${label#sub-}"
    [[ -n "$label" ]] || die "Participant label is empty."
    if [[ ! "$label" =~ ^[A-Za-z0-9][A-Za-z0-9._-]*$ ]]; then
        die "Invalid participant label: $1"
    fi
    printf 'sub-%s\n' "$label"
}

participant_label_no_prefix() {
    local sub
    sub="$(normalize_participant_id "$1")"
    printf '%s\n' "${sub#sub-}"
}

print_command() {
    local arg
    local first=1
    for arg in "$@"; do
        if (( first )); then
            first=0
        else
            printf ' '
        fi
        printf '%q' "$arg"
    done
    printf '\n'
}

load_config() {
    local config_path="$1"
    if [[ -z "$config_path" ]]; then
        if [[ -f "${REPO_ROOT}/config/linux.env" ]]; then
            config_path="${REPO_ROOT}/config/linux.env"
        else
            config_path="${REPO_ROOT}/config/linux.env.example"
        fi
    fi
    [[ -f "$config_path" ]] || die "Configuration file not found: $config_path"
    # shellcheck source=/dev/null
    source "$config_path"
    CONFIG_PATH="$config_path"
    info "Using config: $CONFIG_PATH"
}

require_config_vars() {
    local name
    for name in "$@"; do
        if [[ -z "${!name:-}" ]]; then
            die "Required configuration variable is unset or empty: $name"
        fi
    done
}

require_common_config() {
    require_config_vars \
        PROJECT_NAME \
        BIDS_DIR \
        DERIVATIVES_ROOT \
        WORK_ROOT \
        LOG_ROOT \
        MANIFEST_ROOT \
        STATUS_ROOT \
        TASK_ID \
        CONTAINER_RUNTIME
}

require_fmriprep_config() {
    require_common_config
    require_config_vars \
        FMRIPREP_IMAGE \
        TEMPLATEFLOW_DIR \
        FS_LICENSE \
        FMRIPREP_OUTPUT_DIR \
        FS_SUBJECTS_DIR \
        FMRIPREP_OUTPUT_SPACES \
        CIFTI_DENSITY \
        FMRIPREP_MAX_JOBS \
        FMRIPREP_NPROCS \
        FMRIPREP_OMP_NTHREADS \
        FMRIPREP_MEM_MB
}

require_mriqc_config() {
    require_common_config
    require_config_vars \
        MRIQC_IMAGE \
        MRIQC_OUTPUT_DIR \
        MRIQC_MODALITIES \
        MRIQC_MAX_JOBS \
        MRIQC_NPROCS \
        MRIQC_OMP_NTHREADS \
        MRIQC_MEM_GB
}

ensure_dir() {
    local dir
    for dir in "$@"; do
        mkdir -p "$dir"
    done
}

require_linux_execution() {
    if [[ "$(uname -s)" != "Linux" ]]; then
        die "Execution mode is restricted to Linux. Use --dry-run or --render-only on this machine."
    fi
}

detect_container_runtime() {
    local render_only="${1:-0}"
    local runtime="${CONTAINER_RUNTIME:-auto}"

    case "$runtime" in
        auto)
            if command -v apptainer >/dev/null 2>&1; then
                printf 'apptainer\n'
            elif command -v singularity >/dev/null 2>&1; then
                printf 'singularity\n'
            elif is_truthy "$render_only"; then
                printf 'apptainer\n'
            else
                die "Neither apptainer nor singularity was found on PATH."
            fi
            ;;
        apptainer|singularity)
            if is_truthy "$render_only" || command -v "$runtime" >/dev/null 2>&1; then
                printf '%s\n' "$runtime"
            else
                die "Configured container runtime was not found on PATH: $runtime"
            fi
            ;;
        *)
            die "CONTAINER_RUNTIME must be auto, apptainer, or singularity; got: $runtime"
            ;;
    esac
}

validate_file_exists() {
    local label="$1"
    local path="$2"
    [[ -f "$path" ]] || die "$label file not found: $path"
}

validate_dir_exists() {
    local label="$1"
    local path="$2"
    [[ -d "$path" ]] || die "$label directory not found: $path"
}

available_cpus() {
    if command -v nproc >/dev/null 2>&1; then
        nproc
    else
        getconf _NPROCESSORS_ONLN
    fi
}

available_mem_mb() {
    if [[ -r /proc/meminfo ]]; then
        awk '/MemAvailable:/ { printf "%d\n", $2 / 1024 }' /proc/meminfo
    elif command -v sysctl >/dev/null 2>&1; then
        sysctl -n hw.memsize | awk '{ printf "%d\n", $1 / 1024 / 1024 }'
    else
        printf '0\n'
    fi
}

gb_to_mb() {
    local gb="$1"
    if [[ "$gb" =~ ^[0-9]+$ ]]; then
        printf '%d\n' "$(( gb * 1024 ))"
    elif [[ "$gb" =~ ^[0-9]+[.][0-9]+$ ]]; then
        awk -v gb="$gb" 'BEGIN { printf "%d\n", gb * 1024 }'
    else
        die "Memory in GB must be numeric; got: $gb"
    fi
}

validate_positive_integer() {
    local label="$1"
    local value="$2"
    [[ "$value" =~ ^[1-9][0-9]*$ ]] || die "$label must be a positive integer; got: $value"
}

check_max_jobs() {
    local max_jobs="$1"
    validate_positive_integer "--max-jobs" "$max_jobs"
    if (( max_jobs > 5 )); then
        die "--max-jobs greater than 5 is not supported by this draft."
    fi
    if (( max_jobs == 5 )); then
        warn "--max-jobs 5 is an explicit override. Resource checks still apply."
    fi
}

check_batch_resources() {
    local label="$1"
    local jobs="$2"
    local nprocs="$3"
    local mem_mb_per_job="$4"
    local allow_oversubscribe="$5"
    local render_only="$6"
    local projected_cpu projected_mem_mb available_cpu available_mem oversubscribed

    validate_positive_integer "${label} jobs" "$jobs"
    validate_positive_integer "${label} nprocs" "$nprocs"
    validate_positive_integer "${label} memory MB" "$mem_mb_per_job"

    projected_cpu="$(( jobs * nprocs ))"
    projected_mem_mb="$(( jobs * mem_mb_per_job ))"

    info "${label} projected resources: ${jobs} jobs x ${nprocs} CPUs = ${projected_cpu} CPUs; memory = ${projected_mem_mb} MB."

    if is_truthy "$render_only"; then
        info "${label} render-only mode: available Linux resources are not checked."
        return 0
    fi

    require_linux_execution
    available_cpu="$(available_cpus)"
    available_mem="$(available_mem_mb)"
    info "Available Linux resources: ${available_cpu} CPUs; ${available_mem} MB memory."

    oversubscribed=0
    if (( available_cpu > 0 && projected_cpu > available_cpu )); then
        warn "${label} requests ${projected_cpu} CPUs, exceeding available CPUs (${available_cpu})."
        oversubscribed=1
    fi
    if (( available_mem > 0 && projected_mem_mb > available_mem )); then
        warn "${label} requests ${projected_mem_mb} MB, exceeding available memory (${available_mem} MB)."
        oversubscribed=1
    fi
    if (( oversubscribed )) && ! is_truthy "$allow_oversubscribe"; then
        die "Requested ${label} resources appear oversubscribed. Re-run with --allow-oversubscribe only after review."
    fi
}

read_subjects_file() {
    local subjects_file="$1"
    local line cleaned
    [[ -f "$subjects_file" ]] || die "Subjects file not found: $subjects_file"
    while IFS= read -r line || [[ -n "$line" ]]; do
        cleaned="${line%%#*}"
        cleaned="$(trim "$cleaned")"
        [[ -z "$cleaned" ]] && continue
        normalize_participant_id "$cleaned"
    done < "$subjects_file" | LC_ALL=C sort -u
}

list_bids_subjects() {
    validate_dir_exists "BIDS" "$BIDS_DIR"
    local path name old_nullglob
    local subjects=()
    old_nullglob="$(shopt -p nullglob || true)"
    shopt -s nullglob
    for path in "$BIDS_DIR"/sub-*; do
        [[ -d "$path" ]] || continue
        name="${path##*/}"
        subjects+=("$(normalize_participant_id "$name")")
    done
    eval "$old_nullglob"
    if ((${#subjects[@]})); then
        printf '%s\n' "${subjects[@]}" | LC_ALL=C sort -u
    fi
}

status_dir() {
    local tool="$1"
    printf '%s/%s\n' "$STATUS_ROOT" "$tool"
}

status_marker() {
    local tool="$1"
    local participant="$2"
    local state="$3"
    printf '%s/%s.%s\n' "$(status_dir "$tool")" "$participant" "$state"
}

archive_existing_marker() {
    local marker="$1"
    local stamp
    if [[ -e "$marker" ]]; then
        stamp="$(timestamp_file)"
        mv "$marker" "${marker}.${stamp}.bak"
    fi
}

marker_value() {
    local marker="$1"
    local key="$2"
    awk -F= -v key="$key" '$1 == key { sub(/^[^=]*=/, ""); print; exit }' "$marker"
}

running_marker_is_active() {
    local marker="$1"
    local marker_pid marker_host this_host
    [[ -f "$marker" ]] || return 1
    marker_pid="$(marker_value "$marker" "PID")"
    marker_host="$(marker_value "$marker" "HOSTNAME")"
    this_host="$(current_host)"
    [[ "$marker_pid" =~ ^[0-9]+$ ]] || return 1
    [[ -n "$marker_host" ]] || return 1
    [[ "$marker_host" == "$this_host" ]] || return 1
    kill -0 "$marker_pid" >/dev/null 2>&1
}

guard_running_marker() {
    local tool="$1"
    local participant="$2"
    local marker
    marker="$(status_marker "$tool" "$participant" "running")"
    if [[ -f "$marker" ]]; then
        if running_marker_is_active "$marker"; then
            die "${tool} already appears to be running for ${participant}; marker: $marker"
        fi
        warn "Found stale ${tool} running marker for ${participant}; archiving before restart."
        archive_existing_marker "$marker"
    fi
}

write_status_marker() {
    local tool="$1"
    local participant="$2"
    local state="$3"
    local return_code="${4:-}"
    local command_file="${5:-}"
    local stdout_log="${6:-}"
    local stderr_log="${7:-}"
    local marker
    marker="$(status_marker "$tool" "$participant" "$state")"
    ensure_dir "$(dirname "$marker")"
    archive_existing_marker "$marker"
    {
        printf 'TOOL=%s\n' "$tool"
        printf 'PARTICIPANT=%s\n' "$participant"
        printf 'STATE=%s\n' "$state"
        printf 'TIMESTAMP_UTC=%s\n' "$(timestamp_utc)"
        printf 'HOSTNAME=%s\n' "$(current_host)"
        printf 'PID=%s\n' "$$"
        [[ -n "$return_code" ]] && printf 'RETURN_CODE=%s\n' "$return_code"
        [[ -n "$command_file" ]] && printf 'COMMAND_FILE=%s\n' "$command_file"
        [[ -n "$stdout_log" ]] && printf 'STDOUT_LOG=%s\n' "$stdout_log"
        [[ -n "$stderr_log" ]] && printf 'STDERR_LOG=%s\n' "$stderr_log"
    } > "$marker"
}
