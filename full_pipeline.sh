# To run everything manually:
#   bash /Users/kalilbouzigues/Projects/stapply-ai/data/full_pipeline.sh all

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_BIN="$PROJECT_ROOT/.venv/bin"
PYTHON="$VENV_BIN/python"
LOG_FILE="$PROJECT_ROOT/logs/ai.log"

# Ensure Homebrew binaries are in PATH for cron (vercel CLI is installed via Homebrew)
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"

# Detect if running interactively (from terminal, not cron) and initialize LOG_TO_TERMINAL
# Must be done early before any functions that use it
if [[ -t 1 ]]; then
  LOG_TO_TERMINAL=1
else
  LOG_TO_TERMINAL=0
fi

# Error logging function
log_error() {
  local error_msg="[ERROR] $(date '+%Y-%m-%d %H:%M:%S') - $*"
  {
    echo "$error_msg"
    echo "[ERROR] Command: $BASH_COMMAND"
    echo "[ERROR] Exit code: $?"
  } >> "$LOG_FILE" 2>&1
  if [[ ${LOG_TO_TERMINAL:-0} -eq 1 ]]; then
    echo "$error_msg" >&2
  fi
}

# Trap to catch errors and log them
trap 'log_error "Script failed at line $LINENO"' ERR

# Helpful to understand the cron environment when this script runs
log_startup() {
  local startup_msg="=== full_pipeline.sh run at $(date) ==="
  {
    echo
    echo "$startup_msg"
    echo "USER=$USER"
    echo "PATH=$PATH"
    echo "PROJECT_ROOT=$PROJECT_ROOT"
    echo "PYTHON=$PYTHON"
  } >> "$LOG_FILE" 2>&1
  if [[ ${LOG_TO_TERMINAL:-0} -eq 1 ]]; then
    echo
    echo "$startup_msg"
    echo "USER=$USER"
    echo "PATH=$PATH"
    echo "PROJECT_ROOT=$PROJECT_ROOT"
    echo "PYTHON=$PYTHON"
  fi
}
log_startup

# Verify virtual environment exists
if [[ ! -f "$PYTHON" ]]; then
  {
    echo "[ERROR] Python interpreter not found at: $PYTHON"
    echo "[ERROR] Virtual environment may not exist at: $VENV_BIN"
    echo "[ERROR] Please ensure .venv is set up correctly"
  } >> "$LOG_FILE" 2>&1
  exit 1
fi

# Verify Python is executable
if [[ ! -x "$PYTHON" ]]; then
  {
    echo "[ERROR] Python interpreter is not executable: $PYTHON"
  } >> "$LOG_FILE" 2>&1
  exit 1
fi

# Helper function to run Python scripts with error handling
run_python_script() {
  local script_path="$1"
  local script_name="$2"

  set +e
  if [[ ${LOG_TO_TERMINAL:-0} -eq 1 ]]; then
    # When interactive, show output in both terminal and log file
    "$PYTHON" "$script_path" 2>&1 | tee -a "$LOG_FILE"
    local exit_code=${PIPESTATUS[0]}
  else
    # When non-interactive (cron), only log to file
    "$PYTHON" "$script_path" >> "$LOG_FILE" 2>&1
    local exit_code=$?
  fi
  set -e

  if [[ $exit_code -ne 0 ]]; then
    {
      echo "[ERROR] $script_name failed with exit code $exit_code"
    } >> "$LOG_FILE" 2>&1
    if [[ ${LOG_TO_TERMINAL:-0} -eq 1 ]]; then
      echo "[ERROR] $script_name failed with exit code $exit_code" >&2
    fi
    return 1
  fi
  return 0
}

