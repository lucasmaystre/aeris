// aeris: small browser-side behaviour, loaded on every page after htmx.

// Show <time datetime="..."> elements in the viewer's timezone, e.g. "2026-10-09 19:59", with the
// full date and timezone as a tooltip. The server renders them in UTC as a fallback.
function localizeTimes(root) {
  const pad = (number) => String(number).padStart(2, "0");
  for (const element of root.querySelectorAll("time[datetime]")) {
    const moment = new Date(element.getAttribute("datetime"));
    if (Number.isNaN(moment.getTime())) continue;
    element.textContent =
      `${moment.getFullYear()}-${pad(moment.getMonth() + 1)}-${pad(moment.getDate())} ` +
      `${pad(moment.getHours())}:${pad(moment.getMinutes())}`;
    element.title = moment.toLocaleString(undefined, {
      weekday: "long", year: "numeric", month: "long", day: "numeric",
      hour: "2-digit", minute: "2-digit", timeZoneName: "short",
    });
  }
}

// Runs on the initial page and on every fragment htmx swaps in.
htmx.onLoad(localizeTimes);
