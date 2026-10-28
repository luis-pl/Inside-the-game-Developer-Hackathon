export function Brand() {
  return (
    <a className="work-brand" href="/" aria-label="Inside the game, home">
      <svg
        viewBox="0 0 32 32"
        width="28"
        height="28"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.5"
        aria-hidden="true"
      >
        <rect x="3" y="5" width="26" height="22" rx="2" />
        <path d="M16 5v22M3 12h5v8H3m26-8h-5v8h5" />
        <circle cx="16" cy="16" r="4" />
      </svg>
      <span>
        inside the game<span className="brand-period">.</span>
      </span>
    </a>
  );
}