# Same as run_python_script, but forwards additional args to the script.
# Used by jobhive-only scrapers that take an ATS name as a positional arg.
run_python_script_with_args() {
  local script_path="$1"
  local script_name="$2"
  shift 2

  set +e
  if [[ ${LOG_TO_TERMINAL:-0} -eq 1 ]]; then
    "$PYTHON" "$script_path" "$@" 2>&1 | tee -a "$LOG_FILE"
    local exit_code=${PIPESTATUS[0]}
  else
    "$PYTHON" "$script_path" "$@" >> "$LOG_FILE" 2>&1
    local exit_code=$?
  fi
  set -e

  if [[ $exit_code -ne 0 ]]; then
    {
      echo "[ERROR] $script_name failed with exit code $exit_code"
    } >> "$LOG_FILE" 2>&1
    if [[ ${LOG_TO_TERMINAL:-0} -eq 1 ]]; then
      echo "[ERROR] $script_name failed with exit code $exit_code" >&2
    fi
    return 1
  fi
  return 0
}

# Generic runner for jobhive-only scrapers (no legacy data/{ats}/main.py).
# Reads the tenant CSV, scrapes each via jobhive, writes data/{ats}/jobs.csv.
run_jobhive_ats() {
  local ats="$1"
  local msg="[run_jobhive_${ats}] Starting jobhive pipeline at $(date '+%Y-%m-%d %H:%M:%S')..."
  {
    echo "$msg"
  } >> "$LOG_FILE" 2>&1
  if [[ ${LOG_TO_TERMINAL:-0} -eq 1 ]]; then
    echo "$msg"
  fi

  if ! run_python_script_with_args "$PROJECT_ROOT/jobhive/scripts/run_pipeline.py" "run_jobhive_${ats}" "$ats"; then
    return 1
  fi

  msg="[run_jobhive_${ats}] Completed successfully at $(date '+%Y-%m-%d %H:%M:%S')"
  {
    echo "$msg"
  } >> "$LOG_FILE" 2>&1
  if [[ ${LOG_TO_TERMINAL:-0} -eq 1 ]]; then
    echo "$msg"
  fi
}

run_cornerstone() { run_jobhive_ats cornerstone; }
run_icims()       { run_jobhive_ats icims; }
run_breezy()      { run_jobhive_ats breezy; }
run_successfactors() { run_jobhive_ats successfactors; }
run_taleo()       { run_jobhive_ats taleo; }
run_oracle()      { run_jobhive_ats oracle; }
run_phenom()      { run_jobhive_ats phenom; }
run_pinpoint()    { run_jobhive_ats pinpoint; }
run_recruiterbox(){ run_jobhive_ats recruiterbox; }
run_eightfold()   { run_jobhive_ats eightfold; }
run_bamboohr()    { run_jobhive_ats bamboohr; }
run_teamtailor()  { run_jobhive_ats teamtailor; }
run_jazzhr()      { run_jobhive_ats jazzhr; }
run_recruitee()   { run_jobhive_ats recruitee; }
run_bundesagentur(){ run_jobhive_ats bundesagentur; }
run_arbetsformedlingen(){ run_jobhive_ats arbetsformedlingen; }

run_ashby()    { run_jobhive_ats ashby; }

run_greenhouse()    { run_jobhive_ats greenhouse; }

run_lever()    { run_jobhive_ats lever; }

run_workable()    { run_jobhive_ats workable; }

run_workday()    { run_jobhive_ats workday; }

run_avature()    { run_jobhive_ats avature; }

run_google()    { run_jobhive_ats google; }

run_amazon()    { run_jobhive_ats amazon; }

run_meta()    { run_jobhive_ats meta; }

run_apple()    { run_jobhive_ats apple; }

run_nvidia() {
  local msg="[run_nvidia] Starting NVIDIA pipeline at $(date '+%Y-%m-%d %H:%M:%S')..."
  {
    echo "$msg"
  } >> "$LOG_FILE" 2>&1
  if [[ ${LOG_TO_TERMINAL:-0} -eq 1 ]]; then
    echo "$msg"
  fi

  if ! run_python_script "$PROJECT_ROOT/nvidia/main.py" "run_nvidia: main.py"; then
    return 1
  fi

  msg="[run_nvidia] Completed successfully at $(date '+%Y-%m-%d %H:%M:%S')"
  {
    echo "$msg"
  } >> "$LOG_FILE" 2>&1
  if [[ ${LOG_TO_TERMINAL:-0} -eq 1 ]]; then
    echo "$msg"
  fi
}

