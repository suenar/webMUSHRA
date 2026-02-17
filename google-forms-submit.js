// ============================================================
// Google Forms Integration for webMUSHRA (GitHub Pages)
//
// HOW TO USE:
//   1. Replace GOOGLE_FORM_ENTRY below with your real entry ID
//   2. Place this file in your webMUSHRA root folder
//   3. Add <script src="google-forms-submit.js"></script>
//      just before </body> in index.html
// ============================================================

(function () {
    'use strict';

    var GOOGLE_FORM_ID = '1FAIpQLScW0skfGpSb7ZIH-DTBlvYP0qQZ9oYU0hNZiShQbnJYcs2j6A';
    var GOOGLE_FORM_ENTRY_ID = 'entry.1260314240';  // REPLACE THIS with your entry ID
    // ========================================

    var FORM_ACTION      = 'https://docs.google.com/forms/d/e/' + GOOGLE_FORM_ID + '/formResponse';
    var listenerAttached = false;

    // ----------------------------------------------------------
    // 1. BUTTON FINDER
    //    The button ID is confirmed as "send_results".
    //    webMUSHRA injects the finish page dynamically, so we
    //    use a MutationObserver to wait for it to appear.
    // ----------------------------------------------------------
    function tryAttachListener() {
        if (listenerAttached) return;

        var btn = document.getElementById('send_results');
        if (!btn) return; // not rendered yet — observer will retry

        console.log('[GForms] "Send Results" button found — attaching listener.');
        btn.addEventListener('click', onSendClicked);
        listenerAttached = true;
    }

    // Watch the DOM for the dynamically injected finish page
    var observer = new MutationObserver(tryAttachListener);
    observer.observe(document.body, { childList: true, subtree: true });

    // Also try immediately after load (in case finish page is first)
    window.addEventListener('load', function () {
        console.log('[GForms] Google Forms integration loaded.');
        tryAttachListener();
    });

    // ----------------------------------------------------------
    // 2. CLICK HANDLER
    //    Wait 800 ms so webMUSHRA can finish writing session data
    //    before we read it.
    // ----------------------------------------------------------
    function onSendClicked() {
        console.log('[GForms] "Send Results" clicked — collecting data in 800 ms…');
        setTimeout(collectAndSubmit, 800);
    }

    // ----------------------------------------------------------
    // 3. DATA COLLECTION
    //    webMUSHRA stores results in a global session object.
    //    We try every known variable name used across versions.
    // ----------------------------------------------------------
    function collectData() {
        var payload = {
            timestamp : new Date().toISOString(),
            userAgent : navigator.userAgent,
            trials    : null,
            formFields: {}
        };

        // Try every known webMUSHRA session variable name
        var sessionCandidates = [
            window.session,
            window._session,
            window.pageManager  && window.pageManager.session,
            window._pageManager && window._pageManager.session,
            window.mushraSession,
        ];

        for (var i = 0; i < sessionCandidates.length; i++) {
            if (sessionCandidates[i]) {
                payload.trials = sessionCandidates[i];
                console.log('[GForms] Session data found (candidate index ' + i + ').');
                break;
            }
        }

        // Collect all visible form inputs (email, age, etc.)
        document.querySelectorAll('input, textarea, select').forEach(function (el) {
            var key = el.name || el.id;
            if (key && el.value) {
                payload.formFields[key] = el.value;
            }
        });

        if (!payload.trials) {
            console.warn('[GForms] Session data not found — only form fields will be saved.');
            console.log('[GForms] Tip: open an issue or check window.session in the console.');
        }

        return payload;
    }

    // ----------------------------------------------------------
    // 4. SUBMIT TO GOOGLE FORMS + DOWNLOAD BACKUP
    // ----------------------------------------------------------
    function collectAndSubmit() {
        var data    = collectData();
        var jsonStr = JSON.stringify(data, null, 2);

        console.log('[GForms] Payload ready:', data);

        var fd = new FormData();
        fd.append(GOOGLE_FORM_ENTRY, jsonStr);

        fetch(FORM_ACTION, { method: 'POST', mode: 'no-cors', body: fd })
            .then(function () {
                console.log('[GForms] Submitted to Google Forms successfully!');
                alert('✅ Results submitted!\n\nA backup file will now download to your computer.');
                downloadJSON(jsonStr, 'results');
            })
            .catch(function (err) {
                console.error('[GForms] Submission error:', err);
                alert('⚠️ Online submission failed.\nDownloading backup file — please email it to the researcher.');
                downloadJSON(jsonStr, 'results_BACKUP');
            });
    }

    function downloadJSON(jsonStr, prefix) {
        var blob   = new Blob([jsonStr], { type: 'application/json' });
        var url    = URL.createObjectURL(blob);
        var a      = document.createElement('a');
        a.href     = url;
        a.download = prefix + '_' + Date.now() + '.json';
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
        console.log('[GForms] Backup file downloaded.');
    }

})();

