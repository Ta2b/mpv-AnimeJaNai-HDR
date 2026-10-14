#!/bin/bash
# Runs a command. When it fails, its last lines become an error annotation: they can then be
# read on the run's summary page, without opening the log.
#
# usage: run.sh TITLE COMMAND...
title="$1"; shift
log="$(mktemp)"
"$@" 2>&1 | tee "$log"
code="${PIPESTATUS[0]}"
if [ "$code" -ne 0 ]; then
    body="$(tail -n 25 "$log" | cut -c1-300 | sed -e 's/%/%25/g' | awk '{printf "%s%%0A", $0}')"
    echo "::error title=$title failed::${body:-no output}"
fi
exit "$code"
