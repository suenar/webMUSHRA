// ============================================================
// Google Forms Integration for webMUSHRA (GitHub Pages)
//
// SETUP:
//   1. FORM_ID — from your form URL: .../forms/d/e/<FORM_ID>/viewform
//   2. ENTRY_ID — "Get pre-filled link" → inspect name="entry.XXXXX" for one question
//   3. That question should be a **Paragraph** (not Short answer): large JSON, often 10k–80k chars
//   4. For GitHub Pages set remoteService: "" in YAML so write.php is not called (405)
//   5. index.html before </body>: <script src="google-forms-submit.js"></script>
// ============================================================

(function () {
    'use strict';

    // ── EDIT THESE TWO LINES ────────────────────────────────
    var FORM_ID  = '1FAIpQLSd7fIg9ohfsN01s8pcOpzx55LBzN0mrSCrWt6hRiO5tyHqbcw';
    var ENTRY_ID = 'entry.1336624633';   // e.g. 'entry.123456789'
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
    // Google Forms rejects large POST bodies (~413). Session objects contain
    // Stimulus references with AudioBuffers — JSON.stringify keeps enumerable
    // keys and blows up size. Export a compact, analysis-friendly shape only.

    function stimulusToPlain(s) {
        if (s == null) { return null; }
        if (typeof s === 'string') { return s; }
        var id = s.id;
        var fp = s.filepath;
        if (id == null && typeof s.getId === 'function') { id = s.getId(); }
        if (fp == null && typeof s.getFilepath === 'function') { fp = s.getFilepath(); }
        if (id == null && fp == null) { return String(s); }
        return { id: id, filepath: fp };
    }

    function responseToPlain(r) {
        if (r == null) { return null; }
        var o = {};
        var k;
        for (k in r) {
            if (!Object.prototype.hasOwnProperty.call(r, k)) { continue; }
            if (k === 'stimulus' || k === 'reference' || k === 'nonReference') {
                o[k] = stimulusToPlain(r[k]);
            } else {
                o[k] = r[k];
            }
        }
        return o;
    }

    function compactSession(sess) {
        if (!sess) { return null; }
        var out = {
            testId: sess.testId,
            uuid: sess.uuid,
            config: sess.config,
            participant: sess.participant ? {
                name: sess.participant.name,
                response: sess.participant.response
            } : null,
            trials: []
        };
        var trials = sess.trials || [];
        var i, j;
        for (i = 0; i < trials.length; i++) {
            var t = trials[i];
            var row = { id: t.id, type: t.type, responses: [] };
            var res = t.responses || [];
            for (j = 0; j < res.length; j++) {
                row.responses.push(responseToPlain(res[j]));
            }
            out.trials.push(row);
        }
        return out;
    }

    function collectData() {
        var payload = {
            timestamp  : new Date().toISOString(),
            userAgent  : navigator.userAgent,
            session    : null,
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
                payload.session = compactSession(candidates[i]);
                console.log('[GForms] Trial data found at candidate[' + i + '] (compact export).');
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

        if (!payload.session) {
            console.warn('[GForms] No trial data found — only form fields will be saved.');
        }

        return payload;
    }

    // ── 4. SUBMIT + BACKUP ───────────────────────────────────

    function submit() {
        var data    = collectData();
        // Compact JSON for Google (no pretty-print) to stay under size limits
        var jsonCompact = JSON.stringify(data);
        var jsonPretty  = JSON.stringify(data, null, 2);
        var charCount   = jsonCompact.length;
        console.log('[GForms] Submitting payload (compact JSON, ' + charCount + ' chars):', data);
        if (charCount > 45000) {
            console.warn('[GForms] Payload is large; Google may reject (413). Consider splitting across multiple form fields or use a Google Apps Script endpoint.');
        }

        var fd = new FormData();
        fd.append(ENTRY_ID, jsonCompact);

        // no-cors: response is opaque — we cannot see HTTP status (413/200).
        // Network errors still reject the promise.
        fetch(ACTION, { method: 'POST', mode: 'no-cors', body: fd })
            .then(function () {
                console.log('[GForms] POST to Google Forms finished (status not visible with no-cors). Check the form responses sheet.');
                alert('Results were sent to Google Forms.\n\nBecause of browser security, we cannot confirm the HTTP status. If nothing appears in your spreadsheet, check the console for size warnings (413 = payload too large).\n\nA JSON backup will download next.');
                downloadJSON(jsonPretty, 'results');
            })
            .catch(function (err) {
                console.error('[GForms] Submission failed (network):', err);
                alert('⚠️ Could not reach Google Forms (network error).\nPlease send the researcher the downloaded backup file.');
                downloadJSON(jsonPretty, 'results_BACKUP');
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
