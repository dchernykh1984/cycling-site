(function () {
    function getTheme() {
        return document.documentElement.getAttribute('data-bs-theme') || 'light';
    }

    function updateThemeIcon() {
        var theme = getTheme();
        document.querySelectorAll('.theme-icon').forEach(function (el) {
            el.innerHTML = theme === 'dark' ? '&#9728;' : '&#9790;';
        });
        document.querySelectorAll('.theme-label').forEach(function (el) {
            el.textContent = theme === 'dark' ? ' Dark' : ' Light';
        });
    }

    window.toggleTheme = function () {
        var next = getTheme() === 'light' ? 'dark' : 'light';
        document.documentElement.setAttribute('data-bs-theme', next);
        updateThemeIcon();

        if (document.body.dataset.authenticated === 'true') {
            var csrf = (document.cookie.match(/csrftoken=([^;]+)/) || [])[1] || '';
            fetch('/accounts/theme/', {
                method: 'POST',
                headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrf},
                body: JSON.stringify({theme: next})
            });
        } else {
            localStorage.setItem('theme', next);
        }
    };

    document.addEventListener('DOMContentLoaded', updateThemeIcon);

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

    syncStickyOffset();
    // Again once the document is parsed (in case this script ever moves above the navbar) and
    // once the web font has landed, since that is what changes the brand's line count.
    document.addEventListener('DOMContentLoaded', syncStickyOffset);
    window.addEventListener('load', syncStickyOffset);
    window.addEventListener('resize', syncStickyOffset);
    window.addEventListener('orientationchange', syncStickyOffset);
}());
