// Holds one persistent native-messaging port open to oldbook-firefox-theme-host
// for as long as this window lives, and applies whatever colors it sends.
// The host, not this script, decides when a fresh theme is worth relaying; a
// dropped port (host exited, browser restarted the extension) just reconnects
// a few seconds later rather than leaving the window on a stale palette.
function apply(message) {
  if (message && message.colors) {
    browser.theme.update({colors: message.colors});
  }
}

function connect() {
  let port;
  try {
    port = browser.runtime.connectNative('oldbook_theme');
  } catch (error) {
    setTimeout(connect, 5000);
    return;
  }
  port.onMessage.addListener(apply);
  port.onDisconnect.addListener(() => setTimeout(connect, 3000));
}

connect();
