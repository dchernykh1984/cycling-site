// A protocol drawn from its structured document: search, group filter, toggles, short and full
// view, and the details of a row whose columns do not fit.
//
// The reader's choices are kept by the document's own ids, not by position, so a live update that
// adds, removes or reorders groups and toggles (protocol-live.js swaps the whole document in and
// calls mount again) keeps what the reader chose: a group that disappeared falls back to "All
// categories", a toggle that disappeared is forgotten, a new toggle starts in its default.
(function () {
  "use strict";

  // columns: the sets of columns the reader turned on (true) or off (false) by hand.
  var state = { search: "", group: "", toggles: {}, columns: {}, full: false };
  // The letters the server folds to Latin (cycling_site/text_search.py), so a query in either
  // script matches a name written in either: "Che" and its Cyrillic spelling find "Chernykh".
  var foldTable = {};

  function searchWords(text) {
    var folded = "";
    for (var i = 0; i < text.length; i += 1) {
      var letter = text.charAt(i);
      folded += Object.prototype.hasOwnProperty.call(foldTable, letter) ? foldTable[letter] : letter;
    }
    return folded.toLowerCase().match(/[a-z0-9]+/g) || [];
  }
  var roots = [];

  function each(root, selector, fn) {
    Array.prototype.forEach.call(root.querySelectorAll(selector), fn);
  }

  function shown(el) {
    return window.getComputedStyle(el).display !== "none";
  }

  function closeDetails(root) {
    each(root, ".protocol-details", function (tr) {
      tr.remove();
    });
    each(root, ".protocol-row-expand", function (button) {
      expanded(button, false);
    });
  }

  function expanded(button, open) {
    button.setAttribute("aria-expanded", open ? "true" : "false");
    button.firstElementChild.textContent = open ? "\u2212" : "+";
  }

  // Header groups span only their visible columns, and a group with none disappears; notes span the
  // visible width. Called after anything that shows or hides columns.
  function layout(root) {
    closeDetails(root);
    each(root, ".protocol-table", function (table) {
      each(table, ".prio-off", function (cell) {
        cell.classList.remove("prio-off");
      });
      keepSomethingVisible(table);
      fitColumns(table);
      var visible = {};
      var count = 0;
      var hidden = false;
      each(table, "thead th[data-col]", function (th) {
        var on = shown(th);
        visible[th.dataset.col] = on;
        if (on) count += 1;
        else hidden = true;
      });
      table.classList.toggle("has-hidden", hidden);
      var labelled = false;
      // Columns outside any group sit under an empty cell (a td: a heading with no text is one a
      // screen reader announces as nothing).
      each(table, ".protocol-group-row [data-cols]", function (th) {
        var span = th.dataset.cols.split(" ").filter(function (col) {
          return visible[col];
        }).length;
        th.hidden = span === 0;
        if (span) th.colSpan = span;
        if (span && th.textContent.trim()) labelled = true;
      });
      // A row of group headings with nothing left to name is only an empty band.
      each(table, ".protocol-group-row", function (row) {
        row.hidden = !labelled;
      });
      var width = count + (hidden ? 1 : 0);
      each(table, ".protocol-note td", function (td) {
        td.colSpan = Math.max(width, 1);
      });
      each(table, ".protocol-row-expand", function (button) {
        button.hidden = !hidden;
      });
    });
    each(root, ".protocol-mode", function (button) {
      button.hidden = !somethingLeftOut(root);
    });
    // A set's chip is pressed while its columns show, whether the reader or the width decided.
    each(root, ".protocol-column-set", function (button) {
      var on = Array.prototype.some.call(
        root.querySelectorAll('.protocol-table thead th[data-set="' + button.dataset.set + '"]'),
        shown
      );
      button.setAttribute("aria-pressed", on ? "true" : "false");
    });
    stickColumns(root);
  }

  function priorityOf(th) {
    var match = /\bprio-(\d+)\b/.exec(th.className);
    return match ? Number(match[1]) : 2;
  }

  function leaveOut(table, th) {
    each(table, '[data-col="' + th.dataset.col + '"]', function (cell) {
      cell.classList.add("prio-off");
    });
  }

  // The short view, on any screen: while a table is wider than its box, the least important columns
  // still shown are left out -- the highest priority number first, all its columns together -- until
  // it fits. Priority 1 always stays. "All columns" shows every one, scrolling in the box.
  function fitColumns(table) {
    var wrap = table.closest(".protocol-table-wrap");
    if (state.full || !wrap || wrap.scrollWidth <= wrap.clientWidth + 1) return;
    // Columns of one set -- every lap, say -- are left out whole or not at all, so the reader
    // never sees laps 1 to 4 with 5 and 6 tucked away. A set the reader turned on stays.
    var sets = {};
    Array.prototype.forEach.call(table.querySelectorAll("thead th[data-col]"), function (th) {
      var free = !th.classList.contains("prio-forced") && !th.classList.contains("col-on");
      if (priorityOf(th) > 1 && shown(th) && free) {
        var key = th.dataset.set || "p" + priorityOf(th);
        (sets[key] = sets[key] || []).push(th);
      }
    });
    var order = Object.keys(sets)
      .map(function (key) {
        return sets[key];
      })
      .sort(function (a, b) {
        return priorityOf(b[0]) - priorityOf(a[0]);
      });
    // The widths are measured once and summed, then checked against the real layout: laying a
    // table of thousands of rows out again for every set would take seconds.
    var widths = order.map(function (set) {
      return set.reduce(function (sum, th) {
        return sum + th.offsetWidth;
      }, 0);
    });
    var overflow = wrap.scrollWidth - wrap.clientWidth;
    var leaveOutSet = function (set) {
      set.forEach(function (th) {
        leaveOut(table, th);
      });
    };
    var i = 0;
    for (var freed = 0; i < order.length && freed < overflow; i += 1) {
      leaveOutSet(order[i]);
      freed += widths[i];
    }
    // The row buttons that open what was left out take a column of their own.
    table.classList.add("has-hidden");
    for (; i < order.length && wrap.scrollWidth > wrap.clientWidth + 1; i += 1) {
      leaveOutSet(order[i]);
    }
  }

  // "All columns" is offered only while there is something to bring back: a column left out, or,
  // with every column shown, a table wider than its box.
  function somethingLeftOut(root) {
    if (root.querySelector(".protocol-table .col-off")) return true;
    if (!state.full) return !!root.querySelector(".protocol-table .prio-off");
    return Array.prototype.some.call(root.querySelectorAll(".protocol-table-wrap"), function (wrap) {
      return wrap.scrollWidth > wrap.clientWidth + 1;
    });
  }

  // A table must never show no column at all: when priorities and switches leave none,
  // its first columns that are switched on stand in, as the server chose at opening.
  function keepSomethingVisible(table) {
    each(table, ".prio-forced", function (cell) {
      cell.classList.remove("prio-forced");
    });
    var heads = Array.prototype.slice.call(table.querySelectorAll("thead th[data-col]"));
    if (heads.some(shown)) return;
    heads
      .filter(function (th) {
        return !th.classList.contains("toggle-off");
      })
      .slice(0, 3)
      .forEach(function (th) {
        each(table, '[data-col="' + th.dataset.col + '"]', function (cell) {
          cell.classList.add("prio-forced");
        });
      });
  }

  // When a table is wider than the screen, its leading place, number and name columns (and
  // the row buttons) stay in view while the rest scrolls, so a time is never read without
  // knowing whose it is. The offsets go into one style element, not onto every cell.
  var stickyStyle = null;
  var STICKY_ROLES = ["role-place", "role-bib", "role-name"];

  function stickColumns(root) {
    if (!stickyStyle) {
      stickyStyle = document.createElement("style");
      stickyStyle.id = "protocol-sticky";
      document.head.appendChild(stickyStyle);
    }
    // Measured unstuck: a stuck cell's offsetLeft includes how far the table is scrolled, so
    // measuring under the old rules would push the columns right by that much on every layout.
    stickyStyle.textContent = "";
    var rules = [];
    each(root, ".protocol-section", function (section) {
      var wrap = section.querySelector(":scope > .protocol-table-wrap");
      if (!wrap || wrap.scrollWidth <= wrap.clientWidth + 1) return;
      var scope = "#" + section.id + " > .protocol-table-wrap ";
      var heads = wrap.querySelectorAll("thead tr:last-child th");
      for (var i = 0; i < heads.length; i += 1) {
        var th = heads[i];
        if (!shown(th)) continue;
        var target;
        if (th.classList.contains("protocol-expand-col")) {
          target = ".protocol-expand-col";
        } else if (STICKY_ROLES.some(function (role) { return th.classList.contains(role); })) {
          target = '[data-col="' + th.dataset.col + '"]';
        } else {
          break;
        }
        rules.push(
          scope + "th" + target + "," + scope + "td" + target +
            "{position:sticky;left:" + th.offsetLeft + "px;z-index:1;background-color:var(--bs-body-bg)}"
        );
      }
    });
    stickyStyle.textContent = rules.join("\n");
  }

  function filter(root) {
    var words = searchWords(state.search);
    each(root, ".protocol-row", function (row) {
      var text = row.dataset.search || "";
      var out =
        words.some(function (word) {
          return text.indexOf(word) === -1;
        }) ||
        (state.group && row.dataset.groupId !== state.group);
      row.classList.toggle("is-filtered", !!out);
      // A row's note and open details follow it directly.
      for (var next = row.nextElementSibling; next && next.dataset.for === row.id; next = next.nextElementSibling) {
        next.classList.toggle("is-filtered", !!out);
      }
    });
    // Innermost sections first, so a section whose children all emptied out empties too.
    var reappeared = false;
    var sections = Array.prototype.slice.call(root.querySelectorAll(".protocol-section")).reverse();
    sections.forEach(function (section) {
      var rows = section.querySelectorAll(".protocol-row");
      if (!rows.length) return;
      var any = Array.prototype.some.call(rows, function (row) {
        return !row.classList.contains("is-filtered");
      });
      if (any && section.classList.contains("is-empty")) reappeared = true;
      section.classList.toggle("is-empty", !any);
    });
    return reappeared;
  }

  function apply(root) {
    Object.keys(state.toggles).forEach(function (id) {
      each(root, '.protocol-table [data-toggle-id="' + id + '"]', function (cell) {
        cell.classList.toggle("toggle-off", !state.toggles[id]);
      });
    });
    each(root, ".protocol-toggle", function (button) {
      button.setAttribute("aria-pressed", state.toggles[button.dataset.toggleId] ? "true" : "false");
    });
    each(root, ".protocol-groups [data-group-id]", function (button) {
      button.setAttribute("aria-pressed", button.dataset.groupId === state.group ? "true" : "false");
    });
    each(root, ".protocol-table", function (table) {
      each(table, "thead th[data-set]", function (th) {
        var choice = state.columns[th.dataset.set];
        each(table, '[data-col="' + th.dataset.col + '"]', function (cell) {
          cell.classList.toggle("col-off", choice === false);
          cell.classList.toggle("col-on", choice === true);
        });
      });
    });
    root.classList.toggle("protocol-full", state.full);
    each(root, ".protocol-mode", function (button) {
      button.setAttribute("aria-pressed", state.full ? "true" : "false");
    });
    filter(root);
    layout(root);
  }

  function toggleDetails(row) {
    var table = row.closest(".protocol-table");
    var button = row.querySelector(".protocol-row-expand");
    if (!table || !button || !table.classList.contains("has-hidden")) return;
    var id = row.id + "-details";
    var open = document.getElementById(id);
    if (open) {
      open.remove();
      expanded(button, false);
      return;
    }
    var list = document.createElement("dl");
    var labels = {};
    each(table, "thead th[data-col]", function (th) {
      labels[th.dataset.col] = th.dataset.label || "";
    });
    each(row, "td[data-col]", function (td) {
      if (shown(td) || !td.textContent.trim()) return;
      var dt = document.createElement("dt");
      dt.textContent = labels[td.dataset.col] || "";
      var dd = document.createElement("dd");
      Array.prototype.forEach.call(td.childNodes, function (node) {
        dd.appendChild(node.cloneNode(true));
      });
      list.appendChild(dt);
      list.appendChild(dd);
    });
    var tr = document.createElement("tr");
    tr.className = "protocol-details";
    tr.id = id;
    tr.setAttribute("data-for", row.id);
    var td = document.createElement("td");
    var visible = 0;
    each(row, "td", function (cell) {
      if (shown(cell)) visible += 1;
    });
    td.colSpan = visible;
    td.appendChild(list);
    tr.appendChild(td);
    row.after(tr);
    expanded(button, true);
  }

  function mount(root) {
    if (!root) return;
    roots = roots.filter(function (r) {
      return document.contains(r);
    });
    roots.push(root);
    root.classList.add("protocol-js");
    var panel = root.querySelector(".protocol-panel");
    if (panel) panel.hidden = false;

    var present = {};
    each(root, ".protocol-toggle", function (button) {
      var id = button.dataset.toggleId;
      present[id] = true;
      if (!(id in state.toggles)) state.toggles[id] = button.dataset.default === "true";
      button.addEventListener("click", function () {
        state.toggles[id] = !state.toggles[id];
        apply(root);
      });
    });
    Object.keys(state.toggles).forEach(function (id) {
      if (!present[id]) delete state.toggles[id];
    });

    var groups = [];
    each(root, ".protocol-groups [data-group-id]", function (button) {
      groups.push(button.dataset.groupId);
      button.addEventListener("click", function () {
        state.group = button.dataset.groupId;
        apply(root);
      });
    });
    if (groups.indexOf(state.group) === -1) state.group = "";

    each(root, ".protocol-search", function (input) {
      try {
        foldTable = JSON.parse(input.dataset.fold || "{}");
      } catch (e) {
        foldTable = {};
      }
      input.value = state.search;
      input.addEventListener("input", function () {
        state.search = input.value;
        // A table the search had hidden when the columns were last fitted was never measured:
        // fit it as it shows again, or it comes back at its full width.
        if (filter(root)) layout(root);
      });
    });
    var sets = {};
    each(root, ".protocol-column-set", function (button) {
      sets[button.dataset.set] = true;
      button.addEventListener("click", function () {
        // What the reader turns on stays on even where it no longer fits, and what they turn
        // off stays off, until "All columns".
        state.columns[button.dataset.set] = button.getAttribute("aria-pressed") !== "true";
        apply(root);
      });
    });
    Object.keys(state.columns).forEach(function (id) {
      if (!sets[id]) delete state.columns[id];
    });
    each(root, ".protocol-mode", function (button) {
      button.addEventListener("click", function () {
        // Every column back, the reader's own choices included; pressed again, the width decides.
        state.full = !state.full;
        state.columns = {};
        apply(root);
      });
    });

    root.addEventListener("click", function (e) {
      var button = e.target.closest(".protocol-row-expand");
      var row = e.target.closest(".protocol-row");
      if (!row || (!button && e.target.closest("a, button"))) return;
      toggleDetails(row);
    });

    apply(root);
  }

  // Fitting depends on the width alone: a phone's address bar coming and going changes only the
  // height, and laying out again then would also close the rows the reader opened.
  var resizeTimer = null;
  var lastWidth = window.innerWidth;
  window.addEventListener("resize", function () {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(function () {
      if (window.innerWidth === lastWidth) return;
      lastWidth = window.innerWidth;
      roots.forEach(layout);
    }, 150);
  });
  // A skin's font arrives after the first layout and sets the text wider or narrower.
  if (document.fonts && document.fonts.ready) {
    document.fonts.ready.then(function () {
      roots.forEach(layout);
    });
  }

  window.ProtocolDocument = { mount: mount };
  mount(document.getElementById("protocol-doc"));
})();
