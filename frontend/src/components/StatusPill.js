export function StatusPill({ status }) {
  const label = { VALID: "Valid", EXPIRED: "Expired", NEEDS_REVIEW: "Needs Review", INSUFFICIENT: "Insufficient" }[status] || status;
  return <span className={`status-pill status-${status}`} data-testid={`status-${status}`}>{label}</span>;
}
