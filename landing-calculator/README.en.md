# landing-calculator

[Русский](README.md) · **English**

A one-page site for Polden, a construction company, with a house price calculator and a lead form. The company doesn't exist, and the prices and contacts on the page are placeholders. The estimate is built line by line, the phone field has an input mask, and a serverless function forwards the lead to Telegram and/or e-mail. The code is HTML, CSS and JS with no build step and no npm dependencies, and the page is 37 KB gzipped (not counting the Manrope font from Google Fonts).

Demo: https://sinnercode228.github.io/portfolio/landing-calculator/

![Calculator: a total of 5 826 000 ₽ and the line-by-line breakdown](docs/screenshot-calculator.jpg)

## An estimate built from rounded lines

Prices, coefficients and build times live in [`js/config.js`](js/config.js), and the `calculate` function in [`js/calc.js`](js/calc.js) builds the estimate from them. Each line of the estimate is rounded separately:

```text
price per m² = round(technology price × floors coef., 10)   coef.: 1 floor — 1, 2 floors — 0.94
shell        = round(area × price per m², 1000)
finishing    = round(shell × (multiplier − 1), 1000)        shell 1, whitebox 1.3, turnkey 1.65
slab         = round(ceil(area / floors × 1.1 − 1e-9) × 7500, 1000)
terrace      = m² × 12 000
garage       = 950 000
total        = sum of the lines
```

I don't round the total. It's the sum of lines that are already rounded, and the breakdown always adds up to it. The test «сумма строк разбивки всегда равна итогу (перебор комбинаций)» ("the breakdown lines always add up to the total, all combinations") in [`tests/calc.test.js`](tests/calc.test.js) checks this on 360 combinations (4 technologies × 3 finish levels × 2 floor counts × 5 areas × 3 option sets).

In JS, `100 * 1.1` gives `110.00000000000001`, which is why the slab formula has `− 1e-9`. Without that correction, `Math.ceil` would come up with 111 m² of slab for a single-story 100 m² house, and 833 000 ₽ instead of 825 000. The area is a whole number and there are one or two floors, so the fractional part of the exact value is either zero or at least 0.05, and the correction doesn't affect it.

The defaults (aerated concrete, 120 m², one floor, white box, slab) come to 3 720 000 + 1 116 000 + 990 000 = 5 826 000 ₽, as in the screenshot. The first test in `calc.test.js` checks this same number.

## Link to a calculation

The «Скопировать ссылку на расчёт» ("Copy link to the calculation") button writes the calculator's 7 parameters to the URL with `history.replaceState`. When someone opens a link like that, `decodeState` runs them through the same `normalizeInput` as the form input. The `tech`, `finish` and `floors` values are looked up in the config with `hasOwnProperty`, so `?tech=__proto__` gives the default, aerated concrete. A plain `cfg.technologies[tech]` check would let that key through (it resolves to `Object.prototype`), and `calculate` would crash with a TypeError.

## Form and serverless handler

The `+7 (___) ___-__-__` mask is built from pure functions in [`js/form-utils.js`](js/form-utils.js). A leading 8 becomes 7, the cursor doesn't jump to the end when you edit the middle of the number, and Backspace right after a parenthesis, space or hyphen deletes the nearest digit to the left. In the demo, `leadEndpoint` in `config.js` is empty and the lead goes nowhere: the success screen shows as usual, and the lead's JSON is printed to the browser console.

Leads are handled by [`serverless/telegram-lead.mjs`](serverless/telegram-lead.mjs), a `handleLead(request, env)` function on the Web Fetch API. A request with a body longer than 20 000 characters gets a 413 before `JSON.parse` even runs. If the hidden honeypot field `website` is filled in, the spam bot gets a 200 `{ ok: true }`, but nothing is sent to Telegram or e-mail. The server checks the phone again against `^\+7\d{10}$` and the name and comment by length, and responds with 422 on failure.

The phone number in the message comes from the validated `phone`, not from the client's `phoneFormatted`. The message is sent with `parse_mode: 'HTML'`, so the fields go through `escapeHtml`. They're truncated before escaping, because Telegram counts its 4096-character limit on the text after HTML entities are parsed. The Telegram message and the Resend e-mail go out in parallel (`Promise.allSettled`), and a 502 comes back only if neither channel got through.

### Setting up lead delivery

The URL of the deployed handler goes in `leadEndpoint` in [`js/config.js`](js/config.js). On Cloudflare Workers the file works as is via `export default { fetch }`; Vercel and Netlify need a wrapper that passes `POST` and `OPTIONS` requests to `handleLead(req, process.env)`. Telegram is enabled with the `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` variables, e-mail through Resend with `RESEND_API_KEY` and `LEAD_EMAIL_TO` (the sender goes in `LEAD_EMAIL_FROM`). `ALLOWED_ORIGIN` goes into the CORS header. If no channel is configured, the handler responds with 500.

What's missing: rate limiting (the `website` honeypot is the only spam protection) and recalculating the estimate on the server, so `calculation.summary` goes to Telegram exactly as the client sent it, apart from truncation and escaping. `ALLOWED_ORIGIN` defaults to `*`; for a real site you need to set it.

## UMD and tests in Node

The scripts are included with plain `<script defer>` tags, and `index.html` opens with a double-click. `config.js`, `calc.js` and `form-utils.js` are written as UMD: in the browser they put an object on `window` (`HOUSE_CONFIG`, `HouseCalc`, `FormUtils`), and in Node they export it through `module.exports`. The tests `require()` the same files the page loads, with no jsdom and no browser. For the lead handler, the tests pass a stubbed `fetch` as the third argument, and nothing goes out to the network.

`app.js` wires the pure functions to the page; its behavior (event handlers, animation, focus) isn't covered by tests. [`tests/page.test.js`](tests/page.test.js) reads `index.html` and `app.js` as text and uses regexes to check that ids are unique, files from `src`/`href` exist, fields have labels, and the project cards' captions match their presets. Another test in the same file makes sure HTML, CSS, JS and the favicon together stay under 50 KB gzipped.

There are 49 tests in total, on the built-in `node:test`: 14 for the calculation ([`tests/calc.test.js`](tests/calc.test.js)), 9 for the mask and the form ([`tests/form-utils.test.js`](tests/form-utils.test.js)), 13 for the handler ([`tests/serverless.test.mjs`](tests/serverless.test.mjs)), 11 for the markup ([`tests/page.test.js`](tests/page.test.js)) and 2 for the dev server ([`tests/serve.test.mjs`](tests/serve.test.mjs)).

## Accessibility

The total is copied into a hidden element with `aria-live="polite"` 700 ms after the last change, so a screen reader doesn't read out every step of the slider. The area slider itself has an `aria-valuetext` with the correct Russian plural form («120 квадратных метров», "120 square meters"). With `prefers-reduced-motion`, animations and transitions drop to 0.01 ms, and the total changes at once, with no counting animation.

## Running locally

```bash
# without Node: open index.html in a browser
npm start            # dev server on node:http, http://localhost:8080
npm start -- 3000    # a different port
npm test             # Node ≥ 22, no dependencies
```

---

Built by Грешный Котик (sinnercode). I take freelance work like this: Telegram [@sinnercode](https://t.me/sinnercode). License: [MIT](LICENSE).
