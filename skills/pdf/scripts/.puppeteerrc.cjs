// Tell puppeteer not to download Chrome during `npm install`.
// mmdc (mermaid-cli) uses puppeteer-core and relies on PUPPETEER_EXECUTABLE_PATH
// (set to /usr/bin/google-chrome-stable in CI) at runtime.
module.exports = {
  skipDownload: true,
};
