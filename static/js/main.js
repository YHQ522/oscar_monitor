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

// ═══════════════════════════════════════════════
//  统一弹窗助手 (SweetAlert2 美化版)
// ═══════════════════════════════════════════════
const SWAL_BASE = {
    customClass: {
        popup: 'swal-popup',
        title: 'swal-title',
        htmlContainer: 'swal-text',
        confirmButton: 'swal-btn swal-btn-confirm',
        cancelButton: 'swal-btn swal-btn-cancel',
    },
    buttonsStyling: false,
    showClass: { popup: 'animate__animated animate__fadeInUp animate__faster' },
    hideClass: { popup: 'animate__animated animate__fadeOutDown animate__faster' },
};

function swalError(msg) {
    return Swal.fire({
        ...SWAL_BASE,
        icon: 'error',
        title: '操作失败',
        html: `<div class="swal-msg">${escapeHtml(msg)}</div>`,
        confirmButtonText: '知道了',
        customClass: { ...SWAL_BASE.customClass, confirmButton: 'swal-btn swal-btn-confirm swal-btn-danger' },
    });
}
function swalSuccess(msg) {
    return Swal.fire({
        ...SWAL_BASE,
        icon: 'success',
        title: '操作成功',
        html: `<div class="swal-msg">${escapeHtml(msg)}</div>`,
        timer: 1800,
        showConfirmButton: false,
    });
}
function swalConfirm(msg, title) {
    return Swal.fire({
        ...SWAL_BASE,
        icon: 'question',
        title: title || '确认操作',
        html: `<div class="swal-msg">${escapeHtml(msg)}</div>`,
        showCancelButton: true,
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        reverseButtons: false,
        focusCancel: true,
        iconColor: '#6366F1',
    });
}
function swalDanger(msg, title) {
    return Swal.fire({
        ...SWAL_BASE,
        icon: 'warning',
        title: title || '危险操作',
        html: `<div class="swal-msg" style="color:#dc3545;">${escapeHtml(msg)}</div>`,
        showCancelButton: true,
        confirmButtonText: '确定删除',
        cancelButtonText: '取消',
        reverseButtons: false,
        focusCancel: true,
        iconColor: '#dc3545',
        customClass: { ...SWAL_BASE.customClass, confirmButton: 'swal-btn swal-btn-confirm swal-btn-danger' },
    });
}
function swalInfo(msg, title) {
    return Swal.fire({
        ...SWAL_BASE,
        icon: 'info',
        title: title || '提示',
        html: `<div class="swal-msg">${escapeHtml(msg)}</div>`,
        confirmButtonText: '知道了',
        iconColor: '#6366F1',
    });
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
            items.push({
                name: name, port: port, svc_name: svc || name, in_control: inControl,
                group: row.querySelector('.app-group')?.value || '',
                health_url: row.querySelector('.app-health-url')?.value || '',
                start_cmd: row.querySelector('.app-start-cmd')?.value || '',
                stop_cmd: row.querySelector('.app-stop-cmd')?.value || '',
                svc_mgr: row.querySelector('.app-svc-mgr')?.value || '',
            });
        }
    });
    return items;
}

function addAppRow(prefix, data) {
    data = data || {};
    const list = document.getElementById(prefix + 'AppList');
    const div = document.createElement('div');
    div.className = prefix + 'app-row border rounded p-2 mb-2 bg-light';
    div.innerHTML = '<div class="row g-1">' +
        '<div class="col-md-3"><input class="form-control form-control-sm app-name" placeholder="应用名称" value="' + (data.name || '') + '"></div>' +
        '<div class="col-md-2"><input class="form-control form-control-sm app-port" type="number" placeholder="端口" value="' + (data.port || '') + '"></div>' +
        '<div class="col-md-3"><input class="form-control form-control-sm app-svc" placeholder="服务名" value="' + (data.svc_name || '') + '"></div>' +
        '<div class="col-md-2"><div class="form-check"><input class="form-check-input app-in-control" type="checkbox"' + (data.in_control ? ' checked' : '') + '><label class="form-check-label small">加入启停管控</label></div></div>' +
        '<div class="col-md-auto"><button type="button" class="btn btn-sm btn-outline-danger" onclick="this.closest(\'.' + prefix + 'app-row\').remove()">&times;</button></div>' +
        '<input type="hidden" class="app-group" value="' + (data.group || '') + '">' +
        '<input type="hidden" class="app-health-url" value="' + (data.health_url || '') + '">' +
        '<input type="hidden" class="app-start-cmd" value="' + (data.start_cmd || '') + '">' +
        '<input type="hidden" class="app-stop-cmd" value="' + (data.stop_cmd || '') + '">' +
        '<input type="hidden" class="app-svc-mgr" value="' + (data.svc_mgr || '') + '">' +
        '</div>';
    list.appendChild(div);
}

// ── 应用模板 ──
var appTemplates = {};
async function loadAppTemplates() {
    try {
        var resp = await apiFetch('/api/app-templates');
        appTemplates = resp;
        ['add', 'edit'].forEach(function(prefix) {
            var sel = document.getElementById(prefix + 'AppTemplate');
            if (!sel) return;
            sel.innerHTML = '<option value="">📋 快速添加...</option>';
            Object.keys(appTemplates).forEach(function(key) {
                var t = appTemplates[key];
                sel.innerHTML += '<option value="' + key + '">' + t.name + '</option>';
            });
        });
    } catch(e) {}
}

function applyTemplate(prefix, key) {
    if (!key || !appTemplates[key]) return;
    var t = appTemplates[key];
    document.getElementById(prefix + 'AppTemplate').value = '';
    addAppRow(prefix, {
        name: t.name, port: t.port, svc_name: t.svc_name || t.name,
        group: t.group || '', health_url: t.health_url || '',
        start_cmd: t.start_cmd || '', stop_cmd: t.stop_cmd || '',
        svc_mgr: t.svc_mgr || '', in_control: true
    });
}

// 自动加载模板
document.addEventListener('DOMContentLoaded', function() {
    if (document.getElementById('addAppTemplate') || document.getElementById('editAppTemplate')) {
        loadAppTemplates();
    }
});

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
            Swal.fire({
                ...SWAL_BASE,
                icon: 'warning',
                title: '必填项未填写',
                html: `<div class="swal-msg">请填写 <strong style="color:#d63384;">${escapeHtml(f.label)}</strong></div>`,
                confirmButtonText: '知道了',
                iconColor: '#d63384',
                didClose: () => { el.focus(); el.classList.add('is-invalid'); setTimeout(() => el.classList.remove('is-invalid'), 2000); }
            });
            return false;
        }
    }
    return true;
}
