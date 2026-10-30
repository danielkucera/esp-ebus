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
        setAttribute() { }, addEventListener() { },
    };
    if (match[1] !== 'select') {
        let value = field.value;
        Object.defineProperty(field, 'value', {
            get() { return value; },
            set(v) { value = String(v); },
        });
    }
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
const metadata = {
    pwmValue: { default: 130, min: 1, max: 255 },
    busWindow: { default: 4350, min: 4332, max: 4424 },
    ebusAddress: { default: 'ff' },
    systemResponse: { default: true },
};
let stored = { config: {}, fields: metadata };
let saved;
let posts = 0;
let responseOk = true;
const context = vm.createContext({
    console: { log: console.log, error() { } },
    document: {
        getElementsByClassName() { return [...fields.values()]; },
        getElementById(id) {
            if (fields.has(id)) return fields.get(id);
            if (!placeholders.has(id)) placeholders.set(id, { addEventListener() { } });
            return placeholders.get(id);
        },
    },
    handleHome() { }, setStatus() { },
    async fetch(url, options) {
        if (options?.method === 'POST') {
            posts++;
            saved = JSON.parse(options.body);
            return { ok: true, text: async () => 'saved' };
        }
        return { ok: responseOk, json: async () => stored };
    },
});
const script = /<script>([\s\S]*?)<\/script>/.exec(html)[1]
    .replace(/\n\s*loadConfig\(\);\s*$/, '');
vm.runInContext(script, context);

(async () => {
    // The HTML itself disables Save before JavaScript starts loading.
    assert.match(html, /id="btnSave"[^>]*disabled/);
    await context.loadConfig();
    assert.equal(context.document.getElementById('btnSave').disabled, false);
    assert.equal(fields.get('busWindow').min, metadata.busWindow.min);
    assert.equal(fields.get('busWindow').max, metadata.busWindow.max);
    assert.equal(fields.get('systemResponse').checked, true);
    fields.get('wifiSsid').value = 'home-network';
    fields.get('wifiPassword').value = 'home-password';
    await context.saveConfig();
    assert.equal(saved.ebusAddress, 'ff', 'fresh reset must retain the default eBUS address');
    assert.equal(saved.pwmValue, '130');
    assert.equal(saved.busWindow, '4350');
    assert.equal(saved.wifiSsid, 'home-network');
    assert.equal(saved.wifiPassword, 'home-password');

    stored = { config: { ebusAddress: '31', busWindow: '4350', systemResponse: 'false' }, fields: metadata };
    await context.loadConfig();
    await context.saveConfig();
    assert.equal(saved.ebusAddress, '31', 'stored selection must override the default');
    assert.equal(saved.systemResponse, 'false');

    stored = { config: {}, fields: metadata };
    await context.loadConfig();
    await context.saveConfig();
    assert.equal(saved.ebusAddress, 'ff', 'loading defaults again must restore the selected option');
    // Changing backend metadata must change UI defaults and limits without HTML edits.
    stored = {
        config: {}, fields: {
            ...metadata,
            busWindow: { default: 4321, min: 4200, max: 4600 },
            ebusAddress: { default: '31' },
        }
    };
    await context.loadConfig();
    await context.saveConfig();
    assert.equal(saved.busWindow, '4321');
    assert.equal(saved.ebusAddress, '31');
    assert.equal(fields.get('busWindow').min, 4200);
    assert.equal(fields.get('busWindow').max, 4600);
    for (const id of ['wifiPassword', 'apModePassword', 'mqttPass']) {
        assert.equal(fields.get(id).value, '');
        assert.equal(fields.get(id).defaultValue, '');
    }

    const before = posts;
    responseOk = false;
    await context.loadConfig();
    assert.equal(context.document.getElementById('btnSave').disabled, true);
    await context.saveConfig();
    assert.equal(posts, before, 'failed loads must not allow a POST');
    responseOk = true;
    stored = {};
    await context.loadConfig();
    await context.saveConfig();
    assert.equal(posts, before, 'missing metadata must not allow a POST');
    assert.equal(context.document.getElementById('btnSaveFile').disabled, true);
    console.log('PASS: server defaults, limits, saved overrides, passwords, and load failures');
})().catch(error => { console.error(error); process.exitCode = 1; });
