# Helpers for check.sh. Source it; do not run it.
#
#   gate <name> <expected-exit> <command...>   run a command, compare its exit status
#   same <name> <file-a> <file-b>              byte-identical and non-empty
#   build_gates <project-dir>                  dependency, test and build gates
#   gates_done                                 print the summary and exit with the result
#
# A gate's stdout lands in $gate_out for the next line to inspect.

# the compiler: `mach` on the PATH, or $MACH to point at a particular one
mach="${MACH:-mach}"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
gate_out="$work/gate.out"
fails=0

gate() {
    local name="$1" want="$2"; shift 2
    "$@" >"$gate_out" 2>"$work/gate.err"
    local got=$?
    if [[ "$got" == "$want" ]]; then
        printf '  ok    %s\n' "$name"
    else
        printf '  FAIL  %s (exit %s, expected %s)\n' "$name" "$got" "$want"
        sed 's/^/        /' "$work/gate.err" | head -5
        fails=$((fails + 1))
    fi
}

# two empty files are a failure, not a match
same() {
    if [[ -s "$2" && -s "$3" ]] && cmp -s "$2" "$3"; then
        printf '  ok    %s\n' "$1"
    else
        printf '  FAIL  %s\n' "$1"
        fails=$((fails + 1))
    fi
}

# the gates every run starts with; stops the run if any fails, since
# nothing after them can be meaningful without both binaries
build_gates() {
    local project="$1"
    gate "dependencies match their pinned commits" 0 "$mach" dep verify "$project" --quiet
    gate "unit tests" 0 "$mach" test "$project" --quiet
    gate "debug build" 0 "$mach" build "$project" --quiet
    gate "release build" 0 "$mach" build "$project" --profile release --quiet
    if [[ "$fails" -gt 0 ]]; then
        echo "  $fails gate(s) failed; runtime gates skipped"
        exit 1
    fi
}

gates_done() {
    if [[ "$fails" -gt 0 ]]; then
        echo "  $fails gate(s) failed"
        exit 1
    fi
    echo "  all gates passed"
}
