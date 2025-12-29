/* File Version: 0.2.2 */
(function (window, document) {
    'use strict';

    const motionFrontendUI = {
        readyQueue: [],
        statusElement: null,
        toastRegion: null,
        initialized: false
    };

    function domReady(handler) {
        if (document.readyState === 'complete' || document.readyState === 'interactive') {
            handler();
            return;
        }
        document.addEventListener('DOMContentLoaded', handler, { once: true });
    }

    function onReady(handler) {
        if (motionFrontendUI.initialized) {
            handler();
        } else {
            motionFrontendUI.readyQueue.push(handler);
        }
    }

    function flushReadyQueue() {
        motionFrontendUI.initialized = true;
        motionFrontendUI.readyQueue.forEach((fn) => {
            try {
                fn();
            } catch (e) {
                console.error('motionFrontendUI.onReady handler error', e);
            }
        });
        motionFrontendUI.readyQueue = [];
    }

    function initAccordions() {
        document.querySelectorAll('.settings-section-title .minimize').forEach((button) => {
            button.addEventListener('click', () => {
                button.classList.toggle('open');
                const expanded = button.classList.contains('open');
                button.setAttribute('aria-expanded', expanded.toString());
                const section = button.closest('.settings-section');
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

    function initRangeMirrors() {
        document.querySelectorAll('.range-field input[type="range"]').forEach((input) => {
            const target = input.parentElement?.querySelector('.range-value');
            if (!target) {
                return;
            }
            const update = () => {
                target.textContent = input.value;
            };
            input.addEventListener('input', update);
            update();
        });
    }

    function bindHelpMarks() {
        document.querySelectorAll('.help-mark').forEach((mark) => {
            mark.addEventListener('click', () => {
                const message = mark.getAttribute('aria-label') || mark.dataset.help || '';
                if (message) {
                    showToast(message, 'info');
                }
            });
        });
    }

    function ensureContainers() {
        motionFrontendUI.toastRegion = document.getElementById('toastRegion');
        if (!motionFrontendUI.toastRegion) {
            motionFrontendUI.toastRegion = document.createElement('div');
            motionFrontendUI.toastRegion.id = 'toastRegion';
            document.body.appendChild(motionFrontendUI.toastRegion);
        }
        motionFrontendUI.statusElement = document.getElementById('statusMessage');
    }

    function showToast(message, variant = 'info') {
        ensureContainers();
        const toast = document.createElement('div');
        toast.className = `toast toast-${variant}`;
        toast.textContent = message;
        motionFrontendUI.toastRegion.appendChild(toast);
        window.setTimeout(() => {
            toast.style.opacity = '0';
            toast.addEventListener('transitionend', () => toast.remove(), { once: true });
        }, 4000);
    }

    function setStatus(message) {
        ensureContainers();
        if (motionFrontendUI.statusElement) {
            motionFrontendUI.statusElement.textContent = message;
        }
    }

    function init() {
        initAccordions();
        initRangeMirrors();
        bindHelpMarks();
        ensureContainers();
    }

    domReady(init);
    window.addEventListener('load', flushReadyQueue, { once: true });

    motionFrontendUI.onReady = onReady;
    motionFrontendUI.showToast = showToast;
    motionFrontendUI.setStatus = setStatus;

    window.motionFrontendUI = motionFrontendUI;
})(window, document);
