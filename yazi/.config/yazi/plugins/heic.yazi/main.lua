local M = {}

function M:peek(job)
    local cache = ya.file_cache {
        file = job.file,
        skip = 0,
    }
    if not cache then
        return
    end

    local out = tostring(cache) .. ".jpg"

    if not fs.cha(Url(out)) then
        local child = Command("magick")
            :arg(tostring(job.file.url))
            :arg(out)
            :spawn()

        if not child then
            return
        end

        child:wait()
    end

    ya.image_show(Url(out), job.area)
end

function M:seek() end

return M
