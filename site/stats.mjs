import { existsSync, readdirSync, readFileSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const dir = join(resolve(process.argv[2] ?? root), 'results')
const keys = ['composite', 'speed', 'mobile', 'accessibility', 'seo', 'agent_readiness', 'clarity', 'design', 'copy']
const sites = (existsSync(dir) ? readdirSync(dir) : [])
  .filter((name) => name.endsWith('.json'))
  .map((name) => JSON.parse(readFileSync(join(dir, name), 'utf8')))
  .filter((site) => site.status === 'done')
const pick = (sorted, q) => sorted[Math.min(sorted.length - 1, Math.floor(q * sorted.length))]

console.log(`${sites.length} ranked sites\n`)
console.log('category'.padEnd(16), 'min  p25  med  p75  max  spread')
for (const key of keys) {
  const values = sites.map((site) => (key === 'composite' ? site.composite : site.scores[key])).sort((a, b) => a - b)
  if (!values.length) continue
  const mean = values.reduce((a, b) => a + b, 0) / values.length
  const spread = Math.round(Math.sqrt(values.reduce((a, b) => a + (b - mean) ** 2, 0) / values.length))
  const row = [values[0], pick(values, 0.25), pick(values, 0.5), pick(values, 0.75), values.at(-1)].map((v) => String(v).padStart(3))
  console.log(key.padEnd(16), row.join('  '), String(spread).padStart(6), spread < 8 ? ' flat: barely separates sites' : '')
}
