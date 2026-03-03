import NavBar from "@/components/navbar";

export default function RecommendationsPage() {
  return (
    <div className="h-screen bg-gradient-to-br from-purple-100 via-blue-50 to-purple-50 flex flex-col overflow-hidden">
      {/* Navigation Bar */}
      <NavBar currentPage={"recommendations"} />
      {/* Main Content of Page : Card Recommendations */}
      <div className="flex-1 my-4 overflow-auto max-w-7xl mx-auto w-[80%] px-8 py-6">
      </div>
    </div>
  );
}
