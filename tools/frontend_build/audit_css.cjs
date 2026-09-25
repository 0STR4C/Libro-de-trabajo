// Conservative inventory: candidates require manual review before removal.
const fs = require('node:fs');
const path = require('node:path');
const { createRequire } = require('node:module');
const requireBuild = createRequire('/build/package.json');
const postcss = requireBuild('postcss');
const selectorParser = requireBuild('postcss-selector-parser');
const root = process.argv[2] || '/project';
const apply = process.argv.includes('--apply');
const sourceFiles = fs.readdirSync(path.join(root, 'frontend')).filter(f => f.endsWith('.jsx')).map(f => `frontend/${f}`);
sourceFiles.push('app/static/index.html', 'app/static/app.js', 'app/static/branding.js');
const source = sourceFiles.map(f => fs.readFileSync(path.join(root, f), 'utf8')).join('\n');
const prefixes = [...source.matchAll(/([\w-]+-)\$\{/g)].map(match => match[1]);
const report = {};
function unused(name) {
  // Reviewed retired families; similarly prefixed menu IDs are not CSS classes.
  if (/^(status-(chip|option|options|dropdown|select)|notice-(actions-menu|actions-pop|owner)|delay-metric-strip)$/.test(name)) return true;
  return !source.includes(name) && !/^(p-|pi-|leaflet-)/.test(name) && !['overdue', 'urgent', 'waiting', 'normal'].includes(name) && !prefixes.some(prefix => name.startsWith(prefix));
}
function pruneSelector(selector) {
  const parsed = selectorParser().astSync(selector);
  function pruneList(list) {
    for (const branch of [...list.nodes]) {
      let impossible = false;
      for (const node of branch.nodes || []) {
        if (['class', 'id'].includes(node.type) && unused(node.value)) impossible = true;
        if (node.type === 'pseudo' && [':is', ':where'].includes(node.value)) {
          pruneList(node);
          if (!node.nodes.length) impossible = true;
        }
      }
      if (impossible) branch.remove();
    }
  }
  pruneList(parsed);
  return parsed.toString();
}
for (const file of ['styles.css', 'operations.css', 'dashboard.css', 'quotes.css', 'settings.css', 'auth.css']) {
  if (!fs.existsSync(path.join(root, 'app/static', file))) continue;
  const tree = postcss.parse(fs.readFileSync(path.join(root, 'app/static', file), 'utf8'));
  const candidates = [];
  tree.walkRules(rule => {
    const keep = pruneSelector(rule.selector);
    if (keep === rule.selector) return;
    candidates.push({ before: rule.selector, after: keep });
    if (apply) { if (keep) rule.selector = keep; else rule.remove(); }
  });
  report[file] = [...new Set(candidates)];
  if (apply) {
    tree.walkAtRules(rule => { if (rule.nodes && !rule.nodes.some(node => node.type !== 'comment')) rule.remove(); });
    fs.writeFileSync(path.join(root, 'app/static', file), tree.toString());
    report[file] = { changedRules: candidates.length };
  }
}
process.stdout.write(JSON.stringify(report, null, 2) + '\n');
