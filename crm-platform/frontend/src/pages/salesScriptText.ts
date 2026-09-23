export const scriptFields = (template: string): string[] => Array.from(new Set(Array.from(template.matchAll(/\{([a-z_]+)\}/g), match => match[1])));
export function customerScriptText(template: string, values: Record<string, string>): { text: string; ready: boolean; missing: string[] } {
  const missing = scriptFields(template).filter(key => !values[key]?.trim());
  const text = template.replace(/\{([a-z_]+)\}/g, (raw, key) => values[key]?.trim() || raw);
  // Also blocks placeholders pasted inside a value and incomplete bracketed placeholders.
  return { text, ready: !!text.trim() && !missing.length && !/[{}\[\]]/.test(text), missing };
}
