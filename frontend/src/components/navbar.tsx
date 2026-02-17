import Link from "next/link";

export default function NavBar() {
  return (
    <nav className="bg-white shadow-sm border-b border-gray-200 flex-shrink-0">
      {/* <div className="max-w-7xl mx-auto px-8 py-4 flex items-center gap-12"> */}
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
          <button className="flex-shrink-0 flex items-center gap-2 px-3 py-2 bg-transparent text-gray-700 rounded-lg font-medium hover:bg-gray-100 hover:shadow-lg transition">
            📷 Scan
          </button>
          <button className="flex-shrink-0 flex items-center gap-2 px-3 py-2 rounded-lg bg-transparent text-gray-700 font-medium hover:bg-gray-100 hover:shadow-lg transition">
            📋 Collection
          </button>
          <button className="flex-shrink-0 flex items-center gap-2 px-3 py-2 rounded-lg bg-transparent text-gray-700 font-medium hover:bg-gray-100 hover:shadow-lg transition">
            📈 Pricing
          </button>
          <button className="flex-shrink-0 flex items-center gap-2 px-3 py-2 rounded-lg bg-transparent text-gray-700 font-medium hover:bg-gray-100 hover:shadow-lg transition">
            ✨ Recommendations
          </button>
        </div>
      </div>
    </nav>
  );
}
