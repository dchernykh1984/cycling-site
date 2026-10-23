(function () {
  var picker = document.getElementById('gallery-event-picker');
  if (!picker) return;
  var input = document.getElementById('gallery-event-query');
  var value = document.getElementById('id_competition');
  var menu = document.getElementById('gallery-event-options');
  var summary = document.getElementById('gallery-selected-event');
  var clear = document.getElementById('gallery-clear-event');
  var status = document.getElementById('gallery-event-status');
  var options = [], active = -1, timer, controller;

  function close() {
    clearTimeout(timer);
    if (controller) controller.abort();
    controller = null;
    status.textContent = '';
    menu.hidden = true;
    input.setAttribute('aria-expanded', 'false');
    input.removeAttribute('aria-activedescendant');
    active = -1;
  }

  function facts(container, event) {
    var name = document.createElement('div');
    name.className = 'fw-semibold';
    name.textContent = event.title;
    container.appendChild(name);
    event.details.forEach(function (fact) {
      var line = document.createElement('div');
      line.className = 'small';
      line.textContent = fact.label + ': ' + fact.value;
      container.appendChild(line);
    });
  }

  function select(event) {
    value.value = event ? event.id : '';
    summary.replaceChildren();
    if (event) facts(summary, event);
    else summary.textContent = picker.dataset.none;
    clear.hidden = !event;
    ['ru', 'kk', 'en'].forEach(function (language) {
      document.getElementById('id_title_' + language).placeholder = event ? event.titles[language] : '';
    });
    input.value = '';
    status.textContent = '';
    close();
    value.dispatchEvent(new Event('change', {bubbles: true}));
  }

  function highlight(index) {
    if (menu.hidden) return;
    var buttons = menu.querySelectorAll('[role="option"]');
    active = buttons.length ? (index + buttons.length) % buttons.length : -1;
    buttons.forEach(function (button, i) {
      button.classList.toggle('active', i === active);
      button.setAttribute('aria-selected', String(i === active));
    });
    if (active >= 0) {
      input.setAttribute('aria-activedescendant', buttons[active].id);
      buttons[active].scrollIntoView({block: 'nearest'});
    }
  }

  async function load() {
    if (controller) controller.abort();
    controller = new AbortController();
    var request = controller;
    status.textContent = picker.dataset.loading;
    try {
      var url = new URL(picker.dataset.url, window.location.origin);
      url.searchParams.set('q', input.value);
      var response = await fetch(url, {signal: request.signal, credentials: 'same-origin', cache: 'no-store'});
      if (!response.ok) throw new Error('Search request failed');
      var data = await response.json();
      if (request !== controller || document.activeElement !== input) return;
      options = data.results;
      active = -1;
      input.removeAttribute('aria-activedescendant');
      menu.replaceChildren();
      options.forEach(function (event, index) {
        var button = document.createElement('button');
        button.type = 'button';
        button.className = 'list-group-item list-group-item-action';
        button.id = 'gallery-event-option-' + index;
        button.tabIndex = -1;
        button.setAttribute('role', 'option');
        button.setAttribute('aria-selected', String(String(event.id) === value.value));
        facts(button, event);
        button.addEventListener('click', function () { select(event); input.focus(); close(); });
        menu.appendChild(button);
      });
      menu.hidden = options.length === 0;
      input.setAttribute('aria-expanded', String(!menu.hidden));
      status.textContent = options.length ? (data.has_more ? picker.dataset.more : '') : picker.dataset.empty;
    } catch (error) {
      if (error.name !== 'AbortError' && request === controller) {
        close();
        status.textContent = picker.dataset.error;
      }
    }
  }

  input.addEventListener('focus', load);
  input.addEventListener('input', function () {
    close();
    timer = setTimeout(load, 200);
  });
  input.addEventListener('keydown', async function (event) {
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault();
      if (menu.hidden) await load();
      highlight(active + (event.key === 'ArrowDown' ? 1 : -1));
    } else if (event.key === 'Enter' && !menu.hidden && options.length) {
      event.preventDefault();
      select(options[active < 0 ? 0 : active]);
    } else if (event.key === 'Escape' || event.key === 'Tab') close();
  });
  clear.addEventListener('click', function () { select(null); });
  document.addEventListener('click', function (event) {
    if (!picker.contains(event.target)) close();
  });
  select(JSON.parse(document.getElementById('gallery-selected-event-data').textContent));
}());
