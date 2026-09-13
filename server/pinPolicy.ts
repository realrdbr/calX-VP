export function requiresPersonalPin(user: { pin?: string; preferences?: { forcePinChange?: boolean } }): boolean {
  return !user.pin || !!user.preferences?.forcePinChange;
}

export function permitsPinSetupRequest(method: string, path: string, username: string): boolean {
  return (method === 'GET' && (path === '/api/session' || path === `/api/users/${encodeURIComponent(username)}`))
    || (method === 'POST' && ['/api/pin', '/api/logout'].includes(path));
}
