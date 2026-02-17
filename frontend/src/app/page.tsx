export default function Home() {
  return (
    <div className="h-screen bg-gradient-to-br from-purple-100 via-blue-50 to-purple-50 flex flex-col overflow-hidden">
      {/* Navigation Bar */}
      <nav className="bg-white shadow-sm border-b border-gray-200 flex-shrink-0">
        <div className="max-w-7xl mx-auto px-8 py-4 flex items-center gap-12">
          {/* Logo */}
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-gradient-to-br from-purple-500 to-blue-500 flex items-center justify-center text-white font-bold text-lg">
              ⚡
            </div>
            <span className="text-xl font-bold text-gray-900">PokéHunter</span>
          </div>

          {/* Navigation Items */}
          <div className="flex gap-6 text-sm">
            <button className="flex items-center gap-2 px-3 py-2 bg-gradient-to-r from-purple-500 to-blue-500 text-white rounded-lg font-medium hover:shadow-lg transition-shadow">
              <span>📷</span> Scan
            </button>
            <button className="text-gray-700 font-medium hover:text-gray-900 transition-colors">
              📋 Collection
            </button>
            <button className="text-gray-700 font-medium hover:text-gray-900 transition-colors">
              📈 Pricing
            </button>
            <button className="text-gray-700 font-medium hover:text-gray-900 transition-colors">
              ✨ Recommendations
            </button>
          </div>
        </div>
      </nav>

      {/* Main Content */}
      <main className="flex-1 overflow-auto max-w-7xl mx-auto w-full px-8 py-6">
        <div className="bg-white rounded-2xl shadow-lg p-8 h-full">
          <h1 className="text-3xl font-bold text-gray-900 mb-2">
            Card Scanner
          </h1>
          <p className="text-base text-gray-600 mb-6">
            Upload a photo of your Pokémon card for instant identification and
            pricing
          </p>

          {/* Upload Section */}
          <div className="border-2 border-dashed border-gray-300 rounded-xl p-8 text-center hover:border-purple-400 transition-colors">
            <div className="text-5xl mb-3">📷</div>
            <h2 className="text-lg font-semibold text-gray-900 mb-2">
              Upload Card Image
            </h2>
            <p className="text-sm text-gray-600 mb-4">
              Supports JPEG and PNG formats. Processing takes 5-10 seconds.
            </p>
            <button className="bg-gray-900 text-white px-6 py-2 text-sm rounded-lg font-medium hover:bg-gray-800 transition-colors inline-flex items-center gap-2 cursor-pointer">
              <span>⬆️</span> Upload Image
            </button>
            <p className="text-xs text-gray-500 mt-3">or drag and drop</p>
          </div>
        </div>
      </main>
    </div>
  );
}
