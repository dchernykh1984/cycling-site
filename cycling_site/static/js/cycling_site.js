(function () {
    // The reader's own time zone, for the times the server writes into the pages that follow (issue
    // #344). Here rather than in base.html, so a skin with its own copy of base.html keeps it. An IANA
    // name is cookie-safe as it is; the server would not decode a percent-encoded one.
    try {
        var zone = Intl.DateTimeFormat().resolvedOptions().timeZone;
        var stored = document.cookie.match(/(?:^|; )tz=([^;]*)/);
        if (zone && (!stored || stored[1] !== zone)) {
            document.cookie = 'tz=' + zone + ';path=/;max-age=31536000;samesite=lax';
        }
    } catch (e) { /* no Intl: the site's default zone stands */ }

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
        // The menu's items, and the button of a skin on offer (_skin_offer.html).
        var item = event.target.closest('.skin-select [data-skin-key], .skin-offer [data-skin-key]');
        if (!item) return;
        var key = item.dataset.skinKey, mode = item.dataset.mode;
        var saved = saveSkin(key);
        if (item.dataset.reload) {
            // A skin of its own is coming or going: its stylesheet, script and templates with it.
            saved.then(function () { location.reload(); });
            return;
        }
        document.documentElement.setAttribute('data-skin', key);
        document.documentElement.setAttribute('data-bs-theme', mode);
        showSkin(key, mode);
    });

    // Every chooser on the page (navbar, profile) shows the skin the page is in.
    function showSkin(key, mode) {
        document.querySelectorAll('.skin-select').forEach(function (chooser) {
            chooser.querySelector('.skin-icon').innerHTML = mode === 'dark' ? '&#9790;' : '&#9728;';
            chooser.querySelectorAll('[data-skin-key]').forEach(function (item) {
                var on = item.dataset.skinKey === key;
                item.classList.toggle('active', on);
                if (on) item.setAttribute('aria-current', 'true'); else item.removeAttribute('aria-current');
                var name = chooser.querySelector('.skin-name');
                if (on && name) name.textContent = item.textContent;
            });
        });
    }

    // The server drew the choosers for the skin it knew of; on a guest's first visit after the
    // switch to the cookie, the early script in base.html has since moved the page to their old one.
    document.addEventListener('DOMContentLoaded', function () {
        var root = document.documentElement;
        showSkin(root.getAttribute('data-skin'), root.getAttribute('data-bs-theme'));
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

(function () {
    // Two downloads at a time, only near the viewport. Leave web threads free for people's marks.
    // A 503 means the server is busy with other people's previews: wait longer each time, with a
    // random spread so waiting pages do not come back together, and keep the card's place.
    var MAX_RETRIES = 12;
    var queue = [], active = 0, observer = null;
    function pump() {
        while (active < 2 && queue.length) {
            load(queue.shift());
        }
    }
    function frameOf(image) {
        return image.closest('[data-photo-preview]');
    }
    function unavailable(image) {
        var frame = frameOf(image);
        frame.querySelector('[data-photo-placeholder]').hidden = true;
        frame.querySelector('[data-photo-unavailable]').hidden = false;
    }
    function enqueue(image) {
        if (observer) {
            observer.observe(frameOf(image));  // queued again when it is, or comes back, into view
        } else {
            queue.push(image);
            pump();
        }
    }
    function retry(image, seconds) {
        image.retries = (image.retries || 0) + 1;
        if (image.retries > MAX_RETRIES) {
            unavailable(image);
            return;
        }
        var delay = Math.min(seconds * Math.pow(2, image.retries - 1), 30) * (0.5 + Math.random());
        setTimeout(function () { enqueue(image); }, delay * 1000);
    }
    function load(image) {
        active += 1;
        var controller = new AbortController();
        var timer = setTimeout(function () { controller.abort(); }, 10000);
        fetch(image.dataset.photoSrc, {signal: controller.signal}).then(function (response) {
            if (response.status === 503) {
                retry(image, Math.min(Number(response.headers.get('Retry-After')) || 2, 60));
                return null;
            }
            if (!response.ok) {
                throw new Error('preview unavailable');
            }
            return response.blob();
        }, function () {
            // Timed out or the connection dropped: the server may still finish and keep the preview.
            retry(image, 2);
            return null;
        }).then(function (blob) {
            if (!blob) return;
            var url = URL.createObjectURL(blob);
            image.onload = function () {
                URL.revokeObjectURL(url);
                image.hidden = false;
                frameOf(image).querySelector('[data-photo-placeholder]').hidden = true;
            };
            image.onerror = function () { URL.revokeObjectURL(url); unavailable(image); };
            image.src = url;
        }).catch(function () { unavailable(image); }).finally(function () {
            clearTimeout(timer);
            active -= 1;
            pump();
        });
    }
    var images = document.querySelectorAll('img[data-photo-src]');
    if (!images.length) return;
    images.forEach(function (image) {
        var placeholder = frameOf(image).querySelector('[data-photo-placeholder]');
        placeholder.textContent = placeholder.dataset.loadingLabel;
    });
    if ('IntersectionObserver' in window) {
        observer = new IntersectionObserver(function (entries) {
            entries.forEach(function (entry) {
                if (!entry.isIntersecting) return;
                observer.unobserve(entry.target);
                queue.push(entry.target.querySelector('img[data-photo-src]'));
            });
            pump();
        }, {rootMargin: '200px'});
    }
    images.forEach(enqueue);
}());
