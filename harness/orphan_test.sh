#!/usr/bin/env bash
# Does a generator killed mid-run leave its teacher engines running? Windows.
#
#   bash harness/orphan_test.sh <gen.exe> <book.epd> <engine.exe>
#
# Starts the generator with 4 workers, waits until its engines are up, kills
# the generator alone and counts how many of its engines are still alive five
# seconds later. Stockfish leaves none either way: it exits when its input
# closes. Reckless keeps running and spins a core, so with it this fails on a
# driver that does not start engines in a process group of their own
# (2026-10-11: 4 of 4 left by the old src/uci_driver.mach, 0 by the new).
# Exit status 0 if none is left.
set -u
gen="$1"; book="$2"; engine="$3"
work="$(mktemp -d)"
"$gen" "$(cygpath -m "$work")/orphan_test.bin" "$book" "$engine" 100000000 1500 4 4242 > "$work/log" 2>&1 &
sleep 12
left=$(powershell -NoProfile -Command "
  \$g = Get-CimInstance Win32_Process | Where-Object { \$_.CommandLine -match 'orphan_test\.bin' -and \$_.Name -match '^gen' } | Select-Object -First 1
  if (-not \$g) { 'generator not found'; exit }
  \$kids = @(Get-CimInstance Win32_Process -Filter \"ParentProcessId=\$(\$g.ProcessId)\" | Where-Object { \$_.Name -notmatch 'conhost' })
  Stop-Process -Id \$g.ProcessId -Force
  Start-Sleep 5
  \$left = @(\$kids | Where-Object { Get-Process -Id \$_.ProcessId -ErrorAction SilentlyContinue })
  \$left | ForEach-Object { Stop-Process -Id \$_.ProcessId -Force }
  '' + \$kids.Count + ' ' + \$left.Count")
rm -rf "$work"
echo "engines started and still running after the generator was killed: $left"
case "$left" in "4 0") exit 0 ;; *) exit 1 ;; esac
