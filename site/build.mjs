import { copyFileSync, existsSync, mkdirSync, readdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const dataDir = resolve(process.argv[2] ?? root)
const dist = join(root, 'dist')
const config = JSON.parse(readFileSync(join(root, 'site', 'config.json'), 'utf8'))

const JUDGES = [
  ['claude', 'Claude', 'anthropic.com'],
  ['gpt', 'GPT', 'openai.com'],
  ['gemini', 'Gemini', 'gemini.google.com'],
  ['muse', 'Muse', 'meta.ai'],
]
const MEASUREMENTS = [
  ['mobile_speed', 'Mobile speed', 'Lighthouse'],
  ['desktop_speed', 'Desktop speed', 'Lighthouse'],
  ['accessibility', 'Accessibility', 'Lighthouse'],
  ['seo', 'SEO', 'Lighthouse'],
  ['agent_readiness', 'Agent readiness', 'Ora'],
]
const GRADES = [
  [9.5, 'A+', 'Exceptional', 'g-aplus'],
  [8.5, 'A', 'Excellent', 'g-a'],
  [7, 'B', 'Good', 'g-b'],
  [5.5, 'C', 'Average', 'g-c'],
  [4, 'D', 'Weak', 'g-d'],
  [0, 'F', 'Poor', 'g-f'],
]
const MEDALS = ['gold', 'silver', 'bronze']
const DOMAIN = /^[a-z0-9-]+(\.[a-z0-9-]+)+$/

const esc = (value) =>
  String(value ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c])
const isInt = (value, low, high) => Number.isInteger(value) && value >= low && value <= high
const grade = (value) => GRADES.find(([min]) => value >= min)
const absolute = (path) => (config.site_url ? config.site_url.replace(/\/$/, '') + path : path)
const favicon = (domain) => `https://www.google.com/s2/favicons?domain=${encodeURIComponent(domain)}&sz=64`
const fullDate = (iso) =>
  iso ? new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric', timeZone: 'UTC' }) : ''

function loadSites() {
  const dir = join(dataDir, 'results')
  const sites = []
  const pending = []
  for (const file of existsSync(dir) ? readdirSync(dir).filter((name) => name.endsWith('.json')).sort() : []) {
    try {
      const site = JSON.parse(readFileSync(join(dir, file), 'utf8'))
      if (!DOMAIN.test(site.domain ?? '') || `${site.domain}.json` !== file) throw new Error('domain does not match file name')
      if (site.status === 'scoring') {
        if (Date.parse(site.queued_at) > Date.now() - 20 * 60 * 1000) pending.push(site)
        continue
      }
      const judged = JUDGES.every(([key]) => isInt(site.judges?.[key]?.score, 1, 10) && site.judges[key].roast)
      const measured = MEASUREMENTS.every(([key]) => site[key] === null || isInt(site[key], 0, 100))
      if (typeof site.score !== 'number' || !judged || !measured) {
        throw new Error('missing scores')
      }
      const values = MEASUREMENTS.map(([key]) => site[key]).filter((value) => value !== null)
      site.measured = values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : 0
      site.harshest = JUDGES.reduce((low, judge) => (site.judges[judge[0]].score < site.judges[low[0]].score ? judge : low))
      site.hasShot = existsSync(join(dataDir, 'shots', `${site.domain}.jpg`))
      site.hasCard = existsSync(join(dataDir, 'cards', `${site.domain}.jpg`))
      sites.push(site)
    } catch (error) {
      console.warn(`skipping ${file}: ${error.message}`)
    }
  }
  sites.sort((a, b) => b.score - a.score || b.measured - a.measured || a.domain.localeCompare(b.domain))
  sites.forEach((site, index) => {
    site.rank = index + 1
  })
  return { sites, pending }
}

function nav(up) {
  const repo = config.repo_url
    ? `<a href="${esc(config.repo_url)}/blob/main/RUBRIC.md">Methodology</a><a href="${esc(config.repo_url)}">GitHub</a>`
    : ''
  return `<header class="nav"><div class="wrap">
<div class="logo"><a class="home" href="${up}"><span class="mark">${esc(config.title[0])}</span>${esc(config.title)}</a><span class="by">built on <a href="https://www.omnara.com">Omnara</a></span></div>
<nav>${repo}</nav>
</div></header>`
}

