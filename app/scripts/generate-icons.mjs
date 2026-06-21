import { deflateSync } from 'node:zlib'
import { mkdirSync, writeFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = dirname(fileURLToPath(import.meta.url))
const buildDir = join(__dirname, '..', 'build')
mkdirSync(buildDir, { recursive: true })

const sizes = [256, 128, 64, 48, 32, 16]

function crc32(buf) {
  let crc = 0xffffffff
  for (const byte of buf) {
    crc ^= byte
    for (let i = 0; i < 8; i += 1) {
      crc = (crc >>> 1) ^ (0xedb88320 & -(crc & 1))
    }
  }
  return (crc ^ 0xffffffff) >>> 0
}

function chunk(type, data) {
  const typeBuf = Buffer.from(type)
  const len = Buffer.alloc(4)
  len.writeUInt32BE(data.length)
  const crc = Buffer.alloc(4)
  crc.writeUInt32BE(crc32(Buffer.concat([typeBuf, data])))
  return Buffer.concat([len, typeBuf, data, crc])
}

function setPixel(data, width, x, y, r, g, b, a = 255) {
  if (x < 0 || y < 0 || x >= width || y >= width) return
  const i = (y * width + x) * 4
  data[i] = r
  data[i + 1] = g
  data[i + 2] = b
  data[i + 3] = a
}

function blendPixel(data, width, x, y, r, g, b, a) {
  if (x < 0 || y < 0 || x >= width || y >= width) return
  const i = (y * width + x) * 4
  const src = a / 255
  const dst = data[i + 3] / 255
  const out = src + dst * (1 - src)
  if (out <= 0) return
  data[i] = Math.round((r * src + data[i] * dst * (1 - src)) / out)
  data[i + 1] = Math.round((g * src + data[i + 1] * dst * (1 - src)) / out)
  data[i + 2] = Math.round((b * src + data[i + 2] * dst * (1 - src)) / out)
  data[i + 3] = Math.round(out * 255)
}

function drawRing(data, width, radius, thickness, alpha) {
  const center = (width - 1) / 2
  for (let y = 0; y < width; y += 1) {
    for (let x = 0; x < width; x += 1) {
      const dx = x - center
      const dy = y - center
      const d = Math.hypot(dx, dy)
      const edge = Math.abs(d - radius)
      if (edge <= thickness) {
        const fade = 1 - edge / thickness
        blendPixel(data, width, x, y, 0, 229, 255, Math.round(alpha * fade))
      }
    }
  }
}

function makePng(width) {
  const data = Buffer.alloc(width * width * 4)
  const center = (width - 1) / 2
  const maxDistance = Math.hypot(center, center)

  for (let y = 0; y < width; y += 1) {
    for (let x = 0; x < width; x += 1) {
      const d = Math.hypot(x - center, y - center) / maxDistance
      const shade = Math.max(0, 1 - d)
      setPixel(data, width, x, y, 3 + shade * 8, 8 + shade * 16, 14 + shade * 28, 255)
    }
  }

  drawRing(data, width, width * 0.42, Math.max(1.5, width * 0.012), 135)
  drawRing(data, width, width * 0.34, Math.max(1.25, width * 0.01), 170)
  drawRing(data, width, width * 0.25, Math.max(1, width * 0.008), 210)

  for (let y = 0; y < width; y += 1) {
    for (let x = 0; x < width; x += 1) {
      const dx = x - center
      const dy = y - center
      const dist = Math.hypot(dx, dy)
      if (dist < width * 0.145) {
        const glow = 1 - dist / (width * 0.145)
        blendPixel(data, width, x, y, 0, 229, 255, Math.round(185 * glow))
      }
    }
  }

  const bar = Math.max(2, Math.round(width * 0.06))
  const left = Math.round(width * 0.43)
  const right = Math.round(width * 0.57)
  const top = Math.round(width * 0.31)
  const bottom = Math.round(width * 0.62)
  for (let y = top; y < bottom; y += 1) {
    for (let x = left; x < right; x += 1) {
      if (x < left + bar || y > bottom - bar || (x > right - bar && y > bottom - width * 0.16)) {
        setPixel(data, width, x, y, 220, 250, 255, 255)
      }
    }
  }

  const raw = Buffer.alloc((width * 4 + 1) * width)
  for (let y = 0; y < width; y += 1) {
    raw[y * (width * 4 + 1)] = 0
    data.copy(raw, y * (width * 4 + 1) + 1, y * width * 4, (y + 1) * width * 4)
  }

  const signature = Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a])
  const ihdr = Buffer.alloc(13)
  ihdr.writeUInt32BE(width, 0)
  ihdr.writeUInt32BE(width, 4)
  ihdr[8] = 8
  ihdr[9] = 6
  ihdr[10] = 0
  ihdr[11] = 0
  ihdr[12] = 0

  return Buffer.concat([
    signature,
    chunk('IHDR', ihdr),
    chunk('IDAT', deflateSync(raw, { level: 9 })),
    chunk('IEND', Buffer.alloc(0))
  ])
}

function makeIco(pngs) {
  const header = Buffer.alloc(6)
  header.writeUInt16LE(0, 0)
  header.writeUInt16LE(1, 2)
  header.writeUInt16LE(pngs.length, 4)

  const entries = []
  let offset = 6 + pngs.length * 16
  for (const { size, png } of pngs) {
    const entry = Buffer.alloc(16)
    entry[0] = size === 256 ? 0 : size
    entry[1] = size === 256 ? 0 : size
    entry[2] = 0
    entry[3] = 0
    entry.writeUInt16LE(1, 4)
    entry.writeUInt16LE(32, 6)
    entry.writeUInt32LE(png.length, 8)
    entry.writeUInt32LE(offset, 12)
    offset += png.length
    entries.push(entry)
  }

  return Buffer.concat([header, ...entries, ...pngs.map(({ png }) => png)])
}

const pngs = sizes.map(size => ({ size, png: makePng(size) }))
writeFileSync(join(buildDir, 'icon.png'), pngs[0].png)
writeFileSync(join(buildDir, 'icon.ico'), makeIco(pngs))
console.log('Generated build/icon.png and build/icon.ico')
