"""The pre-commit hook that keeps hex colours out of the site's templates (scripts/check_template_colours.py)."""

from scripts.check_template_colours import colours, main


def _template(tmp_path, text):
    path = tmp_path / "page.html"
    path.write_text(text)
    return str(path)


def _listing(tmp_path, *lines):
    path = tmp_path / "allowed.txt"
    path.write_text("# header\n" + "".join(f"{line}\n" for line in lines))
    return path


def test_a_colour_in_css_markup_or_script_is_found():
    text = "<style>.a { color: #2c3e50; background:#FFF }</style><path fill='#4285F4'/>{ color: '#0d6efd' }"
    assert colours(text) == ["#2c3e50", "#FFF", "#4285F4", "#0d6efd"]


def test_comments_anchors_and_character_references_are_not_colours():
    text = (
        "{% comment %}issue #118{% endcomment %}{# issue #229 #}<!-- #fff -->/* #000 */\n"
        "  // issues #111, #113\n"
        "<a href='#add'>x</a><a href=\"#bad\"></a><a data-bs-target='#cafe'></a>&#123; https://example.com/#abc"
        "{% url 'x' %}#add{{ link }}#abc"
    )
    assert colours(text) == []


def test_a_new_colour_fails_and_a_listed_one_passes(tmp_path):
    template = _template(tmp_path, "<style>.a { color: #2c3e50 }</style>")
    assert main([template], _listing(tmp_path)) == 1
    assert main([template], _listing(tmp_path, f"{template} #2C3E50")) == 0


def test_a_listed_colour_that_is_gone_fails_so_the_list_shrinks(tmp_path):
    template = _template(tmp_path, "<style>.a { color: var(--bs-body-color) }</style>")
    assert main([template], _listing(tmp_path, f"{template} #2c3e50")) == 1


def test_the_site_templates_hold_only_the_listed_colours():
    assert main() == 0
