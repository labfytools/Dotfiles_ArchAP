#!/usr/bin/env bash

title="$(mango-msg -t get_tree 2>/dev/null | jq -r '
  recurse(.nodes[]?, .floating_nodes[]?)
  | select(.focused == true)
  | .name // empty
' | head -n1)"

if [ -z "$title" ]; then
  title="Bureau"
fi

short="$(printf '%s' "$title" | cut -c1-60)"

jq -cn --arg text " $short" --arg tooltip "$title" \
  '{text:$text, tooltip:$tooltip}'
