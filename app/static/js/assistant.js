/* AI Event Assistant chat widget.
   Markup: <div data-ai-chat data-event-id="3"> ... [data-chat-log] [data-chat-form] ...
   An optional <select data-chat-event> switches the event being asked about. */
(function () {
  'use strict';
  var root = document.querySelector('[data-ai-chat]');
  if (!root) return;

  var log = root.querySelector('[data-chat-log]');
  var form = root.querySelector('[data-chat-form]');
  var input = form.querySelector('input[name="question"]');
  var sendButton = form.querySelector('button[type="submit"]');
  var select = root.querySelector('[data-chat-event]');
  var busy = false;

  function eventId() { return select ? select.value : root.getAttribute('data-event-id'); }

  function scrollDown() { log.scrollTop = log.scrollHeight; }

  function addMessage(kind, text) {
    var el = document.createElement('div');
    el.className = 'ch-msg ' + (kind === 'user' ? 'ch-msg-user' : 'ch-msg-ai');
    el.textContent = text;           /* textContent: never insert HTML from the server */
    log.appendChild(el);
    scrollDown();
    return el;
  }

  function addTyping() {
    var el = document.createElement('div');
    el.className = 'ch-msg ch-msg-ai ch-typing';
    el.setAttribute('aria-label', 'Assistant is typing');
    el.innerHTML = '<span></span><span></span><span></span>';
    log.appendChild(el);
    scrollDown();
    return el;
  }

  function renderAnswer(data) {
    var el = addMessage('ai', data.answer);
    if (!data.found) el.classList.add('not-found');

    if (data.sources && data.sources.length) {
      var row = document.createElement('div');
      row.className = 'ch-msg-sources';
      var label = document.createElement('span');
      label.textContent = 'Source:';
      row.appendChild(label);
      data.sources.forEach(function (source) {
        var chip = document.createElement('span');
        chip.className = 'ch-chip';
        chip.textContent = source;
        row.appendChild(chip);
      });
      el.appendChild(row);
    }
    if (data.note) {
      var note = document.createElement('div');
      note.className = 'ch-msg-note';
      note.textContent = data.note;
      el.appendChild(note);
    }
    scrollDown();
  }

  function setBusy(state) {
    busy = state;
    sendButton.disabled = state;
    input.disabled = state;
    if (!state) input.focus();
  }

  function ask(question) {
    if (busy || !question.trim()) return;
    setBusy(true);
    addMessage('user', question);
    var typing = addTyping();

    fetch('/api/events/' + encodeURIComponent(eventId()) + '/ask', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': window.CH.csrfToken()
      },
      credentials: 'same-origin',
      body: JSON.stringify({ question: question })
    })
      .then(function (response) {
        return response.json().then(function (data) { return { ok: response.ok, data: data }; });
      })
      .then(function (result) {
        typing.remove();
        if (!result.ok) {
          var err = addMessage('ai', result.data.error || 'Something went wrong. Please try again.');
          err.classList.add('not-found');
        } else {
          renderAnswer(result.data);
        }
      })
      .catch(function () {
        typing.remove();
        addMessage('ai', 'Could not reach CollegeHub. Check your connection and try again.')
          .classList.add('not-found');
      })
      .finally(function () { setBusy(false); });
  }

  form.addEventListener('submit', function (event) {
    event.preventDefault();
    var question = input.value;
    input.value = '';
    ask(question);
  });

  root.querySelectorAll('[data-suggest]').forEach(function (button) {
    button.addEventListener('click', function () { ask(button.getAttribute('data-suggest')); });
  });

  if (select) {
    select.addEventListener('change', function () {
      log.innerHTML = '';
      addMessage('ai', 'Now answering questions about: ' + select.options[select.selectedIndex].text);
    });
  }
})();
