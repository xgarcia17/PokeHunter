export default function NavBar() {
    return (
        <nav className="bg-white shadow-sm border-b border-gray-200 flex-shrink-0">
            <div className="max-w-7xl mx-auto px-8 py-4 flex items-center gap-12">
                {/* Logo */}
                <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-lg bg-gradient-to-br from-purple-500 to-blue-500 flex items-center justify-center text-white font-bold text-lg">
                    ⚡
                    </div>
                    <span className="text-xl font-bold text-gray-900">PokéHunter</span>
                </div>
                <div className="flex gap-6 text-sm ">
                    <button className="flex items-center gap-2 px-3 py-2 bg-gradient-to-r from-purple-500 to-blue-500 text-white rounded-lg font-medium hover:shadow-lg transition-shadow">
                        <span>📷</span> Scan
                    </button>
                    <button className="flex items-center gap-2 px-3 py-2 bg-gradient-to-r from-purple-500 to-blue-500 text-white rounded-lg font-medium hover:shadow-lg transition-shadow">
                        <span>📋</span> Collection
                    </button>
                    <button className="flex items-center gap-2 px-3 py-2 bg-gradient-to-r from-purple-500 to-blue-500 text-white rounded-lg font-medium hover:shadow-lg transition-shadow">
                        <span>📈</span> Pricing
                    </button>
                    <button className="flex items-center gap-2 px-3 py-2 bg-gradient-to-r from-purple-500 to-blue-500 text-white rounded-lg font-medium hover:shadow-lg transition-shadow">
                        <span>✨</span> Recommendations
                    </button>
                </div>
            </div>
        </nav>
    )
}