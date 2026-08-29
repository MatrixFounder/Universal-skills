# Shared bash helper for visual regression checks in per-skill E2E suites.
#
# Usage from skills/<skill>/scripts/tests/test_e2e.sh:
#
#   ROOT="$(cd "$SKILL_DIR/../../.." && pwd -P)"     # repo root (physical!)
#   SKILL=docx                                       # or pptx/xlsx/pdf
#   source "$ROOT/tests/visual/_visual_helper.sh"
#   visual_check "$TMP/out.pdf" "fixture-base"       # PDF path → golden name
#
# Conventions:
# - Goldens live at $ROOT/tests/visual/goldens/$SKILL/$NAME.png
# - The comparator script soft-skips when the golden or ImageMagick is
#   missing UNLESS STRICT_VISUAL=1 (set by CI). That keeps `bash
#   test_e2e.sh` green on a fresh local checkout while still failing
#   loudly in CI on real visual drift.
# - Caller must set ROOT, SKILL, PY, ok, nok before sourcing. ROOT must be
#   PHYSICALLY resolved (pwd -P): skills are installed as symlinks
#   (~/.claude/skills/<skill> -> repo), and a logical pwd makes
#   "$SKILL_DIR/../../.." escape the repository entirely.

visual_check() {
    # NOTE: this function MUST always `return 0`. Per-skill test_e2e.sh
    # runs under `set -euo pipefail`; any non-zero return as a standalone
    # command would abort the suite mid-stream — hiding all subsequent
    # checks AND the trailing "$pass passed, $fail failed" summary.
    # Failure is recorded via `nok` (increments $fail); the final
    # `[ "$fail" -eq 0 ]` at the end of each suite decides the exit code.
    local pdf="$1" name="$2"
    local golden="$ROOT/tests/visual/goldens/$SKILL/$name.png"
    local out rc _errexit
    # Restore the caller's errexit rather than forcing it on: html and
    # design-md deliberately run under `set -uo pipefail` with no -e.
    case $- in *e*) _errexit=1 ;; *) _errexit=0 ;; esac
    if [ ! -s "$pdf" ]; then
        nok "visual: $name" "PDF input missing or empty: $pdf"
        return 0
    fi
    set +e
    out=$("$PY" "$ROOT/tests/visual/visual_compare.py" \
              --pdf "$pdf" --golden "$golden" --page 1 --dpi 80 2>&1)
    rc=$?
    if [ "$_errexit" = 1 ]; then set -e; fi
    if [ "$rc" -eq 0 ]; then
        ok "visual: $name"
    else
        nok "visual: $name" "$out (exit $rc)"
    fi
    return 0
}
