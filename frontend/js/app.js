/**
 * Exam Proctoring System — Frontend Application
 * AWS-inspired minimalist SPA with live data polling
 */

(() => {
    'use strict';

    // ─────────────────────────────────────────────
    // Configuration
    // ─────────────────────────────────────────────
    const API_BASE = window.location.origin;
    const POLL_INTERVAL = 3000; // 3 seconds
    let pollTimer = null;
    let currentPage = 'exam';

    // ─────────────────────────────────────────────
    // API Client
    // ─────────────────────────────────────────────
    async function api(endpoint, options = {}) {
        try {
            const url = `${API_BASE}${endpoint}`;
            const res = await fetch(url, {
                headers: { 'Content-Type': 'application/json' },
                ...options
            });
            if (!res.ok) {
                const err = await res.json().catch(() => ({ error: res.statusText }));
                throw new Error(err.error || res.statusText);
            }
            return await res.json();
        } catch (e) {
            console.warn(`API ${endpoint}:`, e.message);
            return null;
        }
    }

    const API = {
        getStatus:       () => api('/api/status'),
        getStats:        () => api('/api/stats'),
        getViolations:   (type) => api(`/api/violations${type ? '?type=' + type : ''}`),
        getAlerts:       (limit = 50) => api(`/api/alerts?limit=${limit}`),
        getReports:      () => api('/api/reports'),
        getRecordings:   () => api('/api/recordings'),
        getConfig:       () => api('/api/config'),
        updateConfig:    (cfg) => api('/api/config', { method: 'PUT', body: JSON.stringify(cfg) }),
        startSession:    (data) => api('/api/session/start', { method: 'POST', body: JSON.stringify(data) }),
        stopSession:     () => api('/api/session/stop', { method: 'POST' }),
        getCurrentSession: () => api('/api/session/current'),
        // Exam (live webcam + detection)
        startExam:       (data) => api('/api/exam/start', { method: 'POST', body: JSON.stringify(data) }),
        stopExam:        () => api('/api/exam/stop', { method: 'POST' }),
        examStatus:      () => api('/api/exam/status'),
        // Exam list management
        getExams:        () => api('/api/exams'),
        addExam:         (data) => api('/api/exams', { method: 'POST', body: JSON.stringify(data) }),
        deleteExam:      (id) => api(`/api/exams/${id}`, { method: 'DELETE' }),
    };


    // ─────────────────────────────────────────────
    // DOM Utilities
    // ─────────────────────────────────────────────
    const $ = (sel) => document.querySelector(sel);
    const $$ = (sel) => document.querySelectorAll(sel);

    function showToast(msg, type = 'success') {
        const toast = document.createElement('div');
        toast.className = `toast ${type}`;
        toast.textContent = msg;
        document.body.appendChild(toast);
        setTimeout(() => toast.remove(), 3000);
    }


    // ─────────────────────────────────────────────
    // Navigation
    // ─────────────────────────────────────────────
    function navigateTo(page) {
        currentPage = page;

        // Update nav active state
        $$('.nav-item').forEach(item => {
            item.classList.toggle('active', item.dataset.page === page);
        });

        // Show/hide page sections
        $$('.page-section').forEach(section => {
            section.classList.toggle('active', section.id === `page-${page}`);
        });

        // Update topbar title
        const pageNames = {
            exam:       'Exam Proctoring',
            dashboard:  'Dashboard',
            monitoring: 'Live Monitoring',
            violations: 'Violation Log',
            alerts:     'Alert Log',
            reports:    'Reports',
            recordings: 'Recordings',
            sessions:   'Session Management',
            settings:   'Configuration'
        };
        $('#page-title').textContent = pageNames[page] || 'Dashboard';

        // Load page data
        loadPageData(page);
    }


    // ─────────────────────────────────────────────
    // Clock
    // ─────────────────────────────────────────────
    function updateClock() {
        const now = new Date();
        const h = String(now.getHours()).padStart(2, '0');
        const m = String(now.getMinutes()).padStart(2, '0');
        const s = String(now.getSeconds()).padStart(2, '0');
        $('#topbar-clock').textContent = `${h}:${m}:${s}`;
    }


    // ─────────────────────────────────────────────
    // Data Loading per Page
    // ─────────────────────────────────────────────
    async function loadPageData(page) {
        switch(page) {
            case 'exam':        await loadExam(); break;
            case 'dashboard':   await loadDashboard(); break;
            case 'monitoring':  await loadMonitoring(); break;
            case 'violations':  await loadViolations(); break;
            case 'alerts':      await loadAlerts(); break;
            case 'reports':     await loadReports(); break;
            case 'recordings':  await loadRecordings(); break;
            case 'sessions':    await loadSessions(); break;
            case 'settings':    await loadSettings(); break;
        }
    }


    // ─────────────────────────────────────────────
    // Dashboard
    // ─────────────────────────────────────────────
    async function loadDashboard() {
        const [stats, session, alerts] = await Promise.all([
            API.getStats(),
            API.getCurrentSession(),
            API.getAlerts(8)
        ]);

        if (stats) renderDashboardStats(stats);
        if (session) renderDashboardSession(session);
        if (alerts) renderDashboardAlerts(alerts);
    }

    function renderDashboardStats(stats) {
        const prob = stats.cheating_probability || 0;

        // Stat cards
        $('#stat-probability').textContent = `${prob}%`;
        $('#stat-face').textContent = stats.face_detected ? 'Present' : 'Absent';
        $('#stat-gaze').textContent = capitalize(stats.gaze_direction || 'Center');
        $('#stat-eyes').textContent = stats.eyes_open ? 'Open' : 'Closed';
        $('#stat-mouth').textContent = stats.mouth_moving ? 'Moving' : 'Still';
        $('#stat-objects').textContent = stats.objects_detected ? 'Yes ⚠' : 'None';

        // Apply color classes to stat values
        $('#stat-face').style.color = stats.face_detected ? 'var(--color-success)' : 'var(--color-danger)';
        $('#stat-objects').style.color = stats.objects_detected ? 'var(--color-danger)' : 'var(--color-success)';
        $('#stat-mouth').style.color = stats.mouth_moving ? 'var(--color-warning)' : 'var(--color-success)';

        // Probability gauge
        const circle = $('#gauge-circle');
        const circumference = 2 * Math.PI * 80; // r=80
        const offset = circumference - (prob / 100) * circumference;
        circle.style.strokeDasharray = circumference;
        circle.style.strokeDashoffset = offset;

        // Color class
        circle.classList.remove('low', 'medium', 'high');
        if (prob < 30)      { circle.classList.add('low'); }
        else if (prob < 60) { circle.classList.add('medium'); }
        else                { circle.classList.add('high'); }

        $('#gauge-number').textContent = prob;

        // Label
        const label = prob < 30 ? 'Low Risk' : prob < 60 ? 'Medium Risk' : 'High Risk';
        $('#gauge-label').textContent = label;
        $('#gauge-label').style.color = prob < 30 ? 'var(--color-success)' : prob < 60 ? 'var(--color-warning)' : 'var(--color-danger)';

        // Reasons
        const reasonsList = $('#gauge-reasons');
        const reasons = stats.cheating_reasons || [];
        if (reasons.length > 0 && prob >= 30) {
            reasonsList.innerHTML = reasons.map(r => `<li>${escapeHtml(r)}</li>`).join('');
        } else {
            reasonsList.innerHTML = '';
        }
    }

    function renderDashboardSession(session) {
        const banner = $('#dashboard-session-banner');
        const text = $('#dashboard-session-text');
        const duration = $('#dashboard-session-duration');

        if (session.active) {
            banner.classList.remove('inactive');
            text.textContent = `Active Session — ${session.student?.name || 'Unknown'} (${session.student?.exam || 'Exam'})`;
            duration.textContent = session.duration || '00:00:00';
        } else {
            banner.classList.add('inactive');
            text.textContent = 'No active session';
            duration.textContent = '';
        }
    }

    function renderDashboardAlerts(alerts) {
        const container = $('#dashboard-alerts');
        if (!alerts || alerts.length === 0) {
            container.innerHTML = `
                <div class="empty-state">
                    <div class="empty-icon">🔔</div>
                    <h4>No alerts yet</h4>
                    <p>Alerts will appear here during monitoring</p>
                </div>`;
            return;
        }

        container.innerHTML = alerts.slice(0, 8).map(a => {
            const severity = getAlertSeverity(a.type);
            return `
                <div class="alert-item ${severity}">
                    <span class="alert-time">${formatAlertTime(a.timestamp)}</span>
                    <div class="alert-content">
                        <div class="alert-type">${escapeHtml(a.type)}</div>
                        <div class="alert-msg">${escapeHtml(a.message)}</div>
                    </div>
                </div>`;
        }).join('');
    }


    // ─────────────────────────────────────────────
    // Monitoring
    // ─────────────────────────────────────────────
    async function loadMonitoring() {
        const [status, stats] = await Promise.all([
            API.getStatus(),
            API.getStats()
        ]);

        if (stats) renderMonitoringCards(stats);
        if (status) renderModulesTable(status);
    }

    function renderMonitoringCards(stats) {
        const modules = [
            {
                title: 'Face Detection',
                value: stats.face_detected ? 'Face Present' : 'Face Absent',
                icon: '👤',
                status: stats.face_detected ? 'ok' : 'err',
                desc: 'MTCNN-based face presence detection'
            },
            {
                title: 'Eye Gaze Tracking',
                value: `Looking ${capitalize(stats.gaze_direction || 'Center')}`,
                icon: '👁',
                status: (stats.gaze_direction || 'center').toLowerCase() === 'center' ? 'ok' : 'warn',
                desc: 'MediaPipe eye landmark tracking'
            },
            {
                title: 'Eye Status',
                value: stats.eyes_open ? 'Eyes Open' : 'Eyes Closed',
                icon: '🔍',
                status: stats.eyes_open ? 'ok' : 'warn',
                desc: `EAR: ${(stats.eye_ratio || 0).toFixed(2)}`
            },
            {
                title: 'Mouth Detection',
                value: stats.mouth_moving ? 'Movement Detected' : 'No Movement',
                icon: '💬',
                status: stats.mouth_moving ? 'warn' : 'ok',
                desc: 'Mouth openness & width monitoring'
            },
            {
                title: 'Object Detection',
                value: stats.objects_detected ? 'Object Found!' : 'Clear',
                icon: '📱',
                status: stats.objects_detected ? 'err' : 'ok',
                desc: 'YOLOv8 phone/book detection'
            },
            {
                title: 'Multiple Faces',
                value: stats.multiple_faces ? 'Multiple Detected!' : 'Single Face',
                icon: '👥',
                status: stats.multiple_faces ? 'err' : 'ok',
                desc: 'Multi-face MTCNN detection'
            }
        ];

        const grid = $('#monitoring-grid');
        grid.innerHTML = modules.map(m => `
            <div class="detection-card">
                <div class="detection-icon ${m.status}">${m.icon}</div>
                <div class="detection-info">
                    <h4>${m.title}</h4>
                    <p><strong>${escapeHtml(m.value)}</strong></p>
                    <p>${escapeHtml(m.desc)}</p>
                </div>
            </div>`).join('');
    }

    function renderModulesTable(status) {
        const modules = status.detection_modules || {};
        const tbody = $('#modules-tbody');
        const moduleInfo = {
            face_detection:       { name: 'Face Detection',       desc: 'MTCNN face presence tracking' },
            eye_tracking:         { name: 'Eye Gaze Tracking',    desc: 'MediaPipe gaze direction & EAR' },
            mouth_detection:      { name: 'Mouth Detection',      desc: 'Lip movement analysis' },
            object_detection:     { name: 'Object Detection',     desc: 'YOLOv8 forbidden object scanning' },
            multi_face_detection: { name: 'Multi-Face Detection', desc: 'Multiple person detection' },
            audio_monitoring:     { name: 'Audio Monitoring',     desc: 'Voice activity & speech detection' }
        };

        tbody.innerHTML = Object.entries(modules).map(([key, enabled]) => {
            const info = moduleInfo[key] || { name: key, desc: '' };
            return `
                <tr>
                    <td><strong>${info.name}</strong></td>
                    <td><span class="badge ${enabled ? 'badge-success' : 'badge-neutral'}">${enabled ? 'Active' : 'Disabled'}</span></td>
                    <td class="mono">${status.server_time || '—'}</td>
                    <td>${info.desc}</td>
                </tr>`;
        }).join('');
    }


    // ─────────────────────────────────────────────
    // Violations
    // ─────────────────────────────────────────────
    async function loadViolations() {
        const typeFilter = $('#violation-filter')?.value || '';
        const violations = await API.getViolations(typeFilter);

        const tbody = $('#violations-tbody');
        const countEl = $('#violation-count');

        if (!violations || violations.length === 0) {
            tbody.innerHTML = `<tr><td colspan="4"><div class="empty-state"><div class="empty-icon">✅</div><h4>No violations recorded</h4><p>Violations will appear here during proctoring</p></div></td></tr>`;
            countEl.textContent = '0 violations';
            return;
        }

        countEl.textContent = `${violations.length} violation${violations.length !== 1 ? 's' : ''}`;

        tbody.innerHTML = violations.map(v => {
            const meta = v.metadata || {};
            const prob = meta.cheating_probability ?? '—';
            const reasons = (meta.cheating_reasons || []).join(', ') || '—';
            const badgeClass = getViolationBadgeClass(v.type);

            return `
                <tr>
                    <td class="mono">${escapeHtml(v.timestamp || '—')}</td>
                    <td><span class="badge ${badgeClass}">${escapeHtml(v.type)}</span></td>
                    <td>${prob}%</td>
                    <td style="max-width:300px">${escapeHtml(reasons)}</td>
                </tr>`;
        }).join('');
    }


    // ─────────────────────────────────────────────
    // Alerts
    // ─────────────────────────────────────────────
    async function loadAlerts() {
        const alerts = await API.getAlerts(100);
        const container = $('#alerts-timeline');

        if (!alerts || alerts.length === 0) {
            container.innerHTML = `
                <div class="empty-state">
                    <div class="empty-icon">🔔</div>
                    <h4>No alerts recorded</h4>
                    <p>Alerts will appear here as they are generated</p>
                </div>`;
            return;
        }

        container.innerHTML = alerts.map(a => {
            const severity = getAlertSeverity(a.type);
            return `
                <div class="alert-item ${severity}">
                    <span class="alert-time">${formatAlertTime(a.timestamp)}</span>
                    <div class="alert-content">
                        <div class="alert-type">${escapeHtml(a.type)}</div>
                        <div class="alert-msg">${escapeHtml(a.message)}</div>
                    </div>
                </div>`;
        }).join('');
    }


    // ─────────────────────────────────────────────
    // Reports
    // ─────────────────────────────────────────────
    async function loadReports() {
        const reports = await API.getReports();
        const tbody = $('#reports-tbody');

        if (!reports || reports.length === 0) {
            tbody.innerHTML = `<tr><td colspan="5"><div class="empty-state"><div class="empty-icon">📄</div><h4>No reports generated</h4><p>Reports are created at the end of each proctoring session</p></div></td></tr>`;
            return;
        }

        tbody.innerHTML = reports.map(r => `
            <tr>
                <td><strong>${escapeHtml(r.filename)}</strong></td>
                <td><span class="badge badge-info">${r.format}</span></td>
                <td>${r.size_formatted}</td>
                <td class="mono">${r.created_at}</td>
                <td><a href="${API_BASE}/api/reports/${encodeURIComponent(r.filename)}" class="btn btn-sm" download>↓ Download</a></td>
            </tr>
        `).join('');
    }


    // ─────────────────────────────────────────────
    // Recordings
    // ─────────────────────────────────────────────
    async function loadRecordings() {
        const recordings = await API.getRecordings();
        const tbody = $('#recordings-tbody');

        if (!recordings || recordings.length === 0) {
            tbody.innerHTML = `<tr><td colspan="5"><div class="empty-state"><div class="empty-icon">🎥</div><h4>No recordings available</h4><p>Recordings are saved during proctoring sessions</p></div></td></tr>`;
            return;
        }

        tbody.innerHTML = recordings.map(r => `
            <tr>
                <td><strong>${escapeHtml(r.filename)}</strong></td>
                <td><span class="badge ${r.type === 'webcam' ? 'badge-info' : 'badge-warning'}">${capitalize(r.type)}</span></td>
                <td>${r.size_formatted}</td>
                <td class="mono">${r.created_at}</td>
                <td><a href="${API_BASE}/api/recordings/${encodeURIComponent(r.filename)}" class="btn btn-sm" download>↓ Download</a></td>
            </tr>
        `).join('');
    }


    // ─────────────────────────────────────────────
    // Sessions
    // ─────────────────────────────────────────────
    async function loadSessions() {
        const session = await API.getCurrentSession();
        const infoEl = $('#session-current-info');
        const startBtn = $('#btn-start-session');
        const stopBtn = $('#btn-stop-session');

        if (session && session.active) {
            infoEl.innerHTML = `
                <div style="display:flex; align-items:center; gap:var(--space-md); margin-bottom:var(--space-md)">
                    <div class="session-dot"></div>
                    <strong>Active Session</strong>
                    <span class="badge badge-success">LIVE</span>
                </div>
                <div class="stats-grid" style="margin-bottom:0">
                    <div class="stat-card">
                        <span class="stat-label">Student</span>
                        <span class="stat-value" style="font-size:18px">${escapeHtml(session.student?.name || '—')}</span>
                        <span class="stat-detail">ID: ${escapeHtml(session.student?.id || '—')}</span>
                    </div>
                    <div class="stat-card">
                        <span class="stat-label">Exam</span>
                        <span class="stat-value" style="font-size:18px">${escapeHtml(session.student?.exam || '—')}</span>
                        <span class="stat-detail">${escapeHtml(session.student?.course || '—')}</span>
                    </div>
                    <div class="stat-card accent">
                        <span class="stat-label">Duration</span>
                        <span class="stat-value" style="font-size:18px; font-family:var(--font-mono)">${session.duration || '00:00:00'}</span>
                    </div>
                    <div class="stat-card danger">
                        <span class="stat-label">Violations</span>
                        <span class="stat-value" style="font-size:18px">${session.violation_count || 0}</span>
                    </div>
                    <div class="stat-card info">
                        <span class="stat-label">Alerts</span>
                        <span class="stat-value" style="font-size:18px">${session.alert_count || 0}</span>
                    </div>
                    <div class="stat-card">
                        <span class="stat-label">Started At</span>
                        <span class="stat-value" style="font-size:14px; font-family:var(--font-mono)">${session.started_at || '—'}</span>
                    </div>
                </div>`;
            startBtn.disabled = true;
            stopBtn.disabled = false;
        } else {
            infoEl.innerHTML = `
                <div class="empty-state">
                    <div class="empty-icon">🎓</div>
                    <h4>No active session</h4>
                    <p>Start a new session below to begin proctoring</p>
                </div>`;
            startBtn.disabled = false;
            stopBtn.disabled = true;
        }
    }


    // ─────────────────────────────────────────────
    // Settings
    // ─────────────────────────────────────────────
    let currentConfig = null;

    async function loadSettings() {
        const config = await API.getConfig();
        if (!config) {
            $('#settings-form-area').innerHTML = `<div class="empty-state"><h4>Unable to load configuration</h4><p>Check that the backend is running</p></div>`;
            return;
        }
        currentConfig = config;
        renderSettingsForm(config);
    }

    function renderSettingsForm(config) {
        const area = $('#settings-form-area');
        const d = config.detection || {};
        const v = config.video || {};
        const s = config.screen || {};
        const l = config.logging || {};
        const am = d.audio_monitoring || {};

        area.innerHTML = `
            <div class="config-section">
                <div class="config-section-title">Video Settings</div>
                <div class="form-row">
                    <div class="form-group">
                        <label class="form-label">Video Source</label>
                        <input class="form-input" type="number" data-path="video.source" value="${v.source ?? 0}">
                        <div class="form-help">0 = default webcam</div>
                    </div>
                    <div class="form-group">
                        <label class="form-label">FPS</label>
                        <input class="form-input" type="number" data-path="video.fps" value="${v.fps ?? 30}">
                    </div>
                </div>
                <div class="form-row">
                    <div class="form-group">
                        <label class="form-label">Resolution Width</label>
                        <input class="form-input" type="number" data-path="video.resolution.0" value="${(v.resolution || [1280])[0]}">
                    </div>
                    <div class="form-group">
                        <label class="form-label">Resolution Height</label>
                        <input class="form-input" type="number" data-path="video.resolution.1" value="${(v.resolution || [0,720])[1]}">
                    </div>
                </div>
            </div>

            <div class="config-section">
                <div class="config-section-title">Screen Recording</div>
                <div class="form-row">
                    <div class="form-group">
                        <label class="form-label">Enable Screen Recording</label>
                        <label class="toggle-switch">
                            <input type="checkbox" data-path="screen.recording" ${s.recording ? 'checked' : ''}>
                            <span class="toggle-slider"></span>
                        </label>
                    </div>
                    <div class="form-group">
                        <label class="form-label">Screen FPS</label>
                        <input class="form-input" type="number" data-path="screen.fps" value="${s.fps ?? 15}">
                    </div>
                </div>
            </div>

            <div class="config-section">
                <div class="config-section-title">Face Detection</div>
                <div class="form-row">
                    <div class="form-group">
                        <label class="form-label">Detection Interval <small>(frames)</small></label>
                        <input class="form-input" type="number" data-path="detection.face.detection_interval" value="${(d.face || {}).detection_interval ?? 5}">
                    </div>
                    <div class="form-group">
                        <label class="form-label">Min Confidence</label>
                        <input class="form-input" type="number" step="0.1" data-path="detection.face.min_confidence" value="${(d.face || {}).min_confidence ?? 0.8}">
                    </div>
                </div>
            </div>

            <div class="config-section">
                <div class="config-section-title">Eye Tracking</div>
                <div class="form-row">
                    <div class="form-group">
                        <label class="form-label">Gaze Threshold <small>(seconds)</small></label>
                        <input class="form-input" type="number" data-path="detection.eyes.gaze_threshold" value="${(d.eyes || {}).gaze_threshold ?? 2}">
                    </div>
                    <div class="form-group">
                        <label class="form-label">Blink Threshold <small>(EAR)</small></label>
                        <input class="form-input" type="number" step="0.1" data-path="detection.eyes.blink_threshold" value="${(d.eyes || {}).blink_threshold ?? 0.3}">
                    </div>
                </div>
                <div class="form-row">
                    <div class="form-group">
                        <label class="form-label">Gaze Sensitivity <small>(pixels)</small></label>
                        <input class="form-input" type="number" data-path="detection.eyes.gaze_sensitivity" value="${(d.eyes || {}).gaze_sensitivity ?? 15}">
                    </div>
                    <div class="form-group">
                        <label class="form-label">Consecutive Frames</label>
                        <input class="form-input" type="number" data-path="detection.eyes.consecutive_frames" value="${(d.eyes || {}).consecutive_frames ?? 3}">
                    </div>
                </div>
            </div>

            <div class="config-section">
                <div class="config-section-title">Mouth & Multi-Face Detection</div>
                <div class="form-row">
                    <div class="form-group">
                        <label class="form-label">Mouth Movement Threshold <small>(frames)</small></label>
                        <input class="form-input" type="number" data-path="detection.mouth.movement_threshold" value="${(d.mouth || {}).movement_threshold ?? 3}">
                    </div>
                    <div class="form-group">
                        <label class="form-label">Multi-Face Alert Threshold <small>(frames)</small></label>
                        <input class="form-input" type="number" data-path="detection.multi_face.alert_threshold" value="${(d.multi_face || {}).alert_threshold ?? 5}">
                    </div>
                </div>
            </div>

            <div class="config-section">
                <div class="config-section-title">Object Detection</div>
                <div class="form-row">
                    <div class="form-group">
                        <label class="form-label">Min Confidence</label>
                        <input class="form-input" type="number" step="0.05" data-path="detection.objects.min_confidence" value="${(d.objects || {}).min_confidence ?? 0.65}">
                    </div>
                    <div class="form-group">
                        <label class="form-label">Detection Interval <small>(frames)</small></label>
                        <input class="form-input" type="number" data-path="detection.objects.detection_interval" value="${(d.objects || {}).detection_interval ?? 5}">
                    </div>
                </div>
                <div class="form-group">
                    <label class="form-label">Max FPS</label>
                    <input class="form-input" type="number" data-path="detection.objects.max_fps" value="${(d.objects || {}).max_fps ?? 5}" style="max-width:200px">
                </div>
            </div>

            <div class="config-section">
                <div class="config-section-title">Audio Monitoring</div>
                <div class="form-row">
                    <div class="form-group">
                        <label class="form-label">Enable Audio Monitoring</label>
                        <label class="toggle-switch">
                            <input type="checkbox" data-path="detection.audio_monitoring.enabled" ${am.enabled ? 'checked' : ''}>
                            <span class="toggle-slider"></span>
                        </label>
                    </div>
                    <div class="form-group">
                        <label class="form-label">Sample Rate</label>
                        <input class="form-input" type="number" data-path="detection.audio_monitoring.sample_rate" value="${am.sample_rate ?? 16000}">
                    </div>
                </div>
                <div class="form-row">
                    <div class="form-group">
                        <label class="form-label">Energy Threshold</label>
                        <input class="form-input" type="number" step="0.001" data-path="detection.audio_monitoring.energy_threshold" value="${am.energy_threshold ?? 0.001}">
                    </div>
                    <div class="form-group">
                        <label class="form-label">ZCR Threshold</label>
                        <input class="form-input" type="number" step="0.01" data-path="detection.audio_monitoring.zcr_threshold" value="${am.zcr_threshold ?? 0.35}">
                    </div>
                </div>
            </div>

            <div class="config-section">
                <div class="config-section-title">Logging & Alerts</div>
                <div class="form-row">
                    <div class="form-group">
                        <label class="form-label">Alert Cooldown <small>(seconds)</small></label>
                        <input class="form-input" type="number" data-path="logging.alert_cooldown" value="${l.alert_cooldown ?? 10}">
                    </div>
                    <div class="form-group">
                        <label class="form-label">Voice Alerts</label>
                        <label class="toggle-switch">
                            <input type="checkbox" data-path="logging.alert_system.voice_alerts" ${(l.alert_system || {}).voice_alerts ? 'checked' : ''}>
                            <span class="toggle-slider"></span>
                        </label>
                    </div>
                </div>
                <div class="form-row">
                    <div class="form-group">
                        <label class="form-label">Alert Volume <small>(0.0 – 1.0)</small></label>
                        <input class="form-input" type="number" step="0.1" min="0" max="1" data-path="logging.alert_system.alert_volume" value="${(l.alert_system || {}).alert_volume ?? 0.8}">
                    </div>
                    <div class="form-group">
                        <label class="form-label">Same Alert Cooldown <small>(seconds)</small></label>
                        <input class="form-input" type="number" data-path="logging.alert_system.cooldown" value="${(l.alert_system || {}).cooldown ?? 10}">
                    </div>
                </div>
            </div>
        `;
    }

    async function saveConfig() {
        if (!currentConfig) return;

        const config = JSON.parse(JSON.stringify(currentConfig));

        // Collect all values from form inputs
        $$('#settings-form-area [data-path]').forEach(input => {
            const path = input.dataset.path;
            const keys = path.split('.');
            let obj = config;
            for (let i = 0; i < keys.length - 1; i++) {
                const key = isNaN(keys[i]) ? keys[i] : parseInt(keys[i]);
                if (obj[key] === undefined) obj[key] = {};
                obj = obj[key];
            }
            const lastKey = isNaN(keys[keys.length - 1]) ? keys[keys.length - 1] : parseInt(keys[keys.length - 1]);

            if (input.type === 'checkbox') {
                obj[lastKey] = input.checked;
            } else if (input.type === 'number') {
                const val = input.value;
                obj[lastKey] = val.includes('.') ? parseFloat(val) : parseInt(val);
            } else {
                obj[lastKey] = input.value;
            }
        });

        const result = await API.updateConfig(config);
        if (result && !result.error) {
            currentConfig = config;
            showToast('Configuration saved successfully');
        } else {
            showToast('Failed to save configuration', 'error');
        }
    }


    // ─────────────────────────────────────────────
    // Helpers
    // ─────────────────────────────────────────────
    function capitalize(str) {
        if (!str) return '';
        return str.charAt(0).toUpperCase() + str.slice(1).toLowerCase();
    }

    function escapeHtml(str) {
        if (!str) return '';
        const div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    }

    function getAlertSeverity(type) {
        const critical = ['MULTIPLE_FACES', 'OBJECT_DETECTED', 'FORBIDDEN_OBJECT', 'OBJECT_DETECTION_ERROR', 'HIGH_CHEATING_PROBABILITY'];
        const warning =  ['FACE_DISAPPEARED', 'MOUTH_MOVEMENT', 'VOICE_DETECTED', 'SPEECH_VIOLATION', 'EYE_MOVEMENT'];
        if (critical.includes(type)) return 'critical';
        if (warning.includes(type)) return 'warning';
        return 'info';
    }

    function getViolationBadgeClass(type) {
        const map = {
            'FACE_DISAPPEARED': 'badge-danger',
            'MULTIPLE_FACES':   'badge-danger',
            'OBJECT_DETECTED':  'badge-danger',
            'MOUTH_MOVING':     'badge-warning',
            'GAZE_AWAY':        'badge-info'
        };
        return map[type] || 'badge-neutral';
    }

    function formatAlertTime(ts) {
        if (!ts) return '—';
        // Extract just time portion if full datetime
        const timePart = ts.includes(' ') ? ts.split(' ')[1] : ts;
        return timePart || ts;
    }


    // ─────────────────────────────────────────────
    // Exam Page
    // ─────────────────────────────────────────────
    let examPolling = null;

    async function loadExam() {
        await loadExamList();
        const status = await API.examStatus();
        if (status && status.running) {
            showExamRunning(status);
        } else {
            showExamSetup();
        }
    }

    async function loadExamList() {
        const exams = await API.getExams();
        if (!exams) return;

        // Populate dropdown
        const select = $('#exam-select');
        if (select) {
            const currentVal = select.value;
            select.innerHTML = '<option value="">— Select an exam —</option>' +
                exams.map(e => `<option value="${escapeHtml(e.id)}" data-name="${escapeHtml(e.name)}" data-course="${escapeHtml(e.course)}" data-duration="${e.duration_min}">${escapeHtml(e.name)} — ${escapeHtml(e.course)} (${e.duration_min} min)</option>`).join('');
            // Restore or auto-select first
            if (currentVal && [...select.options].some(o => o.value === currentVal)) {
                select.value = currentVal;
            } else if (exams.length > 0) {
                select.value = exams[0].id;
            }
            // Fire change to populate fields
            select.dispatchEvent(new Event('change'));
        }

        // Populate exam list in manage card
        const listEl = $('#exam-list');
        if (listEl) {
            if (exams.length === 0) {
                listEl.innerHTML = '<div style="color:var(--color-text-muted);font-size:13px;padding:var(--space-sm)">No exams configured. Add one above.</div>';
            } else {
                listEl.innerHTML = exams.map(e => `
                    <div style="display:flex;justify-content:space-between;align-items:center;padding:6px 8px;border-bottom:1px solid var(--color-border);font-size:13px">
                        <div><strong>${escapeHtml(e.name)}</strong> <span style="color:var(--color-text-muted)">• ${escapeHtml(e.course)} • ${e.duration_min} min</span></div>
                        <button class="btn btn-sm" style="color:var(--color-danger);padding:2px 8px;font-size:12px" data-delete-exam="${escapeHtml(e.id)}">×</button>
                    </div>
                `).join('');

                // Attach delete handlers
                listEl.querySelectorAll('[data-delete-exam]').forEach(btn => {
                    btn.addEventListener('click', async () => {
                        const examId = btn.dataset.deleteExam;
                        await API.deleteExam(examId);
                        showToast('Exam deleted');
                        await loadExamList();
                    });
                });
            }
        }
    }

    function showExamSetup() {
        const setupCard = $('#exam-setup-card');
        const liveArea = $('#exam-live-area');
        const startBtn = $('#btn-exam-start');
        const stopBtn = $('#btn-exam-stop');

        if (setupCard) setupCard.style.display = '';
        if (liveArea)  liveArea.style.display = 'none';
        if (startBtn)  startBtn.disabled = false;
        if (stopBtn)   stopBtn.disabled = true;

        // Stop video feed
        const feed = $('#exam-video-feed');
        if (feed) { feed.src = ''; feed.style.display = 'none'; }
        const placeholder = $('#exam-video-placeholder');
        if (placeholder) placeholder.style.display = '';
        const badge = $('#exam-live-badge');
        if (badge) badge.style.display = 'none';

        // Stop polling
        if (examPolling) { clearInterval(examPolling); examPolling = null; }
    }

    function showExamRunning(status) {
        const setupCard = $('#exam-setup-card');
        const liveArea = $('#exam-live-area');
        const startBtn = $('#btn-exam-start');
        const stopBtn = $('#btn-exam-stop');

        if (setupCard) setupCard.style.display = 'none';
        if (liveArea)  liveArea.style.display = '';
        if (startBtn)  startBtn.disabled = true;
        if (stopBtn)   stopBtn.disabled = false;

        // Start video feed
        const feed = $('#exam-video-feed');
        if (feed) {
            feed.src = `${API_BASE}/api/exam/video_feed`;
            feed.style.display = 'block';
        }
        const placeholder = $('#exam-video-placeholder');
        if (placeholder) placeholder.style.display = 'none';
        const badge = $('#exam-live-badge');
        if (badge) badge.style.display = '';

        // Update session info
        if (status && status.session) {
            const s = status.session;
            const student = s.student || {};
            $('#exam-info-student').textContent = student.name || '—';
            $('#exam-info-exam').textContent = student.exam || '—';
            $('#exam-info-duration').textContent = s.duration || '00:00:00';
            $('#exam-info-violations').textContent = s.violation_count || '0';
        }

        // Start polling stats
        if (!examPolling) {
            examPolling = setInterval(updateExamStats, 1500);
            updateExamStats();
        }
    }

    async function updateExamStats() {
        const [stats, status] = await Promise.all([
            API.getStats(),
            API.examStatus()
        ]);

        if (status) {
            if (!status.running) {
                showExamSetup();
                return;
            }
            const s = status.session || {};
            $('#exam-info-duration').textContent = s.duration || '00:00:00';
            $('#exam-info-violations').textContent = s.violation_count || '0';
        }

        if (stats) {
            const prob = stats.cheating_probability || 0;

            // Update gauge
            const circle = $('#exam-gauge-circle');
            const circumference = 2 * Math.PI * 80;
            const offset = circumference - (prob / 100) * circumference;
            if (circle) {
                circle.style.strokeDasharray = circumference;
                circle.style.strokeDashoffset = offset;
                circle.classList.remove('low', 'medium', 'high');
                circle.classList.add(prob < 30 ? 'low' : prob < 60 ? 'medium' : 'high');
            }
            const gNum = $('#exam-gauge-number');
            if (gNum) gNum.textContent = prob;
            const gLabel = $('#exam-gauge-label');
            if (gLabel) {
                gLabel.textContent = prob < 30 ? 'Low Risk' : prob < 60 ? 'Medium Risk' : 'High Risk';
                gLabel.style.color = prob < 30 ? 'var(--color-success)' : prob < 60 ? 'var(--color-warning)' : 'var(--color-danger)';
            }

            // Reasons
            const reasonsEl = $('#exam-reasons');
            const reasons = stats.cheating_reasons || [];
            if (reasonsEl) {
                reasonsEl.innerHTML = (reasons.length > 0 && prob >= 30)
                    ? reasons.map(r => `<li>${escapeHtml(r)}</li>`).join('')
                    : '';
            }

            // Detection badges
            function detBadge(val, okText, errText, isInverted) {
                const isOk = isInverted ? !val : val;
                return `<span class="badge ${isOk ? 'badge-success' : 'badge-danger'}">${isOk ? okText : errText}</span>`;
            }
            const d = (id, html) => { const el = $(id); if (el) el.innerHTML = html; };
            d('#exam-det-face', detBadge(stats.face_detected, 'Present', 'Absent', false));
            d('#exam-det-gaze', `<span class="badge ${(stats.gaze_direction||'').toLowerCase()==='center' ? 'badge-success' : 'badge-warning'}">${capitalize(stats.gaze_direction||'Center')}</span>`);
            d('#exam-det-eyes', detBadge(stats.eyes_open, 'Open', 'Closed', false));
            d('#exam-det-mouth', detBadge(stats.mouth_moving, 'Still', 'Moving', true));
            d('#exam-det-objects', detBadge(stats.objects_detected, 'Clear', 'Detected!', true));
            d('#exam-det-multi', detBadge(stats.multiple_faces, 'Single', 'Multiple!', true));
        }
    }


    // ─────────────────────────────────────────────
    // Polling
    // ─────────────────────────────────────────────
    function startPolling() {
        stopPolling();
        pollTimer = setInterval(() => {
            if (currentPage === 'dashboard' || currentPage === 'monitoring') {
                loadPageData(currentPage);
            }
            // Exam page has its own polling via examPolling
        }, POLL_INTERVAL);
    }

    function stopPolling() {
        if (pollTimer) {
            clearInterval(pollTimer);
            pollTimer = null;
        }
    }


    // ─────────────────────────────────────────────
    // Event Bindings
    // ─────────────────────────────────────────────
    function initEvents() {
        // Nav clicks
        $$('.nav-item').forEach(item => {
            item.addEventListener('click', () => {
                const page = item.dataset.page;
                if (page) navigateTo(page);
            });
        });

        // Buttons with data-page (e.g. "View all" buttons)
        $$('[data-page]').forEach(el => {
            if (!el.classList.contains('nav-item')) {
                el.addEventListener('click', () => navigateTo(el.dataset.page));
            }
        });

        // Refresh button
        $('#btn-refresh')?.addEventListener('click', () => {
            loadPageData(currentPage);
            showToast('Data refreshed');
        });

        // Session form
        $('#session-form')?.addEventListener('submit', async (e) => {
            e.preventDefault();
            const data = {
                student_id:   $('#inp-student-id').value,
                student_name: $('#inp-student-name').value,
                exam_name:    $('#inp-exam-name').value,
                course:       $('#inp-course').value
            };
            const result = await API.startSession(data);
            if (result && !result.error) {
                showToast('Session started successfully');
                loadSessions();
            } else {
                showToast(result?.error || 'Failed to start session', 'error');
            }
        });

        // Stop session
        $('#btn-stop-session')?.addEventListener('click', async () => {
            const result = await API.stopSession();
            if (result && !result.error) {
                showToast('Session stopped');
                loadSessions();
            } else {
                showToast(result?.error || 'Failed to stop session', 'error');
            }
        });

        // Exam start
        $('#btn-exam-start')?.addEventListener('click', async () => {
            const data = {
                student_id:   $('#exam-student-id')?.value || 'STUDENT_001',
                student_name: $('#exam-student-name')?.value || 'Unknown',
                exam_name:    $('#exam-name')?.value || 'Examination',
                course:       $('#exam-course')?.value || 'N/A'
            };
            const result = await API.startExam(data);
            if (result && !result.error) {
                showToast('Exam started — camera active');
                const status = await API.examStatus();
                showExamRunning(status);
            } else {
                showToast(result?.error || 'Failed to start exam', 'error');
            }
        });

        // Exam stop
        $('#btn-exam-stop')?.addEventListener('click', async () => {
            const result = await API.stopExam();
            if (result && !result.error) {
                showToast(`Exam ended — ${result.total_violations || 0} violations recorded`);
                showExamSetup();
            } else {
                showToast(result?.error || 'Failed to stop exam', 'error');
            }
        });

        // Exam selector change
        $('#exam-select')?.addEventListener('change', (e) => {
            const opt = e.target.selectedOptions[0];
            if (opt && opt.value) {
                $('#exam-name').value = opt.dataset.name || '';
                $('#exam-course').value = opt.dataset.course || '';
            } else {
                $('#exam-name').value = '';
                $('#exam-course').value = '';
            }
        });

        // Add exam
        $('#btn-add-exam')?.addEventListener('click', async () => {
            const name = $('#new-exam-name')?.value?.trim();
            const course = $('#new-exam-course')?.value?.trim();
            const duration = parseInt($('#new-exam-duration')?.value) || 60;
            if (!name) { showToast('Exam name is required', 'error'); return; }
            const result = await API.addExam({ name, course, duration_min: duration });
            if (result && !result.error) {
                showToast('Exam added');
                $('#new-exam-name').value = '';
                $('#new-exam-course').value = '';
                $('#new-exam-duration').value = '60';
                await loadExamList();
            } else {
                showToast(result?.error || 'Failed to add exam', 'error');
            }
        });

        // Save config
        $('#btn-save-config')?.addEventListener('click', saveConfig);

        // Violation filter
        $('#violation-filter')?.addEventListener('change', loadViolations);
    }


    // ─────────────────────────────────────────────
    // Initialize
    // ─────────────────────────────────────────────
    function init() {
        updateClock();
        setInterval(updateClock, 1000);
        initEvents();
        navigateTo('exam');
        startPolling();
    }

    // Boot
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

})();
