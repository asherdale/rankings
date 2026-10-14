import { copyFileSync, existsSync, mkdirSync, readdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const dataDir = resolve(process.argv[2] ?? root)
const dist = join(root, 'dist')
const config = JSON.parse(readFileSync(join(root, 'site', 'config.json'), 'utf8'))
const rubric = JSON.parse(readFileSync(join(root, 'rubric.json'), 'utf8'))

const CATEGORIES = [
  ['speed', 'Speed', 'Speed'],
  ['mobile', 'Mobile', 'Mobile'],
  ['accessibility', 'Accessibility', 'Access.'],
  ['seo', 'SEO', 'SEO'],
  ['agent_readiness', 'Agent readiness', 'Agents'],
  ['clarity', 'Clarity', 'Clarity'],
  ['design', 'Design', 'Design'],
  ['copy', 'Copy', 'Copy'],
]
const GRADE_CLASS = { 'A+': 'g-aplus', A: 'g-a', B: 'g-b', C: 'g-c', D: 'g-d', F: 'g-f' }
const GRADES = rubric.grades.map(([min, letter, label]) => [min, letter, label, GRADE_CLASS[letter]])
const MEDALS = ['gold', 'silver', 'bronze']
const DOMAIN = /^[a-z0-9-]+(\.[a-z0-9-]+)+$/

const esc = (value) =>
  String(value ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c])
const isScore = (value) => Number.isInteger(value) && value >= 0 && value <= 100
const grade = (value) => GRADES.find(([min]) => value >= min)
const absolute = (path) => (config.site_url ? config.site_url.replace(/\/$/, '') + path : path)
const favicon = (domain) => `https://www.google.com/s2/favicons?domain=${encodeURIComponent(domain)}&sz=64`
const prettyModel = (slug) =>
  (String(slug).split('/').at(-1) ?? '')
    .split('-')
    .map((w) => (/^gpt$/i.test(w) ? 'GPT' : w[0].toUpperCase() + w.slice(1)))
    .join(' ')
    .replace('GPT ', 'GPT-')
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
        pending.push(site)
        continue
      }
      if (!isScore(site.composite) || !CATEGORIES.every(([key]) => isScore(site.scores?.[key]))) {
        throw new Error('missing scores')
      }
      site.hasShot = existsSync(join(dataDir, 'shots', `${site.domain}.jpg`))
      site.hasCard = existsSync(join(dataDir, 'cards', `${site.domain}.jpg`))
      sites.push(site)
    } catch (error) {
      console.warn(`skipping ${file}: ${error.message}`)
    }
  }
  sites.sort((a, b) => b.composite - a.composite || a.domain.localeCompare(b.domain))
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
<a class="logo" href="${up}"><span class="mark">${esc(config.title[0])}</span>${esc(config.title)}<span class="by">built on Omnara</span></a>
<nav><a href="${up}#board">Leaderboard</a>${repo}</nav>
</div></header>`
}

function page({ title, description, path, image, depth, body, refresh }) {
  const up = depth ? '../'.repeat(depth) : './'
  return `<!doctype html>
<html lang="en"${['light', 'dark'].includes(config.theme) ? ` class="${config.theme}"` : ''}>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light dark">
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
<link rel="stylesheet" href="${up}style.css">
</head>
<body>
${nav(up)}
<main class="wrap">
${body}
</main>
<footer><div class="wrap">A side project by <a href="https://x.com/${esc(config.x_handle)}">@${esc(config.x_handle)}</a>. Scored by AI agents running on <a href="https://www.omnara.com">Omnara</a>, with <a href="https://developer.chrome.com/docs/lighthouse">Lighthouse</a> and <a href="https://ora.ai">Ora</a>.</div></footer>
</body>
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
<svg viewBox="0 0 120 120"><circle cx="60" cy="60" r="${r}" class="track"/><circle cx="60" cy="60" r="${r}" class="fill" stroke-dasharray="${((value / 100) * c).toFixed(1)} ${c.toFixed(1)}"/></svg>
<span>${value}</span>
</div>`
}

function scoringBanner(pending, up) {
  if (!pending.length) return ''
  const names = pending
    .slice(0, 12)
    .map((site) => `<a href="${up}${esc(site.domain)}/"><img src="${favicon(site.domain)}" alt="" width="16" height="16">${esc(site.domain)}</a>`)
    .join('')
  const more = pending.length > 12 ? `<span>+${pending.length - 12} more</span>` : ''
  return `<section class="banner">
<div class="banner-head"><span class="spinner"></span><b>Scoring ${pending.length} site${pending.length === 1 ? '' : 's'} right now</b><span class="muted">This page refreshes every 30 seconds.</span></div>
<div class="banner-sites">${names}${more}</div>
</section>`
}

function indexPage(sites, pending) {
  const avg = sites.length ? Math.round(sites.reduce((sum, site) => sum + site.composite, 0) / sites.length) : 0
  const updated = sites.map((site) => site.audited_at).filter(Boolean).sort().at(-1)
  const rows = sites
    .map(
      (site) => `<tr onclick="location.href='${esc(site.domain)}/'">
