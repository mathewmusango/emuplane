// Copy the product's mark into the docs site, resized when ImageMagick is available.
const { spawnSync } = require('node:child_process')
const { copyFileSync, existsSync, mkdirSync, readFileSync, renameSync, unlinkSync } = require('node:fs')
const path = require('node:path')

const site = path.resolve(__dirname, '..')
const source = path.resolve(site, '../web/public/emuplane.png')
const target = path.resolve(site, 'static/img/mark.png')
const SIZE = '128x128'

const resizer = ['magick', 'convert'].find(
  (binary) => spawnSync(binary, ['-version'], { stdio: 'ignore' }).status === 0,
)

mkdirSync(path.dirname(target), { recursive: true })
const before = existsSync(target) ? readFileSync(target) : null

if (resizer) {
  const scratch = `${target}.tmp`
  const done = spawnSync(resizer, [source, '-resize', SIZE, '-strip', scratch], { stdio: 'inherit' })
  if (done.status !== 0) {
    console.error(`brand: ${resizer} could not resize ${source}`)
    process.exit(done.status || 1)
  }
  const after = readFileSync(scratch)
  if (before && after.equals(before)) {
    unlinkSync(scratch)
    console.log(`brand: ${path.relative(site, target)} is already current`)
  } else {
    renameSync(scratch, target)
    console.log(`brand: ${resizer} wrote ${path.relative(site, target)} at ${SIZE}`)
  }
} else if (before) {
  console.log(`brand: no ImageMagick, ${path.relative(site, target)} is already there`)
} else {
  copyFileSync(source, target)
  console.log(`brand: no ImageMagick, copied ${path.relative(site, target)} at full size`)
}
