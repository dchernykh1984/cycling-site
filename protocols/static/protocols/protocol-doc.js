// A protocol drawn from its structured document: search, group filter, toggles, short and full
// view, and the details of a row whose columns do not fit.
//
// The reader's choices are kept by the document's own ids, not by position, so a live update that
// adds, removes or reorders groups and toggles (protocol-live.js swaps the whole document in and
// calls mount again) keeps what the reader chose: a group that disappeared falls back to "All", a
// toggle that disappeared is forgotten, a new toggle starts in its default.
(function () {
  "use strict";

  var state = { search: "", group: "", toggles: {}, full: false };
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
      keepSomethingVisible(table);
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
      each(table, ".protocol-group-row th[data-cols]", function (th) {
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

  function filter(root) {
    var query = state.search.trim().toLowerCase();
    each(root, ".protocol-row", function (row) {
      var out =
        (query && (row.dataset.search || "").indexOf(query) === -1) ||
        (state.group && row.dataset.groupId !== state.group);
      row.classList.toggle("is-filtered", !!out);
      // A row's note and open details follow it directly.
      for (var next = row.nextElementSibling; next && next.dataset.for === row.id; next = next.nextElementSibling) {
        next.classList.toggle("is-filtered", !!out);
      }
    });
    // Innermost sections first, so a section whose children all emptied out empties too.
    var sections = Array.prototype.slice.call(root.querySelectorAll(".protocol-section")).reverse();
    sections.forEach(function (section) {
      var rows = section.querySelectorAll(".protocol-row");
      if (!rows.length) return;
      var any = Array.prototype.some.call(rows, function (row) {
        return !row.classList.contains("is-filtered");
      });
      section.classList.toggle("is-empty", !any);
    });
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
      input.value = state.search;
      input.addEventListener("input", function () {
        state.search = input.value;
        filter(root);
      });
    });
    each(root, ".protocol-mode", function (button) {
      button.addEventListener("click", function () {
        state.full = !state.full;
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

  ["(max-width: 767.98px)", "(max-width: 1199.98px)"].forEach(function (query) {
    var list = window.matchMedia(query);
    var relayout = function () {
      roots.forEach(layout);
    };
    if (list.addEventListener) list.addEventListener("change", relayout);
    else if (list.addListener) list.addListener(relayout);
  });

  window.ProtocolDocument = { mount: mount };
  mount(document.getElementById("protocol-doc"));
})();