run_microsoft() {
  local msg="[run_microsoft] Starting Microsoft pipeline at $(date '+%Y-%m-%d %H:%M:%S')..."
  {
    echo "$msg"
  } >> "$LOG_FILE" 2>&1
  if [[ ${LOG_TO_TERMINAL:-0} -eq 1 ]]; then
    echo "$msg"
  fi

  if ! run_python_script "$PROJECT_ROOT/microsoft/main.py" "run_microsoft: main.py"; then
    return 1
  fi

  msg="[run_microsoft] Completed successfully at $(date '+%Y-%m-%d %H:%M:%S')"
  {
    echo "$msg"
  } >> "$LOG_FILE" 2>&1
  if [[ ${LOG_TO_TERMINAL:-0} -eq 1 ]]; then
    echo "$msg"
  fi
}

run_tiktok()    { run_jobhive_ats tiktok; }

run_cursor() {
  local msg="[run_cursor] Starting Cursor pipeline at $(date '+%Y-%m-%d %H:%M:%S')..."
  {
    echo "$msg"
  } >> "$LOG_FILE" 2>&1
  if [[ ${LOG_TO_TERMINAL:-0} -eq 1 ]]; then
    echo "$msg"
  fi

  if ! run_python_script "$PROJECT_ROOT/cursor/main.py" "run_cursor: main.py"; then
    return 1
  fi

  msg="[run_cursor] Completed successfully at $(date '+%Y-%m-%d %H:%M:%S')"
  {
    echo "$msg"
  } >> "$LOG_FILE" 2>&1
  if [[ ${LOG_TO_TERMINAL:-0} -eq 1 ]]; then
    echo "$msg"
  fi
}

run_tesla()    { run_jobhive_ats tesla; }

run_mercor()    { run_jobhive_ats mercor; }

run_smartrecruiters()    { run_jobhive_ats smartrecruiters; }

run_join()    { run_jobhive_ats join_com; }

run_rippling()    { run_jobhive_ats rippling; }

run_personio()    { run_jobhive_ats personio; }

run_ai() {
  local msg="[run_ai] Starting AI pipeline at $(date '+%Y-%m-%d %H:%M:%S')..."
  {
    echo "$msg"
  } >> "$LOG_FILE" 2>&1
  if [[ ${LOG_TO_TERMINAL:-0} -eq 1 ]]; then
    echo "$msg"
  fi
  
  # Run ai.py with output path pointing to ../map/public/ai.csv
  set +e
  if [[ ${LOG_TO_TERMINAL:-0} -eq 1 ]]; then
    "$PYTHON" "$PROJECT_ROOT/ai.py" --output ../map/public/ai.csv 2>&1 | tee -a "$LOG_FILE"
    local exit_code=${PIPESTATUS[0]}
  else
    "$PYTHON" "$PROJECT_ROOT/ai.py" --output ../map/public/ai.csv >> "$LOG_FILE" 2>&1
    local exit_code=$?
  fi
  set -e
  
  if [[ $exit_code -ne 0 ]]; then
    {
      echo "[ERROR] run_ai: ai.py failed with exit code $exit_code"
    } >> "$LOG_FILE" 2>&1
    if [[ ${LOG_TO_TERMINAL:-0} -eq 1 ]]; then
      echo "[ERROR] run_ai: ai.py failed with exit code $exit_code" >&2
    fi
    return 1
  fi
  
  # Resolve vercel in the current PATH so failures are visible in logs
  VERCEL_BIN="$(command -v vercel || true)"
  if [[ -z "$VERCEL_BIN" ]]; then
    msg="[run_ai] vercel CLI not found in PATH, skipping deploy"
    {
      echo "$msg"
    } >> "$LOG_FILE" 2>&1
    if [[ ${LOG_TO_TERMINAL:-0} -eq 1 ]]; then
      echo "$msg"
    fi
  else
    msg="[run_ai] Deploying to Vercel at $(date '+%Y-%m-%d %H:%M:%S')..."
    {
      echo "$msg"
    } >> "$LOG_FILE" 2>&1
    if [[ ${LOG_TO_TERMINAL:-0} -eq 1 ]]; then
      echo "$msg"
    fi
    
    set +e
    if [[ ${LOG_TO_TERMINAL:-0} -eq 1 ]]; then
      (cd "$PROJECT_ROOT/../map" && "$VERCEL_BIN" --prod 2>&1 | tee -a "$LOG_FILE")
      local exit_code=${PIPESTATUS[0]}
    else
      (cd "$PROJECT_ROOT/../map" && "$VERCEL_BIN" --prod >> "$LOG_FILE" 2>&1)
      local exit_code=$?
    fi
    set -e
    
    if [[ $exit_code -ne 0 ]]; then
      msg="[ERROR] run_ai: Vercel deployment failed with exit code $exit_code"
      {
        echo "$msg"
      } >> "$LOG_FILE" 2>&1
      if [[ ${LOG_TO_TERMINAL:-0} -eq 1 ]]; then
        echo "$msg" >&2
      fi
      return 1
    fi
  fi
  
  msg="[run_ai] Completed successfully at $(date '+%Y-%m-%d %H:%M:%S')"
  {
    echo "$msg"
  } >> "$LOG_FILE" 2>&1
  if [[ ${LOG_TO_TERMINAL:-0} -eq 1 ]]; then
    echo "$msg"
  fi
}

