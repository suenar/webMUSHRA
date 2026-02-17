// ============================================================
// Google Forms Integration for webMUSHRA (GitHub Pages)
//
// SETUP — only two things to change:
//   1. Set ENTRY_ID to your Google Form entry ID (see below)
//   2. Make sure index.html has this before </body>:
//        <script src="google-forms-submit.js"></script>
// ============================================================

(function () {
    'use strict';

    // ── EDIT THESE TWO LINES ────────────────────────────────
    var FORM_ID  = '1FAIpQLScW0skfGpSb7ZIH-DTBlvYP0qQZ9oYU0hNZiShQbnJYcs2j6A';
    var ENTRY_ID = 'entry.1260314240';   // e.g. 'entry.123456789'
    // ────────────────────────────────────────────────────────

    var ACTION           = 'https://docs.google.com/forms/d/e/' + FORM_ID + '/formResponse';
    var listenerAttached = false;

    // ── 1. WAIT FOR THE BUTTON ───────────────────────────────
    // webMUSHRA injects the finish page into the DOM dynamically,
    // so the button doesn't exist at page-load time.
    // MutationObserver keeps watching until it appears.

    function tryAttach() {
        if (listenerAttached) { return; }
        var btn = document.getElementById('send_results');
        if (!btn) { return; }
        btn.addEventListener('click', onSendClick);
        listenerAttached = true;
        console.log('[GForms] Listener attached to #send_results.');
    }

    new MutationObserver(tryAttach)
        .observe(document.body, { childList: true, subtree: true });

    window.addEventListener('load', function () {
        console.log('[GForms] Script loaded.');
        tryAttach();
    });

    // ── 2. ON CLICK ──────────────────────────────────────────
    // Wait 800 ms so webMUSHRA finishes collecting its trial data
    // before we read it.

    function onSendClick() {
        console.log('[GForms] Send Results clicked — waiting 800 ms for data…');
        setTimeout(submit, 800);
    }

    // ── 3. COLLECT DATA ──────────────────────────────────────

    function collectData() {
        var payload = {
            timestamp  : new Date().toISOString(),
            userAgent  : navigator.userAgent,
            trials     : null,
            formFields : {}
        };

        // webMUSHRA keeps trial data in one of these globals
        var candidates = [
            window.session,
            window._session,
            window.pageManager  && window.pageManager.session,
            window._pageManager && window._pageManager.session
        ];

        for (var i = 0; i < candidates.length; i++) {
            if (candidates[i]) {
                payload.trials = candidates[i];
                console.log('[GForms] Trial data found at candidate[' + i + '].');
                break;
            }
        }

        // Also capture any visible form fields (email, age, etc.)
        document.querySelectorAll('input, textarea, select').forEach(function (el) {
            var key = el.name || el.id;
            if (key && el.value) {
                payload.formFields[key] = el.value;
            }
        });

        if (!payload.trials) {
            console.warn('[GForms] No trial data found — only form fields will be saved.');
        }

        return payload;
    }

    // ── 4. SUBMIT + BACKUP ───────────────────────────────────

    function submit() {
        var data    = collectData();
        var jsonStr = JSON.stringify(data, null, 2);
        console.log('[GForms] Submitting payload:', data);

        var fd = new FormData();
        fd.append(ENTRY_ID, jsonStr);          // ← uses ENTRY_ID, defined above

        fetch(ACTION, { method: 'POST', mode: 'no-cors', body: fd })
            .then(function () {
                console.log('[GForms] Submitted to Google Forms successfully!');
                alert('✅ Results submitted!\n\nA backup file will now download.');
                downloadJSON(jsonStr, 'results');
            })
            .catch(function (err) {
                console.error('[GForms] Submission failed:', err);
                alert('⚠️ Online submission failed.\nPlease email the backup file to the researcher.');
                downloadJSON(jsonStr, 'results_BACKUP');
            });
    }

    function downloadJSON(jsonStr, prefix) {
        var blob = new Blob([jsonStr], { type: 'application/json' });
        var url  = URL.createObjectURL(blob);
        var a    = document.createElement('a');
        a.href     = url;
        a.download = prefix + '_' + Date.now() + '.json';
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
        console.log('[GForms] Backup downloaded.');
    }

}());
