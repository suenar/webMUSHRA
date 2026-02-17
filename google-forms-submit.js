// Google Forms Integration for webMUSHRA
// This script intercepts the form submission and sends data to Google Forms

(function() {
    'use strict';
    
    // ========================================
    // CONFIGURATION - CHANGE THESE VALUES
    // ========================================
    var GOOGLE_FORM_ID = '1FAIpQLScW0skfGpSb7ZIH-DTBlvYP0qQZ9oYU0hNZiShQbnJYcs2j6A';
    var GOOGLE_FORM_ENTRY_ID = 'entry.XXXXXXXXX';  // REPLACE THIS with your entry ID
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
