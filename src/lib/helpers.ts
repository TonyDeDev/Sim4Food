export function initials(first: string, last: string): string {
  return ((first || " ")[0] + (last || " ")[0]).toUpperCase();
}

// Used on the login screen, where we don't collect a name up front —
// this is a placeholder until a real backend returns the account's name.
export function nameFromEmail(email: string): { first: string; last: string } {
  const local = email.split("@")[0] || "friend";
  const parts = local.split(/[.\-_0-9]+/).filter(Boolean);
  const cap = (w: string) => w.charAt(0).toUpperCase() + w.slice(1);

  if (parts.length >= 2) return { first: cap(parts[0]), last: cap(parts[1]) };
  if (parts.length === 1) return { first: cap(parts[0]), last: "Owner" };
  return { first: "Your", last: "Account" };
}

export function generateOtp(): string {
  return String(Math.floor(100000 + Math.random() * 900000));
}

export const swatchPalette = [
  "#31e992", // Spring Green
  "#000000", // Press Black
  "#bed4fb", // Cornflower Wash
  "#d2ddd2", // Sage Border
  "#edfe5e", // Highlighter Lime
];