run_fetch_job() {
  local msg="[run_fetch_job] Starting fetch_job at $(date '+%Y-%m-%d %H:%M:%S')..."
  {
    echo "$msg"
  } >> "$LOG_FILE" 2>&1
  if [[ ${LOG_TO_TERMINAL:-0} -eq 1 ]]; then
    echo "$msg"
  fi
  
  if ! run_python_script "$PROJECT_ROOT/fetch_job.py" "run_fetch_job: fetch_job.py"; then
    return 1
  fi
  
  msg="[run_fetch_job] Completed successfully at $(date '+%Y-%m-%d %H:%M:%S')"
  {
    echo "$msg"
  } >> "$LOG_FILE" 2>&1
  if [[ ${LOG_TO_TERMINAL:-0} -eq 1 ]]; then
    echo "$msg"
  fi
}

JOB="${1:-all}"

# Track if any step failed
FAILED=0

# Temporarily disable exit on error for function calls so we can handle errors gracefully
set +e

case "$JOB" in
  ashby)
    if ! run_ashby; then
      FAILED=1
    fi
    ;;
  greenhouse)
    if ! run_greenhouse; then
      FAILED=1
    fi
    ;;
  lever)
    if ! run_lever; then
      FAILED=1
    fi
    ;;
  workable)
    if ! run_workable; then
      FAILED=1
    fi
    ;;
  workday)
    if ! run_workday; then
      FAILED=1
    fi
    ;;
  avature)
    if ! run_avature; then
      FAILED=1
    fi
    ;;
  google)
    if ! run_google; then
      FAILED=1
    fi
    ;;
  amazon)
    if ! run_amazon; then
      FAILED=1
    fi
    ;;
  meta)
    if ! run_meta; then
      FAILED=1
    fi
    ;;
  apple)
    if ! run_apple; then
      FAILED=1
    fi
    ;;
  nvidia)
    if ! run_nvidia; then
      FAILED=1
    fi
    ;;
  microsoft)
    if ! run_microsoft; then
      FAILED=1
    fi
    ;;
  tiktok)
    if ! run_tiktok; then
      FAILED=1
    fi
    ;;
  cursor)
    if ! run_cursor; then
      FAILED=1
    fi
    ;;
  tesla)
    if ! run_tesla; then
      FAILED=1
    fi
    ;;
  mercor)
    if ! run_mercor; then
      FAILED=1
    fi
    ;;
  smartrecruiters)
    if ! run_smartrecruiters; then
      FAILED=1
    fi
    ;;
  cornerstone)
    if ! run_cornerstone; then
      FAILED=1
    fi
    ;;
  icims)
    if ! run_icims; then
      FAILED=1
    fi
    ;;
  breezy)
    if ! run_breezy; then
      FAILED=1
    fi
    ;;
  successfactors)
    if ! run_successfactors; then
      FAILED=1
    fi
    ;;
  taleo)
    if ! run_taleo; then
      FAILED=1
    fi
    ;;
  oracle)
    if ! run_oracle; then
      FAILED=1
    fi
    ;;
  phenom)
    if ! run_phenom; then
      FAILED=1
    fi
    ;;
  pinpoint)
    if ! run_pinpoint; then
      FAILED=1
    fi
    ;;
  recruiterbox)
    if ! run_recruiterbox; then
      FAILED=1
    fi
    ;;
  eightfold)
    if ! run_eightfold; then
      FAILED=1
    fi
    ;;
  bamboohr)
    if ! run_bamboohr; then
      FAILED=1
    fi
    ;;
  teamtailor)
    if ! run_teamtailor; then
      FAILED=1
    fi
    ;;
  jazzhr)
    if ! run_jazzhr; then
      FAILED=1
    fi
    ;;
  recruitee)
    if ! run_recruitee; then
      FAILED=1
    fi
    ;;
  bundesagentur)
    if ! run_bundesagentur; then
      FAILED=1
    fi
    ;;
  arbetsformedlingen)
    if ! run_arbetsformedlingen; then
      FAILED=1
    fi
    ;;
  join)
    if ! run_join; then
      FAILED=1
    fi
    ;;
  rippling)
    if ! run_rippling; then
      FAILED=1
    fi
    ;;
  personio)
    if ! run_personio; then
      FAILED=1
    fi
    ;;
  google)
    run_google
    ;;
  ai)
    if ! run_ai; then
      FAILED=1
    fi
    ;;
  fetch_job)
    if ! run_fetch_job; then
      FAILED=1
    fi
    ;;
  all)

    msg="[pipeline] Running full pipeline (all jobs)..."
    {
      echo "$msg"
    } >> "$LOG_FILE" 2>&1
    if [[ ${LOG_TO_TERMINAL:-0} -eq 1 ]]; then
      echo "$msg"
    fi
    
    if ! run_ashby; then
      FAILED=1
      warn_msg="[WARNING] run_ashby failed, continuing with other jobs..."
      {
        echo "$warn_msg"
      } >> "$LOG_FILE" 2>&1
      if [[ ${LOG_TO_TERMINAL:-0} -eq 1 ]]; then
        echo "$warn_msg" >&2
      fi
    fi
    
    if ! run_greenhouse; then
      FAILED=1
      warn_msg="[WARNING] run_greenhouse failed, continuing with other jobs..."
      {
        echo "$warn_msg"
      } >> "$LOG_FILE" 2>&1
      if [[ ${LOG_TO_TERMINAL:-0} -eq 1 ]]; then
        echo "$warn_msg" >&2
      fi
    fi
    
    if ! run_lever; then
      FAILED=1
      warn_msg="[WARNING] run_lever failed, continuing with other jobs..."
      {
        echo "$warn_msg"
      } >> "$LOG_FILE" 2>&1
      if [[ ${LOG_TO_TERMINAL:-0} -eq 1 ]]; then
        echo "$warn_msg" >&2
      fi
    fi
    
    if ! run_workable; then
      FAILED=1
      warn_msg="[WARNING] run_workable failed, continuing with other jobs..."
      {
        echo "$warn_msg"
      } >> "$LOG_FILE" 2>&1
      if [[ ${LOG_TO_TERMINAL:-0} -eq 1 ]]; then
        echo "$warn_msg" >&2
      fi
    fi

    if ! run_workday; then
      FAILED=1
      warn_msg="[WARNING] run_workday failed, continuing with other jobs..."
      {
        echo "$warn_msg"
      } >> "$LOG_FILE" 2>&1
      if [[ ${LOG_TO_TERMINAL:-0} -eq 1 ]]; then
        echo "$warn_msg" >&2
      fi
    fi

    if ! run_avature; then
      FAILED=1
      warn_msg="[WARNING] run_avature failed, continuing with other jobs..."
      {
        echo "$warn_msg"
      } >> "$LOG_FILE" 2>&1
      if [[ ${LOG_TO_TERMINAL:-0} -eq 1 ]]; then
        echo "$warn_msg" >&2
      fi
    fi

    if ! run_google; then
      FAILED=1
      warn_msg="[WARNING] run_google failed, continuing with other jobs..."
      {
        echo "$warn_msg"
      } >> "$LOG_FILE" 2>&1
      if [[ ${LOG_TO_TERMINAL:-0} -eq 1 ]]; then
        echo "$warn_msg" >&2
      fi
    fi

    if ! run_amazon; then
      FAILED=1
      warn_msg="[WARNING] run_amazon failed, continuing with other jobs..."
      {
        echo "$warn_msg"
      } >> "$LOG_FILE" 2>&1
      if [[ ${LOG_TO_TERMINAL:-0} -eq 1 ]]; then
        echo "$warn_msg" >&2
      fi
    fi

    if ! run_meta; then
      FAILED=1
      warn_msg="[WARNING] run_meta failed, continuing with other jobs..."
      {
        echo "$warn_msg"
      } >> "$LOG_FILE" 2>&1
      if [[ ${LOG_TO_TERMINAL:-0} -eq 1 ]]; then
        echo "$warn_msg" >&2
      fi
    fi

    if ! run_apple; then
      FAILED=1
      warn_msg="[WARNING] run_apple failed, continuing with other jobs..."
      {
        echo "$warn_msg"
      } >> "$LOG_FILE" 2>&1
      if [[ ${LOG_TO_TERMINAL:-0} -eq 1 ]]; then
        echo "$warn_msg" >&2
      fi
    fi

    if ! run_nvidia; then
      FAILED=1
      warn_msg="[WARNING] run_nvidia failed, continuing with other jobs..."
      {
        echo "$warn_msg"
      } >> "$LOG_FILE" 2>&1
      if [[ ${LOG_TO_TERMINAL:-0} -eq 1 ]]; then
        echo "$warn_msg" >&2
      fi
    fi

    if ! run_microsoft; then
      FAILED=1
      warn_msg="[WARNING] run_microsoft failed, continuing with other jobs..."
      {
        echo "$warn_msg"
      } >> "$LOG_FILE" 2>&1
      if [[ ${LOG_TO_TERMINAL:-0} -eq 1 ]]; then
        echo "$warn_msg" >&2
      fi
    fi

    if ! run_tiktok; then
      FAILED=1
      warn_msg="[WARNING] run_tiktok failed, continuing with other jobs..."
      {
        echo "$warn_msg"
      } >> "$LOG_FILE" 2>&1
      if [[ ${LOG_TO_TERMINAL:-0} -eq 1 ]]; then
        echo "$warn_msg" >&2
      fi
    fi

    if ! run_cursor; then
      FAILED=1
      warn_msg="[WARNING] run_cursor failed, continuing with other jobs..."
      {
        echo "$warn_msg"
      } >> "$LOG_FILE" 2>&1
      if [[ ${LOG_TO_TERMINAL:-0} -eq 1 ]]; then
        echo "$warn_msg" >&2
      fi
    fi

    if ! run_tesla; then
      FAILED=1
      warn_msg="[WARNING] run_tesla failed, continuing with other jobs..."
      {
        echo "$warn_msg"
      } >> "$LOG_FILE" 2>&1
      if [[ ${LOG_TO_TERMINAL:-0} -eq 1 ]]; then
        echo "$warn_msg" >&2
      fi
    fi

    if ! run_mercor; then
      FAILED=1
      warn_msg="[WARNING] run_mercor failed, continuing with other jobs..."
      {
        echo "$warn_msg"
      } >> "$LOG_FILE" 2>&1
      if [[ ${LOG_TO_TERMINAL:-0} -eq 1 ]]; then
        echo "$warn_msg" >&2
      fi
    fi

    if ! run_smartrecruiters; then
      FAILED=1
      warn_msg="[WARNING] run_smartrecruiters failed, continuing with other jobs..."
      {
        echo "$warn_msg"
      } >> "$LOG_FILE" 2>&1
      if [[ ${LOG_TO_TERMINAL:-0} -eq 1 ]]; then
        echo "$warn_msg" >&2
      fi
    fi

    if ! run_join; then
      FAILED=1
      warn_msg="[WARNING] run_join failed, continuing with other jobs..."
      {
        echo "$warn_msg"
      } >> "$LOG_FILE" 2>&1
      if [[ ${LOG_TO_TERMINAL:-0} -eq 1 ]]; then
        echo "$warn_msg" >&2
      fi
    fi

    if ! run_rippling; then
      FAILED=1
      warn_msg="[WARNING] run_rippling failed, continuing with other jobs..."
      {
        echo "$warn_msg"
      } >> "$LOG_FILE" 2>&1
      if [[ ${LOG_TO_TERMINAL:-0} -eq 1 ]]; then
        echo "$warn_msg" >&2
      fi
    fi

    if ! run_personio; then
      FAILED=1
      warn_msg="[WARNING] run_personio failed, continuing with other jobs..."
      {
        echo "$warn_msg"
      } >> "$LOG_FILE" 2>&1
      if [[ ${LOG_TO_TERMINAL:-0} -eq 1 ]]; then
        echo "$warn_msg" >&2
      fi
    fi

    if ! run_ai; then
      FAILED=1
      warn_msg="[WARNING] run_ai failed, continuing with other jobs..."
      {
        echo "$warn_msg"
      } >> "$LOG_FILE" 2>&1
      if [[ ${LOG_TO_TERMINAL:-0} -eq 1 ]]; then
        echo "$warn_msg" >&2
      fi
    fi

    if ! run_fetch_job; then
      FAILED=1
      warn_msg="[WARNING] run_fetch_job failed"
      {
        echo "$warn_msg"
      } >> "$LOG_FILE" 2>&1
      if [[ ${LOG_TO_TERMINAL:-0} -eq 1 ]]; then
        echo "$warn_msg" >&2
      fi
    fi
    ;;
  *)
    {
      echo "[ERROR] Invalid job: $JOB"
      echo "[ERROR] Usage: $0 {ashby|greenhouse|lever|workable|workday|avature|google|amazon|meta|apple|nvidia|microsoft|tiktok|cursor|tesla|mercor|smartrecruiters|join|rippling|personio|ai|fetch_job|all}"
    } >> "$LOG_FILE" 2>&1
    exit 1
    ;;
esac

# Re-enable exit on error
set -e

# Log completion status
if [[ $FAILED -eq 0 ]]; then
  completion_msg="[pipeline] ✅ Pipeline completed successfully at $(date)"
  {
    echo "$completion_msg"
    echo "=== Pipeline run finished ==="
    echo
  } >> "$LOG_FILE" 2>&1
  if [[ ${LOG_TO_TERMINAL:-0} -eq 1 ]]; then
    echo "$completion_msg"
    echo "=== Pipeline run finished ==="
  fi
else
  completion_msg="[pipeline] ❌ Pipeline completed with errors at $(date)"
  {
    echo "$completion_msg"
    echo "=== Pipeline run finished ==="
    echo
  } >> "$LOG_FILE" 2>&1
  if [[ ${LOG_TO_TERMINAL:-0} -eq 1 ]]; then
    echo "$completion_msg" >&2
    echo "=== Pipeline run finished ===" >&2
  fi
fi

# Exit with appropriate code
if [[ $FAILED -eq 1 ]]; then
  exit 1
fi
