export * from './scenario-v3.mjs';
import { pathToFileURL } from 'node:url';
import { seed } from './load-v3.mjs';
if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) await seed({replace:process.argv.includes('--replace-demo')});
