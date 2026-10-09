// INVARIANT: only an explicit success for the still-current, non-aborted
// conversation while compositor secure may release the session lock.
function mayUnlock(active, aborting, secure, result, success) {
    return active === true && aborting === false && secure === true
        && result === success;
}
