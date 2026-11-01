// SPDX-License-Identifier: GPL-3.0-or-later
// Exercise the real page's retention and incremental DOM updates over a long run.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const html = fs.readFileSync(path.join(__dirname, '../../static/logs.html'), 'utf8');
const scripts = [...html.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/g)];
const elements = new Map();
const levels = ['DEBUG', 'INFO', 'WARN', 'ERROR'].map(value => ({ value, checked: true, addEventListener() { } }));
let fullTableRenders = 0;
const rows = [];
const table = {
    get innerHTML() { return rows.map(row => row.html).join(''); },
    set innerHTML(value) {
        fullTableRenders++;
        rows.length = 0;
        for (const match of value.matchAll(/<tr\b[\s\S]*?<\/tr>/g)) rows.push(makeRow(match[0]));
    },
    get children() { return rows; },
    get lastElementChild() { return rows.at(-1); },
    get textContent() { return this.innerHTML; },
    insertAdjacentHTML(where, value) {
        assert.equal(where, 'afterbegin');
        rows.unshift(makeRow(value));
    },
};
function makeRow(html) {
    return { html, remove() { rows.splice(rows.indexOf(this), 1); } };
}
elements.set('logsBody', table);
const context = vm.createContext({
    console,
    handleHome() { },
    document: {
        getElementById(id) {
            if (!elements.has(id)) elements.set(id, { checked: false, textContent: '', addEventListener() { } });
            return elements.get(id);
        },
        querySelectorAll(selector) {
            return selector.includes(':checked') ? levels.filter(level => level.checked) : levels;
        },
    },
    fetch: async () => ({ ok: true, json: async () => ({ logs: [] }) }),
    setTimeout: () => 0,
    clearTimeout() { },
});
vm.runInContext(scripts.at(-1)[1], context);
const run = code => vm.runInContext(code, context);
function batch(entries) {
    context.entries = entries;
    run('var batchResult = addFetchedEntries(entries); prependRenderedEntries(batchResult.newEntries, batchResult.removedEntries);');
}
const entry = i => ({ millis: i, level: i % 2 ? 'INFO' : 'DEBUG', sid: 1, pid: 2, message: { index: i } });

(async () => {
    // Complete the empty initial fetch before driving updates directly.
    await new Promise(resolve => setImmediate(resolve));
    batch(Array.from({ length: 2000 }, (_, i) => entry(i)));
    assert.equal(run('storedEntries.length'), 2000);
    assert.equal(run('seenEntries.size'), 2000);
    assert.equal(rows.length, 2000);
    const rendersBeforeEviction = fullTableRenders;
    for (let i = 2000; i < 10000; i += 20) batch(Array.from({ length: 20 }, (_, j) => entry(i + j)));
    assert.equal(run('storedEntries.length'), 2000);
    assert.equal(run('seenEntries.size'), 2000, 'deduplication memory must stay bounded');
    assert.equal(rows.length, 2000);
    assert.equal(run('renderedLines.length'), 2000);
    assert.equal(fullTableRenders, rendersBeforeEviction, 'eviction must not rebuild the table');
    assert(rows[0].html.includes('9999'));
    assert(rows.at(-1).html.includes('8000'));
    batch([entry(9999)]);
    assert.equal(rows.length, 2000, 'overlapping fetches must not duplicate entries');

    levels.find(level => level.value === 'DEBUG').checked = false;
    run('renderFromStoredData()');
    assert.equal(rows.length, 1000);
    for (let i = 10000; i < 12500; i += 10) batch(Array.from({ length: 10 }, (_, j) => entry(i + j)));
    assert.equal(rows.length, 1000, 'filtered evicted entries must not remove unrelated rows');
    assert.equal(run('renderedLines.length'), 1000);
    assert.equal(run('seenEntries.size'), 2000);

    // Restart markers remain visible even with all levels disabled, and evict normally.
    for (const level of levels) level.checked = false;
    run('renderFromStoredData()');
    batch([{ millis: 1, level: 'RESTART', message: 'restart', logRestart: true }]);
    assert.equal(rows.length, 1);
    batch(Array.from({ length: 2001 }, (_, i) => entry(20000 + i)));
    assert.equal(rows.length, 0);
    assert.equal(run('renderedLines.length'), 0);
    assert.equal(run('seenEntries.size'), 2000);
    console.log('Log retention, deduplication, filters, restart markers and incremental rendering passed.');
})().catch(error => { console.error(error); process.exitCode = 1; });
