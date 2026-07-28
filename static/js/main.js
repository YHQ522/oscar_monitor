// Common JavaScript utilities for the oscar monitor

function escapeHtml(str) {
    if (!str) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}

async function apiFetch(url, options) {
    const resp = await fetch(url, options);
    if (resp.status === 401) {
        const data = await resp.json().catch(() => ({}));
        window.location.href = data.redirect || '/login';
        throw new Error('会话已过期');
    }
    if (!resp.ok) {
        const text = await resp.text();
        try { return JSON.parse(text); } catch(e) { throw new Error(text); }
    }
    const text = await resp.text();
    try { return JSON.parse(text); } catch(e) { throw new Error('无效的响应: ' + text.substring(0, 100)); }
}

function collectApps(prefix) {
    const items = [];
    document.querySelectorAll('.' + prefix + 'app-row').forEach(row => {
        const name = row.querySelector('.app-name').value.trim();
        const port = parseInt(row.querySelector('.app-port').value) || 0;
        const svc = row.querySelector('.app-svc').value.trim();
        const inControl = row.querySelector('.app-in-control').checked;
        if (name && port) {
            items.push({name: name, port: port, svc_name: svc || name, in_control: inControl});
        }
    });
    return items;
}

function addAppRow(prefix) {
    const list = document.getElementById(prefix + 'AppList');
    const div = document.createElement('div');
    div.className = prefix + 'app-row border rounded p-2 mb-2 bg-light';
    div.innerHTML = '<div class="row g-1">' +
        '<div class="col-md-3"><input class="form-control form-control-sm app-name" placeholder="应用名称"></div>' +
        '<div class="col-md-2"><input class="form-control form-control-sm app-port" type="number" placeholder="端口"></div>' +
        '<div class="col-md-3"><input class="form-control form-control-sm app-svc" placeholder="服务名"></div>' +
        '<div class="col-md-2"><div class="form-check"><input class="form-check-input app-in-control" type="checkbox"><label class="form-check-label small">加入启停管控</label></div></div>' +
        '<div class="col-md-auto"><button type="button" class="btn btn-sm btn-outline-danger" onclick="this.closest(\'.' + prefix + 'app-row\').remove()">&times;</button></div>' +
        '</div>';
    list.appendChild(div);
}

function toggleCheckAll(sectionId, cls, checked) {
    document.querySelectorAll('#' + sectionId + ' .' + cls).forEach(c => {
        c.checked = checked;
        c.dispatchEvent(new Event('change'));
    });
}

function syncCheckAll(prefix) {
    ['Cat', 'Os'].forEach(type => {
        const cls = '.' + prefix + '-cat-check, .' + prefix + '-os-check';
        const sectionId = type === 'Cat' ? prefix + 'DbCheckItems' : prefix + 'OsCheckItems';
        const items = document.querySelectorAll('#' + sectionId + ' input[type=checkbox]');
        const allChecked = Array.from(items).every(c => c.checked);
        const noneChecked = Array.from(items).every(c => !c.checked);
        const master = document.getElementById(prefix + type + 'All');
        if (master) {
            master.checked = allChecked;
            master.indeterminate = !allChecked && !noneChecked;
        }
    });
}

function validateRequired(fields) {
    for (const f of fields) {
        const el = document.getElementById(f.id);
        const val = (el.value || '').trim();
        if (!val) {
            alert(f.label + '为必填项');
            el.focus();
            return false;
        }
    }
    return true;
}