function page({ title, description, path, image, depth, body, refresh, backdrop }) {
  const up = depth ? '../'.repeat(depth) : './'
  return `<!doctype html>
<html lang="en"${['light', 'dark'].includes(config.theme) ? ` class="${config.theme}"` : ''}>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="dark">
${refresh ? '<meta http-equiv="refresh" content="30">' : ''}
<title>${esc(title)}</title>
<meta name="description" content="${esc(description)}">
<meta property="og:title" content="${esc(title)}">
<meta property="og:description" content="${esc(description)}">
<meta property="og:url" content="${esc(absolute(path))}">
${image ? `<meta property="og:image" content="${esc(absolute(image))}">` : ''}
<meta name="twitter:card" content="${image ? 'summary_large_image' : 'summary'}">
${config.x_handle ? `<meta name="twitter:creator" content="@${esc(config.x_handle)}">` : ''}
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Geist:wght@400;500;600;700&family=Geist+Mono:wght@400;500&display=swap">
<link rel="icon" href="${up}favicon.svg" type="image/svg+xml">
<link rel="stylesheet" href="${up}style.css">
</head>
<body>
${nav(up)}
${backdrop ?? ''}
<main class="wrap">
${body}
</main>
<footer><div class="wrap">A side project by <a href="https://x.com/${esc(config.x_handle)}">@${esc(config.x_handle)}</a>. Scored by AI agents running on <a href="https://www.omnara.com">Omnara</a>, with <a href="https://developer.chrome.com/docs/lighthouse">Lighthouse</a> and <a href="https://ora.ai">Ora</a>.</div></footer>
${backdrop ? `<script type="module">
import { ShaderMount, neuroNoiseFragmentShader, getShaderColorFromString as color } from './shader.js'
const still = matchMedia('(prefers-reduced-motion: reduce)').matches
new ShaderMount(document.querySelector('.backdrop .shader'), neuroNoiseFragmentShader, {
  u_colorFront: color('#c6f432'),
  u_colorMid: color('#1f6f5c'),
  u_colorBack: color('#0a0f1a'),
  u_brightness: 0.02,
  u_contrast: 0.35,
  u_fit: 0,
  u_scale: 1.2,
  u_rotation: 0,
  u_originX: 0.5,
  u_originY: 0.5,
  u_offsetX: 0,
  u_offsetY: 0,
  u_worldWidth: 0,
  u_worldHeight: 0,
}, undefined, still ? 0 : 0.6, 0, 1)
</script>
` : ''}</body>
</html>
`
}

function gradeBadge(value) {
  const [, letter, , cls] = grade(value)
  return `<span class="grade ${cls}">${letter}</span>`
}

function ring(value, size) {
  const r = 52
  const c = 2 * Math.PI * r
  const cls = grade(value)[3]
  return `<div class="ring ${cls}" style="width:${size}px;height:${size}px">
<svg viewBox="0 0 120 120"><circle cx="60" cy="60" r="${r}" class="track"/><circle cx="60" cy="60" r="${r}" class="fill" stroke-dasharray="${((value / 10) * c).toFixed(1)} ${c.toFixed(1)}"/></svg>
<span>${value.toFixed(1)}</span>
</div>`
}

const roastLine = (site) => `${site.harshest[1]}: “${site.judges[site.harshest[0]].roast}”`

const postUrl = () => config.x_post_url || (config.x_handle ? `https://x.com/${config.x_handle}` : '')
const byNewest = (sites) => [...sites].sort((a, b) => String(b.audited_at).localeCompare(String(a.audited_at)))
const ago = (iso) => (iso ? `<time datetime="${esc(iso)}" data-ago>${fullDate(iso)}</time>` : '')

function live(sites, pending) {
  if (pending.length) {
    const names = pending
      .slice(0, 6)
      .map((site) => `<a class="chip" href="${esc(site.domain)}/"><img src="${favicon(site.domain)}" alt="" width="14" height="14">${esc(site.domain)}</a>`)
      .join('')
    const more = pending.length > 6 ? `<span class="chip">+${pending.length - 6} more</span>` : ''
    return `<div class="live"><span class="spinner"></span><b>Scoring now</b>${names}${more}</div>`
  }
  const recent = byNewest(sites)
    .slice(0, 3)
    .map((site) => `<a class="chip" href="${esc(site.domain)}/"><img src="${favicon(site.domain)}" alt="" width="14" height="14">${esc(site.domain)}${ago(site.audited_at)}</a>`)
    .join('')
  return recent ? `<div class="live"><span class="pulse"></span>Last rated${recent}</div>` : ''
}

