/**
 * Pages kept out of the live site until they're ready to come back (docs/tasks.md M16). Nothing is
 * removed: the code, the routes and the data files all stay, and `npm run dev` still shows them, so
 * they can be worked on. To bring one back, take it off this list.
 */
const HIDDEN = new Set(['/coaches', '/build'])

export const isHidden = (path: string) => !import.meta.env.DEV && HIDDEN.has(path)
