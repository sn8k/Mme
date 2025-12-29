/* File Version: 0.30.0 */
(function (window, document, fetch) {
    'use strict';

    const context = window.motionFrontendContext || {};
    const state = {
        cameraId: context.cameraId || null,
        audioId: context.audioId || null,
        pollingHandle: null,
        mjpegUrl: null,
        pendingRequest: null,
        isDirty: false,
        initialValues: {},
        streamingCameras: new Set(),  // Track which cameras are streaming
        usePolling: true,  // Whether to use polling mode (false = MJPEG streaming)
        userOverridePreviewCount: false,  // Track if user manually changed preview count
        visibleOverlays: new Set(),  // Track which camera overlays are visible
        cameraStats: {},  // Store stats per camera { cameraId: { fps, width, height, bandwidth_kbps } }
        statsPollingHandle: null,  // Handle for stats polling
        audioDevices: context.audioDevices || []  // Configured audio devices
    };

    function buildUrl(path) {
        const base = context.basePath || '';
        return `${base}${path}`;
    }

    function handleResponse(response) {
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        return response.json();
    }

    function apiGet(path) {
        return fetch(buildUrl(path), {
            credentials: 'include'
        }).then(handleResponse);
    }

    function apiPost(path, payload) {
        return fetch(buildUrl(path), {
            method: 'POST',
            credentials: 'include',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        }).then(handleResponse);
    }

    function apiPut(path, payload) {
        return fetch(buildUrl(path), {
            method: 'PUT',
            credentials: 'include',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        }).then(handleResponse);
    }

    function apiDelete(path, payload) {
        const options = {
            method: 'DELETE',
            credentials: 'include'
        };
        if (payload) {
            options.headers = { 'Content-Type': 'application/json' };
            options.body = JSON.stringify(payload);
        }
        return fetch(buildUrl(path), options).then(handleResponse);
    }

    /**
     * Format bandwidth for display.
     * @param {number} kbps - Bandwidth in kilobits per second.
     * @returns {string} Formatted bandwidth string.
     */
    function formatBandwidth(kbps) {
        if (kbps >= 1000) {
            return (kbps / 1000).toFixed(1) + ' Mb/s';
        }
        return kbps.toFixed(0) + ' Kb/s';
    }

    /**
     * Poll MJPEG stats from server and update state.
     */
    async function pollMJPEGStats() {
        try {
            const data = await apiGet('/api/mjpeg/');
            if (data && data.cameras) {
                // Update stats for each camera
                for (const [cameraId, info] of Object.entries(data.cameras)) {
                    if (info.exists && info.is_running) {
                        state.cameraStats[cameraId] = {
                            real_fps: info.real_fps || 0,
                            width: info.width || 0,
                            height: info.height || 0,
                            bandwidth_kbps: info.bandwidth_kbps || 0,
                            frame_count: info.frame_count || 0
                        };
                    }
                }
                // Refresh overlays if any are visible
                if (state.visibleOverlays.size > 0) {
                    updatePreviewGrid();
                }
            }
        } catch (error) {
            // Silent fail - stats polling is non-critical
            console.debug('Stats polling failed:', error);
        }
    }

    /**
     * Start polling for camera stats.
     */
    function startStatsPolling() {
        if (state.statsPollingHandle) {
            clearInterval(state.statsPollingHandle);
        }
        // Poll every 1 second
        state.statsPollingHandle = setInterval(pollMJPEGStats, 1000);
        // Initial poll
        pollMJPEGStats();
    }

    /**
     * Stop polling for camera stats.
     */
    function stopStatsPolling() {
        if (state.statsPollingHandle) {
            clearInterval(state.statsPollingHandle);
            state.statsPollingHandle = null;
        }
    }

    // ========== Meeting API Functions ==========
    
    /**
     * Get Meeting service status.
     */
    async function getMeetingStatus() {
        try {
            return await apiGet('/api/meeting/');
        } catch (error) {
            console.error('Failed to get Meeting status:', error);
            return null;
        }
    }
    
    /**
     * Control Meeting service (start/stop/heartbeat).
     */
    async function controlMeeting(action) {
        try {
            const result = await apiPost('/api/meeting/', { action: action });
            updateMeetingStatusLabel(result);
            return result;
        } catch (error) {
            console.error(`Failed to ${action} Meeting service:`, error);
            motionFrontendUI.showToast(`Erreur Meeting: ${error.message}`, 'error');
            return null;
        }
    }
    
    /**
     * Update Meeting status label in UI.
     */
    function updateMeetingStatusLabel(data) {
        const statusLabel = document.getElementById('meetingStatusLabel');
        if (!statusLabel) return;
        
        if (!data || !data.service) {
            statusLabel.textContent = '--';
            statusLabel.className = 'meeting-status';
            return;
        }
        
        const service = data.service;
        if (!service.is_configured) {
            statusLabel.textContent = 'Non configuré';
            statusLabel.className = 'meeting-status stopped';
        } else if (service.is_running) {
            if (service.last_heartbeat_success) {
                statusLabel.textContent = `✓ Connecté (${service.last_heartbeat ? new Date(service.last_heartbeat).toLocaleTimeString() : '--'})`;
                statusLabel.className = 'meeting-status connected';
            } else if (service.last_error) {
                statusLabel.textContent = `⚠ Erreur: ${service.last_error}`;
                statusLabel.className = 'meeting-status error';
            } else {
                statusLabel.textContent = 'Connexion en cours...';
                statusLabel.className = 'meeting-status';
            }
        } else {
            statusLabel.textContent = 'Démarrage...';
            statusLabel.className = 'meeting-status';
        }
    }
    
    /**
     * Poll Meeting status periodically.
     */
    let lastMeetingData = null;
    async function pollMeetingStatus() {
        const data = await getMeetingStatus();
        if (data) {
            lastMeetingData = data;
            updateMeetingStatusLabel(data);
        } else if (lastMeetingData) {
            // Keep showing last known status if request failed
            updateMeetingStatusLabel(lastMeetingData);
        }
    }
    
    /**
     * Initialize Meeting controls - auto-start service if configured.
     */
    function initMeetingControls() {
        // Poll Meeting status every 10 seconds
        setInterval(pollMeetingStatus, 10000);
        // Initial poll and auto-start
        pollMeetingStatus();
        // Auto-start the service (will only start if configured)
        controlMeeting('start');
    }

    function loadMainConfig() {
        motionFrontendUI.setStatus('Loading preferences...');
        return apiGet('/api/config/main/');
    }

    function loadCameraConfig(cameraId) {
        if (!cameraId) {
            return Promise.resolve(null);
        }
        return apiGet(`/api/config/camera/${cameraId}/`);
    }

    function loadCameraConfigSections(cameraId) {
        if (!cameraId) {
            return Promise.resolve({ sections: [] });
        }
        return apiGet(`/api/config/camera/${cameraId}/sections/`);
    }

    function populateInputs(configMap) {
        if (!configMap) {
            return;
        }
        Object.entries(configMap).forEach(([key, value]) => {
            const entry = document.getElementById(`${key}Entry`) ||
                document.getElementById(`${key}Select`) ||
                document.getElementById(`${key}Switch`) ||
                document.getElementById(`${key}Slider`);
            if (!entry) {
                return;
            }
            if (entry.type === 'checkbox') {
                entry.checked = Boolean(value);
            } else if (entry.type === 'range' || entry.type === 'number') {
                entry.value = Number(value);
                entry.dispatchEvent(new Event('input'));
            } else {
                entry.value = value;
            }
        });
    }

    function evaluateDepends(row) {
        const depends = row.dataset.depends;
        if (!depends) {
            return true;
        }
        const tokens = depends.split(/\s+/);
        return tokens.every((token) => {
            const isNegated = token.startsWith('!');
            let key = isNegated ? token.substring(1) : token;
            let expectedValue = null;
            
            // Check for key=value syntax (e.g., overlayLeftText=custom)
            if (key.includes('=')) {
                const parts = key.split('=');
                key = parts[0];
                expectedValue = parts[1];
            }
            
            const checkbox = document.getElementById(`${key}Switch`);
            const input = document.getElementById(`${key}Entry`) || document.getElementById(`${key}Select`);
            let value = false;
            
            if (expectedValue !== null) {
                // Compare against expected value
                if (input) {
                    value = input.value === expectedValue;
                }
            } else {
                // Boolean check (original behavior)
                if (checkbox) {
                    value = checkbox.checked;
                } else if (input) {
                    value = Boolean(input.value);
                }
            }
            return isNegated ? !value : value;
        });
    }

    function applyDependVisibility() {
        document.querySelectorAll('[data-depends]').forEach((row) => {
            row.classList.toggle('hidden', !evaluateDepends(row));
        });
    }

    function captureInitialValues() {
        state.initialValues = {};
        document.querySelectorAll('[data-config-id]').forEach((row) => {
            const id = row.dataset.configId;
            const input = document.getElementById(`${id}Entry`) ||
                document.getElementById(`${id}Select`) ||
                document.getElementById(`${id}Switch`) ||
                document.getElementById(`${id}Slider`);
            if (!input) return;
            if (input.type === 'checkbox') {
                state.initialValues[id] = input.checked;
            } else {
                state.initialValues[id] = input.value;
            }
        });
        state.isDirty = false;
        updateSaveButton();
    }

    function checkDirty() {
        let dirty = false;
        document.querySelectorAll('[data-config-id]').forEach((row) => {
            if (row.classList.contains('hidden')) return;
            const id = row.dataset.configId;
            const input = document.getElementById(`${id}Entry`) ||
                document.getElementById(`${id}Select`) ||
                document.getElementById(`${id}Switch`) ||
                document.getElementById(`${id}Slider`);
            if (!input) return;
            const initial = state.initialValues[id];
            let current;
            if (input.type === 'checkbox') {
                current = input.checked;
            } else {
                current = input.value;
            }
            if (String(initial) !== String(current)) {
                dirty = true;
            }
        });
        state.isDirty = dirty;
        updateSaveButton();
    }

    function updateSaveButton() {
        const btn = document.getElementById('saveConfigBtn');
        if (btn) {
            btn.classList.toggle('hidden', !state.isDirty);
        }
    }

    function collectChanges(containerSelector) {
        const data = {};
        document.querySelectorAll(`${containerSelector} [data-config-id]`).forEach((row) => {
            if (row.classList.contains('hidden')) {
                return;
            }
            const id = row.dataset.configId;
            const input = document.getElementById(`${id}Entry`) ||
                document.getElementById(`${id}Select`) ||
                document.getElementById(`${id}Switch`) ||
                document.getElementById(`${id}Slider`);
            if (!input) {
                return;
            }
            if (input.type === 'checkbox') {
                data[id] = input.checked;
            } else {
                data[id] = input.value;
            }
        });
        return data;
    }

    function pushConfigs(payload, cameraId = null) {
        const url = cameraId ? `/api/config/camera/${cameraId}/` : '/api/config/main/';
        motionFrontendUI.setStatus('Saving...');
        return apiPost(url, payload)
            .then((response) => {
                motionFrontendUI.showToast('Configuration saved', 'success');
                
                // Handle RTSP auto-start/stop response
                if (cameraId && response) {
                    if (response.rtsp_action === 'starting') {
                        if (response.rtsp_started) {
                            updateRTSPUI(cameraId, {
                                is_running: true,
                                rtsp_url: response.rtsp_url,
                                has_audio: response.rtsp_url && response.rtsp_url.includes('audio'),
                                error: response.rtsp_error
                            });
                            motionFrontendUI.showToast(_('RTSP stream started'), 'success');
                        } else {
                            updateRTSPUI(cameraId, {
                                is_running: false,
                                error: response.rtsp_error || _('Failed to start RTSP stream')
                            });
                            motionFrontendUI.showToast(_('RTSP error: %s').replace('%s', response.rtsp_error || 'Unknown'), 'error');
                        }
                    } else if (response.rtsp_action === 'stopping') {
                        updateRTSPUI(cameraId, { is_running: false });
                        motionFrontendUI.showToast(_('RTSP stream stopped'), 'success');
                    }
                }
                
                return response;
            })
            .catch((error) => {
                motionFrontendUI.showToast(`Save failed: ${error.message}`, 'error');
                throw error;
            })
            .finally(() => motionFrontendUI.setStatus('Ready'));
    }

    function bindButtons() {
        const applyBtn = document.getElementById('applyButton');
        if (applyBtn) {
            applyBtn.addEventListener('click', () => {
                const mainPayload = collectChanges('#configColumns');
                const tasks = [pushConfigs(mainPayload)];
                if (state.cameraId) {
                    tasks.push(pushConfigs(collectChanges('#cameraConfigColumns'), state.cameraId));
                }
                Promise.all(tasks)
                    .then(() => captureInitialValues())
                    .catch(() => { /* handled in push */ });
            });
        }

        const saveConfigBtn = document.getElementById('saveConfigBtn');
        if (saveConfigBtn) {
            saveConfigBtn.addEventListener('click', () => {
                const mainPayload = collectChanges('#configColumns');
                const tasks = [pushConfigs(mainPayload)];
                if (state.cameraId) {
                    tasks.push(pushConfigs(collectChanges('#cameraConfigColumns'), state.cameraId));
                }
                Promise.all(tasks)
                    .then(() => captureInitialValues())
                    .catch(() => { /* handled in push */ });
            });
        }

        const cameraSelect = document.getElementById('cameraSelect');
        if (cameraSelect) {
            cameraSelect.addEventListener('change', () => {
                state.cameraId = cameraSelect.value || null;
                refreshCameraConfig();
                refreshFrame();
                // Update remove button state based on selection
                updateRemoveCameraButtonState();
            });
        }

        const updateButton = document.getElementById('updateButton');
        if (updateButton) {
            updateButton.addEventListener('click', () => triggerUpdate());
        }

        // Add camera button handler
        const addCameraButton = document.getElementById('addCameraButton');
        if (addCameraButton) {
            addCameraButton.addEventListener('click', () => showAddCameraDialog());
        }

        // Remove camera button handler
        const remCameraButton = document.getElementById('remCameraButton');
        if (remCameraButton) {
            remCameraButton.addEventListener('click', () => {
                if (state.cameraId) {
                    deleteCamera(state.cameraId);
                }
            });
        }

        // Preview count change listener
        const previewCountSelect = document.getElementById('previewCountSelect');
        if (previewCountSelect) {
            previewCountSelect.addEventListener('change', () => {
                state.userOverridePreviewCount = true;  // User manually changed preview count
                updatePreviewGrid();
            });
        }

        document.querySelectorAll('input, select').forEach((input) => {
            input.addEventListener('change', () => {
                applyDependVisibility();
                checkDirty();
                // Update preview grid if previewCount changed
                if (input.id === 'previewCountSelect') {
                    updatePreviewGrid();
                }
            });
            input.addEventListener('input', checkDirty);
        });
    }

    function refreshCameraConfig() {
        const cameraConfigContainer = document.getElementById('cameraConfigColumns');
        if (!cameraConfigContainer) return;

        if (!state.cameraId) {
            cameraConfigContainer.innerHTML = `
                <div class="no-camera-selected" id="noCameraSelected">
                    <p>Sélectionnez une caméra pour afficher sa configuration.</p>
                </div>
            `;
            return;
        }

        motionFrontendUI.setStatus('Loading camera configuration...');
        loadCameraConfigSections(state.cameraId)
            .then((data) => {
                const sections = data.sections || [];
                renderCameraConfigSections(cameraConfigContainer, sections);
                applyDependVisibility();
                captureInitialValues();
                bindDynamicInputs();
            })
            .catch((error) => {
                motionFrontendUI.showToast(`Camera config error: ${error.message}`, 'error');
            })
            .finally(() => motionFrontendUI.setStatus('Ready'));
    }

    function renderCameraConfigSections(container, sections) {
        const cameraName = getCameraName(state.cameraId);
        
        let html = `
            <div class="camera-config-header">
                <h3>Configuration caméra: ${escapeHtml(cameraName)}</h3>
            </div>
        `;

        for (const section of sections) {
            html += `
                <section class="settings-section camera-config-section collapsed" data-section="${section.slug}">
                    <header class="settings-section-title">
                        <button class="minimize" aria-expanded="false"></button>
                        <h2>${escapeHtml(section.title)}</h2>
                    </header>
                    <table class="settings" style="display: none;">
                        ${renderConfigItems(section.configs || [])}
                    </table>
                </section>
            `;
        }

        container.innerHTML = html;
        
        // Rebind minimize buttons with full accordion behavior
        bindAccordionButtons(container);
    }

    /**
     * Bind accordion behavior to minimize buttons within a container.
     * @param {HTMLElement} container - The container to search for .minimize buttons
     */
    function bindAccordionButtons(container) {
        container.querySelectorAll('.settings-section-title .minimize').forEach((btn) => {
            btn.addEventListener('click', () => {
                btn.classList.toggle('open');
                const expanded = btn.classList.contains('open');
                btn.setAttribute('aria-expanded', expanded.toString());
                const section = btn.closest('.settings-section');
                if (section) {
                    section.classList.toggle('collapsed', !expanded);
                    const table = section.querySelector('.settings');
                    if (table) {
                        table.style.display = expanded ? '' : 'none';
                    }
                }
            });
        });
    }

    function renderConfigItems(configs) {
        return configs.map(config => renderConfigItem(config)).join('');
    }

    function renderConfigItem(config) {
        if (config.type === 'separator') {
            return `
                <tr class="settings-item settings-separator">
                    <td colspan="2"><h4 class="settings-section-subtitle">${escapeHtml(config.label || '')}</h4></td>
                </tr>
            `;
        }

        const dataAttrs = [];
        if (config.depends) dataAttrs.push(`data-depends="${config.depends}"`);
        if (config.validate) dataAttrs.push(`data-validate="${config.validate}"`);

        let controlHtml = '';
        
        switch (config.type) {
            case 'str':
            case 'pwd':
            case 'number':
                const inputType = config.type === 'pwd' ? 'password' : (config.type === 'number' ? 'number' : 'text');
                const onchangeAttr = config.onchange ? `onchange="${config.onchange}" oninput="${config.onchange}"` : '';
                controlHtml = `
                    <input id="${config.id}Entry" name="${config.id}" class="styled"
                        type="${inputType}" value="${escapeHtml(String(config.value || ''))}"
                        ${config.placeholder ? `placeholder="${escapeHtml(config.placeholder)}"` : ''}
                        ${config.min !== undefined ? `min="${config.min}"` : ''}
                        ${config.max !== undefined ? `max="${config.max}"` : ''}
                        ${config.readonly ? 'readonly' : ''}
                        ${onchangeAttr}
                        autocomplete="off">
                `;
                break;
            
            case 'range':
                controlHtml = `
                    <div class="range-field">
                        <input id="${config.id}Slider" type="range" name="${config.id}" class="styled"
                            value="${config.value || 0}"
                            ${config.min !== undefined ? `min="${config.min}"` : ''}
                            ${config.max !== undefined ? `max="${config.max}"` : ''}>
                        <span class="range-value" data-target="${config.id}Slider">${config.value || 0}</span>
                    </div>
                `;
                break;
            
            case 'bool':
                controlHtml = `
                    <label class="switch">
                        <input type="checkbox" id="${config.id}Switch" name="${config.id}" ${config.value ? 'checked' : ''}>
                        <span class="slider"></span>
                    </label>
                `;
                break;
            
            case 'choices':
                const options = (config.choices || []).map(choice => 
                    `<option value="${escapeHtml(choice.value)}" ${choice.value === config.value ? 'selected' : ''}>${escapeHtml(choice.label || choice.value)}</option>`
                ).join('');
                controlHtml = `<select id="${config.id}Select" name="${config.id}" class="styled">${options}</select>`;
                break;
            
            case 'html':
                controlHtml = `<div id="${config.id}Html" class="embedded-html">${config.html || ''}</div>`;
                break;
            
            default:
                controlHtml = '<span class="placeholder">Unsupported control</span>';
        }

        return `
            <tr class="settings-item" data-config-id="${config.id}" data-type="${config.type}" ${dataAttrs.join(' ')}>
                <td class="settings-label">
                    <label for="${config.id}Entry">${escapeHtml(config.label || config.id)}</label>
                </td>
                <td class="settings-control">
                    ${controlHtml}
                    ${config.unit ? `<span class="unit">${escapeHtml(config.unit)}</span>` : ''}
                </td>
            </tr>
        `;
    }

    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    function getCameraName(cameraId) {
        const cameras = context.cameras || [];
        const camera = cameras.find(c => c.id === cameraId);
        return camera ? camera.name : `Camera ${cameraId}`;
    }

    function bindDynamicInputs() {
        document.querySelectorAll('#cameraConfigColumns input, #cameraConfigColumns select').forEach((input) => {
            input.addEventListener('change', () => {
                applyDependVisibility();
                checkDirty();
            });
            input.addEventListener('input', checkDirty);
            
            // Handle range slider value display
            if (input.type === 'range') {
                const valueSpan = document.querySelector(`[data-target="${input.id}"]`);
                if (valueSpan) {
                    input.addEventListener('input', () => {
                        valueSpan.textContent = input.value;
                    });
                }
            }
        });
    }

    function loadAllConfigs() {
        Promise.all([loadMainConfig(), loadCameraConfig(state.cameraId)])
            .then(([mainConfig, cameraConfig]) => {
                populateInputs(mainConfig);
                populateInputs(cameraConfig);
                applyDependVisibility();
                captureInitialValues();
                updatePreviewGrid();
            })
            .catch((error) => {
                motionFrontendUI.showToast(`Failed to load configuration: ${error.message}`, 'error');
            })
            .finally(() => motionFrontendUI.setStatus('Ready'));
    }

    function updatePreviewGrid() {
        const previewCountSelect = document.getElementById('previewCountSelect');
        const previewGrid = document.getElementById('previewGrid');
        const noCameraMessage = document.getElementById('noCameraMessage');
        if (!previewGrid) return;
        
        const cameras = context.cameras || [];
        
        // Show "no camera configured" message if no cameras
        if (cameras.length === 0) {
            previewGrid.classList.add('hidden');
            if (noCameraMessage) {
                noCameraMessage.classList.remove('hidden');
                noCameraMessage.innerHTML = `<p>Aucune caméra configurée. Cliquez sur <strong>+</strong> pour ajouter une caméra.</p>`;
            }
            return;
        } else {
            previewGrid.classList.remove('hidden');
            if (noCameraMessage) {
                noCameraMessage.classList.add('hidden');
            }
        }
        
        // Get current preview count setting
        let count = previewCountSelect ? previewCountSelect.value : '4';
        
        // Auto-select simple view (1) when only one camera AND user hasn't manually changed it
        if (cameras.length === 1 && !state.userOverridePreviewCount) {
            count = '1';
            if (previewCountSelect && previewCountSelect.value !== '1') {
                previewCountSelect.value = '1';
            }
        }
        previewGrid.dataset.previewCount = count;
        
        const cells = previewGrid.querySelectorAll('.preview-cell');
        
        cells.forEach((cell, index) => {
            const img = cell.querySelector('.preview-frame');
            const label = cell.querySelector('.preview-label');
            let overlay = cell.querySelector('.stream-details-overlay');
            
            if (cameras[index]) {
                const cam = cameras[index];
                const isStreaming = state.streamingCameras.has(cam.id);
                const isOverlayVisible = state.visibleOverlays.has(cam.id);
                
                // Remove empty state
                cell.classList.remove('empty-slot');
                
                // Create or update stream details overlay
                if (!overlay) {
                    overlay = document.createElement('div');
                    overlay.className = 'stream-details-overlay';
                    cell.querySelector('.frame-container').appendChild(overlay);
                }
                
                if (isStreaming && !state.usePolling) {
                    // Use MJPEG stream URL
                    const streamUrl = buildUrl(`/stream/${cam.id}/`);
                    if (img.src !== streamUrl) {
                        img.src = streamUrl;
                    }
                    // Update streaming details overlay
                    if (isOverlayVisible) {
                        overlay.classList.add('visible');
                        const stats = state.cameraStats[cam.id] || {};
                        const fpsDisplay = stats.real_fps !== undefined ? stats.real_fps.toFixed(1) : '--';
                        const resDisplay = (stats.width && stats.height) ? `${stats.width}x${stats.height}` : '--x--';
                        const bwDisplay = stats.bandwidth_kbps !== undefined ? formatBandwidth(stats.bandwidth_kbps) : '-- Kb/s';
                        
                        overlay.innerHTML = `
                            <div class="stream-header">
                                <span class="stream-status live">LIVE</span>
                                <span class="stream-info">MJPEG</span>
                            </div>
                            <div class="stream-stats">
                                <span class="stat-item">FPS: ${fpsDisplay}</span>
                                <span class="stat-item">${resDisplay}</span>
                                <span class="stat-item">${bwDisplay}</span>
                            </div>
                            <div class="stream-controls">
                                <button class="stream-control-btn stop-btn" data-camera-id="${cam.id}" title="Arrêter le stream">
                                    <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor"><rect x="6" y="6" width="12" height="12"/></svg>
                                </button>
                                <button class="stream-control-btn fullscreen-btn" data-camera-id="${cam.id}" title="Plein écran">
                                    <svg class="icon-maximize" viewBox="0 0 24 24" width="16" height="16" stroke="currentColor" stroke-width="2" fill="none"><path d="M8 3H5a2 2 0 0 0-2 2v3m18 0V5a2 2 0 0 0-2-2h-3m0 18h3a2 2 0 0 0 2-2v-3M3 16v3a2 2 0 0 0 2 2h3"></path></svg>
                                    <svg class="icon-minimize" viewBox="0 0 24 24" width="16" height="16" stroke="currentColor" stroke-width="2" fill="none" style="display:none"><path d="M8 3v3a2 2 0 0 1-2 2H3m18 0h-3a2 2 0 0 1-2-2V3m0 18v-3a2 2 0 0 1 2-2h3M3 16h3a2 2 0 0 1 2 2v3"></path></svg>
                                </button>
                            </div>
                        `;
                        // Bind stop button
                        const stopBtn = overlay.querySelector('.stop-btn');
                        if (stopBtn) {
                            stopBtn.onclick = (e) => {
                                e.stopPropagation();
                                stopCameraStream(cam.id);
                            };
                        }
                        // Bind fullscreen button
                        const fullscreenBtn = overlay.querySelector('.fullscreen-btn');
                        if (fullscreenBtn) {
                            fullscreenBtn.onclick = (e) => {
                                e.stopPropagation();
                                toggleFullscreen(fullscreenBtn);
                            };
                        }
                    } else {
                        overlay.classList.remove('visible');
                        overlay.innerHTML = '';
                    }
                } else {
                    // Use single frame with polling - show play button in overlay
                    img.src = buildUrl(`/frame/${cam.id}/?_ts=${Date.now()}`);
                    if (isOverlayVisible) {
                        overlay.classList.add('visible');
                        overlay.innerHTML = `
                            <div class="stream-header">
                                <span class="stream-status offline">OFFLINE</span>
                            </div>
                            <div class="stream-stats">
                                <span class="stat-item">FPS: --</span>
                                <span class="stat-item">--x--</span>
                                <span class="stat-item">-- Kb/s</span>
                            </div>
                            <div class="stream-controls">
                                <button class="stream-control-btn play-btn" data-camera-id="${cam.id}" title="Démarrer le stream">
                                    <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor"><polygon points="5,3 19,12 5,21"/></svg>
                                </button>
                                <button class="stream-control-btn fullscreen-btn" data-camera-id="${cam.id}" title="Plein écran">
                                    <svg class="icon-maximize" viewBox="0 0 24 24" width="16" height="16" stroke="currentColor" stroke-width="2" fill="none"><path d="M8 3H5a2 2 0 0 0-2 2v3m18 0V5a2 2 0 0 0-2-2h-3m0 18h3a2 2 0 0 0 2-2v-3M3 16v3a2 2 0 0 0 2 2h3"></path></svg>
                                    <svg class="icon-minimize" viewBox="0 0 24 24" width="16" height="16" stroke="currentColor" stroke-width="2" fill="none" style="display:none"><path d="M8 3v3a2 2 0 0 1-2 2H3m18 0h-3a2 2 0 0 1-2-2V3m0 18v-3a2 2 0 0 1 2-2h3M3 16h3a2 2 0 0 1 2 2v3"></path></svg>
                                </button>
                            </div>
                        `;
                        // Bind play button
                        const playBtn = overlay.querySelector('.play-btn');
                        if (playBtn) {
                            playBtn.onclick = (e) => {
                                e.stopPropagation();
                                startCameraStream(cam.id);
                            };
                        }
                        // Bind fullscreen button
                        const fullscreenBtn = overlay.querySelector('.fullscreen-btn');
                        if (fullscreenBtn) {
                            fullscreenBtn.onclick = (e) => {
                                e.stopPropagation();
                                toggleFullscreen(fullscreenBtn);
                            };
                        }
                    } else {
                        overlay.classList.remove('visible');
                        overlay.innerHTML = '';
                    }
                }
                
                if (label) {
                    label.textContent = cam.name;
                    // Add streaming indicator
                    if (isStreaming) {
                        label.classList.add('streaming');
                    } else {
                        label.classList.remove('streaming');
                    }
                }
                
                // Add click handler to toggle overlay visibility
                cell.onclick = () => toggleOverlayVisibility(cam.id);
                cell.style.cursor = 'pointer';
                cell.title = 'Cliquer pour afficher/masquer les contrôles';
            } else {
                // Show "no camera" placeholder for empty slots
                img.src = '';
                img.alt = 'No camera';
                if (label) label.textContent = `--`;
                cell.onclick = null;
                cell.style.cursor = 'default';
                cell.title = 'Aucune caméra configurée';
                cell.classList.add('empty-slot');
            }
        });
    }

    function toggleOverlayVisibility(cameraId) {
        if (state.visibleOverlays.has(cameraId)) {
            state.visibleOverlays.delete(cameraId);
        } else {
            state.visibleOverlays.add(cameraId);
        }
        updatePreviewGrid();
    }

    async function toggleCameraStream(cameraId) {
        const isStreaming = state.streamingCameras.has(cameraId);
        
        if (isStreaming) {
            await stopCameraStream(cameraId);
        } else {
            await startCameraStream(cameraId);
        }
    }

    async function startCameraStream(cameraId) {
        motionFrontendUI.setStatus(`Starting stream for camera ${cameraId}...`);
        
        try {
            const result = await apiPost('/api/mjpeg/', { action: 'start', camera_id: cameraId });
            
            if (result.status === 'ok' && result.camera?.is_running) {
                state.streamingCameras.add(cameraId);
                motionFrontendUI.showToast(`Stream started`, 'success');
                
                // Switch to streaming mode for this camera
                state.usePolling = false;
                updatePreviewGrid();
            } else {
                const error = result.camera?.error || 'Unknown error';
                motionFrontendUI.showToast(`Failed to start stream: ${error}`, 'error');
            }
        } catch (error) {
            motionFrontendUI.showToast(`Error: ${error.message}`, 'error');
        } finally {
            motionFrontendUI.setStatus('Ready');
        }
    }

    async function stopCameraStream(cameraId) {
        motionFrontendUI.setStatus(`Stopping stream for camera ${cameraId}...`);
        
        try {
            await apiPost('/api/mjpeg/', { action: 'stop', camera_id: cameraId });
            state.streamingCameras.delete(cameraId);
            motionFrontendUI.showToast(`Stream stopped`, 'success');
            
            // Check if we should switch back to polling mode
            if (state.streamingCameras.size === 0) {
                state.usePolling = true;
            }
            updatePreviewGrid();
        } catch (error) {
            motionFrontendUI.showToast(`Error: ${error.message}`, 'error');
        } finally {
            motionFrontendUI.setStatus('Ready');
        }
    }

    async function loadMJPEGStatus() {
        try {
            const result = await apiGet('/api/mjpeg/');
            
            // Update streaming cameras set
            state.streamingCameras.clear();
            if (result.cameras) {
                for (const [camId, status] of Object.entries(result.cameras)) {
                    if (status.is_running) {
                        state.streamingCameras.add(camId);
                    }
                }
            }
            
            // Update usePolling based on streaming cameras
            state.usePolling = state.streamingCameras.size === 0;
            
            return result;
        } catch (error) {
            console.error('Failed to load MJPEG status:', error);
            return null;
        }
    }

    function hslToHex(h, s, l) {
        s /= 100;
        l /= 100;
        const a = s * Math.min(l, 1 - l);
        const f = n => {
            const k = (n + h / 30) % 12;
            const color = l - a * Math.max(Math.min(k - 3, 9 - k, 1), -1);
            return Math.round(255 * color).toString(16).padStart(2, '0');
        };
        return `${f(0)}${f(8)}${f(4)}`;
    }

    function refreshFrame() {
        updatePreviewGrid();
    }

    function setupFramePolling() {
        const interval = Math.max(2000, context.frameRefreshInterval || 4000);
        if (state.pollingHandle) {
            window.clearInterval(state.pollingHandle);
        }
        state.pollingHandle = window.setInterval(refreshFrame, interval);
    }

    function triggerUpdate() {
        // First, check for updates and show modal with info
        motionFrontendUI.setStatus('Checking for updates...');
        
        // Fetch both release and source info in parallel
        Promise.all([
            apiGet('/api/update/'),
            apiPost('/api/update/', { action: 'check_source', branch: 'main' })
        ])
            .then(([releaseInfo, sourceInfo]) => {
                showUpdateModal(releaseInfo, sourceInfo);
            })
            .catch((error) => {
                motionFrontendUI.showToast(`Update check failed: ${error.message}`, 'error');
            })
            .finally(() => motionFrontendUI.setStatus('Ready'));
    }

    function showUpdateModal(updateInfo, sourceInfo) {
        // Remove existing modal if present
        const existingModal = document.getElementById('updateModal');
        if (existingModal) {
            existingModal.remove();
        }

        const modal = document.createElement('div');
        modal.id = 'updateModal';
        modal.className = 'modal-overlay';
        
        const currentVersion = updateInfo.current_version || 'unknown';
        const latestVersion = updateInfo.latest_version || 'unknown';
        const updateAvailable = updateInfo.update_available || false;
        const releaseNotes = updateInfo.latest_release?.body || '';
        const releaseUrl = updateInfo.latest_release?.html_url || 'https://github.com/sn8k/Mme/releases';
        const error = updateInfo.error;
        
        // Source info
        const sourceBranch = sourceInfo?.branch || 'main';
        const sourceCommit = sourceInfo?.source_info?.commit_sha || 'unknown';
        const sourceMessage = sourceInfo?.source_info?.commit_message || '';
        const sourceDate = sourceInfo?.source_info?.commit_date || '';
        const sourceUrl = sourceInfo?.source_info?.html_url || `https://github.com/sn8k/Mme/tree/${sourceBranch}`;
        const sourceError = sourceInfo?.error;
        
        let statusHtml = '';
        let actionButtonHtml = '';
        
        if (error) {
            statusHtml = `
                <div class="update-status update-status-error">
                    <span class="status-icon">⚠️</span>
                    <span>Error: ${error}</span>
                </div>
            `;
            actionButtonHtml = `<button type="button" class="button button-secondary" id="retryUpdateCheck">Retry</button>`;
        } else if (updateAvailable) {
            statusHtml = `
                <div class="update-status update-status-available">
                    <span class="status-icon">🆕</span>
                    <span>Update available: <strong>${latestVersion}</strong></span>
                </div>
            `;
            actionButtonHtml = `<button type="button" class="button button-primary" id="performUpdate">Install Update</button>`;
        } else {
            statusHtml = `
                <div class="update-status update-status-uptodate">
                    <span class="status-icon">✓</span>
                    <span>You are running the latest release version</span>
                </div>
            `;
        }
        
        // Format release notes (convert markdown-ish to HTML)
        const formattedNotes = releaseNotes
            .replace(/^### (.+)$/gm, '<h4>$1</h4>')
            .replace(/^## (.+)$/gm, '<h3>$1</h3>')
            .replace(/^- (.+)$/gm, '<li>$1</li>')
            .replace(/(<li>.*<\/li>\n?)+/g, '<ul>$&</ul>')
            .replace(/\n\n/g, '<br><br>')
            .replace(/\n/g, '<br>');
        
        // Format source date
        let formattedSourceDate = '';
        if (sourceDate) {
            try {
                formattedSourceDate = new Date(sourceDate).toLocaleString();
            } catch {
                formattedSourceDate = sourceDate;
            }
        }
        
        modal.innerHTML = `
            <div class="modal-dialog modal-dialog-wide">
                <div class="modal-header">
                    <h3>🔄 Software Update</h3>
                    <button type="button" class="modal-close" id="closeUpdateModal">&times;</button>
                </div>
                <div class="modal-body">
                    <!-- Update mode tabs -->
                    <div class="update-tabs">
                        <button type="button" class="update-tab active" data-tab="release">
                            📦 Releases
                        </button>
                        <button type="button" class="update-tab" data-tab="source">
                            🔧 Source (Dev)
                        </button>
                    </div>
                    
                    <!-- Release tab content -->
                    <div id="releaseTab" class="update-tab-content active">
                        <div class="version-info">
                            <div class="version-row">
                                <span class="version-label">Current version:</span>
                                <span class="version-value">${currentVersion}</span>
                            </div>
                            <div class="version-row">
                                <span class="version-label">Latest release:</span>
                                <span class="version-value">${latestVersion}</span>
                            </div>
                        </div>
                        ${statusHtml}
                        ${releaseNotes ? `
                            <div class="release-notes">
                                <h4>Release Notes</h4>
                                <div class="release-notes-content">${formattedNotes}</div>
                            </div>
                        ` : ''}
                        <div class="update-links">
                            <a href="${releaseUrl}" target="_blank" rel="noopener noreferrer">View releases on GitHub →</a>
                        </div>
                    </div>
                    
                    <!-- Source tab content -->
                    <div id="sourceTab" class="update-tab-content">
                        <div class="source-info-notice">
                            <span class="notice-icon">⚠️</span>
                            <span>Source updates install the latest development code. This may include untested features.</span>
                        </div>
                        <div class="version-info">
                            <div class="version-row">
                                <span class="version-label">Current version:</span>
                                <span class="version-value">${currentVersion}</span>
                            </div>
                            <div class="version-row">
                                <span class="version-label">Branch:</span>
                                <span class="version-value">${sourceBranch}</span>
                            </div>
                            <div class="version-row">
                                <span class="version-label">Latest commit:</span>
                                <span class="version-value commit-sha">${sourceCommit}</span>
                            </div>
                            ${sourceDate ? `
                            <div class="version-row">
                                <span class="version-label">Commit date:</span>
                                <span class="version-value">${formattedSourceDate}</span>
                            </div>
                            ` : ''}
                        </div>
                        ${sourceMessage ? `
                            <div class="commit-message">
                                <strong>Latest commit:</strong> ${sourceMessage}
                            </div>
                        ` : ''}
                        ${sourceError ? `
                            <div class="update-status update-status-error">
                                <span class="status-icon">⚠️</span>
                                <span>Error: ${sourceError}</span>
                            </div>
                        ` : `
                            <div class="update-status update-status-source">
                                <span class="status-icon">🔧</span>
                                <span>Update from source to get the latest development version</span>
                            </div>
                        `}
                        <div class="update-links">
                            <a href="${sourceUrl}" target="_blank" rel="noopener noreferrer">View source on GitHub →</a>
                        </div>
                    </div>
                    
                    <div id="updateProgress" class="update-progress hidden">
                        <div class="progress-bar">
                            <div class="progress-bar-fill"></div>
                        </div>
                        <div class="progress-text">Updating...</div>
                    </div>
                </div>
                <div class="modal-footer">
                    <button type="button" class="button button-secondary" id="cancelUpdate">Close</button>
                    <div id="releaseActions" class="update-actions">
                        ${actionButtonHtml}
                    </div>
                    <div id="sourceActions" class="update-actions hidden">
                        ${!sourceError ? `<button type="button" class="button button-warning" id="performSourceUpdate">Update from Source</button>` : ''}
                    </div>
                </div>
            </div>
        `;
        
        document.body.appendChild(modal);
        
        // Tab switching
        const tabs = modal.querySelectorAll('.update-tab');
        const releaseTab = document.getElementById('releaseTab');
        const sourceTab = document.getElementById('sourceTab');
        const releaseActions = document.getElementById('releaseActions');
        const sourceActions = document.getElementById('sourceActions');
        
        tabs.forEach(tab => {
            tab.addEventListener('click', () => {
                tabs.forEach(t => t.classList.remove('active'));
                tab.classList.add('active');
                
                const tabName = tab.getAttribute('data-tab');
                if (tabName === 'release') {
                    releaseTab.classList.add('active');
                    sourceTab.classList.remove('active');
                    releaseActions.classList.remove('hidden');
                    sourceActions.classList.add('hidden');
                } else {
                    releaseTab.classList.remove('active');
                    sourceTab.classList.add('active');
                    releaseActions.classList.add('hidden');
                    sourceActions.classList.remove('hidden');
                }
            });
        });
        
        // Event handlers
        const closeModal = () => modal.remove();
        
        document.getElementById('closeUpdateModal').addEventListener('click', closeModal);
        document.getElementById('cancelUpdate').addEventListener('click', closeModal);
        modal.addEventListener('click', (e) => {
            if (e.target === modal) closeModal();
        });
        
        const retryBtn = document.getElementById('retryUpdateCheck');
        if (retryBtn) {
            retryBtn.addEventListener('click', () => {
                closeModal();
                triggerUpdate();
            });
        }
        
        const performBtn = document.getElementById('performUpdate');
        if (performBtn) {
            performBtn.addEventListener('click', () => {
                performUpdate(modal, 'release');
            });
        }
        
        const performSourceBtn = document.getElementById('performSourceUpdate');
        if (performSourceBtn) {
            performSourceBtn.addEventListener('click', () => {
                performUpdate(modal, 'source', sourceBranch);
            });
        }
    }

    function performUpdate(modal, updateType = 'release', branch = 'main') {
        const progressDiv = document.getElementById('updateProgress');
        const progressText = progressDiv.querySelector('.progress-text');
        const progressFill = progressDiv.querySelector('.progress-bar-fill');
        const performBtn = document.getElementById('performUpdate');
        const performSourceBtn = document.getElementById('performSourceUpdate');
        const cancelBtn = document.getElementById('cancelUpdate');
        
        // Show progress, disable buttons
        progressDiv.classList.remove('hidden');
        if (performBtn) performBtn.disabled = true;
        if (performSourceBtn) performSourceBtn.disabled = true;
        if (cancelBtn) cancelBtn.disabled = true;
        
        const isSource = updateType === 'source';
        progressText.textContent = isSource ? `Downloading source from ${branch}...` : 'Downloading update...';
        progressFill.style.width = '30%';
        
        const payload = isSource 
            ? { action: 'update_source', branch: branch }
            : { action: 'update' };
        
        apiPost('/api/update/', payload)
            .then((result) => {
                if (result.success) {
                    progressFill.style.width = '100%';
                    progressText.textContent = result.message || 'Update complete!';
                    
                    // Show restart notice
                    if (result.requires_restart) {
                        setTimeout(() => {
                            motionFrontendUI.showToast(
                                'Update installed! Please restart the server to apply changes.',
                                'success'
                            );
                        }, 1000);
                        
                        // Update the modal content
                        progressText.innerHTML = `
                            <strong>Update installed!</strong><br>
                            Updated from ${result.old_version} to ${result.new_version}<br>
                            <em>Please restart the server to apply changes.</em>
                        `;
                    }
                    
                    if (cancelBtn) {
                        cancelBtn.disabled = false;
                        cancelBtn.textContent = 'Close';
                    }
                } else {
                    throw new Error(result.error || result.message || 'Update failed');
                }
            })
            .catch((error) => {
                progressFill.style.width = '0%';
                progressFill.classList.add('error');
                progressText.textContent = `Update failed: ${error.message}`;
                
                motionFrontendUI.showToast(`Update failed: ${error.message}`, 'error');
                
                if (performBtn) performBtn.disabled = false;
                if (cancelBtn) cancelBtn.disabled = false;
            });
    }

    function showAddCameraDialog() {
        // Create modal dialog for adding camera
        const existingModal = document.getElementById('addCameraModal');
        if (existingModal) {
            existingModal.remove();
        }

        const modal = document.createElement('div');
        modal.id = 'addCameraModal';
        modal.className = 'modal-overlay';
        modal.innerHTML = `
            <div class="modal-dialog modal-dialog-wide">
                <div class="modal-header">
                    <h3>Ajouter une caméra</h3>
                    <button type="button" class="modal-close" id="closeAddCameraModal">&times;</button>
                </div>
                <div class="modal-body">
                    <div class="detected-cameras-section">
                        <div class="section-header">
                            <label>Caméras détectées</label>
                            <button type="button" class="button button-small" id="refreshDetectedCameras" title="Rafraîchir">
                                <span class="refresh-icon">↻</span>
                            </button>
                        </div>
                        <div id="detectedCamerasList" class="detected-cameras-list">
                            <div class="loading-cameras">Détection en cours...</div>
                        </div>
                        <div class="filter-toggle">
                            <label class="checkbox-label">
                                <input type="checkbox" id="showFilteredCameras">
                                <span>Afficher les caméras masquées</span>
                            </label>
                            <button type="button" class="button button-small button-text" id="manageFiltersBtn">
                                Gérer les filtres
                            </button>
                        </div>
                    </div>
                    <div class="manual-entry-section">
                        <label class="section-label">Ou saisir manuellement</label>
                        <div class="form-group">
                            <label for="newCameraName">Nom de la caméra</label>
                            <input type="text" id="newCameraName" class="form-control" placeholder="Ex: Entrée principale">
                        </div>
                        <div class="form-group">
                            <label for="newCameraUrl">URL du flux</label>
                            <input type="text" id="newCameraUrl" class="form-control" placeholder="rtsp://... ou /dev/video0">
                        </div>
                    </div>
                </div>
                <div class="modal-footer">
                    <button type="button" class="button button-secondary" id="cancelAddCamera">Annuler</button>
                    <button type="button" class="button button-primary" id="confirmAddCamera">Ajouter</button>
                </div>
            </div>
        `;
        document.body.appendChild(modal);

        // Load detected cameras
        loadDetectedCameras(false);

        // Event handlers
        const closeModal = () => modal.remove();

        document.getElementById('closeAddCameraModal').addEventListener('click', closeModal);
        document.getElementById('cancelAddCamera').addEventListener('click', closeModal);
        modal.addEventListener('click', (e) => {
            if (e.target === modal) closeModal();
        });

        document.getElementById('refreshDetectedCameras').addEventListener('click', () => {
            const showFiltered = document.getElementById('showFilteredCameras').checked;
            loadDetectedCameras(showFiltered);
        });

        document.getElementById('showFilteredCameras').addEventListener('change', (e) => {
            loadDetectedCameras(e.target.checked);
        });

        document.getElementById('manageFiltersBtn').addEventListener('click', () => {
            showFilterManagementDialog();
        });

        document.getElementById('confirmAddCamera').addEventListener('click', () => {
            const name = document.getElementById('newCameraName').value.trim();
            const deviceUrl = document.getElementById('newCameraUrl').value.trim();
            addCamera(name, deviceUrl).then(closeModal);
        });

        // Allow Enter key to submit
        modal.querySelector('.manual-entry-section').addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                document.getElementById('confirmAddCamera').click();
            }
        });
    }

    function loadDetectedCameras(includeFiltered) {
        const listContainer = document.getElementById('detectedCamerasList');
        if (!listContainer) return;

        listContainer.innerHTML = '<div class="loading-cameras">Détection en cours...</div>';

        const url = `/api/cameras/detect/${includeFiltered ? '?include_filtered=true' : ''}`;
        apiGet(url)
            .then((data) => {
                renderDetectedCameras(data.cameras || [], data.filter_patterns || []);
            })
            .catch((error) => {
                listContainer.innerHTML = `<div class="error-message">Erreur: ${escapeHtml(error.message)}</div>`;
            });
    }

    function renderDetectedCameras(cameras, filterPatterns) {
        const listContainer = document.getElementById('detectedCamerasList');
        if (!listContainer) return;

        if (cameras.length === 0) {
            listContainer.innerHTML = '<div class="no-cameras-found">Aucune caméra détectée</div>';
            return;
        }

        const html = cameras.map((cam) => {
            const isFiltered = isMatchingFilter(cam, filterPatterns);
            const filteredClass = isFiltered ? 'camera-filtered' : '';
            const sourceIcon = getSourceIcon(cam.source_type);
            
            return `
                <div class="detected-camera-item ${filteredClass}" 
                     data-device-path="${escapeHtml(cam.device_path)}"
                     data-name="${escapeHtml(cam.name)}">
                    <div class="camera-icon">${sourceIcon}</div>
                    <div class="camera-info">
                        <div class="camera-name">${escapeHtml(cam.name)}</div>
                        <div class="camera-device">${escapeHtml(cam.device_path)}</div>
                        ${cam.driver ? `<div class="camera-driver">${escapeHtml(cam.driver)}</div>` : ''}
                    </div>
                    <div class="camera-actions">
                        <button type="button" class="button button-small button-primary select-camera-btn">
                            Sélectionner
                        </button>
                        ${!isFiltered ? `
                            <button type="button" class="button button-small button-text hide-camera-btn" title="Masquer">
                                👁️‍🗨️
                            </button>
                        ` : ''}
                    </div>
                </div>
            `;
        }).join('');

        listContainer.innerHTML = html;

        // Bind click events
        listContainer.querySelectorAll('.select-camera-btn').forEach((btn) => {
            btn.addEventListener('click', (e) => {
                const item = e.target.closest('.detected-camera-item');
                const devicePath = item.dataset.devicePath;
                const name = item.dataset.name;
                
                document.getElementById('newCameraName').value = name;
                document.getElementById('newCameraUrl').value = devicePath;
                
                // Highlight selected
                listContainer.querySelectorAll('.detected-camera-item').forEach(el => el.classList.remove('selected'));
                item.classList.add('selected');
            });
        });

        listContainer.querySelectorAll('.hide-camera-btn').forEach((btn) => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                const item = e.target.closest('.detected-camera-item');
                const name = item.dataset.name;
                
                // Add filter pattern for this camera
                addCameraFilterPattern(escapeRegex(name));
            });
        });
    }

    function isMatchingFilter(camera, patterns) {
        for (const pattern of patterns) {
            try {
                const regex = new RegExp(pattern, 'i');
                if (regex.test(camera.name) || regex.test(camera.driver) || regex.test(camera.device_path)) {
                    return true;
                }
            } catch (e) {
                // Invalid regex, skip
            }
        }
        return false;
    }

    function getSourceIcon(sourceType) {
        const icons = {
            'v4l2': '📹',
            'usb': '🔌',
            'csi': '📷',
            'dshow': '🎥',
        };
        return icons[sourceType] || '📷';
    }

    function escapeRegex(string) {
        return string.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    }

    function addCameraFilterPattern(pattern) {
        apiPut('/api/cameras/filters/', { pattern })
            .then(() => {
                motionFrontendUI.showToast('Caméra masquée', 'success');
                const showFiltered = document.getElementById('showFilteredCameras')?.checked || false;
                loadDetectedCameras(showFiltered);
            })
            .catch((error) => {
                motionFrontendUI.showToast(`Erreur: ${error.message}`, 'error');
            });
    }

    function showFilterManagementDialog() {
        const existingModal = document.getElementById('filterManagementModal');
        if (existingModal) {
            existingModal.remove();
        }

        const modal = document.createElement('div');
        modal.id = 'filterManagementModal';
        modal.className = 'modal-overlay';
        modal.innerHTML = `
            <div class="modal-dialog">
                <div class="modal-header">
                    <h3>Gérer les filtres de caméras</h3>
                    <button type="button" class="modal-close" id="closeFilterModal">&times;</button>
                </div>
                <div class="modal-body">
                    <p class="filter-info">Les caméras correspondant à ces motifs regex seront masquées par défaut.</p>
                    <div id="filterPatternsList" class="filter-patterns-list">
                        <div class="loading">Chargement...</div>
                    </div>
                    <div class="add-filter-section">
                        <input type="text" id="newFilterPattern" class="form-control" placeholder="Nouveau motif regex...">
                        <button type="button" class="button button-primary" id="addFilterPatternBtn">Ajouter</button>
                    </div>
                </div>
                <div class="modal-footer">
                    <button type="button" class="button button-secondary" id="closeFilterModalBtn">Fermer</button>
                </div>
            </div>
        `;
        document.body.appendChild(modal);

        // Load current patterns
        loadFilterPatterns();

        const closeModal = () => {
            modal.remove();
            // Refresh detected cameras after closing filter modal
            const showFiltered = document.getElementById('showFilteredCameras')?.checked || false;
            loadDetectedCameras(showFiltered);
        };

        document.getElementById('closeFilterModal').addEventListener('click', closeModal);
        document.getElementById('closeFilterModalBtn').addEventListener('click', closeModal);
        modal.addEventListener('click', (e) => {
            if (e.target === modal) closeModal();
        });

        document.getElementById('addFilterPatternBtn').addEventListener('click', () => {
            const input = document.getElementById('newFilterPattern');
            const pattern = input.value.trim();
            if (pattern) {
                apiPut('/api/cameras/filters/', { pattern })
                    .then(() => {
                        input.value = '';
                        loadFilterPatterns();
                    })
                    .catch((error) => {
                        motionFrontendUI.showToast(`Erreur: ${error.message}`, 'error');
                    });
            }
        });

        document.getElementById('newFilterPattern').addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                document.getElementById('addFilterPatternBtn').click();
            }
        });
    }

    function loadFilterPatterns() {
        const listContainer = document.getElementById('filterPatternsList');
        if (!listContainer) return;

        apiGet('/api/cameras/filters/')
            .then((data) => {
                renderFilterPatterns(data.patterns || []);
            })
            .catch((error) => {
                listContainer.innerHTML = `<div class="error-message">Erreur: ${escapeHtml(error.message)}</div>`;
            });
    }

    function renderFilterPatterns(patterns) {
        const listContainer = document.getElementById('filterPatternsList');
        if (!listContainer) return;

        if (patterns.length === 0) {
            listContainer.innerHTML = '<div class="no-filters">Aucun filtre configuré</div>';
            return;
        }

        const html = patterns.map((pattern) => `
            <div class="filter-pattern-item">
                <code class="pattern-text">${escapeHtml(pattern)}</code>
                <button type="button" class="button button-small button-danger remove-filter-btn" data-pattern="${escapeHtml(pattern)}">
                    ✕
                </button>
            </div>
        `).join('');

        listContainer.innerHTML = html;

        // Bind remove buttons
        listContainer.querySelectorAll('.remove-filter-btn').forEach((btn) => {
            btn.addEventListener('click', () => {
                const pattern = btn.dataset.pattern;
                apiDelete('/api/cameras/filters/', { pattern })
                    .then(() => loadFilterPatterns())
                    .catch((error) => {
                        motionFrontendUI.showToast(`Erreur: ${error.message}`, 'error');
                    });
            });
        });
    }

    /**
     * Update the remove camera button state based on current selection.
     */
    function updateRemoveCameraButtonState() {
        const remCameraButton = document.getElementById('remCameraButton');
        if (remCameraButton) {
            remCameraButton.disabled = !state.cameraId;
        }
    }

    function addCamera(name, deviceUrl) {
        motionFrontendUI.setStatus('Adding camera...');
        return apiPost('/api/config/camera/add/', { name, device_url: deviceUrl })
            .then((result) => {
                motionFrontendUI.showToast(`Camera "${result.camera.name}" added successfully`, 'success');
                // Update context cameras
                context.cameras = context.cameras || [];
                context.cameras.push(result.camera);
                // Update camera list in sidebar
                refreshCameraList();
                // Auto-select the new camera
                state.cameraId = result.camera.id;
                const cameraSelect = document.getElementById('cameraSelect');
                if (cameraSelect) {
                    cameraSelect.value = result.camera.id;
                }
                // Load and display camera config
                refreshCameraConfig();
                // Refresh preview grid
                updatePreviewGrid();
                // Enable remove button
                updateRemoveCameraButtonState();
                return result;
            })
            .catch((error) => {
                motionFrontendUI.showToast(`Failed to add camera: ${error.message}`, 'error');
                throw error;
            })
            .finally(() => motionFrontendUI.setStatus('Ready'));
    }

    function deleteCamera(cameraId) {
        if (!confirm('Êtes-vous sûr de vouloir supprimer cette caméra ?')) {
            return Promise.resolve();
        }
        
        motionFrontendUI.setStatus('Deleting camera...');
        return apiDelete(`/api/config/camera/${cameraId}/delete/`)
            .then((result) => {
                motionFrontendUI.showToast('Camera deleted', 'success');
                // Remove from context
                context.cameras = (context.cameras || []).filter(c => c.id !== cameraId);
                // Clear selection
                state.cameraId = null;
                const cameraSelect = document.getElementById('cameraSelect');
                if (cameraSelect) {
                    cameraSelect.value = '';
                }
                // Refresh UI
                refreshCameraList();
                refreshCameraConfig();
                updatePreviewGrid();
                // Update remove button state
                updateRemoveCameraButtonState();
                return result;
            })
            .catch((error) => {
                motionFrontendUI.showToast(`Failed to delete camera: ${error.message}`, 'error');
                throw error;
            })
            .finally(() => motionFrontendUI.setStatus('Ready'));
    }

    function refreshCameraList() {
        apiGet('/api/config/list/')
            .then((data) => {
                const cameras = data.cameras || [];
                context.cameras = cameras;
                
                // Update camera select dropdown
                const cameraSelect = document.getElementById('cameraSelect');
                if (cameraSelect) {
                    const currentValue = cameraSelect.value;
                    cameraSelect.innerHTML = '<option value="">-- Select camera --</option>';
                    cameras.forEach((cam) => {
                        const option = document.createElement('option');
                        option.value = cam.id;
                        option.textContent = cam.name;
                        cameraSelect.appendChild(option);
                    });
                    // Restore selection if still exists
                    if (cameras.some(c => c.id === currentValue)) {
                        cameraSelect.value = currentValue;
                    }
                    cameraSelect.disabled = cameras.length === 0;
                }

                // Update remove button state
                const remCameraButton = document.getElementById('remCameraButton');
                if (remCameraButton) {
                    remCameraButton.disabled = !state.cameraId;
                }

                // Update sidebar camera list if exists
                const cameraList = document.getElementById('cameraList');
                if (cameraList) {
                    cameraList.innerHTML = '';
                    cameras.forEach((cam) => {
                        const li = document.createElement('li');
                        li.innerHTML = `
                            <a href="?camera=${cam.id}" class="camera-link ${cam.id === state.cameraId ? 'active' : ''}">
                                <span class="camera-name">${escapeHtml(cam.name)}</span>
                                <span class="camera-status ${cam.enabled ? 'enabled' : 'disabled'}"></span>
                            </a>
                        `;
                        cameraList.appendChild(li);
                    });
                }
            })
            .catch((error) => {
                console.error('Failed to refresh camera list:', error);
            });
    }

    function initSidebarToggle() {
        const toggle = document.getElementById('sidebarToggle');
        const sidebar = document.getElementById('menuSidebar');
        const scrim = document.getElementById('sidebarScrim');
        if (!toggle || !sidebar) {
            return;
        }

        const showLabel = toggle.dataset.labelShow || toggle.getAttribute('aria-label') || 'Show menu';
        const hideLabel = toggle.dataset.labelHide || 'Hide menu';
        const breakpoint = Number(toggle.dataset.sidebarBreakpoint || 1024);
        const state = {
            isOpen: false
        };

        function applyState(open) {
            state.isOpen = open;
            document.body.classList.toggle('sidebar-open', open);
            toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
            toggle.setAttribute('aria-label', open ? hideLabel : showLabel);
            sidebar.setAttribute('aria-hidden', open ? 'false' : 'true');
            if (scrim) {
                scrim.setAttribute('aria-hidden', open ? 'false' : 'true');
            }
        }

        toggle.addEventListener('click', () => {
            applyState(!state.isOpen);
        });

        sidebar.querySelectorAll('[data-sidebar-close]').forEach((btn) => {
            btn.addEventListener('click', () => applyState(false));
        });

        if (scrim) {
            scrim.addEventListener('click', () => applyState(false));
        }

        window.addEventListener('keydown', (event) => {
            if (event.key === 'Escape' && state.isOpen && window.innerWidth < breakpoint) {
                applyState(false);
            }
        });

        applyState(false);
    }

    function initThemeToggle() {
        const toggle = document.getElementById('themeToggle');
        if (!toggle) {
            return;
        }

        const savedTheme = localStorage.getItem('mfe-theme') || 'dark';
        applyTheme(savedTheme);

        function applyTheme(theme) {
            document.body.classList.toggle('theme-light', theme === 'light');
            toggle.dataset.theme = theme;
            localStorage.setItem('mfe-theme', theme);
        }

        toggle.addEventListener('click', () => {
            const current = toggle.dataset.theme || 'dark';
            const next = current === 'dark' ? 'light' : 'dark';
            applyTheme(next);
        });
    }

    function init() {
        initSidebarToggle();
        initThemeToggle();
        
        // Auto-select first camera if none selected and cameras exist
        const cameras = context.cameras || [];
        if (!state.cameraId && cameras.length > 0) {
            state.cameraId = cameras[0].id;
            // Update the camera select dropdown
            const cameraSelect = document.getElementById('cameraSelect');
            if (cameraSelect) {
                cameraSelect.value = state.cameraId;
            }
        }
        
        bindButtons();
        loadAllConfigs();
        
        // Initialize Meeting controls after config is loaded
        setTimeout(initMeetingControls, 500);
        
        // Load camera config if a camera is selected
        if (state.cameraId) {
            refreshCameraConfig();
        }
        
        // Load MJPEG status, then auto-start streams for all cameras
        loadMJPEGStatus().then(() => {
            // Auto-start streaming for all configured cameras
            const camerasToStream = context.cameras || [];
            if (camerasToStream.length > 0) {
                autoStartAllStreams(camerasToStream);
            } else {
                refreshFrame();
                setupFramePolling();
            }
        });
        
        // Auto-start Meeting service if configured
        getMeetingStatus().then(data => {
            if (data && data.status && data.status.is_configured && !data.status.is_running) {
                controlMeeting('start');
            }
        });
    }

    async function autoStartAllStreams(cameras) {
        motionFrontendUI.setStatus('Starting camera streams...');
        
        try {
            // Start streams for all cameras that are not already streaming
            const startPromises = cameras
                .filter(cam => !state.streamingCameras.has(cam.id))
                .map(cam => apiPost('/api/mjpeg/', { action: 'start', camera_id: cam.id }).catch(() => null));
            
            const results = await Promise.all(startPromises);
            
            // Update streaming cameras state
            cameras.forEach((cam, index) => {
                const result = results[index];
                if (result?.status === 'ok' && result?.camera?.is_running) {
                    state.streamingCameras.add(cam.id);
                }
            });
            
            // Switch to streaming mode if any camera started
            if (state.streamingCameras.size > 0) {
                state.usePolling = false;
                // Start polling for stats when streaming is active
                startStatsPolling();
            }
            
            updatePreviewGrid();
        } catch (error) {
            console.error('Failed to auto-start streams:', error);
        } finally {
            motionFrontendUI.setStatus('Ready');
            setupFramePolling();
        }
    }

    // Global function for copying stream URL
    window.copyStreamUrl = function() {
        const urlDisplay = document.getElementById('streamUrlDisplay');
        if (!urlDisplay) return;
        
        // Build full URL using server IP and camera's dedicated MJPEG port
        const mjpegPort = urlDisplay.dataset.mjpegPort || '8081';
        const serverIp = urlDisplay.dataset.serverIp || window.location.hostname;
        const fullUrl = `http://${serverIp}:${mjpegPort}/stream/`;
        
        navigator.clipboard.writeText(fullUrl).then(() => {
            motionFrontendUI.showToast('URL copiée dans le presse-papier', 'success');
        }).catch(() => {
            // Fallback for older browsers
            const textArea = document.createElement('textarea');
            textArea.value = fullUrl;
            document.body.appendChild(textArea);
            textArea.select();
            document.execCommand('copy');
            document.body.removeChild(textArea);
            motionFrontendUI.showToast('URL copiée', 'success');
        });
    };

    // ====================
    // User Management Functions
    // ====================

    /**
     * Load current user information.
     * @returns {Promise<Object>} User info object.
     */
    async function loadCurrentUser() {
        try {
            const data = await apiGet('/api/user/me/');
            return data;
        } catch (error) {
            console.error('Failed to load user info:', error);
            return null;
        }
    }

    /**
     * Change the current user's password.
     * @param {string} currentPassword - Current password.
     * @param {string} newPassword - New password.
     * @param {string} confirmPassword - Confirmation of new password.
     * @returns {Promise<Object>} Result of the password change.
     */
    async function changePassword(currentPassword, newPassword, confirmPassword) {
        try {
            const result = await apiPost('/api/user/password/', {
                current_password: currentPassword,
                new_password: newPassword,
                confirm_password: confirmPassword
            });
            return result;
        } catch (error) {
            throw error;
        }
    }

    /**
     * Show password change modal dialog.
     */
    function showPasswordChangeModal() {
        const modalHtml = `
            <div class="modal-overlay" id="passwordChangeModal">
                <div class="modal-dialog">
                    <div class="modal-header">
                        <h3>Changer le mot de passe</h3>
                        <button type="button" class="modal-close" onclick="closePasswordChangeModal()">&times;</button>
                    </div>
                    <form id="passwordChangeForm" class="modal-body">
                        <div class="form-group">
                            <label for="currentPassword">Mot de passe actuel</label>
                            <input type="password" id="currentPassword" name="currentPassword" class="styled" required autocomplete="current-password">
                        </div>
                        <div class="form-group">
                            <label for="newPassword">Nouveau mot de passe</label>
                            <input type="password" id="newPassword" name="newPassword" class="styled" required minlength="6" autocomplete="new-password">
                            <small class="form-hint">Au moins 6 caractères</small>
                        </div>
                        <div class="form-group">
                            <label for="confirmPassword">Confirmer le nouveau mot de passe</label>
                            <input type="password" id="confirmPassword" name="confirmPassword" class="styled" required autocomplete="new-password">
                        </div>
                        <div class="form-error" id="passwordChangeError" style="display: none;"></div>
                    </form>
                    <div class="modal-footer">
                        <button type="button" class="button" onclick="closePasswordChangeModal()">Annuler</button>
                        <button type="button" class="button apply-button" onclick="submitPasswordChange()">Changer</button>
                    </div>
                </div>
            </div>
        `;
        
        const modalHost = document.getElementById('modalHost');
        if (modalHost) {
            modalHost.innerHTML = modalHtml;
        }
        
        // Focus on current password field
        setTimeout(() => {
            const currentPwdInput = document.getElementById('currentPassword');
            if (currentPwdInput) {
                currentPwdInput.focus();
            }
        }, 100);
    }

    /**
     * Close password change modal.
     */
    window.closePasswordChangeModal = function() {
        const modal = document.getElementById('passwordChangeModal');
        if (modal) {
            modal.remove();
        }
    };

    /**
     * Submit password change form.
     */
    window.submitPasswordChange = async function() {
        const currentPassword = document.getElementById('currentPassword').value;
        const newPassword = document.getElementById('newPassword').value;
        const confirmPassword = document.getElementById('confirmPassword').value;
        const errorDiv = document.getElementById('passwordChangeError');
        
        // Client-side validation
        if (!currentPassword || !newPassword || !confirmPassword) {
            errorDiv.textContent = 'Tous les champs sont requis';
            errorDiv.style.display = 'block';
            return;
        }
        
        if (newPassword.length < 6) {
            errorDiv.textContent = 'Le nouveau mot de passe doit contenir au moins 6 caractères';
            errorDiv.style.display = 'block';
            return;
        }
        
        if (newPassword !== confirmPassword) {
            errorDiv.textContent = 'Les nouveaux mots de passe ne correspondent pas';
            errorDiv.style.display = 'block';
            return;
        }
        
        try {
            const result = await changePassword(currentPassword, newPassword, confirmPassword);
            if (result.status === 'ok') {
                closePasswordChangeModal();
                motionFrontendUI.showToast(result.message || 'Mot de passe modifié avec succès', 'success');
            }
        } catch (error) {
            let errorMessage = 'Erreur lors du changement de mot de passe';
            if (error.message.includes('400')) {
                // Try to parse the error response
                try {
                    const response = await fetch(buildUrl('/api/user/password/'), {
                        method: 'POST',
                        credentials: 'include',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            current_password: currentPassword,
                            new_password: newPassword,
                            confirm_password: confirmPassword
                        })
                    });
                    const data = await response.json();
                    errorMessage = data.error || errorMessage;
                } catch (e) {
                    // Keep default error message
                }
            }
            errorDiv.textContent = errorMessage;
            errorDiv.style.display = 'block';
        }
    };

    // Expose password change modal function globally
    window.showPasswordChangeModal = showPasswordChangeModal;

    // ====================
    // Fullscreen Functions
    // ====================

    /**
     * Toggle fullscreen mode for a camera preview cell.
     * @param {HTMLElement} button - The fullscreen button clicked.
     */
    window.toggleFullscreen = function(button) {
        const previewCell = button.closest('.preview-cell');
        if (!previewCell) return;
        
        const isFullscreen = previewCell.classList.contains('fullscreen');
        
        if (isFullscreen) {
            // Exit fullscreen
            previewCell.classList.remove('fullscreen');
            document.body.style.overflow = '';
            
            // Exit browser fullscreen if active
            if (document.fullscreenElement) {
                document.exitFullscreen().catch(() => {});
            }
        } else {
            // Remove fullscreen from any other cell first
            document.querySelectorAll('.preview-cell.fullscreen').forEach(cell => {
                cell.classList.remove('fullscreen');
            });
            
            // Enter fullscreen
            previewCell.classList.add('fullscreen');
            document.body.style.overflow = 'hidden';
            
            // Try to enter browser fullscreen for true fullscreen experience
            if (previewCell.requestFullscreen) {
                previewCell.requestFullscreen().catch(() => {
                    // Browser fullscreen may be blocked, CSS fullscreen still works
                });
            }
        }
    };

    // Handle ESC key to exit fullscreen
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            const fullscreenCell = document.querySelector('.preview-cell.fullscreen');
            if (fullscreenCell) {
                fullscreenCell.classList.remove('fullscreen');
                document.body.style.overflow = '';
            }
        }
    });

    // Handle browser fullscreen change
    document.addEventListener('fullscreenchange', () => {
        if (!document.fullscreenElement) {
            // Browser exited fullscreen, also remove our CSS fullscreen
            const fullscreenCell = document.querySelector('.preview-cell.fullscreen');
            if (fullscreenCell) {
                fullscreenCell.classList.remove('fullscreen');
                document.body.style.overflow = '';
            }
        }
    });

    // Check if user must change password on init
    async function checkMustChangePassword() {
        const urlParams = new URLSearchParams(window.location.search);
        if (urlParams.get('change_password') === '1') {
            // Remove the parameter from URL
            urlParams.delete('change_password');
            const newUrl = window.location.pathname + (urlParams.toString() ? '?' + urlParams.toString() : '');
            window.history.replaceState({}, '', newUrl);
            
            // Show password change modal
            setTimeout(() => {
                showPasswordChangeModal();
                motionFrontendUI.showToast('Vous devez changer votre mot de passe', 'warning');
            }, 500);
        }
    }

    // Call on init
    function initUserManagement() {
        checkMustChangePassword();
    }

    // ========== Audio Device Management ==========

    /**
     * Load audio device configuration sections.
     */
    function loadAudioConfigSections(audioId) {
        if (!audioId) {
            return Promise.resolve({ sections: [] });
        }
        return apiGet(`/api/config/audio/${audioId}/sections/`);
    }

    /**
     * Refresh the audio device configuration in the sidebar.
     */
    function refreshAudioConfig() {
        const audioConfigContainer = document.getElementById('audioConfigColumns');
        if (!audioConfigContainer) return;

        if (!state.audioId) {
            audioConfigContainer.innerHTML = `
                <div class="no-audio-selected" id="noAudioSelected">
                    <p>Sélectionnez un périphérique audio pour afficher sa configuration.</p>
                </div>
            `;
            return;
        }

        motionFrontendUI.setStatus('Loading audio configuration...');
        loadAudioConfigSections(state.audioId)
            .then((data) => {
                const sections = data.sections || [];
                renderAudioConfigSections(audioConfigContainer, sections);
                applyDependVisibility();
                captureInitialValues();
                bindDynamicInputs();
            })
            .catch((error) => {
                motionFrontendUI.showToast(`Audio config error: ${error.message}`, 'error');
            })
            .finally(() => motionFrontendUI.setStatus('Ready'));
    }

    /**
     * Render audio configuration sections in the container.
     */
    function renderAudioConfigSections(container, sections) {
        const audioName = getAudioName(state.audioId);
        
        let html = `
            <div class="audio-config-header">
                <h3>Configuration audio: ${escapeHtml(audioName)}</h3>
            </div>
        `;

        for (const section of sections) {
            html += `
                <section class="settings-section audio-config-section collapsed" data-section="${section.slug}">
                    <header class="settings-section-title">
                        <button class="minimize" aria-expanded="false"></button>
                        <h2>${escapeHtml(section.title)}</h2>
                    </header>
                    <table class="settings" style="display: none;">
                        ${renderConfigItems(section.configs || [])}
                    </table>
                </section>
            `;
        }

        container.innerHTML = html;
        
        // Rebind minimize buttons with full accordion behavior
        bindAccordionButtons(container);
    }

    /**
     * Get audio device name from state.
     */
    function getAudioName(audioId) {
        const audio = state.audioDevices.find(a => a.id === audioId);
        return audio ? audio.name : audioId;
    }

    /**
     * Show dialog to add an audio device.
     */
    function showAddAudioDialog() {
        const existingModal = document.getElementById('addAudioModal');
        if (existingModal) {
            existingModal.remove();
        }

        const modal = document.createElement('div');
        modal.id = 'addAudioModal';
        modal.className = 'modal-overlay';
        modal.innerHTML = `
            <div class="modal-dialog modal-dialog-wide">
                <div class="modal-header">
                    <h3>Ajouter un périphérique audio</h3>
                    <button type="button" class="modal-close" id="closeAddAudioModal">&times;</button>
                </div>
                <div class="modal-body">
                    <div class="detected-audio-section">
                        <div class="section-header">
                            <label>Périphériques audio détectés</label>
                            <button type="button" class="button button-small" id="refreshDetectedAudio" title="Rafraîchir">
                                <span class="refresh-icon">↻</span>
                            </button>
                        </div>
                        <div id="detectedAudioList" class="detected-audio-list">
                            <div class="loading-audio">Détection en cours...</div>
                        </div>
                        <div class="filter-toggle">
                            <label class="checkbox-label">
                                <input type="checkbox" id="showFilteredAudio">
                                <span>Afficher les périphériques masqués</span>
                            </label>
                            <button type="button" class="button button-small button-text" id="manageAudioFiltersBtn">
                                Gérer les filtres
                            </button>
                        </div>
                    </div>
                    <div class="manual-entry-section">
                        <label class="section-label">Ou saisir manuellement</label>
                        <div class="form-group">
                            <label for="newAudioName">Nom du périphérique</label>
                            <input type="text" id="newAudioName" class="form-control" placeholder="Ex: Microphone USB">
                        </div>
                        <div class="form-group">
                            <label for="newAudioDeviceId">Identifiant du périphérique</label>
                            <input type="text" id="newAudioDeviceId" class="form-control" placeholder="hw:0,0 (Linux) ou index (Windows)">
                        </div>
                    </div>
                </div>
                <div class="modal-footer">
                    <button type="button" class="button button-secondary" id="cancelAddAudio">Annuler</button>
                    <button type="button" class="button button-primary" id="confirmAddAudio">Ajouter</button>
                </div>
            </div>
        `;
        document.body.appendChild(modal);

        // Load detected audio devices
        loadDetectedAudioDevices(false);

        // Event handlers
        const closeModal = () => modal.remove();

        document.getElementById('closeAddAudioModal').addEventListener('click', closeModal);
        document.getElementById('cancelAddAudio').addEventListener('click', closeModal);
        modal.addEventListener('click', (e) => {
            if (e.target === modal) closeModal();
        });

        document.getElementById('refreshDetectedAudio').addEventListener('click', () => {
            const showFiltered = document.getElementById('showFilteredAudio').checked;
            loadDetectedAudioDevices(showFiltered);
        });

        document.getElementById('showFilteredAudio').addEventListener('change', (e) => {
            loadDetectedAudioDevices(e.target.checked);
        });

        document.getElementById('manageAudioFiltersBtn').addEventListener('click', () => {
            showAudioFilterManagementDialog();
        });

        document.getElementById('confirmAddAudio').addEventListener('click', () => {
            const name = document.getElementById('newAudioName').value.trim();
            const deviceId = document.getElementById('newAudioDeviceId').value.trim();
            addAudioDevice(name, deviceId).then(closeModal);
        });

        // Allow Enter key to submit
        modal.querySelector('.manual-entry-section').addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                document.getElementById('confirmAddAudio').click();
            }
        });
    }

    /**
     * Load detected audio devices from the server.
     */
    function loadDetectedAudioDevices(includeFiltered) {
        const listContainer = document.getElementById('detectedAudioList');
        if (!listContainer) return;

        listContainer.innerHTML = '<div class="loading-audio">Détection en cours...</div>';

        const url = `/api/audio/detect/${includeFiltered ? '?include_filtered=true' : ''}`;
        apiGet(url)
            .then((data) => {
                renderDetectedAudioDevices(data.devices || [], data.filter_patterns || []);
            })
            .catch((error) => {
                listContainer.innerHTML = `<div class="error-message">Erreur: ${escapeHtml(error.message)}</div>`;
            });
    }

    /**
     * Render detected audio devices in the list.
     */
    function renderDetectedAudioDevices(devices, filterPatterns) {
        const listContainer = document.getElementById('detectedAudioList');
        if (!listContainer) return;

        if (devices.length === 0) {
            listContainer.innerHTML = '<div class="no-audio-found">Aucun périphérique audio détecté</div>';
            return;
        }

        const html = devices.map((device) => {
            const isFiltered = isMatchingAudioFilter(device, filterPatterns);
            const filteredClass = isFiltered ? 'audio-filtered' : '';
            const sourceIcon = getAudioSourceIcon(device.source_type);
            
            return `
                <div class="detected-audio-item ${filteredClass}" 
                     data-device-id="${escapeHtml(device.device_id)}"
                     data-name="${escapeHtml(device.name)}">
                    <div class="audio-icon">${sourceIcon}</div>
                    <div class="audio-info">
                        <div class="audio-name">${escapeHtml(device.name)}</div>
                        <div class="audio-device-id">${escapeHtml(device.device_id)}</div>
                        ${device.driver ? `<div class="audio-driver">${escapeHtml(device.driver)}</div>` : ''}
                    </div>
                    <div class="audio-actions">
                        <button type="button" class="button button-small button-primary select-audio-btn">
                            Sélectionner
                        </button>
                        ${!isFiltered ? `
                            <button type="button" class="button button-small button-text hide-audio-btn" title="Masquer">
                                👁️‍🗨️
                            </button>
                        ` : ''}
                    </div>
                </div>
            `;
        }).join('');

        listContainer.innerHTML = html;

        // Bind click events
        listContainer.querySelectorAll('.select-audio-btn').forEach((btn) => {
            btn.addEventListener('click', (e) => {
                const item = e.target.closest('.detected-audio-item');
                const deviceId = item.dataset.deviceId;
                const name = item.dataset.name;
                
                document.getElementById('newAudioName').value = name;
                document.getElementById('newAudioDeviceId').value = deviceId;
                
                // Highlight selected
                listContainer.querySelectorAll('.detected-audio-item').forEach(el => el.classList.remove('selected'));
                item.classList.add('selected');
            });
        });

        listContainer.querySelectorAll('.hide-audio-btn').forEach((btn) => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                const item = e.target.closest('.detected-audio-item');
                const name = item.dataset.name;
                
                // Add filter pattern for this audio device
                addAudioFilterPattern(escapeRegex(name));
            });
        });
    }

    /**
     * Check if an audio device matches any filter pattern.
     */
    function isMatchingAudioFilter(device, patterns) {
        for (const pattern of patterns) {
            try {
                const regex = new RegExp(pattern, 'i');
                if (regex.test(device.name) || regex.test(device.driver) || regex.test(device.device_id)) {
                    return true;
                }
            } catch (e) {
                // Invalid regex, skip
            }
        }
        return false;
    }

    /**
     * Get icon for audio source type.
     */
    function getAudioSourceIcon(sourceType) {
        const icons = {
            'alsa': '🎤',
            'wasapi': '🔊',
            'dshow': '🎙️',
        };
        return icons[sourceType] || '🎤';
    }

    /**
     * Add an audio filter pattern.
     */
    function addAudioFilterPattern(pattern) {
        apiPut('/api/audio/filters/', { pattern })
            .then(() => {
                motionFrontendUI.showToast('Périphérique audio masqué', 'success');
                const showFiltered = document.getElementById('showFilteredAudio')?.checked || false;
                loadDetectedAudioDevices(showFiltered);
            })
            .catch((error) => {
                motionFrontendUI.showToast(`Erreur: ${error.message}`, 'error');
            });
    }

    /**
     * Show dialog to manage audio filter patterns.
     */
    function showAudioFilterManagementDialog() {
        const existingModal = document.getElementById('audioFilterManagementModal');
        if (existingModal) {
            existingModal.remove();
        }

        const modal = document.createElement('div');
        modal.id = 'audioFilterManagementModal';
        modal.className = 'modal-overlay';
        modal.innerHTML = `
            <div class="modal-dialog">
                <div class="modal-header">
                    <h3>Gérer les filtres audio</h3>
                    <button type="button" class="modal-close" id="closeAudioFilterModal">&times;</button>
                </div>
                <div class="modal-body">
                    <p class="filter-info">Les périphériques correspondant à ces motifs regex seront masqués par défaut.</p>
                    <div id="audioFilterPatternsList" class="filter-patterns-list">
                        <div class="loading">Chargement...</div>
                    </div>
                    <div class="add-filter-section">
                        <input type="text" id="newAudioFilterPattern" class="form-control" placeholder="Nouveau motif regex...">
                        <button type="button" class="button button-primary" id="addAudioFilterPatternBtn">Ajouter</button>
                    </div>
                </div>
                <div class="modal-footer">
                    <button type="button" class="button button-secondary" id="closeAudioFilterModalBtn">Fermer</button>
                </div>
            </div>
        `;
        document.body.appendChild(modal);

        // Load current patterns
        loadAudioFilterPatterns();

        // Event handlers
        const closeModal = () => modal.remove();
        document.getElementById('closeAudioFilterModal').addEventListener('click', closeModal);
        document.getElementById('closeAudioFilterModalBtn').addEventListener('click', closeModal);
        modal.addEventListener('click', (e) => {
            if (e.target === modal) closeModal();
        });

        document.getElementById('addAudioFilterPatternBtn').addEventListener('click', () => {
            const pattern = document.getElementById('newAudioFilterPattern').value.trim();
            if (pattern) {
                addAudioFilterPattern(pattern);
                document.getElementById('newAudioFilterPattern').value = '';
                loadAudioFilterPatterns();
            }
        });
    }

    /**
     * Load audio filter patterns from server.
     */
    function loadAudioFilterPatterns() {
        const listContainer = document.getElementById('audioFilterPatternsList');
        if (!listContainer) return;

        apiGet('/api/audio/filters/')
            .then((data) => {
                const patterns = data.patterns || [];
                if (patterns.length === 0) {
                    listContainer.innerHTML = '<div class="no-patterns">Aucun filtre défini</div>';
                    return;
                }

                const html = patterns.map((pattern) => `
                    <div class="filter-pattern-item">
                        <code>${escapeHtml(pattern)}</code>
                        <button type="button" class="button button-small button-danger remove-pattern-btn" data-pattern="${escapeHtml(pattern)}">
                            ✕
                        </button>
                    </div>
                `).join('');

                listContainer.innerHTML = html;

                // Bind remove buttons
                listContainer.querySelectorAll('.remove-pattern-btn').forEach((btn) => {
                    btn.addEventListener('click', (e) => {
                        const pattern = e.target.dataset.pattern;
                        removeAudioFilterPattern(pattern);
                    });
                });
            })
            .catch((error) => {
                listContainer.innerHTML = `<div class="error-message">Erreur: ${escapeHtml(error.message)}</div>`;
            });
    }

    /**
     * Remove an audio filter pattern.
     */
    function removeAudioFilterPattern(pattern) {
        apiDelete('/api/audio/filters/', { pattern })
            .then(() => {
                loadAudioFilterPatterns();
                motionFrontendUI.showToast('Filtre supprimé', 'success');
            })
            .catch((error) => {
                motionFrontendUI.showToast(`Erreur: ${error.message}`, 'error');
            });
    }

    /**
     * Add a new audio device.
     */
    function addAudioDevice(name, deviceId) {
        motionFrontendUI.setStatus('Adding audio device...');
        return apiPost('/api/config/audio/add/', { name, device_id: deviceId })
            .then((result) => {
                motionFrontendUI.showToast(`Périphérique audio "${result.audio.name}" ajouté`, 'success');
                // Update audio devices list
                state.audioDevices.push(result.audio);
                // Refresh audio list
                refreshAudioList();
                // Auto-select the new device
                state.audioId = result.audio.id;
                const audioSelect = document.getElementById('audioSelect');
                if (audioSelect) {
                    audioSelect.value = result.audio.id;
                }
                // Load and display audio config
                refreshAudioConfig();
                // Enable remove button
                updateRemoveAudioButtonState();
                return result;
            })
            .catch((error) => {
                motionFrontendUI.showToast(`Erreur ajout périphérique audio: ${error.message}`, 'error');
                throw error;
            })
            .finally(() => motionFrontendUI.setStatus('Ready'));
    }

    /**
     * Delete an audio device.
     */
    function deleteAudioDevice(audioId) {
        if (!confirm('Êtes-vous sûr de vouloir supprimer ce périphérique audio ?')) {
            return Promise.resolve();
        }
        
        motionFrontendUI.setStatus('Deleting audio device...');
        return apiDelete(`/api/config/audio/${audioId}/delete/`)
            .then((result) => {
                motionFrontendUI.showToast('Périphérique audio supprimé', 'success');
                // Remove from state
                state.audioDevices = state.audioDevices.filter(a => a.id !== audioId);
                // Clear selection
                state.audioId = null;
                const audioSelect = document.getElementById('audioSelect');
                if (audioSelect) {
                    audioSelect.value = '';
                }
                // Refresh UI
                refreshAudioList();
                refreshAudioConfig();
                // Update remove button state
                updateRemoveAudioButtonState();
                return result;
            })
            .catch((error) => {
                motionFrontendUI.showToast(`Erreur suppression: ${error.message}`, 'error');
                throw error;
            })
            .finally(() => motionFrontendUI.setStatus('Ready'));
    }

    /**
     * Refresh the audio device list from server.
     */
    function refreshAudioList() {
        apiGet('/api/config/audio/list/')
            .then((data) => {
                const audioDevices = data.audio_devices || [];
                state.audioDevices = audioDevices;
                
                // Update audio select dropdown
                const audioSelect = document.getElementById('audioSelect');
                if (audioSelect) {
                    const currentValue = audioSelect.value;
                    audioSelect.innerHTML = '<option value="">-- Sélectionner audio --</option>';
                    audioDevices.forEach((audio) => {
                        const option = document.createElement('option');
                        option.value = audio.id;
                        option.textContent = audio.name;
                        audioSelect.appendChild(option);
                    });
                    // Restore selection if still exists
                    if (audioDevices.some(a => a.id === currentValue)) {
                        audioSelect.value = currentValue;
                    }
                    audioSelect.disabled = audioDevices.length === 0;
                }

                // Update remove button state
                updateRemoveAudioButtonState();
            })
            .catch((error) => {
                console.error('Failed to refresh audio list:', error);
            });
    }

    /**
     * Update remove audio button state.
     */
    function updateRemoveAudioButtonState() {
        const remAudioButton = document.getElementById('remAudioButton');
        if (remAudioButton) {
            remAudioButton.disabled = !state.audioId;
        }
    }

    /**
     * Push audio configuration to server.
     */
    function pushAudioConfig(payload, audioId) {
        if (!audioId) return Promise.resolve();
        const url = `/api/config/audio/${audioId}/`;
        motionFrontendUI.setStatus('Saving audio configuration...');
        return apiPost(url, payload)
            .then(() => motionFrontendUI.showToast('Configuration audio enregistrée', 'success'))
            .catch((error) => {
                motionFrontendUI.showToast(`Erreur: ${error.message}`, 'error');
                throw error;
            })
            .finally(() => motionFrontendUI.setStatus('Ready'));
    }

    /**
     * Bind audio event handlers.
     */
    function bindAudioButtons() {
        const addAudioButton = document.getElementById('addAudioButton');
        if (addAudioButton) {
            addAudioButton.addEventListener('click', () => showAddAudioDialog());
        }

        const remAudioButton = document.getElementById('remAudioButton');
        if (remAudioButton) {
            remAudioButton.addEventListener('click', () => {
                if (state.audioId) {
                    deleteAudioDevice(state.audioId);
                }
            });
        }

        const audioSelect = document.getElementById('audioSelect');
        if (audioSelect) {
            audioSelect.addEventListener('change', () => {
                state.audioId = audioSelect.value || null;
                refreshAudioConfig();
                updateRemoveAudioButtonState();
            });
        }
    }

    /**
     * Initialize audio management.
     */
    function initAudioManagement() {
        bindAudioButtons();
        refreshAudioList();
        updateRemoveAudioButtonState();
    }

    // ========================================================================
    // RTSP Streaming Functions
    // ========================================================================

    /**
     * Check RTSP server status (FFmpeg availability).
     */
    async function checkRTSPStatus() {
        try {
            const data = await apiGet('/api/rtsp/');
            return data;
        } catch (err) {
            console.error('Failed to check RTSP status:', err);
            return { ffmpeg_available: false, streams: {} };
        }
    }

    /**
     * Get RTSP stream status for a camera.
     */
    async function getRTSPStreamStatus(cameraId) {
        try {
            const data = await apiGet(`/api/rtsp/${cameraId}/`);
            return data;
        } catch (err) {
            console.error('Failed to get RTSP stream status:', err);
            return { is_running: false, error: err.message };
        }
    }

    /**
     * Start RTSP stream for current camera.
     */
    async function startRTSPStream(cameraId, options = {}) {
        const cid = cameraId || state.cameraId;
        if (!cid) return;

        setStatus(_('Starting RTSP stream...'));
        
        try {
            const data = await apiPost(`/api/rtsp/${cid}/`, {
                action: 'start',
                video_bitrate: options.video_bitrate || 2000
            });
            
            if (data.status === 'ok') {
                setStatus(_('RTSP stream started'));
                updateRTSPUI(cid, data);
            } else {
                setStatus(_('RTSP stream error') + ': ' + (data.error || 'Unknown error'));
            }
            
            return data;
        } catch (err) {
            setStatus(_('RTSP error: %s').replace('%s', err.message));
            console.error('Failed to start RTSP stream:', err);
            return { status: 'error', error: err.message };
        }
    }

    /**
     * Stop RTSP stream for current camera.
     */
    async function stopRTSPStream(cameraId) {
        const cid = cameraId || state.cameraId;
        if (!cid) return;

        setStatus(_('Stopping RTSP stream...'));
        
        try {
            const data = await apiPost(`/api/rtsp/${cid}/`, {
                action: 'stop'
            });
            
            if (data.status === 'ok') {
                setStatus(_('RTSP stream stopped'));
                updateRTSPUI(cid, { is_running: false });
            }
            
            return data;
        } catch (err) {
            setStatus(_('RTSP error: %s').replace('%s', err.message));
            console.error('Failed to stop RTSP stream:', err);
            return { status: 'error', error: err.message };
        }
    }

    /**
     * Update RTSP UI elements based on stream status.
     * Now uses camera-specific element IDs and works with toggle-based enable/disable.
     */
    function updateRTSPUI(cameraId, status) {
        // Get camera-specific elements
        const urlDisplay = document.getElementById(`rtspUrlDisplay_${cameraId}`);
        const statusBadge = document.getElementById(`rtspStatusBadge_${cameraId}`);
        const audioBadge = document.getElementById(`rtspAudioBadge_${cameraId}`);
        const errorDisplay = document.getElementById(`rtspError_${cameraId}`);
        
        if (status.is_running) {
            if (statusBadge) {
                statusBadge.textContent = _('RTSP stream active');
                statusBadge.className = 'rtsp-status active';
            }
            if (urlDisplay) {
                // Replace {host} placeholder with actual host
                const host = window.location.hostname;
                const rtspUrl = (status.rtsp_url || '').replace('{host}', host);
                urlDisplay.innerHTML = `
                    <span class="stream-url">${rtspUrl}</span>
                    <button type="button" class="btn-copy" onclick="navigator.clipboard.writeText('${rtspUrl}')" title="${_('Copy RTSP URL')}">📋</button>
                `;
                urlDisplay.style.display = 'block';
            }
            if (audioBadge) {
                audioBadge.textContent = status.has_audio ? _('RTSP with audio') : _('RTSP video only');
                audioBadge.className = 'rtsp-audio-badge ' + (status.has_audio ? 'with-audio' : 'no-audio');
                audioBadge.style.display = 'inline-block';
            }
        } else {
            if (statusBadge) {
                statusBadge.textContent = _('RTSP stream stopped');
                statusBadge.className = 'rtsp-status stopped';
            }
            if (urlDisplay) {
                urlDisplay.style.display = 'none';
            }
            if (audioBadge) {
                audioBadge.style.display = 'none';
            }
        }
        
        // Show error if any
        if (errorDisplay) {
            if (status.error) {
                errorDisplay.textContent = status.error;
                errorDisplay.style.display = 'block';
            } else {
                errorDisplay.style.display = 'none';
            }
        }
    }

    /**
     * Refresh RTSP section for current camera.
     * Called after camera config sections are loaded to update RTSP controls status.
     */
    async function refreshRTSPSection() {
        if (!state.cameraId) return;
        
        // Check if RTSP status badge exists for this camera (means the section is rendered)
        const statusBadge = document.getElementById(`rtspStatusBadge_${state.cameraId}`);
        if (!statusBadge) return;  // RTSP section not yet rendered
        
        // Check FFmpeg availability first
        const serverStatus = await checkRTSPStatus();
        
        if (!serverStatus.ffmpeg_available) {
            // Show warning in the RTSP section
            statusBadge.textContent = _('FFmpeg not available');
            statusBadge.className = 'rtsp-status error';
            const errorDisplay = document.getElementById(`rtspError_${state.cameraId}`);
            if (errorDisplay) {
                errorDisplay.textContent = _('FFmpeg is required for RTSP streaming. Please install FFmpeg.');
                errorDisplay.style.display = 'block';
            }
            return;
        }
        
        // Get stream status for this camera
        const streamStatus = await getRTSPStreamStatus(state.cameraId);
        updateRTSPUI(state.cameraId, streamStatus);
    }

    /**
     * Initialize RTSP controls.
     */
    function initRTSPControls() {
        // Refresh RTSP status when camera config is loaded
        const cameraSelect = document.getElementById('cameraSelect');
        if (cameraSelect) {
            cameraSelect.addEventListener('change', () => {
                // Delay to allow config to load
                setTimeout(() => {
                    if (state.cameraId) {
                        refreshRTSPSection();
                    }
                }, 500);
            });
        }
    }

    // Expose RTSP functions globally for inline onclick handlers
    window.startRTSPStream = startRTSPStream;
    window.stopRTSPStream = stopRTSPStream;
    window.updateRTSPUI = updateRTSPUI;

    motionFrontendUI.onReady(init);
    motionFrontendUI.onReady(initUserManagement);
    motionFrontendUI.onReady(initAudioManagement);
    motionFrontendUI.onReady(initRTSPControls);
})(window, document, window.fetch);
