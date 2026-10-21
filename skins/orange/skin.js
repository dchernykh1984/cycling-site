// UBT Almaty skin: lay the owner's home-page text out as cards, one per section.
//
// The text is the owner's rich text (.home-body), written as headings with paragraphs under them.
// Each h2 and everything up to the next h2 becomes one .ubt-section; whatever comes before the first
// h2, and the first section when its heading repeats the page title, becomes the wide intro card.
// Nothing is removed or reordered, so the words, links and their order stay exactly as written.
(function () {
    function sectionize(body) {
        var nodes = Array.prototype.slice.call(body.childNodes);
        if (!nodes.some(function (n) { return n.nodeName === 'H2'; })) return;
        var title = (document.querySelector('.ubt-hero-title') || {}).textContent || '';
        var sections = [];
        var current = null;
        nodes.forEach(function (node) {
            if (node.nodeName === 'H2' || !current) {
                current = document.createElement('section');
                current.className = 'ubt-section';
                sections.push(current);
            }
            current.appendChild(node);
        });
        sections.forEach(function (section, i) {
            var heading = section.querySelector(':scope > h2');
            var meaningful = Array.prototype.some.call(section.childNodes, function (n) {
                return n.nodeType === 1 || (n.nodeType === 3 && n.textContent.trim());
            });
            if (!meaningful) return;
            if (i === 0 && (!heading || heading.textContent.trim().toLowerCase() === title.trim().toLowerCase())) {
                section.classList.add('ubt-section-intro');
            }
            body.appendChild(section);
        });
        body.classList.add('ubt-sectioned');
    }

    function run() {
        document.querySelectorAll('.home-body').forEach(sectionize);
    }
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', run);
    else run();
}());
