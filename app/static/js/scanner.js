/* QR attendance scanner for the Logistics Team.
   The browser only reads the QR text and sends it to the server. Every
   decision (valid / duplicate / wrong event) is made by the backend. */
(function () {
  'use strict';
  var root = document.querySelector('[data-scanner]');
  if (!root) return;

  var scanUrl = root.getAttribute('data-scan-url');
  var eventId = parseInt(root.getAttribute('data-event-id'), 10);
  var resultBox = document.getElementById('scan-result');
  var startBtn = document.getElementById('scan-start');
  var stopBtn = document.getElementById('scan-stop');
  var idle = document.getElementById('viewfinder-idle');
  var manualForm = document.getElementById('manual-form');
  var manualInput = document.getElementById('manual-value');
  var recent = document.getElementById('recent-scans');
  var attendedEl = document.getElementById('count-attended');
  var registeredEl = document.getElementById('count-registered');

  var scanner = null;
  var busy = false;
  var lastValue = '';
  var lastTime = 0;

  var VIEW = {
    success:     { icon: 'bi-check-circle-fill',  title: 'Checked in' },
    duplicate:   { icon: 'bi-exclamation-triangle-fill', title: 'Already checked in' },
    wrong_event: { icon: 'bi-signpost-split-fill', title: 'Wrong event' },
    cancelled:   { icon: 'bi-x-octagon-fill',      title: 'Registration cancelled' },
    not_open:    { icon: 'bi-lock-fill',           title: 'Event not open' },
    invalid:     { icon: 'bi-x-circle-fill',       title: 'Invalid QR code' },
    error:       { icon: 'bi-wifi-off',            title: 'Could not verify' },
    loading:     { icon: 'bi-hourglass-split',     title: 'Checking...' },
    idle:        { icon: 'bi-qr-code-scan',        title: 'Ready to scan' }
  };

  function show(state, message) {
    var view = VIEW[state] || VIEW.error;
    resultBox.className = 'ch-result state-' + state;
    resultBox.setAttribute('role', state === 'success' ? 'status' : 'alert');
    resultBox.innerHTML = '';
    var icon = document.createElement('i');
    icon.className = 'bi ' + view.icon;
    icon.setAttribute('aria-hidden', 'true');
    var body = document.createElement('div');
    var h = document.createElement('h3');
    h.textContent = view.title;
    var p = document.createElement('p');
    p.textContent = message;
    body.appendChild(h);
    body.appendChild(p);
    resultBox.appendChild(icon);
    resultBox.appendChild(body);
  }

  function addRecent(data) {
    if (!recent) return;
    var empty = document.getElementById('recent-empty');
    if (empty) empty.remove();
    var li = document.createElement('li');
    li.className = 'ch-row';
    var left = document.createElement('div');
    var name = document.createElement('strong');
    name.textContent = data.student_name;
    var code = document.createElement('span');
    code.className = 'ch-sub ch-code';
    code.textContent = data.reg_code;
    left.appendChild(name);
    left.appendChild(code);
    var time = document.createElement('span');
    time.className = 'ch-badge ch-badge-success';
    time.textContent = data.scanned_at;
    li.appendChild(left);
    li.appendChild(time);
    recent.insertBefore(li, recent.firstChild);
    while (recent.children.length > 8) recent.removeChild(recent.lastChild);
  }

  function submit(value) {
    value = (value || '').trim();
    if (!value || busy) return;
    busy = true;
    show('loading', 'Verifying with the server...');

    fetch(scanUrl, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': window.CH.csrfToken() },
      credentials: 'same-origin',
      body: JSON.stringify({ event_id: eventId, value: value })
    })
      .then(function (response) { return response.json(); })
      .then(function (data) {
        show(data.status, data.message);
        if (data.status === 'success') {
          addRecent(data);
          if (navigator.vibrate) navigator.vibrate(120);
        } else if (navigator.vibrate) {
          navigator.vibrate([80, 60, 80]);
        }
        if (typeof data.attended === 'number') {
          attendedEl.textContent = data.attended;
          registeredEl.textContent = data.registered;
        }
      })
      .catch(function () {
        show('error', 'Network problem. Nothing was recorded. Try scanning again.');
      })
      .finally(function () {
        window.setTimeout(function () { busy = false; }, 1500);
      });
  }

  function onScan(text) {
    var now = Date.now();
    if (text === lastValue && now - lastTime < 4000) return; /* same code held in view */
    lastValue = text;
    lastTime = now;
    submit(text);
  }

  function setRunning(running) {
    startBtn.classList.toggle('d-none', running);
    stopBtn.classList.toggle('d-none', !running);
    if (idle) idle.classList.toggle('d-none', running);
  }

  function start() {
    if (typeof Html5Qrcode === 'undefined') {
      show('error', 'The camera scanner library did not load. Use manual entry below.');
      return;
    }
    if (!window.isSecureContext) {
      show('error', 'Camera access needs HTTPS or localhost. Use manual entry below.');
      return;
    }
    scanner = scanner || new Html5Qrcode('reader');
    scanner.start(
      { facingMode: 'environment' },
      { fps: 10, qrbox: { width: 240, height: 240 } },
      onScan,
      function () { /* ignore frames without a code */ }
    ).then(function () {
      setRunning(true);
      show('idle', 'Hold a student QR code in front of the camera.');
    }).catch(function () {
      show('error', 'Could not open the camera. Allow camera permission or use manual entry.');
    });
  }

  function stop() {
    if (!scanner) return;
    scanner.stop().then(function () { setRunning(false); }).catch(function () { setRunning(false); });
  }

  startBtn.addEventListener('click', start);
  stopBtn.addEventListener('click', stop);

  manualForm.addEventListener('submit', function (event) {
    event.preventDefault();
    submit(manualInput.value);
    manualInput.value = '';
    manualInput.focus();
  });

  show('idle', 'Start the camera, or type a registration ID below.');
})();
