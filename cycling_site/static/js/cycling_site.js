(function () {
    // The skin chooser (_skin_select.html), in the navbar and on the profile.
    function saveSkin(key) {
        if (document.body.dataset.authenticated !== 'true') {
            // A cookie, not the browser's storage: the server draws the page in the guest's skin.
            document.cookie = 'skin=' + key + ';path=/;max-age=31536000;samesite=lax';
            return Promise.resolve();
        }
        var csrf = (document.cookie.match(/csrftoken=([^;]+)/) || [])[1] || '';
        // From the template: the address carries the reader's language prefix, and the bare one
        // answers a POST with a redirect that drops the request body.
        return fetch(document.body.dataset.themeUrl, {
            method: 'POST',
            headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrf},
            body: JSON.stringify({theme: key})
        });
    }

    document.addEventListener('click', function (event) {
        var item = event.target.closest('.skin-select [data-skin-key]');
        if (!item) return;
        var key = item.dataset.skinKey, mode = item.dataset.mode;
        var saved = saveSkin(key);
        if (item.dataset.reload) {
            // Its stylesheet is not on this page; the next one carries it.
            saved.then(function () { location.reload(); });
            return;
        }
        document.documentElement.setAttribute('data-skin', key);
        document.documentElement.setAttribute('data-bs-theme', mode);
        // Every chooser on the page (navbar, profile) shows the new choice.
        document.querySelectorAll('.skin-select').forEach(function (chooser) {
            chooser.querySelector('.skin-icon').innerHTML = mode === 'dark' ? '&#9728;' : '&#9790;';
            var name = chooser.querySelector('.skin-name');
            if (name) name.textContent = item.textContent;
            chooser.querySelectorAll('[data-skin-key]').forEach(function (other) {
                var on = other.dataset.skinKey === key;
                other.classList.toggle('active', on);
                if (on) other.setAttribute('aria-current', 'true'); else other.removeAttribute('aria-current');
            });
        });
    });

    // Mark current section's nav-link as active based on the URL path
    document.addEventListener('DOMContentLoaded', function () {
        var currentPath = window.location.pathname;
        document.querySelectorAll('.navbar-nav .nav-link').forEach(function (link) {
            var href = link.getAttribute('href');
            if (href && href !== '/' && href !== '#' && currentPath.startsWith(href)) {
                link.classList.add('active');
                link.setAttribute('aria-current', 'page');
            }
        });
    });

    // The sticky category band on the participant list has to stop below the navbar, which is
    // itself sticky. Its height is not a constant: at the narrowest widths the brand wraps to a
    // second line and it grows from 88px to 128px, which would leave the band hidden behind it.
    // Measuring is the only honest way; the CSS carries a fallback for when this never runs.
    function syncStickyOffset() {
        var nav = document.querySelector('nav.navbar');
        if (!nav) {
            return;
        }
        var height = Math.round(nav.getBoundingClientRect().height);
        document.documentElement.style.setProperty('--ubt-sticky-top', height + 'px');
    }

    // Only the participant list has a band to offset, so no other page pays for the listeners.
    if (document.querySelector('.participant-category')) {
        syncStickyOffset();
        // Again once the document is parsed (in case this script ever moves above the navbar)
        // and once the web font has landed, since that is what changes the brand's line count.
        document.addEventListener('DOMContentLoaded', syncStickyOffset);
        window.addEventListener('load', syncStickyOffset);
        window.addEventListener('resize', syncStickyOffset);
        window.addEventListener('orientationchange', syncStickyOffset);
    }
}());

// Share buttons (issue #327). A page may pass the address to share in data-share-url (an event's
// invitation link, say) or define window.shareUrl() to build it from what is on screen (the
// calendar's filters); otherwise the page's own address is shared. Phones get their own share
// sheet; where there is none, the link is copied and the button says so for a moment.
(function () {
    document.addEventListener('click', function (e) {
        var btn = e.target.closest && e.target.closest('.share-btn');
        if (!btn) return;
        var url = btn.dataset.shareUrl || (window.shareUrl ? window.shareUrl() : window.location.href);
        var title = btn.dataset.shareTitle || document.title;
        if (navigator.share) {
            navigator.share({ title: title, url: url }).catch(function () { /* closed by the reader */ });
            return;
        }
        if (!navigator.clipboard) return;
        navigator.clipboard.writeText(url).then(function () {
            var label = btn.querySelector('.share-label');
            if (!label) return;
            var idle = label.textContent;
            label.textContent = btn.dataset.copiedLabel;
            // A narrow screen shows the icon alone; the confirmation must show there too, or a phone
            // without a share sheet copies the link without a word.
            var hidden = label.classList.contains('d-none');
            label.classList.remove('d-none');
            setTimeout(function () {
                label.textContent = idle;
                if (hidden) label.classList.add('d-none');
            }, 2000);
        });
    });
}());
