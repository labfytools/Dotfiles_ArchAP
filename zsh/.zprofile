if uwsm check may-start && uwsm select; then
    exec uwsm start default
fi

# Keep user-local launchers available before the interactive shell starts.
export PATH="$HOME/.local/bin:$PATH"
