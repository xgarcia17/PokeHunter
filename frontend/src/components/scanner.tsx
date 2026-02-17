export default function Scanner() {
    return (
        <div className="bg-white rounded-2xl shadow-lg p-8 h-full">
          <h1 className="text-3xl font-bold text-gray-900 mb-2">
            PokéCard Scanner
          </h1>
          <p className="text-base text-gray-600 mb-6">
            Upload a photo of your Pokémon card for instant identification and
            pricing
          </p>

          {/* Upload Section */}
          <div className="border-2 border-dashed border-gray-300 rounded-xl p-8 text-center hover:border-purple-400 transition-colors">
            <div className="text-5xl mb-3">📷</div>
            <h2 className="text-lg font-semibold text-gray-900 mb-2">
              Upload Image of Your Pokémon Card
            </h2>
            <p className="text-sm text-gray-600 mb-4">
              Supports JPEG and PNG formats. Processing may take up to 5-10 seconds.
            </p>
            <button className="bg-gray-900 text-white px-6 py-2 text-sm rounded-lg font-medium hover:bg-gray-800 transition-colors inline-flex items-center gap-2 cursor-pointer">
              <span>⬆️</span> Upload Image
            </button>
            <p className="text-xs text-gray-500 mt-3">or drag and drop</p>
          </div>
        </div>
    );
}