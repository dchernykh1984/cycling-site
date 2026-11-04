(function () {
    // The charts of the owners' statistics page (stats/templates/stats/dashboard.html, issue #184).
    if (!window.Chart) return;

    // The colours are the skin's, read off the page. The first line is the one the chart is about, in
    // the colour of links: every skin keeps that readable on its own background, which its primary
    // colour is not (Lux keeps a near-black one in its dark mode). A second line is grey and dashed,
    // told apart by more than its colour.
    var style = getComputedStyle(document.body);
    function colour(name) { return style.getPropertyValue(name).trim(); }
    var looks = [
        {borderColor: colour('--bs-link-color'), borderDash: []},
        {borderColor: colour('--bs-secondary-color'), borderDash: [6, 4]}
    ];
    Chart.defaults.color = colour('--bs-body-color');
    Chart.defaults.font.family = style.fontFamily;
    var charts = JSON.parse(document.getElementById('stats-charts').textContent);

    // Drawn once the skin's fonts are in: Chart.js keeps the widths it measured, and labels measured in
    // a fallback font ran into each other when the real one came.
    document.fonts.ready.then(function () {
        document.querySelectorAll('canvas[data-chart]').forEach(draw);
    });

    function draw(canvas) {
        var chart = charts[canvas.dataset.chart];
        new Chart(canvas, {
            type: 'line',
            data: {
                labels: chart.points.map(function (point) { return point.at; }),
                datasets: chart.names.map(function (name, line) {
                    var look = looks[line];
                    return {
                        label: name,
                        data: chart.points.map(function (point) { return point.values[line]; }),
                        borderColor: look.borderColor,
                        // Hollow, so the legend's sample shows the dash too.
                        backgroundColor: 'transparent',
                        borderDash: look.borderDash,
                        borderWidth: 2,
                        pointRadius: 0,
                        pointHoverRadius: 4
                    };
                })
            },
            options: {
                maintainAspectRatio: false,
                animation: false,
                // One tooltip for every line at the point under the finger, not only for the line hit.
                interaction: {mode: 'index', intersect: false},
                plugins: {legend: {display: chart.names.length > 1}},
                scales: {
                    x: {grid: {display: false}, ticks: {maxRotation: 0, autoSkip: true}},
                    y: {beginAtZero: true, ticks: {precision: 0}, grid: {color: colour('--bs-border-color')}}
                }
            }
        });
    }
}());
