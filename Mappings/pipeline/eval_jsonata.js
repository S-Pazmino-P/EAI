const jsonata = require('jsonata');
let buf = '';
process.stdin.on('data', d => (buf += d));
process.stdin.on('end', async () => {
  try {
    const { expression, rows, metadata } = JSON.parse(buf);
    const expr = jsonata(expression);
    const bindings = metadata ? { metadata: metadata } : {};
    const out = [];
    for (const row of rows) {
      const r = await expr.evaluate(row, bindings);
      out.push(r === undefined ? null : r);
    }
    process.stdout.write(JSON.stringify(out));
  } catch (e) {
    process.stderr.write(JSON.stringify({ error: String(e && e.message || e) }));
    process.exit(1);
  }
});