function backdrop() {
  return '<div class="backdrop" aria-hidden="true"><div class="shader"></div></div>'
}

function indexPage(sites, pending) {
  const rows = sites
    .map(
      (site) => `<tr data-domain="${esc(site.domain)}" onclick="location.href='${esc(site.domain)}/'">
<td class="rank" data-value="${site.rank}">${site.rank <= 3 ? `<span class="medal ${MEDALS[site.rank - 1]}">${site.rank}</span>` : site.rank}</td>
<td class="site"><div><img src="${favicon(site.domain)}" alt="" width="24" height="24" loading="lazy"><div><a href="${esc(site.domain)}/">${esc(site.domain)}</a><span>${esc(roastLine(site))}</span></div></div></td>
<td class="total ${grade(site.score)[3]}" data-value="${site.score}"><span class="num">${site.score.toFixed(1)}</span>${gradeBadge(site.score)}</td>
${JUDGES.map(([key]) => site.judges[key].score).map((value) => `<td class="cat ${grade(value)[3]}" data-value="${value}"><span>${value}</span><i style="--w:${value * 10}%"></i></td>`).join('\n')}
</tr>`,
    )
    .join('\n')
  const cta = postUrl() ? `<div class="actions"><a class="btn primary" href="${esc(postUrl())}">Get your site ranked</a></div>` : ''
  const body = `<section class="hero">
<h1>${esc(config.headline)}</h1>
<p class="lede">${esc(config.tagline)}</p>
${cta}
${live(sites, pending)}
</section>
${
  sites.length
    ? `<section id="board">
<div class="section-head"><h2>Leaderboard</h2><input id="find" type="search" placeholder="Find a site" aria-label="Find a site" autocomplete="off"></div>
<div class="board"><table>
<thead><tr><th data-col="0">#</th><th>Website</th><th data-col="2" class="sorted">Score</th>${JUDGES.map(([, name, lab], i) => `<th data-col="${i + 3}"><img src="${favicon(lab)}" alt="" width="14" height="14">${name}</th>`).join('')}</tr></thead>
<tbody>
${rows}
</tbody>
</table>
<p class="board-empty" hidden>That site isn't ranked yet.${postUrl() ? ` <a href="${esc(postUrl())}">Reply with your domain</a> to get it scored.` : ''}</p>
</div>
</section>`
    : '<p class="empty">No sites ranked yet.</p>'
}
<script>
document.querySelectorAll('time[data-ago]').forEach((el) => {
  const mins = Math.max(0, Math.round((Date.now() - new Date(el.dateTime)) / 60000))
  el.textContent = mins < 1 ? 'just now' : mins < 60 ? mins + ' min ago' : mins < 1440 ? Math.round(mins / 60) + ' h ago' : Math.round(mins / 1440) + ' d ago'
})
const table = document.querySelector('#board table')
if (table) {
  const body = table.tBodies[0]
  let last = 2
  let dir = -1
  table.querySelectorAll('th[data-col]').forEach((th) => {
    th.addEventListener('click', () => {
      const col = Number(th.dataset.col)
      dir = last === col ? -dir : col === 0 ? 1 : -1
      last = col
      table.querySelectorAll('th').forEach((h) => h.classList.toggle('sorted', h === th))
      ;[...body.rows]
        .sort((a, b) => (Number(a.cells[col].dataset.value) - Number(b.cells[col].dataset.value)) * dir)
        .forEach((row) => body.appendChild(row))
    })
  })
  const find = document.querySelector('#find')
  find.addEventListener('input', () => {
    const query = find.value.trim().toLowerCase()
    let shown = 0
    for (const row of body.rows) {
      row.hidden = !row.dataset.domain.includes(query)
      if (!row.hidden) shown++
    }
    table.hidden = shown === 0
    document.querySelector('.board-empty').hidden = shown > 0
  })
}
</script>`
  return page({
    title: config.title,
    description: config.tagline,
    path: '/',
    depth: 0,
    body,
    refresh: pending.length > 0,
    backdrop: backdrop(),
  })
}

function pendingPage(site) {
  const body = `<p class="back"><a href="../#board">← Leaderboard</a></p>
<section class="pending">
<span class="spinner big"></span>
<div class="site-id"><img src="${favicon(site.domain)}" alt="" width="40" height="40"><div><h1>${esc(site.domain)}</h1></div></div>
<p class="pending-text">AI agents are scoring this site right now. It usually takes about two minutes, and this page refreshes on its own.</p>
</section>`
  return page({
    title: `${site.domain} · ${config.title}`,
    description: `AI agents are scoring ${site.domain} right now.`,
    path: `/${site.domain}/`,
    depth: 1,
    body,
    refresh: true,
  })
}

