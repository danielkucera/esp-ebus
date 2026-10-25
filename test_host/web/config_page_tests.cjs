// Run the real configuration-page JavaScript against an empty NVS response.
// A select deliberately has no defaultValue, matching the browser DOM.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

const html = fs.readFileSync(process.argv[2] || path.join(__dirname, '../../static/config.html'), 'utf8');
const fields = new Map();
for (const match of html.matchAll(/<(input|select|textarea)\b([^>]*)>/g)) {
    const attrs = Object.fromEntries([...match[2].matchAll(/([\w-]+)="([^"]*)"/g)].map(x => [x[1], x[2]]));
    if (!attrs.class?.split(/\s+/).includes('config')) continue;
    const field = {
        id: attrs.id, tagName: match[1].toUpperCase(), type: attrs.type || 'text',
        value: attrs.value || '', defaultValue: attrs.value || '',
        checked: false, defaultChecked: false,
        setAttribute() {}, addEventListener() {},
    };
    if (match[1] === 'select') {
        const body = html.slice(match.index + match[0].length).split('</select>')[0];
        field.options = [...body.matchAll(/<option\b([^>]*)>/g)].map(option => ({
            value: /value="([^"]*)"/.exec(option[1])[1],
            defaultSelected: /\bselected\b/.test(option[1]),
        }));
        field.type = 'select-one';
        delete field.defaultValue;
        field.selectedIndex = field.options.findIndex(option => option.defaultSelected);
        if (field.selectedIndex < 0) field.selectedIndex = 0;
        Object.defineProperty(field, 'value', {
            get() { return this.options[this.selectedIndex]?.value || ''; },
            set(value) { this.selectedIndex = this.options.findIndex(option => option.value === String(value)); },
        });
    }
    fields.set(field.id, field);
}
const placeholders = new Map();
let stored = {};
let saved;
const context = vm.createContext({
    console,
    document: {
        getElementsByClassName() { return [...fields.values()]; },
        getElementById(id) {
            if (fields.has(id)) return fields.get(id);
            if (!placeholders.has(id)) placeholders.set(id, { addEventListener() {} });
            return placeholders.get(id);
        },
    },
    handleHome() {}, setStatus() {},
    async fetch(url, options) {
        if (options?.method === 'POST') {
            saved = JSON.parse(options.body);
            return { ok: true, text: async () => 'saved' };
        }
        return { ok: true, json: async () => stored };
    },
});
const script = /<script>([\s\S]*?)<\/script>/.exec(html)[1]
    .replace(/\n\s*loadConfig\(\);\s*$/, '');
vm.runInContext(script, context);

(async () => {
    await context.loadConfig();
    fields.get('wifiSsid').value = 'home-network';
    fields.get('wifiPassword').value = 'home-password';
    await context.saveConfig();
    assert.equal(saved.ebusAddress, 'ff', 'fresh reset must retain the default eBUS address');
    assert.equal(saved.pwmValue, '130');
    assert.equal(saved.busWindow, '4400');
    assert.equal(saved.busOffset, '50');
    assert.equal(saved.wifiSsid, 'home-network');
    assert.equal(saved.wifiPassword, 'home-password');

    stored = { config: { ebusAddress: '31', busWindow: '4400', busOffset: '0' } };
    await context.loadConfig();
    await context.saveConfig();
    assert.equal(saved.ebusAddress, '31', 'stored selection must override the default');
    assert.equal(saved.busOffset, '0');

    stored = {};
    await context.loadConfig();
    await context.saveConfig();
    assert.equal(saved.ebusAddress, 'ff', 'loading defaults again must restore the selected option');
    assert.equal(saved.busOffset, '50');
    console.log('PASS: empty NVS, saved selections, and repeated defaults preserve valid bus settings');
})().catch(error => { console.error(error); process.exitCode = 1; });
