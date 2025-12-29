/* File Version: 0.1.0 */
(function (window, document, fetch) {
    'use strict';

    function updateField(id, value) {
        const node = document.getElementById(id);
        if (node) {
            node.textContent = value;
        }
    }

    function loadVersion() {
        fetch('/version/', { credentials: 'include' })
            .then((response) => response.json())
            .then((payload) => {
                updateField('frontendVersion', payload.frontend || '—');
                updateField('backendVersion', payload.backend || '—');
                updateField('gitCommit', payload.commit || '—');
                updateField('buildDate', payload.build_date || '—');
            })
            .catch(() => {
                updateField('frontendVersion', 'offline');
            });
    }

    document.addEventListener('DOMContentLoaded', loadVersion, { once: true });
})(window, document, window.fetch);
