const SVG_SWITCH = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect x="4" y="20" width="56" height="24" rx="3" fill="#1890ff" stroke="#0050b3" stroke-width="1.5"/><circle cx="14" cy="32" r="2.5" fill="#fff"/><circle cx="22" cy="32" r="2.5" fill="#fff"/><circle cx="30" cy="32" r="2.5" fill="#fff"/><circle cx="38" cy="32" r="2.5" fill="#fff"/><circle cx="46" cy="32" r="2.5" fill="#fff"/><circle cx="54" cy="32" r="2.5" fill="#52c41a"/><path d="M18 26 L26 26 M38 26 L46 26" stroke="#fff" stroke-width="1.2"/></svg>`

const SVG_ROUTER = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect x="4" y="28" width="56" height="20" rx="10" fill="#722ed1" stroke="#391085" stroke-width="1.5"/><line x1="16" y1="28" x2="16" y2="12" stroke="#722ed1" stroke-width="2"/><line x1="32" y1="28" x2="32" y2="6" stroke="#722ed1" stroke-width="2"/><line x1="48" y1="28" x2="48" y2="12" stroke="#722ed1" stroke-width="2"/><circle cx="16" cy="10" r="2.5" fill="#722ed1"/><circle cx="32" cy="4" r="2.5" fill="#722ed1"/><circle cx="48" cy="10" r="2.5" fill="#722ed1"/><path d="M14 38 L50 38 M14 38 L18 34 M14 38 L18 42 M50 38 L46 34 M50 38 L46 42" stroke="#fff" stroke-width="1.5" fill="none"/></svg>`

const SVG_SERVER = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect x="12" y="6" width="40" height="52" rx="2" fill="#595959" stroke="#262626" stroke-width="1.5"/><rect x="16" y="10" width="32" height="8" fill="#434343"/><circle cx="44" cy="14" r="1.5" fill="#52c41a"/><rect x="16" y="22" width="32" height="8" fill="#434343"/><circle cx="44" cy="26" r="1.5" fill="#52c41a"/><rect x="16" y="34" width="32" height="8" fill="#434343"/><circle cx="44" cy="38" r="1.5" fill="#faad14"/><rect x="16" y="46" width="32" height="8" fill="#434343"/><circle cx="44" cy="50" r="1.5" fill="#f5222d"/></svg>`

const SVG_FIREWALL = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><path d="M32 6 L54 14 L54 32 Q54 48 32 58 Q10 48 10 32 L10 14 Z" fill="#f5222d" stroke="#a8071a" stroke-width="1.5"/><path d="M22 32 L30 40 L44 24" stroke="#fff" stroke-width="3.5" fill="none" stroke-linecap="round" stroke-linejoin="round"/></svg>`

const SVG_PORT = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect x="14" y="18" width="36" height="28" rx="4" fill="#13c2c2" stroke="#006d75" stroke-width="1.5"/><rect x="22" y="26" width="5" height="10" rx="1" fill="#fff"/><rect x="30" y="26" width="5" height="10" rx="1" fill="#fff"/><rect x="38" y="26" width="5" height="10" rx="1" fill="#fff"/><line x1="32" y1="46" x2="32" y2="56" stroke="#13c2c2" stroke-width="3"/><circle cx="32" cy="58" r="3" fill="#006d75"/></svg>`

const SVG_HYPERVISOR = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect x="6" y="10" width="52" height="12" rx="2" fill="#2f54eb" stroke="#10239e" stroke-width="1"/><rect x="6" y="26" width="52" height="12" rx="2" fill="#597ef7" stroke="#10239e" stroke-width="1"/><rect x="6" y="42" width="52" height="12" rx="2" fill="#85a5ff" stroke="#10239e" stroke-width="1"/><circle cx="12" cy="16" r="1.8" fill="#fff"/><circle cx="12" cy="32" r="1.8" fill="#fff"/><circle cx="12" cy="48" r="1.8" fill="#fff"/><rect x="18" y="14" width="20" height="1.5" fill="#fff"/><rect x="18" y="30" width="20" height="1.5" fill="#fff"/><rect x="18" y="46" width="20" height="1.5" fill="#fff"/></svg>`

