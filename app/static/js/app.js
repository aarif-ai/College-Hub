/* CollegeHub shared behaviour (vanilla JS, no dependencies). */
(function () {
  'use strict';

  /* Confirm dialogs: <form data-confirm="Are you sure?"> */
  document.addEventListener('submit', function (event) {
    var form = event.target;
    if (!(form instanceof HTMLFormElement)) return;

    var message = form.getAttribute('data-confirm');
    if (message && !window.confirm(message)) {
      event.preventDefault();
      return;
    }

    /* Loading state: stops double submits and shows progress. */
    var button = event.submitter || form.querySelector('button[type="submit"]');
    if (button && !form.hasAttribute('data-no-loading')) {
      button.classList.add('is-loading');
      window.setTimeout(function () { button.classList.remove('is-loading'); }, 8000);
    }
  });

  /* Success messages fade away; errors stay until dismissed. */
  document.querySelectorAll('.alert-success.alert-dismissible').forEach(function (el) {
    window.setTimeout(function () {
      if (window.bootstrap && document.body.contains(el)) {
        bootstrap.Alert.getOrCreateInstance(el).close();
      }
    }, 7000);
  });

  /* Copy to clipboard: <button data-copy="text"> */
  document.addEventListener('click', function (event) {
    var trigger = event.target.closest('[data-copy]');
    if (!trigger || !navigator.clipboard) return;
    navigator.clipboard.writeText(trigger.getAttribute('data-copy')).then(function () {
      var original = trigger.innerHTML;
      trigger.innerHTML = '<i class="bi bi-check2"></i> Copied';
      window.setTimeout(function () { trigger.innerHTML = original; }, 1600);
    });
  });

  /* Demo account helper on the login page. */
  document.addEventListener('click', function (event) {
    var fill = event.target.closest('[data-fill-login]');
    if (!fill) return;
    var email = document.getElementById('f-identifier');
    var password = document.getElementById('f-password');
    if (email) email.value = fill.getAttribute('data-fill-login');
    if (password && fill.hasAttribute('data-fill-password')) {
      password.value = fill.getAttribute('data-fill-password');
    }
    if (password) password.focus();
  });

  /* Character counter: <textarea data-counter="#target"> */
  document.querySelectorAll('textarea[data-counter]').forEach(function (area) {
    var target = document.querySelector(area.getAttribute('data-counter'));
    if (!target) return;
    var update = function () { target.textContent = area.value.length + ' / ' + area.maxLength; };
    area.addEventListener('input', update);
    update();
  });
})();

/* Helper used by the other scripts. */
window.CH = window.CH || {};
window.CH.csrfToken = function () {
  var meta = document.querySelector('meta[name="csrf-token"]');
  return meta ? meta.getAttribute('content') : '';
};