function sitePage(site, total) {
  const [, , label] = grade(site.score)
  const judges = JUDGES.map(([key, name, lab]) => {
    const judge = site.judges[key]
    return `<div class="judge ${grade(judge.score)[3]}">
<div class="judge-head"><img src="${favicon(lab)}" alt="" width="20" height="20"><b>${name}</b><span class="judge-score">${judge.score}<small>/10</small></span></div>
<p>“${esc(judge.roast)}”</p>
</div>`
  }).join('\n')
  const facts = MEASUREMENTS.map(([key, name, source]) => [name, source, site[key], key === 'agent_readiness' ? site.agent_readiness_summary : ''])
    .map(
      ([name, source, value, note]) => `<div class="row">
<div class="row-name">${name}<small>${source}</small></div>
<div class="row-bar ${value === null ? '' : grade(value / 10)[3]}"><i style="--w:${value ?? 0}%"></i></div>
<div class="row-value">${value === null ? 'n/a' : (value / 10).toFixed(1)}</div>
${note ? `<p class="row-note">${esc(note)}</p>` : ''}
</div>`,
    )
    .join('\n')
  const receipt = [
    Number.isInteger(site.minutes) ? `Scored in ${site.minutes} min on its own machine` : '',
    site.blocks_automated_browsers ? 'screenshots from Lighthouse because the site blocks automated browsers' : '',
  ]
    .filter(Boolean)
    .join(' · ')
  const image = site.hasCard ? `/cards/${site.domain}.jpg` : site.hasShot ? `/shots/${site.domain}.jpg` : null
  const body = `<p class="back"><a href="../#board">← Leaderboard</a></p>
<header class="report-head">
<div class="site-id"><img src="${favicon(site.domain)}" alt="" width="40" height="40"><div><h1>${esc(site.domain)}</h1><p>Judged ${fullDate(site.audited_at)}</p></div></div>
<a class="btn" href="https://${esc(site.domain)}" rel="nofollow noopener">Visit site ↗</a>
</header>
<section class="summary">
${ring(site.score, 168)}
<div class="summary-text">
<div class="summary-grade">${gradeBadge(site.score)}<span>${label}</span><span class="dot">·</span><span>Rank <b>#${site.rank}</b> of ${total}</span></div>
<p class="verdict">The average of four AI judges, each from a different lab.</p>
</div>
</section>
<section class="judges">${judges}</section>
<section class="split">
<div class="panel"><h2>By the numbers</h2><div class="rows">${facts}</div></div>
${site.hasShot ? `<div class="panel shot"><h2>Homepage</h2><img src="../shots/${esc(site.domain)}.jpg" alt="${esc(site.domain)} homepage"></div>` : ''}
</section>
<p class="receipt">${receipt}</p>`
  return page({
    title: `${site.domain}: ${site.score.toFixed(1)}/10 · ${config.title}`,
    description: roastLine(site),
    path: `/${site.domain}/`,
    image,
    depth: 1,
    body,
  })
}

const { sites, pending } = loadSites()
rmSync(dist, { recursive: true, force: true })
mkdirSync(join(dist, 'shots'), { recursive: true })
mkdirSync(join(dist, 'cards'), { recursive: true })
for (const file of ['style.css', 'shader.js', 'favicon.svg']) copyFileSync(join(root, 'site', file), join(dist, file))
writeFileSync(join(dist, 'index.html'), indexPage(sites, pending))
for (const site of sites) {
  mkdirSync(join(dist, site.domain), { recursive: true })
  writeFileSync(join(dist, site.domain, 'index.html'), sitePage(site, sites.length))
  if (site.hasShot) copyFileSync(join(dataDir, 'shots', `${site.domain}.jpg`), join(dist, 'shots', `${site.domain}.jpg`))
  if (site.hasCard) copyFileSync(join(dataDir, 'cards', `${site.domain}.jpg`), join(dist, 'cards', `${site.domain}.jpg`))
}
for (const site of pending) {
  mkdirSync(join(dist, site.domain), { recursive: true })
  writeFileSync(join(dist, site.domain, 'index.html'), pendingPage(site))
}
console.log(`built ${sites.length} ranked and ${pending.length} scoring sites into dist/`)
