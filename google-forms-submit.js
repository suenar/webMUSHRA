// ============================================================
// Google Forms Integration for webMUSHRA (GitHub Pages)
//
// SETUP:
//   1. FORM_ID — from your form URL: .../forms/d/e/<FORM_ID>/viewform
//   2. ENTRY_ID — "Get pre-filled link" → inspect name="entry.XXXXX" for one question
//   3. That question should be a **Paragraph** (not Short answer): large JSON, often 10k–80k chars
//   Payload keys (short): ts, ua, s, q | s.tr[] = trials: { i, rs } | rs MUSHRA: { x:{i,f}, c, m }
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

    // Stimulus → { i: id, f: filepath } (short keys)
    function stimulusToShort(s) {
        if (s == null) { return null; }
        if (typeof s === 'string') { return { i: s, f: null }; }
        var id = s.id;
        var fp = s.filepath;
        if (id == null && typeof s.getId === 'function') { id = s.getId(); }
        if (fp == null && typeof s.getFilepath === 'function') { fp = s.getFilepath(); }
        if (id == null && fp == null) { return { i: String(s), f: null }; }
        return { i: id, f: fp };
    }

    // MUSHRA: x=stimulus {i,f}, c=score, m=time (no comment, no trial type in parent)
    // Likert multi-stimulus: x=stimulus, lr=rating, m=time
    function compactResponse(r) {
        if (r == null) { return null; }
        if (r.stimulus != null && r.score != null) {
            return { x: stimulusToShort(r.stimulus), c: r.score, m: r.time };
        }
        if (r.stimulus != null && r.stimulusRating != null) {
            return { x: stimulusToShort(r.stimulus), lr: r.stimulusRating, m: r.time };
        }
        // Other types (no comment): short keys a/b/w/rc/nc
        var o = {};
        if (r.reference != null) { o.a = stimulusToShort(r.reference); }
        if (r.nonReference != null) { o.b = stimulusToShort(r.nonReference); }
        if (r.answer != null) { o.w = r.answer; }
        if (r.referenceScore != null) { o.rc = r.referenceScore; }
        if (r.nonReferenceScore != null) { o.nc = r.nonReferenceScore; }
        return o;
    }

    // Session: short keys (tid,u,cfg,p,tr) to shrink POST body for Google Forms
    function compactSession(sess) {
        if (!sess) { return null; }
        var out = {
            tid: sess.testId,
            u: sess.uuid,
            cfg: sess.config,
            p: sess.participant ? {
                n: sess.participant.name,
                r: sess.participant.response
            } : null,
            tr: []
        };
        var trials = sess.trials || [];
        var i, j;
        for (i = 0; i < trials.length; i++) {
            var t = trials[i];
            var row = { i: t.id, rs: [] };
            var res = t.responses || [];
            for (j = 0; j < res.length; j++) {
                row.rs.push(compactResponse(res[j]));
            }
            out.tr.push(row);
        }
        return out;
    }

    function collectData() {
        var payload = {
            ts: new Date().toISOString(),
            ua: navigator.userAgent,
            s: null,
            q: {}
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
                payload.s = compactSession(candidates[i]);
                console.log('[GForms] Trial data found at candidate[' + i + '] (compact export).');
                break;
            }
        }

        // Also capture any visible form fields (email, age, etc.)
        document.querySelectorAll('input, textarea, select').forEach(function (el) {
            var key = el.name || el.id;
            if (key && el.value) {
                payload.q[key] = el.value;
            }
        });

        if (!payload.s) {
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
