// Exact versions come from package-lock.json; binaries embed the offline bundles.
import { mkdir, readFile, writeFile, copyFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
await mkdir('assets/vendor', { recursive: true });
const packages = [
  ['mathjax', 'es5/tex-svg-full.js', 'mathjax.js'],
  ['mermaid', 'dist/mermaid.min.js', 'mermaid.js'],
];
const manifest = {};
let licenses = 'Hugemark embedded JavaScript dependencies\n\n';
for (const [name, source, dest] of packages) {
  const pkg = JSON.parse(await readFile(`node_modules/${name}/package.json`, 'utf8'));
  const data = await readFile(`node_modules/${name}/${source}`);
  await writeFile(`assets/vendor/${dest}`, data);
  manifest[dest] = { package: name, version: pkg.version, sha256: createHash('sha256').update(data).digest('hex') };
  licenses += `\n===== ${name} ${pkg.version} =====\n` + await readFile(`node_modules/${name}/LICENSE`, 'utf8');
}
await writeFile('assets/vendor/manifest.json', JSON.stringify(manifest, null, 2) + '\n');
await writeFile('assets/vendor/LICENSES.txt', licenses);
