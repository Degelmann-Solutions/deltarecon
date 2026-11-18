#!/usr/bin/env bash
# Renews the Linux captures of the page "Your own calculations on the
# reference model": runs the commands the present capture files name, in
# their order, and writes each step's file anew.
#
#   bash <docs>/scripts/capture-own-calculations.sh <source folder> <target folder>
#
# Run it in the package folder of the released package, unpacked into a fresh
# folder, after `./quickstart --lang en --no-pause`. The source folder is
# `src/captures/v<version>/own-calculations/` (absolute); the target folder
# must not exist. `order.txt` of the source folder names the steps in the
# order they run; `<step>-linux.txt` holds, per command, the line
# `command: <as typed>`, its output (standard output and standard error),
# and the line `exit status: <n>`. Only the `command:` lines are read.
# Every command runs in this shell, as a reader types it, so a variable of
# one step is there in the next.
set -u
if [ $# -ne 2 ] || [ ! -f "$1/order.txt" ]; then
  echo "usage: capture-own-calculations.sh <source folder with order.txt> <target folder>" >&2
  exit 2
fi
capture_source=$1
capture_target=$2
mkdir "$capture_target" || exit 2

while IFS= read -r capture_step <&3; do
  [ -n "$capture_step" ] || continue
  capture_file="$capture_target/$capture_step-linux.txt"
  while IFS= read -r capture_line <&4; do
    case $capture_line in
      'command: '*) ;;
      *) continue ;;
    esac
    capture_command=${capture_line#command: }
    printf 'command: %s\n' "$capture_command" >>"$capture_file"
    eval "$capture_command" >>"$capture_file" 2>&1 </dev/null
    printf 'exit status: %s\n' "$?" >>"$capture_file"
  done 4<"$capture_source/$capture_step-linux.txt"
  echo "capture-own-calculations: $capture_step written"
done 3<"$capture_source/order.txt"