const SVG_VM = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect x="6" y="10" width="52" height="36" rx="2" fill="#fa8c16" stroke="#ad4e00" stroke-width="1.5"/><rect x="10" y="14" width="44" height="28" fill="#fff"/><circle cx="14" cy="18" r="1.2" fill="#fa8c16"/><circle cx="18" cy="18" r="1.2" fill="#fa8c16"/><rect x="14" y="23" width="36" height="2" fill="#fa8c16"/><rect x="14" y="28" width="26" height="2" fill="#fa8c16"/><rect x="14" y="33" width="30" height="2" fill="#fa8c16"/><path d="M26 46 L38 46 L36 52 L28 52 Z" fill="#fa8c16"/><rect x="22" y="52" width="20" height="3" rx="1" fill="#fa8c16"/></svg>`

const SVG_ECS = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><path d="M16 40 Q4 40 6 30 Q4 20 16 22 Q18 12 30 14 Q44 10 48 22 Q60 22 58 34 Q60 42 46 42 Z" fill="#1890ff" stroke="#0050b3" stroke-width="1.5"/><rect x="22" y="28" width="22" height="14" rx="1" fill="#fff"/><circle cx="26" cy="32" r="1.3" fill="#1890ff"/><circle cx="26" cy="36" r="1.3" fill="#1890ff"/><rect x="30" y="31" width="12" height="1.5" fill="#1890ff"/><rect x="30" y="35" width="12" height="1.5" fill="#1890ff"/><rect x="30" y="39" width="8" height="1.5" fill="#1890ff"/></svg>`

const SVG_POD = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><polygon points="32,4 56,18 56,44 32,58 8,44 8,18" fill="#326ce5" stroke="#1e3d73" stroke-width="1.5"/><polygon points="32,14 48,23 48,40 32,49 16,40 16,23" fill="none" stroke="#fff" stroke-width="2"/><circle cx="32" cy="31" r="4" fill="#fff"/><path d="M32 18 L32 24 M32 38 L32 44 M20 28 L25 30 M39 32 L44 34" stroke="#fff" stroke-width="1.5"/></svg>`

const SVG_CONTAINER = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect x="4" y="16" width="56" height="36" rx="2" fill="#0db7ed" stroke="#00608c" stroke-width="1.5"/><line x1="12" y1="16" x2="12" y2="52" stroke="#00608c" stroke-width="1.5"/><line x1="20" y1="16" x2="20" y2="52" stroke="#00608c" stroke-width="1.5"/><line x1="28" y1="16" x2="28" y2="52" stroke="#00608c" stroke-width="1.5"/><line x1="36" y1="16" x2="36" y2="52" stroke="#00608c" stroke-width="1.5"/><line x1="44" y1="16" x2="44" y2="52" stroke="#00608c" stroke-width="1.5"/><line x1="52" y1="16" x2="52" y2="52" stroke="#00608c" stroke-width="1.5"/><rect x="4" y="16" width="56" height="6" fill="#00608c" opacity="0.3"/></svg>`

const SVG_APP = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect x="6" y="8" width="52" height="48" rx="3" fill="#eb2f96" stroke="#9e1068" stroke-width="1.5"/><rect x="6" y="8" width="52" height="10" rx="3" fill="#9e1068"/><circle cx="12" cy="13" r="1.5" fill="#fff"/><circle cx="18" cy="13" r="1.5" fill="#fff"/><circle cx="24" cy="13" r="1.5" fill="#fff"/><rect x="12" y="24" width="40" height="3" rx="1" fill="#fff"/><rect x="12" y="32" width="30" height="3" rx="1" fill="#fff"/><rect x="12" y="40" width="36" height="3" rx="1" fill="#fff"/><rect x="12" y="48" width="20" height="3" rx="1" fill="#fff"/></svg>`

const SVG_DEFAULT = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect x="10" y="10" width="44" height="44" rx="4" fill="#bfbfbf" stroke="#595959" stroke-width="1.5"/><text x="32" y="40" text-anchor="middle" font-size="28" fill="#fff" font-family="sans-serif">?</text></svg>`

const ICON_MAP: Record<string, string> = {
  switch: SVG_SWITCH,
  router: SVG_ROUTER,
  server: SVG_SERVER,
  firewall: SVG_FIREWALL,
  port: SVG_PORT,
  hypervisor: SVG_HYPERVISOR,
  vm: SVG_VM,
  ecs: SVG_ECS,
  pod: SVG_POD,
  container: SVG_CONTAINER,
  app: SVG_APP,
}

function toDataUrl(svg: string): string {
  return `data:image/svg+xml;utf8,${encodeURIComponent(svg)}`
}

export function getNodeIconByCode(code: string | null | undefined): string {
  const svg = (code && ICON_MAP[code]) || SVG_DEFAULT
  return toDataUrl(svg)
}
