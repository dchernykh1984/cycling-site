from agent.sources import parse_sources


def test_website_source():
    result = parse_sources("https://changan-race.kz/ru/")
    assert len(result) == 1
    assert result[0].kind == "website"
    assert result[0].fetch_url == "https://changan-race.kz/ru/"


def test_public_channel_and_post_link():
    result = parse_sources("https://t.me/roadcyclingkz\nhttps://t.me/mystartkz/903")
    urls = {s.fetch_url for s in result}
    assert urls == {"https://t.me/s/roadcyclingkz", "https://t.me/s/mystartkz"}  # post id dropped
    assert all(s.kind == "tg_public" for s in result)


def test_private_telegram_marked_unfetchable():
    result = parse_sources("https://t.me/+3mTEnASuHG40MTRi\nhttps://t.me/c/1949598843/1")
    assert len(result) == 2
    assert all(s.kind == "tg_private" and s.fetch_url is None for s in result)


def test_telegram_line_with_handles_and_links_deduped():
    # Mixed line: handles, a quoted display name (ignored), and a link that repeats a handle.
    line = 'telegram: @almatyriders , "RideBikes", @roadbikealmaty , https://t.me/velokz (@velokz)'
    result = parse_sources(line)
    urls = {s.fetch_url for s in result}
    assert "https://t.me/s/almatyriders" in urls
    assert "https://t.me/s/roadbikealmaty" in urls
    # the link and the @handle both point to the same channel -> one source, not two
    assert "https://t.me/s/velokz" in urls
    assert len(result) == 3


def test_blank_and_comment_lines_ignored():
    result = parse_sources("\n# a comment\n   \nhttps://velomania.kz/")
    assert len(result) == 1
    assert result[0].fetch_url == "https://velomania.kz/"
