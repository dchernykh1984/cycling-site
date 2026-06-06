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
}());
