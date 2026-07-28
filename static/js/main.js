// Common JavaScript utilities for the oscar monitor

// ── SweetAlert2 wrappers (replace native alert/confirm) ──

const Toast = Swal.mixin({
    toast: true, position: 'top-end', showConfirmButton: false,
    timer: 3000, timerProgressBar: true,
    didOpen: (t) => { t.addEventListener('mouseenter', Swal.stopTimer); t.addEventListener('mouseleave', Swal.resumeTimer); }
});

function swalConfirm(title, text, confirmText) {
    return Swal.fire({
        title: title, text: text || '', icon: 'question',
        showCancelButton: true, confirmButtonText: confirmText || '确定',
        cancelButtonText: '取消', confirmButtonColor: '#0d6efd',
        customClass: { popup: 'animate__animated animate__fadeInUp animate__faster' }
    }).then(r => r.isConfirmed);
}

function swalToast(msg, icon) {
    Toast.fire({ icon: icon || 'success', title: msg });
}

function swalError(msg) {
    Swal.fire({ icon: 'error', title: '操作失败', text: msg, confirmButtonColor: '#dc3545',
        customClass: { popup: 'animate__animated animate__shakeX animate__faster' } });
}

function swalSuccess(msg) {
    Swal.fire({ icon: 'success', title: '操作成功', text: msg, timer: 2000, showConfirmButton: false,
        customClass: { popup: 'animate__animated animate__bounceIn animate__faster' } });
}

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
            Swal.fire({ icon: 'warning', title: '必填项', text: f.label + '为必填项', confirmButtonColor: '#0d6efd',
                customClass: { popup: 'animate__animated animate__headShake animate__faster' } });
            el.focus();
            return false;
        }
    }
    return true;
}

// ── Shared rendering helpers ──────────────────────────────

function renderTable(result) {
    if (!result || result.error) {
        return '<div class="text-danger">错误: ' + (result.error || '无数据') + '</div>';
    }
    if (!result.columns || result.columns.length === 0) {
        if (result.rows && result.rows.length > 0) {
            return '<pre class="small p-2 bg-light">' + result.rows.map(r => r.join(' | ')).join('\n') + '</pre>';
        }
        return '<div class="text-muted">无数据</div>';
    }
    let html = '<div class="table-responsive"><table class="table table-sm table-bordered table-striped mb-0">';
    html += '<thead class="table-dark"><tr>';
    result.columns.forEach(col => { html += '<th>' + col + '</th>'; });
    html += '</tr></thead><tbody>';
    if (result.rows && result.rows.length > 0) {
        result.rows.forEach(row => {
            html += '<tr>';
            for (let i = 0; i < result.columns.length; i++) {
                html += '<td class="small">' + (row[i] !== undefined ? row[i] : '') + '</td>';
            }
            html += '</tr>';
        });
    } else {
        html += '<tr><td colspan="' + result.columns.length + '" class="text-muted">无数据</td></tr>';
    }
    html += '</tbody></table></div>';
    return html;
}

function renderCard(title, icon, content) {
    return '<div class="card mb-2">' +
        '<div class="card-header py-1"><i class="bi bi-' + icon + '"></i> <strong>' + title + '</strong></div>' +
        '<div class="card-body p-1">' + content + '</div></div>';
}

function renderMetrics(items) {
    if (!items || items.length === 0) return '<span class="text-muted small">无数据</span>';
    return items.map(m => '<div class="d-flex justify-content-between small mb-1"><span>' + m.label + '</span><strong>' + m.value + '</strong></div>').join('');
}

function renderDiskTable(disks) {
    if (!disks || disks.length === 0) return '<span class="text-muted small">无数据</span>';
    let h = '<table class="table table-sm table-bordered mb-0"><thead class="table-secondary"><tr><th>磁盘</th><th>已用</th><th>总量</th><th>使用率</th></tr></thead><tbody>';
    disks.forEach(d => {
        const pctBar = d.pct !== null ? '<div class="progress" style="height:4px;"><div class="progress-bar ' + (d.pct > 80 ? 'bg-danger' : d.pct > 60 ? 'bg-warning' : 'bg-success') + '" style="width:' + d.pct + '%"></div></div> ' + d.pct + '%' : '-';
        h += '<tr><td>' + d.mount + '</td><td>' + d.used + '</td><td>' + d.total + '</td><td>' + pctBar + '</td></tr>';
    });
    h += '</tbody></table>';
    return h;
}

// ── OS output parsers (shared by detail & index pages) ────

function parseWinMem(output) {
    const m = output.match(/TotalMB=(\d+).*?FreeMB=(\d+).*?UsedMB=(\d+)/);
    if (!m) return null;
    const total = parseInt(m[1]), used = parseInt(m[3]), free = parseInt(m[2]);
    return [
        {label: '总量', value: (total/1024).toFixed(1) + ' GB'},
        {label: '已用', value: (used/1024).toFixed(1) + ' GB'},
        {label: '可用', value: (free/1024).toFixed(1) + ' GB'},
        {label: '使用率', value: (used/total*100).toFixed(1) + '%'},
    ];
}

function parseLinuxMem(output) {
    const m = output.match(/Mem:\s+(\S+)\s+(\S+)\s+(\S+)/);
    if (!m) return null;
    return [
        {label: '总量', value: m[1]},
        {label: '已用', value: m[2]},
        {label: '可用', value: m[3]},
    ];
}

function parseWinDisk(output) {
    const disks = [];
    const lines = output.split('\n');
    for (const line of lines) {
        const m = line.match(/^(\w+)\s+([\d.]+)GB\/([\d.]+)GB/);
        if (m) {
            const used = parseFloat(m[2]), total = parseFloat(m[3]);
            disks.push({mount: m[1] + ':', used: m[2] + ' GB', total: m[3] + ' GB', pct: total > 0 ? Math.round(used/total*100) : null});
        }
    }
    if (disks.length > 0) return disks;
    for (const line of lines) {
        const parts = line.trim().split(/\s+/);
        if (parts.length >= 6 && parts[4].endsWith('%')) {
            disks.push({mount: parts[5], used: parts[2], total: parts[1], pct: parseInt(parts[4])});
        }
    }
    return disks.length > 0 ? disks : null;
}

function parseLinuxDisk(output) {
    const disks = [];
    const lines = output.split('\n');
    for (const line of lines) {
        if (line.startsWith('/') || line.match(/^[A-Z]:/)) {
            const parts = line.trim().split(/\s+/);
            if (parts.length >= 5) {
                disks.push({mount: parts[5] || parts[0], used: parts[2], total: parts[1], pct: parseInt(parts[4]) || null});
            }
        }
    }
    return disks.length > 0 ? disks : null;
}

function parseWinCpu(output) {
    const m = output.match(/LoadPercentage=(\d+)/);
    if (m) return [{label: 'CPU使用率', value: m[1] + '%'}];
    return null;
}

function parseLinuxCpu(output) {
    const m = output.match(/load average:\s*([\d.]+),\s*([\d.]+),\s*([\d.]+)/);
    if (m) return [
        {label: '1分钟', value: m[1]},
        {label: '5分钟', value: m[2]},
        {label: '15分钟', value: m[3]},
    ];
    return null;
}