<td class="rank" data-value="${site.rank}">${site.rank <= 3 ? `<span class="medal ${MEDALS[site.rank - 1]}">${site.rank}</span>` : site.rank}</td>
<td class="site"><div><img src="${favicon(site.domain)}" alt="" width="24" height="24" loading="lazy"><a href="${esc(site.domain)}/">${esc(site.domain)}</a></div></td>
<td class="total" data-value="${site.composite}"><span class="num">${site.composite}</span>${gradeBadge(site.composite)}</td>
${CATEGORIES.map(([key]) => `<td class="cat" data-value="${site.scores[key]}"><span>${site.scores[key]}</span><i style="--w:${site.scores[key]}%"></i></td>`).join('\n')}
</tr>`,
    )
    .join('\n')
  const goodShare = sites.length ? Math.round((100 * sites.filter((site) => site.composite >= 70).length) / sites.length) : 0
  const stats = sites.length
    ? `<section class="stats">
<div><span>Sites ranked</span><b>${sites.length}</b></div>
<div><span>Average score</span><b>${avg}</b></div>
<div><span>Graded B or better</span><b>${goodShare}%</b></div>
</section>`
    : ''
  const top = sites
    .slice(0, 3)
    .map(
      (site, i) => `<a class="top-row" href="${esc(site.domain)}/">
<span class="medal ${MEDALS[i]}">${i + 1}</span>
<img src="${favicon(site.domain)}" alt="" width="28" height="28">
<div class="top-name"><b>${esc(site.domain)}</b><span>${esc(site.roast)}</span></div>
${ring(site.composite, 64)}
</a>`,
    )
    .join('\n')
  const body = `<section class="hero">
<div class="hero-text">
${updated ? `<p class="eyebrow">Updated ${fullDate(updated)}</p>` : ''}
<h1>${esc(config.headline)}</h1>
<p class="lede">${esc(config.tagline)}</p>
<div class="actions">
${config.x_handle ? `<a class="btn primary" href="https://x.com/${esc(config.x_handle)}">Get your site ranked</a>` : ''}
<a class="btn" href="#board">See the leaderboard</a>
</div>
</div>
${top ? `<div class="top"><div class="top-head">Top of the board</div>${top}</div>` : ''}
</section>
${scoringBanner(pending, './')}
${stats}
${
  sites.length
    ? `<section id="board">
<div class="board-head"><h2>Leaderboard</h2></div>
<div class="board"><table>
<thead><tr><th data-col="0">#</th><th>Website</th><th data-col="2" class="sorted">Score</th>${CATEGORIES.map(([, name, short], i) => `<th data-col="${i + 3}" title="${esc(name)}">${esc(short)}</th>`).join('')}</tr></thead>
<tbody>
${rows}
</tbody>
</table></div>
</section>`
    : '<p class="empty">No sites ranked yet.</p>'
}
<script>
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
}
</script>`
  return page({
    title: `${config.title}: ${config.headline}`,
    description: config.tagline,
    path: '/',
    depth: 0,
    body,
    refresh: pending.length > 0,
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
    title: `${site.domain} is being scored`,
    description: `AI agents are scoring ${site.domain} right now.`,
    path: `/${site.domain}/`,
    depth: 1,
    body,
    refresh: true,
  })
}

function sitePage(site, total) {
  const [, letter, label, cls] = grade(site.composite)
  const rows = CATEGORIES.map(([key, name]) => {
    const value = site.scores[key]
    const note = site.notes?.[key]
    return `<div class="row">
<div class="row-name">${esc(name)}</div>
<div class="row-bar ${grade(value)[3]}"><i style="--w:${value}%"></i></div>
<div class="row-value">${value}</div>
${note ? `<p class="row-note">${esc(note)}</p>` : ''}
</div>`
  }).join('\n')
  const receipt = [
    Number.isInteger(site.minutes) ? `Scored in ${site.minutes} min on its own machine` : '',
    site.model ? `reviewed by ${esc(prettyModel(site.model))}` : '',
    site.blocks_automated_browsers ? 'screenshots from Lighthouse because the site blocks automated browsers' : '',
  ]
    .filter(Boolean)
    .join(' · ')
  const image = site.hasCard ? `/cards/${site.domain}.jpg` : site.hasShot ? `/shots/${site.domain}.jpg` : null
  const body = `<p class="back"><a href="../#board">← Leaderboard</a></p>
<header class="report-head">
<div class="site-id"><img src="${favicon(site.domain)}" alt="" width="40" height="40"><div><h1>${esc(site.domain)}</h1><p>Audited ${fullDate(site.audited_at)}</p></div></div>
<a class="btn" href="https://${esc(site.domain)}" rel="nofollow noopener">Visit site ↗</a>
</header>
<section class="summary">
${ring(site.composite, 168)}
<div class="summary-text">
<div class="summary-grade">${gradeBadge(site.composite)}<span>${label}</span><span class="dot">·</span><span>Rank <b>#${site.rank}</b> of ${total}</span></div>
${site.roast ? `<p class="verdict">“${esc(site.roast)}”</p>` : ''}
${site.fix ? `<p class="fix"><b>Fix this first</b>${esc(site.fix)}</p>` : ''}
</div>
</section>
<section class="split">
<div class="panel"><h2>Scores</h2><div class="rows">${rows}</div></div>
${site.hasShot ? `<div class="panel shot"><h2>Homepage</h2><img src="../shots/${esc(site.domain)}.jpg" alt="${esc(site.domain)} homepage"></div>` : ''}
</section>
<p class="receipt">${receipt}</p>`
  return page({
    title: `${site.domain} got ${letter} (${site.composite}/100), #${site.rank} of ${total}`,
    description: site.roast ?? config.tagline,
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
copyFileSync(join(root, 'site', 'style.css'), join(dist, 'style.css'))
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