// Google Forms Integration for webMUSHRA
// This script intercepts the form submission and sends data to Google Forms

(function() {
    'use strict';
    
    // ========================================
    // CONFIGURATION - CHANGE THESE VALUES
    // ========================================
    var GOOGLE_FORM_ID = '1FAIpQLScW0skfGpSb7ZIH-DTBlvYP0qQZ9oYU0hNZiShQbnJYcs2j6A';
    var GOOGLE_FORM_ENTRY_ID = 'entry.1260314240';  // REPLACE THIS with your entry ID
    // ========================================
    
    var GOOGLE_FORM_ACTION = 'https://docs.google.com/forms/d/e/' + GOOGLE_FORM_ID + '/formResponse';
    
    // Wait for page to load
    window.addEventListener('load', function() {
        console.log('Google Forms integration loaded');
        
        // Find the submit button (try multiple selectors)
        var submitButton = document.getElementById('btnSend') || 
                          document.querySelector('button[type="submit"]') ||
                          document.querySelector('.btn-send');
        
        if (submitButton) {
            console.log('Submit button found:', submitButton);
            
            // Add our custom handler
            submitButton.addEventListener('click', function(e) {
                console.log('Submit button clicked - intercepting...');
                
                // Small delay to let webMUSHRA collect its data
                setTimeout(function() {
                    submitToGoogleForms();
                }, 500);
            });
        } else {
            console.warn('Submit button not found - will try alternative method');
            
            // Alternative: Monitor for form submissions
            document.addEventListener('submit', function(e) {
                console.log('Form submit detected');
                setTimeout(function() {
                    submitToGoogleForms();
                }, 500);
            });
        }
    });
    
    function submitToGoogleForms() {
        console.log('Preparing to submit to Google Forms...');
        
        // Collect data from webMUSHRA session
        var results = {
            timestamp: new Date().toISOString(),
            userAgent: navigator.userAgent,
            data: null
        };
        
        // Try to get webMUSHRA session data
        if (typeof _session !== 'undefined') {
            results.data = _session;
        } else if (typeof pageManager !== 'undefined' && pageManager.session) {
            results.data = pageManager.session;
        } else {
            // Collect all form inputs as fallback
            var formData = {};
            document.querySelectorAll('input, textarea, select').forEach(function(element) {
                if (element.name || element.id) {
                    var key = element.name || element.id;
                    formData[key] = element.value;
                }
            });
            results.data = formData;
        }
        
        var resultsJSON = JSON.stringify(results, null, 2);
        console.log('Results to submit:', resultsJSON);
        
        // Create FormData for Google Forms
        var googleFormData = new FormData();
        googleFormData.append(GOOGLE_FORM_ENTRY_ID, resultsJSON);
        
        // Submit to Google Forms
        fetch(GOOGLE_FORM_ACTION, {
            method: 'POST',
            mode: 'no-cors',
            body: googleFormData
        })
        .then(function() {
            console.log('Successfully submitted to Google Forms!');
            
            // Show success message
            alert('Results submitted successfully!\n\nA backup will also download.');
            
            // Download backup JSON
            downloadBackup(resultsJSON);
        })
        .catch(function(error) {
            console.error('Error submitting to Google Forms:', error);
            alert('There was an error submitting online.\n\nDownloading backup file...');
            downloadBackup(resultsJSON);
        });
    }
    
    function downloadBackup(jsonData) {
        var dataStr = 'data:text/json;charset=utf-8,' + encodeURIComponent(jsonData);
        var downloadAnchor = document.createElement('a');
        downloadAnchor.setAttribute('href', dataStr);
        downloadAnchor.setAttribute('download', 'webmushra_results_' + Date.now() + '.json');
        document.body.appendChild(downloadAnchor);
        downloadAnchor.click();
        downloadAnchor.remove();
        console.log('Backup file downloaded');
    }
})();
