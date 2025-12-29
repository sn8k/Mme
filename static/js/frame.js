/* File Version: 0.2.0 */
(function (window, document) {
    'use strict';

    const context = window.motionFrontendContext || {};
    let timer;

    function refresh() {
        const img = document.getElementById('cameraFrame');
        if (!img || !context.cameraId) {
            return;
        }
        img.src = `${context.staticPath}/frame/${context.cameraId}/?_ts=${Date.now()}`;
    }

    function start() {
        refresh();
        timer = window.setInterval(refresh, Math.max(2000, context.frameRefreshInterval || 5000));
    }

    function stop() {
        if (timer) {
            clearInterval(timer);
            timer = null;
        }
    }

    document.addEventListener('visibilitychange', () => {
        if (document.hidden) {
            stop();
        } else {
            start();
        }
    });

    motionFrontendUI.onReady(start);
})(window, document);
