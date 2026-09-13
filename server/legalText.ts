export function renderLegalText(template: string, values: Record<string, string | undefined>): string {
  return template.replace(/\{([A-Z_]+)\}(\.)?/g, (_, key: string, period: string | undefined) => {
    const value = values[key]?.trim() || 'Vom Betreiber noch zu ergänzen';
    return value + (period && !/[.!?…]$/.test(value) ? '.' : '');
  });
}
