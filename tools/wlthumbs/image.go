package main

import (
	"image"
	"image/png"
	"os"

	"golang.org/x/image/draw"
)

// shmFormat is one 32-bit packed format we know how to read. wlroots advertises
// formats as DRM fourccs (plus the two historical wl_shm enum values 0/1 for
// ARGB/XRGB8888). swapRB is true when the memory byte order is B,G,R,x (so we
// must swap R and B to get RGBA); false when it is already R,G,B,x.
type shmFormat struct {
	value  uint32
	swapRB bool
}

// knownFormats is the preference order for capture buffers. We force opaque
// output, so alpha vs. no-alpha doesn't matter; any entry present is accepted.
var knownFormats = []shmFormat{
	{1, true},           // wl_shm XRGB8888   -> B,G,R,x
	{0, true},           // wl_shm ARGB8888   -> B,G,R,A
	{0x34325258, true},  // DRM XR24 XRGB8888 -> B,G,R,x
	{0x34325241, true},  // DRM AR24 ARGB8888 -> B,G,R,A
	{0x34324258, false}, // DRM XB24 XBGR8888 -> R,G,B,x
	{0x34324241, false}, // DRM AB24 ABGR8888 -> R,G,B,A
}

// chooseFormat picks the first format the compositor offered that we recognize.
func chooseFormat(offered []uint32) (value uint32, swapRB, ok bool) {
	for _, kf := range knownFormats {
		for _, v := range offered {
			if v == kf.value {
				return kf.value, kf.swapRB, true
			}
		}
	}
	return 0, false, false
}

// writeThumb converts raw pixels to RGBA, applies the output transform, scales
// to fit within `size`, and writes a PNG.
func writeThumb(raw []byte, w, h int, transform uint32, swapRB bool, size int, path string) error {
	img := toRGBA(raw, w, h, swapRB)
	img = applyTransform(img, transform)

	b := img.Bounds()
	sw, sh := b.Dx(), b.Dy()
	dw, dh := sw, sh
	if sw > size || sh > size {
		if sw >= sh {
			dw, dh = size, size*sh/sw
		} else {
			dw, dh = size*sw/sh, size
		}
	}
	dw, dh = max(dw, 1), max(dh, 1)

	dst := image.NewRGBA(image.Rect(0, 0, dw, dh))
	draw.BiLinear.Scale(dst, dst.Bounds(), img, b, draw.Src, nil)

	f, err := os.Create(path)
	if err != nil {
		return err
	}
	defer f.Close()
	enc := png.Encoder{CompressionLevel: png.BestSpeed}
	return enc.Encode(f, dst)
}

// toRGBA converts a packed 32-bit buffer into an opaque image.RGBA. If swapRB is
// set the source byte order is B,G,R,x; otherwise it is already R,G,B,x.
func toRGBA(raw []byte, w, h int, swapRB bool) *image.RGBA {
	img := image.NewRGBA(image.Rect(0, 0, w, h))
	dst := img.Pix
	for i := 0; i < w*h; i++ {
		j := i * 4
		if swapRB {
			dst[j+0], dst[j+1], dst[j+2] = raw[j+2], raw[j+1], raw[j+0]
		} else {
			dst[j+0], dst[j+1], dst[j+2] = raw[j+0], raw[j+1], raw[j+2]
		}
		dst[j+3] = 255 // force opaque
	}
	return img
}

// applyTransform re-orients pixels per the wl_output transform enum (0-7). It is
// a no-op for the common "normal" transform.
func applyTransform(src *image.RGBA, t uint32) *image.RGBA {
	if t == 0 {
		return src
	}
	b := src.Bounds()
	w, h := b.Dx(), b.Dy()
	dw, dh := w, h
	if t == 1 || t == 3 || t == 5 || t == 7 { // 90/270 rotations swap dimensions
		dw, dh = h, w
	}
	dst := image.NewRGBA(image.Rect(0, 0, dw, dh))
	for sy := 0; sy < h; sy++ {
		for sx := 0; sx < w; sx++ {
			var dx, dy int
			switch t {
			case 1: // 90
				dx, dy = sy, w-1-sx
			case 2: // 180
				dx, dy = w-1-sx, h-1-sy
			case 3: // 270
				dx, dy = h-1-sy, sx
			case 4: // flipped
				dx, dy = w-1-sx, sy
			case 5: // flipped-90
				dx, dy = sy, sx
			case 6: // flipped-180
				dx, dy = sx, h-1-sy
			case 7: // flipped-270
				dx, dy = h-1-sy, w-1-sx
			}
			si := src.PixOffset(sx, sy)
			di := dst.PixOffset(dx, dy)
			copy(dst.Pix[di:di+4], src.Pix[si:si+4])
		}
	}
	return dst
}
