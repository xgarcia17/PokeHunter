import Link from "next/link";
import clsx from "clsx";


type Page = "scan" | "collection" | "pricing" | "recommendations";

interface NavBarProps { currentPage: Page; }

const MINI_BUTTON_CLASSNAME =
  "flex-shrink-0 flex items-center gap-2 px-3 py-2 rounded-lg bg-transparent text-gray-700 font-medium hover:bg-gray-100 hover:shadow-lg transition cursor-pointer";

const linkData: Record<Page, { href: string; label: string }> = {
  scan: { href: "/", label: "📷 Scan" },
  collection: { href: "/collection", label: "📋 Collection" },
  pricing: { href: "/pricing", label: "📈 Pricing" },
  recommendations: { href: "/recommendations", label: "✨ Recommendations" },
};


function populateNavBar(currentPage: Page) {
  // return an array of <Link> elements, ensuring the caller can render them
  return (Object.keys(linkData) as Page[]).map((page) => {
    const { href, label } = linkData[page];
    return (
      <Link
        key={page}
        href={href}
        className={clsx(
          MINI_BUTTON_CLASSNAME,
          page === currentPage && "bg-gradient-to-br from-purple-500 to-blue-500 text-white"
        )}
      >
        {label}
      </Link>
    );
  });
}

export default function NavBar({ currentPage }: NavBarProps) {
  return (
    <nav className="bg-white shadow-sm border-b border-gray-200 flex-shrink-0">
      <div className="w-full max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-3 flex flex-wrap md:flex-nowrap items-center justify-center gap-4 sm:gap-6 md:gap-8 lg:gap-12">
        {/* Logo */}
        <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-transparent hover:bg-gray-100 hover:shadow-lg transition mr-auto">
          <Link href="/" aria-label="Home" className="flex items-center gap-3">
            <div className="w-[100%] h-[100%] rounded-lg bg-gradient-to-br from-purple-500 to-blue-500 flex items-center justify-center text-white font-bold text-lg">
              ⚡
            </div>
            <span className="text-xl font-bold text-gray-900">PokéHunter</span>
          </Link>
        </div>
        {/* Navigation Buttons */}
        <div className="flex gap-6 text-sm mx-auto">
          {populateNavBar(currentPage)}
        </div>
      </div>
    </nav>
  );
}
