/**
 * Top application header displaying the Food Recall Monitor brand title.
 */

/**
 * Renders the site-wide emerald header bar with the product name.
 *
 * @returns Header element.
 */
export default function Header() {
  return (
    <header className="border-b border-emerald-700 bg-emerald-600 px-6 py-8 shadow-sm">
      <div className="mx-auto flex max-w-7xl justify-center">
        <h1 className="text-center text-3xl font-bold tracking-tight text-white">
          Food Recall Monitor
        </h1>
      </div>
    </header>
  );
}
