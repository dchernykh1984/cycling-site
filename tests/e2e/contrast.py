"""How readable a colour is where it is drawn: WCAG contrast of what actually reaches the screen.

The browser does the colour work. Each colour is painted onto a 1x1 canvas over the backgrounds
beneath it -- the element's ancestors, from the page down -- and the pixel read back: that is the
colour after transparency -- of the colour itself and the opacity of the element and its
ancestors -- is blended in, and after any format (rgb, oklch, a wide-gamut color()) is brought
into sRGB. A colour the browser cannot read, or a way of drawing a flat colour cannot stand for
(filters, blend modes, gradients), is an error, never a pass.
"""

from playwright.sync_api import Locator, Page

_PAINT = """
(el, what) => {
  // Text drawn as a shadow: Bootstrap hides a focused select's text in Firefox (color: transparent)
  // and paints it with an unblurred, unshifted text-shadow instead.
  const textColour = (style) => {
    const shadow = style.textShadow.match(/^(.*\\))\\s+0px\\s+0px\\s+0px$/);
    const clear = style.color === 'transparent' || /,\\s*0\\)$/.test(style.color);
    return clear && shadow ? shadow[1] : style.color;
  };
  const canvas = () => {
    const g = document.createElement('canvas').getContext('2d', {willReadFrequently: true});
    g.canvas.width = g.canvas.height = 1;
    return g;
  };
  const paint = (g, value) => {
    g.fillStyle = '#010203';
    g.fillStyle = value;
    if (g.fillStyle === '#010203' && value.replace(/\\s/g, '') !== 'rgb(1,2,3)') {
      throw new Error('unknown colour format: ' + value);
    }
    g.fillRect(0, 0, 1, 1);
  };
  const chain = [];
  for (let node = el; node; node = node.parentElement) chain.unshift(node);
  for (const node of chain) {
    const style = getComputedStyle(node);
    // What a flat colour cannot stand for: refuse rather than report a contrast nobody sees.
    const unsupported = [
      style.filter !== 'none' && 'filter: ' + style.filter,
      style.mixBlendMode !== 'normal' && 'mix-blend-mode: ' + style.mixBlendMode,
      /gradient\\(/.test(style.backgroundImage) && 'a gradient background',
    ].find(Boolean);
    if (unsupported) throw new Error('cannot judge contrast through ' + unsupported + ' on ' + node.tagName);
  }
  const last = what === 'fill-beneath' ? chain.length - 1 : chain.length;
  // Paint chain[i] and everything drawn on it over what g already holds. An element's opacity
  // blends its whole group -- background, children, text -- with what lies beneath, as a browser
  // composites it: the group is drawn on a canvas of its own, then laid over at that opacity.
  const render = (i, g) => {
    if (i === last) {
      if (what === 'text') paint(g, textColour(getComputedStyle(el)));
      if (what.startsWith('colour:')) paint(g, what.slice(7));
      return;
    }
    const style = getComputedStyle(chain[i]);
    const group = canvas();
    group.drawImage(g.canvas, 0, 0);
    paint(group, style.backgroundColor);
    render(i + 1, group);
    g.globalAlpha = parseFloat(style.opacity);
    g.drawImage(group.canvas, 0, 0);
    g.globalAlpha = 1;
  };
  const g = canvas();
  // A page with no background of its own shows the canvas, white.
  paint(g, '#ffffff');
  render(0, g);
  return Array.from(g.getImageData(0, 0, 1, 1).data.slice(0, 3));
}
"""


def drawn(locator: Locator, what: str = "text") -> list[int]:
    """The sRGB colour of a locator's text ("text"), its fill ("fill"), or what lies under it."""
    return locator.evaluate(_PAINT, what)


def painted(page: Page, colour: str, over: str = "body") -> list[int]:
    """Any CSS colour as it would show over an element's backdrop (for testing this module)."""
    return page.locator(over).evaluate(_PAINT, f"colour:{colour}")


def _luminance(rgb):
    channels = [value / 255 for value in rgb]
    linear = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def ratio(first, second) -> float:
    lighter, darker = sorted((_luminance(first), _luminance(second)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


def legibility(locator: Locator) -> float:
    """Contrast of a locator's text against the colour right under it."""
    return ratio(drawn(locator, "text"), drawn(locator, "fill"))


def is_large(locator: Locator) -> bool:
    """WCAG large text: 24px, or 18.66px bold, which needs only 3:1."""
    size, weight = locator.evaluate(
        "el => [parseFloat(getComputedStyle(el).fontSize), +getComputedStyle(el).fontWeight]"
    )
    return size >= 24 or (size >= 18.66 and weight >= 700)
