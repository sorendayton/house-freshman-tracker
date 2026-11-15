// Prints data.js as JSON so the Python checks can read it: node scripts/read_data.js data.js
const fs = require("fs");
const vm = require("vm");

const context = { window: {} };
vm.runInNewContext(fs.readFileSync(process.argv[2], "utf8"), context);
if (!Array.isArray(context.window.FRESHMEN)) {
  throw new Error("data.js did not set window.FRESHMEN to a list");
}
process.stdout.write(JSON.stringify({
  members: context.window.FRESHMEN,
  changelog: context.window.CHANGELOG || [],
}));
